# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Scheduler service for periodic tasks.

Runs CRON jobs for:
- Municipalities sync: every Sunday at midnight
- Candidate websites re-indexing: every day at 3 AM

Usage:
    python -m src.services.scheduler
"""

import asyncio
import logging
import subprocess
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.services.municipalities_sync import sync_municipalities
from src.services.candidate_indexer import index_all_candidates

logger = logging.getLogger(__name__)

# Path to the import script
SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
IMPORT_SCRIPT = SCRIPTS_DIR / "import-firestore.js"
MUNICIPALITIES_JSON = (
    Path(__file__).parent.parent.parent
    / "firebase"
    / "firestore_data"
    / "dev"
    / "municipalities.json"
)


async def sync_and_import_municipalities() -> None:
    """Sync municipalities from API and import to Firestore."""
    try:
        logger.info("Starting scheduled municipalities sync...")

        # Step 1: Fetch from API and save to file
        count = await sync_municipalities()
        logger.info(f"Synced {count} municipalities from API")

        # Step 2: Import to Firestore
        logger.info("Importing municipalities to Firestore...")
        result = subprocess.run(
            [
                "node",
                str(IMPORT_SCRIPT),
                "municipalities",
                str(MUNICIPALITIES_JSON),
                "--clean",
            ],
            capture_output=True,
            text=True,
            cwd=str(SCRIPTS_DIR.parent),
        )

        if result.returncode != 0:
            logger.error(f"Firestore import failed: {result.stderr}")
            raise Exception(f"Firestore import failed: {result.stderr}")

        logger.info(f"Firestore import output: {result.stdout}")
        logger.info("Scheduled municipalities sync complete!")

    except Exception as e:
        logger.error(f"Scheduled sync failed: {e}", exc_info=True)


async def reindex_candidate_websites() -> None:
    """Re-scrape and re-index all candidate websites."""
    try:
        logger.info("Starting scheduled candidate websites re-indexing...")

        results = await index_all_candidates()

        total = sum(results.values())
        successful = sum(1 for v in results.values() if v > 0)

        logger.info(
            f"Candidate websites re-indexing complete: "
            f"{total} chunks for {successful}/{len(results)} candidates"
        )

    except Exception as e:
        logger.error(f"Scheduled candidate re-indexing failed: {e}", exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the scheduler."""
    scheduler = AsyncIOScheduler()

    # Run every Sunday at midnight (00:00)
    scheduler.add_job(
        sync_and_import_municipalities,
        CronTrigger(day_of_week="sun", hour=0, minute=0),
        id="municipalities_sync",
        name="Sync municipalities from geo.api.gouv.fr",
        replace_existing=True,
    )

    # Re-index candidate websites every day at 3 AM
    scheduler.add_job(
        reindex_candidate_websites,
        CronTrigger(hour=3, minute=0),
        id="candidates_reindex",
        name="Re-index candidate websites daily",
        replace_existing=True,
    )

    logger.info(
        "Scheduler configured: "
        "municipalities sync every Sunday at midnight, "
        "candidate websites re-indexing daily at 3 AM"
    )
    return scheduler


async def run_scheduler() -> None:
    """Run the scheduler indefinitely."""
    scheduler = create_scheduler()
    scheduler.start()

    logger.info("Scheduler started. Press Ctrl+C to exit.")

    try:
        # Keep the scheduler running
        while True:
            await asyncio.sleep(3600)  # Sleep for 1 hour
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler...")
        scheduler.shutdown()


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger.info("Starting scheduler service...")
    asyncio.run(run_scheduler())


if __name__ == "__main__":
    main()
