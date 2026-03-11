"""Tests for the pipeline context shared data bus."""
import pytest

from src.services.data_pipeline.base import (
    put_context,
    get_context,
    clear_context,
)


@pytest.fixture(autouse=True)
def _clean_context():
    """Ensure each test starts with a clean context."""
    clear_context()
    yield
    clear_context()


def test_put_and_get():
    put_context("foo", {"a": 1})
    assert get_context("foo") == {"a": 1}


def test_get_missing_returns_none():
    assert get_context("nonexistent") is None


def test_overwrite():
    put_context("key", "v1")
    put_context("key", "v2")
    assert get_context("key") == "v2"


def test_clear():
    put_context("a", 1)
    put_context("b", 2)
    clear_context()
    assert get_context("a") is None
    assert get_context("b") is None


def test_scraper_writes_indexer_reads():
    """Simulate scraper→indexer data flow via context."""
    # Scraper puts scraped data
    scraped = {"cand_1": {"pages": 5}, "cand_2": {"pages": 3}}
    put_context("scraped_websites", scraped)

    # Indexer reads it without importing scraper
    result = get_context("scraped_websites")
    assert result is scraped
    assert result["cand_1"]["pages"] == 5
    assert len(result) == 2


def test_get_scraped_websites_accessor():
    """Test the scraper module's accessor uses context."""
    from src.services.data_pipeline.scraper import get_scraped_websites

    assert get_scraped_websites() is None

    data = {"c1": "site_data"}
    put_context("scraped_websites", data)
    assert get_scraped_websites() is data
