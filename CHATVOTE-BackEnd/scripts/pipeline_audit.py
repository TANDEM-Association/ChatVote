#!/usr/bin/env python3
"""
End-to-end pipeline verification for 5 municipalities.
Traces data from pourquituvotes.fr → Ministry PDFs → Firebase → Qdrant.
"""

import os, sys, json, re, time, io
from pathlib import Path
from typing import Optional
import requests
from datetime import datetime

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
QDRANT_URL = "http://212.47.245.238:6333"
QDRANT_API_KEY = "7384d5cc296a254996640081df3a08f824a2f999bb1fb98d91929d811ddc22cb"
COLLECTION = "candidates_websites_prod"
MINISTRY_BASE = "https://programme-candidats.interieur.gouv.fr/elections-municipales-2026/data-pdf"

CITIES = [
    "Charleville-Mézières",
    "Chartres",
    "Colomiers",
    "Bègles",
    "Mérignac",
]

FLAGGED_CANDIDATES = [
    # (candidate_id or partial name, city, party, issue)
    ("loi_prud_homme", "Bègles", "lfi", "only 2 chunks, 0 themes"),
    ("guldner", "Bègles", "extreme_gauche", "4 chunks"),
    ("bastera", "Bègles", "rn", "4 chunks"),
    ("millet", "Mérignac", "divers_droite", "4 chunks"),
    ("bourlieux", "Mérignac", "rn", "4 chunks"),
    ("perchet", "Mérignac", "extreme_gauche", "4 chunks"),
]

os.environ["ENV"] = "dev"
sys.path.insert(0, str(Path(__file__).parent.parent))

# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "ChatVote-audit/1.0"})

def get_json(url, timeout=15):
    try:
        r = SESSION.get(url, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}

def head_exists(url, timeout=8):
    try:
        r = SESSION.head(url, timeout=timeout, allow_redirects=True)
        return r.status_code == 200
    except Exception:
        return False

def get_pdf_bytes(url, timeout=20):
    try:
        r = SESSION.get(url, timeout=timeout)
        if r.status_code == 200:
            return r.content
        return None
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Stage 1: pourquituvotes.fr
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("STAGE 1: pourquituvotes.fr — fetching city slugs and candidates")
print("="*70)

villes_data = get_json("https://pourquituvotes.fr/data/villes.json")
if "error" in villes_data:
    print(f"[ERROR] Could not fetch villes.json: {villes_data['error']}")
    villes_list = []
else:
    # Could be list or dict
    if isinstance(villes_data, list):
        villes_list = villes_data
    elif isinstance(villes_data, dict):
        villes_list = list(villes_data.values()) if villes_data else []
    else:
        villes_list = []
    print(f"Total cities from pourquituvotes: {len(villes_list)}")

# Find slugs for our 5 cities
def normalize(s):
    import unicodedata
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.strip()

city_slugs = {}  # city_name -> {"slug": ..., "code_commune": ...}
for city in CITIES:
    norm = normalize(city)
    for v in villes_list:
        vname = ""
        slug = ""
        code = ""
        if isinstance(v, dict):
            vname = v.get("nom", v.get("name", v.get("ville", "")))
            slug = v.get("slug", v.get("id", ""))
            code = v.get("code_commune", v.get("code", v.get("insee", "")))
        elif isinstance(v, str):
            vname = v
            slug = normalize(v).replace(" ", "-")
        if normalize(vname) == norm:
            city_slugs[city] = {"slug": slug, "code_commune": code, "raw": v}
            break
    if city not in city_slugs:
        # Try partial match on slug
        for v in villes_list:
            if isinstance(v, dict):
                slug = v.get("slug", "")
                if norm.replace(" ", "-") in slug or norm.replace("-", "") in normalize(slug).replace("-",""):
                    city_slugs[city] = {"slug": slug, "code_commune": v.get("code_commune",""), "raw": v}
                    break

for city in CITIES:
    info = city_slugs.get(city)
    if info:
        print(f"  {city}: slug={info['slug']}, code={info['code_commune']}")
    else:
        print(f"  {city}: NOT FOUND in villes.json")

