"""Indexer phase: party manifestos (PDFs from Firebase Storage)."""
from __future__ import annotations

import logging
import time as _time

from src.services.data_pipeline.base import NodeConfig
from src.services.data_pipeline.indexer.progress import PhaseTracker

logger = logging.getLogger(__name__)


async def run_manifesto_phase(
    cfg: NodeConfig,
    tracker: PhaseTracker,
    *,
    force: bool = False,
) -> int:
    """Index party manifestos into all_parties collection.

    Returns total chunks indexed.
    """
    settings = cfg.settings
    if not settings.get("index_manifestos", True):
        logger.info("[indexer] manifesto indexing disabled, skipping")
        return 0

    # Skip if already indexed this pipeline run (checkpoint-based)
    already = cfg.checkpoints.get("manifesto_indexed_parties", {})
    if already and not force:
        logger.info("[indexer] manifestos already indexed (%d parties), skipping", len(already))
        return 0

    logger.info("[indexer] starting manifesto indexing phase...")
    tracker.update_progress("manifestos", {"chunks": 0, "parties": 0})

    from src.services.manifesto_indexer import index_all_parties

    t0 = _time.monotonic()
    results = await index_all_parties()
    logger.info("[indexer:timing] index_all_parties() took %.2fs", _time.monotonic() - t0)

    total = sum(results.values())
    tracker.update_progress("manifestos", {"chunks": total, "parties": len(results)})

    # Save checkpoint so next run skips
    cfg.checkpoints["manifesto_indexed_parties"] = {
        pid: cnt for pid, cnt in results.items()
    }
    logger.info(
        "[indexer] manifesto indexing complete: %d chunks across %d parties — details: %s",
        total, len(results), results,
    )
    await tracker.emit()
    return total
