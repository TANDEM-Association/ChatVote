#!/usr/bin/env python3
"""Download profession de foi PDFs from the French interior ministry website.

Standalone script — no project imports needed.

Mirrors the pipeline behavior: fetches top N communes by population from
geo.api.gouv.fr, then downloads PDFs only for those communes.

Steps:
1. Fetch top communes by population from geo.api.gouv.fr
2. Download candidatures CSV from data.gouv.fr
3. Filter to only communes in the top N
4. Download each PDF from programme-candidats.interieur.gouv.fr
5. Save to BACKUP_DIR/{commune_code}/1-{commune_code}-{panneau}.pdf

Usage:
    python scripts/backup_all_professions.py
    python scripts/backup_all_professions.py --communes 500
    python scripts/backup_all_professions.py --output ~/Desktop/professions_backup
    python scripts/backup_all_professions.py --all  # ignore top-N filter
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import os
import sys
import tempfile
import time
from pathlib import Path

import json

import aiohttp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
GEO_API_URL = (
    "https://geo.api.gouv.fr/communes"
    "?fields=nom,code,population,codeDepartement"
    "&boost=population"
)

CSV_URL = (
    "https://static.data.gouv.fr/resources/"
    "elections-municipales-2026-listes-candidates-au-premier-tour/"
    "20260313-152615/municipales-2026-candidatures-france-entiere-tour-1-2026-03-13.csv"
)

BASE_URL = "https://programme-candidats.interieur.gouv.fr/elections-municipales-2026"
PDF_URL_TPL = f"{BASE_URL}/data-pdf/{{tour}}-{{commune_code}}-{{panneau}}.pdf"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
    "Referer": f"{BASE_URL}/",
}


# ---------------------------------------------------------------------------
# Step 1: Fetch top communes by population
# ---------------------------------------------------------------------------
async def fetch_top_communes(session: aiohttp.ClientSession, top_n: int) -> set[str]:
    """Fetch communes from geo.api.gouv.fr, return top N codes by population."""
    logger.info("Fetching communes from geo.api.gouv.fr (top %d) ...", top_n)
    async with session.get(GEO_API_URL) as resp:
        resp.raise_for_status()
        data = await resp.json()

    # Sort by population descending, take top N
    communes = sorted(data, key=lambda c: c.get("population", 0), reverse=True)
    top_codes = {c["code"] for c in communes[:top_n]}
    smallest = communes[top_n - 1] if top_n <= len(communes) else communes[-1]
    logger.info(
        "Top %d communes (smallest: %s, pop %d)",
        len(top_codes), smallest.get("nom", "?"), smallest.get("population", 0),
    )
    return top_codes


# ---------------------------------------------------------------------------
# Step 2: Parse candidatures CSV → set of (commune_code, panneau)
# ---------------------------------------------------------------------------
async def fetch_candidatures(
    session: aiohttp.ClientSession,
    allowed_communes: set[str] | None = None,
) -> set[tuple[str, str]]:
    """Download CSV and return unique (commune_code, panneau) pairs.

    If allowed_communes is set, only return pairs for those communes.
    """
    csv_url = os.environ.get("DATA_GOUV_CANDIDATURES_URL", CSV_URL)
    logger.info("Downloading candidatures CSV from %s ...", csv_url)

    with tempfile.NamedTemporaryFile(mode="wb", suffix=".csv", delete=False) as tmp:
        tmp_path = tmp.name
        async with session.get(csv_url) as resp:
            resp.raise_for_status()
            async for chunk in resp.content.iter_chunked(64 * 1024):
                tmp.write(chunk)

    pairs: set[tuple[str, str]] = set()
    skipped = 0
    with open(tmp_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            commune_code = row.get("Code circonscription", "").strip()
            panneau = row.get("Numéro de panneau", "").strip()
            if not commune_code or not panneau:
                continue
            if allowed_communes and commune_code not in allowed_communes:
                skipped += 1
                continue
            pairs.add((commune_code, panneau))

    os.unlink(tmp_path)
    if allowed_communes:
        logger.info(
            "Found %d unique (commune, panneau) pairs from CSV "
            "(filtered to %d communes, skipped %d rows)",
            len(pairs), len(allowed_communes), skipped,
        )
    else:
        logger.info("Found %d unique (commune, panneau) pairs from CSV (unfiltered)", len(pairs))
    return pairs


# ---------------------------------------------------------------------------
# Step 2: Download PDFs
# ---------------------------------------------------------------------------
async def download_pdf(
    session: aiohttp.ClientSession,
    sem: asyncio.Semaphore,
    commune_code: str,
    panneau: str,
    output_dir: Path,
    tour: int = 1,
) -> bool:
    """Download a single PDF. Returns True if saved successfully."""
    url = PDF_URL_TPL.format(tour=tour, commune_code=commune_code, panneau=panneau)
    async with sem:
        try:
            async with session.get(url) as resp:
                if resp.status in (404, 403):
                    return False
                if resp.status != 200:
                    return False

                content = await resp.read()
                if not content[:4] == b"%PDF":
                    return False

                pdf_dir = output_dir / commune_code
                pdf_dir.mkdir(parents=True, exist_ok=True)
                pdf_path = pdf_dir / f"{tour}-{commune_code}-{panneau}.pdf"
                pdf_path.write_bytes(content)
                return True
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False


async def main():
    parser = argparse.ArgumentParser(
        description="Backup all profession de foi PDFs from data.gouv.fr"
    )
    parser.add_argument(
        "--output", "-o",
        default=os.path.expanduser("~/Documents/professions_de_foi_backup"),
        help="Output directory (default: ~/Documents/professions_de_foi_backup)",
    )
    parser.add_argument(
        "--concurrency", "-c",
        type=int,
        default=15,
        help="Max concurrent downloads (default: 15)",
    )
    parser.add_argument(
        "--tour", "-t",
        type=int,
        default=1,
        help="Election round (default: 1)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Backup directory: %s", output_dir)

    sem = asyncio.Semaphore(args.concurrency)
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
        # 1. Get all commune/panneau pairs
        pairs = await fetch_candidatures(session)

        # 2. Check which PDFs already exist locally (resume support)
        to_download = []
        already_exists = 0
        for commune_code, panneau in pairs:
            pdf_path = output_dir / commune_code / f"{args.tour}-{commune_code}-{panneau}.pdf"
            if pdf_path.exists() and pdf_path.stat().st_size > 100:
                already_exists += 1
            else:
                to_download.append((commune_code, panneau))

        logger.info(
            "Already downloaded: %d | To download: %d",
            already_exists, len(to_download),
        )

        if not to_download:
            logger.info("Nothing to download — backup is complete!")
            return

        # 3. Download in batches with progress
        t0 = time.monotonic()
        downloaded = 0
        not_found = 0
        total = len(to_download)
        batch_size = 100

        for i in range(0, total, batch_size):
            batch = to_download[i : i + batch_size]
            tasks = [
                download_pdf(session, sem, cc, p, output_dir, args.tour)
                for cc, p in batch
            ]
            results = await asyncio.gather(*tasks)
            batch_ok = sum(1 for r in results if r)
            batch_miss = sum(1 for r in results if not r)
            downloaded += batch_ok
            not_found += batch_miss

            elapsed = time.monotonic() - t0
            progress = i + len(batch)
            rate = progress / elapsed if elapsed > 0 else 0
            eta = (total - progress) / rate if rate > 0 else 0

            logger.info(
                "Progress: %d/%d (%.0f%%) | Downloaded: %d | Not found: %d | "
                "%.1f/s | ETA: %.0fs",
                progress, total, 100 * progress / total,
                downloaded, not_found, rate, eta,
            )

    elapsed = time.monotonic() - t0
    total_files = already_exists + downloaded
    total_size_mb = sum(
        f.stat().st_size
        for f in output_dir.rglob("*.pdf")
    ) / (1024 * 1024)

    logger.info(
        "\n=== Backup Complete ===\n"
        "Directory: %s\n"
        "Total PDFs: %d (%.1f MB)\n"
        "  Already had: %d\n"
        "  Newly downloaded: %d\n"
        "  Not found on server: %d\n"
        "Time: %.1fs",
        output_dir, total_files, total_size_mb,
        already_exists, downloaded, not_found, elapsed,
    )


if __name__ == "__main__":
    asyncio.run(main())