# Fetch election data per city
pqtv_candidates = {}  # city -> list of candidate dicts
for city in CITIES:
    info = city_slugs.get(city)
    if not info or not info.get("slug"):
        pqtv_candidates[city] = {"error": "no slug found"}
        continue
    slug = info["slug"]
    url = f"https://pourquituvotes.fr/data/elections/{slug}-2026.json"
    data = get_json(url)
    if "error" in data:
        # Try without year suffix
        url2 = f"https://pourquituvotes.fr/data/elections/{slug}.json"
        data = get_json(url2)
    pqtv_candidates[city] = data
    if "error" in data:
        print(f"  {city}: [ERROR] {data['error']} (url={url})")
    else:
        # Count candidates
        cands = []
        if isinstance(data, list):
            cands = data
        elif isinstance(data, dict):
            cands = data.get("candidats", data.get("listes", data.get("candidates", [])))
        print(f"  {city}: {len(cands)} candidates/listes found")

# ---------------------------------------------------------------------------
# Stage 2: Ministry profession de foi PDFs
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("STAGE 2: Ministry PDFs — checking existence by commune_code + panneau")
print("="*70)

# We need commune codes — get from Firebase in Stage 3, but also from villes.json
# Fallback: known INSEE codes for our 5 cities
KNOWN_CODES = {
    "Charleville-Mézières": "08105",
    "Chartres": "28085",
    "Colomiers": "31149",
    "Bègles": "33032",
    "Mérignac": "33281",
}

ministry_pdfs = {}  # city -> {tour: {panneau: True/False}}
for city in CITIES:
    code = KNOWN_CODES.get(city)
    if not code:
        info = city_slugs.get(city, {})
        code = info.get("code_commune", "")
    if not code:
        print(f"  {city}: no commune code, skipping Ministry PDF check")
        ministry_pdfs[city] = {}
        continue

    ministry_pdfs[city] = {}
    for tour in [1, 2]:
        found = {}
        # Check panneaux 1..20 with HEAD requests
        for panneau in range(1, 21):
            url = f"{MINISTRY_BASE}/tour{tour}-{code}-{panneau:02d}.pdf"
            exists = head_exists(url)
            if exists:
                found[panneau] = url
        ministry_pdfs[city][tour] = found
        if found:
            print(f"  {city} (code={code}) tour{tour}: panneaux found = {sorted(found.keys())}")
        else:
            print(f"  {city} (code={code}) tour{tour}: no PDFs found at ministry")

# ---------------------------------------------------------------------------
# Stage 3: Firebase candidates
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("STAGE 3: Firebase — fetching candidates per municipality")
print("="*70)

try:
    import firebase_admin
    from firebase_admin import firestore, credentials
    cred_path = "chat-vote-dev-firebase-adminsdk-fbsvc-5357066618.json"
    if not firebase_admin._apps:
        if Path(cred_path).exists():
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        else:
            firebase_admin.initialize_app()
    db = firestore.client()
    firebase_ok = True
    print("  Firebase initialized OK")
except Exception as e:
    firebase_ok = False
    print(f"  [ERROR] Firebase init failed: {e}")

firebase_candidates = {}  # city -> list of candidate docs
if firebase_ok:
    for city in CITIES:
        code = KNOWN_CODES.get(city, "")
        try:
            docs = db.collection("candidates").where(
                "municipality_code", "==", code
            ).stream()
            cands = []
            for doc in docs:
                d = doc.to_dict()
                d["_id"] = doc.id
                cands.append(d)
            firebase_candidates[city] = cands
            print(f"  {city} (code={code}): {len(cands)} candidates in Firebase")
        except Exception as e:
            firebase_candidates[city] = []
            print(f"  {city}: [ERROR] {e}")

# Also fetch municipality docs to verify codes
if firebase_ok:
    print("\n  Verifying municipality codes from Firebase municipalities collection:")
    for city in CITIES:
        try:
            docs = db.collection("municipalities").where(
                "name", "==", city
            ).limit(3).stream()
            for doc in docs:
                d = doc.to_dict()
                print(f"    {city}: code={d.get('code', d.get('municipality_code', 'N/A'))}, id={doc.id}")
        except Exception as e:
            print(f"    {city}: [ERROR] {e}")

