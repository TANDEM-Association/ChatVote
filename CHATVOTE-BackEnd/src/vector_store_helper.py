# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import os
from pathlib import Path
from typing import Union, Optional, Any
import logging

from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from qdrant_client import AsyncQdrantClient, QdrantClient
from qdrant_client.models import (
    Filter,
    FieldCondition,
    MatchAny,
    MatchValue,
    Range,
    VectorParams,
    Distance,
)
from src.models.candidate import Candidate
from src.models.party import Party

from src.model_config import (
    GOOGLE_EMBED_MODEL,
    GOOGLE_EMBED_DIM,
    SCALEWAY_EMBED_MODEL,
    SCALEWAY_EMBED_DIM,
    SCALEWAY_EMBED_DEFAULT_URL,
    OPENAI_EMBED_MODEL,
    OPENAI_EMBED_DIM,
    OLLAMA_EMBED_MODEL,
    OLLAMA_EMBED_DIM,
)
from src.utils import load_env, safe_load_api_key

from src.chatbot_async import rerank_documents, Responder

load_env()

logger = logging.getLogger(__name__)

BASE_PATH = Path(__file__).parent

# Get environment suffix
env = os.getenv("ENV", "dev")
env_suffix = f"_{env}" if env in ["prod", "dev"] else "_dev"

PARTY_INDEX_NAME = f"all_parties{env_suffix}"
VOTING_BEHAVIOR_INDEX_NAME = f"justified_voting_behavior{env_suffix}"
PARLIAMENTARY_QUESTIONS_INDEX_NAME = f"parliamentary_questions{env_suffix}"
CANDIDATES_INDEX_NAME = f"candidates_websites{env_suffix}"


def _ensure_payload_indexes(collection_name: str) -> None:
    """Create payload indexes for unified metadata fields if they don't exist."""
    from qdrant_client.models import PayloadSchemaType

    indexes_to_create = [
        ("metadata.party_ids", PayloadSchemaType.KEYWORD),
        ("metadata.candidate_ids", PayloadSchemaType.KEYWORD),
        ("metadata.fiabilite", PayloadSchemaType.INTEGER),
        ("metadata.theme", PayloadSchemaType.KEYWORD),
    ]

    for field_name, schema_type in indexes_to_create:
        try:
            qdrant_client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=schema_type,
            )
        except Exception as e:
            # Qdrant returns an error when the index already exists — that's fine.
            # Log anything else so infra failures aren't invisible.
            if "already exists" in str(e).lower():
                logger.debug(f"Payload index {field_name} already exists on {collection_name}")
            else:
                logger.warning(f"Failed to create payload index {field_name} on {collection_name}: {e}")


def _build_party_filter(party_ids: list[str]) -> Filter:
    """Build a Qdrant filter for matching any of the given party_ids."""
    return Filter(
        must=[
            FieldCondition(
                key="metadata.party_ids",
                match=MatchAny(any=party_ids),
            )
        ]
    )


def _build_fiabilite_filter(max_fiabilite: int = 3) -> Filter:
    """Build a Qdrant filter excluding sources above max_fiabilite.

    Uses must_not with gt so that points WITHOUT the fiabilite field
    are still included (backward-compatible with pre-fiabilite data).
    """
    return Filter(
        must_not=[
            FieldCondition(
                key="metadata.fiabilite",
                range=Range(gt=max_fiabilite),
            )
        ]
    )


def _combine_filters(*filters: "Filter | None") -> "Filter | None":
    """Merge multiple Filters into one by combining all must/must_not conditions."""
    all_must = []
    all_must_not = []
    for f in filters:
        if f is not None:
            if f.must:
                all_must.extend(f.must)
            if f.must_not:
                all_must_not.extend(f.must_not)
    if not all_must and not all_must_not:
        return None
    return Filter(
        must=all_must or None,
        must_not=all_must_not or None,
    )


