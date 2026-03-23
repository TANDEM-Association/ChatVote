"""Pipeline node: scrape social media content via Apify for candidates without websites.

Handles Instagram profiles, Facebook pages, and X/Twitter profiles.
Converts posts/bios into ScrapedPage objects for the existing indexing pipeline.

Usage (standalone):
    poetry run python -m src.services.data_pipeline.social_scraper
    poetry run python -m src.services.data_pipeline.social_scraper --dry-run
    poetry run python -m src.services.data_pipeline.social_scraper --candidate cand-75056-1
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlparse

from src.services.candidate_website_scraper import ScrapedPage, ScrapedWebsite

logger = logging.getLogger(__name__)

# Max posts to fetch per profile
MAX_POSTS_INSTAGRAM = 30
MAX_POSTS_FACEBOOK = 30
MAX_TWEETS = 50

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

_PLATFORM_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("instagram", re.compile(r"instagram\.com", re.I)),
    ("facebook", re.compile(r"facebook\.com|fb\.com", re.I)),
    ("twitter", re.compile(r"twitter\.com|x\.com", re.I)),
]


def detect_platform(url: str) -> str | None:
    """Return platform name or None if not a social media URL."""
    for name, pattern in _PLATFORM_PATTERNS:
        if pattern.search(url):
            return name
    return None


def _extract_handle(url: str) -> str:
    """Extract username/handle from social URL."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    # Remove trailing segments like /photos, /posts, etc.
    parts = path.split("/")
    if parts:
        return parts[0]
    return path


# ---------------------------------------------------------------------------
# Apify client helpers
# ---------------------------------------------------------------------------

def _get_apify_client():
    """Get ApifyClient instance."""
    from apify_client import ApifyClient

    token = os.getenv("APIFY_API_KEY", "")
    if not token:
        raise RuntimeError("APIFY_API_KEY environment variable not set")
    return ApifyClient(token)


def scrape_instagram(client, urls: list[str]) -> dict[str, list[dict]]:
    """Scrape Instagram profiles. Returns {url: [items]}."""
    if not urls:
        return {}

    logger.info("[social_scraper] Scraping %d Instagram profiles via Apify...", len(urls))
    run = client.actor("apify/instagram-scraper").call(
        run_input={
            "directUrls": urls,
            "resultsType": "details",
            "resultsLimit": MAX_POSTS_INSTAGRAM,
        },
        timeout_secs=300,
    )

    if run["status"] != "SUCCEEDED":
        logger.error("[social_scraper] Instagram run failed: %s", run["status"])
        return {}

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    logger.info("[social_scraper] Instagram: %d profile(s) returned", len(items))

    # Map by input URL (match via username)
    url_by_handle: dict[str, str] = {}
    for u in urls:
        handle = _extract_handle(u).lower().rstrip("/")
        url_by_handle[handle] = u

    result: dict[str, list[dict]] = {}
    for item in items:
        username = (item.get("username") or "").lower()
        matched_url = url_by_handle.get(username, urls[0] if len(urls) == 1 else "")
        if matched_url:
            result.setdefault(matched_url, []).append(item)

    return result


def scrape_facebook(client, urls: list[str]) -> dict[str, list[dict]]:
    """Scrape Facebook page posts. Returns {url: [posts]}."""
    if not urls:
        return {}

    logger.info("[social_scraper] Scraping %d Facebook pages via Apify...", len(urls))
    run = client.actor("apify/facebook-posts-scraper").call(
        run_input={
            "startUrls": [{"url": u} for u in urls],
            "resultsLimit": MAX_POSTS_FACEBOOK,
        },
        timeout_secs=600,
    )

    if run["status"] != "SUCCEEDED":
        logger.error("[social_scraper] Facebook run failed: %s", run["status"])
        return {}

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    logger.info("[social_scraper] Facebook: %d post(s) returned", len(items))

    # Group by page URL
    result: dict[str, list[dict]] = {}
    for item in items:
        page_url = item.get("pageUrl") or item.get("url") or ""
        # Match to input URL
        matched = None
        for u in urls:
            if _extract_handle(u).lower() in page_url.lower():
                matched = u
                break
        if not matched and urls:
            # Fallback: assign to first URL if single
            matched = urls[0] if len(urls) == 1 else page_url
        if matched:
            result.setdefault(matched, []).append(item)

    return result


