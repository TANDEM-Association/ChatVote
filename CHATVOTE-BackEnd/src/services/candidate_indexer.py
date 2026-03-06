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
import logging
import os
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
    CandidateWebsiteScraper,
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

    for page in scraped_website.pages:
        chunks = text_splitter.split_text(page.content)

        for chunk in chunks:
            cm = ChunkMetadata(
                namespace=candidate.candidate_id,
                source_document=f"candidate_website_{page.page_type}",
                party_ids=candidate.party_ids or [],
                candidate_ids=[candidate.candidate_id],
                candidate_name=candidate.full_name,
                municipality_code=candidate.municipality_code or "",
                municipality_name=candidate.municipality_name or "",
                election_type_id=candidate.election_type_id,
                document_name=f"{candidate.full_name} - {page.page_type.capitalize()}",
                url=page.url,
                page_title=page.title,
                page_type=page.page_type,
                page=chunk_index + 1,
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
) -> int:
    """
    Index a candidate's website content into Qdrant.

    If scraped_website is not provided, will scrape the website first.

    Returns the number of chunks indexed.
    """
    logger.info(
        f"Indexing website for candidate: {candidate.full_name} ({candidate.candidate_id})"
    )

    # Scrape if not provided
    if scraped_website is None:
        if not candidate.website_url:
            logger.warning(
                f"Candidate {candidate.candidate_id} has no website URL, skipping"
            )
            return 0

        scraper = CandidateWebsiteScraper()
        scraped_website = await scraper.scrape_candidate_website(candidate)

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
    documents = create_documents_from_scraped_website(candidate, scraped_website)

    if not documents:
        logger.warning(f"No documents created for candidate {candidate.candidate_id}")
        return 0

    logger.info(f"Created {len(documents)} chunks for {candidate.full_name}")

    # Delete existing documents for this candidate
    await delete_candidate_documents(candidate.candidate_id)

    # Index into Qdrant
    vector_store = _get_candidates_vector_store()

    # Add documents in batches
    batch_size = 50
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        await vector_store.aadd_documents(batch)
        logger.debug(
            f"Indexed batch {i // batch_size + 1} for {candidate.candidate_id}"
        )

    logger.info(
        f"Successfully indexed {len(documents)} chunks for {candidate.full_name}"
    )
    return len(documents)


async def index_all_candidates() -> dict[str, int]:
    """
    Index websites for all candidates with a website URL.

    Returns a dict of candidate_id -> number of chunks indexed.
    """
    logger.info("Starting indexation of all candidate websites...")

    candidates = await aget_candidates_with_website()
    logger.info(f"Found {len(candidates)} candidates with website URLs")

    results = {}

    # Scrape all websites first
    scraper = CandidateWebsiteScraper()
    scraped_websites = await scraper.scrape_multiple_candidates(
        candidates, max_concurrent=3
    )

    # Create a map of candidate_id -> scraped_website
    scraped_map = {sw.candidate_id: sw for sw in scraped_websites}

    # Index each candidate
    for candidate in candidates:
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
        f"Indexation complete: {total} total chunks for {successful}/{len(candidates)} candidates"
    )

    return results


async def index_candidate_by_id(candidate_id: str) -> int:
    """Index website for a specific candidate by ID."""
    candidate = await aget_candidate_by_id(candidate_id)
    if candidate is None:
        logger.error(f"Candidate {candidate_id} not found in Firestore")
        return 0

    return await index_candidate_website(candidate)


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