def _get_embeddings() -> tuple[Embeddings, int]:
    """
    Get the embeddings model based on available API keys.
    Priority: EMBEDDING_PROVIDER override > Google > Scaleway > OpenAI > Ollama.
    Returns tuple of (embeddings, dimension).
    """
    # Allow forcing a specific provider via env var
    forced_provider = os.getenv("EMBEDDING_PROVIDER", "").lower()

    google_api_key = safe_load_api_key("GOOGLE_API_KEY")
    openai_api_key = safe_load_api_key("OPENAI_API_KEY")
    scaleway_api_key = safe_load_api_key("SCALEWAY_EMBED_API_KEY") or safe_load_api_key("QWEN3_8B_SCW_SECRET_KEY")

    if forced_provider == "google" and google_api_key:
        return _google_embeddings(google_api_key)
    if forced_provider == "scaleway" and scaleway_api_key:
        return _scaleway_embeddings(scaleway_api_key)
    if forced_provider == "openai" and openai_api_key:
        return _openai_embeddings(openai_api_key)
    if forced_provider == "ollama":
        return _ollama_embeddings()
    if forced_provider and forced_provider not in ("google", "scaleway", "openai", "ollama"):
        logger.warning(f"Unknown EMBEDDING_PROVIDER '{forced_provider}', falling back to auto-detect")

    # Auto-detect: Google > Scaleway > OpenAI > Ollama
    if google_api_key:
        return _google_embeddings(google_api_key)

    if scaleway_api_key:
        return _scaleway_embeddings(scaleway_api_key)

    if openai_api_key:
        return _openai_embeddings(openai_api_key)

    ollama_base_url = os.getenv("OLLAMA_BASE_URL")
    if ollama_base_url:
        return _ollama_embeddings()

    raise ValueError(
        "No embedding API key found. Set GOOGLE_API_KEY, SCALEWAY_EMBED_API_KEY, OPENAI_API_KEY, or OLLAMA_BASE_URL."
    )


def _google_embeddings(api_key: str) -> tuple[Embeddings, int]:
    from langchain_google_genai import GoogleGenerativeAIEmbeddings

    logger.info("Using Google Generative AI Embeddings")
    return (
        GoogleGenerativeAIEmbeddings(
            model=GOOGLE_EMBED_MODEL,
            google_api_key=api_key,
        ),
        GOOGLE_EMBED_DIM,
    )


def _scaleway_embeddings(api_key: str) -> tuple[Embeddings, int]:
    from langchain_openai import OpenAIEmbeddings

    base_url = os.getenv("SCALEWAY_EMBED_BASE_URL", SCALEWAY_EMBED_DEFAULT_URL)
    model = SCALEWAY_EMBED_MODEL
    dim = SCALEWAY_EMBED_DIM
    logger.info(f"Using Scaleway Embeddings ({model}, {dim}d)")
    return (
        OpenAIEmbeddings(
            model=model,
            openai_api_key=api_key,
            openai_api_base=base_url,
            dimensions=dim,
        ),
        dim,
    )


def _openai_embeddings(api_key: str) -> tuple[Embeddings, int]:
    from langchain_openai import OpenAIEmbeddings

    logger.info("Using OpenAI Embeddings")
    return (
        OpenAIEmbeddings(
            model=OPENAI_EMBED_MODEL,
            openai_api_key=api_key,
        ),
        OPENAI_EMBED_DIM,
    )


def _ollama_embeddings() -> tuple[Embeddings, int]:
    from langchain_ollama import OllamaEmbeddings

    ollama_base_url = os.getenv("OLLAMA_BASE_URL")
    if not ollama_base_url:
        raise ValueError("OLLAMA_BASE_URL not set")
    logger.info(
        f"Using Ollama Embeddings ({OLLAMA_EMBED_MODEL}, {OLLAMA_EMBED_DIM}d)"
    )
    return (
        OllamaEmbeddings(
            model=OLLAMA_EMBED_MODEL,
            base_url=ollama_base_url,
        ),
        OLLAMA_EMBED_DIM,
    )


embed, EMBEDDING_DIM = _get_embeddings()

# Initialize Qdrant clients (sync for admin ops, async for hot-path searches)
_qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
_qdrant_api_key = os.getenv("QDRANT_API_KEY")

# When QDRANT_URL is an https:// Scaleway serverless endpoint, the default
# qdrant-client tries gRPC on port 6334 which is unreachable.  Force REST
# over the standard HTTPS port so container-to-container calls work.
_force_rest = _qdrant_url.startswith("https://")
qdrant_client = QdrantClient(
    url=_qdrant_url, api_key=_qdrant_api_key, prefer_grpc=False, https=_force_rest,
    port=443 if _force_rest else 6333, timeout=30,
)
async_qdrant_client = AsyncQdrantClient(
    url=_qdrant_url, api_key=_qdrant_api_key, prefer_grpc=False, https=_force_rest,
    port=443 if _force_rest else 6333, timeout=30,
)

