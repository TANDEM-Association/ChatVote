#!/usr/bin/env python3
"""Ingest 2nd-round municipales 2026 candidatures CSV into Firestore.

Downloads the 2nd-tour candidatures CSV from data.gouv.fr, matches lists to
existing Firestore candidates, and enriches them with `is_second_round: True`
plus second-round metadata. Also writes `lists_round_2` arrays to
`electoral_lists/{commune_code}` docs and sets `system_status/election_config`.

Usage:
    cd CHATVOTE-BackEnd
    poetry run python scripts/ingest_second_tour_candidatures.py
    poetry run python scripts/ingest_second_tour_candidatures.py --dry-run
    poetry run python scripts/ingest_second_tour_candidatures.py --deactivate
"""

import argparse
import csv
import io
import logging
import os
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

# Add project root to path so we can import from src
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Load .env before importing src modules
from dotenv import load_dotenv  # noqa: E402
_env_path = PROJECT_ROOT / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)

import requests  # noqa: E402

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SECOND_TOUR_CSV_URL = (
    "https://www.data.gouv.fr/api/1/datasets/r/c7e8ced6-3d08-452e-af06-d553634b6d61"
)

SECOND_ROUND_DATE = "2026-03-22"
FIRST_ROUND_DATE = "2026-03-15"

# Firestore batch size limit
BATCH_LIMIT = 400

# ---------------------------------------------------------------------------
# Nuance → party_ids mapping (from fetch_second_turn_candidates.py)
# ---------------------------------------------------------------------------
NUANCE_TO_PARTY = {
    "LRN": "rn",
    "LUXD": "rn",           # Union extrême droite often RN-led
    "LFI": "lfi",
    "LEXG": "extreme_gauche",
    "LUG": "union_gauche",
    "LDVG": "divers_gauche",
    "LUD": "union_droite",
    "LDVD": "divers_droite",
    "LREC": "reconquete",
    "LDIV": "divers",
    "LECO": "ecologiste",
    "LSOC": "socialiste",
    "LCOM": "communiste",
    "LLR": "lr",
    "LENS": "ensemble",
    "LHOR": "horizons",
    "LREM": "ensemble",
    "LMDM": "modem",
}


# ---------------------------------------------------------------------------
# Normalisation helpers (from fetch_second_turn_candidates.py)
# ---------------------------------------------------------------------------
def _normalize(s: str) -> str:
    """Strip accents, uppercase, collapse whitespace/hyphens."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.upper().strip().replace("-", " ").replace("  ", " ")


def _levenshtein(a: str, b: str) -> int:
    """Compute Levenshtein distance between two strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(
                prev[j + 1] + 1,
                curr[j] + 1,
                prev[j] + (ca != cb),
            ))
        prev = curr
    return prev[-1]


# ---------------------------------------------------------------------------
# CSV download and parse
# ---------------------------------------------------------------------------
def download_csv(url: str) -> str:
    """Download CSV from URL and return as decoded string."""
    logger.info("Downloading 2nd-tour candidatures CSV from %s …", url)
    resp = requests.get(url, timeout=120, allow_redirects=True)
    resp.raise_for_status()
    content = resp.content
    # Try UTF-8 with BOM, then latin-1
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV with any known encoding")


def parse_csv(text: str) -> dict[str, dict]:
    """Parse the 2nd-tour candidatures CSV.

    Returns:
        communes: {commune_code: {
            commune_code, commune_name,
            lists: {panneau: {panel_number, list_label, list_short_label,
                               nuance_code, nuance_label,
                               head_first_name, head_last_name}}
        }}
    """
    communes: dict[str, dict] = {}
    total_rows = 0
    skipped = 0

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    for row in reader:
        total_rows += 1
        commune_code = row.get("Code circonscription", "").strip()
        if not commune_code:
            skipped += 1
            continue

        commune_name = row.get("Circonscription", "").strip()
        panneau = row.get("Numéro de panneau", "").strip()
        if not panneau:
            skipped += 1
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
                "panel_number": int(panneau) if panneau.isdigit() else 0,
                "list_label": row.get("Libellé de la liste", "").strip(),
                "list_short_label": row.get("Libellé abrégé de liste", "").strip(),
                "nuance_code": row.get("Code nuance de liste", "").strip(),
                "nuance_label": row.get("Nuance de liste", "").strip(),
                "head_first_name": None,
                "head_last_name": None,
            }

        lst = commune["lists"][panneau]
        tete_de_liste = row.get("Tête de liste", "").strip() == "OUI"
        if tete_de_liste:
            lst["head_first_name"] = row.get("Prénom sur le bulletin de vote", "").strip()
            lst["head_last_name"] = row.get("Nom sur le bulletin de vote", "").strip()

    logger.info(
        "CSV parsed: %d rows → %d communes, %d skipped rows",
        total_rows, len(communes), skipped,
    )
    return communes


