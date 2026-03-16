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
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
from urllib.parse import urlparse

import aiohttp

from src.services.data_pipeline.url_cache import cached_fetch
from src.services.candidate_website_scraper import ScrapedPage, ScrapedWebsite
from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeConfig,
    NodeStatus,
    put_context,
    register_node,
    save_checkpoint,
    update_status,
)

logger = logging.getLogger(__name__)

CONTEXT_KEY = "scraped_websites"

# ---------------------------------------------------------------------------
# Local cache — avoid re-downloading from Drive on subsequent runs
# ---------------------------------------------------------------------------
_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "crawl_scraped"


def _save_to_cache(cid: str, sw: ScrapedWebsite) -> None:
    """Persist a ScrapedWebsite to local JSON cache."""
    _t_cache_write = _time.monotonic()
    try:
        d = _CACHE_DIR / cid
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            "candidate_id": sw.candidate_id,
            "website_url": sw.website_url,
            "backend": sw.backend,
            "pages": [
                {"url": p.url, "title": p.title, "content": p.content, "page_type": p.page_type, "depth": p.depth}
                for p in sw.pages
            ],
        }
        (d / "scraped.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        logger.debug("[crawl:timing] cache_write(%s) took %.2fs, %d pages", cid, _time.monotonic() - _t_cache_write, len(sw.pages))
    except Exception as exc:
        logger.debug("[crawl_scraper] cache write failed for %s: %s", cid, exc)


def _load_from_cache(cid: str) -> ScrapedWebsite | None:
    """Load a ScrapedWebsite from local JSON cache, or None if missing."""
    _t_cache_read = _time.monotonic()
    try:
        path = _CACHE_DIR / cid / "scraped.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        sw = ScrapedWebsite(
            candidate_id=payload["candidate_id"],
            website_url=payload["website_url"],
            backend=payload.get("backend", "crawl_service"),
        )
        sw.pages = [
            ScrapedPage(
                url=p["url"], title=p["title"], content=p["content"],
                page_type=p["page_type"], depth=p.get("depth", 0),
            )
            for p in payload.get("pages", [])
        ]
        logger.debug("[crawl:timing] cache_read(%s) took %.2fs, %d pages", cid, _time.monotonic() - _t_cache_read, len(sw.pages))
        return sw
    except Exception as exc:
        logger.debug("[crawl_scraper] cache read failed for %s: %s", cid, exc)
        return None


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


_PAGINATION_PATTERN = re.compile(
    r"(?:category|categorie|tag|page|archive|actualit|evenement|event|blog|article)"
    r"[_\-].*?[_\-]?(?:page[_\-]?\d+)",
    re.I,
)

# Pages that are never useful for RAG — matched against filename/URL
_NOISE_PAGE_PATTERNS = [
    # Legal / privacy / cookies
    re.compile(r"(?:politique.de.cookies|cookie.?policy|declaration.de.confidentialite|privacy.?policy|mentions?.?legale|imprint|cgu|rgpd|gdpr)", re.I),
    # Fundraising / donation / lending / volunteer recruitment pages
    re.compile(r"(?:financer|pretez|prete[rz]|don(?:ation|er)|soutenir.campagne|merci.(?:de.soutenir|pret|beaucoup|pour.votre)|formu.?choix.montant|je.prete|action.pour.nous.aider)", re.I),
    # Event logistics / ballot logistics (not policy content)
    re.compile(r"(?:grand.meeting|etre.assesseur|bulletins?.de.vote|procuration)", re.I),
    # Support / endorsement lists (names, not policy)
    re.compile(r"(?:les.soutiens|comite.de.soutien|nos.soutiens|(?:liste|comit).*.soutien)", re.I),
    # Category listing pages (just links, no real content)
    re.compile(r"^category_", re.I),
    # Comparison tools / navigation pages
    re.compile(r"(?:comparateur.de.programme|comparatif)", re.I),
    # Contact / form confirmation pages
    re.compile(r"(?:^contact$|merci.?$|confirmation|formulaire.?envoy)", re.I),
    # Homepage / index (mostly navigation, cookie banners)
    re.compile(r"^index\.md$", re.I),
    # Candidate list pages (names, not policy)
    re.compile(r"(?:les.candidat|tetes?.de.liste|nos.candidat).*arrondissement", re.I),
]


def _is_noise_page(page: ScrapedPage) -> bool:
    """Return True if the page is non-political noise (legal, fundraising, cookies, etc.)."""
    name = page.url or ""
    return any(pat.search(name) for pat in _NOISE_PAGE_PATTERNS)


def _is_pagination_page(page: ScrapedPage) -> bool:
    """Return True if the page is a paginated listing (category_plans_page_13.md, etc.).

    These pages repeat the same listing template with different offsets — they add
    noise without new political content.  We keep page 1 (or no page number) and
    drop pages 2+.
    """
    # Check the filename / URL
    name = page.url or ""
    if _PAGINATION_PATTERN.search(name):
        return True
    # Also catch numeric-only page suffixes like blog-page-5.md
    if re.search(r"[_\-]page[_\-]?\d{1,4}(?:\.md)?$", name, re.I):
        # Keep page 1
        m = re.search(r"page[_\-]?(\d+)", name, re.I)
        if m and int(m.group(1)) > 1:
            return True
    return False


