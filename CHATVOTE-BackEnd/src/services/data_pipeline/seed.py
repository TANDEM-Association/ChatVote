"""Pipeline node: merge population + candidatures + websites into Firestore seed data."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    content_hash,
    register_node,
    save_checkpoint,
    should_skip,
)
from src.services.data_pipeline.candidatures import get_candidatures
from src.services.data_pipeline.population import get_all_communes, get_top_communes
from src.services.data_pipeline.professions import get_professions
from src.services.data_pipeline.websites import get_websites

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
SEED_DIR = REPO_ROOT / "firebase" / "firestore_data" / "dev"

# Map nuance codes from the candidatures CSV to Firestore party_ids.
# These must match the party_id values in parties.json.
NUANCE_TO_PARTY_ID: dict[str, str] = {
    "LDIV": "divers",
    "LDSV": "divers",
    "LDVC": "divers_centre",
    "LDVD": "divers_droite",
    "LDVG": "divers_gauche",
    "LECO": "europe-ecologie-les-verts",
    "LEXD": "extreme_droite",
    "LEXG": "extreme_gauche",
    "LFI": "lfi",
    "LHOR": "divers",
    "LLR": "lr",
    "LREC": "reconquete",
    "LREN": "union_centre",
    "LRN": "rn",
    "LSOC": "ps",
    "LUC": "union_centre",
    "LUD": "union_droite",
    "LUDI": "union_droite",
    "LUG": "union_gauche",
    "LUXD": "extreme_droite",
    "LVEC": "europe-ecologie-les-verts",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    """Normalize a string for fuzzy matching (strip accents, lowercase, alpha only)."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", s.lower())


