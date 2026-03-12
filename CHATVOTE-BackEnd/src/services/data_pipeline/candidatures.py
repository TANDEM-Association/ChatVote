"""Pipeline node: load data.gouv.fr municipal elections candidatures CSV.

Supports both remote URLs and local file paths via DATA_GOUV_CANDIDATURES_URL.
"""
from __future__ import annotations

import csv
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import aiohttp

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    content_hash,
    register_node,
    save_checkpoint,
    should_skip,
)
from src.services.data_pipeline.population import get_all_communes, get_top_communes

logger = logging.getLogger(__name__)

DEFAULT_CSV_URL = (
    "https://static.data.gouv.fr/resources/"
    "elections-municipales-2026-listes-candidates-au-premier-tour/"
    "20260306-161147/municipales-2026-candidatures-france-entiere-tour-1-2026-03-06-13h56.csv"
)

# ---------------------------------------------------------------------------
# Module-level cache so other nodes can access the result
# ---------------------------------------------------------------------------
_cached_communes: dict[str, dict] | None = None


def get_candidatures() -> dict[str, dict] | None:
    """Return the parsed candidatures dict populated by the last run, or ``None``."""
    return _cached_communes


# ---------------------------------------------------------------------------
# Node implementation
# ---------------------------------------------------------------------------
class CandidaturesNode(DataSourceNode):
    node_id = "candidatures"
    label = "Candidatures CSV"
    default_settings: dict[str, Any] = {}

    async def _load_csv(self, source: str, force: bool, cfg: NodeConfig) -> tuple[str, str, str]:
        """Load CSV to a temp file. Returns (tmp_path, source_hash, last_modified).

        *source* can be a URL (http/https) or a local file path.
        """
        if source.startswith("http://") or source.startswith("https://"):
            return await self._download_csv(source, force, cfg)
        else:
            return self._copy_local_csv(source, cfg)

    async def _download_csv(self, url: str, force: bool, cfg: NodeConfig) -> tuple[str, str, str]:
        """Stream-download CSV from URL to temp file."""
        async with aiohttp.ClientSession() as session:
            # HEAD to check Last-Modified
            async with session.head(url) as head_resp:
                head_resp.raise_for_status()
                last_modified = head_resp.headers.get("Last-Modified", "")

            stored_modified = cfg.checkpoints.get("source_modified")
            if not force and last_modified and last_modified == stored_modified:
                logger.info("[candidatures] Last-Modified unchanged (%s), skipping", last_modified)
                return "", "", last_modified  # empty path signals skip

            logger.info("[candidatures] downloading %s", url)
            with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
                tmp_path = tmp.name
                first_bytes = b""
                total_size = 0
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.content.iter_chunked(1024 * 64):
                        if total_size < 10240:
                            first_bytes += chunk
                        total_size += len(chunk)
                        tmp.write(chunk)

        hash_input = first_bytes[:10240] + str(total_size).encode()
        return tmp_path, content_hash(hash_input), last_modified

    def _copy_local_csv(self, path: str, cfg: NodeConfig) -> tuple[str, str, str]:
        """Copy a local CSV to a temp file for uniform processing."""
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Candidatures CSV not found at {path}")

        logger.info("[candidatures] loading local file %s", path)
        with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
            tmp_path = tmp.name
            shutil.copyfile(src, tmp_path)

        # Read first 10KB for hash
        with open(tmp_path, "rb") as f:
            first_bytes = f.read(10240)
        file_size = src.stat().st_size
        hash_input = first_bytes + str(file_size).encode()
        last_modified = str(src.stat().st_mtime)

        return tmp_path, content_hash(hash_input), last_modified

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        global _cached_communes

        source = os.environ.get("DATA_GOUV_CANDIDATURES_URL", DEFAULT_CSV_URL)

        # ------------------------------------------------------------------
        # 0. Validate population node has run (needed for seed node later)
        # ------------------------------------------------------------------
        all_communes = get_all_communes()
        if all_communes is None:
            raise RuntimeError(
                "Population node must run first — no cached commune data available"
            )
        # Parse ALL communes from the CSV, not just top N.
        # The top_communes filter only applies to scraping, not candidatures.
        all_commune_codes = set(all_communes.keys())

        # ------------------------------------------------------------------
        # 1. Load CSV (remote or local)
        # ------------------------------------------------------------------
        tmp_path, source_hash, last_modified = await self._load_csv(source, force, cfg)

        if not tmp_path:
            if _cached_communes is None:
                # Cache is empty (server restart) — force re-download
                tmp_path, source_hash, last_modified = await self._load_csv(source, True, cfg)
            else:
                # Last-Modified unchanged and cache populated → skip
                return cfg

        # ------------------------------------------------------------------
        # 2. Content-hash check
        # ------------------------------------------------------------------
        stored_hash = cfg.checkpoints.get("source_hash")
        if not force and should_skip(source_hash, stored_hash) and _cached_communes is not None:
            logger.info("[candidatures] content hash unchanged (%s), skipping", source_hash)
            os.unlink(tmp_path)
            return cfg

        # ------------------------------------------------------------------
        # 3. Parse the CSV
        # ------------------------------------------------------------------
        communes: dict[str, dict] = {}
        total_rows = 0
        total_candidates = 0

        try:
            with open(tmp_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    total_rows += 1
                    commune_code = row["Code circonscription"]
                    if commune_code not in all_commune_codes:
                        continue

                    commune_name = row["Circonscription"]
                    panneau = row.get("Numéro de panneau", "").strip()
                    if not panneau:
                        continue

                    if commune_code not in communes:
                        communes[commune_code] = {
                            "commune_code": commune_code,
                            "commune_name": commune_name,
                            "lists": {},
                        }

                    commune = communes[commune_code]
                    if panneau not in commune["lists"]:
                        commune["lists"][panneau] = {
                            "panneau": int(panneau),
                            "list_label": row["Libellé de la liste"],
                            "list_short_label": row["Libellé abrégé de liste"],
                            "nuance_code": row.get("Code nuance de liste", ""),
                            "nuance_label": row.get("Nuance de liste", ""),
                            "head_first_name": None,
                            "head_last_name": None,
                            "candidates": [],
                        }

                    lst = commune["lists"][panneau]
                    candidate = {
                        "ordre": int(row["Ordre"]) if row.get("Ordre", "").strip() else 0,
                        "sexe": row["Sexe"],
                        "nom": row["Nom sur le bulletin de vote"],
                        "prenom": row["Prénom sur le bulletin de vote"],
                        "nationalite": row.get("Nationalité", ""),
                        "tete_de_liste": row.get("Tête de liste") == "OUI",
                    }
                    lst["candidates"].append(candidate)
                    total_candidates += 1

                    if candidate["tete_de_liste"]:
                        lst["head_first_name"] = candidate["prenom"]
                        lst["head_last_name"] = candidate["nom"]
        finally:
            os.unlink(tmp_path)

        _cached_communes = communes

        # ------------------------------------------------------------------
        # 4. Compute counts
        # ------------------------------------------------------------------
        total_lists = sum(len(c["lists"]) for c in communes.values())

        cfg.counts = {
            "total_rows": total_rows,
            "matched_communes": len(communes),
            "total_lists": total_lists,
            "total_candidates": total_candidates,
        }

        # ------------------------------------------------------------------
        # 5. Update checkpoints
        # ------------------------------------------------------------------
        cfg.checkpoints["source_hash"] = source_hash
        cfg.checkpoints["source_modified"] = last_modified
        await save_checkpoint(cfg.node_id, cfg.checkpoints)

        logger.info(
            "[candidatures] parsed %d rows → %d communes, %d lists, %d candidates",
            total_rows,
            len(communes),
            total_lists,
            total_candidates,
        )

        return cfg


register_node(CandidaturesNode())
