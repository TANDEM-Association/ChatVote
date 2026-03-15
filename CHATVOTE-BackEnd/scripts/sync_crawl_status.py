#!/usr/bin/env python3
"""Standalone script to sync crawl status (col R) and Drive folder (col Q) on the Google Sheet.

Reads the sheet, lists Drive folders, matches them to candidates, and updates columns Q & R.
No Firestore or backend needed — works purely from Sheet + Drive state.

Usage:
    cd CHATVOTE-BackEnd
    poetry run python scripts/sync_crawl_status.py [--dry-run]
"""
import argparse
import asyncio
import logging
import sys
import os

# Allow imports from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import aiohttp
from src.services.data_pipeline.crawl_scraper import (
    CrawlScraperNode,
    _get_crawl_credentials,
    _row_get,
    COL_CANDIDATE_ID,
    COL_WEBSITE_URL,
    COL_STATUS,
    COL_DRIVE_FOLDER,
    COL_CRAWL_STATUS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SOCIAL_DOMAINS = (
    "facebook.com", "fb.com", "instagram.com", "twitter.com",
    "x.com", "tiktok.com", "linkedin.com", "youtube.com",
)


async def main(dry_run: bool = False) -> None:
    node = CrawlScraperNode()
    settings = node.default_settings
    sheet_id = settings["sheet_id"]
    drive_folder_id = settings["drive_folder_id"]

    creds = _get_crawl_credentials()
    token = node._ensure_token(creds)

    async with aiohttp.ClientSession() as session:
        # 1. Read sheet (wide: A:R)
        logger.info("Reading Google Sheet...")
        rows = await node._fetch_sheet_rows_wide(session, sheet_id, token)
        logger.info("Sheet has %d rows (including header)", len(rows))

        # 2. Build processed_ids from sheet status column
        processed_ids: set[str] = set()
        for row in rows[1:]:
            cid = _row_get(row, COL_CANDIDATE_ID)
            status = _row_get(row, COL_STATUS)
            if cid and status.upper() == "PROCESSED":
                processed_ids.add(cid)
        logger.info("Found %d PROCESSED candidates in sheet", len(processed_ids))

        # 3. List Drive folders to build drive_folder_map
        token = node._ensure_token(creds)
        logger.info("Listing Drive folders...")
        subfolders = await node._drive_list(
            session, drive_folder_id, token,
            mime_filter="application/vnd.google-apps.folder",
            order_by="createdTime desc",
        )
        logger.info("Found %d subfolders in Drive", len(subfolders))

        # 4. Match candidates to Drive folders
        drive_folder_map: dict[str, tuple[str, str]] = {}
        for row in rows[1:]:
            cid = _row_get(row, COL_CANDIDATE_ID)
            url = _row_get(row, COL_WEBSITE_URL)
            if not cid or not url:
                continue
            folder = node._match_url_to_folder(url, subfolders)
            if folder:
                drive_folder_map[cid] = (folder["name"], folder["id"])

        logger.info("Matched %d candidates to Drive folders", len(drive_folder_map))

        # 5. For this standalone sync, downloaded_ids = candidates with Drive folders
        downloaded_ids = set(drive_folder_map.keys())

        # 6. Build updates (same logic as _sync_crawl_status_to_sheet)
        updates: list[dict] = []
        stats: dict[str, int] = {}

        for i, row in enumerate(rows[1:], 2):
            cid = _row_get(row, COL_CANDIDATE_ID)
            website = _row_get(row, COL_WEBSITE_URL)
            status_col = _row_get(row, COL_STATUS)
            current_q = _row_get(row, COL_DRIVE_FOLDER)
            current_r = _row_get(row, COL_CRAWL_STATUS)

            if status_col.upper() != "PROCESSED" or not cid:
                continue

            # Determine crawl status
            if not website or not website.startswith(("http://", "https://")):
                domain = ""
            else:
                domain = website.split("//", 1)[-1].split("/", 1)[0].lower().removeprefix("www.")

            if any(domain == d or domain.endswith("." + d) for d in SOCIAL_DOMAINS):
                crawl_status = "SOCIAL_MEDIA"
            elif not website:
                crawl_status = "NO_WEBSITE"
            elif cid in downloaded_ids:
                crawl_status = "DONE"
            elif cid in drive_folder_map:
                crawl_status = "DONE"
            elif cid in processed_ids:
                crawl_status = "CRAWLED"
            else:
                crawl_status = "CRAWLING"

            stats[crawl_status] = stats.get(crawl_status, 0) + 1

            if crawl_status != current_r:
                updates.append({"range": f"Feuil1!R{i}", "values": [[crawl_status]]})

            if cid in drive_folder_map and not current_q:
                _fname, fid = drive_folder_map[cid]
                drive_url = f"https://drive.google.com/drive/folders/{fid}"
                updates.append({"range": f"Feuil1!Q{i}", "values": [[drive_url]]})

        logger.info("Status breakdown: %s", stats)
        logger.info("Updates to write: %d cells", len(updates))

        if dry_run:
            for u in updates[:20]:
                logger.info("  [DRY RUN] %s → %s", u["range"], u["values"][0][0])
            if len(updates) > 20:
                logger.info("  ... and %d more", len(updates) - 20)
            return

        if updates:
            token = node._ensure_token(creds)
            updated = await node._batch_update_cells(session, sheet_id, token, updates)
            logger.info("Synced %d cells to Google Sheet (columns Q & R)", updated)
        else:
            logger.info("Nothing to update — sheet is already in sync")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sync crawl status to Google Sheet")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
