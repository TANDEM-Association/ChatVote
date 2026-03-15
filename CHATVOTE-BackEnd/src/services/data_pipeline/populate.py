"""Pipeline node: merge population + candidatures + websites into Firestore (populate).

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
import base64
import hashlib
import json
import logging
import os
import re
import time as _time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

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
from src.services.data_pipeline.pourquituvotes import get_pourquituvotes_urls
from src.services.data_pipeline.professions import get_professions
from src.services.data_pipeline.websites import get_websites

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
SEED_DIR = REPO_ROOT / "firebase" / "firestore_data" / "dev"

SHEETS_API_URL = "https://sheets.googleapis.com/v4/spreadsheets"
APP_TRUTH_SHEET_ID = os.environ.get(
    "APP_TRUTH_SHEET_ID",
    "15Mge7CUwsFMn5h7SVRYoo5V1SyDE2vU5h4F9OnDHWB8",
)
APP_TRUTH_TAB = "app_truth"

# Columns for the app_truth tab
APP_TRUTH_HEADERS = [
    "candidate_id",
    "first_name",
    "last_name",
    "commune_code",
    "commune_name",
    "population",
    "population_rank",
    "party_ids",
    "nuance_code",
    "nuance_label",
    "list_label",
    "panel_number",
    "election_type_id",
    "position",
    "is_incumbent",
    "website_url",
    "website_source",
    "manifesto_pdf_url",
]

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
    pqtv_urls: dict[tuple[str, str], str] | None = None,
) -> int:
    """Add website URLs to candidates with source attribution. Returns count linked."""
    linked = 0
    pqtv = pqtv_urls or {}
    for cand in candidates.values():
        code = cand["commune_code"]
        ln = _norm(cand["last_name"])
        fn = _norm(cand["first_name"])

        sheet_url = websites.get((code, fn + ln)) or websites.get((code, ln))
        pqtv_url = pqtv.get((code, fn + ln)) or pqtv.get((code, ln))

        url = sheet_url or pqtv_url
        if url:
            cand["website_url"] = url
            # Track source(s)
            sources = []
            if sheet_url:
                sources.append("custom-sheet")
            if pqtv_url:
                sources.append("pourquituvotes")
            cand["website_source"] = ",".join(sources)
            linked += 1
        else:
            cand["website_url"] = ""
            cand["website_source"] = ""
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
            cand["manifesto_pdf_url"] = match.get("pdf_url", "")
            linked += 1
            logger.debug("[seed] linked manifesto for %s-%s: %s", code, panneau, cand["manifesto_pdf_url"])
        # Don't set manifesto_pdf_url="" here — with merge=True that would
        # overwrite a URL previously written by the professions node.
    return linked


# ---------------------------------------------------------------------------
# Firestore parallel batch write
# ---------------------------------------------------------------------------
_BATCH_SIZE = 450  # Firestore limit is 500; leave margin
_CONCURRENCY = 5   # Max parallel batch commits


def _get_sheets_credentials():
    """Build Google SA credentials with Sheets write scope."""
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials

    b64 = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_BASE64", "")
    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    if b64:
        raw = base64.b64decode(b64).decode()
    elif not raw:
        return None  # no credentials available — skip sheet sync
    raw = raw.strip().strip("'\"")
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    creds.refresh(Request())
    return creds


async def _sync_candidates_to_sheet(
    candidates: dict[str, Any],
    municipalities: dict[str, Any] | None = None,
) -> int:
    """Write all candidates to the app_truth tab in Google Sheets.

    Clears existing data then writes header + all rows in one batch.
    Returns the number of rows written.
    """
    _t_creds = _time.monotonic()
    creds = _get_sheets_credentials()
    if creds is None:
        logger.info("[seed] no Google Sheets credentials — skipping app_truth sync")
        return 0
    logger.info("[seed:timing] sheet_creds took %.2fs", _time.monotonic() - _t_creds)

    # Build population lookup and rank
    pop_lookup: dict[str, int] = {}
    if municipalities:
        for code, m in municipalities.items():
            pop_lookup[code] = m.get("population", 0)

    # Compute population rank per commune (1 = biggest)
    commune_pops = sorted(set(pop_lookup.values()), reverse=True)
    pop_rank_map = {pop: rank + 1 for rank, pop in enumerate(commune_pops)}

    # Build rows sorted by candidate_id for stable ordering
    _t_rows = _time.monotonic()
    rows = [APP_TRUTH_HEADERS]
    for cid in sorted(candidates.keys()):
        c = candidates[cid]
        commune_code = c.get("commune_code", "")
        population = pop_lookup.get(commune_code, 0)
        rank = pop_rank_map.get(population, "")
        rows.append([
            c.get("candidate_id", ""),
            c.get("first_name", ""),
            c.get("last_name", ""),
            commune_code,
            c.get("commune_name", ""),
            population,
            rank,
            ",".join(c.get("party_ids", [])),
            c.get("nuance_code", ""),
            c.get("nuance_label", ""),
            c.get("list_label", ""),
            c.get("panel_number", ""),
            c.get("election_type_id", ""),
            c.get("position", ""),
            str(c.get("is_incumbent", False)),
            c.get("website_url", ""),
            c.get("website_source", ""),
            c.get("manifesto_pdf_url", ""),
        ])
    logger.info("[seed:timing] sheet_row_build took %.2fs, %d rows", _time.monotonic() - _t_rows, len(rows) - 1)

    token = creds.token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        # 1. Clear the tab
        clear_url = (
            f"{SHEETS_API_URL}/{APP_TRUTH_SHEET_ID}/values/"
            f"{APP_TRUTH_TAB}!A:T:clear"
        )
        _t_clear = _time.monotonic()
        async with session.post(clear_url, headers=headers, json={}) as resp:
            resp.raise_for_status()
        logger.info("[seed:timing] sheet_clear took %.2fs", _time.monotonic() - _t_clear)

        # 2. Write all rows in one update
        update_url = (
            f"{SHEETS_API_URL}/{APP_TRUTH_SHEET_ID}/values/"
            f"{APP_TRUTH_TAB}!A1?valueInputOption=RAW"
        )
        body = {"values": rows}
        _t_write_sheet = _time.monotonic()
        async with session.put(update_url, headers=headers, json=body) as resp:
            resp.raise_for_status()
            data = await resp.json()
        logger.info("[seed:timing] sheet_write took %.2fs", _time.monotonic() - _t_write_sheet)

    written = data.get("updatedRows", 0)
    logger.info(
        "[seed] synced %d candidates to app_truth sheet (%d rows incl header)",
        len(candidates), written,
    )
    return written


async def _write_collection(
    collection_name: str,
    docs: dict[str, Any],
    node_id: str,
) -> int:
    """Write all docs to Firestore using parallel batch commits.

    Returns the total number of documents written.
    """
    from src.firebase_service import async_db

    _t_wc = _time.monotonic()
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
                batch.set(ref, data, merge=True)
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

    logger.info("[seed:timing] _write_collection(%s) total took %.2fs, %d docs", collection_name, _time.monotonic() - _t_wc, written)
    return written


# ---------------------------------------------------------------------------
# Node implementation
# ---------------------------------------------------------------------------
class PopulateNode(DataSourceNode):
    node_id = "populate"
    label = "Populate / Merge"

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        # ------------------------------------------------------------------
        # 0. Validate upstream nodes have run
        # ------------------------------------------------------------------
        _t_validation = _time.monotonic()
        all_communes = get_all_communes()
        if all_communes is None:
            raise RuntimeError(
                "Population node must run before populate node"
                "(get_all_communes() returned None)"
            )

        top_communes = get_top_communes()
        if top_communes is None:
            raise RuntimeError(
                "Population node must run before populate node"
                "(get_top_communes() returned None)"
            )

        candidatures = get_candidatures()
        if candidatures is None:
            raise RuntimeError(
                "Candidatures node must run before populate node"
                "(get_candidatures() returned None)"
            )

        websites = get_websites()  # May be None — that's OK
        logger.info("[seed:timing] upstream_validation took %.2fs", _time.monotonic() - _t_validation)

        # ------------------------------------------------------------------
        # 1. Build the three collections (scoped to top communes only)
        # ------------------------------------------------------------------
        top_commune_codes = set(top_communes.keys())
        filtered_candidatures = {
            code: data for code, data in candidatures.items()
            if code in top_commune_codes
        }
        logger.info(
            "[seed] filtered candidatures: %d/%d communes (top %d)",
            len(filtered_candidatures), len(candidatures), len(top_commune_codes),
        )

        _t_el = _time.monotonic()
        electoral_lists = _build_electoral_lists(filtered_candidatures)
        logger.info("[seed:timing] build_electoral_lists took %.2fs, %d lists", _time.monotonic() - _t_el, len(electoral_lists))
        electoral_commune_codes = set(electoral_lists.keys())
        _t_mun = _time.monotonic()
        municipalities = _build_municipalities(all_communes, electoral_commune_codes)
        logger.info("[seed:timing] build_municipalities took %.2fs, %d docs", _time.monotonic() - _t_mun, len(municipalities))
        _t_cand = _time.monotonic()
        candidates = _build_candidates(filtered_candidatures)
        logger.info("[seed:timing] build_candidates took %.2fs, %d docs", _time.monotonic() - _t_cand, len(candidates))

        # ------------------------------------------------------------------
        # 2. Enrich candidates with website URLs (with source tracking)
        # ------------------------------------------------------------------
        pqtv_urls = get_pourquituvotes_urls()  # May be None
        websites_linked = 0
        if websites:
            _t_enrich_web = _time.monotonic()
            websites_linked = _enrich_candidates_with_websites(
                candidates, websites, pqtv_urls=pqtv_urls,
            )
            logger.info("[seed:timing] enrich_websites took %.2fs, %d linked", _time.monotonic() - _t_enrich_web, websites_linked)
            logger.info("[seed] enriched %d candidates with website URLs", websites_linked)

        # ------------------------------------------------------------------
        # 2b. Enrich candidates with professions de foi
        # ------------------------------------------------------------------
        professions = get_professions()
        professions_linked = 0
        if professions:
            _t_enrich_prof = _time.monotonic()
            professions_linked = _enrich_candidates_with_professions(candidates, professions)
            logger.info("[seed:timing] enrich_professions took %.2fs, %d linked", _time.monotonic() - _t_enrich_prof, professions_linked)
            logger.info("[seed] enriched %d candidates with profession de foi", professions_linked)

        with_manifesto = sum(1 for c in candidates.values() if c.get("manifesto_pdf_url"))

        # ------------------------------------------------------------------
        # 3. Check collection-level hashes — skip entirely if unchanged
        #    NOTE: We only store collection-level hashes in the checkpoint,
        #    NOT per-doc hashes.  Storing 120k per-doc hashes would exceed
        #    Firestore's 1 MB document-size limit on the config doc.
        # ------------------------------------------------------------------
        _t_hash = _time.monotonic()
        mun_hash = _collection_hash(municipalities)
        el_hash = _collection_hash(electoral_lists)
        cand_hash = _collection_hash(candidates)
        logger.info("[seed:timing] hash_computation took %.2fs", _time.monotonic() - _t_hash)

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
            _t_write = _time.monotonic()
            written = await _write_collection(coll_name, docs, cfg.node_id)
            total_written += written
            logger.info("[seed:timing] write_%s took %.2fs, %d docs", coll_name, _time.monotonic() - _t_write, written)
            logger.info("[seed] %s: %d docs written", coll_name, written)

        # ------------------------------------------------------------------
        # 5. Write JSON fixtures for local dev
        # ------------------------------------------------------------------
        SEED_DIR.mkdir(parents=True, exist_ok=True)

        _t_json = _time.monotonic()
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
        logger.info("[seed:timing] json_fixtures took %.2fs", _time.monotonic() - _t_json)

        # ------------------------------------------------------------------
        # 5b. Sync candidates to app_truth Google Sheet
        # ------------------------------------------------------------------
        sheet_rows = 0
        try:
            _t_sheet = _time.monotonic()
            sheet_rows = await _sync_candidates_to_sheet(candidates, municipalities)
            logger.info("[seed:timing] sheet_sync took %.2fs, %d rows", _time.monotonic() - _t_sheet, sheet_rows)
        except Exception as exc:
            logger.warning("[seed] app_truth sheet sync failed: %s", exc)

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
        cfg.checkpoints["cached_at"] = datetime.now(timezone.utc).isoformat()
        await save_checkpoint(cfg.node_id, cfg.checkpoints)

        cfg.counts = {
            "municipalities": len(municipalities),
            "electoral_lists": len(electoral_lists),
            "candidates": len(candidates),
            "with_website": websites_linked,
            "with_manifesto": with_manifesto,
            "docs_written": total_written,
            "sheet_rows": sheet_rows,
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


register_node(PopulateNode())
