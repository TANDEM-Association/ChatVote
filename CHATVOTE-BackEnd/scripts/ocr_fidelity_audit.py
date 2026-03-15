"""
OCR Fidelity Audit: image-only profession de foi PDFs vs Qdrant chunks
Compares OCR-extracted text from scanned PDFs against stored Qdrant chunks.
"""

import os
import sys
import json
import re
import tempfile
import unicodedata
import difflib
import urllib.request
from pathlib import Path
from datetime import datetime

# ── deps ──────────────────────────────────────────────────────────────────────
import fitz            # pymupdf
import pytesseract
from PIL import Image
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# ── config ────────────────────────────────────────────────────────────────────
QDRANT_URL     = "http://212.47.245.238:6333"
QDRANT_API_KEY = "7384d5cc296a254996640081df3a08f824a2f999bb1fb98d91929d811ddc22cb"
COLLECTION     = "candidates_websites_prod"
PDF_DIR        = Path("/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd/.omc/scientist/pdfs")
REPORT_DIR     = Path("/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd/.omc/scientist/reports")
FIG_DIR        = Path("/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-BackEnd/.omc/scientist/figures")
PDF_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_ONLY_CITIES = {
    "08105": "Charleville-Mézières",
    "28085": "Chartres",
    "31149": "Colomiers",
    "33039": "Bègles",
    "33281": "Mérignac",
}

TESSERACT_LANG = "fra"
DPI = 200  # render resolution for OCR (200 DPI is a good balance of speed/quality)


# ── helpers ───────────────────────────────────────────────────────────────────

def normalize(text: str) -> str:
    """Lowercase, strip accents, collapse whitespace."""
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> list[str]:
    return normalize(text).split()


def sliding_segments(text: str, window: int = 20) -> list[str]:
    """Return overlapping word-window segments from text."""
    words = tokenize(text)
    return [" ".join(words[i : i + window]) for i in range(0, max(1, len(words) - window + 1), 5)]


def find_missing_segments(source_text: str, target_text: str, window: int = 20, top_n: int = 3) -> list[str]:
    """Find segments of source_text that have low similarity to anything in target_text."""
    target_norm = normalize(target_text)
    segments = sliding_segments(source_text, window)
    scored = []
    for seg in segments:
        ratio = difflib.SequenceMatcher(None, seg, target_norm[:len(seg)*3]).ratio()
        scored.append((ratio, seg))
    scored.sort(key=lambda x: x[0])
    # deduplicate: skip if first 50 chars overlap with already-selected
    seen = []
    result = []
    for ratio, seg in scored:
        prefix = seg[:50]
        if all(difflib.SequenceMatcher(None, prefix, s[:50]).ratio() < 0.6 for s in seen):
            result.append(seg[:150])
            seen.append(seg)
        if len(result) >= top_n:
            break
    return result


def ocr_pdf(pdf_path: Path) -> tuple[str, int, int]:
    """OCR all pages of a PDF. Returns (full_text, page_count, total_chars)."""
    doc = fitz.open(str(pdf_path))
    pages_text = []
    mat = fitz.Matrix(DPI / 72, DPI / 72)  # scale factor

    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        page_text = pytesseract.image_to_string(img, lang=TESSERACT_LANG)
        pages_text.append(page_text)

    doc.close()
    full_text = "\n".join(pages_text)
    return full_text, len(pages_text), len(full_text)


def download_pdf(url: str, dest: Path) -> bool:
    """Download PDF from URL. Returns True on success."""
    if dest.exists() and dest.stat().st_size > 1000:
        return True
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ChatVoteAudit/1.0)"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 500:
            print(f"    WARNING: tiny download ({len(data)} bytes) for {url}")
            return False
        dest.write_bytes(data)
        return True
    except Exception as e:
        print(f"    DOWNLOAD ERROR: {e}")
        return False


# ── Step 1: Fetch Qdrant data ─────────────────────────────────────────────────

