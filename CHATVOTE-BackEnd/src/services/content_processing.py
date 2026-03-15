# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""Pure functions for content processing: filtering, chunking, source inference.

These functions have NO side effects (no I/O, no network, no Qdrant, no Firestore).
They are fully unit-testable without mocks.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from langchain_text_splitters import RecursiveCharacterTextSplitter

# ---------------------------------------------------------------------------
# Text splitter configs
# ---------------------------------------------------------------------------
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
LARGE_PAGE_THRESHOLD = 50_000  # pages > 50KB get larger chunks
LARGE_CHUNK_SIZE = 2000
LARGE_CHUNK_OVERLAP = 300
MAX_CHUNKS_PER_PAGE = 80  # cap to avoid one page dominating the index

_SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=_SEPARATORS,
)

large_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=LARGE_CHUNK_SIZE,
    chunk_overlap=LARGE_CHUNK_OVERLAP,
    length_function=len,
    separators=_SEPARATORS,
)


# ---------------------------------------------------------------------------
# Consent / cookie banner boilerplate
# ---------------------------------------------------------------------------
_CONSENT_BLOCK = re.compile(
    r"(?:Gérer le consentement|Gestion des cookies|Politique d'utilisation des cookies)"
    r".*?"
    r"(?:Toujours activ|Enregistrer les préférences|Accepter|Refuser|Tout accepter)",
    re.I | re.DOTALL,
)

# Accessibility widget boilerplate
_A11Y_WIDGET_PATTERNS = [
    re.compile(r"Disability profiles supported", re.I),
    re.compile(r"(WCAG|ADA|Section 508)\s+(2\.\d|compliance)", re.I),
    re.compile(r"screen.reader\s+adjustments", re.I),
    re.compile(r"Seizure Safe Profile", re.I),
    re.compile(r"keyboard navigation\s+(optimization|motor)", re.I),
    re.compile(r"shortcuts such as .M.\s*\(menus\)", re.I),
    re.compile(r"Accessible website.*UserWay", re.I),
]


def strip_consent_boilerplate(text: str) -> str:
    """Remove GDPR consent blocks from a chunk while keeping surrounding content."""
    cleaned = _CONSENT_BLOCK.sub("", text).strip()
    cleaned = re.sub(r"\s*Gérer le consentement\s*$", "", cleaned, flags=re.I).strip()
    return cleaned


def is_a11y_widget_chunk(text: str) -> bool:
    """Return True if the chunk is entirely accessibility widget boilerplate."""
    hits = sum(1 for pat in _A11Y_WIDGET_PATTERNS if pat.search(text))
    return hits >= 2


# ---------------------------------------------------------------------------
# Source document inference from page URL
# ---------------------------------------------------------------------------
_PROGRAMME_KEYWORDS = frozenset(
    ["programme", "projet", "propositions", "mesures", "priorites", "engagements"]
)
_ABOUT_KEYWORDS = frozenset(
    ["bilan", "realisations", "about", "qui-sommes", "equipe", "liste",
     "biographie", "candidat"]
)
_ACTUALITE_KEYWORDS = frozenset(
    ["actualite", "actualites", "actu", "news", "blog", "communique", "presse"]
)
_LEGAL_KEYWORDS = frozenset(
    ["mentions-legales", "politique-confidentialite", "cgu", "rgpd", "cookies"]
)


def infer_source_document(url: str, page_type: str, depth: int) -> str:
    """Infer a source_document type from the page URL, type, and depth.

    Args:
        url: Page URL.
        page_type: e.g. "html", "pdf_transcription", "social_bio", "social_post".
        depth: Crawl depth (0 = homepage).

    Returns:
        A source_document key recognized by ChunkMetadata fiabilité mapping.
    """
    # Social media pages get their own prefix
    if page_type in ("social_bio", "social_post"):
        return f"candidate_{page_type}"

    # Non-HTML pages keep the original type suffix
    if page_type != "html":
        return f"candidate_website_{page_type}"

    # Normalize URL path for keyword matching
    try:
        path = urlparse(url.lower()).path
    except Exception:
        path = url.lower()

    # Check legal/boilerplate pages first
    for kw in _LEGAL_KEYWORDS:
        if kw in path:
            return "candidate_website_html"

    for kw in _PROGRAMME_KEYWORDS:
        if kw in path:
            return "candidate_website_programme"

    for kw in _ABOUT_KEYWORDS:
        if kw in path:
            return "candidate_website_about"

    for kw in _ACTUALITE_KEYWORDS:
        if kw in path:
            return "candidate_website_actualite"

    # Homepage (depth 0) is treated as "about"
    if depth == 0:
        return "candidate_website_about"

    return "candidate_website_html"


