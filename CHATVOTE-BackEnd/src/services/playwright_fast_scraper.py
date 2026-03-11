# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Fast async Playwright scraper with markdownify for HTML→markdown conversion.

Uses a shared browser instance across all concurrent scrapes (no subprocess per
candidate). BFS crawl: sitemap.xml → homepage → internal links, max depth 2,
max 15 pages + 5 PDFs per site.

Speed gains vs. the old subprocess approach:
- Single browser shared across all candidates (not 229 separate launches)
- domcontentloaded + 1.5s wait (not networkidle + 3s)
- No scrolling (save ~2s per page)
- No delay between pages within same site
- Async throughout
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from playwright.async_api import Browser, BrowserContext, async_playwright

from src.models.candidate import Candidate

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

MAX_PAGES = 15
MAX_DEPTH = 2
MAX_PDFS = 5
PAGE_TIMEOUT = 15000  # 15s
MIN_CONTENT_LENGTH = 80
MAX_CONTENT_LENGTH = 30000

# URL patterns to skip (non-content pages)
_SKIP_PATTERNS = re.compile(
    r"/(login|logout|signin|signout|register|signup|search|cart|shop|"
    r"account|profile|password|reset|confirm|unsubscribe|print|share|"
    r"feed|rss|sitemap\.xml|robots\.txt)",
    re.IGNORECASE,
)

# Cookie accept button selectors (French sites)
_COOKIE_SELECTORS = [
    "button:has-text('Accepter')",
    "button:has-text('Tout accepter')",
    "button:has-text('J\\'accepte')",
    "button:has-text('Accept')",
    "button:has-text('OK')",
    "button:has-text('Fermer')",
    "[id*='cookie'] button",
    "[class*='cookie'] button",
    "[id*='consent'] button",
    "[class*='consent'] button",
    "[id*='gdpr'] button",
    "[class*='gdpr'] button",
]


# ── Data classes (same interface as candidate_website_scraper) ─────────────


@dataclass
class ScrapedPage:
    url: str
    title: str
    content: str
    page_type: str = "html"
    depth: int = 0
    content_length: int = 0

    def __post_init__(self):
        self.content_length = len(self.content)


@dataclass
class ScrapedWebsite:
    candidate_id: str
    website_url: str
    pages: List[ScrapedPage] = field(default_factory=list)
    error: Optional[str] = None
    stats: Dict[str, int] = field(default_factory=dict)
    backend: str = ""  # "playwright", "playwright-fast", or "firecrawl"

    @property
    def total_content_length(self) -> int:
        return sum(p.content_length for p in self.pages)

    @property
    def is_successful(self) -> bool:
        return len(self.pages) > 0


# ── HTML → Markdown helpers ────────────────────────────────────────────────


