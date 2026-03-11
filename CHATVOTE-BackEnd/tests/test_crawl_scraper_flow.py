"""Integration test for the crawl_scraper pipeline node.

Run standalone:
    poetry run python tests/test_crawl_scraper_flow.py
    poetry run python tests/test_crawl_scraper_flow.py --dry-run
    poetry run python tests/test_crawl_scraper_flow.py --timeout 120 --max-candidates 2

Flags:
    --dry-run         Check state only, do not modify the sheet or Firestore
    --timeout SECS    Poll timeout in seconds (default: 120)
    --max-candidates  Maximum candidates to submit (default: 2)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(PROJECT_ROOT / ".env.local", override=True)
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("test_crawl_scraper")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SHEET_ID = "15Mge7CUwsFMn5h7SVRYoo5V1SyDE2vU5h4F9OnDHWB8"
DRIVE_FOLDER_ID = "1rLVC3BTVKhOxxGu2GzIfq9BOexleIcRE"
SHEET_RANGE = "Feuil1!A:K"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_API = "https://www.googleapis.com/drive/v3"

COL_CANDIDATE_ID = 0
COL_WEBSITE_URL = 8
COL_STATUS = 10

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _row_get(row: list[str], idx: int) -> str:
    return row[idx].strip() if idx < len(row) else ""


def _slugify_url(url: str) -> str:
    parsed = urlparse(url)
    raw = parsed.netloc + parsed.path
    raw = raw.lower().rstrip("/")
    return re.sub(r"[^a-z0-9]+", "-", raw).strip("-")


def _get_creds():
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials

    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    if not raw:
        raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS_JSON is not set")
    info = json.loads(raw.strip().strip("'\""))
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(Request())
    return creds


def _init_firebase() -> None:
    import firebase_admin
    from firebase_admin import credentials as fb_creds

    if firebase_admin._apps:
        return
    cred_b64 = os.environ.get("FIREBASE_CREDENTIALS_BASE64", "")
    if cred_b64:
        import base64
        cred = fb_creds.Certificate(json.loads(base64.b64decode(cred_b64)))
    else:
        cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
        cred = fb_creds.Certificate(cred_path) if cred_path else fb_creds.ApplicationDefault()
    firebase_admin.initialize_app(cred)
    logger.info("[%s] Firebase initialized", _ts())


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

async def run_test(dry_run: bool, poll_timeout: int, max_candidates: int) -> None:
    import aiohttp

    print("=" * 70)
    print(f"  crawl_scraper integration test  dry_run={dry_run}")
    print("=" * 70)

    # ── Step 1: Firestore candidates ──────────────────────────────────────
    logger.info("[%s] Step 1: fetch unscraped candidates from Firestore", _ts())
    from firebase_admin import firestore
    db = firestore.client()

    all_docs = list(db.collection("candidates").stream())
    unscraped = []
    for doc in all_docs:
        d = doc.to_dict()
        if d.get("website_url") and not d.get("has_scraped"):
            unscraped.append({"id": doc.id, **d})

    logger.info("[%s] %d unscraped candidates with websites (total %d)", _ts(), len(unscraped), len(all_docs))
    selected = unscraped[:max_candidates]

    if not selected:
        logger.info("[%s] nothing to do", _ts())
        return

    for c in selected:
        logger.info("  %-30s  %s", c.get("candidate_id", c["id"]), c.get("website_url", ""))

    # ── Step 2: Read Google Sheet ─────────────────────────────────────────
    logger.info("[%s] Step 2: read Google Sheet", _ts())
    creds = _get_creds()
    token = creds.token

    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(f"{SHEETS_API}/{SHEET_ID}/values/{SHEET_RANGE}", headers=headers) as resp:
            resp.raise_for_status()
            sheet_data = await resp.json()

    rows = sheet_data.get("values", [])
    data_rows = rows[1:] if len(rows) > 1 else []
    existing_ids = {_row_get(r, COL_CANDIDATE_ID) for r in data_rows if _row_get(r, COL_CANDIDATE_ID)}

    logger.info("[%s] sheet has %d data rows, %d unique candidate IDs", _ts(), len(data_rows), len(existing_ids))

    to_submit = [c for c in selected if (c.get("candidate_id") or c["id"]) not in existing_ids]
    already_in = [c for c in selected if (c.get("candidate_id") or c["id"]) in existing_ids]

    logger.info("[%s] %d to submit, %d already in sheet", _ts(), len(to_submit), len(already_in))

    # ── Step 3: Check Drive folder ────────────────────────────────────────
    logger.info("[%s] Step 3: check Drive folder (Shared Drive)", _ts())

    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}
        drive_url = (
            f"{DRIVE_API}/files"
            f"?q='{DRIVE_FOLDER_ID}'+in+parents"
            "+and+mimeType='application/vnd.google-apps.folder'+and+trashed=false"
            "&fields=files(id,name,createdTime)"
            "&orderBy=createdTime+desc&pageSize=50"
            "&supportsAllDrives=true&includeItemsFromAllDrives=true"
        )
        async with session.get(drive_url, headers=headers) as resp:
            resp.raise_for_status()
            drive_data = await resp.json()

    subfolders = drive_data.get("files", [])
    logger.info("[%s] %d subfolders in Drive", _ts(), len(subfolders))

    # Test URL→folder matching for selected candidates
    for c in selected:
        url = c.get("website_url", "")
        slug = _slugify_url(url)
        matched = [sf for sf in subfolders if sf["name"].startswith(slug)]
        if matched:
            logger.info("  MATCH: %s → %s", url, matched[0]["name"])
        else:
            logger.info("  NO MATCH: %s (slug=%s)", url, slug)

    if dry_run:
        logger.info("[%s] DRY RUN — stopping before writes", _ts())
        _report(selected, existing_ids, data_rows, subfolders)
        return

    # ── Step 4: Append to Sheet ───────────────────────────────────────────
    if to_submit:
        logger.info("[%s] Step 4: appending %d rows to sheet", _ts(), len(to_submit))
        new_rows = []
        for c in to_submit:
            cid = c.get("candidate_id", c["id"])
            new_rows.append([
                cid,
                c.get("first_name", ""),
                c.get("last_name", ""),
                c.get("municipality_code", ""),
                c.get("municipality_name", ""),
                ",".join(c.get("party_ids", [])),
                c.get("election_type_id", ""),
                c.get("position", ""),
                c.get("website_url", ""),
                "",
                "",
            ])
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            append_url = f"{SHEETS_API}/{SHEET_ID}/values/{SHEET_RANGE}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
            async with session.post(append_url, headers=headers, json={"values": new_rows}) as resp:
                resp.raise_for_status()
                logger.info("[%s] appended %d rows OK", _ts(), len(new_rows))

    # ── Step 5: Poll for PROCESSED ────────────────────────────────────────
    logger.info("[%s] Step 5: polling for PROCESSED (timeout=%ds)", _ts(), poll_timeout)
    tracked_ids = {(c.get("candidate_id") or c["id"]) for c in selected}
    processed_ids: set[str] = set()
    t0 = time.monotonic()

    while time.monotonic() - t0 < poll_timeout:
        elapsed = round(time.monotonic() - t0, 1)

        if not creds.valid:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            token = creds.token

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {token}"}
            async with session.get(f"{SHEETS_API}/{SHEET_ID}/values/{SHEET_RANGE}", headers=headers) as resp:
                resp.raise_for_status()
                poll_data = await resp.json()

        for row in poll_data.get("values", [])[1:]:
            cid = _row_get(row, COL_CANDIDATE_ID)
            status = _row_get(row, COL_STATUS)
            if cid in tracked_ids and status.upper() == "PROCESSED":
                processed_ids.add(cid)

        logger.info("[%s] @%.0fs — %d/%d processed", _ts(), elapsed, len(processed_ids), len(tracked_ids))

        if processed_ids >= tracked_ids:
            break
        await asyncio.sleep(30)
    else:
        logger.warning("[%s] timeout — %d/%d", _ts(), len(processed_ids), len(tracked_ids))

    # ── Step 6: Download content from Drive ───────────────────────────────
    logger.info("[%s] Step 6: download crawled content from Drive", _ts())

    async with aiohttp.ClientSession() as session:
        headers = {"Authorization": f"Bearer {token}"}

        # Refresh subfolder list
        async with session.get(drive_url, headers=headers) as resp:
            resp.raise_for_status()
            drive_data = await resp.json()
        subfolders = drive_data.get("files", [])

        grand_total_pages = 0
        grand_total_chars = 0

        for c in selected:
            cid = c.get("candidate_id", c["id"])
            url = c.get("website_url", "")
            slug = _slugify_url(url)
            matched = [sf for sf in subfolders if sf["name"].startswith(slug)]

            if not matched:
                logger.warning("  %s: no Drive folder for %s", cid, url)
                continue

            folder = matched[0]
            logger.info("  %s → %s", cid, folder["name"])

            pages_found = 0
            chars_found = 0

            # Try markdown/
            for subfolder_name in ["markdown", "pdf_markdown"]:
                find_url = (
                    f"{DRIVE_API}/files"
                    f"?q='{folder['id']}'+in+parents+and+name='{subfolder_name}'"
                    "&fields=files(id,name)&supportsAllDrives=true&includeItemsFromAllDrives=true"
                )
                async with session.get(find_url, headers=headers) as resp:
                    fd = await resp.json()

                if not fd.get("files"):
                    continue

                sf_id = fd["files"][0]["id"]
                list_url = (
                    f"{DRIVE_API}/files"
                    f"?q='{sf_id}'+in+parents&fields=files(id,name,size)"
                    "&supportsAllDrives=true&includeItemsFromAllDrives=true"
                )
                async with session.get(list_url, headers=headers) as resp:
                    files = (await resp.json()).get("files", [])

                for f in files:
                    if not f["name"].endswith(".md"):
                        continue
                    try:
                        dl_url = f"{DRIVE_API}/files/{f['id']}?alt=media&supportsAllDrives=true"
                        async with session.get(dl_url, headers=headers) as resp:
                            content = await resp.read()
                        text = content.decode("utf-8", errors="replace").strip()
                        pages_found += 1
                        chars_found += len(text)
                        logger.info(
                            "    [%s] %-40s  %d chars  preview: %.80s",
                            subfolder_name, f["name"], len(text),
                            text.replace("\n", " ")[:80],
                        )
                    except Exception as exc:
                        logger.warning("    download error %s: %s", f["name"], exc)

            grand_total_pages += pages_found
            grand_total_chars += chars_found

            if pages_found == 0:
                logger.warning("    no text content found, would fall back to OCR descriptions.json")

    # ── Report ────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print(f"  candidates selected   : {len(selected)}")
    print(f"  submitted to sheet    : {len(to_submit)}")
    print(f"  processed by crawl    : {len(processed_ids)}")
    print(f"  drive subfolders      : {len(subfolders)}")
    print(f"  total pages downloaded: {grand_total_pages}")
    print(f"  total chars           : {grand_total_chars}")
    print("=" * 70)


def _report(
    selected: list[dict],
    existing_ids: set[str],
    data_rows: list[list[str]],
    subfolders: list[dict],
) -> None:
    print()
    print("=" * 70)
    print("  DRY RUN REPORT")
    print("-" * 70)
    print("  Candidates that would be submitted:")
    for c in selected:
        cid = c.get("candidate_id", c["id"])
        in_sheet = cid in existing_ids
        tag = "(in sheet)" if in_sheet else "(NEW)"
        print(f"    {cid:<30}  {c.get('website_url',''):<50}  {tag}")

    print(f"\n  Sheet rows ({len(data_rows)} total):")
    for row in data_rows[:15]:
        cid = _row_get(row, COL_CANDIDATE_ID)
        url = _row_get(row, COL_WEBSITE_URL)
        status = _row_get(row, COL_STATUS) or "(empty)"
        print(f"    {cid:<30}  {url[:50]:<50}  status={status}")
    if len(data_rows) > 15:
        print(f"    ... and {len(data_rows) - 15} more rows")

    print(f"\n  Drive subfolders ({len(subfolders)} total):")
    for sf in subfolders[:10]:
        print(f"    {sf['name']:<60}  {sf.get('createdTime', '?')[:19]}")
    if len(subfolders) > 10:
        print(f"    ... and {len(subfolders) - 10} more")
    print("=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser(description="crawl_scraper integration test")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-candidates", type=int, default=2)
    args = parser.parse_args()

    _init_firebase()
    asyncio.run(run_test(args.dry_run, args.timeout, args.max_candidates))


if __name__ == "__main__":
    main()
