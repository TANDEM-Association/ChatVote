# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Service to index party manifestos (election programs) into Qdrant vector store.

This service:
1. Reads PDFs directly from Firebase Storage URLs (in memory, no disk download)
2. Extracts text using pypdf
3. Chunks the text
4. Creates embeddings
5. Indexes into Qdrant with namespace = party_id
"""

import asyncio
import io
import logging
from typing import Optional

import aiohttp
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from src.models.party import Party
from src.firebase_service import aget_parties, aget_party_by_id
from src.services.chunk_classifier import classify_chunks_themes
from src.vector_store_helper import (
    get_qdrant_vector_store,
    qdrant_client,
    PARTY_INDEX_NAME,
)

logger = logging.getLogger(__name__)

# Text splitter configuration
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""],
)


async def fetch_pdf_content(url: str) -> Optional[bytes]:
    """Fetch PDF content from URL into memory."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to fetch PDF from {url}: {response.status}")
                    return None
                return await response.read()
    except Exception as e:
        logger.error(f"Error fetching PDF from {url}: {e}")
        return None


def extract_pages_from_pdf(pdf_content: bytes) -> list[tuple[int, str]]:
    """Extract text from PDF bytes, returning [(1-indexed page_num, text), ...]."""
    try:
        pdf_file = io.BytesIO(pdf_content)
        reader = PdfReader(pdf_file)
        pages = []
        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text and page_text.strip():
                pages.append((page_num, page_text))
        return pages
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return []


def extract_text_from_pdf(pdf_content: bytes) -> str:
    """Legacy wrapper — use extract_pages_from_pdf for page-aware chunking."""
    pages = extract_pages_from_pdf(pdf_content)
    return "\n\n".join(text for _, text in pages)


def create_documents_from_pages(
    pages: list[tuple[int, str]],
    party: Party,
    source_url: str,
) -> list[Document]:
    """Split pages into chunks preserving real PDF page numbers."""
    from src.models.chunk_metadata import ChunkMetadata

    documents = []
    chunk_index = 0

    for page_num, page_text in pages:
        chunks = text_splitter.split_text(page_text)
        for chunk in chunks:
            cm = ChunkMetadata(
                namespace=party.party_id,
                source_document="election_manifesto",
                party_ids=[party.party_id],
                party_name=party.name,
                document_name=f"{party.name} - Programme électoral",
                url=source_url,
                page=page_num,
                chunk_index=chunk_index,
                total_chunks=0,
            )
            doc = Document(page_content=chunk, metadata=cm.to_qdrant_payload())
            documents.append(doc)
            chunk_index += 1

    for doc in documents:
        doc.metadata["total_chunks"] = len(documents)

    return documents


def create_documents_from_text(
    text: str,
    party: Party,
    source_url: str,
) -> list[Document]:
    """Legacy wrapper — use create_documents_from_pages for page-aware chunking."""
    pages = [(1, text)] if text else []
    return create_documents_from_pages(pages, party, source_url)


async def delete_party_documents(party_id: str) -> int:
    """Delete all existing documents for a party from Qdrant."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector

    try:
        # Delete points with matching namespace
        qdrant_client.delete(
            collection_name=PARTY_INDEX_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.namespace",
                            match=MatchValue(value=party_id),
                        )
                    ]
                )
            ),
        )
        logger.info(f"Deleted existing documents for party {party_id}")
        return 1
    except Exception as e:
        logger.error(f"Error deleting documents for party {party_id}: {e}")
        return 0


async def index_party_manifesto(party: Party) -> int:
    """
    Index a party's manifesto into Qdrant.

    Returns the number of chunks indexed.
    """
    if not party.election_manifesto_url:
        logger.warning(f"Party {party.party_id} has no manifesto URL, skipping")
        return 0

    logger.info(f"Indexing manifesto for party: {party.name} ({party.party_id})")

    # Step 1: Fetch PDF from URL
    pdf_content = await fetch_pdf_content(party.election_manifesto_url)
    if not pdf_content:
        logger.error(f"Could not fetch PDF for party {party.party_id}")
        return 0

    logger.info(f"Fetched PDF ({len(pdf_content)} bytes) for {party.party_id}")

    # Step 2: Extract pages
    pages = extract_pages_from_pdf(pdf_content)
    if not pages:
        logger.error(f"Could not extract text from PDF for party {party.party_id}")
        return 0

    total_chars = sum(len(t) for _, t in pages)
    logger.info(f"Extracted {total_chars} chars from {len(pages)} pages for {party.party_id}")

    # Step 3: Create documents (chunks with real page numbers)
    documents = create_documents_from_pages(
        pages=pages,
        party=party,
        source_url=party.election_manifesto_url,
    )

    if not documents:
        logger.warning(f"No documents created for party {party.party_id}")
        return 0

    logger.info(f"Created {len(documents)} chunks for {party.party_id}")

    # Step 4: Classify themes (optional — degrades gracefully)
    try:
        chunk_texts = [doc.page_content for doc in documents]
        classifications = await classify_chunks_themes(chunk_texts)
        for doc, cls in zip(documents, classifications, strict=True):
            if cls.theme:
                doc.metadata["theme"] = cls.theme
            if cls.sub_theme:
                doc.metadata["sub_theme"] = cls.sub_theme
        logger.info(f"Theme classification complete for {party.party_id}")
    except Exception as e:
        logger.warning(f"Theme classification skipped for {party.party_id}: {e}")

    # Step 5: Delete existing documents for this party
    await delete_party_documents(party.party_id)

    # Step 6: Index into Qdrant
    vector_store = get_qdrant_vector_store()

    # Add documents in batches to avoid memory issues
    batch_size = 50
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        await vector_store.aadd_documents(batch)
        logger.debug(f"Indexed batch {i//batch_size + 1} for {party.party_id}")

    logger.info(f"Successfully indexed {len(documents)} chunks for {party.name}")
    return len(documents)


async def index_all_parties() -> dict[str, int]:
    """
    Index manifestos for all parties in Firestore.

    Returns a dict of party_id -> number of chunks indexed.
    """
    logger.info("Starting indexation of all party manifestos...")

    parties = await aget_parties()
    results = {}

    for party in parties:
        try:
            count = await index_party_manifesto(party)
            results[party.party_id] = count
        except Exception as e:
            logger.error(f"Error indexing party {party.party_id}: {e}")
            results[party.party_id] = 0

    total = sum(results.values())
    logger.info(f"Indexation complete: {total} total chunks for {len(parties)} parties")

    return results


async def index_party_by_id(party_id: str) -> int:
    """Index manifesto for a specific party by ID."""
    party = await aget_party_by_id(party_id)
    if not party:
        logger.error(f"Party {party_id} not found in Firestore")
        return 0

    return await index_party_manifesto(party)


# CLI entry point
def main() -> None:
    """CLI entry point to index all existing parties."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    print("🚀 Starting manifesto indexation for all parties...")

    try:
        results = asyncio.run(index_all_parties())

        print("\n📊 Results:")
        for party_id, count in results.items():
            status = "✅" if count > 0 else "❌"
            print(f"  {status} {party_id}: {count} chunks")

        total = sum(results.values())
        print(f"\n🎉 Total: {total} chunks indexed for {len(results)} parties")

    except Exception as e:
        logger.error(f"Indexation failed: {e}", exc_info=True)
        print(f"❌ Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