# Cache collection existence to avoid repeated get_collections() round-trips
_known_collections: set[str] = set()


def _ensure_collection_exists(collection_name: str) -> None:
    """
    Ensure a Qdrant collection exists with correct dimensions, creating/recreating if necessary.
    """
    try:
        collections = qdrant_client.get_collections().collections
        existing_collection = next(
            (c for c in collections if c.name == collection_name), None
        )

        if existing_collection is not None:
            # Check if dimensions match
            collection_info = qdrant_client.get_collection(collection_name)
            existing_dim = None
            if hasattr(collection_info.config.params, "vectors"):
                vectors_config = collection_info.config.params.vectors
                if isinstance(vectors_config, dict) and "dense" in vectors_config:
                    existing_dim = vectors_config["dense"].size
                elif hasattr(vectors_config, "size"):
                    existing_dim = vectors_config.size

            if existing_dim is not None and existing_dim != EMBEDDING_DIM:
                logger.warning(
                    f"Collection {collection_name} has {existing_dim} dimensions but expected {EMBEDDING_DIM}. "
                    f"Recreating collection..."
                )
                qdrant_client.delete_collection(collection_name)
                existing_collection = None
            else:
                logger.debug(
                    f"Collection {collection_name} already exists with correct dimensions"
                )

        if existing_collection is None:
            logger.info(
                f"Creating Qdrant collection: {collection_name} with {EMBEDDING_DIM} dimensions"
            )
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config={
                    "dense": VectorParams(
                        size=EMBEDDING_DIM,
                        distance=Distance.COSINE,
                    )
                },
            )
            logger.info(f"Collection {collection_name} created successfully")
    except Exception as e:
        logger.error(f"Error ensuring collection {collection_name} exists: {e}")
        raise


def _get_vector_store(
    collection_name: str, force_recreate: bool = False
) -> QdrantVectorStore:
    """
    Get or create a Qdrant vector store for the given collection.
    """
    if force_recreate:
        # Delete collection if it exists
        try:
            collections = qdrant_client.get_collections().collections
            if any(c.name == collection_name for c in collections):
                logger.info(
                    f"Force recreating collection {collection_name}, deleting existing..."
                )
                qdrant_client.delete_collection(collection_name)
        except Exception as e:
            logger.warning(f"Error deleting collection {collection_name}: {e}")

    _ensure_collection_exists(collection_name)
    _ensure_payload_indexes(collection_name)
    return QdrantVectorStore(
        client=qdrant_client,
        collection_name=collection_name,
        embedding=embed,
        vector_name="dense",
        content_payload_key="page_content",
    )


# Lazy initialization of vector stores
_qdrant_vector_store: Optional[QdrantVectorStore] = None
_voting_behavior_vector_store: Optional[QdrantVectorStore] = None
_parliamentary_questions_vector_store: Optional[QdrantVectorStore] = None
_candidates_vector_store: Optional[QdrantVectorStore] = None


def get_qdrant_vector_store() -> QdrantVectorStore:
    global _qdrant_vector_store
    if _qdrant_vector_store is None:
        _qdrant_vector_store = _get_vector_store(PARTY_INDEX_NAME)
    return _qdrant_vector_store


def get_voting_behavior_vector_store() -> QdrantVectorStore:
    global _voting_behavior_vector_store
    if _voting_behavior_vector_store is None:
        _voting_behavior_vector_store = _get_vector_store(VOTING_BEHAVIOR_INDEX_NAME)
    return _voting_behavior_vector_store


def get_parliamentary_questions_vector_store() -> QdrantVectorStore:
    global _parliamentary_questions_vector_store
    if _parliamentary_questions_vector_store is None:
        _parliamentary_questions_vector_store = _get_vector_store(
            PARLIAMENTARY_QUESTIONS_INDEX_NAME
        )
    return _parliamentary_questions_vector_store


def get_candidates_vector_store() -> QdrantVectorStore:
    global _candidates_vector_store
    if _candidates_vector_store is None:
        _candidates_vector_store = _get_vector_store(CANDIDATES_INDEX_NAME)
    return _candidates_vector_store


