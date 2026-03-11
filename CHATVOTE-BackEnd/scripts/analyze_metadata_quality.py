#!/usr/bin/env python3
"""
Qdrant metadata quality analyzer.

Scrolls all points across all collections, analyzes field coverage,
value distributions, cross-references Firestore, and reports quality issues.

Exit code 0 if overall quality > 80%, 1 otherwise.

Usage:
    python scripts/analyze_metadata_quality.py [--env dev|prod]
"""

import argparse
import os
import sys
from collections import Counter, defaultdict
from typing import Any

# Must be set BEFORE importing firebase_admin
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")

from qdrant_client import QdrantClient

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")

COLLECTION_TEMPLATES = [
    "all_parties_{env}",
    "candidates_websites_{env}",
    "justified_voting_behavior_{env}",
    "parliamentary_questions_{env}",
]

# Fields that every chunk MUST have (non-null, non-empty)
CRITICAL_FIELDS = ["namespace", "source_document"]

# Fields that should ideally be present
IMPORTANT_FIELDS = ["url", "theme", "fiabilite", "page_type"]

# Categorical fields whose value distributions are interesting
CATEGORICAL_FIELDS = ["source_document", "page_type", "theme", "fiabilite"]

# Minimum chunk content length to not flag as "too short"
MIN_CONTENT_LENGTH = 20

# Quality target
QUALITY_TARGET_PCT = 80.0

SCROLL_BATCH = 256  # points per scroll page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_pct(num: int, denom: int) -> str:
    if denom == 0:
        return "N/A"
    pct = 100.0 * num / denom
    if pct >= 90:
        icon = "✅"
    elif pct >= 70:
        icon = "⚠️ "
    else:
        icon = "❌"
    return f"{icon} {pct:5.1f}% ({num}/{denom})"


def _extract_metadata(payload: dict) -> dict:
    """Payload may store metadata flat or nested under 'metadata' key."""
    if "metadata" in payload and isinstance(payload["metadata"], dict):
        return payload["metadata"]
    return payload


def _field_value(meta: dict, field: str) -> Any:
    """Return field value; treat empty string / empty list as missing."""
    v = meta.get(field)
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    if isinstance(v, list) and len(v) == 0:
        return None
    return v


def _is_present(meta: dict, field: str) -> bool:
    return _field_value(meta, field) is not None


# ---------------------------------------------------------------------------
# Qdrant scroll — returns all points
# ---------------------------------------------------------------------------

