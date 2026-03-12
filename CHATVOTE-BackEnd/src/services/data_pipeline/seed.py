"""Pipeline node: merge population + candidatures + websites into Firestore seed data.

This node builds three Firestore collections from upstream pipeline data:
- ``municipalities`` (~35k docs — ALL French communes)
- ``electoral_lists`` (~35k docs — one per commune with candidatures)
- ``candidates`` (~50k docs — one per tête de liste)

**When does it actually write?**
Each collection is fingerprinted with a SHA-256 hash.  If the hash matches
the one stored in the checkpoint, the entire collection is skipped.  Writes
only happen when upstream data (population, candidatures, websites) changes.

**Why not per-doc hashing?**
Storing 120k per-doc hashes in the checkpoint would exceed Firestore's 1 MB
document-size limit and was the root cause of seed timeouts on Scaleway.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time as _time
import unicodedata
from pathlib import Path
from typing import Any

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    NodeStatus,
    content_hash,
    register_node,
    save_checkpoint,
    should_skip,
    update_status,
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
def _build_municipalities(communes: dict[str, dict[str, Any]], electoral_commune_codes: set[str] | None = None) -> dict[str, Any]:
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
            "has_electoral_data": code in electoral_commune_codes if electoral_commune_codes else False,
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
# Firestore parallel batch write
# ---------------------------------------------------------------------------
_BATCH_SIZE = 450  # Firestore limit is 500; leave margin
_CONCURRENCY = 5   # Max parallel batch commits


async def _write_collection(
    collection_name: str,
    docs: dict[str, Any],
    node_id: str,
) -> int:
    """Write all docs to Firestore using parallel batch commits.

    Returns the total number of documents written.
    """
    from src.firebase_service import async_db

    items = list(docs.items())
    total = len(items)
    if total == 0:
        return 0

    # Split into chunks of _BATCH_SIZE
    chunks: list[list[tuple[str, Any]]] = []
    for i in range(0, total, _BATCH_SIZE):
        chunks.append(items[i : i + _BATCH_SIZE])

    written = 0
    t0 = _time.monotonic()
    sem = asyncio.Semaphore(_CONCURRENCY)

    async def _commit_chunk(chunk: list[tuple[str, Any]]) -> int:
        async with sem:
            batch = async_db.batch()
            for doc_id, data in chunk:
                ref = async_db.collection(collection_name).document(doc_id)
                batch.set(ref, data)
            await batch.commit()
            return len(chunk)

    # Fire all batch commits with bounded concurrency
    tasks = [_commit_chunk(chunk) for chunk in chunks]
    for i, coro in enumerate(asyncio.as_completed(tasks)):
        count = await coro
        written += count
        # Log progress every 10 batches
        if (i + 1) % 10 == 0 or written == total:
            elapsed = _time.monotonic() - t0
            rate = written / elapsed if elapsed > 0 else 0
            logger.info(
                "[seed] %s: %d/%d docs written (%.0f docs/s, %.1fs)",
                collection_name, written, total, rate, elapsed,
            )

    # Status update so Scaleway knows we're alive
    await update_status(
        node_id, NodeStatus.RUNNING,
        counts={"phase": collection_name, "written": written, "total": total},
    )

    return written


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
        electoral_lists = _build_electoral_lists(candidatures)
        electoral_commune_codes = set(electoral_lists.keys())
        municipalities = _build_municipalities(all_communes, electoral_commune_codes)
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
        #    NOTE: We only store collection-level hashes in the checkpoint,
        #    NOT per-doc hashes.  Storing 120k per-doc hashes would exceed
        #    Firestore's 1 MB document-size limit on the config doc.
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
        # 4. Write to Firestore (parallel batch commits per collection)
        #    Only collections whose hash changed get rewritten.
        # ------------------------------------------------------------------
        total_written = 0

        collections_to_write: list[tuple[str, dict[str, Any], str, str, str | None]] = [
            ("municipalities", municipalities, mun_hash, "municipalities_hash", stored_mun_hash),
            ("electoral_lists", electoral_lists, el_hash, "electoral_lists_hash", stored_el_hash),
            ("candidates", candidates, cand_hash, "candidates_hash", stored_cand_hash),
        ]

        for coll_name, docs, new_hash, hash_key, old_hash in collections_to_write:
            if not force and should_skip(new_hash, old_hash):
                logger.info("[seed] %s: hash unchanged, skipping (%d docs)", coll_name, len(docs))
                continue

            logger.info("[seed] %s: hash changed, writing %d docs...", coll_name, len(docs))
            written = await _write_collection(coll_name, docs, cfg.node_id)
            total_written += written
            logger.info("[seed] %s: %d docs written", coll_name, written)

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
        #    IMPORTANT: Only store collection-level hashes and counts here.
        #    Do NOT store per-doc hashes — that would exceed Firestore's
        #    1 MB document limit with 120k+ entries.
        # ------------------------------------------------------------------
        # Clean up legacy per-doc hashes if present (from older versions)
        for legacy_key in [
            "municipalities_doc_hashes",
            "electoral_lists_doc_hashes",
            "candidates_doc_hashes",
        ]:
            cfg.checkpoints.pop(legacy_key, None)

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
        }

        logger.info(
            "[seed] done — %d municipalities, %d electoral_lists, %d candidates "
            "(%d with website, %d with manifesto) | %d written",
            len(municipalities),
            len(electoral_lists),
            len(candidates),
            websites_linked,
            with_manifesto,
            total_written,
        )

        return cfg


register_node(SeedNode())
