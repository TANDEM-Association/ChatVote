#!/usr/bin/env python3
"""
Generate municipalities.json, electoral_lists.json and candidates.json
from the data.gouv.fr candidatures CSV (municipales-2026).

Uses the population CSV to pick the top N communes by population,
then extracts lists and candidates from the candidatures CSV.
No fallback data — only real data from official sources.

Usage:
    python scripts/generate_seed_from_csv.py              # Top 287 communes
    python scripts/generate_seed_from_csv.py --top 50     # Top 50 communes
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
COWORK_DIR = Path(__file__).resolve().parents[3] / "chatvote-cowork" / "scraper"
CSV_PATH = COWORK_DIR / "candidatures.csv"
POP_CSV_PATH = COWORK_DIR / "communes_population.csv"
WEBSITES_CSV_PATH = COWORK_DIR / "candidate_websites.csv"
SEED_DIR = REPO_ROOT / "firebase" / "firestore_data" / "dev"

MUNICIPALITIES_OUT = SEED_DIR / "municipalities.json"
ELECTORAL_LISTS_OUT = SEED_DIR / "electoral_lists.json"
CANDIDATES_OUT = SEED_DIR / "candidates.json"


def load_top_communes(top_n: int) -> dict[str, dict]:
    """Load top N communes by population from the population CSV.

    Returns {code: {code, nom, population, dep_code, dep_nom, reg_code, reg_nom, ...}}
    """
    if not POP_CSV_PATH.exists():
        print(f"ERROR: Population CSV not found at {POP_CSV_PATH}")
        sys.exit(1)

    communes = []
    with open(POP_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row.get("code_insee", "")
            typecom = row.get("typecom", "")
            # Only actual communes (not arrondissements, etc.)
            if typecom != "COM":
                continue
            try:
                population = int(row.get("population", 0))
            except (ValueError, TypeError):
                population = 0
            communes.append({
                "code": code,
                "nom": row.get("nom_standard", ""),
                "population": population,
                "dep_code": row.get("dep_code", ""),
                "dep_nom": row.get("dep_nom", ""),
                "reg_code": row.get("reg_code", ""),
                "reg_nom": row.get("reg_nom", ""),
                "code_postal": row.get("code_postal", ""),
                "epci_code": row.get("epci_code", ""),
                "epci_nom": row.get("epci_nom", ""),
                "superficie_km2": row.get("superficie_km2", ""),
            })

    communes.sort(key=lambda c: c["population"], reverse=True)
    top = communes[:top_n]
    print(f"  Top {len(top)} communes by population")
    print(f"  Largest: {top[0]['nom']} ({top[0]['population']:,})")
    print(f"  Smallest: {top[-1]['nom']} ({top[-1]['population']:,})")
    return {c["code"]: c for c in top}


def build_municipalities_json(communes: dict[str, dict]) -> dict:
    """Build municipalities.json from population data."""
    result = {}
    for code, c in communes.items():
        result[code] = {
            "code": code,
            "nom": c["nom"],
            "population": c["population"],
            "codeDepartement": c["dep_code"],
            "departement": {"code": c["dep_code"], "nom": c["dep_nom"]},
            "codeRegion": c["reg_code"],
            "region": {"code": c["reg_code"], "nom": c["reg_nom"]},
            "codesPostaux": [c["code_postal"]] if c["code_postal"] else [],
            "codeEpci": c["epci_code"],
            "epci": {"code": c["epci_code"], "nom": c["epci_nom"]},
        }
    return result


def parse_csv(target_codes: set[str]):
    """Parse the candidatures CSV, filtering to target communes only.

    Returns:
        communes: {commune_code: {commune_name, lists: {panneau: {..., candidates: [...]}}}}
    """
    communes: dict = {}
    skipped = 0

    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            commune_code = row["Code circonscription"]
            if commune_code not in target_codes:
                skipped += 1
                continue

            commune_name = row["Circonscription"]
            panneau = row["Numéro de panneau"]

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
                "ordre": int(row["Ordre"]),
                "sexe": row["Sexe"],
                "nom": row["Nom sur le bulletin de vote"],
                "prenom": row["Prénom sur le bulletin de vote"],
                "nationalite": row.get("Nationalité", ""),
                "tete_de_liste": row.get("Tête de liste") == "OUI",
            }
            lst["candidates"].append(candidate)

            if candidate["tete_de_liste"]:
                lst["head_first_name"] = candidate["prenom"]
                lst["head_last_name"] = candidate["nom"]

    print(f"  Parsed CSV: {len(communes)} target communes found, {skipped:,} rows skipped")
    return communes


def build_electoral_lists(communes: dict) -> dict:
    """Build electoral_lists.json from parsed data."""
    result = {}
    for commune_code, commune in communes.items():
        lists_sorted = sorted(commune["lists"].values(), key=lambda x: x["panneau"])
        lists_clean = []
        for lst in lists_sorted:
            lists_clean.append({
                "panel_number": lst["panneau"],
                "list_label": lst["list_label"],
                "list_short_label": lst["list_short_label"],
                "nuance_code": lst["nuance_code"],
                "nuance_label": lst["nuance_label"],
                "head_first_name": lst["head_first_name"],
                "head_last_name": lst["head_last_name"],
            })

        result[commune_code] = {
            "commune_code": commune_code,
            "commune_name": commune["commune_name"],
            "list_count": len(lists_clean),
            "lists": lists_clean,
        }
    return result


NUANCE_TO_PARTY_IDS = {
    "LRN":  ["rn"],
    "LFI":  ["lfi"],
    "LSOC": ["ps"],
    "LLR":  ["lr"],
    "LREC": ["reconquete"],
    "LVEC": ["europe-ecologie-les-verts"],
    "LECO": ["europe-ecologie-les-verts"],
    "LUG":  ["union_gauche"],
    "LUD":  ["union_droite"],
    "LUC":  ["union_centre"],
    "LDVG": ["divers_gauche"],
    "LDVD": ["divers_droite"],
    "LDVC": ["divers_centre"],
    "LDIV": ["divers"],
    "LEXG": ["extreme_gauche"],
    "LEXD": ["extreme_droite"],
    "LUXD": ["extreme_droite"],
}


def build_candidates(communes: dict) -> dict:
    """Build candidates.json — one entry per tête de liste."""
    result = {}
    for commune_code, commune in communes.items():
        for panneau, lst in commune["lists"].items():
            # Only create candidate entries for têtes de liste
            head = None
            for c in lst["candidates"]:
                if c["tete_de_liste"]:
                    head = c
                    break

            if not head:
                continue

            nuance_code = lst["nuance_code"]
            party_ids = NUANCE_TO_PARTY_IDS.get(nuance_code, [])

            cand_id = f"cand-{commune_code}-{panneau}"
            result[cand_id] = {
                "candidate_id": cand_id,
                "first_name": head["prenom"],
                "last_name": head["nom"],
                "commune_code": commune_code,
                "commune_name": commune["commune_name"],
                "municipality_code": commune_code,
                "municipality_name": commune["commune_name"],
                "party_ids": party_ids,
                "list_label": lst["list_label"],
                "nuance_label": lst["nuance_label"],
                "nuance_code": lst["nuance_code"],
                "panel_number": lst["panneau"],
                "election_type_id": "municipalities-2026",
                "position": "Tête de liste",
                "presence_score": 0,
                "is_incumbent": False,
            }
    return result


def load_scraped_pdfs() -> dict[str, list[dict]]:
    """Load index.json from cowork scraper output.

    Returns {commune_code: [{panneau, list_name, pdf_path, tete_de_liste, ...}]}
    """
    index_path = COWORK_DIR / "output" / "index.json"
    if not index_path.exists():
        return {}
    data = json.loads(index_path.read_text(encoding="utf-8"))
    by_commune: dict[str, list[dict]] = {}
    for entry in data:
        code = entry.get("commune_code", "")
        if code:
            by_commune.setdefault(code, []).append(entry)
    return by_commune


def _norm(s: str) -> str:
    """Normalize a string for fuzzy matching (strip accents, lowercase, alpha only)."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z]", "", s.lower())