# ---------------------------------------------------------------------------
# Firestore candidate lookup
# ---------------------------------------------------------------------------
def fetch_candidates_by_municipality(db) -> dict[str, list[dict]]:
    """Fetch all candidates from Firestore, grouped by municipality_code.

    Returns:
        {municipality_code: [{id, party_ids, nuance_code, first_name, last_name}]}
    """
    logger.info("Fetching all candidates from Firestore …")
    by_municipality: dict[str, list[dict]] = defaultdict(list)
    count = 0

    docs = db.collection("candidates").stream()
    for doc in docs:
        data = doc.to_dict()
        muni_code = data.get("municipality_code", "")
        if not muni_code:
            continue
        by_municipality[muni_code].append({
            "id": doc.id,
            "party_ids": data.get("party_ids", []),
            "nuance_code": data.get("nuance_code", ""),
            "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""),
        })
        count += 1

    logger.info("Fetched %d candidates across %d municipalities", count, len(by_municipality))
    return dict(by_municipality)


# ---------------------------------------------------------------------------
# Matching: list → Firestore candidates
# ---------------------------------------------------------------------------
def _match_list_to_candidates(
    commune_code: str,
    nuance_code: str,
    list_label: str,
    head_last_name: str | None,
    by_municipality: dict[str, list[dict]],
) -> list[str]:
    """Return candidate IDs from Firestore that match this 2nd-round list.

    Matching strategy (in priority order):
    1. nuance_code exact match on candidate's nuance_code field
    2. nuance_code → NUANCE_TO_PARTY → candidate's party_ids
    3. Head-of-list last name appears in list_label
    4. Levenshtein fuzzy match on head last name vs candidate last name (threshold 2)
    """
    candidates_in_commune = by_municipality.get(commune_code, [])
    if not candidates_in_commune:
        return []

    matched_ids: list[str] = []
    norm_nuance = nuance_code.strip('"').strip()
    party_hint = NUANCE_TO_PARTY.get(norm_nuance, "")
    norm_list = _normalize(list_label)
    norm_head = _normalize(head_last_name) if head_last_name else ""

    for cand in candidates_in_commune:
        cid = cand["id"]
        cand_nuance = cand.get("nuance_code", "")
        party_ids = cand.get("party_ids", [])
        norm_last = _normalize(cand.get("last_name", ""))

        # Strategy 1: nuance code exact match
        if cand_nuance and cand_nuance == norm_nuance:
            matched_ids.append(cid)
            continue

        # Strategy 2: party_ids match via NUANCE_TO_PARTY mapping
        if party_hint and isinstance(party_ids, list) and party_hint in party_ids:
            matched_ids.append(cid)
            continue
        if party_hint and isinstance(party_ids, str) and party_hint in party_ids:
            matched_ids.append(cid)
            continue

        # Strategy 3: candidate last name appears in list label
        if len(norm_last) > 2 and norm_last in norm_list:
            matched_ids.append(cid)
            continue

        # Strategy 4: fuzzy match on head last name vs candidate last name
        if norm_head and len(norm_head) > 2 and len(norm_last) > 2:
            dist = _levenshtein(norm_head, norm_last)
            if dist <= 2:
                matched_ids.append(cid)
                continue

    return matched_ids


