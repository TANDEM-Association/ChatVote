#!/usr/bin/env python3
"""Fetch municipales 2026 1st-round results and identify lists qualifying
for the 2nd round. Match with app_truth candidate_ids by commune code
and write to Google Sheets.

A commune goes to 2nd round when no list got >50% of expressed votes.
Lists qualifying for 2nd round need ≥10% of expressed votes.
(If fewer than 2 qualify at 10%, the top 2 go through.)

The CSV only has list-level data (no individual candidate names for communes
≥1000 inhabitants). Matching with app_truth is done by commune code + nuance.

Creates/updates the "candidate second turn" tab. Does NOT touch other tabs.

Usage:
    cd CHATVOTE-BackEnd
    poetry run python scripts/fetch_second_turn_candidates.py
"""

import base64
import csv
import io
import json
import logging
import os
import sys
import unicodedata

import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MUNICIPALES_CSV_URL = (
    "https://www.data.gouv.fr/api/1/datasets/r/4feeef01-24f7-4d5a-914f-8aa806f31ec2"
)

SHEETS_API_URL = "https://sheets.googleapis.com/v4/spreadsheets"
SHEET_ID = os.environ.get(
    "APP_TRUTH_SHEET_ID",
    "15Mge7CUwsFMn5h7SVRYoo5V1SyDE2vU5h4F9OnDHWB8",
)
TAB_NAME = "candidate second turn"

META_COLS = 18           # Fixed columns before repeating candidate groups
CAND_GROUP_SIZE = 13     # Columns per candidate/list in municipales CSV

HEADERS_OUT = [
    "candidate_id",
    "code_departement",
    "libelle_departement",
    "code_commune",
    "libelle_commune",
    "inscrits",
    "votants",
    "exprimes",
    "numero_panneau",
    "nuance_liste",
    "libelle_liste_abrege",
    "libelle_liste",
    "voix",
    "pct_voix_inscrits",
    "pct_voix_exprimes",
]


# ---------------------------------------------------------------------------
# Google Sheets auth (reuses project pattern)
# ---------------------------------------------------------------------------
def _get_sheets_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials

    b64 = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_BASE64", "")
    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    if b64:
        raw = base64.b64decode(b64).decode()
    elif not raw:
        logger.error("No Google Sheets credentials found in env")
        sys.exit(1)
    raw = raw.strip().strip("'\"")
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    creds.refresh(Request())
    return creds


# ---------------------------------------------------------------------------
# Normalisation helpers
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
# Nuance mapping: data.gouv nuance codes → app_truth party_ids
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
# Fetch candidate_id lookup from app_truth tab
# ---------------------------------------------------------------------------
def fetch_app_truth_lookup(creds):
    """Return lookup structures from app_truth.

    Returns:
        by_commune: {commune_code: [(candidate_id, first_name, last_name, party_ids, nuance_code)]}
        by_name: {normalized "LAST|FIRST": (candidate_id, commune_code)}
    """
    token = creds.token
    headers = {"Authorization": f"Bearer {token}"}

    # A=candidate_id, B=first_name, C=last_name, D=commune_code, ..., H=party_ids, I=nuance_code
    url = (
        f"{SHEETS_API_URL}/{SHEET_ID}/values/app_truth!A:I"
        "?majorDimension=ROWS"
    )
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    rows = resp.json().get("values", [])

    if not rows:
        logger.warning("app_truth tab is empty")
        return {}, {}

    by_commune: dict[str, list[tuple]] = {}
    by_name: dict[str, tuple[str, str]] = {}

    for row in rows[1:]:
        if len(row) < 4:
            continue
        cid = row[0]
        first = row[1]
        last = row[2]
        commune_code = row[3]
        party_ids = row[7] if len(row) > 7 else ""
        nuance_code = row[8] if len(row) > 8 else ""

        by_commune.setdefault(commune_code, []).append(
            (cid, first, last, party_ids, nuance_code)
        )

        name_key = f"{_normalize(last)}|{_normalize(first)}"
        by_name[name_key] = (cid, commune_code)

    logger.info(
        "Loaded %d candidates from app_truth across %d communes",
        len(by_name), len(by_commune),
    )
    return by_commune, by_name