# ---------------------------------------------------------------------------
# Stage 4: Qdrant indexed data
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("STAGE 4: Qdrant — querying chunk counts per candidate")
print("="*70)

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, ScrollRequest

qclient = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
    prefer_grpc=False,
    https=False,
    timeout=30,
)

def get_candidate_qdrant_stats(candidate_id: str) -> dict:
    """Get chunk count and metadata summary for a candidate_id (= namespace)."""
    try:
        results, _ = qclient.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="metadata.namespace",
                        match=MatchValue(value=candidate_id),
                    )
                ]
            ),
            limit=200,
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            return {"count": 0, "source_types": [], "themes": [], "sub_themes": []}

        source_types = set()
        themes = set()
        sub_themes = set()
        for pt in results:
            payload = pt.payload or {}
            meta = payload.get("metadata", {})
            st = meta.get("source_document", meta.get("source_type", meta.get("document_type", "")))
            if st:
                source_types.add(st)
            th = meta.get("theme", "")
            if th:
                themes.add(th)
            sth = meta.get("sub_theme", "")
            if sth:
                sub_themes.add(sth)
        return {
            "count": len(results),
            "source_types": sorted(source_types),
            "themes": sorted(themes),
            "sub_themes": sorted(sub_themes),
            "sample_payload": results[0].payload if results else {},
        }
    except Exception as e:
        return {"count": -1, "error": str(e)}

# Collect all candidate_ids from Firebase
all_candidate_ids = []
for city in CITIES:
    for cand in firebase_candidates.get(city, []):
        cid = cand.get("candidate_id", cand.get("_id", ""))
        if cid:
            all_candidate_ids.append((city, cid))

print(f"  Total candidates to check in Qdrant: {len(all_candidate_ids)}")
qdrant_stats = {}
for i, (city, cid) in enumerate(all_candidate_ids):
    stats = get_candidate_qdrant_stats(cid)
    qdrant_stats[cid] = stats
    if stats["count"] != 0:
        print(f"  [{city}] {cid}: {stats['count']} chunks | sources={stats['source_types']} | themes={len(stats['themes'])}")
    else:
        print(f"  [{city}] {cid}: 0 chunks (NOT INDEXED)")

# ---------------------------------------------------------------------------
# Stage 5: Cross-comparison
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("STAGE 5: CROSS-COMPARISON TABLE")
print("="*70)

# Parse panneau from candidate_id: cand-{code}-{panneau}
def parse_panneau(candidate_id: str) -> Optional[str]:
    m = re.search(r"cand-\d+-(\d+)", candidate_id)
    return m.group(1) if m else None

# Extract pqtv programme URLs — build a lookup: normalized_name -> programmeUrl
def extract_pqtv_lookup(city: str) -> dict:
    data = pqtv_candidates.get(city, {})
    lookup = {}
    if isinstance(data, dict) and "error" in data:
        return lookup
    items = data if isinstance(data, list) else data.get("candidats", data.get("listes", data.get("candidates", [])))
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("nom", item.get("name", item.get("tete_de_liste", "")))
        prog_url = item.get("programmeUrl", item.get("programme_url", item.get("website", item.get("site", ""))))
        if name:
            lookup[normalize(name)] = {"name": name, "programmeUrl": prog_url, "raw": item}
    return lookup

city_reports = {}
gaps = []

