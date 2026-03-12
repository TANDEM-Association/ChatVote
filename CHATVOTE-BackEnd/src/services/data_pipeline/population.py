"""Pipeline node: fetch communes with population from geo.api.gouv.fr and pick top N."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from typing import Any

import aiohttp

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    register_node,
    save_checkpoint,
    should_skip,
)

logger = logging.getLogger(__name__)

# geo.api.gouv.fr returns all ~35k communes as JSON with population data
GEO_API_URL = (
    "https://geo.api.gouv.fr/communes"
    "?fields=nom,code,population,codeDepartement,codeRegion,codesPostaux,codeEpci"
    ",departement,region,epci,zone,surface,siren"
    "&boost=population"
)

# ---------------------------------------------------------------------------
# Module-level cache so other nodes can access the result
# ---------------------------------------------------------------------------
_cached_communes: dict[str, dict[str, Any]] | None = None
_cached_all_communes: dict[str, dict[str, Any]] | None = None


def get_top_communes() -> dict[str, dict[str, Any]] | None:
    """Return the top N communes dict populated by the last run, or ``None``."""
    return _cached_communes


def get_all_communes() -> dict[str, dict[str, Any]] | None:
    """Return ALL communes dict populated by the last run, or ``None``."""
    return _cached_all_communes


# ---------------------------------------------------------------------------
# Node implementation
# ---------------------------------------------------------------------------
class PopulationNode(DataSourceNode):
    node_id = "population"
    label = "Population INSEE"
    default_settings: dict[str, Any] = {"communes_to_scrap": 287}

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        global _cached_communes, _cached_all_communes

        api_url = os.environ.get("GEO_API_COMMUNES_URL", GEO_API_URL)
        top_n: int = int(
            cfg.settings.get("communes_to_scrap") or cfg.settings.get("top_communes", 287)
        )

        # ------------------------------------------------------------------
        # 1. Fetch communes JSON from geo.api.gouv.fr
        # ------------------------------------------------------------------
        logger.info("[population] fetching %s", api_url)
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                resp.raise_for_status()
                raw_bytes = await resp.read()

        # ------------------------------------------------------------------
        # 2. Check content hash — skip if unchanged (unless forced)
        # ------------------------------------------------------------------
        h = hashlib.sha256()
        h.update(raw_bytes[:10240])
        h.update(str(len(raw_bytes)).encode())
        source_hash = f"sha256:{h.hexdigest()}"
        stored_hash = cfg.checkpoints.get("source_hash")

        if not force and should_skip(source_hash, stored_hash) and _cached_communes is not None and _cached_all_communes is not None:
            logger.info("[population] data unchanged (hash=%s), skipping", source_hash)
            return cfg

        # ------------------------------------------------------------------
        # 3. Parse JSON
        # ------------------------------------------------------------------
        data = json.loads(raw_bytes)

        communes: list[dict[str, Any]] = []
        for item in data:
            pop = item.get("population", 0) or 0
            dep_obj = item.get("departement") or {}
            reg_obj = item.get("region") or {}
            epci_obj = item.get("epci") or {}
            communes.append({
                "code": item["code"],
                "nom": item["nom"],
                "population": pop,
                "dep_code": item.get("codeDepartement", ""),
                "dep_nom": dep_obj.get("nom", ""),
                "reg_code": item.get("codeRegion", ""),
                "reg_nom": reg_obj.get("nom", ""),
                "code_postal": (item.get("codesPostaux") or [""])[0],
                "codes_postaux": item.get("codesPostaux") or [],
                "epci_code": item.get("codeEpci", ""),
                "epci_nom": epci_obj.get("nom", ""),
                "zone": item.get("zone", ""),
                "surface": item.get("surface", 0) or 0,
                "siren": item.get("siren", ""),
            })

        # ------------------------------------------------------------------
        # 4. Sort by population desc, pick top N
        # ------------------------------------------------------------------
        communes.sort(key=lambda c: c["population"], reverse=True)
        top = communes[:top_n]

        if not top:
            raise ValueError("No communes found — geo API returned empty data")

        top_dict = {c["code"]: c for c in top}
        all_dict = {c["code"]: c for c in communes}
        _cached_communes = top_dict
        _cached_all_communes = all_dict

        # ------------------------------------------------------------------
        # 5. Update config: checkpoints and counts
        # ------------------------------------------------------------------
        cfg.checkpoints["source_hash"] = source_hash
        await save_checkpoint(cfg.node_id, cfg.checkpoints)

        cfg.counts = {
            "total_all_communes": len(all_dict),
            "total_communes": len(top_dict),
            "largest_name": top[0]["nom"],
            "largest_pop": top[0]["population"],
            "smallest_name": top[-1]["nom"],
            "smallest_pop": top[-1]["population"],
        }

        logger.info(
            "[population] fetched %d communes → top %d (to scrap)  |  largest: %s (%s)  smallest: %s (%s)",
            len(all_dict),
            len(top_dict),
            top[0]["nom"],
            f"{top[0]['population']:,}",
            top[-1]["nom"],
            f"{top[-1]['population']:,}",
        )

        return cfg


register_node(PopulationNode())