def scrape_twitter(client, urls: list[str]) -> dict[str, list[dict]]:
    """Scrape X/Twitter profiles. Returns {url: [tweets]}."""
    if not urls:
        return {}

    handles = [_extract_handle(u) for u in urls]
    logger.info("[social_scraper] Scraping %d X/Twitter profiles via Apify...", len(handles))

    run = client.actor("apify/twitter-scraper").call(
        run_input={
            "twitterHandles": handles,
            "maxTweets": MAX_TWEETS,
        },
        timeout_secs=300,
    )

    if run["status"] != "SUCCEEDED":
        logger.error("[social_scraper] Twitter run failed: %s", run["status"])
        return {}

    items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    logger.info("[social_scraper] Twitter: %d item(s) returned", len(items))

    # Map by handle
    handle_to_url = {_extract_handle(u).lower(): u for u in urls}
    result: dict[str, list[dict]] = {}
    for item in items:
        handle = (item.get("userName") or item.get("author", {}).get("userName", "")).lower()
        matched = handle_to_url.get(handle)
        if matched:
            result.setdefault(matched, []).append(item)

    return result


# ---------------------------------------------------------------------------
# Convert Apify results to ScrapedPage objects
# ---------------------------------------------------------------------------

def _instagram_to_pages(url: str, items: list[dict]) -> list[ScrapedPage]:
    """Convert Instagram profile data to ScrapedPage list."""
    pages: list[ScrapedPage] = []

    for item in items:
        bio = item.get("biography", "")
        full_name = item.get("fullName", "")
        username = item.get("username", "")

        # Bio page
        if bio:
            pages.append(ScrapedPage(
                url=url,
                title=f"{full_name or username} - Instagram Bio",
                content=f"{full_name}\n\n{bio}",
                page_type="social_bio",
            ))

        # Posts as individual pages
        for post in item.get("latestPosts", []):
            caption = post.get("caption", "")
            if not caption or len(caption.strip()) < 20:
                continue
            timestamp = post.get("timestamp", "")
            date_str = timestamp[:10] if timestamp else ""
            pages.append(ScrapedPage(
                url=f"{url}p/{post.get('shortCode', '')}/",
                title=f"{full_name or username} - Post {date_str}",
                content=caption,
                page_type="social_post",
            ))

    return pages


def _facebook_to_pages(url: str, items: list[dict]) -> list[ScrapedPage]:
    """Convert Facebook posts to ScrapedPage list."""
    pages: list[ScrapedPage] = []

    for item in items:
        text = item.get("text") or item.get("message") or ""
        if not text or len(text.strip()) < 20:
            continue

        post_url = item.get("postUrl") or item.get("url") or url
        timestamp = item.get("time", "")
        date_str = timestamp[:10] if timestamp else ""

        pages.append(ScrapedPage(
            url=post_url,
            title=f"Facebook Post {date_str}",
            content=text,
            page_type="social_post",
        ))

    return pages


def _twitter_to_pages(url: str, items: list[dict]) -> list[ScrapedPage]:
    """Convert tweets to ScrapedPage list."""
    pages: list[ScrapedPage] = []

    # Separate profile info from tweets
    for item in items:
        # Profile bio
        if "description" in item and item.get("description"):
            pages.append(ScrapedPage(
                url=url,
                title=f"{item.get('name', '')} - X/Twitter Bio",
                content=f"{item.get('name', '')}\n\n{item['description']}",
                page_type="social_bio",
            ))

        # Tweet text
        full_text = item.get("fullText") or item.get("text", "")
        if full_text and len(full_text.strip()) >= 20:
            tweet_url = item.get("tweetUrl") or item.get("url") or url
            pages.append(ScrapedPage(
                url=tweet_url,
                title="Tweet",
                content=full_text,
                page_type="social_post",
            ))

    return pages