for city in CITIES:
    pqtv_lookup = extract_pqtv_lookup(city)
    candidates = firebase_candidates.get(city, [])
    ministry = ministry_pdfs.get(city, {})
    panneau_to_pdf_url = {}
    for tour, panneaux in ministry.items():
        for p, url in panneaux.items():
            panneau_to_pdf_url[p] = url  # use tour1 primarily

    rows = []
    for cand in candidates:
        cid = cand.get("candidate_id", cand.get("_id", ""))
        first = cand.get("first_name", "")
        last = cand.get("last_name", "")
        full_name = f"{first} {last}".strip()
        party_ids = cand.get("party_ids", [])
        party = ", ".join(party_ids)
        has_website = cand.get("has_website", bool(cand.get("website_url")))
        website_url = cand.get("website_url", "")
        has_manifesto = cand.get("has_manifesto", False)
        panneau_str = parse_panneau(cid) or cand.get("panneau", "")
        panneau_num = int(panneau_str) if panneau_str and panneau_str.isdigit() else None

        # pqtv match
        norm_name = normalize(full_name)
        pqtv_match = None
        for k, v in pqtv_lookup.items():
            if norm_name in k or k in norm_name:
                pqtv_match = v
                break

        # Ministry PDF
        ministry_pdf_url = panneau_to_pdf_url.get(panneau_num) if panneau_num else None
        ministry_pdf_exists = ministry_pdf_url is not None

        # Qdrant
        stats = qdrant_stats.get(cid, {"count": 0, "source_types": [], "themes": []})
        chunk_count = stats.get("count", 0)
        source_types = stats.get("source_types", [])
        themes = stats.get("themes", [])

        # Gap detection
        data_gaps = []
        if pqtv_match and pqtv_match.get("programmeUrl") and not has_website:
            data_gaps.append(f"PQTV has programmeUrl but Firebase has_website=False")
        if pqtv_match and pqtv_match.get("programmeUrl") and chunk_count == 0:
            data_gaps.append(f"PQTV has programmeUrl but 0 Qdrant chunks")
        if ministry_pdf_exists and not has_manifesto:
            data_gaps.append(f"Ministry PDF exists (panneau {panneau_num}) but has_manifesto=False")
        if ministry_pdf_exists and chunk_count == 0:
            data_gaps.append(f"Ministry PDF exists but 0 Qdrant chunks")
        if ministry_pdf_exists and chunk_count > 0 and chunk_count < 3:
            data_gaps.append(f"Ministry PDF exists but only {chunk_count} chunks (too few)")
        if chunk_count > 0 and len(themes) == 0:
            data_gaps.append(f"Has {chunk_count} chunks but 0 themes classified")
        if has_website and website_url and chunk_count == 0:
            data_gaps.append(f"has_website=True but 0 Qdrant chunks (not scraped/indexed)")

        if data_gaps:
            gaps.append({"city": city, "candidate_id": cid, "name": full_name, "party": party, "gaps": data_gaps})

        rows.append({
            "candidate_id": cid,
            "name": full_name,
            "party": party,
            "panneau": panneau_str,
            "pqtv_programme_url": pqtv_match.get("programmeUrl", "") if pqtv_match else "NO_MATCH",
            "ministry_pdf": "YES" if ministry_pdf_exists else "NO",
            "ministry_pdf_url": ministry_pdf_url or "",
            "firebase_has_website": has_website,
            "firebase_website_url": website_url,
            "firebase_has_manifesto": has_manifesto,
            "qdrant_chunks": chunk_count,
            "qdrant_sources": "|".join(source_types),
            "qdrant_themes": len(themes),
            "qdrant_theme_list": "|".join(themes),
            "data_gaps": "; ".join(data_gaps),
        })

    city_reports[city] = rows
    print(f"\n--- {city} ({len(rows)} candidates) ---")
    print(f"{'ID':<40} {'Name':<30} {'Party':<20} {'Pan':<4} {'PQTV':<6} {'MiniPDF':<8} {'FBweb':<6} {'FBman':<6} {'Qchks':<6} {'Qthm':<5} GAPS")
    print("-"*160)
    for r in rows:
        pqtv_flag = "YES" if r["pqtv_programme_url"] and r["pqtv_programme_url"] not in ("", "NO_MATCH") else ("?" if r["pqtv_programme_url"] == "NO_MATCH" else "NO")
        gap_flag = "*** " + r["data_gaps"][:80] if r["data_gaps"] else ""
        print(f"{r['candidate_id']:<40} {r['name']:<30} {r['party']:<20} {r['panneau']:<4} {pqtv_flag:<6} {r['ministry_pdf']:<8} {str(r['firebase_has_website']):<6} {str(r['firebase_has_manifesto']):<6} {r['qdrant_chunks']:<6} {r['qdrant_themes']:<5} {gap_flag}")

