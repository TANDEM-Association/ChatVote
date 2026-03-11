"""Tests for the unified chunking module (src/services/chunking.py).

Replaces test_manifesto_indexer.py and test_candidate_indexer.py which tested
the legacy duplicated chunking code.
"""

import pytest
from unittest.mock import AsyncMock, call

from langchain_core.documents import Document

from src.services.chunking import (
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MIN_CHUNK_LENGTH,
    create_documents_from_text,
    create_documents_from_pages,
    batch_index,
)
from src.models.chunk_metadata import Fiabilite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _long_text(length: int = 2500) -> str:
    """Generate a text longer than CHUNK_SIZE so splitting actually happens."""
    # Use sentences to give the splitter natural break points.
    sentence = "The quick brown fox jumps over the lazy dog. "
    repetitions = (length // len(sentence)) + 1
    return (sentence * repetitions)[:length]


# =========================================================================
# create_documents_from_text
# =========================================================================


class TestCreateDocumentsFromText:
    """Tests for the flat-text entry point."""

    def test_basic_splitting_produces_multiple_chunks(self):
        text = _long_text(2500)
        docs = create_documents_from_text(
            text,
            namespace="party_123",
            source_document="election_manifesto",
        )
        assert len(docs) > 1, "Text of 2500 chars should produce >1 chunk"

    def test_all_chunks_have_page_zero(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="election_manifesto",
        )
        for doc in docs:
            assert doc.metadata["page"] == 0

    def test_chunk_index_sequential(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="election_manifesto",
        )
        indices = [doc.metadata["chunk_index"] for doc in docs]
        assert indices == list(range(len(docs)))

    def test_total_chunks_backfilled(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="election_manifesto",
        )
        for doc in docs:
            assert doc.metadata["total_chunks"] == len(docs)

    def test_metadata_propagation(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="lfi",
            source_document="election_manifesto",
            party_ids=["lfi"],
            party_name="La France Insoumise",
            url="https://example.com/manifesto.pdf",
            document_name="Programme 2027",
        )
        meta = docs[0].metadata
        assert meta["namespace"] == "lfi"
        assert meta["source_document"] == "election_manifesto"
        assert meta["party_ids"] == ["lfi"]
        assert meta["party_name"] == "La France Insoumise"
        assert meta["url"] == "https://example.com/manifesto.pdf"
        assert meta["document_name"] == "Programme 2027"

    def test_candidate_metadata(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="cand_42",
            source_document="candidate_website",
            candidate_ids=["cand_42"],
            candidate_name="Jean Dupont",
            municipality_code="75056",
            municipality_name="Paris",
            municipality_postal_code="75001",
        )
        meta = docs[0].metadata
        assert meta["candidate_ids"] == ["cand_42"]
        assert meta["candidate_name"] == "Jean Dupont"
        assert meta["municipality_code"] == "75056"
        assert meta["municipality_name"] == "Paris"
        assert meta["municipality_postal_code"] == "75001"

    def test_min_chunk_length_filtering(self):
        # Short text that is below MIN_CHUNK_LENGTH after stripping
        short = "Hi."  # 3 chars < 30
        docs = create_documents_from_text(
            short,
            namespace="ns",
            source_document="election_manifesto",
        )
        assert len(docs) == 0, "Chunks shorter than MIN_CHUNK_LENGTH should be filtered"

    def test_empty_text_returns_empty(self):
        docs = create_documents_from_text(
            "",
            namespace="ns",
            source_document="election_manifesto",
        )
        assert docs == []

    def test_none_like_empty_text(self):
        """Empty string is falsy, so create_documents_from_text passes [] to pages."""
        docs = create_documents_from_text(
            "",
            namespace="ns",
            source_document="election_manifesto",
        )
        assert docs == []

    def test_text_exactly_at_chunk_size(self):
        """Text exactly at CHUNK_SIZE should produce one chunk (if above MIN_CHUNK_LENGTH)."""
        text = "A" * CHUNK_SIZE
        docs = create_documents_from_text(
            text,
            namespace="ns",
            source_document="election_manifesto",
        )
        assert len(docs) == 1

    def test_text_shorter_than_chunk_size_but_above_min(self):
        text = "A" * 100  # Well above MIN_CHUNK_LENGTH but below CHUNK_SIZE
        docs = create_documents_from_text(
            text,
            namespace="ns",
            source_document="election_manifesto",
        )
        assert len(docs) == 1
        assert docs[0].page_content == text

    def test_extra_metadata_kwargs_passed_through(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="candidate_website",
            election_type_id="municipales_2026",
            is_tete_de_liste=True,
            nuance_politique="DVG",
        )
        meta = docs[0].metadata
        assert meta["election_type_id"] == "municipales_2026"
        assert meta["is_tete_de_liste"] is True
        assert meta["nuance_politique"] == "DVG"


# =========================================================================
# create_documents_from_pages
# =========================================================================


class TestCreateDocumentsFromPages:
    """Tests for the page-aware entry point (PDF manifesto use case)."""

    def test_page_numbers_preserved(self):
        pages = [
            (1, _long_text(500)),
            (2, _long_text(500)),
            (3, _long_text(500)),
        ]
        docs = create_documents_from_pages(
            pages,
            namespace="rn",
            source_document="election_manifesto",
        )
        page_nums = {doc.metadata["page"] for doc in docs}
        # Each page has 500 chars < CHUNK_SIZE so one chunk per page
        assert page_nums == {1, 2, 3}

    def test_multiple_chunks_per_page(self):
        """A long page should be split into multiple chunks, all with the same page number."""
        pages = [(5, _long_text(3000))]
        docs = create_documents_from_pages(
            pages,
            namespace="ns",
            source_document="election_manifesto",
        )
        assert len(docs) > 1
        for doc in docs:
            assert doc.metadata["page"] == 5

    def test_total_chunks_spans_all_pages(self):
        pages = [
            (1, _long_text(1500)),
            (2, _long_text(1500)),
        ]
        docs = create_documents_from_pages(
            pages,
            namespace="ns",
            source_document="election_manifesto",
        )
        total = len(docs)
        assert total > 2, "Two pages of 1500 chars each should produce >2 chunks total"
        for doc in docs:
            assert doc.metadata["total_chunks"] == total

    def test_chunk_index_continuous_across_pages(self):
        pages = [
            (1, _long_text(1500)),
            (2, _long_text(1500)),
        ]
        docs = create_documents_from_pages(
            pages,
            namespace="ns",
            source_document="election_manifesto",
        )
        indices = [doc.metadata["chunk_index"] for doc in docs]
        assert indices == list(range(len(docs)))

    def test_empty_pages_list(self):
        docs = create_documents_from_pages(
            [],
            namespace="ns",
            source_document="election_manifesto",
        )
        assert docs == []

    def test_page_with_only_whitespace_filtered(self):
        pages = [(1, "   \n\n   ")]
        docs = create_documents_from_pages(
            pages,
            namespace="ns",
            source_document="election_manifesto",
        )
        assert docs == []

    def test_mixed_short_and_long_pages(self):
        pages = [
            (1, "Too short"),            # < MIN_CHUNK_LENGTH, should be filtered
            (2, _long_text(800)),        # Should produce 1 chunk
            (3, _long_text(2500)),       # Should produce >1 chunk
        ]
        docs = create_documents_from_pages(
            pages,
            namespace="ns",
            source_document="election_manifesto",
        )
        page_nums = [doc.metadata["page"] for doc in docs]
        assert 1 not in page_nums, "Page 1 content is too short, should be filtered"
        assert 2 in page_nums
        assert 3 in page_nums

    def test_default_arrays_are_empty(self):
        """party_ids and candidate_ids default to empty lists."""
        docs = create_documents_from_pages(
            [(1, _long_text(500))],
            namespace="ns",
            source_document="election_manifesto",
        )
        meta = docs[0].metadata
        assert meta["party_ids"] == []
        assert meta["candidate_ids"] == []


# =========================================================================
# ChunkMetadata integration
# =========================================================================


class TestChunkMetadataIntegration:
    """Verify ChunkMetadata auto-assignment and payload shape."""

    def test_fiabilite_auto_government(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="justified_voting_behavior",
        )
        assert docs[0].metadata["fiabilite"] == int(Fiabilite.GOVERNMENT)

    def test_fiabilite_auto_official(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="election_manifesto",
        )
        assert docs[0].metadata["fiabilite"] == int(Fiabilite.OFFICIAL)

    def test_fiabilite_auto_press_for_candidate_website(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="candidate_website",
        )
        assert docs[0].metadata["fiabilite"] == int(Fiabilite.PRESS)

    def test_fiabilite_auto_official_for_candidate_about(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="candidate_website_about",
        )
        assert docs[0].metadata["fiabilite"] == int(Fiabilite.OFFICIAL)

    def test_fiabilite_fallback_unknown_source(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="some_unknown_source",
        )
        assert docs[0].metadata["fiabilite"] == int(Fiabilite.PRESS)

    def test_party_ids_array_in_payload(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="election_manifesto",
            party_ids=["lfi", "eelv"],
        )
        assert docs[0].metadata["party_ids"] == ["lfi", "eelv"]

    def test_candidate_ids_array_in_payload(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="candidate_website",
            candidate_ids=["c1", "c2", "c3"],
        )
        assert docs[0].metadata["candidate_ids"] == ["c1", "c2", "c3"]

    def test_namespace_in_payload(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="my_namespace_id",
            source_document="election_manifesto",
        )
        assert docs[0].metadata["namespace"] == "my_namespace_id"

    def test_none_fields_excluded_from_payload(self):
        """ChunkMetadata.to_qdrant_payload() excludes None values."""
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="election_manifesto",
            # Deliberately not setting party_name, url, etc.
        )
        meta = docs[0].metadata
        assert "party_name" not in meta
        assert "candidate_name" not in meta
        assert "municipality_code" not in meta

    def test_page_title_and_type_in_payload(self):
        docs = create_documents_from_text(
            _long_text(),
            namespace="ns",
            source_document="candidate_website",
            page_title="Nos engagements",
            page_type="programme",
        )
        meta = docs[0].metadata
        assert meta["page_title"] == "Nos engagements"
        assert meta["page_type"] == "programme"


