# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Firecrawl-based website scraper -- faster alternative to Playwright.

Uses the Firecrawl API to crawl websites and extract clean markdown/text.
Returns the same ScrapedWebsite/ScrapedPage format as the Playwright scraper.

Config:
    FIRECRAWL_API_KEY env var (required)
"""

import os
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from src.models.candidate import Candidate

logger = logging.getLogger(__name__)

FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "")
FIRECRAWL_BASE_URL = "https://api.firecrawl.dev/v2"


@dataclass
class ScrapedPage:
    """Same structure as candidate_website_scraper.ScrapedPage."""

    url: str
    title: str
    content: str
    page_type: str = "html"  # html or pdf
    depth: int = 0
    content_length: int = 0

    def __post_init__(self):
        self.content_length = len(self.content)


@dataclass
class ScrapedWebsite:
    """Same structure as candidate_website_scraper.ScrapedWebsite."""

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


class FirecrawlScraper:
    """Scrape candidate websites using Firecrawl API."""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or FIRECRAWL_API_KEY
        if not self.api_key:
            raise ValueError("FIRECRAWL_API_KEY is required")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def scrape_candidate_website(self, candidate: Candidate) -> ScrapedWebsite:
        """Crawl a candidate's website using Firecrawl and return ScrapedWebsite."""
        url = candidate.website_url
        if not url:
            return ScrapedWebsite(candidate_id=candidate.candidate_id, website_url="")

        logger.info(f"[Firecrawl] Starting crawl for {candidate.full_name}: {url}")
        t0 = time.monotonic()

        try:
            async with aiohttp.ClientSession() as session:
                # Start crawl job
                crawl_resp = await session.post(
                    f"{FIRECRAWL_BASE_URL}/crawl",
                    headers=self.headers,
                    json={
                        "url": url,
                        "limit": 15,  # Match Playwright scraper limit
                        "maxDiscoveryDepth": 2,
                        "scrapeOptions": {
                            "formats": ["markdown"],
                            "onlyMainContent": True,
                        },
                    },
                )

                if crawl_resp.status != 200:
                    error_text = await crawl_resp.text()
                    logger.error(
                        f"[Firecrawl] Crawl start failed ({crawl_resp.status}): {error_text}"
                    )
                    return ScrapedWebsite(
                        candidate_id=candidate.candidate_id,
                        website_url=url,
                        error=f"Crawl start failed: {crawl_resp.status}",
                    )

                crawl_data = await crawl_resp.json()

                # If the response has data directly (synchronous completion)
                if crawl_data.get("status") == "completed" and crawl_data.get("data"):
                    pages = self._parse_crawl_results(crawl_data["data"])
                    elapsed = time.monotonic() - t0
                    logger.info(
                        f"[Firecrawl] Completed {candidate.full_name}: "
                        f"{len(pages)} pages in {elapsed:.1f}s"
                    )
                    return ScrapedWebsite(
                        candidate_id=candidate.candidate_id,
                        website_url=url,
                        pages=pages,
                        stats={
                            "pages_visited": len(pages),
                            "elapsed_s": round(elapsed, 1),
                        },
                    )

                # Async crawl -- poll for results
                job_id = crawl_data.get("id")
                if not job_id:
                    job_id = crawl_data.get("jobId", "")
                    if not job_id:
                        # Try to extract from success response URL
                        success_url = crawl_data.get("url", "")
                        if "/crawl/" in success_url:
                            job_id = success_url.split("/crawl/")[-1]

                if not job_id:
                    logger.error(f"[Firecrawl] No job ID in response: {crawl_data}")
                    return ScrapedWebsite(
                        candidate_id=candidate.candidate_id,
                        website_url=url,
                        error="No job ID returned",
                    )

                # Poll for completion (max 5 minutes)
                all_pages_data: list[dict] = []
                for _attempt in range(150):  # 150 * 2s = 5 min
                    await asyncio.sleep(2)

                    status_resp = await session.get(
                        f"{FIRECRAWL_BASE_URL}/crawl/{job_id}",
                        headers=self.headers,
                    )

                    if status_resp.status != 200:
                        continue

                    status_data = await status_resp.json()
                    status = status_data.get("status", "")

                    if status == "completed":
                        all_pages_data = status_data.get("data", [])

                        # Handle pagination if there's a "next" URL
                        next_url = status_data.get("next")
                        while next_url:
                            next_resp = await session.get(
                                next_url, headers=self.headers
                            )
                            if next_resp.status != 200:
                                break
                            next_data = await next_resp.json()
                            all_pages_data.extend(next_data.get("data", []))
                            next_url = next_data.get("next")

                        break
                    elif status == "failed":
                        logger.error(f"[Firecrawl] Crawl failed for {url}")
                        return ScrapedWebsite(
                            candidate_id=candidate.candidate_id,
                            website_url=url,
                            error="Crawl failed",
                        )

                pages = self._parse_crawl_results(all_pages_data)
                elapsed = time.monotonic() - t0

                logger.info(
                    f"[Firecrawl] Completed {candidate.full_name}: "
                    f"{len(pages)} pages, {sum(len(p.content) for p in pages):,} chars "
                    f"in {elapsed:.1f}s"
                )

                return ScrapedWebsite(
                    candidate_id=candidate.candidate_id,
                    website_url=url,
                    pages=pages,
                    stats={
                        "pages_visited": len(pages),
                        "elapsed_s": round(elapsed, 1),
                    },
                )

        except Exception as e:
            elapsed = time.monotonic() - t0
            logger.error(f"[Firecrawl] Error crawling {url}: {e}", exc_info=True)
            return ScrapedWebsite(
                candidate_id=candidate.candidate_id,
                website_url=url,
                error=str(e),
                stats={"elapsed_s": round(elapsed, 1)},
            )

    def _parse_crawl_results(self, data: list[dict]) -> list[ScrapedPage]:
        """Convert Firecrawl response data to ScrapedPage objects."""
        pages = []
        for item in data:
            content = item.get("markdown", "")
            if not content or len(content.strip()) < 30:
                continue

            metadata = item.get("metadata", {})
            url = metadata.get("sourceURL", item.get("url", ""))
            title = metadata.get("title", "")

            # Detect page type from URL
            page_type = "pdf" if url.lower().endswith(".pdf") else "html"

            # Infer depth from URL structure (rough heuristic)
            path = urlparse(url).path.strip("/")
            depth = len(path.split("/")) if path else 0

            pages.append(
                ScrapedPage(
                    url=url,
                    title=title,
                    content=content,
                    page_type=page_type,
                    depth=min(depth, 2),
                )
            )

        return pages

    async def scrape_multiple_candidates(
        self,
        candidates: List[Candidate],
        max_concurrent: int = 10,
    ) -> List[ScrapedWebsite]:
        """Scrape multiple candidate websites concurrently.

        Firecrawl handles its own rate limiting, so we can be more aggressive
        than with Playwright (10 concurrent vs 3).
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _scrape(candidate: Candidate) -> ScrapedWebsite:
            async with semaphore:
                return await self.scrape_candidate_website(candidate)

        tasks = [_scrape(c) for c in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        scraped = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"[Firecrawl] Exception for {candidates[i].candidate_id}: {result}"
                )
                scraped.append(
                    ScrapedWebsite(
                        candidate_id=candidates[i].candidate_id,
                        website_url=candidates[i].website_url or "",
                        error=str(result),
                    )
                )
            else:
                scraped.append(result)

        return scraped


async def scrape_url(url: str, api_key: str = "") -> str:
    """Simple helper: scrape a single URL and return markdown content.

    Useful for the document upload feature (scrape URL -> process).
    """
    key = api_key or FIRECRAWL_API_KEY
    if not key:
        raise ValueError("FIRECRAWL_API_KEY is required")

    async with aiohttp.ClientSession() as session:
        resp = await session.post(
            f"{FIRECRAWL_BASE_URL}/scrape",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "url": url,
                "formats": ["markdown"],
                "onlyMainContent": True,
            },
        )

        if resp.status != 200:
            error = await resp.text()
            raise RuntimeError(f"Firecrawl scrape failed ({resp.status}): {error}")

        data = await resp.json()
        return data.get("data", {}).get("markdown", "")