def scroll_all(client: QdrantClient, collection: str) -> tuple[list[dict], list[str], list]:
    """Scroll through all points in a collection, return list of payloads."""
    payloads: list[dict] = []
    contents: list[str] = []
    ids: list[Any] = []
    offset = None

    while True:
        results, next_offset = client.scroll(
            collection_name=collection,
            limit=SCROLL_BATCH,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            break
        for point in results:
            payloads.append(point.payload or {})
            contents.append((point.payload or {}).get("page_content", ""))
            ids.append(point.id)
        if next_offset is None:
            break
        offset = next_offset

    return payloads, contents, ids


# ---------------------------------------------------------------------------
# Firestore cross-reference
# ---------------------------------------------------------------------------

def load_firestore_ids() -> tuple[set[str], set[str]]:
    """Return (candidate_ids, party_ids) sets from Firestore."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.ApplicationDefault())

        db = firestore.client()

        candidate_ids = {doc.id for doc in db.collection("candidates").stream()}
        party_ids = {doc.id for doc in db.collection("parties").stream()}
        return candidate_ids, party_ids

    except Exception as exc:
        print(f"  ⚠️  Could not connect to Firestore: {exc}")
        return set(), set()


# ---------------------------------------------------------------------------
# Per-collection analysis
# ---------------------------------------------------------------------------

def analyze_collection(
    client: QdrantClient,
    collection: str,
    fs_candidate_ids: set[str],
    fs_party_ids: set[str],
) -> dict:
    """Analyze one collection. Returns a result dict."""

    print(f"\n  📦 Scrolling {collection} …", end="", flush=True)

    try:
        payloads, contents, point_ids = scroll_all(client, collection)
    except Exception as exc:
        print(f" ❌ ERROR: {exc}")
        return {"error": str(exc), "collection": collection, "total": 0}

    total = len(payloads)
    print(f" {total} points")

    if total == 0:
        return {"collection": collection, "total": 0, "empty": True}

    # --- Extract metadata dicts -----------------------------------------
    metas = [_extract_metadata(p) for p in payloads]

    # --- Unique namespaces -----------------------------------------------
    namespaces: set[str] = set()
    for m in metas:
        ns = _field_value(m, "namespace")
        if ns:
            namespaces.add(str(ns))

    # --- Field coverage --------------------------------------------------
    all_fields = set()
    for m in metas:
        all_fields.update(m.keys())
    # Remove structural keys that aren't metadata fields
    all_fields.discard("page_content")

    coverage: dict[str, int] = {}
    for field in sorted(all_fields):
        coverage[field] = sum(1 for m in metas if _is_present(m, field))

    # --- Categorical distributions --------------------------------------
    distributions: dict[str, Counter] = {}
    for field in CATEGORICAL_FIELDS:
        c: Counter = Counter()
        for m in metas:
            v = _field_value(m, field)
            if v is not None:
                c[str(v)] += 1
            else:
                c["<missing>"] += 1
        distributions[field] = c

    # --- Content quality ------------------------------------------------
    short_chunks = sum(
        1 for c in contents if len((c or "").strip()) < MIN_CONTENT_LENGTH
    )
    content_lengths = [len((c or "").strip()) for c in contents]
    avg_len = sum(content_lengths) / total if total else 0
    min_len = min(content_lengths) if content_lengths else 0
    max_len = max(content_lengths) if content_lengths else 0

    # --- Missing critical fields ----------------------------------------
    missing_critical: dict[str, int] = {}
    for field in CRITICAL_FIELDS:
        count = sum(1 for m in metas if not _is_present(m, field))
        if count:
            missing_critical[field] = count

    # --- Missing important fields ----------------------------------------
    missing_important: dict[str, int] = {}
    for field in IMPORTANT_FIELDS:
        count = sum(1 for m in metas if not _is_present(m, field))
        if count:
            missing_important[field] = count

    # --- Duplicate detection (namespace + chunk_index) ------------------
    seen: Counter = Counter()
    for m in metas:
        ns = _field_value(m, "namespace") or ""
        ci = _field_value(m, "chunk_index")
        key = f"{ns}:{ci}"
        seen[key] += 1
    duplicates = sum(v - 1 for v in seen.values() if v > 1)

    # --- Orphaned IDs --------------------------------------------------
    orphaned_candidates: set[str] = set()
    orphaned_parties: set[str] = set()

    if fs_candidate_ids or fs_party_ids:
        for m in metas:
            for cid in (_field_value(m, "candidate_ids") or []):
                if fs_candidate_ids and str(cid) not in fs_candidate_ids:
                    orphaned_candidates.add(str(cid))
            for pid in (_field_value(m, "party_ids") or []):
                if fs_party_ids and str(pid) not in fs_party_ids:
                    orphaned_parties.add(str(pid))

    # --- Quality score (per chunk) -------------------------------------
    # A chunk passes if: has all critical fields, content >= MIN_CONTENT_LENGTH
    passing = 0
    for m, content in zip(metas, contents):
        ok = all(_is_present(m, f) for f in CRITICAL_FIELDS)
        ok = ok and len((content or "").strip()) >= MIN_CONTENT_LENGTH
        if ok:
            passing += 1

    return {
        "collection": collection,
        "total": total,
        "namespaces": namespaces,
        "coverage": coverage,
        "distributions": distributions,
        "short_chunks": short_chunks,
        "avg_len": avg_len,
        "min_len": min_len,
        "max_len": max_len,
        "missing_critical": missing_critical,
        "missing_important": missing_important,
        "duplicates": duplicates,
        "orphaned_candidates": orphaned_candidates,
        "orphaned_parties": orphaned_parties,
        "passing": passing,
    }


# ---------------------------------------------------------------------------
# Report printing
# ---------------------------------------------------------------------------

def print_separator(char: str = "─", width: int = 72) -> None:
    print(char * width)


def print_header(title: str) -> None:
    print()
    print_separator("═")
    print(f"  {title}")
    print_separator("═")


def print_section(title: str) -> None:
    print()
    print_separator()
    print(f"  {title}")
    print_separator()


def print_collection_summary(results: list[dict]) -> None:
    print_header("📊  PER-COLLECTION SUMMARY")
    fmt = "  {:<40}  {:>8}  {:>12}"
    print(fmt.format("Collection", "Chunks", "Namespaces"))
    print_separator()
    total_chunks = 0
    for r in results:
        if r.get("error"):
            print(f"  {r['collection']:<40}  ❌ ERROR: {r['error']}")
            continue
        if r.get("empty"):
            print(f"  {r['collection']:<40}  (empty)")
            continue
        ns_count = len(r.get("namespaces", set()))
        chunks = r["total"]
        total_chunks += chunks
        print(fmt.format(r["collection"], chunks, ns_count))
    print_separator()
    print(f"  {'TOTAL':<40}  {total_chunks:>8}")


def print_field_coverage(results: list[dict]) -> None:
    print_header("📋  FIELD COVERAGE MATRIX")

    # Collect all fields across all collections
    all_fields: set[str] = set()
    for r in results:
        if r.get("error") or r.get("empty"):
            continue
        all_fields.update(r.get("coverage", {}).keys())

    cols = [r["collection"].replace("_dev", "").replace("_prod", "") for r in results
            if not r.get("error") and not r.get("empty")]

    col_width = 16
    label_width = 32
    header = f"  {'Field':<{label_width}}" + "".join(f"  {c:<{col_width}}" for c in cols)
    print(header)
    print_separator()

    for field in sorted(all_fields):
        row = f"  {field:<{label_width}}"
        for r in results:
            if r.get("error") or r.get("empty"):
                continue
            cov = r["coverage"].get(field, 0)
            total = r["total"]
            pct = 100.0 * cov / total if total else 0
            if pct >= 90:
                cell = f"✅{pct:4.0f}%"
            elif pct >= 70:
                cell = f"⚠️ {pct:3.0f}%"
            elif pct == 0:
                cell = "➖ 0%  "
            else:
                cell = f"❌{pct:4.0f}%"
            row += f"  {cell:<{col_width}}"
        print(row)


def print_distributions(results: list[dict]) -> None:
    print_header("📈  VALUE DISTRIBUTIONS FOR KEY FIELDS")

    for r in results:
        if r.get("error") or r.get("empty") or r["total"] == 0:
            continue
        coll_short = r["collection"]
        print(f"\n  🗂  {coll_short}  ({r['total']} chunks)")

        for field in CATEGORICAL_FIELDS:
            dist = r.get("distributions", {}).get(field)
            if not dist:
                continue
            total = r["total"]
            print(f"\n    📌 {field}:")
            for value, count in dist.most_common(15):
                bar_len = int(30 * count / total)
                bar = "█" * bar_len
                pct = 100.0 * count / total
                print(f"       {str(value):<35}  {bar:<30}  {pct:5.1f}%  ({count})")
            if len(dist) > 15:
                print(f"       … {len(dist) - 15} more values")


def print_orphaned_ids(results: list[dict], fs_available: bool) -> None:
    print_header("🔗  ORPHANED IDs (Qdrant → Firestore cross-reference)")

    if not fs_available:
        print("  ⚠️  Firestore unavailable — skipping orphan checks")
        return

    any_orphans = False
    for r in results:
        if r.get("error") or r.get("empty"):
            continue
        oc = r.get("orphaned_candidates", set())
        op = r.get("orphaned_parties", set())
        if oc or op:
            any_orphans = True
            print(f"\n  🗂  {r['collection']}")
            if oc:
                print(f"    ❌ Orphaned candidate_ids ({len(oc)}):")
                for cid in sorted(oc)[:20]:
                    print(f"       • {cid}")
                if len(oc) > 20:
                    print(f"       … {len(oc) - 20} more")
            if op:
                print(f"    ❌ Orphaned party_ids ({len(op)}):")
                for pid in sorted(op)[:20]:
                    print(f"       • {pid}")
                if len(op) > 20:
                    print(f"       … {len(op) - 20} more")

    if not any_orphans:
        print("  ✅  No orphaned IDs found — all references resolve in Firestore")


def print_quality_issues(results: list[dict]) -> None:
    print_header("🔍  QUALITY ISSUES REPORT")

    for r in results:
        if r.get("error") or r.get("empty"):
            continue

        issues: list[str] = []
        total = r["total"]

        # Critical missing fields
        for field, count in r.get("missing_critical", {}).items():
            issues.append(f"❌ Missing '{field}': {count} chunks ({100*count/total:.1f}%)")

        # Important missing fields
        for field, count in r.get("missing_important", {}).items():
            issues.append(f"⚠️  Missing '{field}': {count} chunks ({100*count/total:.1f}%)")

        # Short content
        sc = r["short_chunks"]
        if sc:
            issues.append(
                f"⚠️  Content too short (<{MIN_CONTENT_LENGTH} chars): "
                f"{sc} chunks ({100*sc/total:.1f}%)"
            )

        # Duplicates
        dups = r["duplicates"]
        if dups:
            issues.append(f"⚠️  Duplicate (namespace+chunk_index) entries: {dups}")

        if issues:
            print(f"\n  🗂  {r['collection']}  ({total} chunks)")
            for iss in issues:
                print(f"    {iss}")
        else:
            print(f"\n  ✅  {r['collection']}  — no issues found")


def print_overall_quality(results: list[dict]) -> float:
    print_header("🏆  OVERALL QUALITY SCORE")

    total_chunks = 0
    total_passing = 0

    for r in results:
        if r.get("error") or r.get("empty"):
            continue
        total_chunks += r["total"]
        total_passing += r.get("passing", 0)

    if total_chunks == 0:
        print("  ⚠️  No data to score")
        return 0.0

    overall_pct = 100.0 * total_passing / total_chunks

    print(f"\n  Total chunks analyzed : {total_chunks}")
    print(f"  Passing quality checks: {total_passing}")
    print(f"  Quality score         : {overall_pct:.1f}%  (target: {QUALITY_TARGET_PCT:.0f}%)")
    print()

    if overall_pct >= QUALITY_TARGET_PCT:
        print(f"  ✅  PASS — quality {overall_pct:.1f}% ≥ {QUALITY_TARGET_PCT:.0f}% target")
    else:
        print(f"  ❌  FAIL — quality {overall_pct:.1f}% < {QUALITY_TARGET_PCT:.0f}% target")

    # Per-collection breakdown
    print()
    fmt = "  {:<44}  {:>8}  {:>8}  {:>8}"
    print(fmt.format("Collection", "Total", "Passing", "Score"))
    print_separator()
    for r in results:
        if r.get("error"):
            print(f"  {r['collection']:<44}  ❌ error")
            continue
        if r.get("empty"):
            print(f"  {r['collection']:<44}  (empty)")
            continue
        t = r["total"]
        p = r.get("passing", 0)
        pct = 100.0 * p / t if t else 0
        icon = "✅" if pct >= QUALITY_TARGET_PCT else "❌"
        print(fmt.format(r["collection"], t, p, f"{icon} {pct:.1f}%"))

    return overall_pct


def print_chunk_lengths(results: list[dict]) -> None:
    print_header("📏  CHUNK LENGTH STATISTICS")

    fmt = "  {:<44}  {:>8}  {:>8}  {:>8}"
    print(fmt.format("Collection", "Avg", "Min", "Max"))
    print_separator()
    for r in results:
        if r.get("error") or r.get("empty"):
            continue
        print(fmt.format(
            r["collection"],
            f"{r['avg_len']:.0f}",
            r["min_len"],
            r["max_len"],
        ))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Qdrant metadata quality analyzer")
    parser.add_argument(
        "--env",
        default=os.environ.get("ENV", "dev"),
        choices=["dev", "prod"],
        help="Environment suffix for collection names (default: dev)",
    )
    parser.add_argument(
        "--qdrant-url",
        default=QDRANT_URL,
        help=f"Qdrant URL (default: {QDRANT_URL})",
    )
    args = parser.parse_args()

    collections = [tpl.format(env=args.env) for tpl in COLLECTION_TEMPLATES]

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║          🔬  CHATVOTE QDRANT METADATA QUALITY ANALYZER              ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")
    print(f"\n  Qdrant  : {args.qdrant_url}")
    print(f"  Env     : {args.env}")
    print(f"  Firestore emulator: {os.environ.get('FIRESTORE_EMULATOR_HOST', 'not set')}")
    print(f"  Collections ({len(collections)}):")
    for c in collections:
        print(f"    • {c}")

    # --- Connect to Qdrant -----------------------------------------------
    print("\n🔌 Connecting to Qdrant …")
    try:
        client = QdrantClient(url=args.qdrant_url, prefer_grpc=False)
        existing = {c.name for c in client.get_collections().collections}
        print(f"  ✅ Connected — {len(existing)} collections found")
    except Exception as exc:
        print(f"  ❌ Cannot connect to Qdrant at {args.qdrant_url}: {exc}")
        return 1

    # Filter to collections that exist
    present_collections = [c for c in collections if c in existing]
    missing_collections = [c for c in collections if c not in existing]

    if missing_collections:
        print(f"\n  ⚠️  Collections not found in Qdrant (will be skipped):")
        for c in missing_collections:
            print(f"    • {c}")

    if not present_collections:
        print("\n  ❌ No target collections exist — nothing to analyze")
        return 1

    # --- Load Firestore IDs -----------------------------------------------
    print("\n🔥 Loading Firestore entity IDs for cross-reference …")
    fs_candidate_ids, fs_party_ids = load_firestore_ids()
    fs_available = bool(fs_candidate_ids or fs_party_ids)
    if fs_available:
        print(f"  ✅ Loaded {len(fs_candidate_ids)} candidates, {len(fs_party_ids)} parties")
    else:
        print("  ⚠️  Firestore returned no data — orphan checks will be skipped")

    # --- Analyze each collection -----------------------------------------
    print("\n🔍 Analyzing collections …")
    results: list[dict] = []
    for collection in collections:
        if collection not in existing:
            results.append({
                "collection": collection,
                "total": 0,
                "empty": True,
                "error": "collection does not exist",
            })
            continue
        r = analyze_collection(client, collection, fs_candidate_ids, fs_party_ids)
        results.append(r)

    # --- Print report -------------------------------------------------------
    print_collection_summary(results)
    print_field_coverage(results)
    print_distributions(results)
    print_orphaned_ids(results, fs_available)
    print_quality_issues(results)
    print_chunk_lengths(results)
    overall_pct = print_overall_quality(results)

    print()
    print_separator("═")
    print()

    return 0 if overall_pct >= QUALITY_TARGET_PCT else 1


if __name__ == "__main__":
    sys.exit(main())