# ---------------------------------------------------------------------------
# Main ingestion logic
# ---------------------------------------------------------------------------
def ingest(db, communes_csv: dict[str, dict], by_municipality: dict[str, list[dict]], dry_run: bool) -> None:
    """Enrich Firestore candidates with is_second_round flag and write lists_round_2."""

    # -----------------------------------------------------------------------
    # Step 1: Reset ALL candidates' is_second_round to False (idempotent)
    # -----------------------------------------------------------------------
    logger.info("Step 1: Resetting is_second_round=False on all candidates …")
    all_candidate_ids: list[str] = []
    for candidates in by_municipality.values():
        for cand in candidates:
            all_candidate_ids.append(cand["id"])

    if not dry_run:
        batch = db.batch()
        batch_count = 0
        for cid in all_candidate_ids:
            ref = db.collection("candidates").document(cid)
            batch.update(ref, {"is_second_round": False})
            batch_count += 1
            if batch_count >= BATCH_LIMIT:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()
        logger.info("Reset %d candidates to is_second_round=False", len(all_candidate_ids))
    else:
        logger.info("[DRY-RUN] Would reset %d candidates to is_second_round=False", len(all_candidate_ids))

    # -----------------------------------------------------------------------
    # Step 2: Match CSV lists to Firestore candidates and collect updates
    # -----------------------------------------------------------------------
    logger.info("Step 2: Matching 2nd-tour lists to candidates …")

    # Track stats
    total_csv_communes = len(communes_csv)
    app_tracked_communes = set(by_municipality.keys())
    matched_communes: set[str] = set()
    candidates_to_update: dict[str, dict] = {}  # candidate_id → update payload
    electoral_lists_updates: dict[str, list[dict]] = {}  # commune_code → lists_round_2

    for commune_code, commune in communes_csv.items():
        lists = commune["lists"]
        if not lists:
            continue

        # Build lists_round_2 for this commune (all lists in the 2nd-round CSV)
        lists_round_2 = []
        for panneau_str, lst in sorted(lists.items(), key=lambda x: x[1]["panel_number"]):
            lists_round_2.append({
                "panel_number": lst["panel_number"],
                "list_label": lst["list_label"],
                "list_short_label": lst["list_short_label"],
                "nuance_code": lst["nuance_code"],
                "nuance_label": lst["nuance_label"],
                "head_first_name": lst["head_first_name"],
                "head_last_name": lst["head_last_name"],
            })

            # Match to Firestore candidates
            cand_ids = _match_list_to_candidates(
                commune_code,
                lst["nuance_code"],
                lst["list_label"],
                lst["head_last_name"],
                by_municipality,
            )

            for cid in cand_ids:
                candidates_to_update[cid] = {
                    "is_second_round": True,
                    "second_round_nuance_code": lst["nuance_code"],
                    "second_round_list_label": lst["list_label"],
                    "second_round_panel_number": lst["panel_number"],
                }
                matched_communes.add(commune_code)

        electoral_lists_updates[commune_code] = lists_round_2

    # -----------------------------------------------------------------------
    # Step 3: Log match rate stats
    # -----------------------------------------------------------------------
    communes_in_app = len(app_tracked_communes & set(communes_csv.keys()))
    candidates_matched = len(candidates_to_update)
    match_rate = (len(matched_communes) / communes_in_app * 100) if communes_in_app > 0 else 0.0

    logger.info("--- Match Rate Summary ---")
    logger.info("Total communes in 2nd-tour CSV:  %d", total_csv_communes)
    logger.info("Communes tracked by app:         %d", len(app_tracked_communes))
    logger.info("CSV communes matching app:        %d", communes_in_app)
    logger.info("Communes with ≥1 match:           %d", len(matched_communes))
    logger.info("Candidates matched:              %d", candidates_matched)
    logger.info("Match rate (of app communes):    %.1f%%", match_rate)

    if match_rate < 50.0 and communes_in_app > 0:
        logger.error(
            "Match rate %.1f%% is below 50%% threshold — manual review recommended! "
            "Check NUANCE_TO_PARTY mapping and Firestore candidate nuance_code fields.",
            match_rate,
        )

    # -----------------------------------------------------------------------
    # Step 4: Write candidate updates to Firestore
    # -----------------------------------------------------------------------
    logger.info("Step 3: Writing %d candidate updates …", candidates_matched)
    if not dry_run:
        batch = db.batch()
        batch_count = 0
        for cid, update_data in candidates_to_update.items():
            ref = db.collection("candidates").document(cid)
            batch.update(ref, update_data)
            batch_count += 1
            if batch_count >= BATCH_LIMIT:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()
        logger.info("Wrote is_second_round=True for %d candidates", candidates_matched)
    else:
        logger.info("[DRY-RUN] Would write is_second_round=True for %d candidates", candidates_matched)
        for cid, data in list(candidates_to_update.items())[:5]:
            logger.info("  [DRY-RUN] candidate %s → %s", cid, data)
        if candidates_matched > 5:
            logger.info("  [DRY-RUN] … and %d more", candidates_matched - 5)

    # -----------------------------------------------------------------------
    # Step 5: Write lists_round_2 to electoral_lists docs
    # -----------------------------------------------------------------------
    logger.info("Step 4: Writing lists_round_2 to %d electoral_lists docs …", len(electoral_lists_updates))
    if not dry_run:
        batch = db.batch()
        batch_count = 0
        for commune_code, lists_round_2 in electoral_lists_updates.items():
            ref = db.collection("electoral_lists").document(commune_code)
            # Use set(merge=True) to add lists_round_2 without overwriting existing fields,
            # and to create the doc if it doesn't exist yet (e.g. local emulator).
            batch.set(ref, {
                "lists_round_2": lists_round_2,
                "list_count_round_2": len(lists_round_2),
            }, merge=True)
            batch_count += 1
            if batch_count >= BATCH_LIMIT:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()
        logger.info("Wrote lists_round_2 to %d electoral_lists docs", len(electoral_lists_updates))
    else:
        logger.info(
            "[DRY-RUN] Would write lists_round_2 to %d electoral_lists docs",
            len(electoral_lists_updates),
        )

    # -----------------------------------------------------------------------
    # Step 6: Set system_status/election_config
    # -----------------------------------------------------------------------
    logger.info("Step 5: Setting system_status/election_config …")
    config_payload = {
        "is_second_round_active": True,
        "second_round_date": SECOND_ROUND_DATE,
        "first_round_date": FIRST_ROUND_DATE,
    }
    if not dry_run:
        db.collection("system_status").document("election_config").set(config_payload)
        logger.info("Set election_config: %s", config_payload)
    else:
        logger.info("[DRY-RUN] Would set election_config: %s", config_payload)


