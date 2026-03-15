#!/usr/bin/env python3
"""
Candidate ID Consistency Audit: Qdrant candidates_websites_prod vs Firebase Firestore
"""
import os
import sys
import json
import re
from collections import defaultdict, Counter
from pathlib import Path
from datetime import datetime

# ── Setup paths ──────────────────────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

REPORT_DIR = BACKEND_DIR / ".omc" / "scientist" / "reports"
FIGURES_DIR = BACKEND_DIR / ".omc" / "scientist" / "figures"
REPORT_DIR.mkdir(parents=True, exist_ok=True)
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ────────────────────────────────────────────────────────────────────
QDRANT_URL = "http://212.47.245.238:6333"
QDRANT_API_KEY = "7384d5cc296a254996640081df3a08f824a2f999bb1fb98d91929d811ddc22cb"
COLLECTION = "candidates_websites_prod"
FIREBASE_CREDS = str(BACKEND_DIR / "chat-vote-firebase-adminsdk.json")


# ── Step 1: Qdrant audit ──────────────────────────────────────────────────────
print("=" * 70)
print("STEP 1: Scrolling Qdrant collection:", COLLECTION)
print("=" * 70)

from qdrant_client import QdrantClient

qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, prefer_grpc=False, timeout=60)

# Confirm collection exists
info = qdrant.get_collection(COLLECTION)
total_points = info.points_count
print(f"Collection total points: {total_points:,}")

# Scroll all points, collecting only payload metadata (no vectors needed)
namespace_ids: set[str] = set()
candidate_ids_field: set[str] = set()

# Per-ID point counts
namespace_point_counts: Counter = Counter()
candidate_ids_point_counts: Counter = Counter()

# Drift tracking: namespace vs candidate_ids disagreements
drift_examples: list[dict] = []

points_processed = 0
offset = None
batch_size = 250

print("Scrolling points (this may take a while for 36K points)...")

while True:
    results, next_offset = qdrant.scroll(
        collection_name=COLLECTION,
        limit=batch_size,
        offset=offset,
        with_payload=["metadata.namespace", "metadata.candidate_ids"],
        with_vectors=False,
    )

    for point in results:
        points_processed += 1
        payload = point.payload or {}
        meta = payload.get("metadata", {})

        ns = meta.get("namespace")
        cids = meta.get("candidate_ids")

        # Normalise candidate_ids to a list
        if isinstance(cids, str):
            cids_list = [cids] if cids else []
        elif isinstance(cids, list):
            cids_list = [c for c in cids if c]
        else:
            cids_list = []

        # Track namespace IDs
        if ns:
            namespace_ids.add(ns)
            namespace_point_counts[ns] += 1

        # Track candidate_ids IDs
        for cid in cids_list:
            candidate_ids_field.add(cid)
            candidate_ids_point_counts[cid] += 1

        # Detect namespace vs candidate_ids drift
        # If both are present, namespace should match one of the candidate_ids
        if ns and cids_list and ns not in cids_list:
            drift_examples.append({
                "point_id": point.id,
                "namespace": ns,
                "candidate_ids": cids_list,
            })
        elif ns and not cids_list:
            # namespace set but candidate_ids empty — also a potential drift
            pass  # counted separately below

    if points_processed % 5000 == 0:
        print(f"  ... processed {points_processed:,} / {total_points:,} points")

    if next_offset is None:
        break
    offset = next_offset

print(f"Done. Processed {points_processed:,} points total.")
print(f"Unique namespace IDs:      {len(namespace_ids):,}")
print(f"Unique candidate_ids IDs:  {len(candidate_ids_field):,}")
print(f"Namespace↔candidate_ids drift examples (first 10): {len(drift_examples[:10])}")

# Points with namespace but no candidate_ids
no_cids_count = sum(1 for pid, cnt in namespace_point_counts.items()
                    if pid not in candidate_ids_field and cnt > 0)