# ---------------------------------------------------------------------------
# Content quality checks (used by profession indexer)
# ---------------------------------------------------------------------------
_FRENCH_WORD_RE = re.compile(r"[a-zA-ZÀ-ÿ]{2,}", re.UNICODE)
_FILE_ARTIFACT_RE = re.compile(r"\.\w{2,4}(?:\s|$)")
_MIN_REAL_WORDS = 10


def is_metadata_only(content: str) -> bool:
    """True if content looks like a filename/InDesign artifact rather than real text."""
    stripped = content.strip()
    if not stripped:
        return False

    stripped_lower = stripped.lower()

    if ".indd" in stripped_lower or "_bat." in stripped_lower or " bat." in stripped_lower:
        return True

    file_matches = _FILE_ARTIFACT_RE.findall(stripped)
    if file_matches:
        words = stripped.split()
        file_ratio = len(file_matches) / max(len(words), 1)
        if file_ratio > 0.5:
            return True

    real_words = _FRENCH_WORD_RE.findall(stripped)
    if len(real_words) < _MIN_REAL_WORDS:
        alpha_chars = sum(1 for c in stripped if c.isalpha())
        if len(stripped) > 0 and alpha_chars / len(stripped) < 0.3:
            return True

    return False


def is_real_content(pages: list[tuple[int, str]], min_words: int = 30) -> bool:
    """Check if extracted pages contain real French content."""
    full_text = " ".join(t for _, t in pages)
    real_words = _FRENCH_WORD_RE.findall(full_text)
    if len(real_words) < min_words:
        return False
    if is_metadata_only(full_text):
        return False
    return True


# ---------------------------------------------------------------------------
# Chunk filtering pipeline
# ---------------------------------------------------------------------------

class FilterStats:
    """Accumulates chunk filtering statistics."""

    __slots__ = ("kept", "dropped_short", "dropped_a11y", "dropped_dedup", "consent_stripped")

    def __init__(self) -> None:
        self.kept = 0
        self.dropped_short = 0
        self.dropped_a11y = 0
        self.dropped_dedup = 0
        self.consent_stripped = 0


def filter_chunks(
    raw_chunks: list[str],
    seen_hashes: set[str] | None = None,
    min_length: int = 30,
) -> tuple[list[str], FilterStats]:
    """Apply content filters to raw text chunks.

    Filters applied in order:
    1. Strip GDPR consent boilerplate
    2. Drop chunks shorter than min_length
    3. Drop accessibility widget chunks
    4. Deduplicate by MD5 hash

    Args:
        raw_chunks: Unfiltered text chunks.
        seen_hashes: Mutable set for cross-page dedup (pass the same set across pages).
        min_length: Minimum stripped length to keep a chunk.

    Returns:
        Tuple of (filtered_chunks, stats).
    """
    if seen_hashes is None:
        seen_hashes = set()

    stats = FilterStats()
    result: list[str] = []

    for chunk in raw_chunks:
        original = chunk
        chunk = strip_consent_boilerplate(chunk)
        if chunk != original:
            stats.consent_stripped += 1

        if len(chunk.strip()) < min_length:
            stats.dropped_short += 1
            continue

        if is_a11y_widget_chunk(chunk):
            stats.dropped_a11y += 1
            continue

        chunk_hash = hashlib.md5(chunk.strip().encode()).hexdigest()
        if chunk_hash in seen_hashes:
            stats.dropped_dedup += 1
            continue
        seen_hashes.add(chunk_hash)

        result.append(chunk)

    stats.kept = len(result)
    return result, stats


def split_page_content(
    content: str,
    *,
    cap: int = MAX_CHUNKS_PER_PAGE,
) -> list[str]:
    """Split a page's content into chunks using adaptive sizing.

    Large pages (>50KB) get bigger chunks to reduce total count.

    Returns:
        List of text chunks (before filtering).
    """
    splitter = large_text_splitter if len(content) > LARGE_PAGE_THRESHOLD else text_splitter
    chunks = splitter.split_text(content)
    if len(chunks) > cap:
        chunks = chunks[:cap]
    return chunks