async def _identify_relevant_documents(
    vector_store: QdrantVectorStore,
    namespace: Optional[str],
    rag_query: str,
    n_docs: int = 5,
    score_threshold: float = 0.65,
    max_fiabilite: int = 3,
) -> list[Document]:
    """
    Identify relevant documents based on the provided query and namespace.
    Uses direct Qdrant client to ensure all metadata is preserved.

    If namespace is None, searches all documents without filtering.
    """
    # Get query vector
    query_vector = await embed.aembed_query(rag_query)

    # Create filter for the namespace (if provided)
    # Note: LangChain stores metadata under "metadata.*" in Qdrant
    namespace_filter = None
    if namespace is not None:
        namespace_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.namespace", match=MatchValue(value=namespace)
                )
            ]
        )

    filter_condition = _combine_filters(namespace_filter, _build_fiabilite_filter(max_fiabilite))

    # Search using async client to avoid blocking the event loop
    try:
        _query_response = await async_qdrant_client.query_points(
            collection_name=vector_store.collection_name,
            query=query_vector,
            using="dense",
            limit=n_docs,
            with_payload=True,
            query_filter=filter_condition,
            score_threshold=score_threshold,
        )
        search_result = _query_response.points
    except Exception as e:
        logger.error(f"Qdrant query_points failed for {vector_store.collection_name}: {type(e).__name__}: {e!r}")
        raise

    # Create LangChain Documents manually to preserve all metadata
    documents = []
    for point in search_result:
        if point.payload is None:
            continue

        # LangChain QdrantVectorStore stores data with:
        # - "page_content" for text content
        # - "metadata" dict for metadata
        content = point.payload.get("page_content", "")

        # Extract metadata from nested "metadata" field if present
        metadata = point.payload.get("metadata", {})

        # If metadata is not nested (legacy format), extract from top level
        if not metadata and "namespace" in point.payload:
            metadata = {
                k: v
                for k, v in point.payload.items()
                if k not in ["page_content", "text"]
            }

        # Create Document with proper content and metadata
        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)

    return documents


async def identify_relevant_docs(
    party: Party,
    rag_query: str,
    n_docs: int = 5,
    score_threshold: float = 0.65,
) -> list[Document]:
    return await _identify_relevant_documents(
        vector_store=get_qdrant_vector_store(),
        namespace=party.party_id,
        rag_query=rag_query,
        n_docs=n_docs,
        score_threshold=score_threshold,
    )


# relevant docs with reranking
async def identify_relevant_docs_with_reranking(
    party: Party,
    rag_query: str,
    n_docs: int = 20,
    score_threshold: float = 0.65,
) -> list[Document]:
    relevant_docs = await _identify_relevant_documents(
        vector_store=get_qdrant_vector_store(),
        namespace=party.party_id,
        rag_query=rag_query,
        n_docs=n_docs,
        score_threshold=score_threshold,
    )

    # For now, return without external reranking since we're moving away from Pinecone
    # TODO: Implement alternative reranking if needed
    return relevant_docs[:5]  # Return top 5 documents


async def identify_relevant_docs_with_llm_based_reranking(
    responder: Responder,
    rag_query: str,
    chat_history: str,
    user_message: str,
    n_docs: int = 20,
    score_threshold: float = 0.65,
    target_party_id: Optional[str] = None,
) -> list[Document]:
    from src.models.assistant import ASSISTANT_ID

    # Determine namespace for search:
    # - If target_party_id is provided, use it
    # - If responder is the ChatVote assistant, search ALL documents (no namespace filter)
    # - Otherwise, use the responder's party_id
    if target_party_id:
        namespace = target_party_id
    elif responder.party_id == ASSISTANT_ID:
        namespace = None  # Search all documents
    else:
        namespace = responder.party_id

    relevant_docs = await _identify_relevant_documents(
        vector_store=get_qdrant_vector_store(),
        namespace=namespace,
        rag_query=rag_query,
        n_docs=n_docs,
        score_threshold=score_threshold,
    )

    # Note: We lose the score information when using direct Qdrant search
    # If score sorting is critical, we could modify _identify_relevant_documents
    # to return scores as well

    if len(relevant_docs) >= 3:
        # get indices of relevant docs
        relevant_docs = await rerank_documents(
            relevant_docs=relevant_docs,
            user_message=user_message,
            chat_history=chat_history,
        )
        return relevant_docs
    else:
        return relevant_docs