def _html_to_markdown(html: str, url: str) -> tuple[str, str]:
    """Convert HTML to clean markdown. Returns (title, markdown_content)."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "noscript", "nav", "footer", "header", "iframe"]):
        tag.decompose()
    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else ""
    body = soup.find("body") or soup
    markdown_text = md(str(body), heading_style="atx", bullets="-", strip=["img"])
    markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()
    content = f"# {title}\n\n> Source: {url}\n\n{markdown_text}"
    return title, content


def _extract_links(html: str, base_url: str) -> tuple[List[str], List[str]]:
    """Extract internal page links and PDF URLs from HTML.

    Returns (page_links, pdf_links).
    """
    soup = BeautifulSoup(html, "html.parser")
    base_domain = urlparse(base_url).netloc
    page_links: List[str] = []
    pdf_links: List[str] = []

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)

        # Same domain only
        if parsed.netloc != base_domain:
            continue

        # Strip fragment
        clean_url = abs_url.split("#")[0].rstrip("/")
        if not clean_url:
            continue

        # PDF detection
        if parsed.path.lower().endswith(".pdf"):
            pdf_links.append(clean_url)
            continue

        # Skip non-content patterns
        if _SKIP_PATTERNS.search(parsed.path):
            continue

        # Only http/https
        if parsed.scheme not in ("http", "https"):
            continue

        page_links.append(clean_url)

    return page_links, pdf_links


async def _fetch_sitemap_urls(base_url: str, session: aiohttp.ClientSession) -> List[str]:
    """Fetch sitemap.xml and return page URLs."""
    parsed = urlparse(base_url)
    sitemap_url = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    try:
        async with session.get(sitemap_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
            urls = re.findall(r"<loc>(https?://[^<]+)</loc>", text)
            base_domain = parsed.netloc
            return [u for u in urls if urlparse(u).netloc == base_domain]
    except Exception:
        return []


async def _download_pdf(url: str, session: aiohttp.ClientSession) -> Optional[ScrapedPage]:
    """Download a PDF and extract text with pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.warning("pypdf not installed; skipping PDF %s", url)
        return None

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                return None
            data = await resp.read()

        reader = PdfReader(io.BytesIO(data))
        texts = []
        for pg in reader.pages:
            try:
                t = pg.extract_text()
                if t:
                    texts.append(t)
            except Exception:
                pass

        content = "\n\n".join(texts).strip()
        content = re.sub(r"\n{3,}", "\n\n", content)
        if len(content) < MIN_CONTENT_LENGTH:
            return None

        parsed = urlparse(url)
        stem = parsed.path.split("/")[-1].replace(".pdf", "")
        return ScrapedPage(
            url=url,
            title=f"[PDF] {stem}",
            content=content[:MAX_CONTENT_LENGTH],
            page_type="pdf",
        )
    except Exception as e:
        logger.warning("PDF download/parse error %s: %s", url, e)
        return None


# ── Cookie dismissal ───────────────────────────────────────────────────────


async def _dismiss_cookie_popup(context_page) -> None:  # type: ignore[type-arg]
    """Try common French cookie accept selectors with a short timeout."""
    for selector in _COOKIE_SELECTORS:
        try:
            await context_page.click(selector, timeout=300)
            return
        except Exception:
            continue


# ── Core crawler ───────────────────────────────────────────────────────────