def _doc_hash(data: dict[str, Any]) -> str:
    """Deterministic SHA-256 of a single document's JSON representation."""
    raw = json.dumps(data, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _collection_hash(docs: dict[str, Any]) -> str:
    """Content hash of an entire collection dict for checkpoint comparison."""
    raw = json.dumps(docs, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return content_hash(raw)


# ---------------------------------------------------------------------------
# Build functions (ported from generate_seed_from_csv.py)
# ---------------------------------------------------------------------------
def _build_municipalities(communes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Build municipalities dict from population data.

    Produces documents matching the frontend ``Municipality`` TypeScript type:
    code, nom, zone, population, surface, codesPostaux, codeRegion,
    codeDepartement, siren, codeEpci, epci, departement, region.
    """
    result: dict[str, Any] = {}
    for code, c in communes.items():
        result[code] = {
            "code": code,
            "nom": c["nom"],
            "population": c["population"],
            "zone": c.get("zone", ""),
            "surface": c.get("surface", 0),
            "codeDepartement": c["dep_code"],
            "departement": {"code": c["dep_code"], "nom": c["dep_nom"]},
            "codeRegion": c["reg_code"],
            "region": {"code": c["reg_code"], "nom": c["reg_nom"]},
            "codesPostaux": c.get("codes_postaux") or ([c["code_postal"]] if c.get("code_postal") else []),
            "siren": c.get("siren", ""),
            "codeEpci": c["epci_code"],
            "epci": {"code": c["epci_code"], "nom": c["epci_nom"]},
        }
    return result


def _build_electoral_lists(communes: dict[str, dict]) -> dict[str, Any]:
    """Build electoral_lists dict from parsed candidatures data."""
    result: dict[str, Any] = {}
    for commune_code, commune in communes.items():
        lists_sorted = sorted(commune["lists"].values(), key=lambda x: x["panneau"])
        lists_clean = []
        for lst in lists_sorted:
            lists_clean.append(
                {
                    "panel_number": lst["panneau"],
                    "list_label": lst["list_label"],
                    "list_short_label": lst["list_short_label"],
                    "nuance_code": lst["nuance_code"],
                    "nuance_label": lst["nuance_label"],
                    "head_first_name": lst["head_first_name"],
                    "head_last_name": lst["head_last_name"],
                }
            )

        result[commune_code] = {
            "commune_code": commune_code,
            "commune_name": commune["commune_name"],
            "list_count": len(lists_clean),
            "lists": lists_clean,
        }
    return result


def _build_candidates(communes: dict[str, dict]) -> dict[str, Any]:
    """Build candidates dict — one entry per tete de liste."""
    result: dict[str, Any] = {}
    for commune_code, commune in communes.items():
        for panneau, lst in commune["lists"].items():
            # Only create candidate entries for tetes de liste
            head = None
            for c in lst["candidates"]:
                if c["tete_de_liste"]:
                    head = c
                    break

            if not head:
                continue

            cand_id = f"cand-{commune_code}-{panneau}"
            nuance_code = lst["nuance_code"]
            party_id = NUANCE_TO_PARTY_ID.get(nuance_code)
            if not party_id:
                logger.warning(
                    "Unknown nuance code %r for %s — defaulting to 'divers'",
                    nuance_code, cand_id,
                )
                party_id = "divers"
            result[cand_id] = {
                "candidate_id": cand_id,
                "first_name": head["prenom"],
                "last_name": head["nom"],
                "commune_code": commune_code,
                "commune_name": commune["commune_name"],
                "municipality_code": commune_code,
                "municipality_name": commune["commune_name"],
                "party_ids": [party_id],
                "list_label": lst["list_label"],
                "nuance_label": lst["nuance_label"],
                "nuance_code": nuance_code,
                "panel_number": lst["panneau"],
                "election_type_id": "municipalities-2026",
                "position": "Tête de liste",
                "is_incumbent": False,
            }
    return result


def _enrich_candidates_with_websites(
    candidates: dict[str, Any],
    websites: dict[tuple[str, str], str],
) -> int:
    """Add website URLs to candidates. Returns count of candidates linked."""
    linked = 0
    for cand in candidates.values():
        code = cand["commune_code"]
        ln = _norm(cand["last_name"])
        fn = _norm(cand["first_name"])
        url = websites.get((code, fn + ln)) or websites.get((code, ln))
        if url:
            cand["has_website"] = True
            cand["website_url"] = url
            linked += 1
        else:
            cand["has_website"] = False
    return linked


def _enrich_candidates_with_professions(
    candidates: dict[str, Any],
    professions: dict[str, list[dict]],
) -> int:
    """Mark candidates that have a profession de foi PDF. Returns count linked.

    The professions dict is keyed by commune_code, each value is a list of
    dicts with at least ``panneau`` and ``pdf_url`` keys.
    """
    linked = 0
    for cand in candidates.values():
        code = cand["commune_code"]
        panneau = str(cand["panel_number"])
        commune_pdfs = professions.get(code, [])
        match = next((p for p in commune_pdfs if str(p.get("panneau")) == panneau), None)
        if match:
            cand["has_manifesto"] = True
            cand["manifesto_pdf_url"] = match.get("pdf_url", "")
            linked += 1
        else:
            cand["has_manifesto"] = False
    return linked


# ---------------------------------------------------------------------------
# Firestore incremental write
# ---------------------------------------------------------------------------
async def _write_collection_incremental(
    collection_name: str,
    docs: dict[str, Any],
    stored_hashes: dict[str, str],
) -> tuple[int, int, dict[str, str]]:
    """Write docs to Firestore, skipping unchanged ones.

    Returns (written_count, skipped_count, new_hashes).
    """
    from src.firebase_service import async_db

    written = 0
    skipped = 0
    new_hashes: dict[str, str] = {}

    # Batch writes — Firestore limits to 500 per batch
    batch = async_db.batch()
    batch_count = 0

    for doc_id, data in docs.items():
        h = _doc_hash(data)
        new_hashes[doc_id] = h

        if h == stored_hashes.get(doc_id):
            skipped += 1
            continue

        ref = async_db.collection(collection_name).document(doc_id)
        batch.set(ref, data)
        written += 1
        batch_count += 1

        if batch_count >= 499:
            await batch.commit()
            batch = async_db.batch()
            batch_count = 0

    if batch_count > 0:
        await batch.commit()

    return written, skipped, new_hashes


# ---------------------------------------------------------------------------
# Node implementation
# ---------------------------------------------------------------------------
class SeedNode(DataSourceNode):
    node_id = "seed"
    label = "Seed / Merge"

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        # ------------------------------------------------------------------
        # 0. Validate upstream nodes have run
        # ------------------------------------------------------------------
        all_communes = get_all_communes()
        if all_communes is None:
            raise RuntimeError(
                "Population node must run before seed node "
                "(get_all_communes() returned None)"
            )

        top_communes = get_top_communes()
        if top_communes is None:
            raise RuntimeError(
                "Population node must run before seed node "
                "(get_top_communes() returned None)"
            )

        candidatures = get_candidatures()
        if candidatures is None:
            raise RuntimeError(
                "Candidatures node must run before seed node "
                "(get_candidatures() returned None)"
            )

        websites = get_websites()  # May be None — that's OK

        # ------------------------------------------------------------------
        # 1. Build the three collections
        # ------------------------------------------------------------------
        # ALL communes go to Firestore municipalities (not just top N)
        municipalities = _build_municipalities(all_communes)
        electoral_lists = _build_electoral_lists(candidatures)
        candidates = _build_candidates(candidatures)

        # ------------------------------------------------------------------
        # 2. Enrich candidates with website URLs
        # ------------------------------------------------------------------
        websites_linked = 0
        if websites:
            websites_linked = _enrich_candidates_with_websites(candidates, websites)
            logger.info("[seed] enriched %d candidates with website URLs", websites_linked)

        # ------------------------------------------------------------------
        # 2b. Enrich candidates with professions de foi
        # ------------------------------------------------------------------
        professions = get_professions()
        professions_linked = 0
        if professions:
            professions_linked = _enrich_candidates_with_professions(candidates, professions)
            logger.info("[seed] enriched %d candidates with profession de foi", professions_linked)

        with_manifesto = sum(1 for c in candidates.values() if c.get("has_manifesto"))

        # ------------------------------------------------------------------
        # 3. Check collection-level hashes — skip entirely if unchanged
        # ------------------------------------------------------------------
        mun_hash = _collection_hash(municipalities)
        el_hash = _collection_hash(electoral_lists)
        cand_hash = _collection_hash(candidates)

        stored_mun_hash = cfg.checkpoints.get("municipalities_hash")
        stored_el_hash = cfg.checkpoints.get("electoral_lists_hash")
        stored_cand_hash = cfg.checkpoints.get("candidates_hash")

        all_unchanged = (
            not force
            and should_skip(mun_hash, stored_mun_hash)
            and should_skip(el_hash, stored_el_hash)
            and should_skip(cand_hash, stored_cand_hash)
        )

        if all_unchanged:
            logger.info("[seed] all collections unchanged, skipping writes")
            cfg.counts = {
                "municipalities": len(municipalities),
                "electoral_lists": len(electoral_lists),
                "candidates": len(candidates),
                "with_website": websites_linked,
                "with_manifesto": with_manifesto,
                "docs_written": 0,
                "docs_skipped": (
                    len(municipalities) + len(electoral_lists) + len(candidates)
                ),
            }
            return cfg

        # ------------------------------------------------------------------
        # 4. Write to Firestore (incremental — per-doc hash comparison)
        # ------------------------------------------------------------------
        total_written = 0
        total_skipped = 0

        collections_to_write: list[tuple[str, dict[str, Any], str]] = [
            ("municipalities", municipalities, "municipalities_hash"),
            ("electoral_lists", electoral_lists, "electoral_lists_hash"),
            ("candidates", candidates, "candidates_hash"),
        ]

        for coll_name, docs, hash_key in collections_to_write:
            stored_doc_hashes: dict[str, str] = cfg.checkpoints.get(
                f"{coll_name}_doc_hashes", {}
            )

            written, skipped, new_doc_hashes = await _write_collection_incremental(
                coll_name, docs, stored_doc_hashes
            )

            total_written += written
            total_skipped += skipped

            cfg.checkpoints[f"{coll_name}_doc_hashes"] = new_doc_hashes

            logger.info(
                "[seed] %s: %d written, %d skipped",
                coll_name,
                written,
                skipped,
            )

        # ------------------------------------------------------------------
        # 5. Write JSON fixtures for local dev
        # ------------------------------------------------------------------
        SEED_DIR.mkdir(parents=True, exist_ok=True)

        for filename, data in [
            ("municipalities.json", municipalities),
            ("electoral_lists.json", electoral_lists),
            ("candidates.json", candidates),
        ]:
            filepath = SEED_DIR / filename
            filepath.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            logger.info("[seed] wrote %s (%d entries)", filepath.name, len(data))

        # ------------------------------------------------------------------
        # 6. Update checkpoints and counts
        # ------------------------------------------------------------------
        cfg.checkpoints["municipalities_hash"] = mun_hash
        cfg.checkpoints["electoral_lists_hash"] = el_hash
        cfg.checkpoints["candidates_hash"] = cand_hash
        cfg.checkpoints["municipalities_count"] = len(municipalities)
        cfg.checkpoints["electoral_lists_count"] = len(electoral_lists)
        cfg.checkpoints["candidates_count"] = len(candidates)
        await save_checkpoint(cfg.node_id, cfg.checkpoints)

        cfg.counts = {
            "municipalities": len(municipalities),
            "electoral_lists": len(electoral_lists),
            "candidates": len(candidates),
            "with_website": websites_linked,
            "with_manifesto": with_manifesto,
            "docs_written": total_written,
            "docs_skipped": total_skipped,
        }

        logger.info(
            "[seed] done — %d municipalities, %d electoral_lists, %d candidates "
            "(%d with website, %d with manifesto) | %d written, %d skipped",
            len(municipalities),
            len(electoral_lists),
            len(candidates),
            websites_linked,
            with_manifesto,
            total_written,
            total_skipped,
        )

        return cfg


register_node(SeedNode())