async def identify_relevant_votes(
    rag_query: str, n_docs: int = 5, score_threshold: float = 0.65
) -> list[Document]:
    """
    Identify relevant votes based on the provided query.

    :param rag_query: The query to search for relevant documents.
    :param n_docs: The number of documents to return.
    :param score_threshold: The score threshold for the similarity search.
    :return: A list of relevant documents.
    """
    return await _identify_relevant_documents(
        vector_store=get_voting_behavior_vector_store(),
        namespace="vote_summary",
        rag_query=rag_query,
        n_docs=n_docs,
        score_threshold=score_threshold,
    )


async def identify_relevant_parliamentary_questions(
    party: Union[Party, str],
    rag_query: str,
    n_docs: int = 5,
    score_threshold: float = 0.7,
) -> list[Document]:
    """
    Identify relevant parliamentary questions based on the provided query and party.
    """
    namespace = f"{party.party_id if isinstance(party, Party) else party}-parliamentary-questions"
    return await _identify_relevant_documents(
        vector_store=get_parliamentary_questions_vector_store(),
        namespace=namespace,
        rag_query=rag_query,
        n_docs=n_docs,
        score_threshold=score_threshold,
    )


# ==================== Candidate Document Search ====================


async def _identify_relevant_candidate_documents(
    rag_query: str,
    municipality_code: Optional[str] = None,
    candidate_id: Optional[str] = None,
    n_docs: int = 10,
    score_threshold: float = 0.65,
    max_fiabilite: int = 3,
) -> list[Document]:
    """
    Identify relevant candidate documents based on the provided query.

    Filtering options:
    - municipality_code: Filter by municipality (for local scope)
    - candidate_id: Filter by specific candidate
    - Neither: Search all candidate documents (national scope)
    """
    # Check if candidates collection exists
    if not _collection_exists(CANDIDATES_INDEX_NAME):
        logger.debug(
            f"Collection {CANDIDATES_INDEX_NAME} does not exist, skipping candidate search"
        )
        return []

    # Get query vector
    query_vector = await embed.aembed_query(rag_query)

    # Build filter conditions
    filter_conditions = []

    if candidate_id is not None:
        filter_conditions.append(
            FieldCondition(
                key="metadata.candidate_id",
                match=MatchValue(value=candidate_id),
            )
        )
    elif municipality_code is not None:
        filter_conditions.append(
            FieldCondition(
                key="metadata.municipality_code",
                match=MatchValue(value=municipality_code),
            )
        )

    # Create filter if we have conditions
    entity_filter = Filter(must=filter_conditions) if filter_conditions else None
    filter_condition = _combine_filters(entity_filter, _build_fiabilite_filter(max_fiabilite))

    # Search using async client to avoid blocking the event loop
    try:
        _query_response = await async_qdrant_client.query_points(
            collection_name=CANDIDATES_INDEX_NAME,
            query=query_vector,
            using="dense",
            limit=n_docs,
            with_payload=True,
            query_filter=filter_condition,
            score_threshold=score_threshold,
        )
        search_result = _query_response.points
    except Exception as e:
        logger.error(f"Qdrant query_points failed for {CANDIDATES_INDEX_NAME}: {type(e).__name__}: {e!r}")
        raise

    # Create LangChain Documents
    documents = []
    for point in search_result:
        if point.payload is None:
            continue

        content = point.payload.get("page_content", "")
        metadata = point.payload.get("metadata", {})

        # Handle legacy format if needed
        if not metadata and "namespace" in point.payload:
            metadata = {
                k: v
                for k, v in point.payload.items()
                if k not in ["page_content", "text"]
            }

        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)

    return documents


async def identify_relevant_candidate_docs(
    candidate: Candidate,
    rag_query: str,
    n_docs: int = 10,
    score_threshold: float = 0.65,
) -> list[Document]:
    """
    Identify relevant documents for a specific candidate.
    """
    return await _identify_relevant_candidate_documents(
        rag_query=rag_query,
        candidate_id=candidate.candidate_id,
        n_docs=n_docs,
        score_threshold=score_threshold,
    )


async def identify_relevant_candidate_docs_by_municipality(
    municipality_code: str,
    rag_query: str,
    n_docs: int = 15,
    score_threshold: float = 0.65,
) -> list[Document]:
    """
    Identify relevant candidate documents for all candidates in a municipality.
    Used for local scope candidate chats.
    """
    return await _identify_relevant_candidate_documents(
        rag_query=rag_query,
        municipality_code=municipality_code,
        n_docs=n_docs,
        score_threshold=score_threshold,
    )


