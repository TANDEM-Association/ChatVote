"""Indexer phase: profession de foi PDFs."""
from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime, timezone
from typing import Any

from src.services.data_pipeline.base import NodeConfig
from src.services.data_pipeline.indexer.progress import PhaseTracker

logger = logging.getLogger(__name__)


async def run_profession_phase(
    cfg: NodeConfig,
    tracker: PhaseTracker,
    *,
    force: bool = False,
) -> int:
    """Index profession de foi PDFs into candidates_websites collection.

    Returns total chunks indexed.
    """
    if not cfg.settings.get("index_professions", True):
        logger.info("[indexer] profession de foi indexing disabled, skipping")
        return 0

    logger.info("[indexer] starting profession de foi indexing phase...")

    from src.services.profession_indexer import index_commune_professions, _PDF_CACHE_DIR

    if not _PDF_CACHE_DIR.exists():
        logger.info("[indexer] no profession PDFs cached, skipping")
        return 0

    commune_dirs = _get_commune_dirs_to_process(_PDF_CACHE_DIR, cfg, force)
    if not commune_dirs:
        return 0

    return await _index_communes(commune_dirs, cfg, tracker)


def _get_commune_dirs_to_process(
    pdf_cache_dir: Any,
    cfg: NodeConfig,
    force: bool,
) -> list:
    """Get filtered list of commune directories that need indexing."""
    from src.services.data_pipeline.population import get_top_communes

    t0 = _time.monotonic()
    commune_dirs = sorted(d for d in pdf_cache_dir.iterdir() if d.is_dir())

    top = get_top_communes()
    allowed_codes = set(top.keys()) if top else None
    if allowed_codes:
        filtered = [d for d in commune_dirs if d.name in allowed_codes]
        if len(filtered) < len(commune_dirs):
            logger.info(
                "[indexer] filtered profession communes: %d -> %d (respecting top_communes)",
                len(commune_dirs), len(filtered),
            )
        commune_dirs = filtered
    logger.info("[indexer:timing] profession dir scan took %.2fs", _time.monotonic() - t0)

    already_indexed = cfg.checkpoints.get("profession_indexed_communes", {}) if not force else {}
    to_process = [d for d in commune_dirs if d.name not in already_indexed]
    logger.info(
        "[indexer] %d communes with profession PDFs "
        "(%d already indexed, %d to process, force=%s)",
        len(commune_dirs), len(already_indexed), len(to_process), force,
    )
    return to_process


async def _index_communes(
    to_process: list,
    cfg: NodeConfig,
    tracker: PhaseTracker,
) -> int:
    """Concurrently index profession de foi for a list of commune directories."""
    from src.services.profession_indexer import index_commune_professions

    prof_chunks = 0
    prof_communes_done = 0
    tracker.update_progress("professions", {"done": 0, "total": len(to_process), "chunks": 0})

    sem = asyncio.Semaphore(3)

    async def _index_one_commune(commune_dir: Any) -> None:
        nonlocal prof_chunks, prof_communes_done
        commune_code = commune_dir.name
        async with sem:
            try:
                t0 = _time.monotonic()
                results = await index_commune_professions(commune_code)
                chunks = sum(results.values())
                logger.info(
                    "[indexer:timing] index_commune_professions(%s) took %.2fs, %d chunks",
                    commune_code, _time.monotonic() - t0, chunks,
                )
                prof_chunks += chunks
                prof_communes_done += 1

                cfg.checkpoints.setdefault(
                    "profession_indexed_communes", {}
                )[commune_code] = datetime.now(timezone.utc).isoformat()

                tracker.update_progress("professions", {
                    "done": prof_communes_done,
                    "total": len(to_process),
                    "chunks": prof_chunks,
                    "current": commune_code,
                })
                if prof_communes_done % 5 == 0:
                    await tracker.emit()
                    logger.info(
                        "[indexer] professions: %d/%d communes, %d chunks",
                        prof_communes_done, len(to_process), prof_chunks,
                    )

                await asyncio.sleep(0)

            except Exception as exc:
                logger.error(
                    "[indexer] profession indexing failed for commune %s: %s",
                    commune_code, exc,
                )

    t0 = _time.monotonic()
    await asyncio.gather(*[_index_one_commune(d) for d in to_process])
    logger.info("[indexer:timing] all profession indexing tasks took %.2fs", _time.monotonic() - t0)

    logger.info(
        "[indexer] profession de foi indexing complete: %d chunks across %d communes",
        prof_chunks, prof_communes_done,
    )
    return prof_chunks