# ── Step 2: Firebase audit ────────────────────────────────────────────────────
print()
print("=" * 70)
print("STEP 2: Loading Firebase Firestore candidates")
print("=" * 70)

import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_CREDS)
    firebase_admin.initialize_app(cred)

db = firestore.client()

fb_candidates: dict[str, dict] = {}
skipped = 0
for doc in db.collection("candidates").stream():
    data = doc.to_dict()
    cid = data.get("candidate_id") or doc.id
    if not cid:
        skipped += 1
        continue
    fb_candidates[cid] = data

print(f"Firebase candidates loaded: {len(fb_candidates):,}")
print(f"Skipped (no candidate_id):  {skipped}")

fb_ids = set(fb_candidates.keys())


# ── Step 3: Cross-comparison ──────────────────────────────────────────────────
print()
print("=" * 70)
print("STEP 3: Cross-comparison")
print("=" * 70)

# All Qdrant IDs = union of namespace_ids and candidate_ids_field
qdrant_all_ids = namespace_ids | candidate_ids_field

# A) In Qdrant but not in Firebase (any field)
in_qdrant_not_fb = qdrant_all_ids - fb_ids
# B) In Firebase but not in Qdrant (any field)
in_fb_not_qdrant = fb_ids - qdrant_all_ids

# C) Namespace-only IDs (not in candidate_ids_field)
namespace_only = namespace_ids - candidate_ids_field
# D) candidate_ids-only IDs (not in namespace_ids)
cids_only = candidate_ids_field - namespace_ids
# E) Both fields agree
both_agree = namespace_ids & candidate_ids_field

print(f"Qdrant unique IDs (union):      {len(qdrant_all_ids):,}")
print(f"Firebase unique IDs:            {len(fb_ids):,}")
print()
print(f"[A] In Qdrant NOT in Firebase:  {len(in_qdrant_not_fb):,}")
print(f"[B] In Firebase NOT in Qdrant:  {len(in_fb_not_qdrant):,}")
print()
print(f"[C] Namespace-only IDs:         {len(namespace_only):,}  (in namespace, not candidate_ids)")
print(f"[D] candidate_ids-only IDs:     {len(cids_only):,}  (in candidate_ids, not namespace)")
print(f"[E] Both fields match:          {len(both_agree):,}")

# F) Case-mismatch detection
def casefold(s: str) -> str:
    return s.lower().strip()

fb_lower_map: dict[str, str] = {casefold(k): k for k in fb_ids}
qdrant_lower_map: dict[str, str] = {casefold(k): k for k in qdrant_all_ids}

case_mismatches: list[dict] = []
for lid, qid in qdrant_lower_map.items():
    fid = fb_lower_map.get(lid)
    if fid and fid != qid:
        case_mismatches.append({"qdrant_id": qid, "firebase_id": fid})

print(f"\n[F] Case mismatches:            {len(case_mismatches):,}")

# G) ID format patterns
def id_pattern(cid: str) -> str:
    # Replace digits with D, letters with L to find structural patterns
    p = re.sub(r"\d+", "N", cid)
    return p

qdrant_patterns = Counter(id_pattern(i) for i in qdrant_all_ids)
fb_patterns = Counter(id_pattern(i) for i in fb_ids)

print("\nQdrant ID patterns (top 10):")
for pat, cnt in qdrant_patterns.most_common(10):
    print(f"  {pat!r:40s}  count={cnt}")

print("\nFirebase ID patterns (top 10):")
for pat, cnt in fb_patterns.most_common(10):
    print(f"  {pat!r:40s}  count={cnt}")


# ── Step 4: Detailed per-candidate point distribution ────────────────────────
print()
print("=" * 70)
print("STEP 4: Point distribution per candidate (namespace field)")
print("=" * 70)

