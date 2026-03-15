"""
Commune chunk audit script.

Queries prod Qdrant + Firestore to show per-candidate:
- Manifesto chunks, website chunks, junk chunks
- Chunk details: URL, theme, source_document, content preview
- Google Drive scraped files (if GOOGLE_SHEETS_CREDENTIALS_BASE64 set)
- Junk detection: no theme, too short, low fiabilité, legal boilerplate
- Per-candidate coverage & ingestion sub-table

Usage:
    cd CHATVOTE-BackEnd
    poetry run python scripts/paris_chunk_audit.py [commune_code]
    # Default: 80021 (Amiens). Use 75056 for Paris.
"""

import json
import os
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

COMMUNE_CODE = sys.argv[1] if len(sys.argv) > 1 else "80021"
QDRANT_URL = "http://212.47.245.238:6333"
QDRANT_API_KEY = "7384d5cc296a254996640081df3a08f824a2f999bb1fb98d91929d811ddc22cb"
CANDIDATES_COLLECTION = "candidates_websites_prod"
PARTIES_COLLECTION = "all_parties_prod"

MIN_CHUNK_LENGTH = 100
LEGAL_BOILERPLATE_KEYWORDS = [
    "mentions légales", "mention légale", "politique de confidentialité",
    "cookies", "rgpd", "cgu", "conditions générales",
    "protection des données", "données personnelles",
    "informations légales", "copyright", "tous droits réservés",
]
JUNK_FIABILITE_THRESHOLD = 4

# Quick-access URLs
QDRANT_DASHBOARD = "http://212.47.245.238:6333/dashboard"
FIREBASE_PROJECT = "chat-vote-prod"
FIRESTORE_CONSOLE = f"https://console.firebase.google.com/project/{FIREBASE_PROJECT}/firestore/databases/-default-/data"
COVERAGE_DASHBOARD = "http://localhost:3000/admin/dashboard"  # local dev


def _qdrant_collection_url(collection: str) -> str:
    return f"{QDRANT_DASHBOARD}#/collections/{collection}"


def _qdrant_scroll_url(collection: str, key: str, value: str) -> str:
    """Qdrant dashboard doesn't support deep filter links, so show the REST API query."""
    return (
        f"curl '{QDRANT_URL}/collections/{collection}/points/scroll' "
        f"-H 'api-key: {QDRANT_API_KEY[:8]}...' "
        f"-d '{{\"filter\":{{\"must\":[{{\"key\":\"metadata.{key}\",\"match\":{{\"value\":\"{value}\"}}}}]}},\"limit\":5,\"with_payload\":true}}'"
    )


def _firestore_doc_url(collection: str, doc_id: str) -> str:
    return f"{FIRESTORE_CONSOLE}/~2F{collection}~2F{doc_id}"


def _firestore_query_url(collection: str, field: str, value: str) -> str:
    return f"{FIRESTORE_CONSOLE}/~2F{collection}  (filter: {field} == {value})"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_meta(payload: dict) -> dict:
    return payload.get("metadata", payload)

def _get_content(payload: dict) -> str:
    return payload.get("page_content", payload.get("text", ""))

def _bar(filled: int, total: int, width: int = 20) -> str:
    if total == 0:
        return "░" * width
    ratio = min(filled / total, 1.0)
    n = int(ratio * width)
    return "█" * n + "░" * (width - n)

def _pct(n: int, d: int) -> str:
    if d == 0:
        return "—"
    return f"{n*100//d}%"


# ---------------------------------------------------------------------------
# Firestore
# ---------------------------------------------------------------------------

def get_firestore_candidates(commune_code: str) -> list[dict]:
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        try:
            app = firebase_admin.get_app("audit")
        except ValueError:
            cred_path = Path(__file__).resolve().parent.parent / "chat-vote-firebase-adminsdk.json"
            if not cred_path.exists():
                import base64
                b64 = os.environ.get("FIREBASE_CREDENTIALS_BASE64", "")
                if b64:
                    cred_data = json.loads(base64.b64decode(b64))
                    cred = credentials.Certificate(cred_data)
                else:
                    print(f"  [WARN] No Firebase credentials at {cred_path}")
                    return []
            else:
                cred = credentials.Certificate(str(cred_path))
            app = firebase_admin.initialize_app(cred, name="audit")

        db = firestore.client(app)
        docs = db.collection("candidates").where(
            filter=firestore.FieldFilter("commune_code", "==", commune_code)
        ).get()
        return [{"_id": doc.id, **doc.to_dict()} for doc in docs]
    except Exception as e:
        print(f"  [WARN] Firestore failed: {e}")
        return []


