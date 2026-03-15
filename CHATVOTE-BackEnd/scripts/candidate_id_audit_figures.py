#!/usr/bin/env python3
"""Generate audit figures from hard-coded audit results (run with system Python 3.14)."""

from pathlib import Path
from datetime import datetime
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FIGURES_DIR = Path("/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd/.omc/scientist/figures")
FIGURES_DIR.mkdir(parents=True, exist_ok=True)
TIMESTAMP = "20260314_165432"

# ── Audit results ─────────────────────────────────────────────────────────────
firebase_ids_total  = 49_897
qdrant_union_ids    = 689
in_fb_not_qdrant    = 49_208
in_qdrant_not_fb    = 0
namespace_only      = 0
cids_only           = 0
both_agree          = 689
drift_examples      = 0
content_missing     = 83
no_content_missing  = in_fb_not_qdrant - content_missing   # 49_125
cands_with_points   = 689
total_ns_points     = 35_960
mean_pts            = 52.2
median_pts          = 7.0
stdev_pts           = 117.9
max_pts             = 1150
max_pts_cand        = "cand-75056-8"
min_pts             = 1

# ── Figure 1: Coverage bar chart ──────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 5))
categories = [
    f"Firebase only — not indexed\n(n={in_fb_not_qdrant:,})",
    f"Covered by Qdrant\n(n={qdrant_union_ids:,})",
    f"Qdrant only — no Firebase record\n(n={in_qdrant_not_fb})",
]
values = [in_fb_not_qdrant, qdrant_union_ids, in_qdrant_not_fb]
colors = ["#e74c3c", "#2ecc71", "#3498db"]
bars = ax.barh(categories, values, color=colors, edgecolor="white", height=0.45)
for bar, val in zip(bars, values):
    ax.text(bar.get_width() + 400, bar.get_y() + bar.get_height() / 2,
            f"{val:,}", va="center", fontsize=12, fontweight="bold")
ax.set_xlabel("Number of Candidate IDs", fontsize=12)
ax.set_title("Candidate ID Coverage: Firebase (49,897) vs Qdrant (689 indexed)",
             fontsize=13, fontweight="bold", pad=14)
ax.set_xlim(0, in_fb_not_qdrant * 1.18)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
plt.tight_layout()
fig1_path = FIGURES_DIR / f"{TIMESTAMP}_venn_coverage.png"
plt.savefig(fig1_path, dpi=150)
plt.close()
print(f"Saved: {fig1_path}")

# ── Figure 2: Qdrant field consistency ───────────────────────────────────────
fig, ax = plt.subplots(figsize=(9, 5))
field_labels = ["namespace\nonly", "candidate_ids\nonly", "Both fields\nagreeing", "Drift\n(ns ≠ cids)"]
field_vals   = [namespace_only, cids_only, both_agree, drift_examples]
colors2      = ["#9b59b6", "#e67e22", "#27ae60", "#e74c3c"]
bars2 = ax.bar(field_labels, field_vals, color=colors2, edgecolor="white", width=0.5)
for bar, val in zip(bars2, field_vals):
    ax.text(bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(field_vals) * 0.02,
            f"{val:,}", ha="center", fontsize=12, fontweight="bold")
ax.set_ylabel("Unique Candidate IDs", fontsize=12)
ax.set_title("Qdrant Metadata Field Consistency\n(namespace vs candidate_ids, per point)",
             fontsize=13, fontweight="bold")
ax.set_ylim(0, max(field_vals) * 1.18)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
plt.tight_layout()
fig2_path = FIGURES_DIR / f"{TIMESTAMP}_qdrant_field_breakdown.png"
plt.savefig(fig2_path, dpi=150)
plt.close()
print(f"Saved: {fig2_path}")

# ── Figure 3: Indexing status stacked bar ─────────────────────────────────────
fig, ax = plt.subplots(figsize=(12, 4))
segments = [qdrant_union_ids, no_content_missing, content_missing]
seg_labels = [
    f"Indexed in Qdrant ({qdrant_union_ids:,})",
    f"No content, not indexed ({no_content_missing:,})",
    f"Has website/manifesto, NOT indexed ({content_missing:,})  ← silent RAG gap",
]
seg_colors = ["#27ae60", "#bdc3c7", "#e74c3c"]
left = 0
for val, color, label in zip(segments, seg_colors, seg_labels):
    ax.barh(["Candidates"], [val], left=left, color=color,
            label=label, height=0.38, edgecolor="white")
    if val > 1000:
        ax.text(left + val / 2, 0, f"{val:,}",
                ha="center", va="center", fontsize=10, fontweight="bold", color="white")
    left += val

ax.set_xlabel("Number of Firebase Candidates (total = 49,897)", fontsize=12)
ax.set_title("Firebase Candidates: Indexing Status Breakdown", fontsize=13, fontweight="bold", pad=14)
ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
ax.set_xlim(0, firebase_ids_total * 1.01)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.spines["left"].set_visible(False)
ax.yaxis.set_visible(False)
plt.tight_layout()
fig3_path = FIGURES_DIR / f"{TIMESTAMP}_indexing_status.png"
plt.savefig(fig3_path, dpi=150)
plt.close()
print(f"Saved: {fig3_path}")

# ── Figure 4: Point count distribution (simulated from summary stats) ─────────
rng = np.random.default_rng(42)
k     = (mean_pts / stdev_pts) ** 2
theta = stdev_pts ** 2 / mean_pts
sim   = rng.gamma(k, theta, cands_with_points)
sim   = np.clip(sim, min_pts, None)
sim[0] = max_pts

fig, ax = plt.subplots(figsize=(11, 5))
ax.hist(sim, bins=50, color="#3498db", edgecolor="white", alpha=0.85)
ax.axvline(mean_pts,   color="#e74c3c", linestyle="--", linewidth=2,
           label=f"Mean = {mean_pts:.1f} pts")
ax.axvline(median_pts, color="#f39c12", linestyle="--", linewidth=2,
           label=f"Median = {median_pts:.1f} pts")
ax.set_xlabel("Points per candidate (namespace field)", fontsize=12)
ax.set_ylabel("Number of candidates", fontsize=12)
ax.set_title(
    f"Distribution of Qdrant Points per Candidate\n"
    f"n={cands_with_points:,} indexed candidates · {total_ns_points:,} total points · "
    f"max={max_pts} ({max_pts_cand})",
    fontsize=12, fontweight="bold")
ax.legend(fontsize=11)
ax.annotate(
    "Distribution simulated from\nsummary stats (mean, σ, median)",
    xy=(0.74, 0.72), xycoords="axes fraction", fontsize=8, color="#666",
    bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#aaa", alpha=0.8))
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
plt.tight_layout()
fig4_path = FIGURES_DIR / f"{TIMESTAMP}_points_distribution.png"
plt.savefig(fig4_path, dpi=150)
plt.close()
print(f"Saved: {fig4_path}")

print("\nAll figures generated.")