counts = list(namespace_point_counts.values())
if counts:
    import statistics
    print(f"Candidates with >=1 point:   {len(namespace_point_counts):,}")
    print(f"Total points via namespace:  {sum(counts):,}")
    print(f"Mean points/candidate:       {statistics.mean(counts):.1f}")
    print(f"Median points/candidate:     {statistics.median(counts):.1f}")
    print(f"Stdev:                       {statistics.stdev(counts):.1f}" if len(counts) > 1 else "")
    print(f"Max points:                  {max(counts)}  ({namespace_point_counts.most_common(1)[0][0]})")
    print(f"Min points:                  {min(counts)}")

    zero_coverage = [cid for cid in fb_ids if namespace_point_counts.get(cid, 0) == 0]
    print(f"\nFirebase candidates with 0 namespace points in Qdrant: {len(zero_coverage):,}")


# ── Step 5: Sample drift examples ────────────────────────────────────────────
if drift_examples:
    print()
    print("=" * 70)
    print(f"STEP 5: Namespace vs candidate_ids drift (showing up to 15 of {len(drift_examples)})")
    print("=" * 70)
    for ex in drift_examples[:15]:
        print(f"  point_id={ex['point_id']}")
        print(f"    namespace:     {ex['namespace']}")
        print(f"    candidate_ids: {ex['candidate_ids']}")


# ── Step 6: Sample IDs from each gap bucket ───────────────────────────────────
print()
print("=" * 70)
print("STEP 6: Sample IDs from each gap bucket")
print("=" * 70)

N = 8
print(f"\n[A] In Qdrant NOT in Firebase (first {N}):")
for x in sorted(in_qdrant_not_fb)[:N]:
    pts = namespace_point_counts.get(x, 0) + candidate_ids_point_counts.get(x, 0)
    print(f"  {x!r:50s}  points~{pts}")

print(f"\n[B] In Firebase NOT in Qdrant (first {N}):")
for x in sorted(in_fb_not_qdrant)[:N]:
    d = fb_candidates[x]
    has_website = bool(d.get("website_url"))
    has_manifesto = bool(d.get("has_manifesto"))
    print(f"  {x!r:50s}  website={has_website}  manifesto={has_manifesto}")

if case_mismatches:
    print(f"\n[F] Case mismatches (first {N}):")
    for m in case_mismatches[:N]:
        print(f"  Qdrant: {m['qdrant_id']!r}  →  Firebase: {m['firebase_id']!r}")


# ── Step 7: Firebase candidates WITH website that are absent from Qdrant ──────
print()
print("=" * 70)
print("STEP 7: Firebase candidates with website/manifesto ABSENT from Qdrant")
print("=" * 70)

fb_with_content_not_in_qdrant = [
    cid for cid in in_fb_not_qdrant
    if fb_candidates[cid].get("website_url") or fb_candidates[cid].get("has_manifesto")
]
print(f"Candidates with content (website or manifesto) missing from Qdrant: {len(fb_with_content_not_in_qdrant):,}")
for x in sorted(fb_with_content_not_in_qdrant)[:10]:
    d = fb_candidates[x]
    print(f"  {x!r:50s}  website={d.get('website_url','')[:60]}  manifesto={d.get('has_manifesto')}")


# ── Step 8: Visualisation ─────────────────────────────────────────────────────
print()
print("=" * 70)
print("STEP 8: Generating visualisations")
print("=" * 70)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# --- Figure 1: Venn-style bar chart ------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5))
categories = [
    "Firebase only\n(not in Qdrant)",
    "Both (any field)",
    "Qdrant only\n(not in Firebase)",
]
values = [len(in_fb_not_qdrant), len(fb_ids & qdrant_all_ids), len(in_qdrant_not_fb)]
colors = ["#e74c3c", "#2ecc71", "#3498db"]
bars = ax.barh(categories, values, color=colors, edgecolor="white", height=0.5)
for bar, val in zip(bars, values):
    ax.text(bar.get_width() + max(values) * 0.01, bar.get_y() + bar.get_height() / 2,
            f"{val:,}", va="center", fontsize=11, fontweight="bold")
