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

# XML sitemap detection — drop entire page
_SITEMAP_PATTERNS = [
    re.compile(r"<\?xml", re.I),
    re.compile(r"<urlset", re.I),
    re.compile(r"<sitemapindex", re.I),
    re.compile(r"xmlns.*sitemaps\.org", re.I),
]

# Facebook/Meta cookie wall — if >50% of content is this, the page is a wall
_META_WALL_KEYWORDS = [
    "cookies d'autres entreprises",
    "produits meta",
    "politique d'utilisation des cookies",
    "cookies essentiels",
    "connectez-vous ou inscrivez-vous",
    "autoriser l'utilisation des cookies de facebook",
    "créer un compte",
    "mot de passe oublié",
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


def _is_sitemap_xml(text: str) -> bool:
    """Return True if the page is an XML sitemap (not useful content)."""
    # Only check first 500 chars — sitemaps have XML markers at the top
    head = text[:500]
    return any(pat.search(head) for pat in _SITEMAP_PATTERNS)


def _normalize_apostrophes(text: str) -> str:
    """Replace curly/typographic apostrophes with straight ones for matching."""
    return text.replace("\u2019", "'").replace("\u2018", "'").replace("\u00b4", "'")


def _is_social_media_wall(text: str, url: str) -> bool:
    """Return True if the page is a Facebook/social media login/cookie wall.

    Only triggers when:
    - URL is from facebook.com, instagram.com, etc. AND
    - Content is predominantly cookie/login boilerplate (>=3 wall keywords)
    This avoids false positives on real pages that just mention Facebook.
    """
    lower_url = url.lower()
    social_domains = ("facebook.com", "instagram.com", "fb.com")
    if not any(d in lower_url for d in social_domains):
        return False
    lower = _normalize_apostrophes(text.lower())
    hits = sum(1 for kw in _META_WALL_KEYWORDS if kw in lower)
    # Need at least 3 wall keywords to be confident it's a wall
    return hits >= 3


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
        if _is_sitemap_xml(page.content):
            logger.debug("[crawl_scraper] dropping sitemap XML: %s", page.url)
            continue
        if _is_social_media_wall(page.content, page.url):
            logger.debug("[crawl_scraper] dropping social media wall: %s", page.url)
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
# Standalone Drive loader (used by indexer to skip Playwright)
# ---------------------------------------------------------------------------

async def load_scraped_from_drive(
    candidate_id: str,
    website_url: str,
    drive_folder_id: str | None = None,
) -> ScrapedWebsite | None:
    """Load a candidate's scraped content from Google Drive.

    Returns a ScrapedWebsite with pages populated from Drive markdown files,
    or None if no Drive folder is found for this candidate.
    """
    try:
        creds = _get_crawl_credentials()
    except Exception:
        return None

    node = CrawlScraperNode()
    if drive_folder_id is None:
        drive_folder_id = node.default_settings["drive_folder_id"]

    slug = _slugify_url(website_url)
    if not slug:
        return None

    async with aiohttp.ClientSession() as session:
        token = node._ensure_token(creds)

        # Find the candidate's subfolder by URL slug
        try:
            subfolders = await node._drive_list(session, drive_folder_id, token,
                mime_filter="application/vnd.google-apps.folder")
        except Exception as exc:
            logger.warning("[load_scraped_from_drive] Drive list failed: %s", exc)
            return None

        # Match slug to folder name
        site_folder = None
        for f in subfolders:
            if f["name"] == slug or slug in f["name"]:
                site_folder = f
                break

        if not site_folder:
            return None

        # Download content
        try:
            token = node._ensure_token(creds)
            raw_pages = await node._download_crawl_content(
                session, site_folder["id"], site_folder["name"], token,
            )
            cleaned = _clean_scraped_pages(raw_pages)
        except Exception as exc:
            logger.warning("[load_scraped_from_drive] download failed %s: %s", candidate_id, exc)
            return None

        if not cleaned:
            return None

        sw = ScrapedWebsite(
            candidate_id=candidate_id,
            website_url=website_url,
            backend="crawl_service",
        )
        sw.pages = cleaned
        logger.info(
            "[load_scraped_from_drive] %s: %d pages, %d chars from Drive",
            candidate_id, len(cleaned), sw.total_content_length,
        )
        return sw


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

        Optimized: single listing of site folder children, parallel file downloads.
        """
        pages: list[ScrapedPage] = []

        # Single API call to list all subfolders in the site folder
        all_children = await self._drive_list(session, site_folder_id, token)
        subfolder_map: dict[str, str] = {}
        for child in all_children:
            if child.get("mimeType") == "application/vnd.google-apps.folder":
                subfolder_map[child["name"]] = child["id"]

        async def _download_md(f: dict, page_type: str, title_prefix: str) -> ScrapedPage | None:
            try:
                raw = await self._drive_download(session, f["id"], token)
                text = raw.decode("utf-8", errors="replace").strip()
                if len(text) > 50:
                    title = f["name"].replace(".md", "").replace("-", " ").title()
                    if title_prefix:
                        title = f"{title_prefix} {title}"
                    return ScrapedPage(
                        url=f["name"], title=title,
                        content=text, page_type=page_type,
                    )
            except Exception as exc:
                logger.debug("[crawl_scraper] download failed %s: %s", f["name"], exc)
            return None

        # --- Priority 1: markdown/ folder ---
        md_folder_id = subfolder_map.get("markdown")
        if md_folder_id:
            md_files = await self._drive_list(session, md_folder_id, token)
            md_files = [f for f in md_files if f["name"].endswith(".md")]
            results = await asyncio.gather(*[_download_md(f, "html", "") for f in md_files])
            pages.extend(p for p in results if p)

        # --- Priority 2: pdf_markdown/ folder ---
        pdf_md_id = subfolder_map.get("pdf_markdown")
        if pdf_md_id:
            pdf_files = await self._drive_list(session, pdf_md_id, token)
            pdf_files = [f for f in pdf_files if f["name"].endswith(".md")]
            results = await asyncio.gather(*[_download_md(f, "pdf_transcription", "[PDF]") for f in pdf_files])
            pages.extend(p for p in results if p)

        # --- Priority 3: images/*/descriptions.json (OCR fallback) ---
        if not pages:
            images_id = subfolder_map.get("images")
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
        # Social media domains that block scrapers or produce junk content
        SKIP_DOMAINS = (
            "facebook.com", "fb.com", "instagram.com", "twitter.com",
            "x.com", "tiktok.com", "linkedin.com", "youtube.com",
        )
        unscraped: list[Candidate] = []
        skipped_social = 0
        async for doc in async_db.collection("candidates").stream():
            data = doc.to_dict()
            raw_url = (data.get("website_url") or "").strip()
            if not raw_url or not raw_url.startswith(("http://", "https://")) or (data.get("has_scraped") and not force):
                continue
            # Skip social media URLs — they block scrapers and waste resources
            domain = raw_url.split("//", 1)[-1].split("/", 1)[0].lower().removeprefix("www.")
            if any(domain == d or domain.endswith("." + d) for d in SKIP_DOMAINS):
                skipped_social += 1
                continue
            try:
                unscraped.append(Candidate(**data))
            except Exception as exc:
                logger.debug("[crawl_scraper] skip malformed %s: %s", doc.id, exc)

        if skipped_social:
            logger.info("[crawl_scraper] skipped %d social media URLs (Facebook/Instagram/etc.)", skipped_social)
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

            # --- 5. Status update before unified loop -----
            if not need_polling:
                logger.info("[crawl_scraper] all candidates already PROCESSED, downloading from Drive")
            await update_status(
                cfg.node_id, NodeStatus.RUNNING,
                counts={
                    "candidates_total": len(unscraped),
                    "submitted": len(to_submit),
                    "processed": len(processed_ids),
                    "downloaded": 0,
                    "download_total": len(tracked_ids),
                    "phase": "downloading" if not need_polling else "polling",
                },
            )

            # --- 5b. Unified poll + download loop --------------------------
            # Instead of polling all → waiting for Drive → downloading all,
            # we download each candidate's content as soon as its Drive folder
            # is detected.  This gives near-instant progress feedback.

            # Build URL map for Drive folder matching
            poll_url_map: dict[str, str] = {}
            for c in unscraped:
                if c.candidate_id in tracked_ids:
                    poll_url_map[c.candidate_id] = c.website_url or ""

            # Also build candidate lookup by id for fast access
            cand_by_id: dict[str, Any] = {
                c.candidate_id: c for c in unscraped if c.candidate_id in tracked_ids
            }

            drive_matched_ids: set[str] = set()
            downloaded_ids: set[str] = set()
            scraped_map: dict[str, ScrapedWebsite] = {}
            download_pages_total = 0
            download_chars_total = 0
            subfolders: list[dict[str, Any]] = []
            drive_ok = True

            async def _download_candidate(
                cid: str, folder: dict[str, Any],
            ) -> None:
                """Download a single candidate's content from Drive immediately."""
                nonlocal download_pages_total, download_chars_total
                candidate = cand_by_id[cid]
                url = poll_url_map.get(cid, candidate.website_url or "")
                sw = ScrapedWebsite(
                    candidate_id=cid,
                    website_url=url,
                    backend="crawl_service",
                )
                try:
                    tk = self._ensure_token(creds)
                    raw_pages = await self._download_crawl_content(
                        session, folder["id"], folder["name"], tk,
                    )
                    cleaned = _clean_scraped_pages(raw_pages)
                    sw.pages = cleaned
                    dropped = len(raw_pages) - len(cleaned)
                    download_pages_total += len(cleaned)
                    download_chars_total += sw.total_content_length
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
                scraped_map[cid] = sw
                downloaded_ids.add(cid)
                # Mark has_scraped in Firestore immediately (survives cancellation)
                if sw.is_successful:
                    try:
                        ref = async_db.collection("candidates").document(cid)
                        await ref.set({
                            "has_scraped": True,
                            "scrape_backend": "crawl_service",
                            "scrape_pages": len(sw.pages),
                            "scrape_chars": sw.total_content_length,
                        }, merge=True)
                    except Exception as exc:
                        logger.debug("[crawl_scraper] Firestore update failed %s: %s", cid, exc)
                # Update status after each download for live progress
                await update_status(
                    cfg.node_id, NodeStatus.RUNNING,
                    counts={
                        "candidates_total": len(unscraped),
                        "submitted": len(to_submit),
                        "processed": len(processed_ids),
                        "downloaded": len(downloaded_ids),
                        "download_total": len(tracked_ids),
                        "pages": download_pages_total,
                        "total_chars": download_chars_total,
                        "current": candidate.full_name,
                        "phase": "downloading",
                    },
                )

            # --- 5b. Unified download + poll loop ----------------------------
            # Always check Drive first and download what's available.
            # If some candidates still need polling, keep looping.
            deadline = _time.monotonic() + poll_timeout

            while _time.monotonic() < deadline:
                token = self._ensure_token(creds)

                # Check 1: Sheet PROCESSED status (only if some still need polling)
                if need_polling - processed_ids:
                    try:
                        rows = await self._fetch_sheet_rows(session, sheet_id, token)
                        for row in rows[1:]:
                            cid = _row_get(row, COL_CANDIDATE_ID)
                            status = _row_get(row, COL_STATUS)
                            if cid in tracked_ids and status.upper() == "PROCESSED":
                                processed_ids.add(cid)
                    except Exception as exc:
                        logger.warning("[crawl_scraper] poll error: %s", exc)

                # Check 2: Drive folders — download immediately on match
                try:
                    token = self._ensure_token(creds)
                    subfolders = await self._drive_list(
                        session, drive_folder_id, token,
                        mime_filter="application/vnd.google-apps.folder",
                        order_by="createdTime desc",
                    )

                    # Match all candidates to Drive folders first
                    download_tasks = []
                    for cid in list(tracked_ids - downloaded_ids):
                        url = poll_url_map.get(cid, "")
                        if not url:
                            continue
                        folder = self._match_url_to_folder(url, subfolders)
                        if folder:
                            if cid not in processed_ids:
                                drive_matched_ids.add(cid)
                            processed_ids.add(cid)
                            download_tasks.append(_download_candidate(cid, folder))

                    # Download up to 5 candidates concurrently
                    if download_tasks:
                        dl_sem = asyncio.Semaphore(5)
                        async def _throttled_dl(coro):
                            async with dl_sem:
                                return await coro
                        await asyncio.gather(*[_throttled_dl(t) for t in download_tasks])
                except Exception as exc:
                    logger.debug("[crawl_scraper] Drive check: %s", exc)

                still_waiting = tracked_ids - downloaded_ids
                phase = "downloading" if downloaded_ids else "polling"
                logger.info(
                    "[crawl_scraper] %d / %d downloaded, %d waiting (%d via Drive)",
                    len(downloaded_ids), len(tracked_ids),
                    len(still_waiting), len(drive_matched_ids),
                )
                await update_status(
                    cfg.node_id, NodeStatus.RUNNING,
                    counts={
                        "candidates_total": len(unscraped),
                        "submitted": len(to_submit),
                        "processed": len(processed_ids),
                        "downloaded": len(downloaded_ids),
                        "download_total": len(tracked_ids),
                        "drive_matched": len(drive_matched_ids),
                        "pages": download_pages_total,
                        "total_chars": download_chars_total,
                        "current": next(
                            (cand_by_id[c].full_name for c in list(downloaded_ids)[-1:]
                             if c in cand_by_id),
                            "",
                        ) if downloaded_ids else "",
                        "phase": phase,
                    },
                )

                if downloaded_ids >= tracked_ids:
                    logger.info("[crawl_scraper] all %d candidates downloaded", len(downloaded_ids))
                    break

                # If no new candidates were submitted (to_submit empty) and no
                # new downloads happened this iteration, the remaining candidates
                # simply have no Drive data — skip them instead of polling forever
                newly_submitted_pending = to_submit and (need_polling - processed_ids)
                if not newly_submitted_pending and not download_tasks:
                    no_drive = tracked_ids - downloaded_ids
                    logger.warning(
                        "[crawl_scraper] %d candidates have no Drive data, skipping: %s",
                        len(no_drive),
                        [cand_by_id[c].full_name for c in list(no_drive)[:5]],
                    )
                    break

                await asyncio.sleep(poll_interval)
            else:
                logger.warning(
                    "[crawl_scraper] timeout — %d / %d downloaded",
                    len(downloaded_ids), len(tracked_ids),
                )

            if not processed_ids and not downloaded_ids:
                logger.warning("[crawl_scraper] nothing processed, crawl service may be down")
                cfg.counts = {
                    "candidates_total": len(unscraped),
                    "submitted": len(to_submit),
                    "processed": 0,
                }
                put_context(CONTEXT_KEY, {})
                return cfg

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
