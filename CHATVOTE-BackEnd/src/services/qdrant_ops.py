"""
Unified Qdrant operations.

Single source of truth for collection management and namespace operations.
Consolidates the duplicated patterns in manifesto_indexer, candidate_indexer,
and index_election_posters.

Usage:
    from src.services.qdrant_ops import (
        delete_by_namespace,
        ensure_collection,
        get_vector_store,
    )

    # Delete all chunks for a party/candidate
    await delete_by_namespace("all_parties_dev", "renaissance")

    # Ensure collection exists with correct config
    ensure_collection("candidates_websites_dev")

    # Get a ready-to-use vector store
    vs = get_vector_store("all_parties_dev")
"""

import logging
from typing import Optional

from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PayloadSchemaType,
    VectorParams,
)

from src.vector_store_helper import (
    qdrant_client,
    embed,
    EMBEDDING_DIM,
    PARTY_INDEX_NAME,
    CANDIDATES_INDEX_NAME,
)

logger = logging.getLogger(__name__)

# Payload indexes that every collection should have
_STANDARD_INDEXES: list[tuple[str, PayloadSchemaType]] = [
    ("metadata.namespace", PayloadSchemaType.KEYWORD),
    ("metadata.party_ids", PayloadSchemaType.KEYWORD),
    ("metadata.candidate_ids", PayloadSchemaType.KEYWORD),
    ("metadata.fiabilite", PayloadSchemaType.INTEGER),
    ("metadata.theme", PayloadSchemaType.KEYWORD),
]

# Additional indexes for the candidates collection
_CANDIDATE_INDEXES: list[tuple[str, PayloadSchemaType]] = [
    ("metadata.municipality_code", PayloadSchemaType.KEYWORD),
    ("metadata.candidate_id", PayloadSchemaType.KEYWORD),
]

# Cache to avoid repeated ensure calls
_ensured_collections: set[str] = set()


def ensure_collection(collection_name: str) -> None:
    """Ensure a Qdrant collection exists with correct vector config and indexes.

    Creates the collection if it doesn't exist. Verifies vector dimensions
    match the current embedding model. Creates standard payload indexes.

    This consolidates:
    - vector_store_helper._ensure_collection_exists()
    - candidate_indexer._ensure_candidates_collection_exists()
    """
    if collection_name in _ensured_collections:
        return

    try:
        collections = qdrant_client.get_collections().collections
        existing = next(
            (c for c in collections if c.name == collection_name), None
        )

        if existing is None:
            logger.info(f"Creating Qdrant collection: {collection_name}")
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=EMBEDDING_DIM,
                        distance=Distance.COSINE,
                    )
                },
            )
        else:
            # Verify dimensions match
            info = qdrant_client.get_collection(collection_name)
            vectors_config = info.config.params.vectors
            existing_dim = None
            if isinstance(vectors_config, dict) and "dense" in vectors_config:
                existing_dim = vectors_config["dense"].size
            elif hasattr(vectors_config, "size"):
                existing_dim = vectors_config.size

            if existing_dim is not None and existing_dim != EMBEDDING_DIM:
                logger.warning(
                    f"Collection {collection_name} has {existing_dim} dims "
                    f"but expected {EMBEDDING_DIM}. Recreating..."
                )
                qdrant_client.delete_collection(collection_name)
                qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "dense": VectorParams(
                            size=EMBEDDING_DIM,
                            distance=Distance.COSINE,
                        )
                    },
                )

        # Ensure payload indexes
        indexes = list(_STANDARD_INDEXES)
        if "candidates" in collection_name:
            indexes.extend(_CANDIDATE_INDEXES)

        for field_name, schema_type in indexes:
            try:
                qdrant_client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=schema_type,
                )
            except Exception as e:
                if "already exists" not in str(e).lower():
                    logger.warning(
                        f"Failed to create index {field_name} "
                        f"on {collection_name}: {e}"
                    )

        _ensured_collections.add(collection_name)
        logger.info(f"Collection {collection_name} ready")

    except Exception as e:
        logger.error(f"Error ensuring collection {collection_name}: {e}")
        raise


def delete_by_namespace(collection_name: str, namespace: str) -> None:
    """Delete all points in a collection matching a namespace.

    This is the standard pattern for re-indexing: delete old chunks
    for a party/candidate, then insert new ones.

    Consolidates:
    - manifesto_indexer.delete_party_documents()
    - candidate_indexer.delete_candidate_documents()
    - index_election_posters.delete_poster_namespace()
    """
    try:
        ensure_collection(collection_name)
        qdrant_client.delete(
            collection_name=collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.namespace",
                            match=MatchValue(value=namespace),
                        )
                    ]
                )
            ),
        )
        logger.info(f"Deleted namespace '{namespace}' from {collection_name}")
    except Exception as e:
        logger.error(
            f"Error deleting namespace '{namespace}' from {collection_name}: {e}"
        )


def count_by_namespace(collection_name: str, namespace: str) -> int:
    """Count points in a collection matching a namespace."""
    try:
        ensure_collection(collection_name)
        result = qdrant_client.count(
            collection_name=collection_name,
            count_filter=Filter(
                must=[
                    FieldCondition(
                        key="metadata.namespace",
                        match=MatchValue(value=namespace),
                    )
                ]
            ),
        )
        return result.count
    except Exception:
        return 0


def get_indexed_namespaces(collection_name: str) -> dict[str, int]:
    """Return {namespace: chunk_count} for all namespaces in a collection.

    Useful for checking which entities are already indexed (skip re-scraping).
    """
    try:
        ensure_collection(collection_name)
        counts: dict[str, int] = {}
        offset = None
        while True:
            results, next_offset = qdrant_client.scroll(
                collection_name=collection_name,
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
        logger.warning(f"Could not enumerate namespaces in {collection_name}: {e}")
        return {}


def get_vector_store(collection_name: str) -> "QdrantVectorStore":
    """Get a LangChain QdrantVectorStore for a collection.

    Ensures the collection exists before returning.
    """
    from langchain_qdrant import QdrantVectorStore

    ensure_collection(collection_name)
    return QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name,
        embedding=embed,
        vector_name="dense",
        content_payload_key="page_content",
    )