async def _crawl_site(
    browser: Browser,
    url: str,
    candidate_id: str,
) -> ScrapedWebsite:
    """BFS crawl a single candidate website using a fresh browser context."""
    result = ScrapedWebsite(candidate_id=candidate_id, website_url=url, backend="playwright-fast")

    context: Optional[BrowserContext] = None
    try:
        context = await browser.new_context(
            ignore_https_errors=True,
            java_script_enabled=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        visited: Set[str] = set()
        pdf_urls: Set[str] = set()
        # BFS queue: (url, depth)
        queue: List[tuple[str, int]] = [(url.rstrip("/"), 0)]
        pages_scraped = 0
        errors = 0

        # Fetch sitemap URLs to prime the queue at depth 1
        async with aiohttp.ClientSession() as session:
            sitemap_urls = await _fetch_sitemap_urls(url, session)

        for smap_url in sitemap_urls[:MAX_PAGES]:
            clean = smap_url.rstrip("/")
            if clean not in visited:
                queue.append((clean, 1))

        # BFS
        async with aiohttp.ClientSession() as pdf_session:
            while queue and pages_scraped < MAX_PAGES:
                current_url, depth = queue.pop(0)
                current_url = current_url.rstrip("/")

                if current_url in visited:
                    continue
                visited.add(current_url)

                # Skip PDFs encountered in the queue
                if urlparse(current_url).path.lower().endswith(".pdf"):
                    if len(pdf_urls) < MAX_PDFS:
                        pdf_urls.add(current_url)
                    continue

                page = await context.new_page()
                try:
                    await page.goto(
                        current_url,
                        wait_until="domcontentloaded",
                        timeout=PAGE_TIMEOUT,
                    )
                    await page.wait_for_timeout(1500)

                    # Try to dismiss cookie popups on first page
                    if pages_scraped == 0:
                        await _dismiss_cookie_popup(page)

                    html = await page.content()

                    title, markdown_content = _html_to_markdown(html, current_url)

                    if len(markdown_content.strip()) >= MIN_CONTENT_LENGTH:
                        result.pages.append(
                            ScrapedPage(
                                url=current_url,
                                title=title,
                                content=markdown_content[:MAX_CONTENT_LENGTH],
                                page_type="html",
                                depth=depth,
                            )
                        )
                        pages_scraped += 1

                    # Extract links for BFS if not at max depth
                    if depth < MAX_DEPTH:
                        page_links, found_pdfs = _extract_links(html, current_url)
                        for pdf_url in found_pdfs:
                            if len(pdf_urls) < MAX_PDFS:
                                pdf_urls.add(pdf_url)
                        for link in page_links:
                            clean_link = link.rstrip("/")
                            if clean_link not in visited:
                                queue.append((clean_link, depth + 1))

                except Exception as e:
                    logger.debug("Page error %s: %s", current_url, e)
                    errors += 1
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass

            # Download PDFs
            pdfs_downloaded = 0
            for pdf_url in list(pdf_urls)[:MAX_PDFS]:
                pdf_page = await _download_pdf(pdf_url, pdf_session)
                if pdf_page:
                    result.pages.append(pdf_page)
                    pdfs_downloaded += 1

        result.stats = {
            "pages_visited": pages_scraped,
            "pdfs_downloaded": pdfs_downloaded,
            "errors": errors,
            "skipped": 0,
        }

        logger.info(
            "Scraped %s: %d pages, %d PDFs, %d chars",
            url,
            pages_scraped,
            pdfs_downloaded,
            result.total_content_length,
        )

    except Exception as e:
        logger.error("Crawl error %s: %s", url, e)
        result.error = str(e)
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass

    return result


# ── Scraper class ──────────────────────────────────────────────────────────


class PlaywrightFastScraper:
    """Fast async Playwright scraper with a shared browser instance.

    Each call to `scrape_candidate_website` creates its own browser context
    for isolation. `scrape_multiple_candidates` shares a single browser
    across all concurrent scrapes.
    """

    def __init__(self) -> None:
        self._browser: Optional[Browser] = None
        self._playwright = None

    async def _ensure_browser(self) -> Browser:
        if self._browser is None or not self._browser.is_connected():
            if self._playwright is None:
                self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        return self._browser

    async def _close(self) -> None:
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    async def scrape_candidate_website(self, candidate: Candidate) -> ScrapedWebsite:
        result = ScrapedWebsite(
            candidate_id=candidate.candidate_id,
            website_url=candidate.website_url or "",
            backend="playwright-fast",
        )

        if not candidate.website_url:
            result.error = "No website URL"
            return result

        url = candidate.website_url
        logger.info("Playwright scrape: %s → %s", candidate.full_name, url)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                result = await _crawl_site(browser, url, candidate.candidate_id)
            finally:
                await browser.close()

        return result

    async def scrape_multiple_candidates(
        self, candidates: List[Candidate], max_concurrent: int = 5
    ) -> List[ScrapedWebsite]:
        sem = asyncio.Semaphore(max_concurrent)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                async def _one(c: Candidate) -> ScrapedWebsite:
                    if not c.website_url:
                        return ScrapedWebsite(
                            candidate_id=c.candidate_id,
                            website_url="",
                            error="No website URL",
                        )
                    async with sem:
                        try:
                            return await _crawl_site(browser, c.website_url, c.candidate_id)
                        except Exception as e:
                            logger.error("Failed %s: %s", c.full_name, e)
                            return ScrapedWebsite(
                                candidate_id=c.candidate_id,
                                website_url=c.website_url or "",
                                error=str(e),
                            )

                return list(await asyncio.gather(*[_one(c) for c in candidates]))
            finally:
                await browser.close()
