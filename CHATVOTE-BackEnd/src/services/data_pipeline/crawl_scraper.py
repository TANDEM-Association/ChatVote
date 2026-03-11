"""Pipeline node: scrape candidate websites via the external crawl K8s service.

Flow:
1. Get candidates from Firestore that need scraping (have website_url, no has_scraped flag)
2. Check which are already in the Google Sheet (avoid duplicates)
3. Append new candidate rows to the Sheet (read+write scope)
4. Poll the Sheet every poll_interval_s until status == "PROCESSED" or timeout
5. List the Google Drive folder for newly created subfolders
6. Download crawled content from Drive subfolders
7. Convert to ScrapedWebsite objects and put into pipeline context under "scraped_websites"
8. Update Firestore candidate docs with has_scraped: True

Google Sheet columns (Feuil1!A:K):
    candidate_id, firstname, lastname, municipality_code, municipality_name,
    party_ids, election, position, website_url, NA, status

Google Drive output structure (Shared Drive, requires supportsAllDrives=true):
    {slug}-{date}/
    ├── markdown/*.md           — HTML pages → markdown (best quality)
    ├── pdf_markdown/*.md       — PDF transcriptions
    ├── report.csv              — crawl metadata
    ├── pages/{hash}/page.md    — per-page content
    ├── pdfs/*.pdf              — raw PDFs
    └── images/{hash}/          — fallback: OCR results
        ├── descriptions.json   — {image_filename: extracted_text}
        └── *.png               — page renders (ignored for RAG)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time as _time
from typing import Any
from urllib.parse import urlparse

import aiohttp

from src.services.candidate_website_scraper import ScrapedPage, ScrapedWebsite
from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    NodeStatus,
    put_context,
    register_node,
    update_status,
)

logger = logging.getLogger(__name__)

CONTEXT_KEY = "scraped_websites"

# ---------------------------------------------------------------------------
# Content cleanup — filter out junk OCR / boilerplate pages
# ---------------------------------------------------------------------------

# Pages whose entire content matches one of these patterns are discarded
_JUNK_PATTERNS = [
    re.compile(r"^\s*e[\-\s]*mail\s*$", re.I),
    re.compile(r"^\s*(contact|menu|nav|footer|header|sidebar|cookie|gdpr|rgpd)\s*$", re.I),
    re.compile(r"^\s*(chargement|loading|please wait|veuillez patienter)\s*\.{0,3}\s*$", re.I),
    re.compile(r"^\s*(accueil|home|bienvenue|welcome)\s*$", re.I),
    re.compile(r"^\s*(suivez[- ]nous|follow us|partager|share)\s*$", re.I),
    re.compile(r"^\s*(lire la suite|read more|en savoir plus|voir plus)\s*$", re.I),
    re.compile(r"^\s*https?://\S+\s*$", re.I),  # page is just a URL
]

# OCR image descriptions that are visual descriptions, not real text content.
# These are useless for RAG — the OCR model describes what an image looks like
# rather than extracting actual text.
_OCR_VISUAL_PATTERNS = [
    re.compile(r"arrow\s+pointing", re.I),
    re.compile(r"^(the\s+)?image\s+features?\b", re.I),
    re.compile(r"^\s*(portrait|photo|group photo|selfie)\s+of\b", re.I),
    re.compile(r"(logo|icon)\s+(of|consisting|featuring)\b", re.I),
    re.compile(r"^(no\s+)?(additional\s+)?text\s+or\s+data", re.I),
    re.compile(r"background[:\s]+(light|dark|blue|green|orange|red|white|gray|grey)", re.I),
    re.compile(r"^(children|people|individuals|person|man|woman)\s+(playing|standing|sitting|posing|wearing|with\s+)", re.I),
    re.compile(r"(urban|skyline|buildings?|architectural|scenic)\s+(area|view|industrial|with)", re.I),
    re.compile(r"social\s+media\s+icons?", re.I),
    re.compile(r"^(facebook|instagram|twitter|youtube|linkedin)\s+(logo|icon)", re.I),
]

# Minimum content length after stripping whitespace to keep a page
_MIN_CONTENT_LENGTH = 80

# Maximum ratio of non-alphanumeric chars — catches garbled OCR
_MAX_NOISE_RATIO = 0.7


def _is_junk_content(text: str) -> bool:
    """Return True if the text is junk / not useful for RAG."""
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) < _MIN_CONTENT_LENGTH:
        return True
    for pat in _JUNK_PATTERNS:
        if pat.match(stripped):
            return True
    # Check noise ratio — garbled OCR often has lots of symbols
    alnum = sum(1 for c in stripped if c.isalnum() or c.isspace())
    if len(stripped) > 0 and alnum / len(stripped) < (1 - _MAX_NOISE_RATIO):
        return True
    return False


def _is_ocr_visual_description(text: str) -> bool:
    """Return True if text is an OCR visual description (describes image, not real text)."""
    stripped = text.strip()
    for pat in _OCR_VISUAL_PATTERNS:
        if pat.search(stripped):
            return True
    return False


def _clean_scraped_pages(pages: list[ScrapedPage]) -> list[ScrapedPage]:
    """Filter out junk pages and return only useful content."""
    cleaned = []
    for page in pages:
        if _is_junk_content(page.content):
            logger.debug("[crawl_scraper] dropping junk page: %s (len=%d)", page.url, len(page.content))
            continue
        cleaned.append(page)
    return cleaned

SHEETS_API_URL = "https://sheets.googleapis.com/v4/spreadsheets"
DRIVE_API_URL = "https://www.googleapis.com/drive/v3"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Column indices in the sheet (0-based)
COL_CANDIDATE_ID = 0
COL_FIRSTNAME = 1
COL_LASTNAME = 2
COL_MUNICIPALITY_CODE = 3
COL_MUNICIPALITY_NAME = 4
COL_PARTY_IDS = 5
COL_ELECTION = 6
COL_POSITION = 7
COL_WEBSITE_URL = 8
COL_NA = 9
COL_STATUS = 10

SHEET_RANGE = "Feuil1!A:K"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_crawl_credentials():
    """Build Google SA credentials with Sheets (read+write) and Drive (read) scopes."""
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials

    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    if not raw:
        raise RuntimeError("GOOGLE_SHEETS_CREDENTIALS_JSON env var is not set")
    raw = raw.strip().strip("'\"")
    info = json.loads(raw)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(Request())
    return creds


def _slugify_url(url: str) -> str:
    """Produce the slug the crawl service uses for Drive folder names.

    The crawl service slugifies URLs like: https://example.com/path →
    example-com-path (strip scheme, replace non-alphanumeric with hyphens,
    collapse, strip trailing).
    """
    parsed = urlparse(url)
    raw = parsed.netloc + parsed.path
    raw = raw.lower().rstrip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug


def _row_get(row: list[str], idx: int) -> str:
    """Safely get a value from a row by index (handles ragged rows)."""
    return row[idx].strip() if idx < len(row) else ""


# ---------------------------------------------------------------------------
# Node implementation
# ---------------------------------------------------------------------------

class CrawlScraperNode(DataSourceNode):
    node_id = "crawl_scraper"
    label = "Crawl Service Scraper"
    default_settings: dict[str, Any] = {
        "sheet_id": "15Mge7CUwsFMn5h7SVRYoo5V1SyDE2vU5h4F9OnDHWB8",
        "drive_folder_id": "1rLVC3BTVKhOxxGu2GzIfq9BOexleIcRE",
        "poll_interval_s": 30,
        "poll_timeout_s": 600,
        "max_candidates": 50,
    }

    def default_config(self) -> NodeConfig:
        """Enabled by default — takes over candidate website scraping from the built-in scraper."""
        return NodeConfig(
            node_id=self.node_id,
            label=self.label,
            enabled=True,
            settings={**self.default_settings},
        )

    # -----------------------------------------------------------------------
    # Sheet helpers
    # -----------------------------------------------------------------------

    async def _fetch_sheet_rows(
        self, session: aiohttp.ClientSession, sheet_id: str, token: str
    ) -> list[list[str]]:
        url = f"{SHEETS_API_URL}/{sheet_id}/values/{SHEET_RANGE}"
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data.get("values", [])

    async def _append_rows(
        self,
        session: aiohttp.ClientSession,
        sheet_id: str,
        token: str,
        new_rows: list[list[str]],
    ) -> None:
        if not new_rows:
            return
        url = (
            f"{SHEETS_API_URL}/{sheet_id}/values/{SHEET_RANGE}:append"
            "?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with session.post(url, headers=headers, json={"values": new_rows}) as resp:
            resp.raise_for_status()

    # -----------------------------------------------------------------------
    # Drive helpers (Shared Drive / Team Drive compatible)
    # -----------------------------------------------------------------------

    async def _drive_list(
        self,
        session: aiohttp.ClientSession,
        folder_id: str,
        token: str,
        *,
        mime_filter: str = "",
        order_by: str = "",
        page_size: int = 200,
    ) -> list[dict[str, Any]]:
        """List children of a Shared Drive folder."""
        q = f"'{folder_id}' in parents and trashed=false"
        if mime_filter:
            q += f" and mimeType='{mime_filter}'"
        url = (
            f"{DRIVE_API_URL}/files"
            f"?q={q}"
            f"&fields=files(id,name,mimeType,size,createdTime)"
            f"&pageSize={page_size}"
            "&supportsAllDrives=true&includeItemsFromAllDrives=true"
        )
        if order_by:
            url += f"&orderBy={order_by}"
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data.get("files", [])

    async def _drive_download(
        self,
        session: aiohttp.ClientSession,
        file_id: str,
        token: str,
    ) -> bytes:
        url = f"{DRIVE_API_URL}/files/{file_id}?alt=media&supportsAllDrives=true"
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.read()

    async def _find_subfolder(
        self,
        session: aiohttp.ClientSession,
        parent_id: str,
        name: str,
        token: str,
    ) -> str | None:
        items = await self._drive_list(
            session, parent_id, token,
            mime_filter="application/vnd.google-apps.folder",
        )
        for item in items:
            if item["name"] == name:
                return item["id"]
        return None

    # -----------------------------------------------------------------------
    # Content download from crawl output folder
    # -----------------------------------------------------------------------

    async def _download_crawl_content(
        self,
        session: aiohttp.ClientSession,
        site_folder_id: str,
        site_folder_name: str,
        token: str,
    ) -> list[ScrapedPage]:
        """Download text content from a crawl service output folder.

        Tries sources in priority order:
        1. markdown/*.md        — HTML→markdown (best quality for RAG)
        2. pdf_markdown/*.md    — PDF transcriptions
        3. images/*/descriptions.json — OCR fallback
        """
        pages: list[ScrapedPage] = []

        # --- Priority 1: markdown/ folder ---
        md_folder_id = await self._find_subfolder(
            session, site_folder_id, "markdown", token
        )
        if md_folder_id:
            md_files = await self._drive_list(session, md_folder_id, token)
            for f in md_files:
                if not f["name"].endswith(".md"):
                    continue
                try:
                    raw = await self._drive_download(session, f["id"], token)
                    text = raw.decode("utf-8", errors="replace").strip()
                    if len(text) > 50:
                        pages.append(ScrapedPage(
                            url=f["name"],
                            title=f["name"].replace(".md", "").replace("-", " ").title(),
                            content=text,
                            page_type="html",
                        ))
                except Exception as exc:
                    logger.debug(
                        "[crawl_scraper] markdown download failed %s: %s",
                        f["name"], exc,
                    )

        # --- Priority 2: pdf_markdown/ folder ---
        pdf_md_id = await self._find_subfolder(
            session, site_folder_id, "pdf_markdown", token
        )
        if pdf_md_id:
            pdf_files = await self._drive_list(session, pdf_md_id, token)
            for f in pdf_files:
                if not f["name"].endswith(".md"):
                    continue
                try:
                    raw = await self._drive_download(session, f["id"], token)
                    text = raw.decode("utf-8", errors="replace").strip()
                    if len(text) > 50:
                        pages.append(ScrapedPage(
                            url=f["name"],
                            title=f"[PDF] {f['name'].replace('.md', '')}",
                            content=text,
                            page_type="pdf_transcription",
                        ))
                except Exception as exc:
                    logger.debug(
                        "[crawl_scraper] pdf_markdown download failed %s: %s",
                        f["name"], exc,
                    )

        # --- Priority 3: images/*/descriptions.json (OCR fallback) ---
        # Only if we got nothing above
        if not pages:
            images_id = await self._find_subfolder(
                session, site_folder_id, "images", token
            )
            if images_id:
                hash_folders = await self._drive_list(
                    session, images_id, token,
                    mime_filter="application/vnd.google-apps.folder",
                )
                for hf in hash_folders:
                    desc_files = await self._drive_list(session, hf["id"], token)
                    for df in desc_files:
                        if df["name"] != "descriptions.json":
                            continue
                        try:
                            raw = await self._drive_download(session, df["id"], token)
                            descs = json.loads(raw)
                            texts = [
                                str(v) for v in descs.values()
                                if v and len(str(v).strip()) >= _MIN_CONTENT_LENGTH
                                and not _is_junk_content(str(v))
                                and not _is_ocr_visual_description(str(v))
                            ]
                            if texts:
                                pages.append(ScrapedPage(
                                    url=f"{site_folder_name}/{hf['name']}",
                                    title=f"[OCR] {hf['name']}",
                                    content="\n\n".join(texts),
                                    page_type="pdf_transcription",
                                ))
                        except Exception as exc:
                            logger.debug(
                                "[crawl_scraper] descriptions.json failed %s: %s",
                                hf["name"], exc,
                            )

        return pages

    # -----------------------------------------------------------------------
    # URL → Drive folder matching
    # -----------------------------------------------------------------------

    def _match_url_to_folder(
        self,
        website_url: str,
        subfolders: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Find the Drive subfolder that matches a candidate's website URL.

        The crawl service names folders like: {slugified_url}-{YYYY-MM-DD}
        E.g. https://rachidadati2026.com → rachidadati2026-com-2026-03-11
        """
        slug = _slugify_url(website_url)
        if not slug:
            return None

        # Try prefix match (folder name starts with the URL slug)
        matches = [
            sf for sf in subfolders
            if sf["name"].startswith(slug)
        ]
        if not matches:
            # Fuzzy: try if slug is contained in folder name
            matches = [sf for sf in subfolders if slug in sf["name"]]

        if not matches:
            return None

        # Return most recent match
        matches.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
        return matches[0]

    # -----------------------------------------------------------------------
    # Refresh token helper
    # -----------------------------------------------------------------------

    def _ensure_token(self, creds) -> str:
        if not creds.valid:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
        return creds.token

    # -----------------------------------------------------------------------
    # Main run
    # -----------------------------------------------------------------------

    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        settings = cfg.settings
        sheet_id: str = settings.get("sheet_id", self.default_settings["sheet_id"])
        drive_folder_id: str = settings.get(
            "drive_folder_id", self.default_settings["drive_folder_id"]
        )
        poll_interval: int = int(
            settings.get("poll_interval_s", self.default_settings["poll_interval_s"])
        )
        poll_timeout: int = int(
            settings.get("poll_timeout_s", self.default_settings["poll_timeout_s"])
        )
        max_candidates: int = int(
            settings.get("max_candidates", self.default_settings["max_candidates"])
        )

        from src.firebase_service import async_db
        from src.models.candidate import Candidate

        # --- 1. Get unscraped candidates from Firestore --------------------
        logger.info("[crawl_scraper] fetching unscraped candidates from Firestore")
        unscraped: list[Candidate] = []
        async for doc in async_db.collection("candidates").stream():
            data = doc.to_dict()
            raw_url = (data.get("website_url") or "").strip()
            if not raw_url or not raw_url.startswith(("http://", "https://")) or (data.get("has_scraped") and not force):
                continue
            try:
                unscraped.append(Candidate(**data))
            except Exception as exc:
                logger.debug("[crawl_scraper] skip malformed %s: %s", doc.id, exc)

        logger.info("[crawl_scraper] %d unscraped candidates with websites", len(unscraped))

        if not unscraped:
            cfg.counts = {"candidates_total": 0, "submitted": 0, "processed": 0}
            put_context(CONTEXT_KEY, {})
            return cfg

        if len(unscraped) > max_candidates:
            logger.info("[crawl_scraper] capping to %d (found %d)", max_candidates, len(unscraped))
            unscraped = unscraped[:max_candidates]

        # --- 2. Credentials ------------------------------------------------
        creds = _get_crawl_credentials()
        token = creds.token

        async with aiohttp.ClientSession() as session:
            # --- 3. Read sheet: find already-processed and new candidates ----
            existing_ids: set[str] = set()
            already_processed_ids: set[str] = set()
            try:
                rows = await self._fetch_sheet_rows(session, sheet_id, token)
                for row in rows[1:]:
                    cid = _row_get(row, COL_CANDIDATE_ID)
                    if not cid:
                        continue
                    existing_ids.add(cid)
                    status = _row_get(row, COL_STATUS)
                    if status.upper() == "PROCESSED":
                        already_processed_ids.add(cid)
                logger.info(
                    "[crawl_scraper] %d in sheet, %d already PROCESSED",
                    len(existing_ids), len(already_processed_ids),
                )
            except Exception as exc:
                logger.warning("[crawl_scraper] sheet read failed: %s", exc)

            # --- 4. Append only truly new candidates to sheet ---------------
            to_submit = [c for c in unscraped if c.candidate_id not in existing_ids]
            logger.info("[crawl_scraper] %d new candidates to submit", len(to_submit))

            if to_submit:
                new_rows = [
                    [
                        c.candidate_id,
                        c.first_name,
                        c.last_name,
                        c.municipality_code or "",
                        c.municipality_name or "",
                        ",".join(c.party_ids) if c.party_ids else "",
                        c.election_type_id or "",
                        c.position or "",
                        c.website_url or "",
                        "",  # NA column
                        "",  # status — empty = not yet processed
                    ]
                    for c in to_submit
                ]
                await self._append_rows(session, sheet_id, token, new_rows)
                logger.info("[crawl_scraper] appended %d rows", len(new_rows))

            tracked_ids = {c.candidate_id for c in unscraped}

            # Candidates already PROCESSED in the sheet → skip polling for them
            processed_ids: set[str] = already_processed_ids & tracked_ids
            need_polling = tracked_ids - processed_ids

            if processed_ids:
                logger.info(
                    "[crawl_scraper] %d already PROCESSED → skipping straight to Drive download",
                    len(processed_ids),
                )

            # --- 5. Poll only for candidates that still need processing -----
            if not need_polling:
                logger.info("[crawl_scraper] all candidates already PROCESSED, skipping poll")
            else:
                await update_status(
                    cfg.node_id, NodeStatus.RUNNING,
                    counts={
                        "candidates_total": len(unscraped),
                        "submitted": len(to_submit),
                        "processed": len(processed_ids),
                        "already_processed": len(processed_ids),
                        "phase": "polling",
                    },
                )

            if need_polling:
                deadline = _time.monotonic() + poll_timeout

                while _time.monotonic() < deadline:
                    token = self._ensure_token(creds)

                    try:
                        rows = await self._fetch_sheet_rows(session, sheet_id, token)
                        for row in rows[1:]:
                            cid = _row_get(row, COL_CANDIDATE_ID)
                            status = _row_get(row, COL_STATUS)
                            if cid in tracked_ids and status.upper() == "PROCESSED":
                                processed_ids.add(cid)
                    except Exception as exc:
                        logger.warning("[crawl_scraper] poll error: %s", exc)

                    logger.info(
                        "[crawl_scraper] poll: %d / %d processed",
                        len(processed_ids), len(tracked_ids),
                    )
                    await update_status(
                        cfg.node_id, NodeStatus.RUNNING,
                        counts={
                            "candidates_total": len(unscraped),
                            "submitted": len(to_submit),
                            "processed": len(processed_ids),
                            "phase": "polling",
                        },
                    )

                    if processed_ids >= tracked_ids:
                        logger.info("[crawl_scraper] all candidates processed")
                        break

                    await asyncio.sleep(poll_interval)
                else:
                    logger.warning(
                        "[crawl_scraper] poll timeout — %d / %d done",
                        len(processed_ids), len(tracked_ids),
                    )

            if not processed_ids:
                logger.warning("[crawl_scraper] nothing processed, crawl service may be down")
                cfg.counts = {
                    "candidates_total": len(unscraped),
                    "submitted": len(to_submit),
                    "processed": 0,
                }
                put_context(CONTEXT_KEY, {})
                return cfg

            # --- 6. List Drive subfolders and match to candidates ----------
            # The crawl service marks rows PROCESSED when the crawl *job is enqueued*,
            # NOT when content is ready in Drive.  We wait for Drive folders to appear
            # for the candidates we care about (retry up to drive_wait_s).
            drive_wait_s = int(settings.get("drive_wait_s", 300))  # 5 min default

            # Build candidate_id → website_url map from sheet
            cand_url_map: dict[str, str] = {}
            try:
                token = self._ensure_token(creds)
                rows = await self._fetch_sheet_rows(session, sheet_id, token)
                for row in rows[1:]:
                    cid = _row_get(row, COL_CANDIDATE_ID)
                    url = _row_get(row, COL_WEBSITE_URL)
                    if cid and url:
                        cand_url_map[cid] = url
            except Exception:
                pass

            # Collect the URLs we need to find in Drive
            needed_urls = {
                cid: cand_url_map.get(cid, next((c.website_url for c in unscraped if c.candidate_id == cid), ""))
                for cid in processed_ids
            }

            subfolders: list[dict[str, Any]] = []
            drive_ok = True
            matched_count = 0
            prev_matched = -1
            stale_polls = 0
            max_stale_polls = 3  # proceed after 3 polls with no new matches
            drive_deadline = _time.monotonic() + drive_wait_s

            while _time.monotonic() < drive_deadline:
                token = self._ensure_token(creds)
                try:
                    subfolders = await self._drive_list(
                        session, drive_folder_id, token,
                        mime_filter="application/vnd.google-apps.folder",
                        order_by="createdTime desc",
                    )
                except Exception as exc:
                    logger.error("[crawl_scraper] Drive access failed: %s", exc)
                    drive_ok = False
                    break

                # Count how many processed candidates have a matching Drive folder
                matched_count = sum(
                    1 for url in needed_urls.values()
                    if url and self._match_url_to_folder(url, subfolders)
                )

                await update_status(
                    cfg.node_id, NodeStatus.RUNNING,
                    counts={
                        "candidates_total": len(unscraped),
                        "submitted": len(to_submit),
                        "processed": len(processed_ids),
                        "drive_matched": matched_count,
                        "drive_needed": len(needed_urls),
                        "phase": "waiting_for_drive",
                    },
                )

                if matched_count >= len(needed_urls):
                    logger.info("[crawl_scraper] all %d candidates have Drive folders", matched_count)
                    break

                # If match count stopped growing, some candidates may have junk URLs
                # that were PROCESSED but never actually crawled. Proceed with what we have.
                if matched_count == prev_matched and matched_count > 0:
                    stale_polls += 1
                    if stale_polls >= max_stale_polls:
                        logger.info(
                            "[crawl_scraper] Drive match count stable at %d / %d for %d polls, proceeding",
                            matched_count, len(needed_urls), max_stale_polls,
                        )
                        break
                else:
                    stale_polls = 0
                prev_matched = matched_count

                logger.info(
                    "[crawl_scraper] Drive: %d / %d folders ready, waiting...",
                    matched_count, len(needed_urls),
                )
                await asyncio.sleep(poll_interval)
            else:
                logger.warning(
                    "[crawl_scraper] Drive wait timeout — %d / %d folders found after %ds",
                    matched_count, len(needed_urls), drive_wait_s,
                )

            logger.info("[crawl_scraper] %d subfolders in Drive, %d matched", len(subfolders), matched_count)

            await update_status(
                cfg.node_id, NodeStatus.RUNNING,
                counts={
                    "candidates_total": len(unscraped),
                    "submitted": len(to_submit),
                    "processed": len(processed_ids),
                    "phase": "downloading",
                },
            )

            # --- 7. Download content and build ScrapedWebsite objects ------
            scraped_map: dict[str, ScrapedWebsite] = {}

            for candidate in unscraped:
                if candidate.candidate_id not in processed_ids:
                    continue

                url = cand_url_map.get(
                    candidate.candidate_id, candidate.website_url or ""
                )
                sw = ScrapedWebsite(
                    candidate_id=candidate.candidate_id,
                    website_url=url,
                    backend="crawl_service",
                )

                if drive_ok and subfolders:
                    folder = self._match_url_to_folder(url, subfolders)
                    if folder:
                        try:
                            token = self._ensure_token(creds)
                            raw_pages = await self._download_crawl_content(
                                session, folder["id"], folder["name"], token,
                            )
                            cleaned = _clean_scraped_pages(raw_pages)
                            sw.pages = cleaned
                            dropped = len(raw_pages) - len(cleaned)
                            logger.info(
                                "[crawl_scraper] %s → %s — %d pages (%d dropped), %d chars",
                                candidate.full_name, folder["name"],
                                len(cleaned), dropped, sw.total_content_length,
                            )
                        except Exception as exc:
                            logger.warning(
                                "[crawl_scraper] download failed for %s: %s",
                                candidate.full_name, exc,
                            )
                            sw.error = str(exc)
                    else:
                        logger.warning(
                            "[crawl_scraper] no Drive folder matched for %s (%s)",
                            candidate.full_name, url,
                        )
                        sw.error = "No matching Drive folder"
                elif not drive_ok:
                    sw.error = "Drive folder not accessible"

                scraped_map[candidate.candidate_id] = sw

            # --- 8. Update Firestore candidate docs ------------------------
            for candidate in unscraped:
                if candidate.candidate_id not in processed_ids:
                    continue
                sw = scraped_map.get(candidate.candidate_id)
                try:
                    ref = async_db.collection("candidates").document(
                        candidate.candidate_id
                    )
                    await ref.set(
                        {
                            "has_scraped": True,
                            "scrape_backend": "crawl_service",
                            "scrape_pages": len(sw.pages) if sw else 0,
                            "scrape_chars": sw.total_content_length if sw else 0,
                        },
                        merge=True,
                    )
                except Exception as exc:
                    logger.debug(
                        "[crawl_scraper] Firestore update failed %s: %s",
                        candidate.candidate_id, exc,
                    )

        # --- 8b. Mark ALL sheet-PROCESSED candidates as scraped in Firestore -
        # The crawl service may have processed hundreds of candidates across
        # previous runs.  Sync their has_scraped flag so the coverage page
        # reflects reality (not just this batch of max_candidates).
        bulk_marked = 0
        for cid in already_processed_ids - tracked_ids:
            try:
                ref = async_db.collection("candidates").document(cid)
                await ref.set(
                    {"has_scraped": True, "scrape_backend": "crawl_service"},
                    merge=True,
                )
                bulk_marked += 1
            except Exception:
                pass
        if bulk_marked:
            logger.info(
                "[crawl_scraper] bulk-marked %d previously PROCESSED candidates as has_scraped",
                bulk_marked,
            )

        # --- 9. Pipeline context and return --------------------------------
        put_context(CONTEXT_KEY, scraped_map)

        total_pages = sum(len(sw.pages) for sw in scraped_map.values())
        total_chars = sum(sw.total_content_length for sw in scraped_map.values())
        with_content = sum(1 for sw in scraped_map.values() if sw.is_successful)

        cfg.counts = {
            "candidates_total": len(unscraped),
            "submitted": len(to_submit),
            "processed": len(processed_ids),
            "with_content": with_content,
            "pages": total_pages,
            "total_chars": total_chars,
        }

        logger.info(
            "[crawl_scraper] done — %d processed, %d with content, %d pages, %d chars",
            len(processed_ids), with_content, total_pages, total_chars,
        )

        return cfg


register_node(CrawlScraperNode())
