# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Unit tests for helper/filter functions in src/vector_store_helper.py.

All tests run without external services (no Qdrant, Firebase, LLM APIs, no Ollama).
Heavy imports are mocked before the module is imported.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Environment setup — must happen before any src imports
# ---------------------------------------------------------------------------

os.environ.setdefault("API_NAME", "chatvote-api")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("FIRESTORE_EMULATOR_HOST", "localhost:8081")
os.environ["GOOGLE_API_KEY"] = "fake-key-for-testing"
# Force Google embeddings — .env may set EMBEDDING_PROVIDER=ollama via load_dotenv
os.environ["EMBEDDING_PROVIDER"] = "google"

# ---------------------------------------------------------------------------
# Mock heavy modules before importing vector_store_helper
# ---------------------------------------------------------------------------

# chatbot_async — used for rerank_documents and Responder
mock_chatbot = MagicMock()
mock_chatbot.rerank_documents = AsyncMock(
    side_effect=lambda relevant_docs, **kw: relevant_docs[:5]
)
mock_chatbot.Responder = type("Responder", (), {"party_id": "test"})
sys.modules.setdefault("src.chatbot_async", mock_chatbot)

# Firebase / Firestore — not needed for filter tests
for _mod in (
    "firebase_admin",
    "firebase_admin.firestore",
    "firebase_admin.credentials",
    "firebase_admin.firestore_async",
    "src.firebase_service",
):
    sys.modules.setdefault(_mod, MagicMock())

# Embedding model — mock the langchain_google_genai import used by _get_embeddings()
_mock_embed_instance = MagicMock()
_mock_embed_instance.aembed_query = AsyncMock(return_value=[0.1] * 3072)
_mock_google_genai = MagicMock()
_mock_google_genai.GoogleGenerativeAIEmbeddings.return_value = _mock_embed_instance
sys.modules.setdefault("langchain_google_genai", _mock_google_genai)

# ---------------------------------------------------------------------------
# Import the module under test + Qdrant model types used in assertions
# ---------------------------------------------------------------------------

# Evict cached module so it re-imports with our mocked dependencies
sys.modules.pop("src.vector_store_helper", None)

from src import vector_store_helper  # noqa: E402  (imports after sys.modules patching)
from qdrant_client.models import (  # noqa: E402
    FieldCondition,
    Filter,
    MatchAny,
    Range,
)

# ---------------------------------------------------------------------------
# Replace module-level Qdrant clients with mocks AFTER import
# ---------------------------------------------------------------------------

_mock_qdrant = MagicMock()
_mock_async_qdrant = AsyncMock()
vector_store_helper.qdrant_client = _mock_qdrant
vector_store_helper.async_qdrant_client = _mock_async_qdrant


# ---------------------------------------------------------------------------
# Autouse fixture — reset shared state between every test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state():
    vector_store_helper._known_collections.clear()
    vector_store_helper._manifesto_namespaces = None
    _mock_qdrant.reset_mock(side_effect=True, return_value=True)
    _mock_async_qdrant.reset_mock(side_effect=True, return_value=True)
    yield


# ---------------------------------------------------------------------------
# Collection name constants
# ---------------------------------------------------------------------------


class TestCollectionNameConstants:
    def test_party_index_name(self):
        assert vector_store_helper.PARTY_INDEX_NAME == "all_parties"

    def test_candidates_index_name(self):
        assert vector_store_helper.CANDIDATES_INDEX_NAME == "candidates_websites"

    def test_voting_behavior_index_name(self):
        assert (
            vector_store_helper.VOTING_BEHAVIOR_INDEX_NAME
            == "justified_voting_behavior"
        )

    def test_parliamentary_questions_index_name(self):
        assert (
            vector_store_helper.PARLIAMENTARY_QUESTIONS_INDEX_NAME
            == "parliamentary_questions"
        )


# ---------------------------------------------------------------------------
# _build_party_filter()
# ---------------------------------------------------------------------------


class TestBuildPartyFilter:
    def test_returns_filter_instance(self):
        result = vector_store_helper._build_party_filter(["lfi"])
        assert isinstance(result, Filter)

    def test_single_party_id(self):
        result = vector_store_helper._build_party_filter(["lfi"])
        assert result.must is not None
        assert len(result.must) == 1
        condition = result.must[0]
        assert isinstance(condition, FieldCondition)
        assert condition.key == "metadata.party_ids"
        assert isinstance(condition.match, MatchAny)
        assert condition.match.any == ["lfi"]

    def test_multiple_party_ids(self):
        ids = ["lfi", "rn", "ps"]
        result = vector_store_helper._build_party_filter(ids)
        condition = result.must[0]
        assert isinstance(condition.match, MatchAny)
        assert condition.match.any == ids

    def test_empty_party_ids_list(self):
        result = vector_store_helper._build_party_filter([])
        assert result.must is not None
        condition = result.must[0]
        assert isinstance(condition.match, MatchAny)
        assert condition.match.any == []

    def test_must_not_is_absent(self):
        result = vector_store_helper._build_party_filter(["lfi"])
        assert not result.must_not


# ---------------------------------------------------------------------------
# _build_fiabilite_filter()
# ---------------------------------------------------------------------------


