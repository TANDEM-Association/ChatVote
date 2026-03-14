"""Pipeline node: index content into Qdrant vector DB for RAG retrieval.

Indexes:
- Party manifestos (PDFs from Firebase Storage → chunks → embeddings)
- Candidate websites (Google Drive → chunks → embeddings)

Data flow: CrawlScraperNode puts content in Google Drive → IndexerNode reads
from Drive → chunks → embeds → Qdrant.  No Playwright scraping involved.

Disabled by default because each run involves costly LLM embedding calls.
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
        "index_manifestos": True,
        "index_candidates": True,
        "index_professions": True,
        "classify_themes": True,
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
        professions_indexed: int = 0
        errors: list[str] = []
        t0 = _time.monotonic()
        classify_themes = settings.get("classify_themes", True)

        # Allow env vars to override phase selection and tuning (useful for K8s Jobs)
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

        # --- Manifesto indexing -------------------------------------------
        if settings.get("index_manifestos", True):
            logger.info("[indexer] starting manifesto indexing phase...")
            await update_status(
                cfg.node_id, NodeStatus.RUNNING,
                counts={"phase": "manifestos", "parties_indexed": 0, "chunks_indexed": 0, "current": "loading parties..."},
            )
            try:
                from src.services.manifesto_indexer import index_all_parties

                logger.info("[indexer] calling index_all_parties()...")
                results = await index_all_parties()
                parties_indexed = sum(results.values())
                logger.info(
                    "[indexer] manifesto indexing complete: %d chunks across %d parties — details: %s",
                    parties_indexed, len(results), results,
                )
            except Exception as exc:
                msg = f"manifesto indexing failed: {type(exc).__name__}: {exc}"
                logger.exception("[indexer] %s", msg)
                errors.append(msg)
        else:
            logger.info("[indexer] manifesto indexing disabled, skipping")

        # --- Candidate website indexing -----------------------------------
        if settings.get("index_candidates", True):
            logger.info("[indexer] indexing candidate websites (Drive-only mode)...")
            await update_status(
                cfg.node_id, NodeStatus.RUNNING,
                counts={
                    "phase": "candidates",
                    "parties_indexed": parties_indexed,
                    "chunks_indexed": 0,
                },
            )
            try:
                from src.services.candidate_indexer import (
                    aget_candidates_with_website,
                    index_candidate_website,
                    _get_indexed_candidate_counts,
                )
                from src.services.data_pipeline.crawl_scraper import load_scraped_from_drive

                # Check pipeline context first (available when crawler ran in same pipeline)
                scraped = get_context("scraped_websites")

                logger.info("[indexer] fetching candidates with websites from Firestore...")
                candidates = await aget_candidates_with_website()
                logger.info("[indexer] found %d candidates with websites", len(candidates))

                # Only index candidates that have been scraped by the crawler
                if scraped:
                    # Pipeline context available — use it directly
                    scraped_ids = {
                        cid for cid, sw in scraped.items()
                        if sw and sw.is_successful
                    }
                    to_index = [
                        c for c in candidates
                        if c.candidate_id in scraped_ids
                    ]
                    logger.info(
                        "[indexer] %d candidates from pipeline context",
                        len(to_index),
                    )
                else:
                    # No pipeline context — filter to has_scraped candidates only
                    from src.firebase_service import async_db

                    scraped_cids: set[str] = set()
                    async for doc in async_db.collection("candidates").stream():
                        data = doc.to_dict()
                        if data.get("has_scraped"):
                            scraped_cids.add(doc.id)

                    existing = _get_indexed_candidate_counts() if not force else {}
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

                if not to_index:
                    logger.info("[indexer] no candidates to index")
                else:
                    indexed_count = 0
                    index_errors = 0
                    skipped_no_drive = 0

                    await update_status(
                        cfg.node_id, NodeStatus.RUNNING,
                        counts={
                            "phase": "candidates",
                            "parties_indexed": parties_indexed,
                            "chunks_indexed": 0,
                            "candidates_done": 0,
                            "candidates_total": len(to_index),
                            "elapsed_s": 0,
                            "eta_s": 0,
                        },
                    )

                    max_concurrent = int(cfg.settings.get("max_concurrent_index", 3))
                    sem = asyncio.Semaphore(max_concurrent)

                    async def _index_one(candidate: Any) -> int:
                        nonlocal indexed_count, candidates_indexed, index_errors, skipped_no_drive
                        async with sem:
                            try:
                                t_start = _time.monotonic()

                                # Source 1: pipeline context (same-run crawl)
                                scraped_website = scraped.get(candidate.candidate_id) if scraped else None

                                # Source 2: Google Drive (previous crawl run)
                                if scraped_website is None and candidate.website_url:
                                    scraped_website = await load_scraped_from_drive(
                                        candidate.candidate_id, candidate.website_url,
                                    )
                                    if scraped_website:
                                        logger.info(
                                            "[indexer] loaded %s from Drive (%d pages, %.1fs)",
                                            candidate.full_name,
                                            len(scraped_website.pages),
                                            _time.monotonic() - t_start,
                                        )

                                if scraped_website is None:
                                    skipped_no_drive += 1
                                    indexed_count += 1
                                    logger.warning(
                                        "[indexer] no Drive data for %s, skipping",
                                        candidate.full_name,
                                    )
                                    return 0

                                logger.info(
                                    "[indexer] indexing %s (%d pages, themes=%s)...",
                                    candidate.full_name,
                                    len(scraped_website.pages),
                                    classify_themes,
                                )
                                count = await index_candidate_website(
                                    candidate, scraped_website,
                                    classify_themes=classify_themes,
                                )
                                candidates_indexed += count
                                indexed_count += 1
                                # Yield to event loop so Socket.IO pings are not starved
                                await asyncio.sleep(0)
                                dur = _time.monotonic() - t_start
                                logger.info(
                                    "[indexer] %d/%d indexed %s (%d chunks, %.1fs)",
                                    indexed_count, len(to_index),
                                    candidate.full_name, count, dur,
                                )

                                # Update progress
                                elapsed = _time.monotonic() - t0
                                rate = indexed_count / elapsed if elapsed > 0 else 0
                                remaining = (len(to_index) - indexed_count) / rate if rate > 0 else 0
                                await update_status(
                                    cfg.node_id, NodeStatus.RUNNING,
                                    counts={
                                        "phase": "candidates",
                                        "parties_indexed": parties_indexed,
                                        "chunks_indexed": candidates_indexed,
                                        "candidates_done": indexed_count,
                                        "candidates_total": len(to_index),
                                        "current": candidate.full_name,
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
                                    "[indexer] error indexing %s: %s: %s",
                                    candidate.candidate_id, type(e).__name__, e,
                                    exc_info=True,
                                )
                                return 0

                    await asyncio.gather(*[_index_one(c) for c in to_index])

                    if skipped_no_drive:
                        logger.warning("[indexer] %d candidates skipped (no Drive data)", skipped_no_drive)

            except Exception as exc:
                msg = f"candidate indexing failed: {exc}"
                logger.exception("[indexer] %s", msg)
                errors.append(msg)
        else:
            logger.info("[indexer] candidate indexing disabled, skipping")

        # --- Profession de foi indexing -----------------------------------
        if settings.get("index_professions", True):
            logger.info("[indexer] starting profession de foi indexing phase...")
            await update_status(
                cfg.node_id, NodeStatus.RUNNING,
                counts={
                    "phase": "professions",
                    "parties_indexed": parties_indexed,
                    "candidates_chunks": candidates_indexed,
                    "professions_chunks": 0,
                },
            )
            try:
                from src.services.profession_indexer import (
                    index_commune_professions,
                    _PDF_CACHE_DIR,
                )

                if not _PDF_CACHE_DIR.exists():
                    logger.info("[indexer] no profession PDFs cached, skipping")
                else:
                    from src.services.data_pipeline.population import get_top_communes

                    top = get_top_communes()
                    allowed_codes = set(top.keys()) if top else None

                    commune_dirs = sorted(
                        d for d in _PDF_CACHE_DIR.iterdir() if d.is_dir()
                    )
                    if allowed_codes:
                        filtered = [d for d in commune_dirs if d.name in allowed_codes]
                        if len(filtered) < len(commune_dirs):
                            logger.info(
                                "[indexer] filtered profession communes: %d → %d (respecting top_communes)",
                                len(commune_dirs), len(filtered),
                            )
                        commune_dirs = filtered

                    already_indexed = (
                        cfg.checkpoints.get("profession_indexed_communes", {})
                        if not force
                        else {}
                    )
                    to_process = [
                        d for d in commune_dirs
                        if d.name not in already_indexed
                    ]
                    logger.info(
                        "[indexer] %d communes with profession PDFs "
                        "(%d already indexed, %d to process, force=%s)",
                        len(commune_dirs), len(already_indexed),
                        len(to_process), force,
                    )

                    prof_chunks = 0
                    prof_communes_done = 0
                    t_prof = _time.monotonic()

                    prof_sem = asyncio.Semaphore(3)

                    async def _index_one_commune(commune_dir: Any) -> None:
                        nonlocal prof_chunks, prof_communes_done
                        commune_code = commune_dir.name
                        async with prof_sem:
                            try:
                                results = await index_commune_professions(commune_code)
                                chunks = sum(results.values())
                                prof_chunks += chunks
                                prof_communes_done += 1

                                # Save checkpoint
                                cfg.checkpoints.setdefault(
                                    "profession_indexed_communes", {}
                                )[commune_code] = datetime.now(timezone.utc).isoformat()

                                # Progress update every 5 communes
                                if prof_communes_done % 5 == 0:
                                    elapsed_prof = _time.monotonic() - t_prof
                                    rate = prof_communes_done / elapsed_prof if elapsed_prof > 0 else 0
                                    remaining = (len(to_process) - prof_communes_done) / rate if rate > 0 else 0
                                    await update_status(
                                        cfg.node_id, NodeStatus.RUNNING,
                                        counts={
                                            "phase": "professions",
                                            "parties_indexed": parties_indexed,
                                            "candidates_chunks": candidates_indexed,
                                            "professions_chunks": prof_chunks,
                                            "communes_done": prof_communes_done,
                                            "communes_total": len(to_process),
                                            "current": commune_code,
                                            "rate_communes_per_sec": round(rate, 2),
                                            "elapsed_s": round(elapsed_prof, 1),
                                            "eta_s": round(remaining, 0),
                                        },
                                    )
                                    logger.info(
                                        "[indexer] professions: %d/%d communes, %d chunks, %.1f/s",
                                        prof_communes_done, len(to_process), prof_chunks, rate,
                                    )

                                # Yield to event loop
                                await asyncio.sleep(0)

                            except Exception as exc:
                                logger.error(
                                    "[indexer] profession indexing failed for commune %s: %s",
                                    commune_code, exc,
                                )

                    await asyncio.gather(*[_index_one_commune(d) for d in to_process])

                    professions_indexed = prof_chunks
                    logger.info(
                        "[indexer] profession de foi indexing complete: "
                        "%d chunks across %d communes",
                        prof_chunks, prof_communes_done,
                    )

            except Exception as exc:
                msg = f"profession indexing failed: {exc}"
                logger.exception("[indexer] %s", msg)
                errors.append(msg)
        else:
            logger.info("[indexer] profession de foi indexing disabled, skipping")

        # --- Final counts -------------------------------------------------
        elapsed = _time.monotonic() - t0
        cfg.counts = {
            "parties_indexed": parties_indexed,
            "chunks_indexed": candidates_indexed,
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
