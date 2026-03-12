#!/usr/bin/env python3
"""Seed Firestore with ALL communes that have cached profession de foi PDFs.

Runs the pipeline: population → candidatures → seed, with communes_to_scrap
set high enough to cover all communes with cached PDFs.

Usage:
    cd CHATVOTE-BackEnd
    poetry run python scripts/seed_all_profession_communes.py
"""

import asyncio
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PDF_CACHE_DIR = Path(tempfile.gettempdir()) / "chatvote_professions_pdfs"


async def main():
    # 1. Find all commune codes with cached PDFs
    cached_communes = set()
    if PDF_CACHE_DIR.exists():
        for d in PDF_CACHE_DIR.iterdir():
            if d.is_dir() and any(d.iterdir()):
                cached_communes.add(d.name)

    logger.info(f"Found {len(cached_communes)} communes with cached PDFs")

    # 2. Check which are already seeded in Firestore
    from src.firebase_service import async_db

    seeded = set()
    munis = await async_db.collection("municipalities").get()
    for m in munis:
        seeded.add(m.id)

    missing = cached_communes - seeded
    logger.info(f"Already seeded: {len(seeded)}, missing: {len(missing)}")

    if not missing:
        logger.info("All communes with PDFs are already seeded!")
        return

    # 3. Run pipeline: population → candidatures → seed
    # We need communes_to_scrap high enough to include all missing communes
    # The API returns ~35k communes sorted by population desc
    # Set to 500 to be safe (covers all communes with >15k population)
    from src.services.data_pipeline.base import load_config, NodeConfig
    from src.services.data_pipeline.population import PopulationNode
    from src.services.data_pipeline.candidatures import CandidaturesNode
    from src.services.data_pipeline.seed import SeedNode

    target_n = 500  # should cover all 142+ communes

    # Population node
    logger.info(f"=== Running population node (top {target_n}) ===")
    pop_node = PopulationNode()
    pop_cfg = await load_config("population", pop_node.default_config())
    pop_cfg.settings["communes_to_scrap"] = target_n
    pop_cfg = await pop_node.run(pop_cfg, force=True)
    logger.info(f"Population: {pop_cfg.counts}")

    # Verify all cached communes are covered
    from src.services.data_pipeline.population import get_top_communes

    top = get_top_communes()
    still_missing = cached_communes - set(top.keys())
    if still_missing:
        logger.warning(
            f"{len(still_missing)} communes still not in top {target_n}: "
            f"{list(still_missing)[:10]}..."
        )

    # Candidatures node
    logger.info("=== Running candidatures node ===")
    cand_node = CandidaturesNode()
    cand_cfg = await load_config("candidatures", cand_node.default_config())
    cand_cfg.settings["top_communes"] = target_n
    cand_cfg = await cand_node.run(cand_cfg, force=True)
    logger.info(f"Candidatures: {cand_cfg.counts}")

    # Seed node — monkey-patch save_checkpoint to strip doc_hashes
    # that bloat beyond Firestore's 4MB gRPC limit at 500+ communes
    logger.info("=== Running seed node ===")
    import src.services.data_pipeline.base as base_mod
    import src.services.data_pipeline.seed as seed_mod
    _original_save_checkpoint = base_mod.save_checkpoint

    async def _slim_save_checkpoint(node_id, checkpoints):
        slim = {k: v for k, v in checkpoints.items() if not k.endswith("_doc_hashes")}
        return await _original_save_checkpoint(node_id, slim)

    seed_mod.save_checkpoint = _slim_save_checkpoint

    seed_node = SeedNode()
    seed_cfg = await load_config("seed", seed_node.default_config())
    seed_cfg.checkpoints = {k: v for k, v in seed_cfg.checkpoints.items() if not k.endswith("_doc_hashes")}
    seed_cfg = await seed_node.run(seed_cfg, force=True)
    logger.info(f"Seed: {seed_cfg.counts}")

    seed_mod.save_checkpoint = _original_save_checkpoint

    # Verify
    munis_after = await async_db.collection("municipalities").get()
    cands_after = await async_db.collection("candidates").get()
    newly_seeded = set(m.id for m in munis_after) - seeded

    logger.info(
        f"\n=== Results ===\n"
        f"Municipalities: {len(seeded)} → {len(munis_after)}\n"
        f"Newly seeded communes: {len(newly_seeded)}\n"
        f"Total candidates: {len(cands_after)}\n"
        f"Communes with PDFs now seeded: {len(cached_communes - (cached_communes - set(m.id for m in munis_after)))}"
    )


if __name__ == "__main__":
    asyncio.run(main())
