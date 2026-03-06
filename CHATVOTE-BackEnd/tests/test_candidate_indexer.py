import sys
from unittest.mock import MagicMock

# Mock Firebase and Qdrant modules before any src.services imports
for mod in [
    "src.firebase_service",
    "src.vector_store_helper",
]:
    if mod not in sys.modules:
        sys.modules[mod] = MagicMock()

import pytest
from src.models.candidate import Candidate


def _make_candidate():
    return Candidate(
        candidate_id="cand-paris-001",
        first_name="Jean",
        last_name="Dupont",
        municipality_code="75056",
        municipality_name="Paris",
        party_ids=["lr", "udi"],
        website_url="https://jeandupont.fr",
        election_type_id="municipales-2026",
    )


def _make_scraped_website():
    from src.services.candidate_website_scraper import ScrapedWebsite, ScrapedPage

    page = ScrapedPage(
        url="https://jeandupont.fr/about",
        title="About",
        content="Jean Dupont is a candidate for Paris. " * 30,
        page_type="about",
    )
    return ScrapedWebsite(
        candidate_id="cand-paris-001",
        website_url="https://jeandupont.fr",
        pages=[page],
    )


def test_candidate_docs_use_chunk_metadata():
    """Documents should use ChunkMetadata with array party_ids."""
    from src.services.candidate_indexer import create_documents_from_scraped_website

    candidate = _make_candidate()
    scraped = _make_scraped_website()
    docs = create_documents_from_scraped_website(candidate, scraped)

    assert len(docs) > 0
    meta = docs[0].metadata
    # party_ids must be a list (not comma-separated string)
    assert isinstance(meta["party_ids"], list)
    assert meta["party_ids"] == ["lr", "udi"]
    # candidate_ids should be present
    assert meta["candidate_ids"] == ["cand-paris-001"]
    # fiabilite should be OFFICIAL (2) for candidate_website_about
    assert meta["fiabilite"] == 2
    assert meta["namespace"] == "cand-paris-001"
    assert meta["municipality_code"] == "75056"


def test_candidate_docs_total_chunks():
    """All docs should have correct total_chunks."""
    from src.services.candidate_indexer import create_documents_from_scraped_website

    candidate = _make_candidate()
    scraped = _make_scraped_website()
    docs = create_documents_from_scraped_website(candidate, scraped)

    for doc in docs:
        assert doc.metadata["total_chunks"] == len(docs)


def test_candidate_docs_blog_page_type():
    """Blog page type should get PRESS fiabilite (3)."""
    from src.services.candidate_indexer import create_documents_from_scraped_website
    from src.services.candidate_website_scraper import ScrapedWebsite, ScrapedPage

    candidate = _make_candidate()
    page = ScrapedPage(
        url="https://jeandupont.fr/blog/post",
        title="Blog Post",
        content="Blog post about local politics. " * 30,
        page_type="blog",
    )
    scraped = ScrapedWebsite(
        candidate_id="cand-paris-001",
        website_url="https://jeandupont.fr",
        pages=[page],
    )
    docs = create_documents_from_scraped_website(candidate, scraped)
    assert docs[0].metadata["fiabilite"] == 3  # PRESS