class TestBuildFiabiliteFilter:
    def test_returns_filter_instance(self):
        result = vector_store_helper._build_fiabilite_filter()
        assert isinstance(result, Filter)

    def test_default_max_fiabilite_is_3(self):
        result = vector_store_helper._build_fiabilite_filter()
        assert result.must_not is not None
        assert len(result.must_not) == 1
        condition = result.must_not[0]
        assert isinstance(condition, FieldCondition)
        assert condition.key == "metadata.fiabilite"
        assert isinstance(condition.range, Range)
        assert condition.range.gt == 3

    def test_custom_max_fiabilite(self):
        result = vector_store_helper._build_fiabilite_filter(max_fiabilite=5)
        condition = result.must_not[0]
        assert condition.range.gt == 5

    def test_uses_must_not_not_must(self):
        result = vector_store_helper._build_fiabilite_filter()
        assert result.must_not is not None
        assert not result.must

    def test_max_fiabilite_zero(self):
        result = vector_store_helper._build_fiabilite_filter(max_fiabilite=0)
        condition = result.must_not[0]
        assert condition.range.gt == 0


# ---------------------------------------------------------------------------
# _combine_filters()
# ---------------------------------------------------------------------------


class TestCombineFilters:
    def _party_filter(self, ids=None):
        return vector_store_helper._build_party_filter(ids or ["lfi"])

    def _fiabilite_filter(self, max_fiabilite=3):
        return vector_store_helper._build_fiabilite_filter(max_fiabilite)

    def test_returns_none_when_all_filters_are_none(self):
        result = vector_store_helper._combine_filters(None, None, None)
        assert result is None

    def test_returns_none_for_no_arguments(self):
        result = vector_store_helper._combine_filters()
        assert result is None

    def test_single_filter_with_must(self):
        f = self._party_filter(["rn"])
        result = vector_store_helper._combine_filters(f)
        assert isinstance(result, Filter)
        assert result.must is not None
        assert len(result.must) == 1
        assert result.must_not is None

    def test_single_filter_with_must_not(self):
        f = self._fiabilite_filter()
        result = vector_store_helper._combine_filters(f)
        assert result.must_not is not None
        assert len(result.must_not) == 1
        assert result.must is None

    def test_combines_two_must_conditions(self):
        f1 = self._party_filter(["lfi"])
        f2 = self._party_filter(["rn"])
        result = vector_store_helper._combine_filters(f1, f2)
        assert result.must is not None
        assert len(result.must) == 2

    def test_combines_must_and_must_not_from_separate_filters(self):
        party_f = self._party_filter(["lfi"])
        fiab_f = self._fiabilite_filter()
        result = vector_store_helper._combine_filters(party_f, fiab_f)
        assert result.must is not None
        assert len(result.must) == 1
        assert result.must_not is not None
        assert len(result.must_not) == 1

    def test_skips_none_filters_in_mix(self):
        party_f = self._party_filter(["ps"])
        result = vector_store_helper._combine_filters(None, party_f, None)
        assert result is not None
        assert len(result.must) == 1

    def test_combined_filter_must_contains_correct_keys(self):
        party_f = self._party_filter(["lfi", "rn"])
        fiab_f = self._fiabilite_filter(max_fiabilite=2)
        result = vector_store_helper._combine_filters(party_f, fiab_f)
        must_keys = [c.key for c in result.must]
        must_not_keys = [c.key for c in result.must_not]
        assert "metadata.party_ids" in must_keys
        assert "metadata.fiabilite" in must_not_keys

    def test_three_must_filters_combined(self):
        f1 = self._party_filter(["lfi"])
        f2 = self._party_filter(["rn"])
        f3 = self._party_filter(["ps"])
        result = vector_store_helper._combine_filters(f1, f2, f3)
        assert len(result.must) == 3


# ---------------------------------------------------------------------------
# _collection_exists()
# ---------------------------------------------------------------------------


class TestCollectionExists:
    def test_returns_true_when_collection_exists(self):
        # get_collection (singular) succeeds → collection exists
        _mock_qdrant.get_collection.return_value = MagicMock()
        assert vector_store_helper._collection_exists("candidates_websites") is True

    def test_returns_false_when_collection_does_not_exist(self):
        # get_collection raises → collection not found
        _mock_qdrant.get_collection.side_effect = Exception("Not found")
        assert vector_store_helper._collection_exists("candidates_websites") is False

    def test_positive_result_is_cached_and_avoids_second_call(self):
        _mock_qdrant.get_collection.return_value = MagicMock()
        # First call hits the client
        vector_store_helper._collection_exists("all_parties")
        # Second call should use the cache — client is called only once
        vector_store_helper._collection_exists("all_parties")
        assert _mock_qdrant.get_collection.call_count == 1

    def test_negative_result_is_not_cached(self):
        _mock_qdrant.get_collection.side_effect = Exception("Not found")
        vector_store_helper._collection_exists("missing_col")
        vector_store_helper._collection_exists("missing_col")
        # Both calls must hit the client since False is not cached
        assert _mock_qdrant.get_collection.call_count == 2

    def test_returns_false_on_connection_error(self):
        _mock_qdrant.get_collection.side_effect = ConnectionError("unreachable")
        result = vector_store_helper._collection_exists("all_parties")
        assert result is False

    def test_returns_false_on_generic_exception(self):
        _mock_qdrant.get_collection.side_effect = RuntimeError("unexpected")
        result = vector_store_helper._collection_exists("all_parties")
        assert result is False

    def test_cache_populated_after_positive_result(self):
        _mock_qdrant.get_collection.return_value = MagicMock()
        vector_store_helper._collection_exists("all_parties")
        assert "all_parties" in vector_store_helper._known_collections

    def test_cache_not_populated_after_negative_result(self):
        _mock_qdrant.get_collection.side_effect = Exception("Not found")
        vector_store_helper._collection_exists("missing_col")
        assert "missing_col" not in vector_store_helper._known_collections

    def test_prepopulated_cache_skips_client_entirely(self):
        # Seed the cache directly (simulates a previous positive lookup)
        vector_store_helper._known_collections.add("all_parties")
        result = vector_store_helper._collection_exists("all_parties")
        assert result is True
        _mock_qdrant.get_collection.assert_not_called()
