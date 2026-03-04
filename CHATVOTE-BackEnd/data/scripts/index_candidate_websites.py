#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Batch script to index candidate campaign websites into the vector store.

Usage:
    # Index all candidates with websites
    python index_candidate_websites.py

    # Index a specific candidate by ID
    python index_candidate_websites.py --candidate-id cand-paris-001

    # Index all candidates in a municipality
    python index_candidate_websites.py --municipality-code 75056

    # Dry run (scrape only, no indexing)
    python index_candidate_websites.py --dry-run

    # Set environment
    ENV=prod python index_candidate_websites.py
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.models.candidate import Candidate  # noqa: E402
from src.firebase_service import (  # noqa: E402
    aget_candidates_with_website,
    aget_candidates_by_municipality,
    aget_candidate_by_id,
)
from src.services.candidate_website_scraper import CandidateWebsiteScraper  # noqa: E402
from src.services.candidate_indexer import (  # noqa: E402
    index_all_candidates,
    index_candidate_by_id,
    index_candidates_by_municipality,
)

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the script."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


async def dry_run_all_candidates() -> None:
    """Scrape all candidates without indexing (for testing)."""
    print("\n=== DRY RUN: Scraping candidates without indexing ===\n")

    candidates = await aget_candidates_with_website()
    print(f"Found {len(candidates)} candidates with website URLs\n")

    scraper = CandidateWebsiteScraper()
    results = await scraper.scrape_multiple_candidates(candidates, max_concurrent=3)

    print("\n=== Results ===\n")
    successful = 0
    failed = 0

    for result in sorted(results, key=lambda r: r.candidate_id):
        if result.is_successful:
            successful += 1
            print(
                f"[OK] {result.candidate_id}: "
                f"{len(result.pages)} pages, {result.total_content_length} chars"
            )
            for page in result.pages:
                print(
                    f"     - {page.page_type}: {page.url} ({len(page.content)} chars)"
                )
        else:
            failed += 1
            print(f"[FAILED] {result.candidate_id}: {result.error}")

    print("\n=== Summary ===")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print(f"Total: {len(results)}")


async def index_single_candidate(candidate_id: str) -> None:
    """Index a single candidate by ID."""
    print(f"\n=== Indexing candidate: {candidate_id} ===\n")

    candidate = await aget_candidate_by_id(candidate_id)
    if candidate is None:
        print(f"Error: Candidate {candidate_id} not found in Firestore")
        sys.exit(1)

    print(f"Candidate: {candidate.full_name}")
    print(
        f"Municipality: {candidate.municipality_name} ({candidate.municipality_code})"
    )
    print(f"Website: {candidate.website_url}")
    print()

    count = await index_candidate_by_id(candidate_id)

    if count > 0:
        print(f"\n[OK] Indexed {count} chunks for {candidate.full_name}")
    else:
        print(f"\n[FAILED] Could not index {candidate.full_name}")
        sys.exit(1)


async def index_municipality_candidates(municipality_code: str) -> None:
    """Index all candidates in a municipality."""
    print(f"\n=== Indexing candidates for municipality: {municipality_code} ===\n")

    candidates = await aget_candidates_by_municipality(municipality_code)
    if not candidates:
        print(f"Error: No candidates found for municipality {municipality_code}")
        sys.exit(1)

    candidates_with_website = [c for c in candidates if c.website_url]
    print(
        f"Found {len(candidates)} candidates, {len(candidates_with_website)} with websites\n"
    )

    for c in candidates:
        has_website = "Yes" if c.website_url else "No"
        print(f"  - {c.full_name} (website: {has_website})")

    print()

    results = await index_candidates_by_municipality(municipality_code)

    print("\n=== Results ===\n")
    total = sum(results.values())
    successful = sum(1 for v in results.values() if v > 0)

    for candidate_id, count in sorted(results.items()):
        status = "OK" if count > 0 else "FAILED"
        print(f"[{status}] {candidate_id}: {count} chunks")

    print(f"\nTotal: {total} chunks indexed for {successful}/{len(results)} candidates")


async def index_all() -> None:
    """Index all candidates with websites."""
    print("\n=== Indexing all candidates with websites ===\n")

    candidates = await aget_candidates_with_website()
    print(f"Found {len(candidates)} candidates with website URLs\n")

    # Group by municipality for display
    by_municipality: dict[str, list[Candidate]] = {}
    for c in candidates:
        key = c.municipality_name or "National"
        if key not in by_municipality:
            by_municipality[key] = []
        by_municipality[key].append(c)

    for muni, cands in sorted(by_municipality.items()):
        print(f"  {muni}: {len(cands)} candidates")

    print()

    results = await index_all_candidates()

    print("\n=== Results ===\n")
    total = sum(results.values())
    successful = sum(1 for v in results.values() if v > 0)

    # Group results by municipality
    for candidate_id, count in sorted(results.items()):
        status = "OK" if count > 0 else "FAILED"
        print(f"[{status}] {candidate_id}: {count} chunks")

    print("\n=== Summary ===")
    print(f"Total chunks indexed: {total}")
    print(f"Successful candidates: {successful}/{len(results)}")


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Index candidate campaign websites into the vector store."
    )
    parser.add_argument(
        "--candidate-id",
        type=str,
        help="Index a specific candidate by ID",
    )
    parser.add_argument(
        "--municipality-code",
        type=str,
        help="Index all candidates in a specific municipality (by INSEE code)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape websites without indexing (for testing)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    env = os.getenv("ENV", "dev")
    print(f"Environment: {env}")
    print(f"Started at: {datetime.now().isoformat()}")

    try:
        if args.dry_run:
            asyncio.run(dry_run_all_candidates())
        elif args.candidate_id:
            asyncio.run(index_single_candidate(args.candidate_id))
        elif args.municipality_code:
            asyncio.run(index_municipality_candidates(args.municipality_code))
        else:
            asyncio.run(index_all())

        print(f"\nCompleted at: {datetime.now().isoformat()}")

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Script failed: {e}", exc_info=True)
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