# ---------------------------------------------------------------------------
# Google Drive
# ---------------------------------------------------------------------------

def check_drive_folders(candidates: list[dict]) -> dict[str, dict]:
    from src.utils import load_env
    load_env()

    b64 = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_BASE64", "")
    if not b64:
        return {}

    try:
        import base64 as b64mod
        import re
        from urllib.parse import urlparse
        from google.auth.transport.requests import Request
        from google.oauth2.service_account import Credentials

        raw = b64mod.b64decode(b64).decode()
        info = json.loads(raw)
        creds = Credentials.from_service_account_info(info, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly",
        ])
        creds.refresh(Request())

        from googleapiclient.discovery import build
        service = build("drive", "v3", credentials=creds, cache_discovery=False)

        DRIVE_FOLDER_ID = "1rLVC3BTVKhOxxGu2GzIfq9BOexleIcRE"

        all_folders = []
        page_token = None
        while True:
            resp = service.files().list(
                q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
                supportsAllDrives=True, includeItemsFromAllDrives=True,
                fields="nextPageToken, files(id, name, webViewLink)",
                pageSize=200, pageToken=page_token,
            ).execute()
            all_folders.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        folder_map = {f["name"]: f for f in all_folders}

        results = {}
        for c in candidates:
            cid = c["_id"]
            url = c.get("website_url") or c.get("website", "")
            if not url or url == "-":
                continue

            parsed = urlparse(url)
            raw_slug = parsed.netloc + parsed.path
            raw_slug = raw_slug.lower().rstrip("/")
            slug = re.sub(r"[^a-z0-9]+", "-", raw_slug).strip("-")

            folder = folder_map.get(slug)
            if not folder:
                for fname, f in folder_map.items():
                    if slug in fname or fname in slug:
                        folder = f
                        break

            if not folder:
                results[cid] = None
                continue

            files_resp = service.files().list(
                q=f"'{folder['id']}' in parents and trashed=false",
                supportsAllDrives=True, includeItemsFromAllDrives=True,
                fields="files(id, name, mimeType, size, webViewLink)",
                pageSize=50,
            ).execute()

            results[cid] = {
                "folder_name": folder["name"],
                "folder_url": folder.get("webViewLink", ""),
                "files": files_resp.get("files", []),
            }

        return results
    except Exception as e:
        print(f"  [WARN] Drive check failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# Junk detection
# ---------------------------------------------------------------------------

def classify_chunk(content: str, meta: dict) -> list[str]:
    reasons = []
    if len(content.strip()) < MIN_CHUNK_LENGTH:
        reasons.append(f"too_short ({len(content.strip())} chars)")
    if not meta.get("theme"):
        reasons.append("no_theme")
    fiab = meta.get("fiabilite", 3)
    if isinstance(fiab, (int, float)) and fiab >= JUNK_FIABILITE_THRESHOLD:
        reasons.append(f"low_fiabilite ({fiab})")
    content_lower = content.lower()
    for kw in LEGAL_BOILERPLATE_KEYWORDS:
        if kw in content_lower:
            reasons.append(f"legal_boilerplate ({kw})")
            break
    return reasons


# ---------------------------------------------------------------------------
# Qdrant
# ---------------------------------------------------------------------------

def scroll_all(client, collection, filt, limit=100):
    all_points = []
    offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection, scroll_filter=filt,
            limit=limit, offset=offset,
            with_payload=True, with_vectors=False,
        )
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset
    return all_points


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"\n{'='*80}")
    print(f"  CHUNK AUDIT: Commune {COMMUNE_CODE}")
    print(f"{'='*80}\n")

    # Quick links
    print(f"  QUICK LINKS:")
    print(f"    Firestore:  {_firestore_query_url('candidates', 'commune_code', COMMUNE_CODE)}")
    print(f"    Firestore:  {_firestore_query_url('municipalities', 'code', COMMUNE_CODE)}")
    print(f"    Qdrant:     {_qdrant_collection_url(CANDIDATES_COLLECTION)}")
    print(f"    Qdrant:     {_qdrant_collection_url(PARTIES_COLLECTION)}")
    print(f"    Dashboard:  {COVERAGE_DASHBOARD}")
    print()

    # 1. Firestore candidates
    print("[1/4] Fetching candidates from Firestore...")
    candidates = get_firestore_candidates(COMMUNE_CODE)
    print(f"  Found {len(candidates)} candidates\n")

    candidate_map = {}
    for c in candidates:
        cid = c["_id"]
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip() or cid
        website_url = c.get("website_url") or c.get("website", "") or ""
        if website_url == "-":
            website_url = ""
        candidate_map[cid] = {
            "name": name,
            "website_url": website_url,
            "has_manifesto": bool(
                c.get("has_manifesto") or c.get("manifesto_url")
                or c.get("election_manifesto_url") or c.get("manifesto_pdf_path")
            ),
            "manifesto_url": c.get("manifesto_url") or c.get("election_manifesto_url") or "",
            "manifesto_pdf_path": c.get("manifesto_pdf_path") or "",
            "has_scraped": bool(c.get("has_scraped")),
            "scrape_chars": c.get("scrape_chars", 0) or 0,
            "party_label": (c.get("list_label") or c.get("nuance_label")
                           or c.get("party_name") or "?"),
            "is_tete_de_liste": bool(c.get("is_tete_de_liste")),
            "nuance_code": c.get("nuance_code", ""),
        }

    # 2. Qdrant chunks
    print("[2/4] Querying Qdrant for chunks...")
    client = QdrantClient(
        url=QDRANT_URL, api_key=QDRANT_API_KEY,
        prefer_grpc=False, check_compatibility=False,
    )

    all_chunks = []
    seen_ids = set()

    for collection in [CANDIDATES_COLLECTION, PARTIES_COLLECTION]:
        points = scroll_all(client, collection, Filter(must=[
            FieldCondition(key="metadata.municipality_code", match=MatchValue(value=COMMUNE_CODE))
        ]))
        for pt in points:
            pid = str(pt.id)
            if pid not in seen_ids:
                seen_ids.add(pid)
                payload = pt.payload or {}
                payload["_collection"] = collection
                all_chunks.append(payload)

    for cid in candidate_map:
        points = scroll_all(client, CANDIDATES_COLLECTION, Filter(must=[
            FieldCondition(key="metadata.namespace", match=MatchValue(value=cid))
        ]))
        for pt in points:
            pid = str(pt.id)
            if pid not in seen_ids:
                seen_ids.add(pid)
                payload = pt.payload or {}
                payload["_collection"] = CANDIDATES_COLLECTION
                all_chunks.append(payload)

    print(f"  Found {len(all_chunks)} total chunks\n")

    # 3. Google Drive
    print("[3/4] Checking Google Drive...")
    drive_results = check_drive_folders(candidates)
    print()

    # 4. Analyze per candidate
    print("[4/4] Analyzing chunks per candidate...\n")

    chunks_by_ns = defaultdict(list)
    for chunk in all_chunks:
        meta = _get_meta(chunk)
        ns = meta.get("namespace", "unknown")
        chunks_by_ns[ns].append(chunk)

    # Build per-candidate stats
    candidate_stats = {}
    for cid, info in candidate_map.items():
        chunks = chunks_by_ns.get(cid, [])
        manifesto = []
        website = []
        junk = []
        good = []

        for chunk in chunks:
            content = _get_content(chunk)
            meta = _get_meta(chunk)
            junk_reasons = classify_chunk(content, meta)
            src = meta.get("source_document", "")

            ci = {
                "source_document": src,
                "theme": meta.get("theme"),
                "sub_theme": meta.get("sub_theme"),
                "url": meta.get("url", ""),
                "page_title": meta.get("page_title", ""),
                "fiabilite": meta.get("fiabilite"),
                "content_preview": (content[:150] + "...") if len(content) > 150 else content,
                "content_length": len(content),
                "junk_reasons": junk_reasons,
            }

            if "profession_de_foi" in src or "election_manifesto" in src:
                manifesto.append(ci)
            else:
                website.append(ci)

            if junk_reasons:
                junk.append(ci)
            else:
                good.append(ci)

        # Themes
        themes = defaultdict(int)
        for c in chunks:
            t = _get_meta(c).get("theme") or "unclassified"
            themes[t] += 1

        # Sources
        sources = defaultdict(int)
        for c in chunks:
            s = _get_meta(c).get("source_document", "unknown")
            sources[s] += 1

        # URLs in chunks
        urls = set()
        for c in chunks:
            u = _get_meta(c).get("url")
            if u:
                urls.add(u)

        drive = drive_results.get(cid)

        candidate_stats[cid] = {
            "chunks": chunks,
            "manifesto": manifesto,
            "website": website,
            "junk": junk,
            "good": good,
            "themes": dict(themes),
            "sources": dict(sources),
            "urls": urls,
            "drive": drive,
        }

    # ═══════════════════════════════════════════════════════════════════════
    # CANDIDATE SUB-TABLE
    # ═══════════════════════════════════════════════════════════════════════

    total_manifesto = total_website = total_junk = total_good = 0

    # Header
    print(f"  {'─'*78}")
    print(f"  {'CANDIDATE SUB-TABLE':^78}")
    print(f"  {'─'*78}")
    print(f"  {'#':<3} {'ID':<16} {'Name':<22} {'Party':<18} {'Chunks':>6}")
    print(f"  {'─'*78}")

    for idx, (cid, info) in enumerate(sorted(candidate_map.items()), 1):
        stats = candidate_stats[cid]
        n_man = len(stats["manifesto"])
        n_web = len(stats["website"])
        n_good = len(stats["good"])
        n_junk = len(stats["junk"])
        n_total = len(stats["chunks"])

        total_manifesto += n_man
        total_website += n_web
        total_junk += n_junk
        total_good += n_good

        # Row 1: basic info
        name_trunc = info["name"][:21]
        party_trunc = info["party_label"][:17]
        print(f"  {idx:<3} {cid:<16} {name_trunc:<22} {party_trunc:<18} {n_total:>6}")

        # Row 2: coverage status
        has_web = "✓" if info["website_url"] else "✗"
        has_man = "✓" if info["has_manifesto"] else "✗"
        has_scr = "✓" if info["has_scraped"] else "✗"
        is_tete = "★" if info["is_tete_de_liste"] else " "
        print(f"      {is_tete} Coverage:  Website {has_web}  |  Manifesto {has_man}  |  Scraped {has_scr}")

        # Row 3: ingestion progress bar
        man_bar = _bar(n_man, max(n_man, 1))
        web_bar = _bar(n_web, max(n_web, 1)) if info["website_url"] else "░" * 20
        junk_pct = _pct(n_junk, n_total)
        print(f"      Ingestion: Manifesto [{man_bar}] {n_man:>3}  |  Website [{web_bar}] {n_web:>3}  |  Junk: {junk_pct} ({n_junk})")

        # Row 4: links
        links = []
        if info["website_url"]:
            links.append(f"🌐 Website:   {info['website_url']}")
        if info["manifesto_pdf_path"]:
            links.append(f"📄 PDF:       {info['manifesto_pdf_path']}")
        elif info["manifesto_url"]:
            links.append(f"📄 PDF:       {info['manifesto_url']}")
        drive = stats["drive"]
        if drive:
            n_files = len(drive.get("files", []))
            links.append(f"📁 Drive:     {drive['folder_name']} ({n_files} items)")
            links.append(f"              {drive['folder_url']}")
        elif drive is None and cid in drive_results:
            links.append("📁 Drive:     not found")
        # Deep links
        links.append(f"🔥 Firestore: {_firestore_doc_url('candidates', cid)}")
        links.append(f"🔍 Qdrant:    {_qdrant_scroll_url(CANDIDATES_COLLECTION, 'namespace', cid)}")
        for link in links:
            print(f"      {link}")

        # Row 5: themes
        if stats["themes"]:
            theme_str = ", ".join(f"{t}:{n}" for t, n in sorted(stats["themes"].items(), key=lambda x: -x[1]))
            print(f"      Themes: {theme_str}")

        # Row 6: sources
        if stats["sources"]:
            src_str = ", ".join(f"{s}:{n}" for s, n in sorted(stats["sources"].items(), key=lambda x: -x[1]))
            print(f"      Sources: {src_str}")

        # Row 7: chunk URLs
        if stats["urls"]:
            print(f"      Chunk URLs ({len(stats['urls'])}):")
            for u in sorted(stats["urls"])[:6]:
                print(f"        - {u}")
            if len(stats["urls"]) > 6:
                print(f"        ... and {len(stats['urls']) - 6} more")

        # Row 8: junk details
        if stats["junk"]:
            print(f"      ⚠ Junk samples ({n_junk}):")
            for j in stats["junk"][:3]:
                reasons = ", ".join(j["junk_reasons"])
                preview = j["content_preview"][:70].replace("\n", " ")
                print(f"        [{reasons}] {preview}")
            if n_junk > 3:
                print(f"        ... and {n_junk - 3} more")

        print(f"  {'─'*78}")

    # Candidates in Firestore but not in Qdrant
    missing_in_qdrant = [cid for cid in candidate_map if cid not in chunks_by_ns or not chunks_by_ns[cid]]
    if missing_in_qdrant:
        print(f"\n  ⚠ NOT INDEXED ({len(missing_in_qdrant)} candidates with 0 chunks in Qdrant):")
        for cid in missing_in_qdrant:
            info = candidate_map[cid]
            has_web = "✓web" if info["website_url"] else "✗web"
            has_man = "✓manifesto" if info["has_manifesto"] else "✗manifesto"
            print(f"    {cid} {info['name']} ({info['party_label']}) — {has_web} {has_man}")

    # Orphan namespaces (in Qdrant but not Firestore)
    orphans = set(chunks_by_ns.keys()) - set(candidate_map.keys())
    if orphans:
        print(f"\n  ⚠ ORPHAN NAMESPACES ({len(orphans)} in Qdrant but not in Firestore):")
        for ns in sorted(orphans)[:5]:
            print(f"    {ns} ({len(chunks_by_ns[ns])} chunks)")

    # ═══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════

    total_chunks = len(all_chunks)
    n_with_website = sum(1 for c in candidate_map.values() if c["website_url"])
    n_with_manifesto = sum(1 for c in candidate_map.values() if c["has_manifesto"])
    n_indexed = sum(1 for cid in candidate_map if cid in chunks_by_ns and chunks_by_ns[cid])
    n_with_drive = sum(1 for cid, d in drive_results.items() if d is not None)

    # Compute coverage & ingestion like the dashboard does
    n_total_cand = len(candidate_map)
    # Coverage: lists (assume present) + website ratio + manifesto ratio
    cov_web = n_with_website / n_total_cand * 100 if n_total_cand else 0
    cov_man = n_with_manifesto / n_total_cand * 100 if n_total_cand else 0
    # Ingestion: scraped ratio + indexed ratio (relative to hasWebsite)
    n_scraped = sum(1 for c in candidate_map.values() if c["has_scraped"])
    ing_scraped = n_scraped / n_with_website * 100 if n_with_website else 0
    ing_indexed = n_indexed / n_with_website * 100 if n_with_website else 0
    # Fixed ingestion: should also consider manifesto indexing
    ing_manifesto_indexed = sum(1 for cid in candidate_map if any(
        "profession_de_foi" in _get_meta(c).get("source_document", "")
        for c in chunks_by_ns.get(cid, [])
    ))
    ing_manifesto = ing_manifesto_indexed / n_total_cand * 100 if n_total_cand else 0

    print(f"\n{'='*80}")
    print(f"  SUMMARY: Commune {COMMUNE_CODE}")
    print(f"{'='*80}")
    print(f"  Candidates:          {n_total_cand}")
    print(f"  With website:        {n_with_website} ({cov_web:.0f}%)")
    print(f"  With manifesto:      {n_with_manifesto} ({cov_man:.0f}%)")
    print(f"  With Drive folder:   {n_with_drive}")
    print()
    print(f"  Total chunks:        {total_chunks}")
    print(f"  Manifesto chunks:    {total_manifesto}")
    print(f"  Website chunks:      {total_website}")
    print(f"  Good chunks:         {total_good}")
    junk_pct = total_junk * 100 // max(total_chunks, 1)
    print(f"  Junk chunks:         {total_junk} ({junk_pct}%)")
    print()
    print(f"  COVERAGE (dashboard):")
    print(f"    Candidates with website:    {n_with_website}/{n_total_cand} = {cov_web:.0f}%")
    print(f"    Candidates with manifesto:  {n_with_manifesto}/{n_total_cand} = {cov_man:.0f}%")
    print()
    print(f"  INGESTION (dashboard — current formula, website-only):")
    print(f"    Scraped:    {n_scraped}/{n_with_website} = {ing_scraped:.0f}%  (of candidates WITH website)")
    print(f"    Indexed:    {n_indexed}/{n_with_website} = {ing_indexed:.0f}%  (of candidates WITH website)")
    if n_with_website == 0:
        print(f"    → 0% because no candidates have a website URL!")
    print()
    print(f"  INGESTION (proposed fix, includes manifesto):")
    print(f"    Manifesto indexed:  {ing_manifesto_indexed}/{n_total_cand} = {ing_manifesto:.0f}%")
    print(f"    Website indexed:    {n_indexed}/{n_with_website if n_with_website else n_total_cand} = {ing_indexed:.0f}%" if n_with_website else f"    Website indexed:    —  (no websites)")
    combined = (ing_manifesto + (ing_indexed if n_with_website else 0)) / (2 if n_with_website else 1)
    print(f"    Combined score:     {combined:.0f}%")
    print()


if __name__ == "__main__":
    main()
