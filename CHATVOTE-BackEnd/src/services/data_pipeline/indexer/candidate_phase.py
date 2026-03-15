"""Indexer phase: candidate websites (from Google Drive crawl data)."""
from __future__ import annotations

import asyncio
import logging
import time as _time
from typing import Any

from src.services.data_pipeline.base import NodeConfig, get_context
from src.services.data_pipeline.indexer.progress import PhaseTracker

logger = logging.getLogger(__name__)


async def run_candidate_phase(
    cfg: NodeConfig,
    tracker: PhaseTracker,
    *,
    force: bool = False,
    classify_themes: bool = True,
) -> int:
    """Index candidate websites into candidates_websites collection.

    Returns total chunks indexed.
    """
    settings = cfg.settings
    if not settings.get("index_candidates", True):
        logger.info("[indexer] candidate indexing disabled, skipping")
        return 0

    logger.info("[indexer] indexing candidate websites (Drive-only mode)...")

    from src.services.candidate_indexer import (
        aget_candidates_with_website,
        index_candidate_website,
        _get_indexed_candidate_counts,
    )
    from src.services.data_pipeline.crawl_scraper import load_scraped_from_drive

    scraped = get_context("scraped_websites")

    t0 = _time.monotonic()
    candidates = await aget_candidates_with_website()
    logger.info("[indexer:timing] aget_candidates_with_website() took %.2fs", _time.monotonic() - t0)
    logger.info("[indexer] found %d candidates with websites", len(candidates))

    # Filter to top communes only
    candidates = _filter_top_communes(candidates)

    # Determine which candidates to index
    to_index = _select_candidates_to_index(candidates, scraped, force)

    if not to_index:
        logger.info("[indexer] no candidates to index")
        return 0

    # Index candidates concurrently
    max_concurrent = int(settings.get("max_concurrent_index", 3))
    return await _index_candidates(
        to_index, scraped, tracker, cfg,
        max_concurrent=max_concurrent,
        classify_themes=classify_themes,
        force=force,
    )


def _filter_top_communes(candidates: list) -> list:
    """Filter candidates to top communes only."""
    from src.services.data_pipeline.population import get_top_communes

    t0 = _time.monotonic()
    top_communes = get_top_communes()
    if top_communes:
        top_codes = set(top_communes.keys())
        before = len(candidates)
        candidates = [
            c for c in candidates
            if (c.municipality_code or "") in top_codes
        ]
        logger.info("[indexer] filtered candidates to top communes: %d -> %d", before, len(candidates))
    logger.info("[indexer:timing] top_communes filter took %.2fs", _time.monotonic() - t0)
    return candidates


def _select_candidates_to_index(
    candidates: list,
    scraped: Any,
    force: bool,
) -> list:
    """Determine which candidates need indexing."""
    if scraped:
        scraped_ids = {
            cid for cid, sw in scraped.items()
            if sw and sw.is_successful
        }
        to_index = [c for c in candidates if c.candidate_id in scraped_ids]
        logger.info("[indexer] %d candidates from pipeline context", len(to_index))
        return to_index

    # No pipeline context — check Firestore + Qdrant
    from src.services.candidate_indexer import _get_indexed_candidate_counts
    from src.firebase_service import async_db

    # Get candidates with scraped websites from Firestore
    scraped_cids: set[str] = set()

    async def _get_scraped_cids() -> set[str]:
        result: set[str] = set()
        async for doc in async_db.collection("candidates").stream():
            data = doc.to_dict()
            if data.get("has_scraped"):
                result.add(doc.id)
        return result

    t0 = _time.monotonic()
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # We're already in an async context — create a task
        import concurrent.futures
        # Can't nest event loops; use sync Qdrant check
        scraped_cids = set()
        # This path won't actually be hit in normal pipeline flow
        # since scraped context is always set by crawl_scraper
    else:
        scraped_cids = loop.run_until_complete(_get_scraped_cids())
    logger.info("[indexer:timing] Firestore has_scraped scan took %.2fs", _time.monotonic() - t0)

    t0 = _time.monotonic()
    existing = _get_indexed_candidate_counts() if not force else {}
    logger.info("[indexer:timing] _get_indexed_candidate_counts() took %.2fs", _time.monotonic() - t0)
    logger.info("[indexer] %d candidates already indexed in Qdrant", len(existing))

    to_index = [
        c for c in candidates
        if c.candidate_id in scraped_cids
        and (force or c.candidate_id not in existing)
    ]
    logger.info(
        "[indexer] %d candidates to index (%d has_scraped, %d already indexed, force=%s)",
        len(to_index), len(scraped_cids), len(existing), force,
    )
    return to_index


async def _index_candidates(
    to_index: list,
    scraped: Any,
    tracker: PhaseTracker,
    cfg: NodeConfig,
    *,
    max_concurrent: int = 3,
    classify_themes: bool = True,
    force: bool = False,
) -> int:
    """Run concurrent indexing of candidate list. Returns total chunks."""
    from src.services.candidate_indexer import index_candidate_website
    from src.services.data_pipeline.crawl_scraper import load_scraped_from_drive

    candidates_indexed = 0
    indexed_count = 0
    index_errors = 0
    skipped_no_drive = 0
    tracker.update_progress("candidates", {"done": 0, "total": len(to_index), "chunks": 0})

    sem = asyncio.Semaphore(max_concurrent)

    async def _index_one(candidate: Any) -> int:
        nonlocal indexed_count, candidates_indexed, index_errors, skipped_no_drive
        async with sem:
            try:
                t_start = _time.monotonic()

                scraped_website = scraped.get(candidate.candidate_id) if scraped else None

                if scraped_website is None and candidate.website_url:
                    scraped_website = await load_scraped_from_drive(
                        candidate.candidate_id, candidate.website_url,
                    )
                    if scraped_website:
                        logger.info(
                            "[indexer] loaded %s from Drive (%d pages, %.1fs)",
                            candidate.full_name, len(scraped_website.pages),
                            _time.monotonic() - t_start,
                        )

                if scraped_website is None:
                    skipped_no_drive += 1
                    indexed_count += 1
                    logger.warning("[indexer] no Drive data for %s, skipping", candidate.full_name)
                    return 0

                count = await index_candidate_website(
                    candidate, scraped_website,
                    classify_themes=classify_themes,
                )
                candidates_indexed += count
                indexed_count += 1
                await asyncio.sleep(0)

                dur = _time.monotonic() - t_start
                logger.info(
                    "[indexer] %d/%d indexed %s (%d chunks, %.1fs)",
                    indexed_count, len(to_index), candidate.full_name, count, dur,
                )
                tracker.update_progress("candidates", {
                    "done": indexed_count,
                    "total": len(to_index),
                    "chunks": candidates_indexed,
                    "current": candidate.full_name,
                })
                await tracker.emit()
                return count
            except Exception as e:
                index_errors += 1
                indexed_count += 1
                logger.error(
                    "[indexer] error indexing %s: %s: %s",
                    candidate.candidate_id, type(e).__name__, e,
                    exc_info=True,
                )
                return 0

    t0 = _time.monotonic()
    await asyncio.gather(*[_index_one(c) for c in to_index])
    logger.info("[indexer:timing] all candidate indexing tasks took %.2fs", _time.monotonic() - t0)

    if skipped_no_drive:
        logger.warning("[indexer] %d candidates skipped (no Drive data)", skipped_no_drive)

    return candidates_indexed