# ---------------------------------------------------------------------------
# Match a qualifying list with app_truth candidates in the same commune
# ---------------------------------------------------------------------------
def _match_list_to_candidates(
    commune_code: str,
    nuance: str,
    list_name: str,
    by_commune: dict[str, list[tuple]],
) -> list[str]:
    """Return list of candidate_ids from app_truth that match this list.

    Matching strategy (in order):
    1. Commune code + nuance code match
    2. Commune code + party_ids fuzzy match via NUANCE_TO_PARTY
    3. Commune code + list name contains candidate last name
    """
    candidates_in_commune = by_commune.get(commune_code, [])
    if not candidates_in_commune:
        return []

    matched_ids = []
    norm_nuance = nuance.strip('"').strip()
    party_hint = NUANCE_TO_PARTY.get(norm_nuance, "")
    norm_list = _normalize(list_name)

    for cid, first, last, party_ids, cand_nuance in candidates_in_commune:
        # Strategy 1: nuance code match
        if cand_nuance and cand_nuance == norm_nuance:
            matched_ids.append(cid)
            continue

        # Strategy 2: party_ids match via mapping
        if party_hint and party_hint in party_ids:
            matched_ids.append(cid)
            continue

        # Strategy 3: candidate last name appears in list name
        norm_last = _normalize(last)
        if len(norm_last) > 2 and norm_last in norm_list:
            matched_ids.append(cid)
            continue

    return matched_ids