ax.set_xlabel("Number of Candidates", fontsize=12)
ax.set_title("Candidate ID Coverage: Firebase vs Qdrant", fontsize=14, fontweight="bold")
ax.set_xlim(0, max(values) * 1.18)
plt.tight_layout()
fig1_path = FIGURES_DIR / f"{TIMESTAMP}_venn_coverage.png"
plt.savefig(fig1_path, dpi=150)
plt.close()
print(f"Saved: {fig1_path}")

# --- Figure 2: Qdrant field breakdown ----------------------------------------
fig, ax = plt.subplots(figsize=(8, 5))
field_categories = ["namespace only", "candidate_ids only", "both fields", "drift\n(ns≠cid)"]
field_values = [len(namespace_only), len(cids_only), len(both_agree), len(drift_examples)]
colors2 = ["#9b59b6", "#e67e22", "#27ae60", "#e74c3c"]
bars2 = ax.bar(field_categories, field_values, color=colors2, edgecolor="white", width=0.5)
for bar, val in zip(bars2, field_values):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(field_values) * 0.01,
            f"{val:,}", ha="center", fontsize=11, fontweight="bold")
ax.set_ylabel("Unique Candidate IDs", fontsize=12)
ax.set_title("Qdrant Metadata Field Consistency\n(namespace vs candidate_ids)", fontsize=13, fontweight="bold")
ax.set_ylim(0, max(field_values) * 1.15)
plt.tight_layout()
fig2_path = FIGURES_DIR / f"{TIMESTAMP}_qdrant_field_breakdown.png"
plt.savefig(fig2_path, dpi=150)
plt.close()
print(f"Saved: {fig2_path}")

# --- Figure 3: Point-count distribution histogram ----------------------------
if counts:
    fig, ax = plt.subplots(figsize=(10, 5))
    clipped = [min(c, 200) for c in counts]
    ax.hist(clipped, bins=40, color="#3498db", edgecolor="white", alpha=0.85)
    ax.set_xlabel("Points per candidate (capped at 200)", fontsize=12)
    ax.set_ylabel("Number of candidates", fontsize=12)
    ax.set_title("Distribution of Qdrant Points per Candidate (namespace field)", fontsize=13, fontweight="bold")
    ax.axvline(statistics.mean(counts), color="red", linestyle="--", label=f"Mean={statistics.mean(counts):.1f}")
    ax.axvline(statistics.median(counts), color="orange", linestyle="--", label=f"Median={statistics.median(counts):.1f}")
    ax.legend(fontsize=10)
    plt.tight_layout()
    fig3_path = FIGURES_DIR / f"{TIMESTAMP}_points_distribution.png"
    plt.savefig(fig3_path, dpi=150)
    plt.close()
    print(f"Saved: {fig3_path}")


# ── Step 9: Write report ──────────────────────────────────────────────────────
print()
print("=" * 70)
print("STEP 9: Writing markdown report")
print("=" * 70)

report_path = REPORT_DIR / f"{TIMESTAMP}_candidate_id_audit.md"

def fmt_sample(items, n=10):
    return "\n".join(f"- `{i}`" for i in sorted(items)[:n])

