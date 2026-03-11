"""Pipeline node: index content into Qdrant vector DB for RAG retrieval.

Indexes:
- Party manifestos (PDFs from Firebase Storage → chunks → embeddings)
- Candidate websites (uses pre-scraped data from scraper node → chunks → embeddings)

Disabled by default because each run involves costly LLM embedding calls.
"""
from __future__ import annotations

import logging
import time as _time
from datetime import datetime, timezone
from typing import Any

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    NodeStatus,
    register_node,
    update_status,
    get_context,
)

logger = logging.getLogger(__name__)


class IndexerNode(DataSourceNode):
    node_id = "indexer"
    label = "Qdrant Indexer"
    default_settings: dict[str, Any] = {
        "enabled": False,
        "index_manifestos": True,
        "index_candidates": True,
    }

    def default_config(self) -> NodeConfig:
        return NodeConfig(
            node_id=self.node_id,
            label=self.label,
            enabled=False,
            settings={**self.default_settings},
        )

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        settings = cfg.settings
        parties_indexed: int = 0
        candidates_indexed: int = 0
        errors: list[str] = []
        t0 = _time.monotonic()

        # --- Manifesto indexing -------------------------------------------
        if settings.get("index_manifestos", True):
            logger.info("[indexer] indexing party manifestos...")
            await update_status(
                cfg.node_id, NodeStatus.RUNNING,
                counts={"phase": "manifestos", "parties_indexed": 0, "candidates_indexed": 0},
            )
            try:
                from src.services.manifesto_indexer import index_all_parties

                results = await index_all_parties()
                parties_indexed = sum(results.values())
                logger.info(
                    "[indexer] manifesto indexing complete: %d chunks across %d parties",
                    parties_indexed, len(results),
                )
            except Exception as exc:
                msg = f"manifesto indexing failed: {exc}"
                logger.exception("[indexer] %s", msg)
                errors.append(msg)
        else:
            logger.info("[indexer] manifesto indexing disabled, skipping")

        # --- Candidate website indexing -----------------------------------
        if settings.get("index_candidates", True):
            logger.info("[indexer] indexing candidate websites...")
            await update_status(
                cfg.node_id, NodeStatus.RUNNING,
                counts={
                    "phase": "candidates",
                    "parties_indexed": parties_indexed,
                    "candidates_indexed": 0,
                },
            )
            try:
                import asyncio

                from src.services.candidate_indexer import (
                    aget_candidates_with_website,
                    index_candidate_website,
                    _get_indexed_candidate_counts,
                )
                # Use pre-scraped data from pipeline context if available
                scraped = get_context("scraped_websites")
                candidates = await aget_candidates_with_website()
                existing = _get_indexed_candidate_counts() if not force else {}

                if scraped:
                    # Always re-index pre-scraped candidates (crawl service
                    # content is fresher than old Playwright scrapes)
                    scraped_ids = {
                        cid for cid, sw in scraped.items()
                        if sw and sw.is_successful
                    }
                    to_index = [
                        c for c in candidates
                        if c.candidate_id in scraped_ids
                    ]
                else:
                    to_index = [c for c in candidates if c.candidate_id not in existing]

                logger.info(
                    "[indexer] %d candidates to index (%d already done, %d pre-scraped)",
                    len(to_index), len(existing),
                    len(scraped) if scraped else 0,
                )

                indexed_count = 0
                index_errors = 0
                # Initial progress so the UI shows totals immediately
                await update_status(
                    cfg.node_id, NodeStatus.RUNNING,
                    counts={
                        "phase": "candidates",
                        "parties_indexed": parties_indexed,
                        "candidates_indexed": 0,
                        "candidates_done": 0,
                        "candidates_total": len(to_index),
                        "elapsed_s": 0,
                        "eta_s": 0,
                    },
                )

                # Index candidates concurrently (embedding API calls are I/O bound)
                max_concurrent = int(cfg.settings.get("max_concurrent_index", 3))
                sem = asyncio.Semaphore(max_concurrent)

                async def _index_one(candidate: Any) -> int:
                    nonlocal indexed_count, candidates_indexed, index_errors
                    async with sem:
                        try:
                            t_start = _time.monotonic()
                            scraped_website = scraped.get(candidate.candidate_id) if scraped else None
                            count = await index_candidate_website(candidate, scraped_website)
                            candidates_indexed += count
                            indexed_count += 1
                            logger.info(
                                "[indexer] %d/%d indexed %s (%d chunks, %.1fs)",
                                indexed_count, len(to_index),
                                candidate.full_name, count,
                                _time.monotonic() - t_start,
                            )

                            # Update progress periodically
                            if indexed_count % 3 == 0 or indexed_count == len(to_index):
                                elapsed = _time.monotonic() - t0
                                rate = indexed_count / elapsed if elapsed > 0 else 0
                                remaining = (len(to_index) - indexed_count) / rate if rate > 0 else 0
                                await update_status(
                                    cfg.node_id, NodeStatus.RUNNING,
                                    counts={
                                        "phase": "candidates",
                                        "parties_indexed": parties_indexed,
                                        "candidates_indexed": candidates_indexed,
                                        "candidates_done": indexed_count,
                                        "candidates_total": len(to_index),
                                        "rate_per_sec": round(rate, 2),
                                        "elapsed_s": round(elapsed, 1),
                                        "eta_s": round(remaining, 0),
                                    },
                                )
                            return count
                        except Exception as e:
                            index_errors += 1
                            indexed_count += 1
                            logger.error(
                                "[indexer] error indexing %s: %s", candidate.candidate_id, e
                            )
                            return 0

                await asyncio.gather(*[_index_one(c) for c in to_index])

            except Exception as exc:
                msg = f"candidate indexing failed: {exc}"
                logger.exception("[indexer] %s", msg)
                errors.append(msg)
        else:
            logger.info("[indexer] candidate indexing disabled, skipping")

        # --- Final counts -------------------------------------------------
        elapsed = _time.monotonic() - t0
        cfg.counts = {
            "parties_indexed": parties_indexed,
            "candidates_indexed": candidates_indexed,
            "elapsed_s": round(elapsed, 1),
        }
        cfg.checkpoints["last_indexed_at"] = datetime.now(timezone.utc).isoformat()

        if errors and parties_indexed == 0 and candidates_indexed == 0:
            raise RuntimeError("; ".join(errors))

        if errors:
            cfg.last_error = "; ".join(errors)

        return cfg


register_node(IndexerNode())
