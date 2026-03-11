"""Tests for src.services.qdrant_ops."""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# We must mock the heavy imports before importing the module under test.
# src.services.qdrant_ops imports from src.vector_store_helper at module level.

_mock_qdrant_client = MagicMock(name="qdrant_client")
_mock_embed = MagicMock(name="embed")
_MOCK_DIM = 3072

_vsh_patch = patch.dict(
    "sys.modules",
    {
        "src.vector_store_helper": MagicMock(
            qdrant_client=_mock_qdrant_client,
            embed=_mock_embed,
            EMBEDDING_DIM=_MOCK_DIM,
            PARTY_INDEX_NAME="all_parties_dev",
            CANDIDATES_INDEX_NAME="candidates_websites_dev",
        ),
    },
)
_vsh_patch.start()

# Now safe to import
from src.services.qdrant_ops import (
    ensure_collection,
    delete_by_namespace,
    count_by_namespace,
    get_indexed_namespaces,
    get_vector_store,
    _ensured_collections,
)
from qdrant_client.models import PayloadSchemaType


# ── fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset():
    """Reset module-level state and mock call counts between tests."""
    _ensured_collections.clear()
    _mock_qdrant_client.reset_mock(side_effect=True, return_value=True)
    yield
    _ensured_collections.clear()


def _collection_obj(name: str):
    return SimpleNamespace(name=name)


def _collection_info(dim: int, named: bool = True):
    """Simulate qdrant_client.get_collection() response."""
    if named:
        vectors = {"dense": SimpleNamespace(size=dim)}
    else:
        vectors = SimpleNamespace(size=dim)
    return SimpleNamespace(config=SimpleNamespace(params=SimpleNamespace(vectors=vectors)))


# ── ensure_collection ────────────────────────────────────────────────────────


class TestEnsureCollection:
    def test_creates_collection_when_missing(self):
        _mock_qdrant_client.get_collections.return_value = SimpleNamespace(collections=[])
        _mock_qdrant_client.create_payload_index.return_value = None

        ensure_collection("all_parties_dev")

        _mock_qdrant_client.create_collection.assert_called_once()
        call_kwargs = _mock_qdrant_client.create_collection.call_args
        assert call_kwargs.kwargs["collection_name"] == "all_parties_dev"
        assert "all_parties_dev" in _ensured_collections

    def test_skips_when_cached(self):
        _ensured_collections.add("all_parties_dev")
        ensure_collection("all_parties_dev")
        _mock_qdrant_client.get_collections.assert_not_called()

    def test_skips_creation_when_exists_with_correct_dim(self):
        _mock_qdrant_client.get_collections.return_value = SimpleNamespace(
            collections=[_collection_obj("all_parties_dev")]
        )
        _mock_qdrant_client.get_collection.return_value = _collection_info(_MOCK_DIM)
        _mock_qdrant_client.create_payload_index.return_value = None

        ensure_collection("all_parties_dev")

        _mock_qdrant_client.create_collection.assert_not_called()
        _mock_qdrant_client.delete_collection.assert_not_called()

    def test_recreates_on_dimension_mismatch(self):
        _mock_qdrant_client.get_collections.return_value = SimpleNamespace(
            collections=[_collection_obj("all_parties_dev")]
        )
        _mock_qdrant_client.get_collection.return_value = _collection_info(1536)  # wrong dim
        _mock_qdrant_client.create_payload_index.return_value = None

        ensure_collection("all_parties_dev")

        _mock_qdrant_client.delete_collection.assert_called_once_with("all_parties_dev")
        assert _mock_qdrant_client.create_collection.call_count == 1

    def test_creates_standard_payload_indexes(self):
        _mock_qdrant_client.get_collections.return_value = SimpleNamespace(collections=[])
        _mock_qdrant_client.create_payload_index.return_value = None

        ensure_collection("all_parties_dev")

        index_calls = _mock_qdrant_client.create_payload_index.call_args_list
        field_names = [c.kwargs["field_name"] for c in index_calls]
        assert "metadata.namespace" in field_names
        assert "metadata.party_ids" in field_names
        assert "metadata.fiabilite" in field_names

    def test_creates_candidate_indexes_for_candidates_collection(self):
        _mock_qdrant_client.get_collections.return_value = SimpleNamespace(collections=[])
        _mock_qdrant_client.create_payload_index.return_value = None

        ensure_collection("candidates_websites_dev")

        index_calls = _mock_qdrant_client.create_payload_index.call_args_list
        field_names = [c.kwargs["field_name"] for c in index_calls]
        # Standard + candidate-specific indexes
        assert "metadata.namespace" in field_names
        assert "metadata.municipality_code" in field_names
        assert "metadata.candidate_id" in field_names

    def test_ignores_already_exists_index_error(self):
        _mock_qdrant_client.get_collections.return_value = SimpleNamespace(collections=[])
        _mock_qdrant_client.create_payload_index.side_effect = Exception("Index already exists")

        # Should NOT raise
        ensure_collection("all_parties_dev")
        assert "all_parties_dev" in _ensured_collections

    def test_propagates_non_index_errors(self):
        _mock_qdrant_client.get_collections.side_effect = ConnectionError("no qdrant")

        with pytest.raises(ConnectionError):
            ensure_collection("all_parties_dev")

    def test_handles_flat_vectors_config(self):
        """When vectors_config is not a dict but a direct VectorParams object."""
        _mock_qdrant_client.get_collections.return_value = SimpleNamespace(
            collections=[_collection_obj("all_parties_dev")]
        )
        _mock_qdrant_client.get_collection.return_value = _collection_info(_MOCK_DIM, named=False)
        _mock_qdrant_client.create_payload_index.return_value = None

        ensure_collection("all_parties_dev")
        _mock_qdrant_client.create_collection.assert_not_called()


