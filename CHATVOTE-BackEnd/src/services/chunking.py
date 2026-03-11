"""
Unified chunking and document creation.

Single source of truth for splitting text into chunks and creating
LangChain Documents with ChunkMetadata. Consolidates the four
previous implementations in manifesto_indexer, candidate_indexer,
document_upload, and index_election_posters.

Usage:
    from src.services.chunking import (
        create_documents_from_text,
        create_documents_from_pages,
        batch_index,
    )

    # From flat text (websites, uploads, OCR output)
    docs = create_documents_from_text(
        text="...",
        namespace="party_id",
        source_document="election_manifesto",
        party_ids=["lfi"],
        party_name="La France Insoumise",
    )

    # From page-aware extraction (PDF manifestos)
    docs = create_documents_from_pages(
        pages=[(1, "page 1 text"), (2, "page 2 text")],
        namespace="party_id",
        source_document="election_manifesto",
        party_ids=["lfi"],
        party_name="La France Insoumise",
    )

    # Index into Qdrant
    await batch_index(vector_store, docs, batch_size=50)
"""

import logging
from typing import Any, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.models.chunk_metadata import ChunkMetadata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared chunking configuration — identical across all pipelines
# ---------------------------------------------------------------------------

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MIN_CHUNK_LENGTH = 30

SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=SEPARATORS,
)


# ---------------------------------------------------------------------------
# Document creation
# ---------------------------------------------------------------------------

def create_documents_from_text(
    text: str,
    *,
    namespace: str,
    source_document: str,
    # Entity references
    party_ids: Optional[list[str]] = None,
    candidate_ids: Optional[list[str]] = None,
    # Display info
    party_name: Optional[str] = None,
    candidate_name: Optional[str] = None,
    municipality_code: Optional[str] = None,
    municipality_name: Optional[str] = None,
    municipality_postal_code: Optional[str] = None,
    # Source info
    document_name: Optional[str] = None,
    url: Optional[str] = None,
    page_title: Optional[str] = None,
    page_type: Optional[str] = None,
    # Extra metadata kwargs passed to ChunkMetadata
    **extra_metadata: Any,
) -> list[Document]:
    """Split text into chunks and create Documents with ChunkMetadata.

    This is the primary entry point for flat text (no page boundaries).
    All chunks get page=0.
    """
    return create_documents_from_pages(
        pages=[(0, text)] if text else [],
        namespace=namespace,
        source_document=source_document,
        party_ids=party_ids,
        candidate_ids=candidate_ids,
        party_name=party_name,
        candidate_name=candidate_name,
        municipality_code=municipality_code,
        municipality_name=municipality_name,
        municipality_postal_code=municipality_postal_code,
        document_name=document_name,
        url=url,
        page_title=page_title,
        page_type=page_type,
        **extra_metadata,
    )


def create_documents_from_pages(
    pages: list[tuple[int, str]],
    *,
    namespace: str,
    source_document: str,
    # Entity references
    party_ids: Optional[list[str]] = None,
    candidate_ids: Optional[list[str]] = None,
    # Display info
    party_name: Optional[str] = None,
    candidate_name: Optional[str] = None,
    municipality_code: Optional[str] = None,
    municipality_name: Optional[str] = None,
    municipality_postal_code: Optional[str] = None,
    # Source info
    document_name: Optional[str] = None,
    url: Optional[str] = None,
    page_title: Optional[str] = None,
    page_type: Optional[str] = None,
    # Extra metadata kwargs passed to ChunkMetadata
    **extra_metadata: Any,
) -> list[Document]:
    """Split page texts into chunks preserving page numbers.

    Args:
        pages: List of (page_number, page_text) tuples. Use page=0 for
               sources without real page numbers (websites, OCR).
        namespace: Primary entity ID (party_id or candidate_id).
        source_document: Source type key for fiabilite inference.
        **extra_metadata: Additional fields passed to ChunkMetadata
            (e.g., election_type_id, is_tete_de_liste, nuance_politique).

    Returns:
        List of LangChain Documents with metadata from ChunkMetadata.
    """
    documents: list[Document] = []
    chunk_index = 0

    # Build base metadata kwargs (shared across all chunks)
    base_meta = {
        "namespace": namespace,
        "source_document": source_document,
        "party_ids": party_ids or [],
        "candidate_ids": candidate_ids or [],
        "document_name": document_name,
        "url": url,
        "page_title": page_title,
        "page_type": page_type,
    }
    # Only include non-None display fields
    if party_name is not None:
        base_meta["party_name"] = party_name
    if candidate_name is not None:
        base_meta["candidate_name"] = candidate_name
    if municipality_code is not None:
        base_meta["municipality_code"] = municipality_code
    if municipality_name is not None:
        base_meta["municipality_name"] = municipality_name
    if municipality_postal_code is not None:
        base_meta["municipality_postal_code"] = municipality_postal_code

    # Merge extra metadata (election_type_id, is_tete_de_liste, etc.)
    base_meta.update(extra_metadata)

    for page_num, page_text in pages:
        chunks = text_splitter.split_text(page_text)
        for chunk in chunks:
            if len(chunk.strip()) < MIN_CHUNK_LENGTH:
                continue

            cm = ChunkMetadata(
                **base_meta,
                page=page_num,
                chunk_index=chunk_index,
                total_chunks=0,  # filled below
            )
            doc = Document(
                page_content=chunk,
                metadata=cm.to_qdrant_payload(),
            )
            documents.append(doc)
            chunk_index += 1

    # Fill total_chunks now that we know the count
    for doc in documents:
        doc.metadata["total_chunks"] = len(documents)

    return documents


# ---------------------------------------------------------------------------
# Batch indexing
# ---------------------------------------------------------------------------

async def batch_index(
    vector_store: Any,
    documents: list[Document],
    *,
    batch_size: int = 50,
    label: str = "",
) -> int:
    """Index documents into Qdrant in batches.

    Args:
        vector_store: LangChain QdrantVectorStore instance.
        documents: Documents to index.
        batch_size: Number of documents per batch.
        label: Label for log messages.

    Returns:
        Number of documents indexed.
    """
    if not documents:
        return 0

    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        await vector_store.aadd_documents(batch)
        logger.debug(
            f"Indexed batch {i // batch_size + 1}/{(len(documents) - 1) // batch_size + 1}"
            + (f" for {label}" if label else "")
        )

    logger.info(
        f"Indexed {len(documents)} chunks"
        + (f" for {label}" if label else "")
    )
    return len(documents)