# =========================================================================
# batch_index
# =========================================================================


class TestBatchIndex:
    """Tests for the async batch indexing function."""

    @pytest.fixture
    def mock_vector_store(self):
        store = AsyncMock()
        store.aadd_documents = AsyncMock(return_value=None)
        return store

    @pytest.fixture
    def sample_docs(self):
        return [
            Document(page_content=f"chunk {i}", metadata={"chunk_index": i})
            for i in range(7)
        ]

    @pytest.mark.asyncio
    async def test_indexes_all_documents(self, mock_vector_store, sample_docs):
        count = await batch_index(mock_vector_store, sample_docs, batch_size=3)
        assert count == 7

    @pytest.mark.asyncio
    async def test_batching_splits_correctly(self, mock_vector_store, sample_docs):
        await batch_index(mock_vector_store, sample_docs, batch_size=3)
        calls = mock_vector_store.aadd_documents.call_args_list
        # 7 docs with batch_size=3 -> batches of 3, 3, 1
        assert len(calls) == 3
        assert len(calls[0].args[0]) == 3
        assert len(calls[1].args[0]) == 3
        assert len(calls[2].args[0]) == 1

    @pytest.mark.asyncio
    async def test_single_batch_when_below_batch_size(self, mock_vector_store, sample_docs):
        await batch_index(mock_vector_store, sample_docs, batch_size=50)
        assert mock_vector_store.aadd_documents.call_count == 1
        assert len(mock_vector_store.aadd_documents.call_args.args[0]) == 7

    @pytest.mark.asyncio
    async def test_empty_documents_returns_zero(self, mock_vector_store):
        count = await batch_index(mock_vector_store, [])
        assert count == 0
        mock_vector_store.aadd_documents.assert_not_called()

    @pytest.mark.asyncio
    async def test_exact_batch_size_multiple(self, mock_vector_store):
        docs = [Document(page_content=f"c{i}", metadata={}) for i in range(6)]
        await batch_index(mock_vector_store, docs, batch_size=3)
        assert mock_vector_store.aadd_documents.call_count == 2

    @pytest.mark.asyncio
    async def test_batch_size_one(self, mock_vector_store, sample_docs):
        await batch_index(mock_vector_store, sample_docs, batch_size=1)
        assert mock_vector_store.aadd_documents.call_count == 7

    @pytest.mark.asyncio
    async def test_returns_document_count(self, mock_vector_store):
        docs = [Document(page_content="x", metadata={}) for _ in range(13)]
        count = await batch_index(mock_vector_store, docs, batch_size=5)
        assert count == 13


# =========================================================================
# Constants sanity checks
# =========================================================================


class TestConstants:
    """Verify the chunking constants match expected values."""

    def test_chunk_size(self):
        assert CHUNK_SIZE == 1000

    def test_chunk_overlap(self):
        assert CHUNK_OVERLAP == 200

    def test_min_chunk_length(self):
        assert MIN_CHUNK_LENGTH == 30

    def test_overlap_less_than_size(self):
        assert CHUNK_OVERLAP < CHUNK_SIZE
