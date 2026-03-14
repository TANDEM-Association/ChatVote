# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Unit tests for src/firebase_service.py.

Firebase Admin SDK is mocked at the sys.modules level BEFORE importing
firebase_service, because that module initialises Firebase at import time.
All tests run without any external services.

Mock strategy
-------------
- firebase_admin and its sub-packages are injected into sys.modules so that
  the module-level initialisation code does not attempt real connections.
- After import, firebase_service.db and firebase_service.async_db are patched
  per-test via patch.object fixtures so every test gets a clean, independent
  mock without interference from pytest-xdist workers or fixture resets.
"""

import os
import sys
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Environment must be set before any src imports to satisfy load_env()
# ---------------------------------------------------------------------------
os.environ["API_NAME"] = "chatvote-api"
os.environ["ENV"] = "local"
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8081"

# ---------------------------------------------------------------------------
# Stub out firebase_admin and sub-modules before firebase_service is imported.
# We only need the initialisation calls not to raise; the actual db clients
# are replaced per-test via patch.object below.
# ---------------------------------------------------------------------------
_stub_admin = MagicMock()
_stub_admin._apps = {}  # falsy → triggers initialize_app branch
_stub_firestore = MagicMock()
_stub_firestore_async = MagicMock()
_stub_credentials = MagicMock()

sys.modules.setdefault("firebase_admin", _stub_admin)
sys.modules.setdefault("firebase_admin.firestore", _stub_firestore)
sys.modules.setdefault("firebase_admin.credentials", _stub_credentials)
sys.modules.setdefault("firebase_admin.firestore_async", _stub_firestore_async)

# firebase_service reads firestore.client() and firestore_async.client() at
# module level.  Give them stable return values so the module loads cleanly.
_stub_firestore.client.return_value = MagicMock()
_stub_firestore_async.client.return_value = MagicMock()

# Evict any mock of src.firebase_service set by other test files (e.g. test_chatbot_async.py)
sys.modules.pop("src.firebase_service", None)

# Safe to import now.
from src import firebase_service  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockAsyncStream:
    """Minimal async iterator to simulate a Firestore async stream."""

    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


def make_sync_doc(data: dict, exists: bool = True) -> MagicMock:
    """Return a MagicMock that behaves like a Firestore DocumentSnapshot."""
    doc = MagicMock()
    doc.exists = exists
    doc.to_dict.return_value = data if exists else {}
    # Support question.get("content") used in proposed-questions stream
    doc.get = lambda field: data.get(field) if exists else None
    return doc


def make_async_doc(data: dict, exists: bool = True) -> MagicMock:
    """Same as make_sync_doc but returned by an awaited .get() call."""
    return make_sync_doc(data, exists)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

PARTY_DATA = {
    "party_id": "lfi",
    "name": "LFI",
    "long_name": "La France Insoumise",
    "description": "Parti de gauche",
    "website_url": "https://lafranceinsoumise.fr",
    "candidate": "Jean-Luc Mélenchon",
    "election_manifesto_url": "https://lafranceinsoumise.fr/programme.pdf",
}

PARTY_DATA_2 = {
    **PARTY_DATA,
    "party_id": "rn",
    "name": "RN",
    "long_name": "Rassemblement National",
    "candidate": "Marine Le Pen",
}

CANDIDATE_DATA = {
    "candidate_id": "cand-001",
    "first_name": "Marie",
    "last_name": "Dupont",
    "election_type_id": "municipales-2026",
    "municipality_code": "75056",
    "municipality_name": "Paris",
    "website_url": "https://marie-dupont.fr",
}

CACHED_RESPONSE_DATA = {
    "content": "Voici la réponse cached.",
    "sources": [{"url": "https://example.com"}],
    "created_at": datetime(2026, 1, 1, 12, 0, 0),
    "rag_query": ["impôts", "fiscalité"],
    "cached_conversation_history": None,
    "depth": 2,
    "user_message_depth": 1,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_cache():
    """Reset the TTL cache dictionaries before and after every test."""
    firebase_service._cache.clear()
    firebase_service._cache_expiry.clear()
    yield
    firebase_service._cache.clear()
    firebase_service._cache_expiry.clear()


@pytest.fixture()
def sync_db():
    """Patch firebase_service.db with a fresh MagicMock for this test."""
    db = MagicMock()
    with patch.object(firebase_service, "db", db):
        yield db


@pytest.fixture()
def async_db():
    """Patch firebase_service.async_db with a fresh MagicMock for this test."""
    db = MagicMock()
    with patch.object(firebase_service, "async_db", db):
        yield db


# ===========================================================================
# _cached_get
# ===========================================================================


class TestCachedGet:
    @pytest.mark.asyncio
    async def test_cache_miss_calls_fetch_fn(self):
        """First call with a new key → fetch_fn must be awaited."""
        fetch_fn = AsyncMock(return_value=["result"])
        result = await firebase_service._cached_get("key_miss", fetch_fn)
        assert result == ["result"]
        fetch_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cache_miss_stores_result(self):
        """After a miss the result is written into _cache and _cache_expiry."""
        fetch_fn = AsyncMock(return_value=42)
        await firebase_service._cached_get("key_store", fetch_fn)
        assert firebase_service._cache["key_store"] == 42
        assert firebase_service._cache_expiry["key_store"] > time.time()

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self):
        """Call within TTL: fetch_fn must NOT be invoked."""
        firebase_service._cache["key_hit"] = "cached_value"
        firebase_service._cache_expiry["key_hit"] = time.time() + 3600

        fetch_fn = AsyncMock(return_value="new_value")
        result = await firebase_service._cached_get("key_hit", fetch_fn)

        assert result == "cached_value"
        fetch_fn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cache_hit_does_not_overwrite_stored_entry(self):
        """The cache dict must not be mutated on a hit."""
        firebase_service._cache["stable"] = "original"
        firebase_service._cache_expiry["stable"] = time.time() + 3600

        await firebase_service._cached_get("stable", AsyncMock(return_value="new"))
        assert firebase_service._cache["stable"] == "original"

    @pytest.mark.asyncio
    async def test_expired_entry_calls_fetch_fn(self):
        """Expiry in the past → cache miss, fetch_fn invoked."""
        firebase_service._cache["old"] = "stale"
        firebase_service._cache_expiry["old"] = time.time() - 1  # expired

        fetch_fn = AsyncMock(return_value="refreshed")
        result = await firebase_service._cached_get("old", fetch_fn)

        assert result == "refreshed"
        fetch_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_expired_entry_updates_stored_value(self):
        """New value replaces the stale entry after a refresh."""
        firebase_service._cache["upd"] = "stale"
        firebase_service._cache_expiry["upd"] = time.time() - 1

        await firebase_service._cached_get("upd", AsyncMock(return_value="fresh"))
        assert firebase_service._cache["upd"] == "fresh"

    @pytest.mark.asyncio
    async def test_different_keys_are_independent(self):
        """Separate keys have independent cache slots."""
        fn_a = AsyncMock(return_value="a")
        fn_b = AsyncMock(return_value="b")

        await firebase_service._cached_get("key_a", fn_a)
        await firebase_service._cached_get("key_b", fn_b)

        fn_a.assert_awaited_once()
        fn_b.assert_awaited_once()

        # Second round: both are now hits
        result_a = await firebase_service._cached_get("key_a", fn_a)
        result_b = await firebase_service._cached_get("key_b", fn_b)
        assert result_a == "a"
        assert result_b == "b"
        assert fn_a.await_count == 1
        assert fn_b.await_count == 1


# ===========================================================================
# aget_parties
# ===========================================================================


class TestAgetParties:
    @pytest.mark.asyncio
    async def test_returns_list_of_party_objects(self, sync_db):
        doc = make_sync_doc(PARTY_DATA)
        sync_db.collection.return_value.stream.return_value = [doc]

        parties = await firebase_service.aget_parties()

        assert len(parties) == 1
        assert parties[0].party_id == "lfi"
        assert parties[0].name == "LFI"

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self, sync_db):
        """Firestore stream must only be called once across two awaits."""
        doc = make_sync_doc(PARTY_DATA)
        sync_db.collection.return_value.stream.return_value = [doc]

        await firebase_service.aget_parties()
        await firebase_service.aget_parties()

        assert sync_db.collection.return_value.stream.call_count == 1

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_collection(self, sync_db):
        sync_db.collection.return_value.stream.return_value = []

        parties = await firebase_service.aget_parties()

        assert parties == []

    @pytest.mark.asyncio
    async def test_returns_multiple_parties(self, sync_db):
        docs = [make_sync_doc(PARTY_DATA), make_sync_doc(PARTY_DATA_2)]
        sync_db.collection.return_value.stream.return_value = docs

        parties = await firebase_service.aget_parties()

        assert len(parties) == 2
        assert {p.party_id for p in parties} == {"lfi", "rn"}


# ===========================================================================
# aget_party_by_id
# ===========================================================================


class TestAgetPartyById:
    @pytest.mark.asyncio
    async def test_returns_party_when_doc_exists(self, sync_db):
        doc = make_sync_doc(PARTY_DATA, exists=True)
        sync_db.collection.return_value.document.return_value.get.return_value = doc

        party = await firebase_service.aget_party_by_id("lfi")

        assert party is not None
        assert party.party_id == "lfi"

    @pytest.mark.asyncio
    async def test_returns_none_when_doc_does_not_exist(self, sync_db):
        doc = make_sync_doc({}, exists=False)
        sync_db.collection.return_value.document.return_value.get.return_value = doc

        party = await firebase_service.aget_party_by_id("nonexistent")

        assert party is None

    @pytest.mark.asyncio
    async def test_caches_result_on_second_call(self, sync_db):
        doc = make_sync_doc(PARTY_DATA, exists=True)
        sync_db.collection.return_value.document.return_value.get.return_value = doc

        p1 = await firebase_service.aget_party_by_id("lfi")
        p2 = await firebase_service.aget_party_by_id("lfi")

        assert p1 == p2
        assert sync_db.collection.return_value.document.return_value.get.call_count == 1

    @pytest.mark.asyncio
    async def test_different_party_ids_use_separate_cache_keys(self, sync_db):
        doc_lfi = make_sync_doc(PARTY_DATA, exists=True)
        doc_rn = make_sync_doc(PARTY_DATA_2, exists=True)
        sync_db.collection.return_value.document.return_value.get.side_effect = [
            doc_lfi,
            doc_rn,
        ]

        lfi = await firebase_service.aget_party_by_id("lfi")
        rn = await firebase_service.aget_party_by_id("rn")

        assert lfi.party_id == "lfi"
        assert rn.party_id == "rn"
        assert "party:lfi" in firebase_service._cache
        assert "party:rn" in firebase_service._cache


# ===========================================================================
# aget_proposed_questions_for_party
# ===========================================================================


class TestAgetProposedQuestionsForParty:
    @pytest.mark.asyncio
    async def test_returns_list_of_question_strings(self, async_db):
        q1 = make_sync_doc({"content": "Quelle est votre position sur l'immigration ?"})
        q2 = make_sync_doc({"content": "Que pensez-vous de la réforme des retraites ?"})
        async_db.collection.return_value.stream.return_value = MockAsyncStream([q1, q2])

        questions = await firebase_service.aget_proposed_questions_for_party("lfi")

        assert len(questions) == 2
        assert "Quelle est votre position sur l'immigration ?" in questions
        assert "Que pensez-vous de la réforme des retraites ?" in questions

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_questions(self, async_db):
        async_db.collection.return_value.stream.return_value = MockAsyncStream([])

        questions = await firebase_service.aget_proposed_questions_for_party("lfi")

        assert questions == []

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self, async_db):
        q = make_sync_doc({"content": "Question?"})
        async_db.collection.return_value.stream.return_value = MockAsyncStream([q])

        await firebase_service.aget_proposed_questions_for_party("rn")
        # Reset the stream to verify it is NOT consumed a second time
        async_db.collection.return_value.stream.return_value = MockAsyncStream([])
        await firebase_service.aget_proposed_questions_for_party("rn")

        # stream was only set up once → call count for collection() should be 1
        assert async_db.collection.call_count == 1

    @pytest.mark.asyncio
    async def test_queries_correct_subcollection_path(self, async_db):
        async_db.collection.return_value.stream.return_value = MockAsyncStream([])

        await firebase_service.aget_proposed_questions_for_party("lfi")

        async_db.collection.assert_called_with("proposed_questions/lfi/questions")


# ===========================================================================
# aget_cached_answers_for_party
# ===========================================================================


class TestAgetCachedAnswersForParty:
    @pytest.mark.asyncio
    async def test_returns_list_of_cached_response_objects(self, async_db):
        doc = make_sync_doc(CACHED_RESPONSE_DATA)
        async_db.collection.return_value.stream.return_value = MockAsyncStream([doc])

        responses = await firebase_service.aget_cached_answers_for_party(
            "lfi", "hash-abc"
        )

        assert len(responses) == 1
        assert responses[0].content == "Voici la réponse cached."

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_cached_answers(self, async_db):
        async_db.collection.return_value.stream.return_value = MockAsyncStream([])

        responses = await firebase_service.aget_cached_answers_for_party(
            "lfi", "hash-xyz"
        )

        assert responses == []

    @pytest.mark.asyncio
    async def test_returns_multiple_cached_responses(self, async_db):
        doc1 = make_sync_doc(CACHED_RESPONSE_DATA)
        doc2 = make_sync_doc({**CACHED_RESPONSE_DATA, "content": "Autre réponse."})
        async_db.collection.return_value.stream.return_value = MockAsyncStream(
            [doc1, doc2]
        )

        responses = await firebase_service.aget_cached_answers_for_party(
            "ps", "hash-multi"
        )

        assert len(responses) == 2
        assert {r.content for r in responses} == {
            "Voici la réponse cached.",
            "Autre réponse.",
        }

    @pytest.mark.asyncio
    async def test_queries_correct_subcollection_path(self, async_db):
        async_db.collection.return_value.stream.return_value = MockAsyncStream([])

        await firebase_service.aget_cached_answers_for_party("lfi", "key123")

        async_db.collection.assert_called_with("cached_answers/lfi/key123")


# ===========================================================================
# awrite_cached_answer_for_party
# ===========================================================================


class TestAwriteCachedAnswerForParty:
    @pytest.mark.asyncio
    async def test_calls_firestore_set_with_model_dump(self, async_db):
        from src.models.chat import CachedResponse

        answer = CachedResponse(**CACHED_RESPONSE_DATA)
        doc_ref = MagicMock()
        doc_ref.set = AsyncMock()
        async_db.collection.return_value.document.return_value = doc_ref

        await firebase_service.awrite_cached_answer_for_party("lfi", "hash-abc", answer)

        doc_ref.set.assert_awaited_once_with(answer.model_dump())

    @pytest.mark.asyncio
    async def test_uses_correct_collection_path(self, async_db):
        from src.models.chat import CachedResponse

        answer = CachedResponse(**CACHED_RESPONSE_DATA)
        doc_ref = MagicMock()
        doc_ref.set = AsyncMock()
        async_db.collection.return_value.document.return_value = doc_ref

        await firebase_service.awrite_cached_answer_for_party("rn", "hash-rn", answer)

        async_db.collection.assert_called_with("cached_answers/rn/hash-rn")

    @pytest.mark.asyncio
    async def test_calls_document_with_no_id_for_auto_id(self, async_db):
        """Passing no argument to .document() requests an auto-generated ID."""
        from src.models.chat import CachedResponse

        answer = CachedResponse(**CACHED_RESPONSE_DATA)
        doc_ref = MagicMock()
        doc_ref.set = AsyncMock()
        async_db.collection.return_value.document.return_value = doc_ref

        await firebase_service.awrite_cached_answer_for_party("lfi", "hash-abc", answer)

        async_db.collection.return_value.document.assert_called_once_with()


# ===========================================================================
# awrite_llm_status
# ===========================================================================


class TestAwriteLlmStatus:
    @pytest.mark.asyncio
    async def test_sets_rate_limit_true(self, async_db):
        doc_ref = MagicMock()
        doc_ref.set = AsyncMock()
        async_db.collection.return_value.document.return_value = doc_ref

        await firebase_service.awrite_llm_status(is_at_rate_limit=True)

        doc_ref.set.assert_awaited_once_with({"is_at_rate_limit": True})

    @pytest.mark.asyncio
    async def test_sets_rate_limit_false(self, async_db):
        doc_ref = MagicMock()
        doc_ref.set = AsyncMock()
        async_db.collection.return_value.document.return_value = doc_ref

        await firebase_service.awrite_llm_status(is_at_rate_limit=False)

        doc_ref.set.assert_awaited_once_with({"is_at_rate_limit": False})

    @pytest.mark.asyncio
    async def test_targets_correct_collection_and_document(self, async_db):
        doc_ref = MagicMock()
        doc_ref.set = AsyncMock()
        async_db.collection.return_value.document.return_value = doc_ref

        await firebase_service.awrite_llm_status(is_at_rate_limit=False)

        async_db.collection.assert_called_with("system_status")
        async_db.collection.return_value.document.assert_called_with("llm_status")


# ===========================================================================
# aget_candidates
# ===========================================================================


class TestAgetCandidates:
    @pytest.mark.asyncio
    async def test_returns_list_of_candidate_objects(self, sync_db):
        doc = make_sync_doc(CANDIDATE_DATA)
        sync_db.collection.return_value.stream.return_value = [doc]

        candidates = await firebase_service.aget_candidates()

        assert len(candidates) == 1
        assert candidates[0].candidate_id == "cand-001"

    @pytest.mark.asyncio
    async def test_skips_malformed_documents(self, sync_db):
        """Docs that fail Candidate(**data) construction are silently skipped."""
        good_doc = make_sync_doc(CANDIDATE_DATA)
        bad_doc = make_sync_doc({"garbage": "data"})  # missing required fields
        sync_db.collection.return_value.stream.return_value = [good_doc, bad_doc]

        candidates = await firebase_service.aget_candidates()

        assert len(candidates) == 1
        assert candidates[0].candidate_id == "cand-001"

    @pytest.mark.asyncio
    async def test_all_malformed_docs_returns_empty_list(self, sync_db):
        """If every doc is malformed the result is [] with no crash."""
        sync_db.collection.return_value.stream.return_value = [
            make_sync_doc({"x": 1}),
            make_sync_doc({"y": 2}),
        ]

        candidates = await firebase_service.aget_candidates()

        assert candidates == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_collection(self, sync_db):
        sync_db.collection.return_value.stream.return_value = []

        candidates = await firebase_service.aget_candidates()

        assert candidates == []

    @pytest.mark.asyncio
    async def test_uses_cache_on_second_call(self, sync_db):
        doc = make_sync_doc(CANDIDATE_DATA)
        sync_db.collection.return_value.stream.return_value = [doc]

        await firebase_service.aget_candidates()
        await firebase_service.aget_candidates()

        assert sync_db.collection.return_value.stream.call_count == 1


# ===========================================================================
# aget_candidates_by_municipality
# ===========================================================================


class TestAgetCandidatesByMunicipality:
    @pytest.mark.asyncio
    async def test_returns_candidates_for_municipality(self, async_db):
        doc = make_sync_doc(CANDIDATE_DATA)
        async_db.collection.return_value.where.return_value.stream.return_value = (
            MockAsyncStream([doc])
        )

        candidates = await firebase_service.aget_candidates_by_municipality("75056")

        assert len(candidates) == 1
        assert candidates[0].municipality_code == "75056"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_match(self, async_db):
        async_db.collection.return_value.where.return_value.stream.return_value = (
            MockAsyncStream([])
        )

        candidates = await firebase_service.aget_candidates_by_municipality("99999")

        assert candidates == []

    @pytest.mark.asyncio
    async def test_filters_by_correct_field_and_value(self, async_db):
        async_db.collection.return_value.where.return_value.stream.return_value = (
            MockAsyncStream([])
        )

        await firebase_service.aget_candidates_by_municipality("75056")

        async_db.collection.return_value.where.assert_called_once_with(
            "municipality_code", "==", "75056"
        )

    @pytest.mark.asyncio
    async def test_queries_candidates_collection(self, async_db):
        async_db.collection.return_value.where.return_value.stream.return_value = (
            MockAsyncStream([])
        )

        await firebase_service.aget_candidates_by_municipality("75056")

        async_db.collection.assert_called_with("candidates")


# ===========================================================================
# aget_candidate_by_id
# ===========================================================================


class TestAgetCandidateById:
    @pytest.mark.asyncio
    async def test_returns_candidate_when_exists(self, async_db):
        doc = make_async_doc(CANDIDATE_DATA, exists=True)
        async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )

        candidate = await firebase_service.aget_candidate_by_id("cand-001")

        assert candidate is not None
        assert candidate.candidate_id == "cand-001"
        assert candidate.first_name == "Marie"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, async_db):
        doc = make_async_doc({}, exists=False)
        async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )

        candidate = await firebase_service.aget_candidate_by_id("nonexistent")

        assert candidate is None

    @pytest.mark.asyncio
    async def test_queries_correct_document(self, async_db):
        doc = make_async_doc(CANDIDATE_DATA, exists=True)
        async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )

        await firebase_service.aget_candidate_by_id("cand-001")

        async_db.collection.return_value.document.assert_called_with("cand-001")

    @pytest.mark.asyncio
    async def test_queries_candidates_collection(self, async_db):
        doc = make_async_doc(CANDIDATE_DATA, exists=True)
        async_db.collection.return_value.document.return_value.get = AsyncMock(
            return_value=doc
        )

        await firebase_service.aget_candidate_by_id("cand-001")

        async_db.collection.assert_called_with("candidates")


# ===========================================================================
# aget_candidates_with_website
# ===========================================================================


class TestAgetCandidatesWithWebsite:
    @pytest.mark.asyncio
    async def test_returns_only_candidates_with_website_url(self, sync_db):
        doc_with = make_sync_doc(CANDIDATE_DATA)  # has website_url
        no_site = {**CANDIDATE_DATA, "candidate_id": "cand-002", "website_url": None}
        doc_without = make_sync_doc(no_site)
        sync_db.collection.return_value.stream.return_value = [doc_with, doc_without]

        candidates = await firebase_service.aget_candidates_with_website()

        assert len(candidates) == 1
        assert candidates[0].website_url == "https://marie-dupont.fr"

    @pytest.mark.asyncio
    async def test_excludes_candidates_with_none_website(self, sync_db):
        data = {**CANDIDATE_DATA, "website_url": None}
        sync_db.collection.return_value.stream.return_value = [make_sync_doc(data)]

        candidates = await firebase_service.aget_candidates_with_website()

        assert candidates == []

    @pytest.mark.asyncio
    async def test_excludes_candidates_with_empty_string_website(self, sync_db):
        data = {**CANDIDATE_DATA, "website_url": ""}
        sync_db.collection.return_value.stream.return_value = [make_sync_doc(data)]

        candidates = await firebase_service.aget_candidates_with_website()

        assert candidates == []

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_empty_collection(self, sync_db):
        sync_db.collection.return_value.stream.return_value = []

        candidates = await firebase_service.aget_candidates_with_website()

        assert candidates == []


# ===========================================================================
# aget_candidates_by_election_type
# ===========================================================================


class TestAgetCandidatesByElectionType:
    @pytest.mark.asyncio
    async def test_returns_candidates_for_election_type(self, async_db):
        doc = make_sync_doc(CANDIDATE_DATA)
        async_db.collection.return_value.where.return_value.stream.return_value = (
            MockAsyncStream([doc])
        )

        candidates = await firebase_service.aget_candidates_by_election_type(
            "municipales-2026"
        )

        assert len(candidates) == 1
        assert candidates[0].election_type_id == "municipales-2026"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_match(self, async_db):
        async_db.collection.return_value.where.return_value.stream.return_value = (
            MockAsyncStream([])
        )

        candidates = await firebase_service.aget_candidates_by_election_type("unknown")

        assert candidates == []

    @pytest.mark.asyncio
    async def test_filters_by_correct_field_and_value(self, async_db):
        async_db.collection.return_value.where.return_value.stream.return_value = (
            MockAsyncStream([])
        )

        await firebase_service.aget_candidates_by_election_type("municipales-2026")

        async_db.collection.return_value.where.assert_called_once_with(
            "election_type_id", "==", "municipales-2026"
        )

    @pytest.mark.asyncio
    async def test_queries_candidates_collection(self, async_db):
        async_db.collection.return_value.where.return_value.stream.return_value = (
            MockAsyncStream([])
        )

        await firebase_service.aget_candidates_by_election_type("municipales-2026")

        async_db.collection.assert_called_with("candidates")

    @pytest.mark.asyncio
    async def test_returns_multiple_candidates(self, async_db):
        cand2 = {
            **CANDIDATE_DATA,
            "candidate_id": "cand-002",
            "first_name": "Pierre",
            "last_name": "Martin",
        }
        docs = [make_sync_doc(CANDIDATE_DATA), make_sync_doc(cand2)]
        async_db.collection.return_value.where.return_value.stream.return_value = (
            MockAsyncStream(docs)
        )

        candidates = await firebase_service.aget_candidates_by_election_type(
            "municipales-2026"
        )

        assert len(candidates) == 2
        assert {c.candidate_id for c in candidates} == {"cand-001", "cand-002"}