def _deduplicate_pages(pages: list[ScrapedPage]) -> list[ScrapedPage]:
    """Remove near-duplicate pages based on content fingerprint (first 500 chars)."""
    seen: set[str] = set()
    unique = []
    for page in pages:
        # Fingerprint: first 500 non-whitespace chars
        fp = re.sub(r"\s+", "", page.content[:500])
        if fp in seen:
            logger.debug("[crawl_scraper] dropping duplicate page: %s", page.url)
            continue
        seen.add(fp)
        unique.append(page)
    return unique


def _drop_aggregate_pages(pages: list[ScrapedPage]) -> list[ScrapedPage]:
    """Drop mega-pages that are aggregations of other pages already in the set.

    If a page is >100KB and >60% of its content is found in other smaller pages,
    it's an aggregate listing (e.g. 'prises-de-position' containing all 'notre-plan-*')
    and should be dropped to avoid massive redundancy.
    """
    AGGREGATE_THRESHOLD = 100_000  # only check pages > 100KB
    OVERLAP_RATIO = 0.6  # drop if >60% of content found in smaller pages

    large_pages = [p for p in pages if len(p.content) > AGGREGATE_THRESHOLD]
    if not large_pages:
        return pages

    small_pages = [p for p in pages if len(p.content) <= AGGREGATE_THRESHOLD]
    if not small_pages:
        return pages

    # Build a set of 100-char shingles from all small pages
    small_shingles: set[str] = set()
    for p in small_pages:
        text = re.sub(r"\s+", " ", p.content)
        for i in range(0, len(text) - 100, 50):
            small_shingles.add(text[i:i + 100])

    result = list(small_pages)
    for page in large_pages:
        text = re.sub(r"\s+", " ", page.content)
        total_shingles = max(1, (len(text) - 100) // 50)
        matched = sum(
            1 for i in range(0, len(text) - 100, 50)
            if text[i:i + 100] in small_shingles
        )
        overlap = matched / total_shingles
        if overlap > OVERLAP_RATIO:
            logger.info(
                "[crawl_scraper] dropping aggregate page: %s (%.0f%% overlap with smaller pages, %dKB)",
                page.url, overlap * 100, len(page.content) // 1024,
            )
        else:
            result.append(page)

    return result


def _clean_scraped_pages(pages: list[ScrapedPage]) -> list[ScrapedPage]:
    """Filter out junk pages and return only useful content."""
    _t_clean = _time.monotonic()
    cleaned = []
    dropped_junk = 0
    dropped_noise = 0
    dropped_pagination = 0
    for page in pages:
        if _is_junk_content(page.content):
            logger.debug("[crawl_scraper] dropping junk page: %s (len=%d)", page.url, len(page.content))
            dropped_junk += 1
            continue
        if _is_sitemap_xml(page.content):
            logger.debug("[crawl_scraper] dropping sitemap XML: %s", page.url)
            dropped_junk += 1
            continue
        if _is_social_media_wall(page.content, page.url):
            logger.debug("[crawl_scraper] dropping social media wall: %s", page.url)
            dropped_junk += 1
            continue
        if _is_noise_page(page):
            logger.debug("[crawl_scraper] dropping noise page: %s", page.url)
            dropped_noise += 1
            continue
        if _is_pagination_page(page):
            logger.debug("[crawl_scraper] dropping pagination page: %s", page.url)
            dropped_pagination += 1
            continue
        cleaned.append(page)
    # Deduplicate near-identical content
    before_dedup = len(cleaned)
    cleaned = _deduplicate_pages(cleaned)
    dropped_dupes = before_dedup - len(cleaned)
    # Drop aggregate mega-pages that duplicate smaller individual pages
    before_agg = len(cleaned)
    cleaned = _drop_aggregate_pages(cleaned)
    dropped_aggregate = before_agg - len(cleaned)
    if dropped_pagination or dropped_dupes or dropped_noise or dropped_aggregate:
        logger.info(
            "[crawl_scraper] content filter: %d kept, %d junk, %d noise, %d pagination, %d duplicates, %d aggregate",
            len(cleaned), dropped_junk, dropped_noise, dropped_pagination, dropped_dupes, dropped_aggregate,
        )
    logger.info(
        "[crawl:timing] clean_scraped_pages took %.2fs, %d in → %d out",
        _time.monotonic() - _t_clean, len(pages), len(cleaned),
    )
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
COL_DRIVE_FOLDER = 16   # column Q
COL_CRAWL_STATUS = 17   # column R

SHEET_RANGE = "Feuil1!A:K"
SHEET_RANGE_WIDE = "Feuil1!A:R"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_crawl_credentials():
    """Build Google SA credentials with Sheets (read+write) and Drive (read) scopes."""
    from google.auth.transport.requests import Request
    from google.oauth2.service_account import Credentials

    import base64
    b64 = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_BASE64", "")
    raw = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_JSON", "")
    if b64:
        raw = base64.b64decode(b64).decode()
    elif not raw:
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
        _t_creds = _time.monotonic()
        creds = _get_crawl_credentials()
        logger.info("[crawl:timing] load_scraped_from_drive get_credentials took %.2fs", _time.monotonic() - _t_creds)
    except Exception:
        return None

    node = CrawlScraperNode()
    if drive_folder_id is None:
        drive_folder_id = node.default_settings["drive_folder_id"]

    slug = _slugify_url(website_url)
    if not slug:
        return None

    logger.info(
        "[load_scraped_from_drive] %s url=%s slug=%s drive_folder_id=%s",
        candidate_id, website_url, slug, drive_folder_id,
    )

    async with aiohttp.ClientSession() as session:
        token = node._ensure_token(creds)

        # Find the candidate's subfolder by URL slug
        try:
            _t_subfolders = _time.monotonic()
            subfolders = await node._drive_list(session, drive_folder_id, token,
                mime_filter="application/vnd.google-apps.folder")
            logger.info("[crawl:timing] load_scraped_from_drive drive_list_subfolders took %.2fs (%d folders)", _time.monotonic() - _t_subfolders, len(subfolders))
        except Exception as exc:
            logger.warning("[load_scraped_from_drive] Drive list failed: %s", exc)
            return None

        # Match slug to folder name — collect all matches, prefer latest
        candidates_folders = sorted(
            [f for f in subfolders if f["name"] == slug or slug in f["name"]],
            key=lambda f: f.get("createdTime", ""),
            reverse=True,  # newest first
        )

        if not candidates_folders:
            logger.warning(
                "[load_scraped_from_drive] no slug match for %s (slug=%s, %d folders in Drive, sample=%s)",
                candidate_id, slug, len(subfolders),
                [f["name"] for f in subfolders[:5]],
            )
            return None

        # Try each matching folder (newest first) until we find one with content
        site_folder = None
        for cf in candidates_folders:
            token = node._ensure_token(creds)
            _t_cf = _time.monotonic()
            cf_children = await node._drive_list(session, cf["id"], token)
            logger.info("[crawl:timing] load_scraped_from_drive drive_list_cf_children(%s) took %.2fs", cf["name"], _time.monotonic() - _t_cf)
            has_content = any(
                c["name"] in ("markdown", "pdf_markdown", "pages")
                for c in cf_children if "folder" in c.get("mimeType", "")
            )
            if has_content:
                site_folder = cf
                break

        if not site_folder:
            logger.warning(
                "[load_scraped_from_drive] no folder with content for %s (slug=%s, %d folder matches checked)",
                candidate_id, slug, len(candidates_folders),
            )
            return None

        # Download content
        try:
            token = node._ensure_token(creds)
            _t_dl = _time.monotonic()
            raw_pages = await node._download_crawl_content(
                session, site_folder["id"], site_folder["name"], token,
            )
            logger.info("[crawl:timing] load_scraped_from_drive download_crawl_content took %.2fs", _time.monotonic() - _t_dl)
            _t_clean = _time.monotonic()
            cleaned = _clean_scraped_pages(raw_pages)
            logger.info("[crawl:timing] load_scraped_from_drive clean_scraped_pages took %.2fs", _time.monotonic() - _t_clean)
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
        _t_fetch = _time.monotonic()
        url = f"{SHEETS_API_URL}/{sheet_id}/values/{SHEET_RANGE}"
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
        rows = data.get("values", [])
        logger.info("[crawl:timing] fetch_sheet_rows took %.2fs, %d rows", _time.monotonic() - _t_fetch, len(rows))
        return rows

    async def _append_rows(
        self,
        session: aiohttp.ClientSession,
        sheet_id: str,
        token: str,
        new_rows: list[list[str]],
    ) -> None:
        if not new_rows:
            return
        _t_append = _time.monotonic()
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
        logger.info("[crawl:timing] append_rows took %.2fs, %d rows appended", _time.monotonic() - _t_append, len(new_rows))

    async def _batch_update_cells(
        self,
        session: aiohttp.ClientSession,
        sheet_id: str,
        token: str,
        updates: list[dict],
    ) -> int:
        """Batch update arbitrary cells. Each item: {"range": "Feuil1!R2", "values": [["val"]]}."""
        if not updates:
            return 0
        url = f"{SHEETS_API_URL}/{sheet_id}/values:batchUpdate"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        body = {"valueInputOption": "RAW", "data": updates}
        async with session.post(url, headers=headers, json=body) as resp:
            resp.raise_for_status()
            data = await resp.json()
        return data.get("totalUpdatedCells", 0)

    async def _sync_crawl_status_to_sheet(
        self,
        session: aiohttp.ClientSession,
        sheet_id: str,
        token: str,
        *,
        processed_ids: set[str],
        downloaded_ids: set[str],
        drive_folder_map: dict[str, tuple[str, str]],
    ) -> None:
        """Write crawl_status (col R) and drive_folder (col Q) for tracked candidates.

        drive_folder_map: {candidate_id: (folder_name, folder_id)}
        """
        _t_sync = _time.monotonic()
        try:
            rows = await self._fetch_sheet_rows_wide(session, sheet_id, token)
        except Exception as exc:
            logger.debug("[crawl_scraper] status sync sheet read failed: %s", exc)
            return

        SOCIAL_DOMAINS = (
            "facebook.com", "fb.com", "instagram.com", "twitter.com",
            "x.com", "tiktok.com", "linkedin.com", "youtube.com",
        )
        updates: list[dict] = []

        for i, row in enumerate(rows[1:], 2):  # sheet row 2+
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

            if crawl_status != current_r:
                updates.append({"range": f"Feuil1!R{i}", "values": [[crawl_status]]})

            # Also fill drive_folder (col Q) if we have it
            if cid in drive_folder_map and not current_q:
                _fname, fid = drive_folder_map[cid]
                drive_url = f"https://drive.google.com/drive/folders/{fid}"
                updates.append({"range": f"Feuil1!Q{i}", "values": [[drive_url]]})

        if updates:
            updated = await self._batch_update_cells(session, sheet_id, token, updates)
            logger.info("[crawl_scraper] synced %d cells to sheet (Q+R)", updated)
        logger.info(
            "[crawl:timing] sync_crawl_status_to_sheet took %.2fs, %d updates",
            _time.monotonic() - _t_sync, len(updates),
        )

    async def _fetch_sheet_rows_wide(
        self, session: aiohttp.ClientSession, sheet_id: str, token: str
    ) -> list[list[str]]:
        """Fetch sheet with columns A through R."""
        _t_fetch_wide = _time.monotonic()
        url = f"{SHEETS_API_URL}/{sheet_id}/values/{SHEET_RANGE_WIDE}"
        headers = {"Authorization": f"Bearer {token}"}
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()
        rows = data.get("values", [])
        logger.info("[crawl:timing] fetch_sheet_rows_wide took %.2fs, %d rows", _time.monotonic() - _t_fetch_wide, len(rows))
        return rows

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
        """List children of a Shared Drive folder (with pagination)."""
        q = f"'{folder_id}' in parents and trashed=false"
        if mime_filter:
            q += f" and mimeType='{mime_filter}'"
        base_url = (
            f"{DRIVE_API_URL}/files"
            f"?q={q}"
            f"&fields=nextPageToken,files(id,name,mimeType,size,createdTime)"
            f"&pageSize={page_size}"
            "&supportsAllDrives=true&includeItemsFromAllDrives=true"
        )
        if order_by:
            base_url += f"&orderBy={order_by}"
        headers = {"Authorization": f"Bearer {token}"}
        all_files: list[dict[str, Any]] = []
        page_token: str | None = None
        page_num = 0
        while True:
            url = base_url
            if page_token:
                url += f"&pageToken={page_token}"
            _t_page = _time.monotonic()
            # Drive API listings are dynamic — never cache them
            raw = await cached_fetch(session, url, headers=headers, skip_cache=True)
            if raw is None:
                break
            data = json.loads(raw)
            batch = data.get("files", [])
            all_files.extend(batch)
            page_num += 1
            logger.debug(
                "[crawl:timing] drive_list page %d took %.2fs, %d files (folder=%s)",
                page_num, _time.monotonic() - _t_page, len(batch), folder_id,
            )
            page_token = data.get("nextPageToken")
            if not page_token:
                break
        return all_files

    async def _drive_download(
        self,
        session: aiohttp.ClientSession,
        file_id: str,
        token: str,
    ) -> bytes:
        _t_dl = _time.monotonic()
        url = f"{DRIVE_API_URL}/files/{file_id}?alt=media&supportsAllDrives=true"
        headers = {"Authorization": f"Bearer {token}"}
        data = await cached_fetch(session, url, headers=headers)
        if data is None:
            raise RuntimeError(f"Drive download failed for file {file_id}")
        logger.debug(
            "[crawl:timing] drive_download(%s) took %.2fs, %d bytes",
            file_id, _time.monotonic() - _t_dl, len(data),
        )
        return data

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
        Uses report.csv to map .md filenames back to original source URLs.
        """
        pages: list[ScrapedPage] = []

        # Single API call to list all subfolders in the site folder
        _t_list_children = _time.monotonic()
        all_children = await self._drive_list(session, site_folder_id, token)
        logger.info("[crawl:timing] download_content_list_children took %.2fs", _time.monotonic() - _t_list_children)
        subfolder_map: dict[str, str] = {}
        report_file_id: str | None = None
        for child in all_children:
            if child.get("mimeType") == "application/vnd.google-apps.folder":
                subfolder_map[child["name"]] = child["id"]
            elif child["name"] == "report.csv":
                report_file_id = child["id"]

        # --- Parallel phase 1: list subfolders + download report.csv simultaneously ---
        import csv as _csv
        import io as _io
        import posixpath as _posixpath

        _t_parallel_prep = _time.monotonic()

        async def _fetch_report_csv() -> dict[str, str]:
            """Download and parse report.csv → {filename: source_url}."""
            if not report_file_id:
                return {}
            try:
                raw_csv = await self._drive_download(session, report_file_id, token)
                mapping: dict[str, str] = {}
                reader = _csv.DictReader(
                    _io.StringIO(raw_csv.decode("utf-8", errors="replace"))
                )
                for row in reader:
                    saved_as = row.get("saved_as", "")
                    source_url = row.get("url", "")
                    if saved_as and source_url:
                        mapping[_posixpath.basename(saved_as)] = source_url
                logger.info("[crawl_scraper] report.csv: %d filename→URL mappings loaded", len(mapping))
                return mapping
            except Exception as exc:
                logger.warning("[crawl_scraper] report.csv parse failed: %s", exc)
                return {}

        async def _list_subfolder(name: str) -> list[dict]:
            fid = subfolder_map.get(name)
            if not fid:
                return []
            files = await self._drive_list(session, fid, token)
            return [f for f in files if f["name"].endswith(".md")]

        # Fire all 3 in parallel: report.csv + markdown/ listing + pdf_markdown/ listing
        url_map_result, md_files, pdf_files = await asyncio.gather(
            _fetch_report_csv(),
            _list_subfolder("markdown"),
            _list_subfolder("pdf_markdown"),
        )
        url_map: dict[str, str] = url_map_result
        logger.info(
            "[crawl:timing] parallel_prep (report.csv + list markdown + list pdf_markdown) took %.2fs, md=%d pdf=%d",
            _time.monotonic() - _t_parallel_prep, len(md_files), len(pdf_files),
        )

        def _resolve_url(filename: str, text: str) -> str:
            source_url = url_map.get(filename, "")
            if not source_url:
                m = re.search(r">\s*Source:\s*(https?://\S+)", text)
                source_url = m.group(1) if m else ""
            # Only keep real HTTP(S) URLs — never store .md filenames
            if source_url and not source_url.startswith(("http://", "https://")):
                source_url = ""
            return source_url

        async def _download_md(f: dict, page_type: str, title_prefix: str) -> ScrapedPage | None:
            _t_md_file = _time.monotonic()
            try:
                raw = await self._drive_download(session, f["id"], token)
                text = raw.decode("utf-8", errors="replace").strip()
                if len(text) > 50:
                    title = f["name"].replace(".md", "").replace("-", " ").title()
                    if title_prefix:
                        title = f"{title_prefix} {title}"
                    source_url = _resolve_url(f["name"], text)
                    logger.debug(
                        "[crawl:timing] download_md(%s) took %.2fs, %d chars",
                        f["name"], _time.monotonic() - _t_md_file, len(text),
                    )
                    return ScrapedPage(
                        url=source_url, title=title,
                        content=text, page_type=page_type,
                    )
            except Exception as exc:
                logger.debug("[crawl_scraper] download failed %s: %s", f["name"], exc)
            return None

        # --- Parallel phase 2: download ALL .md files from both folders at once ---
        _t_all_downloads = _time.monotonic()
        all_download_tasks = [
            *[_download_md(f, "html", "") for f in md_files],
            *[_download_md(f, "pdf_transcription", "[PDF]") for f in pdf_files],
        ]
        if all_download_tasks:
            results = await asyncio.gather(*all_download_tasks)
            pages.extend(p for p in results if p)
        logger.info(
            "[crawl:timing] parallel_download_all_md took %.2fs, %d tasks → %d pages",
            _time.monotonic() - _t_all_downloads, len(all_download_tasks), len(pages),
        )

        # --- Priority 3: images/*/descriptions.json (OCR fallback) ---
        if not pages:
            images_id = subfolder_map.get("images")
            if images_id:
                _t_ocr = _time.monotonic()
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
                logger.info("[crawl:timing] download_content_ocr_fallback took %.2fs", _time.monotonic() - _t_ocr)

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
        _t_match = _time.monotonic()
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
            logger.debug(
                "[crawl:timing] match_url_to_folder checked %d folders, no match, took %.3fs (url=%s)",
                len(subfolders), _time.monotonic() - _t_match, website_url,
            )
            return None

        # Return most recent match
        matches.sort(key=lambda x: x.get("createdTime", ""), reverse=True)
        logger.debug(
            "[crawl:timing] match_url_to_folder checked %d folders, found match '%s', took %.3fs",
            len(subfolders), matches[0]["name"], _time.monotonic() - _t_match,
        )
        return matches[0]

    # -----------------------------------------------------------------------
    # Refresh token helper
    # -----------------------------------------------------------------------

    def _ensure_token(self, creds) -> str:
        if not creds.valid:
            _t_refresh = _time.monotonic()
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            logger.info("[crawl:timing] token_refresh took %.2fs", _time.monotonic() - _t_refresh)
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

        # --- 1. Get candidates from Firestore --------------------------------
        logger.info("[crawl_scraper] fetching candidates from Firestore")
        # Social media domains that block scrapers or produce junk content
        SKIP_DOMAINS = (
            "facebook.com", "fb.com", "instagram.com", "twitter.com",
            "x.com", "tiktok.com", "linkedin.com", "youtube.com",
        )
        unscraped: list[Candidate] = []
        already_scraped_candidates: list[Candidate] = []
        skipped_social = 0
        _t_firestore_scan = _time.monotonic()
        async for doc in async_db.collection("candidates").stream():
            data = doc.to_dict()
            raw_url = (data.get("website_url") or "").strip()
            if not raw_url or not raw_url.startswith(("http://", "https://")):
                continue
            # Skip social media URLs — they block scrapers and waste resources
            domain = raw_url.split("//", 1)[-1].split("/", 1)[0].lower().removeprefix("www.")
            if any(domain == d or domain.endswith("." + d) for d in SKIP_DOMAINS):
                skipped_social += 1
                continue
            try:
                cand = Candidate(**data)
            except Exception as exc:
                logger.debug("[crawl_scraper] skip malformed %s: %s", doc.id, exc)
                continue
            if data.get("has_scraped") and not force:
                already_scraped_candidates.append(cand)
            else:
                unscraped.append(cand)

        logger.info("[crawl:timing] step1_firestore_candidate_scan took %.2fs, found %d unscraped + %d already scraped", _time.monotonic() - _t_firestore_scan, len(unscraped), len(already_scraped_candidates))
        if skipped_social:
            logger.info("[crawl_scraper] skipped %d social media URLs (Facebook/Instagram/etc.)", skipped_social)
        logger.info("[crawl_scraper] %d unscraped candidates with websites", len(unscraped))

        # Filter to top communes only
        from src.services.data_pipeline.population import get_top_communes
        top_communes = get_top_communes()
        if top_communes:
            top_codes = set(top_communes.keys())
            before = len(unscraped)
            unscraped = [
                c for c in unscraped
                if (c.municipality_code or "") in top_codes
            ]
            already_scraped_candidates = [
                c for c in already_scraped_candidates
                if (c.municipality_code or "") in top_codes
            ]
            logger.info(
                "[crawl_scraper] filtered to top communes: %d -> %d unscraped, %d already scraped",
                before, len(unscraped), len(already_scraped_candidates),
            )

        if not unscraped and not already_scraped_candidates:
            cfg.counts = {"candidates_total": 0, "submitted": 0, "processed": 0}
            put_context(CONTEXT_KEY, {})
            return cfg

        # If nothing new to scrape but we have cached data, load it and return
        if not unscraped:
            _t_cache = _time.monotonic()
            scraped_map: dict[str, ScrapedWebsite] = {}
            for cand in already_scraped_candidates:
                sw = _load_from_cache(cand.candidate_id)
                if sw and sw.is_successful:
                    scraped_map[cand.candidate_id] = sw
            logger.info(
                "[crawl_scraper] no new candidates — loaded %d/%d from cache (%.2fs)",
                len(scraped_map), len(already_scraped_candidates), _time.monotonic() - _t_cache,
            )
            put_context(CONTEXT_KEY, scraped_map)
            total_pages = sum(len(sw.pages) for sw in scraped_map.values())
            total_chars = sum(sw.total_content_length for sw in scraped_map.values())
            cfg.counts = {
                "candidates_total": len(already_scraped_candidates),
                "submitted": 0, "processed": 0, "cached": len(scraped_map),
                "with_content": len(scraped_map), "pages": total_pages, "total_chars": total_chars,
            }
            return cfg

        if len(unscraped) > max_candidates:
            logger.info("[crawl_scraper] capping to %d (found %d)", max_candidates, len(unscraped))
            unscraped = unscraped[:max_candidates]

        # --- 2. Credentials ------------------------------------------------
        _t_step2 = _time.monotonic()
        creds = _get_crawl_credentials()
        token = creds.token
        logger.info("[crawl:timing] step2_credentials took %.2fs", _time.monotonic() - _t_step2)

        async with aiohttp.ClientSession() as session:
            # --- 3. Read sheet: find already-processed and new candidates ----
            existing_ids: set[str] = set()
            already_processed_ids: set[str] = set()
            try:
                _t_step3 = _time.monotonic()
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
                logger.info("[crawl:timing] step3_sheet_read took %.2fs, %d rows", _time.monotonic() - _t_step3, len(rows))
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
                _t_step4 = _time.monotonic()
                await self._append_rows(session, sheet_id, token, new_rows)
                logger.info("[crawl:timing] step4_sheet_append took %.2fs, %d rows", _time.monotonic() - _t_step4, len(new_rows))
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
            drive_folder_map: dict[str, tuple[str, str]] = {}  # cid → (name, id)
            download_pages_total = 0
            download_chars_total = 0
            subfolders: list[dict[str, Any]] = []

            async def _download_candidate(
                cid: str, folder: dict[str, Any],
            ) -> None:
                """Download a single candidate's content from Drive immediately."""
                nonlocal download_pages_total, download_chars_total
                _t_candidate_total = _time.monotonic()
                candidate = cand_by_id[cid]
                url = poll_url_map.get(cid, candidate.website_url or "")
                sw = ScrapedWebsite(
                    candidate_id=cid,
                    website_url=url,
                    backend="crawl_service",
                )
                try:
                    tk = self._ensure_token(creds)
                    _t_dl_content = _time.monotonic()
                    raw_pages = await self._download_crawl_content(
                        session, folder["id"], folder["name"], tk,
                    )
                    logger.info("[crawl:timing] download_content(%s) took %.2fs", cid, _time.monotonic() - _t_dl_content)
                    _t_dl_clean = _time.monotonic()
                    cleaned = _clean_scraped_pages(raw_pages)
                    logger.info("[crawl:timing] clean_pages(%s) took %.2fs", cid, _time.monotonic() - _t_dl_clean)
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
                # Cache locally so next run skips Drive download
                if sw.is_successful:
                    _save_to_cache(cid, sw)
                # Mark has_scraped in Firestore immediately (survives cancellation)
                if sw.is_successful:
                    try:
                        _t_fs_update = _time.monotonic()
                        ref = async_db.collection("candidates").document(cid)
                        await ref.set({
                            "has_scraped": True,
                            "scrape_backend": "crawl_service",
                            "scrape_pages": len(sw.pages),
                            "scrape_chars": sw.total_content_length,
                        }, merge=True)
                        logger.info("[crawl:timing] firestore_update(%s) took %.2fs", cid, _time.monotonic() - _t_fs_update)
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
                logger.info(
                    "[crawl:timing] download_candidate(%s / %s) total took %.2fs, %d pages",
                    candidate.full_name, cid,
                    _time.monotonic() - _t_candidate_total, len(sw.pages),
                )

            # --- 5b. Unified download + poll loop ----------------------------
            # Always check Drive first and download what's available.
            # If some candidates still need polling, keep looping.
            deadline = _time.monotonic() + poll_timeout

            while _time.monotonic() < deadline:
                _t_poll_iter = _time.monotonic()
                token = self._ensure_token(creds)

                # Check 1: Sheet PROCESSED status (only if some still need polling)
                if need_polling - processed_ids:
                    try:
                        _t_poll_sheet = _time.monotonic()
                        rows = await self._fetch_sheet_rows(session, sheet_id, token)
                        logger.info("[crawl:timing] poll_sheet_check took %.2fs", _time.monotonic() - _t_poll_sheet)
                        for row in rows[1:]:
                            cid = _row_get(row, COL_CANDIDATE_ID)
                            status = _row_get(row, COL_STATUS)
                            if cid in tracked_ids and status.upper() == "PROCESSED":
                                processed_ids.add(cid)
                    except Exception as exc:
                        logger.warning("[crawl_scraper] poll error: %s", exc)

                # Check 2: Drive folders — download immediately on match
                download_tasks = []
                try:
                    token = self._ensure_token(creds)
                    _t_poll_drive = _time.monotonic()
                    subfolders = await self._drive_list(
                        session, drive_folder_id, token,
                        mime_filter="application/vnd.google-apps.folder",
                        order_by="createdTime desc",
                    )
                    logger.info("[crawl:timing] poll_drive_list took %.2fs, %d folders", _time.monotonic() - _t_poll_drive, len(subfolders))

                    # Match all candidates to Drive folders first
                    for cid in list(tracked_ids - downloaded_ids):
                        url = poll_url_map.get(cid, "")
                        if not url:
                            continue
                        folder = self._match_url_to_folder(url, subfolders)
                        if folder:
                            if cid not in processed_ids:
                                drive_matched_ids.add(cid)
                            processed_ids.add(cid)
                            drive_folder_map[cid] = (folder["name"], folder["id"])
                            download_tasks.append(_download_candidate(cid, folder))

                    # Download up to 5 candidates concurrently
                    if download_tasks:
                        dl_sem = asyncio.Semaphore(5)
                        async def _throttled_dl(coro):
                            async with dl_sem:
                                return await coro
                        _t_poll_dl = _time.monotonic()
                        await asyncio.gather(*[_throttled_dl(t) for t in download_tasks])
                        logger.info("[crawl:timing] poll_downloads took %.2fs, %d candidates", _time.monotonic() - _t_poll_dl, len(download_tasks))
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

                # Sync crawl status + drive_folder to sheet columns Q & R
                try:
                    token = self._ensure_token(creds)
                    _t_poll_sync = _time.monotonic()
                    await self._sync_crawl_status_to_sheet(
                        session, sheet_id, token,
                        processed_ids=processed_ids,
                        downloaded_ids=downloaded_ids,
                        drive_folder_map=drive_folder_map,
                    )
                    logger.info("[crawl:timing] poll_sheet_sync took %.2fs", _time.monotonic() - _t_poll_sync)
                except Exception as exc:
                    logger.debug("[crawl_scraper] status sync failed: %s", exc)

                logger.info("[crawl:timing] poll_iteration took %.2fs (processed=%d, downloaded=%d)", _time.monotonic() - _t_poll_iter, len(processed_ids), len(downloaded_ids))

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
            _t_step8 = _time.monotonic()
            _step8_count = 0
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
                    _step8_count += 1
                except Exception as exc:
                    logger.debug(
                        "[crawl_scraper] Firestore update failed %s: %s",
                        candidate.candidate_id, exc,
                    )
            logger.info("[crawl:timing] step8_firestore_updates took %.2fs, %d candidates", _time.monotonic() - _t_step8, _step8_count)

        # --- 8b. Mark ALL sheet-PROCESSED candidates as scraped in Firestore -
        # The crawl service may have processed hundreds of candidates across
        # previous runs.  Sync their has_scraped flag so the coverage page
        # reflects reality (not just this batch of max_candidates).
        _t_step8b = _time.monotonic()
        bulk_marked = 0
        for cid in already_processed_ids - tracked_ids:
            try:
                ref = async_db.collection("candidates").document(cid)
                await ref.update(
                    {"has_scraped": True, "scrape_backend": "crawl_service"},
                )
                bulk_marked += 1
            except Exception:
                pass  # doc doesn't exist — skip (don't create stubs)
        logger.info("[crawl:timing] step8b_bulk_mark took %.2fs, %d marked", _time.monotonic() - _t_step8b, bulk_marked)
        if bulk_marked:
            logger.info(
                "[crawl_scraper] bulk-marked %d previously PROCESSED candidates as has_scraped",
                bulk_marked,
            )

        # --- 9. Load cached data for already-scraped candidates ---------------
        _t_cache_load = _time.monotonic()
        cached_count = 0
        for cand in already_scraped_candidates:
            cid = cand.candidate_id
            if cid in scraped_map:
                continue  # already downloaded this run
            sw = _load_from_cache(cid)
            if sw and sw.is_successful:
                scraped_map[cid] = sw
                cached_count += 1
        logger.info(
            "[crawl_scraper] loaded %d/%d already-scraped candidates from local cache (%.2fs)",
            cached_count, len(already_scraped_candidates), _time.monotonic() - _t_cache_load,
        )

        # --- 10. Pipeline context and return --------------------------------
        put_context(CONTEXT_KEY, scraped_map)

        total_pages = sum(len(sw.pages) for sw in scraped_map.values())
        total_chars = sum(sw.total_content_length for sw in scraped_map.values())
        with_content = sum(1 for sw in scraped_map.values() if sw.is_successful)

        cfg.counts = {
            "candidates_total": len(unscraped) + len(already_scraped_candidates),
            "submitted": len(to_submit),
            "processed": len(processed_ids),
            "cached": cached_count,
            "with_content": with_content,
            "pages": total_pages,
            "total_chars": total_chars,
        }

        cfg.checkpoints["cached_at"] = datetime.now(timezone.utc).isoformat()
        await save_checkpoint(cfg.node_id, cfg.checkpoints)  # noqa: F821

        cfg.cache_info = [
            {
                "label": "Scraped candidate pages",
                "local_dir": str(_CACHE_DIR),
            }
        ]

        _total_elapsed = _time.monotonic() - _t_firestore_scan
        logger.info(
            "[crawl_scraper] done — %d processed, %d with content, %d pages, %d chars",
            len(processed_ids), with_content, total_pages, total_chars,
        )
        logger.info(
            "[crawl:timing:summary] CRAWL_SCRAPER total=%.1fs | candidates_total=%d "
            "submitted=%d processed=%d downloaded=%d cached=%d with_content=%d "
            "pages=%d chars=%d",
            _total_elapsed,
            len(unscraped) + len(already_scraped_candidates),
            len(to_submit), len(processed_ids), len(downloaded_ids),
            cached_count, with_content, total_pages, total_chars,
        )

        return cfg


register_node(CrawlScraperNode())


# ---------------------------------------------------------------------------
# Drive cleanup: detect & trash failed crawl folders
# ---------------------------------------------------------------------------

_CONTENT_SUBFOLDERS = {"markdown", "pdf_markdown", "pages"}


async def detect_failed_drive_folders(
    drive_folder_id: str | None = None,
    *,
    dry_run: bool = True,
) -> dict:
    """Scan Google Drive for failed crawl folders (no usable content).

    A folder is considered "failed" if it has NO subfolders named
    markdown, pdf_markdown, or pages — typically only images/ or placeholder.txt.

    Args:
        drive_folder_id: Override the default Drive folder ID.
        dry_run: If True (default), only report. If False, trash the folders.

    Returns dict with keys: failed, trashed, total_scanned, errors.
    """
    try:
        creds = _get_crawl_credentials()
    except Exception as exc:
        return {"error": str(exc), "failed": [], "trashed": 0, "total_scanned": 0}

    node = CrawlScraperNode()
    if drive_folder_id is None:
        drive_folder_id = node.default_settings["drive_folder_id"]

    failed: list[dict] = []
    errors: list[str] = []
    total_scanned = 0
    trashed = 0

    async with aiohttp.ClientSession() as session:
        token = node._ensure_token(creds)

        # List all top-level subfolders
        try:
            subfolders = await node._drive_list(
                session, drive_folder_id, token,
                mime_filter="application/vnd.google-apps.folder",
            )
        except Exception as exc:
            return {"error": f"Drive list failed: {exc}", "failed": [], "trashed": 0, "total_scanned": 0}

        total_scanned = len(subfolders)
        logger.info("[drive_cleanup] scanning %d folders for failed crawls", total_scanned)

        for sf in subfolders:
            token = node._ensure_token(creds)
            try:
                children = await node._drive_list(session, sf["id"], token)
                child_folder_names = {
                    c["name"] for c in children
                    if "folder" in c.get("mimeType", "")
                }

                has_content = bool(child_folder_names & _CONTENT_SUBFOLDERS)
                if has_content:
                    continue

                # Check for any non-trivial files (report.csv counts as content)
                file_names = [c["name"] for c in children if "folder" not in c.get("mimeType", "")]
                has_report = "report.csv" in file_names

                entry = {
                    "id": sf["id"],
                    "name": sf["name"],
                    "created": sf.get("createdTime", ""),
                    "child_folders": sorted(child_folder_names),
                    "files": sorted(file_names),
                    "has_report": has_report,
                    "empty": len(children) == 0,
                }
                failed.append(entry)

                if not dry_run:
                    try:
                        token = node._ensure_token(creds)
                        # Trash the folder (recoverable via Drive trash)
                        async with session.patch(
                            f"https://www.googleapis.com/drive/v3/files/{sf['id']}",
                            headers={"Authorization": f"Bearer {token}"},
                            json={"trashed": True},
                            params={"supportsAllDrives": "true"},
                        ) as resp:
                            if resp.status == 200:
                                trashed += 1
                                logger.info("[drive_cleanup] trashed %s (%s)", sf["name"], sf["id"])
                            else:
                                errors.append(f"Trash {sf['name']}: HTTP {resp.status}")
                    except Exception as exc:
                        errors.append(f"Trash {sf['name']}: {exc}")

            except Exception as exc:
                errors.append(f"Scan {sf['name']}: {exc}")

    logger.info(
        "[drive_cleanup] done — %d/%d failed, %d trashed, %d errors",
        len(failed), total_scanned, trashed, len(errors),
    )
    return {
        "failed": failed,
        "trashed": trashed,
        "total_scanned": total_scanned,
        "dry_run": dry_run,
        "errors": errors,
    }
