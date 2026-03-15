#!/usr/bin/env python3
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Production data audit for 5 municipalities.
Checks Firebase candidates + Qdrant indexed chunks + recent chat sessions.
Schema-corrected version: municipalities use 'nom' field, doc.id == code.
"""

import os
import sys
import json
from datetime import datetime, timezone, timedelta
from collections import defaultdict

os.environ["ENV"] = "prod"
os.chdir("/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd")
sys.path.insert(0, "/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd")

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny

QDRANT_URL = "http://212.47.245.238:6333"
QDRANT_API_KEY = "7384d5cc296a254996640081df3a08f824a2f999bb1fb98d91929d811ddc22cb"
COLL_CANDIDATES = "candidates_websites_prod"
COLL_PARTIES = "all_parties_prod"

qdrant = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
    prefer_grpc=False,
    https=False,
    timeout=60,
    check_compatibility=False,
)

import firebase_admin
from firebase_admin import firestore, credentials

if not firebase_admin._apps:
    cred = credentials.Certificate(
        "/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd/chat-vote-firebase-adminsdk.json"
    )
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ── Confirmed municipality codes (from prior discovery step) ──
# Mérignac 33281 = Gironde (Bordeaux suburb, ~70k pop), 16216 = Charente, 17229 = Charente-Maritime
TARGETS: dict[str, list[str]] = {
    "Charleville-Mézières": ["08105"],
    "Chartres":             ["28085"],
    "Colomiers":            ["31149"],
    "Bègles":               ["33039"],
    "Mérignac":             ["33281"],   # primary; will also check 16216, 17229
}
MERIGNAC_ALL_CODES = ["16216", "17229", "33281"]

# ────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────

def get_all_candidates_for_code(code: str) -> list[dict]:
    docs = db.collection("candidates").where("municipality_code", "==", code).stream()
    result = []
    for doc in docs:
        d = doc.to_dict()
        d["_doc_id"] = doc.id
        result.append(d)
    return result


def count_qdrant_for_candidate(candidate_id: str) -> dict:
    """Scroll all Qdrant points for a candidate_id. Returns breakdown by source type + themes."""
    result = {
        "total": 0,
        "profession_de_foi": 0,
        "website": 0,
        "other": 0,
        "themes": set(),
        "null_theme_chunks": 0,
        "sample_meta": None,
        "raw_sources": set(),
    }
    try:
        offset = None
        while True:
            points, next_offset = qdrant.scroll(
                collection_name=COLL_CANDIDATES,
                scroll_filter=Filter(
                    must=[FieldCondition(
                        key="metadata.candidate_ids",
                        match=MatchAny(any=[candidate_id]),
                    )]
                ),
                limit=200,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                break
            for pt in points:
                result["total"] += 1
                meta = (pt.payload or {}).get("metadata", {}) or {}
                if result["sample_meta"] is None:
                    result["sample_meta"] = {k: meta.get(k) for k in
                        ["source_document", "page_type", "source_type", "doc_type",
                         "theme", "municipality_code", "candidate_ids", "namespace"]}

                source = (
                    meta.get("source_document") or meta.get("page_type") or
                    meta.get("source_type") or meta.get("doc_type") or ""
                ).lower()
                result["raw_sources"].add(source or "(empty)")

                if any(k in source for k in ["profession", "foi", "manifesto", "pdf"]):
                    result["profession_de_foi"] += 1
                elif any(k in source for k in ["website", "web", "scraped", "crawl", "scrape"]):
                    result["website"] += 1
                else:
                    result["other"] += 1

                theme = meta.get("theme") or meta.get("topic") or ""
                if theme:
                    result["themes"].add(theme)
                else:
                    result["null_theme_chunks"] += 1

            if next_offset is None:
                break
            offset = next_offset
    except Exception as e:
        result["error"] = str(e)

    result["themes"] = sorted(result["themes"])
    result["raw_sources"] = sorted(result["raw_sources"])
    return result


def count_qdrant_by_muni_code(code: str) -> int:
    try:
        r = qdrant.count(
            collection_name=COLL_CANDIDATES,
            count_filter=Filter(must=[FieldCondition(key="metadata.municipality_code", match=MatchValue(value=code))]),
            exact=True,
        )
        return r.count
    except Exception as e:
        return -1


def get_party_manifesto_counts(party_ids: list[str]) -> dict:
    result = {}
    for pid in party_ids:
        # try namespace field first, then party_id field
        for field in ["metadata.namespace", "metadata.party_id", "metadata.party_ids"]:
            try:
                cr = qdrant.count(
                    collection_name=COLL_PARTIES,
                    count_filter=Filter(must=[FieldCondition(key=field, match=MatchValue(value=pid))]),
                    exact=True,
                )
                if cr.count > 0:
                    result[pid] = {"count": cr.count, "field": field}
                    break
            except Exception:
                pass
        if pid not in result:
            result[pid] = {"count": 0, "field": "not_found"}
    return result


def get_recent_sessions(hours: int = 6) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    try:
        docs = db.collection("chat_sessions").where("created_at", ">=", cutoff).limit(1000).stream()
        result = []
        for doc in docs:
            d = doc.to_dict()
            d["_doc_id"] = doc.id
            result.append(d)
        return result
    except Exception as e:
        print(f"  WARN chat_sessions query failed: {e}")
        return []


# ────────────────────────────────────────────────────────────────
# STEP 1: Qdrant collection info
# ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("[STEP 1] Qdrant collection info")
print("=" * 70)

coll_info = qdrant.get_collection(COLL_CANDIDATES)
party_coll_info = qdrant.get_collection(COLL_PARTIES)
print(f"  {COLL_CANDIDATES}: {coll_info.points_count} total points")
print(f"  {COLL_PARTIES}:    {party_coll_info.points_count} total points")

# Sample one point to see what metadata fields actually look like
sample_pts, _ = qdrant.scroll(COLL_CANDIDATES, limit=1, with_payload=True, with_vectors=False)
if sample_pts:
    sample_meta = (sample_pts[0].payload or {}).get("metadata", {})
    print(f"\n  Sample metadata keys: {sorted(sample_meta.keys())}")
    print(f"  Sample metadata values: { {k: sample_meta.get(k) for k in ['source_document','page_type','source_type','doc_type','theme','municipality_code','candidate_id']} }")

# ────────────────────────────────────────────────────────────────
# STEP 2: Recent chat sessions
# ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("[STEP 2] Recent chat sessions (last 6h)")
print("=" * 70)

recent_sessions = get_recent_sessions(6)
print(f"  Total recent sessions: {len(recent_sessions)}")
if recent_sessions:
    for s in recent_sessions[:3]:
        print(f"    id={s['_doc_id']} party_ids={s.get('party_ids')} title={s.get('title','?')[:50]} created={s.get('created_at')}")

# Also check last 24h for broader context
recent_24h = get_recent_sessions(24)
print(f"  Total sessions last 24h: {len(recent_24h)}")

# ────────────────────────────────────────────────────────────────
# STEP 3: Per-municipality deep audit
# ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("[STEP 3] Per-municipality candidate + Qdrant audit")
print("=" * 70)

all_party_ids_seen: set[str] = set()
audit_results: dict[str, dict] = {}

for city, codes in TARGETS.items():
    # For Mérignac, also load 16216 + 17229 for completeness
    all_codes = MERIGNAC_ALL_CODES if city == "Mérignac" else codes
    primary_code = codes[0]

    print(f"\n  {'─'*60}")
    print(f"  {city}  |  primary code={primary_code}  |  all codes={all_codes}")
    print(f"  {'─'*60}")

    all_candidates: list[dict] = []
    candidates_by_code: dict[str, list] = {}
    for code in all_codes:
        cands = get_all_candidates_for_code(code)
        candidates_by_code[code] = cands
        all_candidates.extend(cands)
        print(f"    code={code}: {len(cands)} candidates")

    # Qdrant direct count per code
    qdrant_counts_by_code = {}
    for code in all_codes:
        n = count_qdrant_by_muni_code(code)
        qdrant_counts_by_code[code] = n
        print(f"    code={code}: Qdrant municipality_code filter -> {n} chunks")

    # Collect party IDs
    for c in all_candidates:
        pids = c.get("party_ids") or []
        if isinstance(pids, list):
            all_party_ids_seen.update(pids)

    # Per-candidate Qdrant drill-down
    candidate_audit: list[dict] = []
    for cand in all_candidates:
        cid = cand.get("candidate_id") or cand.get("_doc_id", "")
        name = f"{cand.get('first_name','')} {cand.get('last_name','')}".strip()
        position = cand.get("position", "") or ""
        party_ids = cand.get("party_ids") or []
        has_website = bool(cand.get("has_website"))
        has_manifesto = bool(cand.get("has_manifesto"))
        has_scraped = bool(cand.get("has_scraped"))
        scrape_chars = cand.get("scrape_chars") or 0
        nuance_label = cand.get("nuance_label") or cand.get("nuance_code") or ""
        list_label = cand.get("list_label") or ""
        muni_code = cand.get("municipality_code", "")

        qdata = count_qdrant_for_candidate(cid)

        flags = []
        if qdata["total"] == 0 and (has_website or has_manifesto):
            flags.append("ZERO_CHUNKS_BUT_HAS_DATA")
        elif qdata["total"] == 0 and not has_website and not has_manifesto:
            flags.append("ZERO_CHUNKS_NO_SOURCE")
        if 0 < qdata["total"] < 3:
            flags.append(f"FEW_CHUNKS({qdata['total']})")
        if qdata["total"] > 0 and len(qdata["themes"]) == 0:
            flags.append("NO_THEMES")
        if qdata.get("null_theme_chunks", 0) > 0 and qdata["total"] > 0:
            pct = 100 * qdata["null_theme_chunks"] // qdata["total"]
            if pct > 20:
                flags.append(f"NULL_THEME_{pct}pct")
        if has_scraped and qdata["website"] == 0 and qdata["total"] > 0:
            flags.append("SCRAPED_BUT_NO_WEB_CHUNKS")

        status = "OK " if qdata["total"] >= 3 else ("FEW" if qdata["total"] > 0 else "---")
        print(f"    [{status}] {name[:28]:<28} chunks={qdata['total']:>4} pdf={qdata['profession_de_foi']:>3} web={qdata['website']:>3} oth={qdata['other']:>3} themes={len(qdata['themes']):>2}  {', '.join(flags) if flags else ''}")

        candidate_audit.append({
            "candidate_id": cid,
            "name": name,
            "municipality_code": muni_code,
            "position": position,
            "party_ids": party_ids,
            "nuance_label": nuance_label,
            "list_label": list_label,
            "has_website": has_website,
            "has_manifesto": has_manifesto,
            "has_scraped": has_scraped,
            "scrape_chars": scrape_chars,
            "qdrant_total": qdata["total"],
            "qdrant_pdf": qdata["profession_de_foi"],
            "qdrant_web": qdata["website"],
            "qdrant_other": qdata["other"],
            "themes": qdata["themes"],
            "null_theme_chunks": qdata.get("null_theme_chunks", 0),
            "raw_sources": qdata.get("raw_sources", []),
            "sample_meta": qdata.get("sample_meta"),
            "flags": flags,
        })

    audit_results[city] = {
        "primary_code": primary_code,
        "all_codes": all_codes,
        "candidates": candidate_audit,
        "qdrant_counts_by_code": qdrant_counts_by_code,
        "recent_sessions_6h": 0,  # filled below
        "recent_sessions_24h": 0,
    }

# ────────────────────────────────────────────────────────────────
# STEP 4: Match recent sessions to municipalities via party_ids
# ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("[STEP 4] Cross-referencing recent sessions with municipalities")
print("=" * 70)

# Build a party_id -> city lookup from our audit data
party_to_city: dict[str, str] = {}
for city, r in audit_results.items():
    for cand in r["candidates"]:
        for pid in cand["party_ids"]:
            party_to_city.setdefault(pid, city)

# Also build municipality-level party set
city_parties: dict[str, set] = {city: set() for city in audit_results}
for city, r in audit_results.items():
    for cand in r["candidates"]:
        city_parties[city].update(cand["party_ids"])

# Count sessions that include any party_id from these municipalities
for city in audit_results:
    cp = city_parties[city]
    s6 = [s for s in recent_sessions if bool(set(s.get("party_ids") or []) & cp)]
    s24 = [s for s in recent_24h if bool(set(s.get("party_ids") or []) & cp)]
    audit_results[city]["recent_sessions_6h"] = len(s6)
    audit_results[city]["recent_sessions_24h"] = len(s24)
    if s6 or s24:
        print(f"  {city}: {len(s6)} sessions (6h), {len(s24)} sessions (24h)")
    else:
        print(f"  {city}: 0 sessions matched")

# ────────────────────────────────────────────────────────────────
# STEP 5: Party manifesto coverage
# ────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("[STEP 5] Party manifesto coverage in all_parties_prod")
print("=" * 70)

# Sample all_parties_prod to see actual metadata structure
party_pts, _ = qdrant.scroll(COLL_PARTIES, limit=3, with_payload=True, with_vectors=False)
for pt in party_pts:
    meta = (pt.payload or {}).get("metadata", {})
    print(f"  Sample party chunk meta: { {k: meta.get(k) for k in ['namespace','party_id','source','theme']} }")

party_manifesto_counts = get_party_manifesto_counts(sorted(all_party_ids_seen))
print(f"\n  Party IDs found across 5 municipalities: {len(all_party_ids_seen)}")
for pid, info in sorted(party_manifesto_counts.items()):
    status = "OK" if info["count"] > 0 else "MISSING"
    print(f"  [{status}] {pid:<35} {info['count']:>4} chunks  (field={info['field']})")

# ────────────────────────────────────────────────────────────────
# STEP 6: Print structured final report
# ────────────────────────────────────────────────────────────────
DIVIDER = "=" * 70
print("\n\n" + DIVIDER)
print("FINAL AUDIT REPORT — ChatVote Production Data Quality")
print(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
print(DIVIDER)

for city in TARGETS:
    r = audit_results[city]
    candidates = r["candidates"]
    n = len(candidates)
    zero  = [c for c in candidates if c["qdrant_total"] == 0]
    few   = [c for c in candidates if 0 < c["qdrant_total"] < 3]
    good  = [c for c in candidates if c["qdrant_total"] >= 3]
    flagged = [c for c in candidates if c["flags"]]
    total_chunks = sum(c["qdrant_total"] for c in candidates)
    all_themes = sorted(set(t for c in candidates for t in c["themes"]))

    qdrant_muni_total = qdrant_counts_by_code = r["qdrant_counts_by_code"]
    qdrant_primary = qdrant_counts_by_code.get(r["primary_code"], -1)

    print(f"\n{'─'*70}")
    print(f"  MUNICIPALITY : {city}")
    print(f"  PRIMARY CODE : {r['primary_code']}  (all codes checked: {r['all_codes']})")
    print(f"{'─'*70}")
    print(f"  Firebase candidates     : {n}")
    print(f"  Qdrant chunks (muni flt): {qdrant_primary}  |  sum-per-candidate: {total_chunks}")
    print(f"  Candidates OK  (≥3 chks): {len(good)}/{n}  ({100*len(good)//max(n,1)}%)")
    print(f"  Candidates FEW (1-2 chks): {len(few)}/{n}")
    print(f"  Candidates ZERO chunks  : {len(zero)}/{n}  ({100*len(zero)//max(n,1)}%)")
    print(f"  Recent sessions (6h)    : {r['recent_sessions_6h']}")
    print(f"  Recent sessions (24h)   : {r['recent_sessions_24h']}")
    print()
    print(f"  {'Candidate':<30} {'Position':<20} {'Nuance':<22} {'Chunks':>6} {'PDF':>4} {'Web':>4} {'Oth':>4} {'Thm':>4}")
    print(f"  {'-'*30} {'-'*20} {'-'*22} {'-'*6} {'-'*4} {'-'*4} {'-'*4} {'-'*4}")
    for c in sorted(candidates, key=lambda x: (-x["qdrant_total"], x["name"])):
        pos = (c["position"] or "—")[:18]
        nua = (c["nuance_label"] or "—")[:20]
        print(f"  {c['name'][:30]:<30} {pos:<20} {nua:<22} {c['qdrant_total']:>6} {c['qdrant_pdf']:>4} {c['qdrant_web']:>4} {c['qdrant_other']:>4} {len(c['themes']):>4}")
        if c["flags"]:
            print(f"    {'':>30} ^ FLAGS: {', '.join(c['flags'])}")

    print(f"\n  Themes covered ({len(all_themes)}): {', '.join(all_themes) if all_themes else 'NONE'}")

    if flagged:
        print(f"\n  [DATA QUALITY FLAGS] {len(flagged)} candidates have issues:")
        for c in flagged:
            print(f"    {c['name'][:35]:<35} → {', '.join(c['flags'])}")
        # Categorise
        zero_but_data = [c for c in flagged if "ZERO_CHUNKS_BUT_HAS_DATA" in c["flags"]]
        if zero_but_data:
            print(f"\n    *** {len(zero_but_data)} candidates have website/manifesto but ZERO indexed chunks — RAG will fail for these ***")
    else:
        print(f"\n  [DATA QUALITY] All candidates adequately indexed")

# ────────────────────────────────────────────────────────────────
# Summary statistics
# ────────────────────────────────────────────────────────────────
total_cands = sum(len(r["candidates"]) for r in audit_results.values())
total_zero  = sum(len([c for c in r["candidates"] if c["qdrant_total"] == 0]) for r in audit_results.values())
total_few   = sum(len([c for c in r["candidates"] if 0 < c["qdrant_total"] < 3]) for r in audit_results.values())
total_good  = sum(len([c for c in r["candidates"] if c["qdrant_total"] >= 3]) for r in audit_results.values())
total_zero_data = sum(
    len([c for c in r["candidates"] if c["qdrant_total"] == 0 and (c["has_website"] or c["has_manifesto"])])
    for r in audit_results.values()
)

print(f"\n{'='*70}")
print("SUMMARY STATISTICS")
print(f"{'='*70}")
print(f"  Total candidates audited  : {total_cands}")
print(f"  Well-indexed  (≥3 chunks) : {total_good}  ({100*total_good//max(total_cands,1)}%)")
print(f"  Few chunks    (1-2)       : {total_few}")
print(f"  Zero chunks               : {total_zero}  ({100*total_zero//max(total_cands,1)}%)")
print(f"  Zero + has data (critical): {total_zero_data}  — these candidates return no RAG context")
print(f"  Party manifesto IDs found : {len(all_party_ids_seen)}")
print(f"  Manifestos indexed >0     : {sum(1 for v in party_manifesto_counts.values() if v['count']>0)}/{len(party_manifesto_counts)}")

# ────────────────────────────────────────────────────────────────
# Save markdown report
# ────────────────────────────────────────────────────────────────
timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
report_path = f"/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd/.omc/scientist/reports/{timestamp}_municipality_audit.md"

lines = []
lines.append("# ChatVote Production Data Audit — 5 Municipalities\n\n")
lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  \n")
lines.append(f"**Scope:** Charleville-Mézières, Chartres, Colomiers, Bègles, Mérignac  \n\n")

lines.append("## [OBJECTIVE]\n\n")
lines.append("Verify production RAG data quality for 5 municipalities whose chat sessions were opened ~5 hours ago. "
             "For each municipality: Firebase candidate records, Qdrant indexed chunks (by source type + theme), "
             "party manifesto coverage, and recent chat session activity.\n\n")

lines.append("## [DATA]\n\n")
lines.append(f"- `{COLL_CANDIDATES}`: **{coll_info.points_count}** total vector points\n")
lines.append(f"- `{COLL_PARTIES}`: **{party_coll_info.points_count}** total vector points\n")
lines.append(f"- Firebase candidates total: **{len([c for r in audit_results.values() for c in r['candidates']])}** (across 5 municipalities)\n")
lines.append(f"- Recent chat sessions scanned: **{len(recent_sessions)}** (6h), **{len(recent_24h)}** (24h)\n\n")

for city in TARGETS:
    r = audit_results[city]
    candidates = r["candidates"]
    n = len(candidates)
    zero  = [c for c in candidates if c["qdrant_total"] == 0]
    few   = [c for c in candidates if 0 < c["qdrant_total"] < 3]
    good  = [c for c in candidates if c["qdrant_total"] >= 3]
    flagged = [c for c in candidates if c["flags"]]
    all_themes = sorted(set(t for c in candidates for t in c["themes"]))
    qdrant_primary = r["qdrant_counts_by_code"].get(r["primary_code"], -1)
    total_chunks_city = sum(c["qdrant_total"] for c in candidates)

    lines.append(f"## {city} (code: `{r['primary_code']}`)\n\n")
    lines.append(f"### [FINDING]\n\n")
    lines.append(f"- Firebase candidates: **{n}**\n")
    lines.append(f"- Qdrant chunks (municipality_code filter): **{qdrant_primary}**  |  sum-per-candidate: **{total_chunks_city}**\n")
    lines.append(f"- Well-indexed candidates (≥3 chunks): **{len(good)}/{n}** ({100*len(good)//max(n,1)}%)\n")
    lines.append(f"- Zero-chunk candidates: **{len(zero)}/{n}**\n")
    lines.append(f"- Recent chat sessions (6h / 24h): {r['recent_sessions_6h']} / {r['recent_sessions_24h']}\n\n")
    lines.append(f"[STAT:n] n={n} candidates  \n")
    lines.append(f"[STAT:effect_size] Indexed rate = {100*len(good)//max(n,1)}% well-indexed ({len(good)}/{n})  \n\n")

    lines.append("| Candidate | Position | Nuance | Chunks | PDF | Web | Other | Themes | Flags |\n")
    lines.append("|-----------|----------|--------|--------|-----|-----|-------|--------|-------|\n")
    for c in sorted(candidates, key=lambda x: (-x["qdrant_total"], x["name"])):
        flag_str = ", ".join(c["flags"]) if c["flags"] else "—"
        pos = (c["position"] or "—")[:20]
        nua = (c["nuance_label"] or "—")[:20]
        lines.append(f"| {c['name'][:30]} | {pos} | {nua} | {c['qdrant_total']} | {c['qdrant_pdf']} | {c['qdrant_web']} | {c['qdrant_other']} | {len(c['themes'])} | {flag_str} |\n")

    lines.append(f"\n**Themes covered ({len(all_themes)}):** {', '.join(all_themes) if all_themes else 'NONE'}  \n\n")

    if flagged:
        lines.append("### [LIMITATION]\n\n")
        zero_data = [c for c in flagged if "ZERO_CHUNKS_BUT_HAS_DATA" in c["flags"]]
        if zero_data:
            lines.append(f"**CRITICAL:** {len(zero_data)} candidates have website/manifesto data but zero indexed chunks — "
                         "RAG will return no context for questions about these candidates.\n\n")
        for c in flagged:
            lines.append(f"- `{c['name']}` ({c['municipality_code']}): {', '.join(c['flags'])}\n")
        lines.append("\n")

lines.append("## Party Manifesto Coverage\n\n")
lines.append("| Party ID | Chunks in all_parties_prod | Status |\n")
lines.append("|----------|---------------------------|--------|\n")
for pid, info in sorted(party_manifesto_counts.items()):
    status = "OK" if info["count"] > 0 else "MISSING"
    lines.append(f"| `{pid}` | {info['count']} | {status} |\n")

lines.append(f"\n## Summary\n\n")
lines.append(f"[STAT:n] Total candidates audited: {total_cands}  \n")
lines.append(f"[STAT:effect_size] Well-indexed rate: {100*total_good//max(total_cands,1)}% ({total_good}/{total_cands})  \n")
lines.append(f"- Zero-chunk candidates: {total_zero} ({100*total_zero//max(total_cands,1)}%)  \n")
lines.append(f"- Critical (zero + has data): {total_zero_data}  \n")
lines.append(f"- Few-chunk (1-2): {total_few}  \n")
lines.append(f"- Recent chat sessions (6h across all 5 cities): {sum(r['recent_sessions_6h'] for r in audit_results.values())}  \n\n")
lines.append("### [LIMITATION]\n\n")
lines.append("- Qdrant `municipality_code` filter and per-candidate `candidate_id` filter may diverge if chunks were indexed without municipality_code metadata.\n")
lines.append("- Chat session matching uses party_ids overlap (no direct municipality_code in session docs); may undercount or misattribute.\n")
lines.append("- Party manifesto matching uses `metadata.namespace` field; parties not yet migrated may show 0.\n")
lines.append("- Mérignac: 3 French communes share this name; audit uses code 33281 (Gironde, ~70k pop) as primary.\n")

with open(report_path, "w") as f:
    f.writelines(lines)

print(f"\n\nReport saved to: {report_path}")