report = f"""# Candidate ID Consistency Audit
**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Collection:** `{COLLECTION}` ({total_points:,} points)
**Firebase project:** chat-vote-prod (`candidates` collection)

---

## [OBJECTIVE]
Identify ID consistency drift between Qdrant vector DB (`candidates_websites_prod`)
and Firebase Firestore (`candidates` collection) to detect data pipeline integrity issues.

---

## [DATA]
| Source | Unique Candidate IDs | Details |
|--------|---------------------|---------|
| Qdrant `metadata.namespace` | {len(namespace_ids):,} | Primary routing field |
| Qdrant `metadata.candidate_ids` | {len(candidate_ids_field):,} | Filter field |
| Qdrant union (any field) | {len(qdrant_all_ids):,} | |
| Firebase `candidates` collection | {len(fb_ids):,} | Skipped: {skipped} malformed docs |
| Total Qdrant points processed | {points_processed:,} | |

---

## [FINDING 1] Coverage Gap: {len(in_qdrant_not_fb):,} Qdrant IDs absent from Firebase
[STAT:n] n = {len(in_qdrant_not_fb):,} IDs
[STAT:effect_size] {len(in_qdrant_not_fb)/len(qdrant_all_ids)*100:.1f}% of all Qdrant IDs have no Firebase record

These IDs exist in Qdrant (namespace or candidate_ids) but have no matching candidate document in Firestore.
Likely causes: deleted candidates, scraping/indexing artifacts, or stale data.

Sample IDs:
{fmt_sample(in_qdrant_not_fb)}

---

## [FINDING 2] Coverage Gap: {len(in_fb_not_qdrant):,} Firebase candidates absent from Qdrant
[STAT:n] n = {len(in_fb_not_qdrant):,} IDs
[STAT:effect_size] {len(in_fb_not_qdrant)/len(fb_ids)*100:.1f}% of Firebase candidates have no Qdrant vectors

These candidates exist in Firestore but have no vectors indexed.
Of these, **{len(fb_with_content_not_in_qdrant):,}** have a website_url or has_manifesto=True —
meaning content exists but was never indexed, causing silent RAG failures.

Sample (with content):
{fmt_sample(fb_with_content_not_in_qdrant)}

---

## [FINDING 3] Within-Qdrant Field Drift
[STAT:n] n = {len(drift_examples):,} points where namespace ≠ candidate_ids values

| Metric | Count |
|--------|-------|
| Namespace-only IDs (not in candidate_ids) | {len(namespace_only):,} |
| candidate_ids-only IDs (not in namespace) | {len(cids_only):,} |
| IDs present in BOTH fields consistently | {len(both_agree):,} |
| Points where namespace ∉ candidate_ids list | {len(drift_examples):,} |

The `namespace` field is used for query routing; `candidate_ids` is used for filter queries.
Drift between these two fields means candidates reachable via namespace search may not be
reachable via candidate_id filter queries and vice versa.

---

## [FINDING 4] Case Mismatches: {len(case_mismatches):,}
[STAT:n] n = {len(case_mismatches):,} IDs differ only in letter casing between Qdrant and Firebase

{'Sample mismatches:' + chr(10) + chr(10).join(f'- Qdrant: `{m["qdrant_id"]}` → Firebase: `{m["firebase_id"]}`' for m in case_mismatches[:8]) if case_mismatches else '_None detected._'}

---

## [FINDING 5] Point Distribution per Candidate
[STAT:n] n = {len(namespace_point_counts):,} candidates with >=1 point in Qdrant

| Metric | Value |
|--------|-------|
| Mean points/candidate | {statistics.mean(counts):.1f} |
| Median points/candidate | {statistics.median(counts):.1f} |
| Stdev | {statistics.stdev(counts):.1f if len(counts) > 1 else 'N/A'} |
| Max (most indexed) | {max(counts)} ({namespace_point_counts.most_common(1)[0][0]}) |
| Min | {min(counts)} |
| Firebase candidates with 0 namespace points | {len(zero_coverage):,} |

---

## [LIMITATION]
- Firebase streaming reads all candidates at once; very large collections (>100K docs) may be slow.
- Qdrant scroll retrieves payload only (no vectors), so comparisons are metadata-only.
- The `candidate_ids` field is a list; a namespace might legitimately differ if a point belongs to multiple candidates.
- Case mismatch detection uses simple `.lower()` normalisation; Unicode edge cases are not handled.
- Point counts from `metadata.namespace` only (not `metadata.candidate_ids`) to avoid double-counting.

---

## Figures
- `{fig1_path.name}` — Candidate ID coverage venn (Firebase vs Qdrant)
- `{fig2_path.name}` — Qdrant field consistency breakdown
- `{fig3_path.name if counts else 'N/A'}` — Point count distribution histogram
"""

report_path.write_text(report)
print(f"Report saved to: {report_path}")
print()
print("AUDIT COMPLETE.")
