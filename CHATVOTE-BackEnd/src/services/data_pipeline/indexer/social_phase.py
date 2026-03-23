"""Indexer phase: social media content."""
from __future__ import annotations

import logging
import os
import time as _time
from datetime import datetime, timezone

from src.services.data_pipeline.base import NodeConfig
from src.services.data_pipeline.indexer.progress import PhaseTracker

logger = logging.getLogger(__name__)


async def run_social_phase(
    cfg: NodeConfig,
    tracker: PhaseTracker,
    *,
    force: bool = False,
    classify_themes: bool = True,
) -> int:
    """Index social media content into candidates_websites collection.

    Returns total chunks indexed.
    """
    skip_social = os.getenv("INDEX_SKIP_SOCIAL", "true").lower() in ("true", "1", "yes")
    if not cfg.settings.get("index_social", True) or skip_social:
        logger.info("[indexer] social media indexing disabled, skipping")
        return 0

    logger.info("[indexer] starting social media indexing phase...")
    social_indexed = 0

    from src.services.data_pipeline.social_scraper import scrape_social_candidates
    from src.services.data_pipeline.crawl_scraper import CrawlScraperNode, _get_crawl_credentials
    from src.services.candidate_indexer import index_candidate_website
    import aiohttp

    t0 = _time.monotonic()
    creds = _get_crawl_credentials()
    node = CrawlScraperNode()
    sheet_id = node.default_settings["sheet_id"]

    async with aiohttp.ClientSession() as session:
        token = node._ensure_token(creds)
        rows = await node._fetch_sheet_rows(session, sheet_id, token)
    logger.info("[indexer:timing] social sheet fetch took %.2fs", _time.monotonic() - t0)

    social_candidates = _build_social_candidate_list(rows, cfg, force)
    logger.info("[indexer] %d social media candidates to scrape", len(social_candidates))

    if not social_candidates:
        return 0

    t0 = _time.monotonic()
    scraped = scrape_social_candidates(social_candidates)
    logger.info("[indexer:timing] scrape_social_candidates() took %.2fs", _time.monotonic() - t0)
    logger.info("[indexer] scraped %d/%d social candidates", len(scraped), len(social_candidates))

    from src.firebase_service import aget_candidate_by_id, async_db

    for cid, sw in scraped.items():
        try:
            t_social_one = _time.monotonic()
            candidate = await aget_candidate_by_id(cid)
            if not candidate:
                logger.warning("[indexer] social candidate %s not in Firestore", cid)
                continue

            t_idx = _time.monotonic()
            count = await index_candidate_website(
                candidate, sw, classify_themes=classify_themes,
            )
            logger.info(
                "[indexer:timing] social index_candidate_website(%s) took %.2fs, %d chunks",
                cid, _time.monotonic() - t_idx, count,
            )
            social_indexed += count

            await async_db.collection("candidates").document(cid).set(
                {"has_scraped": True}, merge=True,
            )
            cfg.checkpoints.setdefault("social_indexed_candidates", {})[cid] = (
                datetime.now(timezone.utc).isoformat()
            )
            logger.info(
                "[indexer:timing] social candidate %s total took %.2fs, %d chunks",
                cid, _time.monotonic() - t_social_one, count,
            )
        except Exception as exc:
            logger.error("[indexer] social indexing failed for %s: %s", cid, exc)

    return social_indexed


def _build_social_candidate_list(
    rows: list,
    cfg: NodeConfig,
    force: bool,
) -> list[dict[str, str]]:
    """Filter sheet rows to social media candidates needing indexing."""
    from src.services.data_pipeline.social_scraper import detect_platform
    from src.services.data_pipeline.population import get_top_communes

    top_communes = get_top_communes()
    top_commune_codes = set(top_communes.keys()) if top_communes else None
    already_social = cfg.checkpoints.get("social_indexed_candidates", {})

    social_candidates = []
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
        if not force and cid in already_social:
            continue
        if top_commune_codes is not None:
            parts = cid.split("-")
            commune_code = parts[1] if len(parts) >= 3 else None
            if commune_code not in top_commune_codes:
                continue

        social_candidates.append({"candidate_id": cid, "url": url, "name": name})

    return social_candidates