# ---------------------------------------------------------------------------
# Stage 6: Deep investigation of flagged candidates
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("STAGE 6: Deep investigation of flagged candidates")
print("="*70)

flagged_details = []

# Find flagged candidates in firebase data
flagged_search_terms = [
    ("prud", "Bègles"),
    ("guldner", "Bègles"),
    ("bastera", "Bègles"),
    ("millet", "Mérignac"),
    ("bourlieux", "Mérignac"),
    ("perchet", "Mérignac"),
]

flagged_cands = []
for city in ["Bègles", "Mérignac"]:
    for cand in firebase_candidates.get(city, []):
        full = (cand.get("first_name","") + " " + cand.get("last_name","")).lower()
        for term, c in flagged_search_terms:
            if c == city and term in full:
                flagged_cands.append((city, cand))
                break

print(f"Found {len(flagged_cands)} flagged candidates to investigate")

for city, cand in flagged_cands:
    cid = cand.get("candidate_id", cand.get("_id",""))
    full_name = f"{cand.get('first_name','')} {cand.get('last_name','')}".strip()
    party_ids = cand.get("party_ids", [])
    panneau_str = parse_panneau(cid) or ""
    panneau_num = int(panneau_str) if panneau_str.isdigit() else None

    print(f"\n  [{city}] {full_name} (id={cid})")
    print(f"    party_ids: {party_ids}")
    print(f"    panneau: {panneau_str}")
    print(f"    has_manifesto: {cand.get('has_manifesto', False)}")
    print(f"    has_website: {cand.get('has_website', False)} | website_url: {cand.get('website_url','')}")

    # Check ministry PDF existence
    code = KNOWN_CODES.get(city, "")
    ministry_found = False
    ministry_found_url = ""
    for tour in [1, 2]:
        if panneau_num:
            url = f"{MINISTRY_BASE}/tour{tour}-{code}-{panneau_num:02d}.pdf"
            exists = head_exists(url)
            print(f"    Ministry tour{tour} (panneau {panneau_num:02d}): {'EXISTS' if exists else 'NOT FOUND'} | {url}")
            if exists and not ministry_found:
                ministry_found = True
                ministry_found_url = url

    # Try to fetch and read the PDF if it exists
    if ministry_found:
        print(f"    Downloading PDF to count pages...")
        pdf_bytes = get_pdf_bytes(ministry_found_url)
        if pdf_bytes:
            print(f"    PDF size: {len(pdf_bytes)/1024:.1f} KB")
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                    n_pages = len(pdf.pages)
                    total_chars = sum(len(p.extract_text() or "") for p in pdf.pages)
                    print(f"    PDF pages: {n_pages} | total chars: {total_chars}")
                    # Expected chunks: roughly total_chars / 1000 (chunk size) with 200 overlap
                    est_chunks = max(1, total_chars // 800)
                    print(f"    Expected chunks (estimate): {est_chunks}")
            except ImportError:
                try:
                    import PyPDF2
                    reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
                    n_pages = len(reader.pages)
                    total_text = " ".join(page.extract_text() or "" for page in reader.pages)
                    total_chars = len(total_text)
                    print(f"    PDF pages: {n_pages} | total chars: {total_chars}")
                    est_chunks = max(1, total_chars // 800)
                    print(f"    Expected chunks (estimate): {est_chunks}")
                except Exception as e2:
                    print(f"    [WARN] Could not parse PDF: {e2}")
        else:
            print(f"    [ERROR] Failed to download PDF")

    # Qdrant details
    stats = qdrant_stats.get(cid, {})
    print(f"    Qdrant chunks: {stats.get('count', 0)}")
    print(f"    Qdrant source_types: {stats.get('source_types', [])}")
    print(f"    Qdrant themes: {stats.get('themes', [])}")
    if stats.get("sample_payload"):
        meta = stats["sample_payload"].get("metadata", {})
        print(f"    Sample chunk metadata keys: {list(meta.keys())}")

    flagged_details.append({
        "city": city,
        "candidate_id": cid,
        "name": full_name,
        "party_ids": party_ids,
        "ministry_pdf_exists": ministry_found,
        "qdrant_chunks": stats.get("count", 0),
        "qdrant_themes": stats.get("themes", []),
    })

# ---------------------------------------------------------------------------
# Summary of all gaps
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("SUMMARY OF ALL DATA GAPS")
print("="*70)
print(f"\nTotal candidates with gaps: {len(gaps)}")
gap_types = {}
for g in gaps:
    for gap_desc in g["gaps"]:
        # Normalize gap type
        key = re.sub(r"\d+", "N", gap_desc.split("(")[0].strip())
        gap_types[key] = gap_types.get(key, 0) + 1

print("\nGap type frequency:")
for k, v in sorted(gap_types.items(), key=lambda x: -x[1]):
    print(f"  {v:3d}x  {k}")

print("\nDetailed gap list:")
for g in gaps:
    print(f"  [{g['city']}] {g['name']} ({g['party']}): {'; '.join(g['gaps'])}")

# ---------------------------------------------------------------------------
# Save report
# ---------------------------------------------------------------------------
report_dir = Path("/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd/.omc/scientist/reports")
report_dir.mkdir(parents=True, exist_ok=True)
figures_dir = Path("/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd/.omc/scientist/figures")
figures_dir.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# Save raw data as JSON
json_path = report_dir / f"{timestamp}_pipeline_audit_data.json"
with open(json_path, "w", encoding="utf-8") as f:
    json.dump({
        "city_reports": city_reports,
        "gaps": gaps,
        "gap_type_frequency": gap_types,
        "flagged_details": flagged_details,
        "ministry_pdfs": {city: {str(t): list(p.keys()) for t, p in tours.items()} for city, tours in ministry_pdfs.items()},
        "pqtv_candidate_counts": {
            city: len(pqtv_candidates[city]) if isinstance(pqtv_candidates.get(city), list)
            else len(pqtv_candidates[city].get("candidats", pqtv_candidates[city].get("listes", [])))
            if isinstance(pqtv_candidates.get(city), dict) and "error" not in pqtv_candidates[city]
            else "error"
            for city in CITIES
        },
    }, f, ensure_ascii=False, indent=2)
print(f"\nData saved to: {json_path}")

# ---------------------------------------------------------------------------
# Visualizations
# ---------------------------------------------------------------------------
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use("Agg")

# Fig 1: chunk counts per city (stacked: 0 chunks vs >0)
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle("Pipeline Audit — Qdrant Coverage per City", fontsize=13)

for ax, city in zip(axes.flat, CITIES[:2]):
    pass  # will do differently

# Bar chart: indexed vs not-indexed per city
city_coverage = {}
for city in CITIES:
    rows = city_reports.get(city, [])
    total = len(rows)
    indexed = sum(1 for r in rows if r["qdrant_chunks"] > 0)
    with_themes = sum(1 for r in rows if r["qdrant_themes"] > 0)
    ministry_exists = sum(1 for r in rows if r["ministry_pdf"] == "YES")
    ministry_missing_chunks = sum(1 for r in rows if r["ministry_pdf"] == "YES" and r["qdrant_chunks"] == 0)
    city_coverage[city] = {
        "total": total,
        "indexed": indexed,
        "not_indexed": total - indexed,
        "with_themes": with_themes,
        "ministry_exists": ministry_exists,
        "ministry_missing_chunks": ministry_missing_chunks,
    }

fig, ax = plt.subplots(figsize=(12, 6))
cities_short = [c[:12] for c in CITIES]
x = range(len(CITIES))
totals = [city_coverage[c]["total"] for c in CITIES]
indexed = [city_coverage[c]["indexed"] for c in CITIES]
not_indexed = [city_coverage[c]["not_indexed"] for c in CITIES]
with_themes = [city_coverage[c]["with_themes"] for c in CITIES]

width = 0.22
ax.bar([xi - width for xi in x], totals, width, label="Total candidates", color="#4472C4")
ax.bar([xi for xi in x], indexed, width, label="Qdrant indexed (>0 chunks)", color="#70AD47")
ax.bar([xi + width for xi in x], with_themes, width, label="With themes classified", color="#FFC000")

ax.set_xticks(list(x))
ax.set_xticklabels(cities_short, rotation=15)
ax.set_ylabel("Candidate count")
ax.set_title("Qdrant Coverage by City")
ax.legend()
ax.grid(axis="y", alpha=0.3)
for xi, t, i, w in zip(x, totals, indexed, with_themes):
    ax.text(xi - width, t + 0.1, str(t), ha="center", va="bottom", fontsize=8)
    ax.text(xi, i + 0.1, str(i), ha="center", va="bottom", fontsize=8)
    ax.text(xi + width, w + 0.1, str(w), ha="center", va="bottom", fontsize=8)

plt.tight_layout()
fig1_path = figures_dir / f"{timestamp}_coverage_by_city.png"
plt.savefig(fig1_path, dpi=120)
plt.close()
print(f"Figure 1 saved: {fig1_path}")

# Fig 2: Gap type breakdown
if gap_types:
    fig, ax = plt.subplots(figsize=(12, 5))
    labels = [k[:55] for k in gap_types.keys()]
    values = list(gap_types.values())
    colors = ["#C00000" if v > 5 else "#FF9900" if v > 2 else "#FFC000" for v in values]
    bars = ax.barh(labels, values, color=colors)
    ax.set_xlabel("Number of candidates affected")
    ax.set_title("Data Gap Types — All 5 Cities")
    ax.grid(axis="x", alpha=0.3)
    for bar, v in zip(bars, values):
        ax.text(v + 0.05, bar.get_y() + bar.get_height()/2, str(v), va="center", fontsize=9)
    plt.tight_layout()
    fig2_path = figures_dir / f"{timestamp}_gap_types.png"
    plt.savefig(fig2_path, dpi=120)
    plt.close()
    print(f"Figure 2 saved: {fig2_path}")

# Fig 3: chunk count distribution across all candidates
all_chunk_counts = [r["qdrant_chunks"] for city in CITIES for r in city_reports.get(city, []) if r["qdrant_chunks"] >= 0]
fig, ax = plt.subplots(figsize=(10, 5))
ax.hist(all_chunk_counts, bins=range(0, max(all_chunk_counts)+2) if all_chunk_counts else [0,1], color="#4472C4", edgecolor="white")
ax.set_xlabel("Qdrant chunk count per candidate")
ax.set_ylabel("Number of candidates")
ax.set_title("Distribution of Qdrant Chunk Counts (all 5 cities)")
ax.axvline(4, color="red", linestyle="--", label="4-chunk threshold (flagged)")
ax.legend()
ax.grid(alpha=0.3)
plt.tight_layout()
fig3_path = figures_dir / f"{timestamp}_chunk_distribution.png"
plt.savefig(fig3_path, dpi=120)
plt.close()
print(f"Figure 3 saved: {fig3_path}")

# ---------------------------------------------------------------------------
# Write markdown report
# ---------------------------------------------------------------------------
md_path = report_dir / f"{timestamp}_pipeline_audit_report.md"
with open(md_path, "w", encoding="utf-8") as f:
    f.write(f"# Pipeline Audit Report\n\n")
    f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    f.write(f"**Scope**: End-to-end pipeline verification for 5 municipalities\n\n")
    f.write(f"**Cities**: {', '.join(CITIES)}\n\n")
    f.write(f"---\n\n")

    # Objective
    f.write("## [OBJECTIVE]\n\n")
    f.write("Identify where data drift occurs in the pipeline: pourquituvotes.fr → Ministry PDFs → Firebase → Qdrant indexing.\n\n")

    # Data summary
    f.write("## [DATA]\n\n")
    total_cands = sum(len(city_reports.get(c, [])) for c in CITIES)
    total_indexed = sum(city_coverage[c]["indexed"] for c in CITIES)
    total_gaps = len(gaps)
    f.write(f"- Total candidates across 5 cities: **{total_cands}**\n")
    f.write(f"- Candidates with any Qdrant chunks: **{total_indexed}** ({100*total_indexed//max(total_cands,1)}%)\n")
    f.write(f"- Candidates with data gaps: **{total_gaps}**\n\n")

    # Per-city coverage table
    f.write("## Coverage Summary\n\n")
    f.write("| City | Total | Indexed | With Themes | Ministry PDFs | Ministry+Missing |\n")
    f.write("|------|-------|---------|-------------|---------------|------------------|\n")
    for city in CITIES:
        cv = city_coverage[city]
        f.write(f"| {city} | {cv['total']} | {cv['indexed']} | {cv['with_themes']} | {cv['ministry_exists']} | {cv['ministry_missing_chunks']} |\n")

    # Per-city detailed tables
    for city in CITIES:
        rows = city_reports.get(city, [])
        f.write(f"\n## {city}\n\n")
        f.write("| candidate_id | name | party | pan | PQTV URL | Ministry PDF | FB website | FB manifesto | Qdrant chunks | Themes | Data Gaps |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in rows:
            pqtv = "YES" if r["pqtv_programme_url"] and r["pqtv_programme_url"] not in ("", "NO_MATCH") else ("?" if r["pqtv_programme_url"] == "NO_MATCH" else "NO")
            gaps_short = r["data_gaps"][:100] if r["data_gaps"] else ""
            f.write(f"| {r['candidate_id']} | {r['name']} | {r['party']} | {r['panneau']} | {pqtv} | {r['ministry_pdf']} | {r['firebase_has_website']} | {r['firebase_has_manifesto']} | {r['qdrant_chunks']} | {r['qdrant_themes']} | {gaps_short} |\n")

    # Gaps section
    f.write("\n## [FINDING] Data Gap Summary\n\n")
    f.write(f"**{len(gaps)} candidates** have at least one data gap.\n\n")
    f.write("### Gap Type Frequency\n\n")
    for k, v in sorted(gap_types.items(), key=lambda x: -x[1]):
        f.write(f"- **{v}x** {k}\n")

    # Flagged investigation
    f.write("\n## [FINDING] Flagged Candidate Deep Investigation\n\n")
    for detail in flagged_details:
        f.write(f"### {detail['name']} ({detail['city']})\n\n")
        f.write(f"- candidate_id: `{detail['candidate_id']}`\n")
        f.write(f"- party_ids: {detail['party_ids']}\n")
        f.write(f"- Ministry PDF exists: **{detail['ministry_pdf_exists']}**\n")
        f.write(f"- Qdrant chunks: **{detail['qdrant_chunks']}**\n")
        f.write(f"- Qdrant themes: {detail['qdrant_themes']}\n\n")

    # Stat annotations
    f.write("\n## Statistics\n\n")
    f.write(f"[STAT:n] n={total_cands} total candidates across 5 municipalities\n\n")
    not_indexed_count = total_cands - total_indexed
    f.write(f"[STAT:effect_size] {not_indexed_count}/{total_cands} ({100*not_indexed_count//max(total_cands,1)}%) candidates have zero Qdrant chunks\n\n")
    f.write(f"[STAT:n] {total_gaps} candidates flagged with at least one data gap\n\n")

    # Limitations
    f.write("\n## [LIMITATION]\n\n")
    f.write("- pourquituvotes.fr slugs may not map 1:1 to Firebase municipality names\n")
    f.write("- Ministry PDF URL pattern assumes `tour1-{code}-{panneau:02d}.pdf` — alternate formats may exist\n")
    f.write("- Qdrant scroll limited to 200 results per candidate — high-content candidates may be undercounted\n")
    f.write("- Firebase query uses exact `municipality_code` match; any code discrepancy yields zero results\n")
    f.write("- Theme classification absence may reflect pipeline stage not yet run, not a true gap\n")

print(f"\nMarkdown report saved to: {md_path}")
print("\n[DONE]")