def deactivate(db, by_municipality: dict[str, list[dict]], dry_run: bool) -> None:
    """Reset all is_second_round flags and set is_second_round_active=False."""
    all_candidate_ids: list[str] = []
    for candidates in by_municipality.values():
        for cand in candidates:
            all_candidate_ids.append(cand["id"])

    logger.info("Deactivating second round: resetting %d candidates …", len(all_candidate_ids))
    if not dry_run:
        batch = db.batch()
        batch_count = 0
        for cid in all_candidate_ids:
            ref = db.collection("candidates").document(cid)
            batch.update(ref, {"is_second_round": False})
            batch_count += 1
            if batch_count >= BATCH_LIMIT:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()
        logger.info("Reset %d candidates to is_second_round=False", len(all_candidate_ids))
    else:
        logger.info("[DRY-RUN] Would reset %d candidates to is_second_round=False", len(all_candidate_ids))

    config_payload = {
        "is_second_round_active": False,
        "second_round_date": SECOND_ROUND_DATE,
        "first_round_date": FIRST_ROUND_DATE,
    }
    if not dry_run:
        db.collection("system_status").document("election_config").set(config_payload)
        logger.info("Set election_config.is_second_round_active=False")
    else:
        logger.info("[DRY-RUN] Would set election_config: %s", config_payload)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest 2nd-tour municipales candidatures into Firestore",
    )
    parser.add_argument(
        "--deactivate",
        action="store_true",
        help="Reset all is_second_round flags and set is_second_round_active=False",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be done without writing to Firestore",
    )
    args = parser.parse_args()

    if args.dry_run:
        logger.info("=== DRY-RUN MODE: no Firestore writes will be made ===")

    # Import db after env is configured (src/firebase_service.py handles init)
    _target_env = os.getenv("ENV")
    from src.utils import load_env  # noqa: E402
    load_env()
    if _target_env:
        os.environ["ENV"] = _target_env

    from src.firebase_service import db  # noqa: E402

    env = os.getenv("ENV", "dev")
    logger.info("Connected to Firestore (ENV=%s)", env)
    if env == "prod" and not args.dry_run:
        logger.warning("WARNING: Writing to PRODUCTION Firestore!")
        response = input("Continue? [y/N] ")
        if response.lower() != "y":
            logger.info("Aborted.")
            sys.exit(0)

    # Fetch all candidates once (needed for both ingest and deactivate)
    by_municipality = fetch_candidates_by_municipality(db)

    if args.deactivate:
        deactivate(db, by_municipality, dry_run=args.dry_run)
        logger.info("Done — second round deactivated.")
        return

    # Download and parse CSV
    csv_text = download_csv(SECOND_TOUR_CSV_URL)
    communes_csv = parse_csv(csv_text)

    # Run ingestion
    ingest(db, communes_csv, by_municipality, dry_run=args.dry_run)

    logger.info("Done.")


if __name__ == "__main__":
    main()
