# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Production-ready scraper for candidate campaign websites.

Features:
1. Sitemap.xml discovery and parsing
2. Recursive crawling of ALL internal links
3. Intelligent content extraction
4. PDF detection and extraction (including JS-generated links)
5. Detailed logging for debugging
6. Robust error handling with retries
"""

import asyncio
import io
import logging
import re
import defusedxml.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup  # type: ignore[import-not-found]
from playwright.async_api import (  # type: ignore[import-not-found]
    async_playwright,
    Page,
    Browser,
    BrowserContext,
    TimeoutError as PlaywrightTimeout,
)
from pypdf import PdfReader

from src.models.candidate import Candidate

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Timeouts
PAGE_TIMEOUT = 20000  # ms - timeout for page load
SCROLL_DELAY = 400  # ms - delay between scroll steps
NAVIGATION_TIMEOUT = 15000  # ms - timeout for navigation

# Limits
MAX_PAGES_PER_SITE = 15  # Maximum pages to scrape per candidate
MAX_PDFS_PER_SITE = 5  # Maximum PDFs to download
MAX_CRAWL_DEPTH = 2  # How deep to follow links
MIN_CONTENT_LENGTH = 100  # Minimum chars for a page to be considered valid
MAX_CONTENT_LENGTH = 30000  # Maximum chars per page

# Rate limiting
RATE_LIMIT_DELAY = 0.2  # seconds between requests
PDF_DOWNLOAD_TIMEOUT = 15  # seconds

# PDF limits
PDF_MAX_SIZE = 15 * 1024 * 1024  # 15 MB max

# Tags to exclude from content extraction
EXCLUDED_TAGS = [
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "noscript",
    "svg",
    "iframe",
    "form",
    "button",
    "input",
    "select",
]

# URL patterns to skip
SKIP_URL_PATTERNS = [
    r"/wp-admin/",
    r"/wp-login",
    r"/feed/",
    r"/rss/",
    r"\?replytocom=",
    r"#comment",
    r"/tag/",
    r"/author/",
    r"/page/\d+",
    r"\?share=",
    r"/attachment/",
    r"\.jpg$",
    r"\.jpeg$",
    r"\.png$",
    r"\.gif$",
    r"\.webp$",
    r"\.css$",
    r"\.js$",
    r"\.xml$",
    r"\.json$",
    r"facebook\.com",
    r"twitter\.com",
    r"instagram\.com",
    r"linkedin\.com",
    r"youtube\.com",
    r"tiktok\.com",
]


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class ScrapedPage:
    """Represents a scraped page from a candidate's website."""

    url: str
    title: str
    content: str
    page_type: str  # "html", "pdf", "sitemap"
    depth: int = 0
    content_length: int = 0

    def __post_init__(self):
        self.content_length = len(self.content)


@dataclass
class ScrapedWebsite:
    """Represents the scraped content from a candidate's entire website."""

    candidate_id: str
    website_url: str
    pages: List[ScrapedPage] = field(default_factory=list)
    error: Optional[str] = None
    stats: Dict[str, int] = field(default_factory=dict)

    @property
    def total_content_length(self) -> int:
        return sum(page.content_length for page in self.pages)

    @property
    def is_successful(self) -> bool:
        return len(self.pages) > 0


@dataclass
class CrawlTask:
    """A URL to be crawled with its metadata."""

    url: str
    depth: int
    source: str  # Where this URL was discovered


# ============================================================================
# MAIN SCRAPER CLASS
# ============================================================================


