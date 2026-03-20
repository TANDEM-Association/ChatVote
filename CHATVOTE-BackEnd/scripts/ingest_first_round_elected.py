#!/usr/bin/env python3
"""Ingest 1st-round municipales 2026 election winners into Firestore.

Downloads the 1st-round results CSV from data.gouv.fr, identifies communes
where a list was elected in the first round (>50% of expressed votes, or only
1 list ran), and writes:
  - `first_round_elected` object + `is_first_round_decided: True` to
    `electoral_lists/{commune_code}` docs
  - `is_first_round_elected: True` to matched Firestore candidates

Usage:
    cd CHATVOTE-BackEnd
    poetry run python scripts/ingest_first_round_elected.py
    poetry run python scripts/ingest_first_round_elected.py --dry-run
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
FIRST_ROUND_CSV_URL = (
    "https://www.data.gouv.fr/api/1/datasets/r/4feeef01-24f7-4d5a-914f-8aa806f31ec2"
)

META_COLS = 18        # Fixed columns before repeating list groups
CAND_GROUP_SIZE = 13  # Columns per list/candidate group

# Firestore batch size limit
BATCH_LIMIT = 400

# ---------------------------------------------------------------------------
# Nuance → party_ids mapping (mirrors ingest_second_tour_candidatures.py)
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
# Normalisation helpers (mirrors ingest_second_tour_candidatures.py)
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


def _parse_pct(s: str) -> float:
    """Parse '43,52%' -> 43.52"""
    s = s.strip().strip('"').replace("%", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# CSV download and parse
# ---------------------------------------------------------------------------
def download_csv(url: str) -> str:
    """Download CSV from URL with 120s timeout and return as decoded string."""
    logger.info("Downloading 1st-round results CSV from %s …", url)
    try:
        resp = requests.get(url, timeout=120, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        logger.error(
            "Request timed out after 120s. The data.gouv.fr server may be slow — "
            "try again later or download the file manually."
        )
        sys.exit(1)
    except requests.exceptions.RequestException as exc:
        logger.error("Failed to download CSV: %s", exc)
        sys.exit(1)

    content = resp.content
    # Try UTF-8 with BOM, then plain UTF-8, then latin-1
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode CSV with any known encoding")


def parse_first_round_csv(text: str) -> dict[str, dict]:
    """Parse the 1st-round results CSV, returning only communes decided in round 1.

    A commune is decided in the 1st round when:
    - only 1 list ran, OR
    - at least one list got >50% of expressed votes

    Returns:
        {commune_code: {
            commune_code, commune_name,
            winner: {
                panel_number, list_label, list_short_label,
                nuance_code, voix, pct_voix_exprimes
            }
        }}
    """
    decided: dict[str, dict] = {}
    total_rows = 0
    skipped_rows = 0
    communes_seen = 0
    communes_second_round = 0

    reader = csv.reader(io.StringIO(text), delimiter=";")
    raw_rows = list(reader)

    if not raw_rows:
        logger.error("CSV is empty — cannot proceed")
        sys.exit(1)

    logger.info(
        "CSV loaded: %d rows (incl. header), %d columns in header",
        len(raw_rows), len(raw_rows[0]),
    )

    for row in raw_rows[1:]:
        total_rows += 1

        if len(row) < META_COLS:
            skipped_rows += 1
            continue

        # Meta columns
        commune_code = row[2].strip().strip('"')
        commune_name = row[3].strip().strip('"')

        if not commune_code:
            skipped_rows += 1
            continue

        communes_seen += 1

        # Parse all list groups
        candidate_cols = row[META_COLS:]
        lists_data = []

        for i in range(len(candidate_cols) // CAND_GROUP_SIZE):
            offset = i * CAND_GROUP_SIZE
            group = candidate_cols[offset: offset + CAND_GROUP_SIZE]
            if len(group) < CAND_GROUP_SIZE:
                continue

            # group[5]=libelle_abrege, group[6]=libelle_liste — skip empty slots
            has_data = (
                group[5].strip('"').strip()
                or group[6].strip('"').strip()
            )
            if not has_data:
                continue

            panneau_raw = group[0].strip('"').strip()
            panel_number = int(panneau_raw) if panneau_raw.isdigit() else 0
            nuance_code = group[4].strip('"').strip()
            list_short_label = group[5].strip('"').strip()
            list_label = group[6].strip('"').strip()
            voix_raw = group[7].strip('"').strip()
            voix = int(voix_raw) if voix_raw.isdigit() else 0
            pct_exprimes = _parse_pct(group[9])

            lists_data.append({
                "panel_number": panel_number,
                "nuance_code": nuance_code,
                "list_short_label": list_short_label,
                "list_label": list_label,
                "voix": voix,
                "pct_voix_exprimes": pct_exprimes,
            })

        if not lists_data:
            skipped_rows += 1
            continue

        # Determine if decided in 1st round
        max_pct = max(lst["pct_voix_exprimes"] for lst in lists_data)
        single_list = len(lists_data) == 1

        if not single_list and max_pct <= 50.0:
            # Goes to 2nd round
            communes_second_round += 1
            continue

        # Find the winner (highest pct, or the only list)
        winner = max(lists_data, key=lambda l: l["pct_voix_exprimes"])

        decided[commune_code] = {
            "commune_code": commune_code,
            "commune_name": commune_name,
            "winner": {
                "panel_number": winner["panel_number"],
                "list_label": winner["list_label"],
                "list_short_label": winner["list_short_label"],
                "nuance_code": winner["nuance_code"],
                "voix": winner["voix"],
                "pct_voix_exprimes": winner["pct_voix_exprimes"],
            },
        }

    logger.info(
        "CSV parsed: %d data rows → %d communes seen, "
        "%d decided in 1st round, %d going to 2nd round, %d skipped rows",
        total_rows, communes_seen, len(decided), communes_second_round, skipped_rows,
    )
    return decided


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
# Matching: winning list → Firestore candidates
# ---------------------------------------------------------------------------
def _match_list_to_candidates(
    commune_code: str,
    nuance_code: str,
    list_label: str,
    by_municipality: dict[str, list[dict]],
) -> list[str]:
    """Return candidate IDs from Firestore that match this winning list.

    Matching strategy (in priority order):
    1. nuance_code exact match on candidate's nuance_code field
    2. nuance_code → NUANCE_TO_PARTY → candidate's party_ids
    3. candidate last name appears in list_label
    4. Levenshtein fuzzy match on candidate last name vs list_label tokens (threshold 2)
    """
    candidates_in_commune = by_municipality.get(commune_code, [])
    if not candidates_in_commune:
        return []

    matched_ids: list[str] = []
    norm_nuance = nuance_code.strip('"').strip()
    party_hint = NUANCE_TO_PARTY.get(norm_nuance, "")
    norm_list = _normalize(list_label)

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

        # Strategy 4: Levenshtein fuzzy match on last name (threshold 2)
        if len(norm_last) > 2:
            dist = _levenshtein(norm_last, norm_list[:len(norm_last) + 4])
            if dist <= 2:
                matched_ids.append(cid)
                continue

    return matched_ids


# ---------------------------------------------------------------------------
# Main ingestion logic
# ---------------------------------------------------------------------------
def ingest(
    db,
    decided_communes: dict[str, dict],
    by_municipality: dict[str, list[dict]],
    dry_run: bool,
) -> None:
    """Write first-round elected data to Firestore.

    For each commune decided in the 1st round:
    - Writes `first_round_elected` + `is_first_round_decided: True` to
      `electoral_lists/{commune_code}` (merge=True)
    - Sets `is_first_round_elected: True` on matched Firestore candidates
    """

    # -----------------------------------------------------------------------
    # Step 1: Match winning lists to Firestore candidates
    # -----------------------------------------------------------------------
    logger.info(
        "Step 1: Matching %d 1st-round winners to Firestore candidates …",
        len(decided_communes),
    )

    app_tracked_communes = set(by_municipality.keys())
    communes_in_app = len(app_tracked_communes & set(decided_communes.keys()))
    communes_matched: set[str] = set()
    candidates_to_update: dict[str, dict] = {}  # candidate_id → update payload
    electoral_lists_updates: dict[str, dict] = {}  # commune_code → Firestore payload

    for commune_code, commune in decided_communes.items():
        winner = commune["winner"]

        # Prepare electoral_lists update regardless of candidate match
        electoral_lists_updates[commune_code] = {
            "first_round_elected": {
                "panel_number": winner["panel_number"],
                "list_label": winner["list_label"],
                "list_short_label": winner["list_short_label"],
                "nuance_code": winner["nuance_code"],
                "voix": winner["voix"],
                "pct_voix_exprimes": winner["pct_voix_exprimes"],
            },
            "is_first_round_decided": True,
        }

        # Match winner to candidates
        cand_ids = _match_list_to_candidates(
            commune_code,
            winner["nuance_code"],
            winner["list_label"],
            by_municipality,
        )

        for cid in cand_ids:
            candidates_to_update[cid] = {
                "is_first_round_elected": True,
                "first_round_nuance_code": winner["nuance_code"],
                "first_round_list_label": winner["list_label"],
                "first_round_panel_number": winner["panel_number"],
            }
            communes_matched.add(commune_code)

    # -----------------------------------------------------------------------
    # Step 2: Log match rate stats
    # -----------------------------------------------------------------------
    candidates_matched = len(candidates_to_update)
    match_rate = (len(communes_matched) / communes_in_app * 100) if communes_in_app > 0 else 0.0

    logger.info("--- Match Rate Summary ---")
    logger.info("Total communes decided in 1st round (CSV):  %d", len(decided_communes))
    logger.info("Communes tracked by app:                    %d", len(app_tracked_communes))
    logger.info("1st-round communes matching app:            %d", communes_in_app)
    logger.info("Communes with ≥1 candidate matched:         %d", len(communes_matched))
    logger.info("Candidates matched:                         %d", candidates_matched)
    logger.info("Match rate (of app communes):               %.1f%%", match_rate)

    if communes_in_app > 0 and match_rate < 50.0:
        logger.warning(
            "Match rate %.1f%% is below 50%% threshold — review NUANCE_TO_PARTY "
            "mapping and Firestore candidate nuance_code fields.",
            match_rate,
        )

    # -----------------------------------------------------------------------
    # Step 3: Write candidate updates to Firestore
    # -----------------------------------------------------------------------
    logger.info("Step 2: Writing is_first_round_elected=True to %d candidates …", candidates_matched)
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
        logger.info("Wrote is_first_round_elected=True for %d candidates", candidates_matched)
    else:
        logger.info(
            "[DRY-RUN] Would write is_first_round_elected=True for %d candidates",
            candidates_matched,
        )
        for cid, data in list(candidates_to_update.items())[:5]:
            logger.info("  [DRY-RUN] candidate %s → %s", cid, data)
        if candidates_matched > 5:
            logger.info("  [DRY-RUN] … and %d more", candidates_matched - 5)

    # -----------------------------------------------------------------------
    # Step 4: Write first_round_elected to electoral_lists docs
    # -----------------------------------------------------------------------
    logger.info(
        "Step 3: Writing first_round_elected to %d electoral_lists docs …",
        len(electoral_lists_updates),
    )
    if not dry_run:
        batch = db.batch()
        batch_count = 0
        for commune_code, payload in electoral_lists_updates.items():
            ref = db.collection("electoral_lists").document(commune_code)
            batch.set(ref, payload, merge=True)
            batch_count += 1
            if batch_count >= BATCH_LIMIT:
                batch.commit()
                batch = db.batch()
                batch_count = 0
        if batch_count > 0:
            batch.commit()
        logger.info(
            "Wrote first_round_elected to %d electoral_lists docs",
            len(electoral_lists_updates),
        )
    else:
        logger.info(
            "[DRY-RUN] Would write first_round_elected to %d electoral_lists docs",
            len(electoral_lists_updates),
        )
        sample = list(electoral_lists_updates.items())[:3]
        for code, payload in sample:
            logger.info("  [DRY-RUN] electoral_lists/%s → %s", code, payload)
        if len(electoral_lists_updates) > 3:
            logger.info("  [DRY-RUN] … and %d more", len(electoral_lists_updates) - 3)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest 1st-round municipales 2026 election winners into Firestore",
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

    # Fetch all candidates once
    by_municipality = fetch_candidates_by_municipality(db)

    # Download and parse 1st-round results CSV
    csv_text = download_csv(FIRST_ROUND_CSV_URL)
    decided_communes = parse_first_round_csv(csv_text)

    # Run ingestion
    ingest(db, decided_communes, by_municipality, dry_run=args.dry_run)

    logger.info("Done.")


if __name__ == "__main__":
    main()