async def identify_relevant_candidate_docs_national(
    rag_query: str,
    n_docs: int = 15,
    score_threshold: float = 0.65,
) -> list[Document]:
    """
    Identify relevant candidate documents across all candidates (national scope).
    """
    return await _identify_relevant_candidate_documents(
        rag_query=rag_query,
        municipality_code=None,
        candidate_id=None,
        n_docs=n_docs,
        score_threshold=score_threshold,
    )


async def identify_relevant_candidate_docs_with_reranking(
    rag_query: str,
    chat_history: str,
    user_message: str,
    municipality_code: Optional[str] = None,
    n_docs: int = 20,
    score_threshold: float = 0.65,
) -> list[Document]:
    """
    Identify relevant candidate documents with LLM-based reranking.

    Args:
        municipality_code: If provided, filters to candidates in that municipality (local scope).
                          If None, searches all candidates (national scope).
    """
    relevant_docs = await _identify_relevant_candidate_documents(
        rag_query=rag_query,
        municipality_code=municipality_code,
        n_docs=n_docs,
        score_threshold=score_threshold,
    )

    if len(relevant_docs) >= 3:
        relevant_docs = await rerank_documents(
            relevant_docs=relevant_docs,
            user_message=user_message,
            chat_history=chat_history,
        )
        return relevant_docs
    else:
        return relevant_docs


async def identify_relevant_docs_combined(
    rag_query: str,
    chat_history: str,
    user_message: str,
    party_ids: list[str],
    candidate_ids: list[str],
    scope: str,
    municipality_code: Optional[str] = None,
    n_docs_manifesto: int = 10,
    n_docs_candidates: int = 10,
    score_threshold: float = 0.65,
) -> tuple[list[Document], list[Document]]:
    """
    Combined search across party manifestos and candidate websites.

    Returns a tuple of (manifesto_docs, candidate_docs).

    Args:
        rag_query: The search query
        chat_history: Conversation history for reranking
        user_message: Current user message for reranking
        party_ids: List of party IDs to search for in manifestos
        candidate_ids: List of specific candidate IDs (if any)
        scope: 'national' or 'local'
        municipality_code: Required if scope is 'local'
        n_docs_manifesto: Number of manifesto docs to retrieve per party
        n_docs_candidates: Number of candidate docs to retrieve
        score_threshold: Minimum similarity score
    """
    import asyncio

    manifesto_docs: list[Document] = []
    candidate_docs: list[Document] = []

    # Create tasks for parallel execution
    tasks = []

    # Determine which Qdrant manifesto namespaces actually exist
    # so we can detect mismatches (e.g., local party_ids like "lfi"
    # vs Qdrant namespaces like "la-france-insoumise")
    _existing_namespaces = _get_manifesto_namespaces()

    party_ids_with_manifesto = [pid for pid in party_ids if pid in _existing_namespaces]

    if party_ids_with_manifesto:
        # Search manifesto for each matched party
        for party_id in party_ids_with_manifesto:
            tasks.append(
                _identify_relevant_manifesto_documents(
                    rag_query=rag_query,
                    namespace=party_id,
                    n_docs=n_docs_manifesto,
                    score_threshold=score_threshold,
                )
            )
        manifesto_task_count = len(party_ids_with_manifesto)
    else:
        # No party_ids match Qdrant namespaces — search ALL manifestos
        # (common for local-scope queries where candidate party_ids differ)
        logger.info(
            f"No manifesto namespaces match party_ids {party_ids}, "
            f"searching all manifestos (available: {_existing_namespaces})"
        )
        tasks.append(
            _identify_relevant_manifesto_documents(
                rag_query=rag_query,
                namespace=None,  # unfiltered search across all parties
                n_docs=n_docs_manifesto * min(len(party_ids), 5),
                score_threshold=score_threshold,
            )
        )
        manifesto_task_count = 1

    # Search candidate websites
    if candidate_ids:
        # Search specific candidates
        for candidate_id in candidate_ids:
            tasks.append(
                _identify_relevant_candidate_documents(
                    rag_query=rag_query,
                    candidate_id=candidate_id,
                    n_docs=n_docs_candidates,
                    score_threshold=score_threshold,
                )
            )
    elif party_ids:
        # Search candidates affiliated with the parties
        if scope == "local" and municipality_code is not None:
            # Local scope: search candidates in the specific municipality
            tasks.append(
                _search_candidate_docs_by_party_and_municipality(
                    rag_query=rag_query,
                    party_ids=party_ids,
                    municipality_code=municipality_code,
                    n_docs=n_docs_candidates,
                    score_threshold=score_threshold,
                )
            )
        else:
            # National scope: search all candidates of the party
            tasks.append(
                _search_candidate_docs_by_party(
                    rag_query=rag_query,
                    party_ids=party_ids,
                    n_docs=n_docs_candidates,
                    score_threshold=score_threshold,
                )
            )

    # Execute all tasks in parallel
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Separate results
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.error(f"Search task {i} failed: {result}")
            continue

        # At this point, result is List[Document] not an exception
        docs: list[Any] = result
        if i < manifesto_task_count:
            # This is a manifesto result
            manifesto_docs.extend(docs)
        else:
            # This is a candidate result
            candidate_docs.extend(docs)

    # Deduplicate manifesto docs by page_content
    seen_manifesto_contents = set()
    unique_manifesto_docs = []
    for doc in manifesto_docs:
        content_key = doc.page_content[:200]  # Use first 200 chars as key
        if content_key not in seen_manifesto_contents:
            seen_manifesto_contents.add(content_key)
            unique_manifesto_docs.append(doc)

    # Deduplicate candidate docs by page_content
    seen_candidate_contents = set()
    unique_candidate_docs = []
    for doc in candidate_docs:
        content_key = doc.page_content[:200]
        if content_key not in seen_candidate_contents:
            seen_candidate_contents.add(content_key)
            unique_candidate_docs.append(doc)

    # Rerank each set if we have enough docs
    if len(unique_manifesto_docs) >= 3:
        unique_manifesto_docs = await rerank_documents(
            relevant_docs=unique_manifesto_docs,
            user_message=user_message,
            chat_history=chat_history,
        )

    if len(unique_candidate_docs) >= 3:
        unique_candidate_docs = await rerank_documents(
            relevant_docs=unique_candidate_docs,
            user_message=user_message,
            chat_history=chat_history,
        )

    return (unique_manifesto_docs, unique_candidate_docs)