class CandidateWebsiteScraper:
    """
    Production-ready website scraper using Playwright.

    Crawling strategy:
    1. Try to fetch and parse sitemap.xml
    2. Start from homepage, extract all internal links
    3. Recursively crawl discovered pages up to MAX_CRAWL_DEPTH
    4. Detect and download PDFs found on any page
    5. Extract clean text content from all pages
    """

    def __init__(self):
        self._visited_urls: Set[str] = set()
        self._pdf_urls: Set[str] = set()
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._stats = {
            "pages_visited": 0,
            "pdfs_downloaded": 0,
            "errors": 0,
            "skipped": 0,
        }

    # ========================================================================
    # BROWSER MANAGEMENT
    # ========================================================================

    async def _init_browser(self, playwright) -> Tuple[Browser, BrowserContext]:
        """Initialize browser and context."""
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                # NOTE: --single-process and --no-zygote omitted: they are Linux/Docker
                # flags that cause browser crashes on macOS and are not needed locally.
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="fr-FR",
            java_script_enabled=True,
        )

        return browser, context

    async def _close_browser(self):
        """Safely close browser resources."""
        try:
            if self._context is not None:
                await self._context.close()
        except Exception:
            pass
        finally:
            self._context = None

        try:
            if self._browser is not None:
                await self._browser.close()
        except Exception:
            pass
        finally:
            self._browser = None

    # ========================================================================
    # URL UTILITIES
    # ========================================================================

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication."""
        parsed = urlparse(url)
        # Remove fragment, trailing slash, normalize scheme
        path = parsed.path.rstrip("/") or "/"
        normalized = f"{parsed.scheme}://{parsed.netloc}{path}"
        if parsed.query:
            normalized += f"?{parsed.query}"
        return normalized.lower()

    def _is_same_domain(self, url: str, base_url: str) -> bool:
        """Check if URL belongs to the same domain."""
        base_domain = urlparse(base_url).netloc.lower()
        url_domain = urlparse(url).netloc.lower()
        # Handle www vs non-www
        base_domain = base_domain.replace("www.", "")
        url_domain = url_domain.replace("www.", "")
        return url_domain == base_domain

    def _should_skip_url(self, url: str) -> bool:
        """Check if URL should be skipped based on patterns."""
        url_lower = url.lower()
        for pattern in SKIP_URL_PATTERNS:
            if re.search(pattern, url_lower):
                return True
        return False

    def _is_pdf_url(self, url: str) -> bool:
        """Check if URL points to a PDF."""
        return url.lower().endswith(".pdf")

    # ========================================================================
    # SITEMAP HANDLING
    # ========================================================================

    async def _fetch_sitemap(self, base_url: str) -> List[str]:
        """Try to fetch and parse sitemap.xml."""
        urls = []
        parsed_base = urlparse(base_url)
        sitemap_urls = [
            f"{parsed_base.scheme}://{parsed_base.netloc}/sitemap.xml",
            f"{parsed_base.scheme}://{parsed_base.netloc}/sitemap_index.xml",
            f"{parsed_base.scheme}://{parsed_base.netloc}/wp-sitemap.xml",
        ]

        async with aiohttp.ClientSession() as session:
            for sitemap_url in sitemap_urls:
                try:
                    async with session.get(
                        sitemap_url,
                        timeout=aiohttp.ClientTimeout(total=10),
                        headers={"User-Agent": "Mozilla/5.0 ChatVote Bot"},
                    ) as response:
                        if response.status == 200:
                            content = await response.text()
                            urls.extend(self._parse_sitemap(content, base_url))
                            if urls:
                                logger.info(
                                    f"Found {len(urls)} URLs in sitemap: {sitemap_url}"
                                )
                                break
                except Exception as e:
                    logger.debug(f"Could not fetch sitemap {sitemap_url}: {e}")

        return urls

    def _parse_sitemap(self, content: str, base_url: str) -> List[str]:
        """Parse sitemap XML content."""
        urls = []
        try:
            root = ET.fromstring(content)
            # Handle different sitemap formats
            namespaces = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            # Try with namespace
            for loc in root.findall(".//sm:loc", namespaces):
                if loc.text:
                    url = loc.text.strip()
                    if self._is_same_domain(url, base_url):
                        urls.append(url)

            # Try without namespace
            if not urls:
                for loc in root.findall(".//loc"):
                    if loc.text:
                        url = loc.text.strip()
                        if self._is_same_domain(url, base_url):
                            urls.append(url)

        except ET.ParseError as e:
            logger.debug(f"Could not parse sitemap: {e}")

        return urls

    # ========================================================================
    # PAGE SCRAPING
    # ========================================================================

    async def _scroll_page(self, page: Page) -> None:
        """Scroll through page to trigger lazy loading."""
        try:
            scroll_height = await page.evaluate("document.body.scrollHeight")
            viewport_height = await page.evaluate("window.innerHeight")

            current = 0
            max_scrolls = 10  # Limit scrolling
            scroll_count = 0

            while current < scroll_height and scroll_count < max_scrolls:
                current += viewport_height
                await page.evaluate(f"window.scrollTo(0, {current})")
                await page.wait_for_timeout(SCROLL_DELAY)

                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height > scroll_height:
                    scroll_height = new_height
                scroll_count += 1

            # Scroll back to top
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(200)

        except Exception as e:
            logger.debug(f"Scroll error (non-fatal): {e}")

    async def _dismiss_popups(self, page: Page) -> None:
        """Dismiss cookie/newsletter popups."""
        selectors = [
            "button:has-text('Accepter')",
            "button:has-text('Accept')",
            "button:has-text('OK')",
            "button:has-text('Continuer')",
            "[id*='cookie'] button",
            "[class*='cookie'] button",
            "[id*='consent'] button",
            "button[aria-label='Close']",
            ".close-button",
        ]

        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=300):
                    await btn.click()
                    await page.wait_for_timeout(200)
                    return
            except Exception:
                continue

    async def _extract_content(self, page: Page) -> Tuple[str, str]:
        """Extract title and clean text content from page."""
        html = await page.content()
        soup = BeautifulSoup(html, "html.parser")

        # Extract title
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Remove unwanted elements
        for tag_name in EXCLUDED_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Remove hidden elements
        for hidden in soup.find_all(style=re.compile(r"display:\s*none", re.I)):
            hidden.decompose()
        for hidden in soup.find_all(attrs={"aria-hidden": "true"}):
            hidden.decompose()

        # Find main content area
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(id=re.compile(r"content|main", re.I))
            or soup.find(class_=re.compile(r"content|main|page", re.I))
            or soup.body
        )

        if main is None:
            return title, ""

        # Extract text from relevant elements
        texts = []
        seen = set()

        for el in main.find_all(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
                "h6",
                "p",
                "li",
                "td",
                "th",
                "blockquote",
                "span",
                "div",
                "section",
                "article",
            ]
        ):
            text = el.get_text(separator=" ", strip=True)
            if text and len(text) > 15:
                # Deduplicate by prefix
                key = text[:80].lower()
                if key not in seen:
                    seen.add(key)
                    texts.append(text)

        content = "\n\n".join(texts)

        # Clean up whitespace
        content = re.sub(r"\n{3,}", "\n\n", content)
        content = re.sub(r" {2,}", " ", content)

        # Truncate if too long
        if len(content) > MAX_CONTENT_LENGTH:
            content = content[:MAX_CONTENT_LENGTH] + "..."

        return title, content.strip()

    async def _extract_links(
        self, page: Page, base_url: str
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        Extract all internal links and PDF links from page.

        Returns:
            Tuple of (internal_urls, pdf_links) where pdf_links is [(url, title), ...]
        """
        internal_links = []
        pdf_links = []

        try:
            anchors = await page.query_selector_all("a[href]")

            for anchor in anchors:
                try:
                    href = await anchor.get_attribute("href")
                    if (
                        href is None
                        or href.startswith("#")
                        or href.startswith("javascript:")
                    ):
                        continue

                    # Get link text for PDF titles
                    text = ""
                    try:
                        text = (await anchor.inner_text()).strip()
                    except Exception:
                        pass

                    # Build absolute URL
                    full_url = urljoin(base_url, href)
                    normalized = self._normalize_url(full_url)

                    # Skip if already visited or should skip
                    if normalized in self._visited_urls:
                        continue
                    if self._should_skip_url(normalized):
                        continue

                    # Check if PDF
                    if self._is_pdf_url(normalized):
                        if normalized not in self._pdf_urls:
                            title = text or normalized.split("/")[-1].replace(
                                ".pdf", ""
                            )
                            pdf_links.append((normalized, title))
                            self._pdf_urls.add(normalized)
                    # Check if internal link
                    elif self._is_same_domain(normalized, base_url):
                        internal_links.append(normalized)

                except Exception:
                    continue

        except Exception as e:
            logger.debug(f"Error extracting links: {e}")

        return list(set(internal_links)), pdf_links

    async def _scrape_page(
        self, page: Page, url: str, depth: int
    ) -> Tuple[Optional[ScrapedPage], List[str], List[Tuple[str, str]]]:
        """
        Scrape a single page.

        Returns:
            Tuple of (scraped_page, discovered_urls, pdf_links)
        """
        try:
            logger.debug(f"Scraping [depth={depth}]: {url}")

            # Navigate
            response = await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=PAGE_TIMEOUT,
            )

            if response is None or response.status >= 400:
                logger.debug(f"HTTP {response.status if response else 'None'}: {url}")
                self._stats["errors"] += 1
                return None, [], []

            # Wait for content (best-effort: some sites never reach networkidle
            # due to continuous background requests e.g. analytics, ads)
            try:
                await page.wait_for_load_state("networkidle", timeout=NAVIGATION_TIMEOUT)
            except PlaywrightTimeout:
                logger.debug(f"networkidle timeout for {url}, continuing with loaded content")

            # Handle popups
            await self._dismiss_popups(page)

            # Scroll to load lazy content
            await self._scroll_page(page)

            # Extract content
            title, content = await self._extract_content(page)

            # Extract links for further crawling
            internal_links, pdf_links = await self._extract_links(page, url)

            if len(content) < MIN_CONTENT_LENGTH:
                logger.debug(
                    f"Skipping {url}: too little content ({len(content)} chars)"
                )
                self._stats["skipped"] += 1
                return None, internal_links, pdf_links

            self._stats["pages_visited"] += 1

            scraped = ScrapedPage(
                url=url,
                title=title,
                content=content,
                page_type="html",
                depth=depth,
            )

            logger.info(f"Scraped: {title[:50]}... ({len(content)} chars)")

            return scraped, internal_links, pdf_links

        except PlaywrightTimeout:
            logger.warning(f"Timeout: {url}")
            self._stats["errors"] += 1
            return None, [], []
        except Exception as e:
            logger.warning(f"Error scraping {url}: {e}")
            self._stats["errors"] += 1
            return None, [], []

    # ========================================================================
    # PDF HANDLING
    # ========================================================================

    async def _download_pdf(self, url: str, title: str) -> Optional[ScrapedPage]:
        """Download and extract text from a PDF."""
        try:
            logger.debug(f"Downloading PDF: {title}")

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=PDF_DOWNLOAD_TIMEOUT),
                    headers={
                        "User-Agent": "Mozilla/5.0 ChatVote Bot",
                        "Accept": "application/pdf,*/*",
                    },
                ) as response:
                    if response.status != 200:
                        logger.debug(f"PDF download failed: HTTP {response.status}")
                        return None

                    # Check size
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > PDF_MAX_SIZE:
                        logger.debug(f"PDF too large: {content_length} bytes")
                        return None

                    pdf_bytes = await response.read()

            # Parse PDF
            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)

            texts = []
            for page_num, pdf_page in enumerate(reader.pages):
                try:
                    text = pdf_page.extract_text()
                    if text:
                        texts.append(text)
                except Exception as e:
                    logger.debug(f"Error extracting PDF page {page_num}: {e}")

            content = "\n\n".join(texts)
            content = re.sub(r"\n{3,}", "\n\n", content)
            content = re.sub(r" {2,}", " ", content)
            content = content.strip()

            if len(content) < 50:
                logger.debug(f"PDF has too little content: {url}")
                return None

            self._stats["pdfs_downloaded"] += 1

            logger.info(f"PDF extracted: {title} ({len(content)} chars)")

            return ScrapedPage(
                url=url,
                title=f"[PDF] {title}",
                content=content[:MAX_CONTENT_LENGTH],
                page_type="pdf",
            )

        except Exception as e:
            logger.warning(f"PDF error {url}: {e}")
            return None

    # ========================================================================
    # MAIN CRAWL LOGIC
    # ========================================================================

    async def scrape_candidate_website(self, candidate: Candidate) -> ScrapedWebsite:
        """
        Scrape a candidate's entire website.

        Strategy:
        1. Fetch sitemap.xml if available
        2. Start from homepage
        3. BFS crawl all internal links up to MAX_CRAWL_DEPTH
        4. Collect and download all PDFs found
        """
        result = ScrapedWebsite(
            candidate_id=candidate.candidate_id,
            website_url=candidate.website_url or "",
        )

        if not candidate.website_url:
            result.error = "No website URL"
            return result

        base_url = candidate.website_url
        logger.info(f"Starting crawl for {candidate.full_name}: {base_url}")

        # Reset state
        self._visited_urls.clear()
        self._pdf_urls.clear()
        self._stats = {
            "pages_visited": 0,
            "pdfs_downloaded": 0,
            "errors": 0,
            "skipped": 0,
        }

        all_pdf_links: List[Tuple[str, str]] = []

        async with async_playwright() as playwright:
            try:
                self._browser, self._context = await self._init_browser(playwright)
                page = await self._context.new_page()

                # Initialize crawl queue with homepage
                queue: deque[CrawlTask] = deque()
                queue.append(CrawlTask(url=base_url, depth=0, source="homepage"))

                # Try to get URLs from sitemap
                sitemap_urls = await self._fetch_sitemap(base_url)
                for url in sitemap_urls[:10]:  # Limit sitemap URLs
                    normalized = self._normalize_url(url)
                    if normalized not in self._visited_urls:
                        queue.append(CrawlTask(url=url, depth=1, source="sitemap"))

                # BFS crawl
                while queue and len(result.pages) < MAX_PAGES_PER_SITE:
                    task = queue.popleft()
                    normalized = self._normalize_url(task.url)

                    # Skip if already visited
                    if normalized in self._visited_urls:
                        continue
                    self._visited_urls.add(normalized)

                    # Skip if too deep
                    if task.depth > MAX_CRAWL_DEPTH:
                        continue

                    # Rate limiting
                    await asyncio.sleep(RATE_LIMIT_DELAY)

                    # Scrape page
                    scraped, new_urls, pdf_links = await self._scrape_page(
                        page, task.url, task.depth
                    )

                    if scraped is not None:
                        result.pages.append(scraped)

                    # Add new URLs to queue
                    for new_url in new_urls:
                        norm_new = self._normalize_url(new_url)
                        if norm_new not in self._visited_urls:
                            queue.append(
                                CrawlTask(
                                    url=new_url, depth=task.depth + 1, source=task.url
                                )
                            )

                    # Collect PDFs
                    all_pdf_links.extend(pdf_links)

                # Download PDFs
                logger.info(f"Found {len(all_pdf_links)} PDFs to download")
                for pdf_url, pdf_title in all_pdf_links[:MAX_PDFS_PER_SITE]:
                    if len(result.pages) >= MAX_PAGES_PER_SITE:
                        break
                    pdf_page = await self._download_pdf(pdf_url, pdf_title)
                    if pdf_page is not None:
                        result.pages.append(pdf_page)

            except (BrokenPipeError, ConnectionResetError) as e:
                logger.warning(f"Browser connection lost: {e}")
                result.error = f"Browser error: {e}"

            except Exception as e:
                logger.error(f"Crawl error for {candidate.full_name}: {e}")
                result.error = str(e)

            finally:
                await self._close_browser()

        # Store stats
        result.stats = self._stats.copy()

        logger.info(
            f"Completed {candidate.full_name}: "
            f"{len(result.pages)} pages, "
            f"{result.total_content_length} chars, "
            f"stats={self._stats}"
        )

        return result

    async def scrape_multiple_candidates(
        self, candidates: List[Candidate], max_concurrent: int = 1
    ) -> List[ScrapedWebsite]:
        """Scrape multiple candidates sequentially (browser is resource-heavy)."""
        results = []

        for candidate in candidates:
            if not candidate.website_url:
                results.append(
                    ScrapedWebsite(
                        candidate_id=candidate.candidate_id,
                        website_url="",
                        error="No website URL",
                    )
                )
                continue

            try:
                result = await self.scrape_candidate_website(candidate)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to scrape {candidate.full_name}: {e}")
                results.append(
                    ScrapedWebsite(
                        candidate_id=candidate.candidate_id,
                        website_url=candidate.website_url or "",
                        error=str(e),
                    )
                )

            # Small delay between candidates
            await asyncio.sleep(0.5)

        return results