def fetch_candidates_from_qdrant() -> dict:
    """Return dict: candidate_id -> candidate info + chunks."""
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=60,
                          check_compatibility=False)
    all_candidates = {}

    for city_code, city_name in IMAGE_ONLY_CITIES.items():
        print(f"\n[Qdrant] Querying {city_name} ({city_code})...")
        offset = None

        while True:
            results, next_offset = client.scroll(
                collection_name=COLLECTION,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(key="metadata.source_document",
                                       match=MatchValue(value="profession_de_foi")),
                        FieldCondition(key="metadata.municipality_code",
                                       match=MatchValue(value=city_code)),
                    ]
                ),
                limit=200,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )

            for point in results:
                payload = point.payload or {}
                meta    = payload.get("metadata", {})
                cids    = meta.get("candidate_ids", [])
                cid     = cids[0] if cids else meta.get("namespace", "unknown")

                if cid not in all_candidates:
                    all_candidates[cid] = {
                        "candidate_id": cid,
                        "city_code":    city_code,
                        "city_name":    city_name,
                        "chunks":       [],
                        "url":          meta.get("url", ""),
                        "name":         meta.get("candidate_name") or cid,
                    }
                all_candidates[cid]["chunks"].append({
                    "page_content":  payload.get("page_content", ""),
                    "chunk_index":   meta.get("chunk_index", 0),
                })

            offset = next_offset
            if next_offset is None:
                break

        city_cands = [c for c in all_candidates.values() if c["city_code"] == city_code]
        print(f"  {len(city_cands)} candidates, "
              f"{sum(len(c['chunks']) for c in city_cands)} chunks total")

    # Sort chunks within each candidate
    for cand in all_candidates.values():
        cand["chunks"].sort(key=lambda c: c["chunk_index"])

    return all_candidates


# ── Step 2 + 3: OCR + compare ─────────────────────────────────────────────────

def audit_candidate(cand: dict) -> dict:
    cid      = cand["candidate_id"]
    url      = cand["url"]
    chunks   = cand["chunks"]
    city     = cand["city_name"]

    # Build chunk text
    chunk_text = "\n".join(c["page_content"] for c in chunks)

    result = {
        "candidate_id":  cid,
        "name":          cand["name"],
        "city":          city,
        "url":           url,
        "n_chunks":      len(chunks),
        "chunk_chars":   len(chunk_text),
        "pdf_pages":     0,
        "ocr_chars":     0,
        "ocr_words":     0,
        "similarity":    0.0,
        "word_coverage": 0.0,
        "missing_segs":  [],
        "extra_segs":    [],
        "verdict":       "NO_PDF",
        "error":         None,
    }

    if not url:
        result["error"] = "no URL in metadata"
        return result

    # Download PDF
    safe_name = re.sub(r"[^\w\-]", "_", cid) + ".pdf"
    pdf_path  = PDF_DIR / safe_name
    print(f"  [{city}] {cid}: downloading PDF...")

    if not download_pdf(url, pdf_path):
        result["error"] = "download failed"
        return result

    # OCR
    print(f"  [{city}] {cid}: OCR ({pdf_path.stat().st_size // 1024} KB)...")
    try:
        ocr_text, n_pages, ocr_chars = ocr_pdf(pdf_path)
    except Exception as e:
        result["error"] = f"OCR failed: {e}"
        return result

    ocr_words = len(tokenize(ocr_text))
    result["pdf_pages"] = n_pages
    result["ocr_chars"] = ocr_chars
    result["ocr_words"] = ocr_words

    if ocr_words < 10:
        result["error"] = "OCR yielded almost no text"
        result["verdict"] = "OCR_EMPTY"
        return result

    # Similarity: SequenceMatcher on normalized texts
    ocr_norm   = normalize(ocr_text)
    chunk_norm = normalize(chunk_text)
    sim = difflib.SequenceMatcher(None, ocr_norm[:5000], chunk_norm[:5000]).ratio()
    result["similarity"] = round(sim, 4)

    # Word-level coverage: % of unique OCR words found in chunk text
    ocr_word_set   = set(tokenize(ocr_text))
    chunk_word_set = set(tokenize(chunk_text))
    if ocr_word_set:
        coverage = len(ocr_word_set & chunk_word_set) / len(ocr_word_set)
    else:
        coverage = 0.0
    result["word_coverage"] = round(coverage, 4)

    # Missing / extra segments
    result["missing_segs"] = find_missing_segments(ocr_text, chunk_text, window=15, top_n=3)
    result["extra_segs"]   = find_missing_segments(chunk_text, ocr_text, window=15, top_n=3)

    # Verdict
    if sim >= 0.85 or coverage >= 0.85:
        result["verdict"] = "MATCH"
    elif sim >= 0.50 or coverage >= 0.50:
        result["verdict"] = "PARTIAL"
    else:
        result["verdict"] = "MISMATCH"

    print(f"    → sim={sim:.3f}  coverage={coverage:.1%}  verdict={result['verdict']}")
    return result