# ── delete_by_namespace ──────────────────────────────────────────────────────


class TestDeleteByNamespace:
    def test_calls_qdrant_delete_with_correct_filter(self):
        # Ensure collection is already cached so we don't hit get_collections
        _ensured_collections.add("all_parties_dev")

        delete_by_namespace("all_parties_dev", "renaissance")

        _mock_qdrant_client.delete.assert_called_once()
        call_kwargs = _mock_qdrant_client.delete.call_args.kwargs
        assert call_kwargs["collection_name"] == "all_parties_dev"
        selector = call_kwargs["points_selector"]
        condition = selector.filter.must[0]
        assert condition.key == "metadata.namespace"
        assert condition.match.value == "renaissance"

    def test_ensures_collection_first(self):
        _mock_qdrant_client.get_collections.return_value = SimpleNamespace(collections=[])
        _mock_qdrant_client.create_payload_index.return_value = None

        delete_by_namespace("all_parties_dev", "some_ns")

        _mock_qdrant_client.create_collection.assert_called_once()
        _mock_qdrant_client.delete.assert_called_once()


# ── count_by_namespace ───────────────────────────────────────────────────────


class TestCountByNamespace:
    def test_returns_count(self):
        _ensured_collections.add("all_parties_dev")
        _mock_qdrant_client.count.return_value = SimpleNamespace(count=42)

        result = count_by_namespace("all_parties_dev", "renaissance")

        assert result == 42
        call_kwargs = _mock_qdrant_client.count.call_args.kwargs
        assert call_kwargs["collection_name"] == "all_parties_dev"

    def test_returns_zero_on_error(self):
        _ensured_collections.add("all_parties_dev")
        _mock_qdrant_client.count.side_effect = Exception("timeout")

        result = count_by_namespace("all_parties_dev", "renaissance")
        assert result == 0


# ── get_indexed_namespaces ───────────────────────────────────────────────────


class TestGetIndexedNamespaces:
    def test_aggregates_namespace_counts(self):
        _ensured_collections.add("all_parties_dev")

        point_a = SimpleNamespace(payload={"metadata": {"namespace": "renaissance"}})
        point_b = SimpleNamespace(payload={"metadata": {"namespace": "renaissance"}})
        point_c = SimpleNamespace(payload={"metadata": {"namespace": "lfi"}})

        # First scroll returns points, second returns empty
        _mock_qdrant_client.scroll.side_effect = [
            ([point_a, point_b, point_c], None),
        ]

        result = get_indexed_namespaces("all_parties_dev")

        assert result == {"renaissance": 2, "lfi": 1}

    def test_handles_pagination(self):
        _ensured_collections.add("all_parties_dev")

        p1 = SimpleNamespace(payload={"metadata": {"namespace": "ns1"}})
        p2 = SimpleNamespace(payload={"metadata": {"namespace": "ns2"}})

        _mock_qdrant_client.scroll.side_effect = [
            ([p1], "offset_token"),
            ([p2], None),
        ]

        result = get_indexed_namespaces("all_parties_dev")
        assert result == {"ns1": 1, "ns2": 1}
        assert _mock_qdrant_client.scroll.call_count == 2

    def test_returns_empty_on_error(self):
        _ensured_collections.add("all_parties_dev")
        _mock_qdrant_client.scroll.side_effect = Exception("connection lost")

        result = get_indexed_namespaces("all_parties_dev")
        assert result == {}

    def test_skips_points_without_namespace(self):
        _ensured_collections.add("all_parties_dev")

        p1 = SimpleNamespace(payload={"metadata": {"namespace": "ns1"}})
        p2 = SimpleNamespace(payload={"metadata": {}})
        p3 = SimpleNamespace(payload=None)

        _mock_qdrant_client.scroll.side_effect = [
            ([p1, p2, p3], None),
        ]

        result = get_indexed_namespaces("all_parties_dev")
        assert result == {"ns1": 1}


# ── get_vector_store ─────────────────────────────────────────────────────────


class TestGetVectorStore:
    def test_returns_qdrant_vector_store(self):
        _ensured_collections.add("all_parties_dev")

        with patch("src.services.qdrant_ops.ensure_collection"):
            with patch("langchain_qdrant.QdrantVectorStore") as MockVS:
                mock_instance = MagicMock()
                MockVS.return_value = mock_instance

                result = get_vector_store("all_parties_dev")

                MockVS.assert_called_once_with(
                    client=_mock_qdrant_client,
                    collection_name="all_parties_dev",
                    embedding=_mock_embed,
                    vector_name="dense",
                    content_payload_key="page_content",
                )
                assert result is mock_instance
