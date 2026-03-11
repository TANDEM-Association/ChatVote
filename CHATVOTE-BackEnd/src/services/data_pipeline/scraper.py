"""Pipeline node: scrape candidate websites.

Separates the website scraping step from the Qdrant indexing step.
This node crawls candidate websites (BFS, max 15 pages + 5 PDFs per site)
and stores the scraped content in memory for the indexer node to embed.

Backends (scraper_backend setting):
- "playwright"      — full Playwright with networkidle, scrolling, popups
- "playwright-fast" — lightweight Playwright, markdown output, ~3x faster
"""
from __future__ import annotations

import logging
import os
import time as _time
from datetime import datetime, timezone
from typing import Any

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    NodeStatus,
    register_node,
    save_checkpoint,
    update_status,
    put_context,
    get_context,
)

logger = logging.getLogger(__name__)

CONTEXT_KEY = "scraped_websites"


def get_scraped_websites() -> dict[str, Any] | None:
    """Return {candidate_id: ScrapedWebsite} from last run, or None."""
    return get_context(CONTEXT_KEY)


class ScraperNode(DataSourceNode):
    node_id = "scraper"
    label = "Website Scraper"
    default_settings: dict[str, Any] = {
        "max_concurrent": 5,
        "scraper_backend": "playwright",
        "firecrawl_fallback": True,
    }

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:

        max_concurrent = int(cfg.settings.get("max_concurrent", 3))
        scraper_backend = cfg.settings.get("scraper_backend", "playwright")

        # Get candidates with websites from Firestore
        from src.services.candidate_indexer import (
            aget_candidates_with_website,
            _get_indexed_candidate_counts,
        )

        # Pick scraper class based on backend setting
        if scraper_backend == "playwright-fast":
            from src.services.playwright_fast_scraper import PlaywrightFastScraper as _Scraper
        else:
            from src.services.candidate_website_scraper import CandidateWebsiteScraper as _Scraper

        candidates = await aget_candidates_with_website()
        logger.info("[scraper] found %d candidates with website URLs", len(candidates))

        if not candidates:
            cfg.counts = {"candidates_total": 0, "scraped": 0, "skipped": 0}
            return cfg

        # If crawl_scraper is enabled, it handles candidate websites — skip them here
        from src.services.data_pipeline.base import load_config
        from src.services.data_pipeline.crawl_scraper import CrawlScraperNode
        crawl_cfg = await load_config("crawl_scraper", CrawlScraperNode().default_config())
        if crawl_cfg.enabled:
            logger.info(
                "[scraper] crawl_scraper is enabled — skipping %d candidates (handled by crawl service)",
                len(candidates),
            )
            cfg.counts = {
                "candidates_total": len(candidates),
                "scraped": 0,
                "skipped": len(candidates),
                "skipped_reason": "crawl_scraper enabled",
            }
            return cfg

        # Skip already-indexed candidates unless forced
        existing = _get_indexed_candidate_counts() if not force else {}
        to_scrape = [c for c in candidates if c.candidate_id not in existing]

        logger.info(
            "[scraper] %d to scrape (%d already indexed, force=%s)",
            len(to_scrape), len(existing), force,
        )

        # Mark already-indexed candidates as scraped in Firestore so the
        # coverage page counts them correctly.
        if existing:
            from src.firebase_service import async_db
            for cand in candidates:
                if cand.candidate_id in existing:
                    try:
                        ref = async_db.collection("candidates").document(cand.candidate_id)
                        await ref.set({"has_scraped": True}, merge=True)
                    except Exception as exc:
                        logger.debug("[scraper] failed to mark %s as scraped: %s", cand.candidate_id, exc)

        if not to_scrape:
            cfg.counts = {
                "candidates_total": len(candidates),
                "scraped": 0,
                "skipped": len(existing),
                "already_indexed": len(existing),
            }
            put_context(CONTEXT_KEY, {})
            return cfg

        # Scrape using selected backend
        t0 = _time.monotonic()

        import asyncio

        scraped_map: dict[str, Any] = {}
        total_pages = 0
        total_chars = 0
        errors = 0
        last_results: list[dict[str, Any]] = []
        sem = asyncio.Semaphore(max_concurrent)

        # Initial progress update so the UI shows something immediately
        await update_status(
            cfg.node_id, NodeStatus.RUNNING,
            counts={
                "candidates_total": len(to_scrape),
                "scraped": 0,
                "errors": 0,
                "pages": 0,
                "total_chars": 0,
                "elapsed_s": 0,
                "eta_s": 0,
            },
        )

        async def _publish_progress() -> None:
            """Push current counters to Firestore."""
            elapsed = _time.monotonic() - t0
            done = len(scraped_map)
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (len(to_scrape) - done) / rate if rate > 0 else 0
            await update_status(
                cfg.node_id, NodeStatus.RUNNING,
                counts={
                    "candidates_total": len(to_scrape),
                    "scraped": done - errors,
                    "errors": errors,
                    "pages": total_pages,
                    "total_chars": total_chars,
                    "rate_per_sec": round(rate, 2),
                    "elapsed_s": round(elapsed, 1),
                    "eta_s": round(remaining, 0),
                    "last_results": last_results[-5:],
                },
            )

        from src.firebase_service import async_db

        async def _persist_scrape_status(cand_id: str, sw: Any, backend: str) -> None:
            """Write scrape result to Firestore candidate doc immediately."""
            try:
                ref = async_db.collection("candidates").document(cand_id)
                await ref.set({
                    "has_scraped": True,
                    "scrape_backend": backend,
                    "scrape_pages": len(sw.pages),
                    "scrape_chars": sw.total_content_length,
                }, merge=True)
            except Exception as exc:
                logger.debug("[scraper] failed to persist status for %s: %s", cand_id, exc)

        async def _scrape_one(candidate: Any) -> None:
            nonlocal total_pages, total_chars, errors
            async with sem:
                try:
                    scraper = _Scraper()
                    sw = await scraper.scrape_candidate_website(candidate)
                    scraped_map[sw.candidate_id] = sw
                    name = getattr(sw, "candidate_name", sw.candidate_id)
                    if sw.is_successful:
                        total_pages += len(sw.pages)
                        total_chars += sw.total_content_length
                        last_results.append({
                            "name": name,
                            "pages": len(sw.pages),
                            "chars": sw.total_content_length,
                            "ok": True,
                            "backend": scraper_backend,
                        })
                        await _persist_scrape_status(sw.candidate_id, sw, scraper_backend)
                    else:
                        errors += 1
                        last_results.append({
                            "name": name,
                            "error": getattr(sw, "error", "unknown"),
                            "ok": False,
                            "backend": scraper_backend,
                        })
                except Exception as exc:
                    logger.warning("[scraper] failed %s: %s", candidate.candidate_id, exc)
                    errors += 1
                    last_results.append({
                        "name": getattr(candidate, "last_name", candidate.candidate_id),
                        "error": str(exc)[:80],
                        "ok": False,
                        "backend": scraper_backend,
                    })
                # Keep bounded
                while len(last_results) > 5:
                    last_results.pop(0)
                # Update progress after each candidate
                await _publish_progress()

        await asyncio.gather(*[_scrape_one(c) for c in to_scrape])

        # --- Firecrawl fallback for errored candidates ---
        firecrawl_fallback = cfg.settings.get("firecrawl_fallback", True)
        firecrawl_key = os.environ.get("FIRECRAWL_API_KEY", "")

        if firecrawl_fallback and firecrawl_key and errors > 0:
            errored_candidates = [
                c for c in to_scrape
                if c.candidate_id in scraped_map and not scraped_map[c.candidate_id].is_successful
            ]

            if errored_candidates:
                logger.info("[scraper] firecrawl fallback: retrying %d errored candidates", len(errored_candidates))
                await update_status(
                    cfg.node_id, NodeStatus.RUNNING,
                    counts={
                        **cfg.counts,
                        "phase": "firecrawl_fallback",
                        "firecrawl_total": len(errored_candidates),
                        "firecrawl_done": 0,
                    },
                )

                from src.services.firecrawl_scraper import FirecrawlScraper
                firecrawl = FirecrawlScraper(api_key=firecrawl_key)
                firecrawl_sem = asyncio.Semaphore(3)  # Firecrawl rate limit
                firecrawl_recovered = 0

                async def _firecrawl_one(candidate: Any) -> None:
                    nonlocal total_pages, total_chars, errors, firecrawl_recovered
                    async with firecrawl_sem:
                        try:
                            sw = await firecrawl.scrape_candidate_website(candidate)
                            if sw.is_successful:
                                scraped_map[sw.candidate_id] = sw
                                total_pages += len(sw.pages)
                                total_chars += sw.total_content_length
                                errors -= 1
                                firecrawl_recovered += 1
                                last_results.append({
                                    "name": getattr(candidate, "full_name", candidate.candidate_id),
                                    "pages": len(sw.pages),
                                    "chars": sw.total_content_length,
                                    "ok": True,
                                    "backend": "firecrawl",
                                })
                                await _persist_scrape_status(sw.candidate_id, sw, "firecrawl")
                        except Exception as exc:
                            logger.warning("[scraper] firecrawl fallback failed %s: %s", candidate.candidate_id, exc)
                        # Keep bounded
                        while len(last_results) > 5:
                            last_results.pop(0)
                        await _publish_progress()

                await asyncio.gather(*[_firecrawl_one(c) for c in errored_candidates])

                logger.info(
                    "[scraper] firecrawl fallback recovered %d / %d candidates",
                    firecrawl_recovered, len(errored_candidates),
                )

        put_context(CONTEXT_KEY, scraped_map)

        elapsed = _time.monotonic() - t0
        cfg.counts = {
            "candidates_total": len(candidates),
            "scraped": len(scraped_map) - errors,
            "errors": errors,
            "skipped": len(existing),
            "pages": total_pages,
            "total_chars": total_chars,
            "elapsed_s": round(elapsed, 1),
        }

        logger.info(
            "[scraper] done — %d scraped, %d errors, %d pages, %d chars in %.1fs",
            len(scraped_map) - errors, errors, total_pages, total_chars, elapsed,
        )

        return cfg


register_node(ScraperNode())
