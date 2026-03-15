"""Pipeline node: fetch communes with population from geo.api.gouv.fr and pick top N."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time as _time
from datetime import datetime, timezone
from typing import Any

import aiohttp

from src.services.data_pipeline.url_cache import cached_fetch_text
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
    default_settings: dict[str, Any] = {"communes_to_scrap": None}

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        global _cached_communes, _cached_all_communes

        api_url = os.environ.get("GEO_API_COMMUNES_URL", GEO_API_URL)
        raw_top_n = cfg.settings.get("communes_to_scrap")
        if not raw_top_n:
            raise ValueError(
                "communes_to_scrap is not set — "
                "configure it in the pipeline dashboard before running"
            )
        top_n: int = int(raw_top_n)

        # ------------------------------------------------------------------
        # 1. Fetch communes JSON from geo.api.gouv.fr
        # ------------------------------------------------------------------
        logger.info("[population] fetching %s", api_url)
        _t_fetch = _time.monotonic()
        async with aiohttp.ClientSession() as session:
            text = await cached_fetch_text(session, api_url)
        if text is None:
            raise RuntimeError(f"Failed to fetch {api_url}")
        raw_bytes = text.encode("utf-8")
        logger.info("[node:timing] [population:timing] api_fetch took %.2fs, %d bytes", _time.monotonic() - _t_fetch, len(raw_bytes))

        # ------------------------------------------------------------------
        # 2. Check content hash — skip if unchanged (unless forced)
        # ------------------------------------------------------------------
        h = hashlib.sha256()
        h.update(raw_bytes[:10240])
        h.update(str(len(raw_bytes)).encode())
        source_hash = f"sha256:{h.hexdigest()}"
        stored_hash = cfg.checkpoints.get("source_hash")

        # Also re-process if top_n changed (setting update without data change)
        cached_top_n = cfg.checkpoints.get("top_n")
        settings_changed = cached_top_n is not None and int(cached_top_n) != top_n

        if not force and not settings_changed and should_skip(source_hash, stored_hash) and _cached_communes is not None and _cached_all_communes is not None:
            logger.info("[population] data unchanged (hash=%s), skipping", source_hash)
            return cfg

        # ------------------------------------------------------------------
        # 3. Parse JSON
        # ------------------------------------------------------------------
        _t_parse = _time.monotonic()
        data = json.loads(raw_bytes)
        logger.info("[node:timing] [population:timing] json_parse took %.2fs", _time.monotonic() - _t_parse)

        _t_build = _time.monotonic()
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
        logger.info("[node:timing] [population:timing] communes_build took %.2fs, %d communes", _time.monotonic() - _t_build, len(communes))

        # ------------------------------------------------------------------
        # 4. Sort by population desc, pick top N
        # ------------------------------------------------------------------
        _t_sort = _time.monotonic()
        communes.sort(key=lambda c: c["population"], reverse=True)
        top = communes[:top_n]

        if not top:
            raise ValueError("No communes found — geo API returned empty data")

        top_dict = {c["code"]: c for c in top}
        all_dict = {c["code"]: c for c in communes}
        logger.info("[node:timing] [population:timing] sort_and_slice took %.2fs", _time.monotonic() - _t_sort)
        _cached_communes = top_dict
        _cached_all_communes = all_dict

        # ------------------------------------------------------------------
        # 5. Update config: checkpoints and counts
        # ------------------------------------------------------------------
        cfg.checkpoints["source_hash"] = source_hash
        cfg.checkpoints["top_n"] = top_n
        cfg.checkpoints["cached_at"] = datetime.now(timezone.utc).isoformat()
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