# ---------------------------------------------------------------------------
# Download & parse CSV — identify 2nd-round qualifiers
# ---------------------------------------------------------------------------
def _parse_pct(s: str) -> float:
    """Parse '43,52%' -> 43.52"""
    s = s.strip().strip('"').replace("%", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def fetch_and_parse(by_commune, by_name):
    """Download municipales 2026 1st-round CSV, identify 2nd-round qualifiers."""
    logger.info("Downloading municipales 2026 1st-round results …")
    resp = requests.get(MUNICIPALES_CSV_URL, timeout=60)
    resp.raise_for_status()

    text = resp.content.decode("utf-8")
    reader = csv.reader(io.StringIO(text), delimiter=";")
    raw_rows = list(reader)

    if not raw_rows:
        logger.error("Empty CSV")
        sys.exit(1)

    logger.info("CSV has %d rows (incl header), %d columns", len(raw_rows), len(raw_rows[0]))

    rows_out: list[list[str]] = [HEADERS_OUT]
    matched = 0
    unmatched = 0
    communes_with_2nd_round = 0

    for row in raw_rows[1:]:
        if len(row) < META_COLS:
            continue

        # Parse all lists in this commune
        candidate_cols = row[META_COLS:]
        lists_data = []

        for i in range(len(candidate_cols) // CAND_GROUP_SIZE):
            offset = i * CAND_GROUP_SIZE
            group = candidate_cols[offset : offset + CAND_GROUP_SIZE]
            if len(group) < CAND_GROUP_SIZE:
                continue

            # Check if this slot has data (list name or candidate name)
            has_data = (
                group[1].strip('"').strip()
                or group[6].strip('"').strip()
            )
            if not has_data:
                continue

            pct_exprimes = _parse_pct(group[9])

            lists_data.append({
                "panneau": group[0].strip('"'),
                "nuance": group[4].strip('"'),
                "libelle_abrege": group[5].strip('"'),
                "libelle": group[6].strip('"'),
                "voix": group[7].strip('"'),
                "pct_inscrits": group[8].strip('"'),
                "pct_exprimes": group[9].strip('"'),
                "pct_exprimes_float": pct_exprimes,
            })

        if not lists_data:
            continue

        # Single list or one list got >50% → elected in 1st round, skip
        max_pct = max(l["pct_exprimes_float"] for l in lists_data)
        if len(lists_data) == 1 or max_pct > 50:
            continue

        communes_with_2nd_round += 1

        # Filter: lists with ≥10% of exprimés qualify for 2nd round
        qualifying = [l for l in lists_data if l["pct_exprimes_float"] >= 10.0]

        # If fewer than 2 qualify at 10%, the top 2 go through
        if len(qualifying) < 2:
            lists_data.sort(key=lambda l: l["pct_exprimes_float"], reverse=True)
            qualifying = lists_data[:2]

        meta = {
            "code_departement": row[0].strip('"'),
            "libelle_departement": row[1].strip('"'),
            "code_commune": row[2].strip('"'),
            "libelle_commune": row[3].strip('"'),
            "inscrits": row[4].strip('"'),
            "votants": row[5].strip('"'),
            "exprimes": row[9].strip('"'),
        }

        commune_code = meta["code_commune"]

        for lst in qualifying:
            # Try to match with app_truth candidates
            cand_ids = _match_list_to_candidates(
                commune_code, lst["nuance"], lst["libelle"], by_commune,
            )
            candidate_id = ", ".join(cand_ids) if cand_ids else ""

            if candidate_id:
                matched += 1
            else:
                unmatched += 1

            rows_out.append([
                candidate_id,
                meta["code_departement"],
                meta["libelle_departement"],
                meta["code_commune"],
                meta["libelle_commune"],
                meta["inscrits"],
                meta["votants"],
                meta["exprimes"],
                lst["panneau"],
                lst["nuance"],
                lst["libelle_abrege"],
                lst["libelle"],
                lst["voix"],
                lst["pct_inscrits"],
                lst["pct_exprimes"],
            ])

    total = len(rows_out) - 1
    logger.info(
        "Found %d communes with 2nd round, %d qualifying lists",
        communes_with_2nd_round, total,
    )
    logger.info("Matched: %d lists, Unmatched: %d lists", matched, unmatched)
    return rows_out, matched, unmatched


# ---------------------------------------------------------------------------
# Write to Google Sheets
# ---------------------------------------------------------------------------
def write_to_sheet(rows: list[list[str]]):
    creds = _get_sheets_credentials()
    token = creds.token
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    meta_url = f"{SHEETS_API_URL}/{SHEET_ID}?fields=sheets.properties.title"
    meta_resp = requests.get(meta_url, headers=headers, timeout=10)
    meta_resp.raise_for_status()
    existing_tabs = [
        s["properties"]["title"] for s in meta_resp.json().get("sheets", [])
    ]

    if TAB_NAME in existing_tabs:
        logger.info("Tab '%s' already exists — clearing data only", TAB_NAME)
    else:
        logger.info("Creating new tab '%s' …", TAB_NAME)
        add_req = {"requests": [{"addSheet": {"properties": {"title": TAB_NAME}}}]}
        requests.post(
            f"{SHEETS_API_URL}/{SHEET_ID}:batchUpdate",
            headers=headers, json=add_req, timeout=10,
        ).raise_for_status()

    clear_url = f"{SHEETS_API_URL}/{SHEET_ID}/values/'{TAB_NAME}'!A:Z:clear"
    requests.post(clear_url, headers=headers, json={}, timeout=10).raise_for_status()

    update_url = (
        f"{SHEETS_API_URL}/{SHEET_ID}/values/"
        f"'{TAB_NAME}'!A1?valueInputOption=RAW"
    )
    write_resp = requests.put(
        update_url, headers=headers, json={"values": rows}, timeout=60,
    )
    write_resp.raise_for_status()
    data = write_resp.json()
    logger.info("Wrote %d rows to '%s' tab", data.get("updatedRows", 0), TAB_NAME)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    creds = _get_sheets_credentials()
    by_commune, by_name = fetch_app_truth_lookup(creds)
    rows, matched, unmatched = fetch_and_parse(by_commune, by_name)
    write_to_sheet(rows)
    logger.info(
        "Done! Matched %d/%d qualifying lists with app_truth candidates",
        matched, matched + unmatched,
    )


if __name__ == "__main__":
    main()
