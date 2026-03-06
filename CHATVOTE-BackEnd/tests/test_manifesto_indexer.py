import sys
from unittest.mock import MagicMock

import pytest

# Mock Firebase and Qdrant modules before any src.services imports
for mod in [
    "src.firebase_service",
    "src.vector_store_helper",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

from src.models.party import Party  # noqa: E402


def _make_party():
    return Party(
        party_id="test-party",
        name="Test Party",
        long_name="Test Party Long",
        description="A test party",
        website_url="https://example.com",
        candidate="Test Candidate",
        election_manifesto_url="https://example.com/test.pdf",
    )


def test_extract_pages_returns_list_of_tuples():
    """extract_pages_from_pdf returns [(page_num, text), ...]."""
    from pypdf import PdfWriter
    import io

    # Create a simple 2-page PDF
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()

    from src.services.manifesto_indexer import extract_pages_from_pdf
    pages = extract_pages_from_pdf(pdf_bytes)
    # Blank pages have no text, so result may be empty
    assert isinstance(pages, list)


def test_create_documents_from_pages_preserves_page_number():
    """Each chunk gets the correct PDF page number, not chunk index."""
    from src.services.manifesto_indexer import create_documents_from_pages

    pages = [
        (1, "First page content about economy and budget policy. " * 25),
        (2, "Second page about environment and climate. " * 25),
    ]
    party = _make_party()
    docs = create_documents_from_pages(pages, party, "https://example.com/test.pdf")

    assert len(docs) > 0
    # First doc should come from page 1
    assert docs[0].metadata["page"] == 1
    # Check that some doc has page 2
    page_2_docs = [d for d in docs if d.metadata["page"] == 2]
    assert len(page_2_docs) > 0
    # All docs should have party_ids as a list
    assert docs[0].metadata["party_ids"] == ["test-party"]
    # Fiabilite should be OFFICIAL (2) for election_manifesto
    assert docs[0].metadata["fiabilite"] == 2
    # total_chunks should be set
    assert docs[0].metadata["total_chunks"] == len(docs)


def test_create_documents_uses_chunk_metadata():
    """Documents use ChunkMetadata for payload construction."""
    from src.services.manifesto_indexer import create_documents_from_pages

    pages = [(5, "Political content. " * 30)]
    party = _make_party()
    docs = create_documents_from_pages(pages, party, "https://example.com/test.pdf")

    meta = docs[0].metadata
    assert meta["namespace"] == "test-party"
    assert meta["source_document"] == "election_manifesto"
    assert meta["party_name"] == "Test Party"
    assert "document_name" in meta
    assert meta["page"] == 5  # Real PDF page, not chunk index


def test_legacy_extract_text_still_works():
    """extract_text_from_pdf backward compat wrapper still works."""
    from src.services.manifesto_indexer import extract_text_from_pdf
    from pypdf import PdfWriter
    import io

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)

    result = extract_text_from_pdf(buf.getvalue())
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_index_party_manifesto_classifies_themes(monkeypatch):
    """Theme classification is called during indexing and results stored in metadata."""
    from unittest.mock import AsyncMock, MagicMock
    from src.services import manifesto_indexer
    from src.services.chunk_classifier import ChunkThemeClassification

    # Mock PDF fetch
    monkeypatch.setattr(manifesto_indexer, "fetch_pdf_content", AsyncMock(return_value=b"fake"))
    # Mock page extraction
    monkeypatch.setattr(
        manifesto_indexer, "extract_pages_from_pdf",
        lambda _: [(1, "Economy content about budget policy and taxes. " * 30)],
    )
    # Mock vector store
    mock_vs = MagicMock()
    mock_vs.aadd_documents = AsyncMock()
    monkeypatch.setattr(manifesto_indexer, "get_qdrant_vector_store", lambda: mock_vs)
    # Mock delete
    monkeypatch.setattr(manifesto_indexer, "delete_party_documents", AsyncMock(return_value=1))
    # Mock theme classification
    mock_classify = AsyncMock(return_value=[
        ChunkThemeClassification(theme="economie", sub_theme="budget")
    ])
    monkeypatch.setattr(
        manifesto_indexer, "classify_chunks_themes", mock_classify
    )

    party = _make_party()
    count = await manifesto_indexer.index_party_manifesto(party)

    assert count > 0
    mock_classify.assert_called_once()
    # Check that the documents passed to vector store have theme in metadata
    added_docs = mock_vs.aadd_documents.call_args_list[0][0][0]
    assert added_docs[0].metadata.get("theme") == "economie"