def _collection_exists(collection_name: str) -> bool:
    """Check if a Qdrant collection exists (positive results are cached)."""
    if collection_name in _known_collections:
        return True
    try:
        collections = qdrant_client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)
        if exists:
            _known_collections.add(collection_name)
        return exists
    except Exception as e:
        logger.warning(f"Error checking collection {collection_name}: {e}")
        return False


_manifesto_namespaces: set[str] | None = None


def _get_manifesto_namespaces() -> set[str]:
    """Return the set of distinct metadata.namespace values in the manifesto collection.

    Results are cached after the first call since manifesto data changes rarely.
    """
    global _manifesto_namespaces
    if _manifesto_namespaces is not None:
        return _manifesto_namespaces

    try:
        # Scroll through all points to collect unique namespaces
        namespaces: set[str] = set()
        offset = None
        while True:
            points, next_offset = qdrant_client.scroll(
                collection_name=PARTY_INDEX_NAME,
                limit=100,
                offset=offset,
                with_payload=["metadata.namespace"],
            )
            for point in points:
                ns = (point.payload or {}).get("metadata", {}).get("namespace")
                if ns:
                    namespaces.add(ns)
            if next_offset is None:
                break
            offset = next_offset
        _manifesto_namespaces = namespaces
        logger.info(f"Manifesto namespaces in Qdrant: {namespaces}")
        return namespaces
    except Exception as e:
        logger.warning(f"Could not fetch manifesto namespaces: {e}")
        return set()


async def _search_candidate_docs_by_party(
    rag_query: str,
    party_ids: list[str],
    n_docs: int = 10,
    score_threshold: float = 0.65,
    max_fiabilite: int = 3,
) -> list[Document]:
    """Search candidate documents filtered by party affiliation using Qdrant MatchAny."""

    if not _collection_exists(CANDIDATES_INDEX_NAME):
        return []

    query_vector = await embed.aembed_query(rag_query)

    query_filter = _combine_filters(
        _build_party_filter(party_ids),
        _build_fiabilite_filter(max_fiabilite),
    )

    try:
        _query_response = await async_qdrant_client.query_points(
            collection_name=CANDIDATES_INDEX_NAME,
            query=query_vector,
            using="dense",
            limit=n_docs,
            with_payload=True,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )
        search_result = _query_response.points
        logger.info(f"Candidate Qdrant search returned {len(search_result)} results")
    except (ConnectionError, TimeoutError) as e:
        logger.warning(f"Qdrant unavailable for candidates search: {type(e).__name__}: {e!r}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in candidates search: {type(e).__name__}: {e!r}", exc_info=True)
        raise

    documents = []
    for point in search_result:
        if point.payload is None:
            continue
        metadata = point.payload.get("metadata", {})
        content = point.payload.get("page_content", "")
        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)

    return documents