def load_candidate_websites(communes_by_name: dict[str, str]) -> dict[tuple[str, str], str]:
    """Load candidate_websites.csv (from Google Sheet export).

    Args:
        communes_by_name: {normalized_commune_name: insee_code} for our target communes.

    Returns:
        {(insee_code, normalized_lastname): website_url}
    """
    if not WEBSITES_CSV_PATH.exists():
        return {}

    result: dict[tuple[str, str], str] = {}
    skipped_commune = 0
    skipped_no_url = 0

    with open(WEBSITES_CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("website_url", "").strip()
            if not url:
                skipped_no_url += 1
                continue

            mname = _norm(row.get("municipality_name", "").strip())
            lastname = _norm(row.get("lastname", "").strip())
            firstname = _norm(row.get("firstname", "").strip())

            code = communes_by_name.get(mname)
            if not code:
                skipped_commune += 1
                continue

            # Store by (code, lastname) — good enough for têtes de liste
            result[(code, lastname)] = url
            # Also store by (code, firstname+lastname) for disambiguation
            result[(code, firstname + lastname)] = url

    total = len({k for k in result if len(k[1]) < 30})  # approx unique by code+lastname
    print(f"  Candidate websites: {total} matched, {skipped_commune} outside target communes, {skipped_no_url} without URL")
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate seed data from data.gouv.fr CSV")
    parser.add_argument("--top", type=int, default=287, help="Number of top communes by population (default: 287)")
    args = parser.parse_args()

    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found at {CSV_PATH}")
        print("Run: python chatvote-cowork/scraper/scrape_elections.py --download-csv")
        sys.exit(1)

    print(f"CSV: {CSV_PATH}")
    print(f"Population: {POP_CSV_PATH}")

    # Step 1: Pick top N communes by population
    top_communes = load_top_communes(args.top)
    target_codes = set(top_communes.keys())

    # Step 2: Build municipalities.json
    municipalities = build_municipalities_json(top_communes)
    with open(MUNICIPALITIES_OUT, "w", encoding="utf-8") as f:
        json.dump(municipalities, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {MUNICIPALITIES_OUT.name}: {len(municipalities)} communes")

    # Step 3: Parse candidatures CSV for target communes
    communes = parse_csv(target_codes)

    # Check which target communes were NOT found in CSV
    found_codes = set(communes.keys())
    missing = target_codes - found_codes
    if missing:
        print(f"\n  WARNING: {len(missing)} communes NOT found in CSV: {sorted(missing)}")

    # Step 4: Load scraped PDFs index to link professions de foi
    scraped = load_scraped_pdfs()
    print(f"  Scraped PDFs index: {sum(len(v) for v in scraped.values())} PDFs across {len(scraped)} communes")

    # Step 4b: Load candidate websites from Google Sheet export
    communes_by_name = {_norm(c["nom"]): c["code"] for c in top_communes.values()}
    websites = load_candidate_websites(communes_by_name)

    # Step 5: Build outputs
    electoral_lists = build_electoral_lists(communes)

    # Enrich electoral lists with PDF availability from scraper
    pdfs_linked = 0
    for code, el in electoral_lists.items():
        commune_pdfs = scraped.get(code, [])
        pdf_by_panneau = {str(p["panneau"]): p for p in commune_pdfs}
        for lst in el["lists"]:
            pdf_entry = pdf_by_panneau.get(str(lst["panel_number"]))
            if pdf_entry:
                lst["has_profession_de_foi"] = True
                lst["pdf_path"] = pdf_entry.get("pdf_path", "")
                lst["pdf_url"] = pdf_entry.get("pdf_url", "")
                pdfs_linked += 1
            else:
                lst["has_profession_de_foi"] = False

    candidates = build_candidates(communes)

    # Enrich candidates with PDF availability + website URLs
    websites_linked = 0
    for cand_id, cand in candidates.items():
        code = cand["commune_code"]
        panneau = str(cand["panel_number"])

        # PDF / profession de foi
        commune_pdfs = scraped.get(code, [])
        pdf_entry = next((p for p in commune_pdfs if str(p["panneau"]) == panneau), None)
        if pdf_entry:
            cand["has_manifesto"] = True
            cand["manifesto_pdf_path"] = pdf_entry.get("pdf_path", "")
        else:
            cand["has_manifesto"] = False

        # Website URL from Google Sheet
        ln = _norm(cand["last_name"])
        fn = _norm(cand["first_name"])
        url = websites.get((code, fn + ln)) or websites.get((code, ln))
        if url:
            cand["has_website"] = True
            cand["website_url"] = url
            websites_linked += 1
        else:
            cand["has_website"] = False

    # Write
    with open(ELECTORAL_LISTS_OUT, "w", encoding="utf-8") as f:
        json.dump(electoral_lists, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {ELECTORAL_LISTS_OUT.name}: {len(electoral_lists)} communes")

    total_lists = sum(el["list_count"] for el in electoral_lists.values())
    print(f"  Total electoral lists: {total_lists}")
    print(f"  Professions de foi linked: {pdfs_linked}")

    with open(CANDIDATES_OUT, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)
    print(f"Wrote {CANDIDATES_OUT.name}: {len(candidates)} candidates (têtes de liste)")

    with_manifesto = sum(1 for c in candidates.values() if c.get("has_manifesto"))
    with_website = sum(1 for c in candidates.values() if c.get("has_website"))
    print(f"  With profession de foi PDF: {with_manifesto}")
    print(f"  With website URL: {with_website}")

    # Summary — top 20 by population
    print("\n--- Top 20 communes ---")
    sorted_codes = sorted(electoral_lists.keys(), key=lambda c: top_communes.get(c, {}).get("population", 0), reverse=True)
    for code in sorted_codes[:20]:
        el = electoral_lists[code]
        pop = top_communes.get(code, {}).get("population", 0)
        cand_count = sum(1 for c in candidates.values() if c["commune_code"] == code)
        pdf_count = sum(1 for lst in el["lists"] if lst.get("has_profession_de_foi"))
        print(f"  {el['commune_name']:.<25} pop {pop:>8,} | {el['list_count']:>2} lists, {pdf_count:>2} PDFs, {cand_count:>2} candidates")


if __name__ == "__main__":
    main()
