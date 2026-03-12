# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Service to index candidate website content into Qdrant vector store.

This service:
1. Takes scraped website content from candidates
2. Chunks the text content
3. Creates embeddings
4. Indexes into Qdrant with namespace = candidate_id and metadata for filtering
"""

import asyncio
import hashlib
import logging
import os
import re
from typing import List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    VectorParams,
)

from src.models.candidate import Candidate
from src.firebase_service import (
    aget_candidates_with_website,
    aget_candidate_by_id,
)
from src.services.candidate_website_scraper import (
    ScrapedWebsite,
)
from src.vector_store_helper import qdrant_client, embed, EMBEDDING_DIM

logger = logging.getLogger(__name__)

# Get environment suffix for collection name
env = os.getenv("ENV", "dev")
env_suffix = f"_{env}" if env in ["prod", "dev"] else "_dev"
CANDIDATES_INDEX_NAME = f"candidates_websites{env_suffix}"

# Text splitter configuration
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""],
)


# ---------------------------------------------------------------------------
# Chunk-level content filtering (runs AFTER splitting, before embedding)
# ---------------------------------------------------------------------------

# Consent / cookie banner boilerplate — strip from chunks that also have real content.
# These are French GDPR cookie consent blocks scraped from every page.
_CONSENT_BLOCK = re.compile(
    r"(?:Gérer le consentement|Gestion des cookies|Politique d'utilisation des cookies)"
    r".*?"
    r"(?:Toujours activ|Enregistrer les préférences|Accepter|Refuser|Tout accepter)",
    re.I | re.DOTALL,
)

# Accessibility widget boilerplate — entire chunk is widget UI text
_A11Y_WIDGET_PATTERNS = [
    re.compile(r"Disability profiles supported", re.I),
    re.compile(r"(WCAG|ADA|Section 508)\s+(2\.\d|compliance)", re.I),
    re.compile(r"screen.reader\s+adjustments", re.I),
    re.compile(r"Seizure Safe Profile", re.I),
    re.compile(r"keyboard navigation\s+(optimization|motor)", re.I),
    re.compile(r"shortcuts such as .M.\s*\(menus\)", re.I),
    re.compile(r"Accessible website.*UserWay", re.I),
]


def _strip_consent_boilerplate(text: str) -> str:
    """Remove GDPR consent blocks from a chunk while keeping surrounding content."""
    cleaned = _CONSENT_BLOCK.sub("", text).strip()
    # Also strip trailing "Gérer le consentement" that appears as a footer link
    cleaned = re.sub(r"\s*Gérer le consentement\s*$", "", cleaned, flags=re.I).strip()
    return cleaned


def _is_a11y_widget_chunk(text: str) -> bool:
    """Return True if the chunk is entirely accessibility widget boilerplate."""
    hits = sum(1 for pat in _A11Y_WIDGET_PATTERNS if pat.search(text))
    # Need at least 2 matches to be confident it's widget text, not a mention
    return hits >= 2


# URL path segments → source_document type (checked left to right, first match wins)
_PROGRAMME_KEYWORDS = frozenset(
    ["programme", "projet", "propositions", "mesures", "priorites", "engagements"]
)
_ABOUT_KEYWORDS = frozenset(
    [
        "bilan",
        "realisations",
        "about",
        "qui-sommes",
        "equipe",
        "liste",
        "biographie",
        "candidat",
    ]
)
_ACTUALITE_KEYWORDS = frozenset(
    ["actualite", "actualites", "actu", "news", "blog", "communique", "presse"]
)
_LEGAL_KEYWORDS = frozenset(
    ["mentions-legales", "politique-confidentialite", "cgu", "rgpd", "cookies"]
)


def _infer_source_document(page) -> str:  # page: ScrapedPage
    """
    Infer a specific source_document type from the page URL, title, and depth.

    Maps to the keys recognised by _SOURCE_FIABILITE_MAP in chunk_metadata.py:
      candidate_website_programme  → OFFICIAL (2)
      candidate_website_about      → OFFICIAL (2)
      candidate_website_actualite  → PRESS    (3)
      candidate_website_html       → PRESS    (3) fallback
    PDFs keep their original page_type suffix (e.g. pdf_transcription).
    """
    # Non-HTML pages (pdf, sitemap, …) keep the original type suffix as-is.
    if page.page_type != "html":
        return f"candidate_website_{page.page_type}"

    # Normalise the URL path for keyword matching.
    url_lower = page.url.lower()
    # Strip scheme + host so we only look at path segments.
    try:
        from urllib.parse import urlparse as _urlparse

        path = _urlparse(url_lower).path
    except Exception:
        path = url_lower

    # Check legal / boilerplate pages first so we can fall through to html.
    for kw in _LEGAL_KEYWORDS:
        if kw in path:
            return "candidate_website_html"  # legal pages → generic fallback

    for kw in _PROGRAMME_KEYWORDS:
        if kw in path:
            return "candidate_website_programme"

    for kw in _ABOUT_KEYWORDS:
        if kw in path:
            return "candidate_website_about"

    for kw in _ACTUALITE_KEYWORDS:
        if kw in path:
            return "candidate_website_actualite"

    # Homepage (depth 0) is treated as "about".
    if page.depth == 0:
        return "candidate_website_about"

    return "candidate_website_html"


def _ensure_candidates_collection_exists() -> None:
    """Ensure the candidates Qdrant collection exists."""
    try:
        collections = qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]

        if CANDIDATES_INDEX_NAME not in collection_names:
            logger.info(f"Creating Qdrant collection: {CANDIDATES_INDEX_NAME}")
            qdrant_client.create_collection(
                collection_name=CANDIDATES_INDEX_NAME,
                vectors_config={
                    "dense": VectorParams(
                        size=EMBEDDING_DIM,
                        distance=Distance.COSINE,
                    )
                },
            )

            # Create payload indexes for efficient filtering
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.namespace",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.municipality_code",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.candidate_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            # New indexes for unified metadata
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.party_ids",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.candidate_ids",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.fiabilite",
                field_schema=PayloadSchemaType.INTEGER,
            )
            qdrant_client.create_payload_index(
                collection_name=CANDIDATES_INDEX_NAME,
                field_name="metadata.theme",
                field_schema=PayloadSchemaType.KEYWORD,
            )

            logger.info(f"Collection {CANDIDATES_INDEX_NAME} created with indexes")
        else:
            logger.debug(f"Collection {CANDIDATES_INDEX_NAME} already exists")
    except Exception as e:
        logger.error(f"Error ensuring collection {CANDIDATES_INDEX_NAME} exists: {e}")
        raise


def _get_candidates_vector_store():
    """Get the Qdrant vector store for candidates."""
    from langchain_qdrant import QdrantVectorStore

    _ensure_candidates_collection_exists()
    return QdrantVectorStore(
        client=qdrant_client,
        collection_name=CANDIDATES_INDEX_NAME,
        embedding=embed,
        vector_name="dense",
        content_payload_key="page_content",
    )


def create_documents_from_scraped_website(
    candidate: Candidate,
    scraped_website: ScrapedWebsite,
) -> List[Document]:
    """Create LangChain documents from scraped website content using ChunkMetadata."""
    from src.models.chunk_metadata import ChunkMetadata

    documents = []
    chunk_index = 0
    seen_hashes: set[str] = set()  # dedup within a candidate

    if not candidate.party_ids:
        logger.warning(
            f"Candidate {candidate.candidate_id} has no party_ids — "
            f"party-based filtering will not find this candidate's chunks"
        )

    for page in scraped_website.pages:
        chunks = text_splitter.split_text(page.content)

        for chunk in chunks:
            # Strip consent boilerplate (keeps surrounding content)
            chunk = _strip_consent_boilerplate(chunk)

            if len(chunk.strip()) < 30:
                continue

            # Drop accessibility widget chunks
            if _is_a11y_widget_chunk(chunk):
                continue

            # Deduplicate — skip chunks we've already seen for this candidate
            chunk_hash = hashlib.md5(chunk.strip().encode()).hexdigest()
            if chunk_hash in seen_hashes:
                continue
            seen_hashes.add(chunk_hash)

            cm = ChunkMetadata(
                namespace=candidate.candidate_id,
                source_document=_infer_source_document(page),
                party_ids=candidate.party_ids or [],
                candidate_ids=[candidate.candidate_id],
                candidate_name=candidate.full_name,
                municipality_code=candidate.municipality_code or "",
                municipality_name=candidate.municipality_name or "",
                election_type_id=candidate.election_type_id,
                is_incumbent=candidate.is_incumbent or None,
                is_tete_de_liste=(candidate.position == "Tête de liste") or None,
                document_name=f"{candidate.full_name} - {page.page_type.capitalize()}",
                url=page.url,
                page_title=page.title,
                page_type=page.page_type,
                page=0,  # No real page number for scraped websites
                chunk_index=chunk_index,
                total_chunks=0,
            )
            doc = Document(page_content=chunk, metadata=cm.to_qdrant_payload())
            documents.append(doc)
            chunk_index += 1

    for doc in documents:
        doc.metadata["total_chunks"] = len(documents)

    return documents


async def delete_candidate_documents(candidate_id: str) -> None:
    """Delete all existing documents for a candidate from Qdrant."""
    try:
        _ensure_candidates_collection_exists()
        qdrant_client.delete(
            collection_name=CANDIDATES_INDEX_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.namespace",
                            match=MatchValue(value=candidate_id),
                        )
                    ]
                )
            ),
        )
        logger.info(f"Deleted existing documents for candidate {candidate_id}")
    except Exception as e:
        logger.error(f"Error deleting documents for candidate {candidate_id}: {e}")


async def index_candidate_website(
    candidate: Candidate,
    scraped_website: Optional[ScrapedWebsite] = None,
    *,
    classify_themes: bool = True,
) -> int:
    """
    Index a candidate's website content into Qdrant.

    If scraped_website is not provided, will scrape the website first.

    Returns the number of chunks indexed.
    """
    import time as _t
    _t0 = _t.monotonic()

    logger.info(
        f"Indexing website for candidate: {candidate.full_name} ({candidate.candidate_id})"
    )

    # scraped_website is required — caller must provide it (from Drive)
    if scraped_website is None:
        logger.warning(
            f"No scraped data provided for {candidate.candidate_id} ({candidate.full_name}), skipping"
        )
        return 0

    if not scraped_website.is_successful:
        logger.error(
            f"Could not scrape website for candidate {candidate.candidate_id}: {scraped_website.error}"
        )
        return 0

    logger.info(
        f"Scraped {len(scraped_website.pages)} pages "
        f"({scraped_website.total_content_length} chars) for {candidate.full_name}"
    )

    # Create documents from scraped content
    _ts = _t.monotonic()
    documents = create_documents_from_scraped_website(candidate, scraped_website)
    logger.info(f"[TIMING] chunk {candidate.full_name}: {_t.monotonic()-_ts:.1f}s — {len(documents)} chunks")

    if not documents:
        logger.warning(f"No documents created for candidate {candidate.candidate_id}")
        return 0

    # Classify themes (LLM-primary with keyword fast-path) — optional, adds 20-45s
    if classify_themes:
        _ts = _t.monotonic()
        try:
            from src.services.theme_classifier import classify_chunks, apply_themes_to_documents
            chunk_texts = [doc.page_content for doc in documents]
            theme_results = await classify_chunks(chunk_texts)
            apply_themes_to_documents(documents, theme_results)
            classified = sum(1 for r in theme_results if r.theme is not None)
            logger.info(
                f"[TIMING] theme classify {candidate.full_name}: {_t.monotonic()-_ts:.1f}s — "
                f"{classified}/{len(documents)} classified"
            )
        except Exception as e:
            logger.warning(
                f"[TIMING] theme classify {candidate.full_name}: {_t.monotonic()-_ts:.1f}s — "
                f"FAILED: {e}"
            )
    else:
        logger.info(f"[indexer] theme classification skipped for {candidate.full_name}")

    # Delete existing documents for this candidate
    _ts = _t.monotonic()
    await delete_candidate_documents(candidate.candidate_id)
    logger.info(f"[TIMING] delete old docs {candidate.full_name}: {_t.monotonic()-_ts:.1f}s")

    # Index into Qdrant
    _ts = _t.monotonic()
    vector_store = _get_candidates_vector_store()

    # Add documents in batches
    batch_size = 50
    for i in range(0, len(documents), batch_size):
        _tb = _t.monotonic()
        batch = documents[i : i + batch_size]
        await vector_store.aadd_documents(batch)
        logger.info(
            f"[TIMING] embed+upload batch {i // batch_size + 1} ({len(batch)} docs) "
            f"{candidate.full_name}: {_t.monotonic()-_tb:.1f}s"
        )
    logger.info(f"[TIMING] total embed+upload {candidate.full_name}: {_t.monotonic()-_ts:.1f}s")

    logger.info(
        f"[TIMING] TOTAL {candidate.full_name}: {_t.monotonic()-_t0:.1f}s — "
        f"{len(documents)} chunks indexed"
    )
    return len(documents)


def _get_indexed_candidate_counts() -> dict[str, int]:
    """Return {candidate_id: chunk_count} for candidates already in Qdrant."""
    try:
        _ensure_candidates_collection_exists()
        counts: dict[str, int] = {}
        offset = None
        while True:
            results, next_offset = qdrant_client.scroll(
                collection_name=CANDIDATES_INDEX_NAME,
                limit=256,
                offset=offset,
                with_payload=["metadata.namespace"],
                with_vectors=False,
            )
            if not results:
                break
            for point in results:
                ns = (point.payload or {}).get("metadata", {}).get("namespace", "")
                if ns:
                    counts[ns] = counts.get(ns, 0) + 1
            if next_offset is None:
                break
            offset = next_offset
        return counts
    except Exception as e:
        logger.warning(f"Could not check existing candidates in Qdrant: {e}")
        return {}


async def index_all_candidates(
    scraper_backend: str = "auto",
    force: bool = False,
) -> dict[str, int]:
    """
    Index websites for all candidates with a website URL.

    Skips candidates already indexed in Qdrant (saves scraping credits).
    Use force=True to re-scrape and re-index everything.

    Args:
        scraper_backend: "auto" (use Firecrawl if key is set, else Playwright),
                         "firecrawl", or "playwright".
        force: If True, re-scrape all candidates even if already indexed.

    Returns a dict of candidate_id -> number of chunks indexed.
    """
    logger.info("Starting indexation of all candidate websites...")

    candidates = await aget_candidates_with_website()
    logger.info(f"Found {len(candidates)} candidates with website URLs")

    # Check which candidates are already indexed
    existing = _get_indexed_candidate_counts() if not force else {}
    if existing:
        logger.info(
            f"Already indexed: {len(existing)} candidates "
            f"({sum(existing.values())} chunks). Skipping these."
        )

    # Filter to only candidates that need scraping
    to_scrape = [c for c in candidates if c.candidate_id not in existing]
    already_done = {cid: count for cid, count in existing.items()}

    if not to_scrape:
        logger.info("All candidates already indexed, nothing to do.")
        return already_done

    logger.info(f"Need to scrape: {len(to_scrape)} candidates")

    results = dict(already_done)

    # Use Drive data first, fall back to Firecrawl (no Playwright)
    from src.services.data_pipeline.crawl_scraper import load_scraped_from_drive

    scraped_websites: list[ScrapedWebsite] = []
    drive_loaded = 0

    for c in to_scrape:
        if c.website_url:
            sw = await load_scraped_from_drive(c.candidate_id, c.website_url)
            if sw and sw.is_successful:
                scraped_websites.append(sw)
                drive_loaded += 1
                continue
        # Firecrawl fallback for candidates not in Drive
        firecrawl_key = os.getenv("FIRECRAWL_API_KEY", "")
        if firecrawl_key:
            try:
                from src.services.firecrawl_scraper import FirecrawlScraper
                scraper = FirecrawlScraper(api_key=firecrawl_key)
                sw = await scraper.scrape_candidate_website(c)
                scraped_websites.append(sw)
            except Exception as exc:
                logger.warning(f"Firecrawl failed for {c.candidate_id}: {exc}")
        else:
            logger.warning(f"No Drive data and no FIRECRAWL_API_KEY for {c.candidate_id}, skipping")

    logger.info(f"Loaded {drive_loaded} from Drive, {len(scraped_websites) - drive_loaded} from Firecrawl")

    # Create a map of candidate_id -> scraped_website
    scraped_map = {sw.candidate_id: sw for sw in scraped_websites}

    # Index each candidate
    for candidate in to_scrape:
        try:
            scraped_website = scraped_map.get(candidate.candidate_id)
            count = await index_candidate_website(candidate, scraped_website)
            results[candidate.candidate_id] = count
        except Exception as e:
            logger.error(f"Error indexing candidate {candidate.candidate_id}: {e}")
            results[candidate.candidate_id] = 0

    total = sum(results.values())
    successful = sum(1 for v in results.values() if v > 0)
    logger.info(
        f"Indexation complete: {total} total chunks for {successful}/{len(results)} candidates "
        f"({len(existing)} were already indexed)"
    )

    return results


async def index_candidate_by_id(candidate_id: str) -> int:
    """Index website for a specific candidate by ID (loads from Drive)."""
    candidate = await aget_candidate_by_id(candidate_id)
    if candidate is None:
        logger.error(f"Candidate {candidate_id} not found in Firestore")
        return 0

    scraped_website = None
    if candidate.website_url:
        from src.services.data_pipeline.crawl_scraper import load_scraped_from_drive
        scraped_website = await load_scraped_from_drive(candidate.candidate_id, candidate.website_url)

    return await index_candidate_website(candidate, scraped_website)


async def index_candidates_by_municipality(municipality_code: str) -> dict[str, int]:
    """Index websites for all candidates in a specific municipality."""
    from src.firebase_service import aget_candidates_by_municipality

    candidates = await aget_candidates_by_municipality(municipality_code)
    candidates_with_website = [c for c in candidates if c.website_url]

    logger.info(
        f"Found {len(candidates_with_website)} candidates with websites "
        f"in municipality {municipality_code}"
    )

    results = {}
    for candidate in candidates_with_website:
        try:
            count = await index_candidate_website(candidate)
            results[candidate.candidate_id] = count
        except Exception as e:
            logger.error(f"Error indexing candidate {candidate.candidate_id}: {e}")
            results[candidate.candidate_id] = 0

    return results


# CLI entry point
def main() -> None:
    """CLI entry point to index all candidate websites."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("Starting candidate website indexation...")

    try:
        results = asyncio.run(index_all_candidates())

        print("\nResults:")
        for candidate_id, count in sorted(results.items()):
            status = "OK" if count > 0 else "FAILED"
            print(f"  [{status}] {candidate_id}: {count} chunks")

        total = sum(results.values())
        successful = sum(1 for v in results.values() if v > 0)
        print(
            f"\nTotal: {total} chunks indexed for {successful}/{len(results)} candidates"
        )

    except Exception as e:
        logger.error(f"Indexation failed: {e}", exc_info=True)
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