async def _search_candidate_docs_by_party_and_municipality(
    rag_query: str,
    party_ids: list[str],
    municipality_code: str,
    n_docs: int = 10,
    score_threshold: float = 0.65,
    max_fiabilite: int = 3,
) -> list[Document]:
    """Search candidate docs filtered by party + municipality using Qdrant filters."""
    logger.info(
        f"Candidate search: municipality={municipality_code}, party_ids={party_ids}, "
        f"collection={CANDIDATES_INDEX_NAME}, n_docs={n_docs}"
    )

    if not _collection_exists(CANDIDATES_INDEX_NAME):
        logger.warning(f"Candidate collection {CANDIDATES_INDEX_NAME} not found")
        return []

    query_vector = await embed.aembed_query(rag_query)

    municipality_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.municipality_code",
                match=MatchValue(value=municipality_code),
            )
        ]
    )

    # Municipality filter is the primary scope — party_ids filtering is skipped
    # because candidate website metadata typically has empty party_ids arrays
    # (the affiliation is inferred from the candidate's Firestore record, not
    # stored in the Qdrant payload).
    query_filter = _combine_filters(municipality_filter, _build_fiabilite_filter(max_fiabilite))

    try:
        _query_response = await async_qdrant_client.query_points(
            collection_name=CANDIDATES_INDEX_NAME,
            query=query_vector,
            using="dense",
            limit=n_docs,
            with_payload=True,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )
        search_result = _query_response.points
        logger.info(f"Candidate Qdrant search returned {len(search_result)} results")
    except (ConnectionError, TimeoutError) as e:
        logger.warning(f"Qdrant unavailable for candidates search: {type(e).__name__}: {e!r}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in candidates search: {type(e).__name__}: {e!r}", exc_info=True)
        raise

    documents = []
    for point in search_result:
        if point.payload is None:
            continue
        metadata = point.payload.get("metadata", {})
        content = point.payload.get("page_content", "")
        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)

    return documents


async def _identify_relevant_manifesto_documents(
    rag_query: str,
    namespace: Optional[str] = None,
    n_docs: int = 10,
    score_threshold: float = 0.65,
    max_fiabilite: int = 3,
) -> list[Document]:
    """
    Search for relevant manifesto documents in the party index.

    If namespace is None, searches across ALL party manifestos (useful for
    local-scope queries where candidate party_ids don't map to manifesto namespaces).
    """

    # Get query embedding
    query_vector = await embed.aembed_query(rag_query)

    # Filter by namespace (party_id) + fiabilité
    namespace_filter = (
        Filter(
            must=[
                FieldCondition(
                    key="metadata.namespace",
                    match=MatchValue(value=namespace),
                )
            ]
        )
        if namespace
        else None
    )
    filter_condition = _combine_filters(
        namespace_filter,
        _build_fiabilite_filter(max_fiabilite),
    )

    try:
        _query_response = await async_qdrant_client.query_points(
            collection_name=PARTY_INDEX_NAME,
            query=query_vector,
            using="dense",
            limit=n_docs,
            with_payload=True,
            query_filter=filter_condition,
            score_threshold=score_threshold,
        )
        search_result = _query_response.points
    except Exception as e:
        logger.error(f"Qdrant query_points failed for {PARTY_INDEX_NAME}: {type(e).__name__}: {e!r}")
        raise

    # Create LangChain Documents
    documents = []
    for point in search_result:
        if point.payload is None:
            continue

        content = point.payload.get("page_content", "")
        metadata = point.payload.get("metadata", {})

        # Handle legacy format if needed
        if not metadata and "namespace" in point.payload:
            metadata = {
                k: v
                for k, v in point.payload.items()
                if k not in ["page_content", "text"]
            }

        # Add source type marker
        metadata["source_type"] = "manifesto"

        doc = Document(page_content=content, metadata=metadata)
        documents.append(doc)

    return documents