# ── Step 4: Visualization ─────────────────────────────────────────────────────

def make_charts(results: list[dict]):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import numpy as np

    # Filter to processed candidates only
    valid = [r for r in results if r["verdict"] not in ("NO_PDF", "OCR_EMPTY") and r["error"] is None]
    if not valid:
        print("No valid results for charts.")
        return

    names     = [f"{r['candidate_id']}\n({r['city'][:10]})" for r in valid]
    sims      = [r["similarity"]    for r in valid]
    coverages = [r["word_coverage"] for r in valid]
    verdicts  = [r["verdict"]       for r in valid]

    colors = {"MATCH": "#2ecc71", "PARTIAL": "#f39c12", "MISMATCH": "#e74c3c"}
    bar_colors = [colors.get(v, "#95a5a6") for v in verdicts]

    x = np.arange(len(valid))
    width = 0.35

    fig, axes = plt.subplots(2, 1, figsize=(max(12, len(valid) * 0.9), 10))

    # Chart 1: Similarity + Coverage bars
    ax = axes[0]
    ax.bar(x - width/2, sims,      width, label="Sequence similarity", color=bar_colors, alpha=0.9)
    ax.bar(x + width/2, coverages, width, label="Word coverage",        color=bar_colors, alpha=0.5)
    ax.axhline(0.85, color="green",  linestyle="--", linewidth=1, label="MATCH threshold (0.85)")
    ax.axhline(0.50, color="orange", linestyle="--", linewidth=1, label="PARTIAL threshold (0.50)")
    ax.set_xticks(x)
    ax.set_xticklabels(names, fontsize=7, rotation=45, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Score (0–1)")
    ax.set_title("OCR vs Qdrant Chunk Fidelity — Similarity & Word Coverage")
    ax.legend(fontsize=8)

    patches = [mpatches.Patch(color=c, label=k) for k, c in colors.items()]
    ax.legend(handles=patches + [
        plt.Line2D([0], [0], color="green",  linestyle="--", label="MATCH threshold"),
        plt.Line2D([0], [0], color="orange", linestyle="--", label="PARTIAL threshold"),
    ], fontsize=8)

    # Chart 2: OCR words vs chunk chars scatter
    ax2 = axes[1]
    for r in valid:
        c = colors.get(r["verdict"], "#95a5a6")
        ax2.scatter(r["ocr_words"], r["chunk_chars"], color=c, s=80, zorder=3)
        ax2.annotate(r["candidate_id"], (r["ocr_words"], r["chunk_chars"]),
                     fontsize=6, textcoords="offset points", xytext=(4, 2))
    ax2.set_xlabel("OCR word count")
    ax2.set_ylabel("Qdrant chunk chars")
    ax2.set_title("OCR Size vs Qdrant Storage Size")
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    out = FIG_DIR / "ocr_fidelity_audit.png"
    plt.savefig(str(out), dpi=120, bbox_inches="tight")
    plt.close()
    print(f"\nChart saved: {out}")


# ── Step 5: Report ────────────────────────────────────────────────────────────

def write_report(results: list[dict]):
    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    path  = REPORT_DIR / f"{ts}_ocr_fidelity_audit.md"

    verdict_counts = {}
    for r in results:
        verdict_counts[r["verdict"]] = verdict_counts.get(r["verdict"], 0) + 1

    lines = [
        "# OCR Fidelity Audit — Profession de Foi PDFs",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_\n",
        "## [OBJECTIVE]",
        "Verify that Qdrant chunks faithfully represent the content of image-only scanned profession de foi PDFs.",
        "OCR is performed with Tesseract 5 (fra language) at 200 DPI via PyMuPDF page rendering.\n",
        "## [DATA]",
        f"- Cities audited: {len(IMAGE_ONLY_CITIES)} (Charleville-Mézières, Chartres, Colomiers, Bègles, Mérignac)",
        f"- Total candidates queried: {len(results)}",
        f"- Verdicts: {verdict_counts}\n",
        "## Summary Table\n",
        "| Candidate ID | Name | City | Pages | OCR Words | Chunks | Sim | Coverage | Verdict |",
        "|---|---|---|---|---|---|---|---|---|",
    ]

    for r in results:
        lines.append(
            f"| `{r['candidate_id']}` | {r['name']} | {r['city']} | "
            f"{r['pdf_pages']} | {r['ocr_words']:,} | {r['n_chunks']} | "
            f"{r['similarity']:.3f} | {r['word_coverage']:.1%} | **{r['verdict']}** |"
        )

    lines.append("\n## Detailed Findings\n")

    for r in results:
        lines += [
            f"### {r['candidate_id']} — {r['name']} ({r['city']})",
            f"- URL: `{r['url']}`",
            f"- PDF pages: {r['pdf_pages']}",
            f"- OCR chars: {r['ocr_chars']:,}  |  OCR words: {r['ocr_words']:,}",
            f"- Qdrant chunks: {r['n_chunks']}  |  Chunk chars: {r['chunk_chars']:,}",
            f"- Similarity ratio: **{r['similarity']:.4f}**",
            f"- Word coverage: **{r['word_coverage']:.1%}**",
            f"- Verdict: **{r['verdict']}**",
        ]
        if r.get("error"):
            lines.append(f"- Error: {r['error']}")
        if r["missing_segs"]:
            lines.append("- Top missing segments (OCR text absent from chunks):")
            for seg in r["missing_segs"]:
                lines.append(f'  - `"{seg}"`')
        if r["extra_segs"]:
            lines.append("- Top extra segments (chunk text absent from OCR):")
            for seg in r["extra_segs"]:
                lines.append(f'  - `"{seg}"`')
        lines.append("")

    lines += [
        "## [FINDING] Overall Fidelity Assessment",
        f"- MATCH (sim≥0.85 or coverage≥0.85): {verdict_counts.get('MATCH', 0)} candidates",
        f"- PARTIAL (sim≥0.50 or coverage≥0.50): {verdict_counts.get('PARTIAL', 0)} candidates",
        f"- MISMATCH (sim<0.50 and coverage<0.50): {verdict_counts.get('MISMATCH', 0)} candidates",
        f"- Download/OCR failures: {verdict_counts.get('NO_PDF', 0) + verdict_counts.get('OCR_EMPTY', 0)} candidates",
        "",
        "## [LIMITATION]",
        "- OCR quality depends on scan resolution and ink clarity of original PDFs.",
        "- Tesseract French model may struggle with unusual fonts or low-contrast scans.",
        "- Similarity metrics are character-level (SequenceMatcher) and word-level (set intersection).",
        "  Neither accounts for paraphrasing or reformatting during chunking.",
        "- Chunks may have been pre-processed (whitespace normalization, header removal) before indexing.",
        "- Download failures may reflect expired Firebase Storage signed URLs or network issues.",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport saved: {path}")
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("OCR FIDELITY AUDIT — Profession de Foi PDFs vs Qdrant Chunks")
    print("=" * 70)

    # Step 1: Fetch Qdrant data
    candidates = fetch_candidates_from_qdrant()
    print(f"\nTotal candidates with chunks: {len(candidates)}")

    # Print what we found
    for cid, cand in sorted(candidates.items()):
        print(f"  {cid:30s}  {cand['city_name']:25s}  {len(cand['chunks'])} chunks  url={bool(cand['url'])}")

    # Step 2-4: OCR + compare each candidate
    print("\n" + "=" * 70)
    print("Starting OCR + fidelity comparison...")
    print("=" * 70)

    results = []
    for cid, cand in sorted(candidates.items()):
        res = audit_candidate(cand)
        results.append(res)

    # Step 5: Charts + report
    print("\n" + "=" * 70)
    print("Generating visualizations and report...")
    make_charts(results)
    report_path = write_report(results)

    # Console summary
    print("\n" + "=" * 70)
    print("SUMMARY TABLE")
    print("=" * 70)
    print(f"{'Candidate ID':<32} {'City':<22} {'Sim':>6} {'Cov':>6} {'Verdict'}")
    print("-" * 80)
    for r in sorted(results, key=lambda x: x["city"]):
        err = f" [{r['error']}]" if r.get("error") else ""
        print(f"{r['candidate_id']:<32} {r['city']:<22} {r['similarity']:>6.3f} {r['word_coverage']:>6.1%} {r['verdict']}{err}")

    print("\nDone.")
    return results


if __name__ == "__main__":
    main()
