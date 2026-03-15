"""Pipeline node: index content into Qdrant vector DB for RAG retrieval.

Indexes:
- Party manifestos (PDFs from Firebase Storage -> chunks -> embeddings)
- Candidate websites (Google Drive -> chunks -> embeddings)
- Social media content
- Profession de foi PDFs

Each phase is in its own module for testability. This file is the thin
orchestrator that runs them in parallel.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time as _time
from datetime import datetime, timezone
from typing import Any

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    register_node,
)
from src.services.data_pipeline.indexer.progress import PhaseTracker

logger = logging.getLogger(__name__)


def _parse_env_overrides(settings: dict[str, Any]) -> bool:
    """Apply env var overrides to settings. Returns classify_themes flag."""
    classify_themes = settings.get("classify_themes", True)

    if os.getenv("INDEX_SKIP_MANIFESTOS", "").lower() in ("true", "1", "yes"):
        settings["index_manifestos"] = False
    if os.getenv("INDEX_SKIP_CANDIDATES", "").lower() in ("true", "1", "yes"):
        settings["index_candidates"] = False
    if os.getenv("INDEX_SKIP_PROFESSIONS", "").lower() in ("true", "1", "yes"):
        settings["index_professions"] = False
    if os.getenv("CLASSIFY_THEMES", "").lower() in ("false", "0", "no"):
        classify_themes = False
    if os.getenv("MAX_CONCURRENT_INDEX"):
        settings["max_concurrent_index"] = int(os.getenv("MAX_CONCURRENT_INDEX"))
    if os.getenv("MAX_PAGES_PER_CANDIDATE"):
        settings["max_pages_per_candidate"] = int(os.getenv("MAX_PAGES_PER_CANDIDATE"))

    max_pages = int(settings.get("max_pages_per_candidate", 10))
    os.environ["MAX_PAGES_PER_CANDIDATE"] = str(max_pages)

    return classify_themes


class IndexerNode(DataSourceNode):
    node_id = "indexer"
    label = "Qdrant Indexer"
    default_settings: dict[str, Any] = {
        "index_manifestos": True,
        "index_candidates": True,
        "index_professions": True,
        "classify_themes": False,
        "max_pages_per_candidate": 10,
    }

    def default_config(self) -> NodeConfig:
        return NodeConfig(
            node_id=self.node_id,
            label=self.label,
            enabled=False,
            settings={**self.default_settings},
        )

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        errors: list[str] = []
        t0 = _time.monotonic()
        classify_themes = _parse_env_overrides(cfg.settings)

        tracker = PhaseTracker(cfg.node_id)

        # Import phase runners
        from src.services.data_pipeline.indexer.manifesto_phase import run_manifesto_phase
        from src.services.data_pipeline.indexer.candidate_phase import run_candidate_phase
        from src.services.data_pipeline.indexer.social_phase import run_social_phase
        from src.services.data_pipeline.indexer.profession_phase import run_profession_phase

        # Wrap each phase with tracking and error collection
        async def _tracked(name: str, coro: Any) -> int:
            await tracker.start_phase(name)
            try:
                result = await coro
                await tracker.finish_phase(name)
                return result
            except Exception as exc:
                await tracker.error_phase(name)
                msg = f"{name} indexing failed: {type(exc).__name__}: {exc}"
                logger.exception("[indexer] %s", msg)
                errors.append(msg)
                return 0

        # Run all phases concurrently
        logger.info("[indexer] launching all indexing phases in parallel...")
        t_all = _time.monotonic()

        parties_indexed, candidates_indexed, social_indexed, professions_indexed = (
            await asyncio.gather(
                _tracked("manifestos", run_manifesto_phase(cfg, tracker, force=force)),
                _tracked("candidates", run_candidate_phase(
                    cfg, tracker, force=force, classify_themes=classify_themes,
                )),
                _tracked("social", run_social_phase(
                    cfg, tracker, force=force, classify_themes=classify_themes,
                )),
                _tracked("professions", run_profession_phase(cfg, tracker, force=force)),
            )
        )
        logger.info("[indexer:timing] all parallel phases took %.2fs", _time.monotonic() - t_all)

        # Final counts
        elapsed = _time.monotonic() - t0
        cfg.counts = {
            "parties_indexed": parties_indexed,
            "chunks_indexed": candidates_indexed,
            "social_indexed": social_indexed,
            "professions_indexed": professions_indexed,
            "elapsed_s": round(elapsed, 1),
        }
        cfg.checkpoints["last_indexed_at"] = datetime.now(timezone.utc).isoformat()
        cfg.checkpoints["cached_at"] = datetime.now(timezone.utc).isoformat()

        if errors and parties_indexed == 0 and candidates_indexed == 0:
            raise RuntimeError("; ".join(errors))

        if errors:
            cfg.last_error = "; ".join(errors)

        return cfg


register_node(IndexerNode())