_CONVERTERS = {
    "instagram": _instagram_to_pages,
    "facebook": _facebook_to_pages,
    "twitter": _twitter_to_pages,
}


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def scrape_social_candidates(
    candidates: list[dict[str, str]],
    dry_run: bool = False,
) -> dict[str, ScrapedWebsite]:
    """Scrape social media for candidates.

    Args:
        candidates: list of {"candidate_id": str, "url": str, "name": str}
        dry_run: if True, skip Apify calls and just report what would be scraped

    Returns:
        {candidate_id: ScrapedWebsite}
    """
    # Group by platform
    by_platform: dict[str, list[dict]] = {"instagram": [], "facebook": [], "twitter": []}
    for c in candidates:
        platform = detect_platform(c["url"])
        if platform:
            by_platform[platform].append(c)
        else:
            logger.warning("[social_scraper] Unknown platform for %s: %s", c["candidate_id"], c["url"])

    logger.info(
        "[social_scraper] %d candidates: %d Instagram, %d Facebook, %d Twitter",
        len(candidates),
        len(by_platform["instagram"]),
        len(by_platform["facebook"]),
        len(by_platform["twitter"]),
    )

    if dry_run:
        return {}

    client = _get_apify_client()

    # Scrape each platform
    scrapers = {
        "instagram": scrape_instagram,
        "facebook": scrape_facebook,
        "twitter": scrape_twitter,
    }

    all_results: dict[str, dict[str, list[dict]]] = {}
    for platform, cands in by_platform.items():
        if not cands:
            continue
        urls = [c["url"] for c in cands]
        try:
            all_results[platform] = scrapers[platform](client, urls)
        except Exception as exc:
            logger.error("[social_scraper] %s scraping failed: %s", platform, exc)
            all_results[platform] = {}

    # Convert to ScrapedWebsite per candidate
    result: dict[str, ScrapedWebsite] = {}
    for platform, cands in by_platform.items():
        platform_results = all_results.get(platform, {})
        converter = _CONVERTERS[platform]

        for c in cands:
            items = platform_results.get(c["url"], [])
            if not items:
                logger.warning("[social_scraper] No results for %s (%s)", c["candidate_id"], c["url"])
                continue

            pages = converter(c["url"], items)
            if not pages:
                logger.warning("[social_scraper] No content for %s after conversion", c["candidate_id"])
                continue

            sw = ScrapedWebsite(
                candidate_id=c["candidate_id"],
                website_url=c["url"],
                backend="apify_social",
            )
            sw.pages = pages

            logger.info(
                "[social_scraper] %s (%s): %d pages, %d chars",
                c["candidate_id"], platform, len(pages), sw.total_content_length,
            )
            result[c["candidate_id"]] = sw

    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import asyncio
    import sys

    sys.path.insert(0, ".")
    from src.utils import load_env

    load_env()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(description="Scrape social media for candidates")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--candidate", type=str, help="Single candidate ID to scrape")
    args = parser.parse_args()

    async def main():
        import aiohttp
        from src.services.data_pipeline.crawl_scraper import (
            CrawlScraperNode,
            _get_crawl_credentials,
        )

        # Read Google Sheet for social media URLs
        creds = _get_crawl_credentials()
        node = CrawlScraperNode()
        sheet_id = node.default_settings["sheet_id"]

        async with aiohttp.ClientSession() as session:
            token = node._ensure_token(creds)
            rows = await node._fetch_sheet_rows(session, sheet_id, token)

        candidates = []
        for row in rows:
            if len(row) < 9:
                continue
            cid = row[0].strip()
            url = row[8].strip() if len(row) > 8 else ""
            name = f"{row[1]} {row[2]}".strip() if len(row) > 2 else cid

            if not url or not url.startswith("http"):
                continue
            if not detect_platform(url):
                continue
            if args.candidate and cid != args.candidate:
                continue

            candidates.append({"candidate_id": cid, "url": url, "name": name})

        logger.info("Found %d social media candidates in Google Sheet", len(candidates))

        if args.dry_run:
            for c in candidates:
                platform = detect_platform(c["url"])
                print(f"  {c['candidate_id']} {c['name']}: [{platform}] {c['url']}")
            return

        results = scrape_social_candidates(candidates, dry_run=False)

        # Summary
        print(f"\n{'=' * 50}")
        print("Social Media Scraping Results")
        print(f"{'=' * 50}")
        total_pages = 0
        total_chars = 0
        for cid, sw in results.items():
            pages = len(sw.pages)
            chars = sw.total_content_length
            total_pages += pages
            total_chars += chars
            print(f"  {cid}: {pages} pages, {chars:,} chars")

        print(f"\nTotal: {len(results)} candidates, {total_pages} pages, {total_chars:,} chars")

    asyncio.run(main())
