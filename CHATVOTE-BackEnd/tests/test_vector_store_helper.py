"""Tests for qdrant-client 1.15.x migration in vector_store_helper.py.

Key change tested: .search() replaced by .query_points() which returns a
QueryResponse with a .points attribute.
"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Patch heavy dependencies before importing vector_store_helper so that the
# module-level side-effects (Firebase, Qdrant connections, embedding init)
# don't run during unit tests.
# ---------------------------------------------------------------------------


def _import_vsh():
    """Import vector_store_helper with all heavy side-effects mocked out."""
    mocks = {
        "src.chatbot_async": MagicMock(),
        "src.firebase_service": MagicMock(),
    }
    qdrant_mock = MagicMock()
    with patch.dict(sys.modules, mocks), \
         patch("qdrant_client.QdrantClient", return_value=qdrant_mock), \
         patch("qdrant_client.AsyncQdrantClient", return_value=qdrant_mock), \
         patch("src.vector_store_helper._get_embeddings", return_value=(MagicMock(), 3072)):
        sys.modules.pop("src.vector_store_helper", None)
        import src.vector_store_helper as vsh
        return vsh


@pytest.fixture(scope="module")
def vsh():
    return _import_vsh()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identify_relevant_documents_calls_query_points(vsh):
    """_identify_relevant_documents calls query_points with expected args and
    returns Documents with correct page_content and metadata."""
    mock_point = MagicMock()
    mock_point.payload = {
        "page_content": "Some policy text",
        "metadata": {"party_id": "ps", "namespace": "ps"},
    }

    query_response = types.SimpleNamespace(points=[mock_point])

    async_client_mock = AsyncMock()
    async_client_mock.query_points = AsyncMock(return_value=query_response)

    embed_mock = AsyncMock()
    embed_mock.aembed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

    vector_store_mock = MagicMock()
    vector_store_mock.collection_name = "all_parties"

    vsh.async_qdrant_client = async_client_mock
    vsh.embed = embed_mock

    docs = await vsh._identify_relevant_documents(
        vector_store=vector_store_mock,
        namespace="ps",
        rag_query="climate policy",
        n_docs=5,
        score_threshold=0.65,
    )

    async_client_mock.query_points.assert_called_once()
    call_kwargs = async_client_mock.query_points.call_args.kwargs
    assert call_kwargs["query"] == [0.1, 0.2, 0.3]
    assert call_kwargs["using"] == "dense"
    assert call_kwargs["query_filter"] is not None
    assert call_kwargs["score_threshold"] == 0.65

    assert len(docs) == 1
    assert docs[0].page_content == "Some policy text"
    assert docs[0].metadata["party_id"] == "ps"


@pytest.mark.asyncio
async def test_identify_relevant_documents_empty_results(vsh):
    """_identify_relevant_documents returns empty list when query_points returns no points."""
    query_response = types.SimpleNamespace(points=[])

    async_client_mock = AsyncMock()
    async_client_mock.query_points = AsyncMock(return_value=query_response)

    embed_mock = AsyncMock()
    embed_mock.aembed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

    vector_store_mock = MagicMock()
    vector_store_mock.collection_name = "all_parties"

    vsh.async_qdrant_client = async_client_mock
    vsh.embed = embed_mock

    docs = await vsh._identify_relevant_documents(
        vector_store=vector_store_mock,
        namespace="ps",
        rag_query="climate policy",
    )

    assert docs == []


@pytest.mark.asyncio
async def test_legacy_payload_fallback(vsh):
    """Legacy payload (no nested 'metadata' key) is handled by building metadata
    from flat payload keys, excluding 'page_content' and 'text'."""
    mock_point = MagicMock()
    mock_point.payload = {
        "page_content": "Legacy content",
        "namespace": "ps",
        "party_id": "ps",
        "source": "manifesto.pdf",
    }

    query_response = types.SimpleNamespace(points=[mock_point])

    async_client_mock = AsyncMock()
    async_client_mock.query_points = AsyncMock(return_value=query_response)

    embed_mock = AsyncMock()
    embed_mock.aembed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

    vector_store_mock = MagicMock()
    vector_store_mock.collection_name = "all_parties"

    vsh.async_qdrant_client = async_client_mock
    vsh.embed = embed_mock

    docs = await vsh._identify_relevant_documents(
        vector_store=vector_store_mock,
        namespace=None,
        rag_query="some query",
    )

    assert len(docs) == 1
    assert docs[0].page_content == "Legacy content"
    # Legacy fallback: namespace and other keys copied into metadata
    assert docs[0].metadata["namespace"] == "ps"
    assert docs[0].metadata["party_id"] == "ps"
    assert docs[0].metadata["source"] == "manifesto.pdf"
    # page_content must NOT appear in metadata
    assert "page_content" not in docs[0].metadata
    assert "text" not in docs[0].metadata


def test_collection_exists_cache(vsh):
    """_collection_exists caches positive results: get_collections called only once."""
    # Reset the cache to a known state
    vsh._known_collections = set()

    collection_name = "test_collection_cache"

    mock_col = MagicMock()
    mock_col.name = collection_name
    collections_response = MagicMock()
    collections_response.collections = [mock_col]

    sync_client_mock = MagicMock()
    sync_client_mock.get_collections = MagicMock(return_value=collections_response)

    vsh.qdrant_client = sync_client_mock

    result1 = vsh._collection_exists(collection_name)
    result2 = vsh._collection_exists(collection_name)

    assert result1 is True
    assert result2 is True
    # get_collections should only have been called once (second call is cached)
    sync_client_mock.get_collections.assert_called_once()


@pytest.mark.asyncio
async def test_candidate_filter_priority(vsh):
    """When both candidate_id and municipality_code are passed, only
    candidate_id filter is used (if/elif branch)."""
    # Make the collection appear to exist
    vsh._known_collections = {"candidates_websites"}

    query_response = types.SimpleNamespace(points=[])

    async_client_mock = AsyncMock()
    async_client_mock.query_points = AsyncMock(return_value=query_response)

    embed_mock = AsyncMock()
    embed_mock.aembed_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

    vsh.async_qdrant_client = async_client_mock
    vsh.embed = embed_mock

    await vsh._identify_relevant_candidate_documents(
        rag_query="housing policy",
        candidate_id="cand_123",
        municipality_code="75056",
    )

    async_client_mock.query_points.assert_called_once()
    call_kwargs = async_client_mock.query_points.call_args.kwargs

    # Extract the filter to inspect conditions
    query_filter = call_kwargs["query_filter"]
    assert query_filter is not None

    # Collect all keys from must conditions in the filter
    must_conditions = query_filter.must
    condition_keys = [c.key for c in must_conditions]

    # candidate_id filter must be present
    assert "metadata.candidate_id" in condition_keys
    # municipality_code filter must NOT be present (elif branch was skipped)
    assert "metadata.municipality_code" not in condition_keys
