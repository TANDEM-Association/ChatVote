"""
OCR pipeline tests using self-contained image-based PDF fixtures.

Tests the full OCR fallback path:
  pypdf fails (0 chars) → Gemini OCR → extracted text

Fixtures are generated programmatically (no external dependencies):
    poetry run python tests/fixtures/generate_pdf_fixtures.py

Tests:
1. Deterministic: pypdf returns nothing for image PDFs, text for text PDFs
2. OCR quality (requires GOOGLE_API_KEY): Gemini extracts correct content
3. Pipeline integration: extract_or_ocr correctly falls back to OCR

Usage:
    # Deterministic tests only (no API key needed)
    poetry run pytest tests/eval/test_ocr_fixtures.py -k "not gemini" -s

    # Full suite with OCR
    GOOGLE_API_KEY=... poetry run pytest tests/eval/test_ocr_fixtures.py -s
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.services.pdf_extract import (
    extract_pages,
    extract_text,
    extract_or_ocr,
    extract_or_ocr_pages,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"

IMAGE_MANIFESTO = FIXTURES_DIR / "image_only_manifesto.pdf"
IMAGE_POSTER = FIXTURES_DIR / "image_only_poster.pdf"
MIXED_PDF = FIXTURES_DIR / "mixed_pdf.pdf"
TEXT_MANIFESTO = FIXTURES_DIR / "text_manifesto.pdf"
SCANNED_HANDWRITTEN = FIXTURES_DIR / "scanned_handwritten.pdf"

# Known content rendered into the image PDFs (ground truth for OCR checks)
MANIFESTO_KEYWORDS = [
    "Marie-Claire Dupont",
    "logements sociaux",
    "pistes cyclables",
    "cantine bio",
    "10 000 arbres",
]

POSTER_KEYWORDS = [
    "Marie-Claire DUPONT",
    "ÉLECTIONS MUNICIPALES",
    "Transports gratuits",
    "ensemble-notre-ville",
]

HANDWRITTEN_KEYWORDS = [
    "Jean-Pierre Martin",
    "impôts locaux",
    "centre médical",
    "emplois locaux",
]


def _skip_if_no_fixtures():
    if not IMAGE_MANIFESTO.exists():
        pytest.skip(
            "PDF fixtures not generated. Run: "
            "poetry run python tests/fixtures/generate_pdf_fixtures.py"
        )


def _skip_if_no_google_key():
    if not os.environ.get("GOOGLE_API_KEY"):
        pytest.skip("GOOGLE_API_KEY required for Gemini OCR tests")


# ---------------------------------------------------------------------------
# Deterministic tests (no API key needed)
# ---------------------------------------------------------------------------

class TestPypdfExtraction:
    """Verify pypdf behavior on different PDF types (no API calls)."""

    def setup_method(self):
        _skip_if_no_fixtures()

    def test_image_manifesto_has_no_text(self):
        """pypdf should extract zero text from image-only manifesto."""
        text = extract_text(IMAGE_MANIFESTO.read_bytes())
        assert len(text.strip()) == 0, f"Expected 0 chars, got {len(text.strip())}"

    def test_image_poster_has_no_text(self):
        """pypdf should extract zero text from image-only poster."""
        text = extract_text(IMAGE_POSTER.read_bytes())
        assert len(text.strip()) == 0

    def test_scanned_handwritten_has_no_text(self):
        """pypdf should extract zero text from simulated handwritten scan."""
        text = extract_text(SCANNED_HANDWRITTEN.read_bytes())
        assert len(text.strip()) == 0

    def test_text_manifesto_has_text(self):
        """pypdf should extract text from a normal text-based PDF."""
        text = extract_text(TEXT_MANIFESTO.read_bytes())
        assert len(text.strip()) > 200, f"Expected >200 chars, got {len(text.strip())}"
        assert "logement" in text.lower() or "LOGEMENT" in text

    def test_text_manifesto_pages(self):
        """extract_pages should return page-number-aware results."""
        pages = extract_pages(TEXT_MANIFESTO.read_bytes())
        assert len(pages) >= 1
        page_num, page_text = pages[0]
        assert page_num == 1
        assert len(page_text.strip()) > 100

    def test_image_pdf_extract_pages_returns_empty(self):
        """extract_pages on image PDF should return empty list."""
        pages = extract_pages(IMAGE_MANIFESTO.read_bytes())
        assert pages == []

    def test_mixed_pdf_extraction(self):
        """Mixed PDF may or may not have some pypdf text depending on generation."""
        data = MIXED_PDF.read_bytes()
        text = extract_text(data)
        # mixed_pdf has image pages — pypdf should get very little
        # (page 2 might have text if reportlab was available, otherwise all images)
        assert isinstance(text, str)


# ---------------------------------------------------------------------------
# OCR fallback path tests (requires GOOGLE_API_KEY)
# ---------------------------------------------------------------------------

class TestOCRFallback:
    """Test that extract_or_ocr correctly falls back to Gemini OCR."""

    def setup_method(self):
        _skip_if_no_fixtures()
        _skip_if_no_google_key()

    def test_text_pdf_skips_ocr(self):
        """extract_or_ocr should NOT call OCR for text-based PDFs."""
        text = asyncio.get_event_loop().run_until_complete(
            extract_or_ocr(TEXT_MANIFESTO.read_bytes(), "text_manifesto.pdf")
        )
        assert len(text.strip()) > 200
        # Should contain real content
        assert "Dupont" in text or "PROGRAMME" in text

    def test_image_manifesto_triggers_ocr(self):
        """extract_or_ocr should fall back to OCR for image-only manifesto."""
        text = asyncio.get_event_loop().run_until_complete(
            extract_or_ocr(IMAGE_MANIFESTO.read_bytes(), "image_only_manifesto.pdf")
        )
        assert len(text.strip()) > 100, "OCR should extract text from image PDF"

    def test_image_poster_triggers_ocr(self):
        """extract_or_ocr should fall back to OCR for image-only poster."""
        text = asyncio.get_event_loop().run_until_complete(
            extract_or_ocr(IMAGE_POSTER.read_bytes(), "image_only_poster.pdf")
        )
        assert len(text.strip()) > 50

    def test_scanned_handwritten_triggers_ocr(self):
        """extract_or_ocr should handle simulated handwritten scans."""
        text = asyncio.get_event_loop().run_until_complete(
            extract_or_ocr(SCANNED_HANDWRITTEN.read_bytes(), "scanned_handwritten.pdf")
        )
        assert len(text.strip()) > 50

    def test_extract_or_ocr_pages_fallback(self):
        """extract_or_ocr_pages should return [(1, text)] for image PDFs."""
        pages = asyncio.get_event_loop().run_until_complete(
            extract_or_ocr_pages(IMAGE_MANIFESTO.read_bytes(), "image_only_manifesto.pdf")
        )
        assert len(pages) >= 1
        page_num, text = pages[0]
        assert page_num == 1  # OCR returns all text as single page
        assert len(text.strip()) > 100


# ---------------------------------------------------------------------------
# OCR content quality tests (requires GOOGLE_API_KEY)
# ---------------------------------------------------------------------------

class TestOCRContentQuality:
    """Verify OCR extracts the correct content from known fixtures."""

    def setup_method(self):
        _skip_if_no_fixtures()
        _skip_if_no_google_key()

    def _ocr(self, pdf_path: Path) -> str:
        return asyncio.get_event_loop().run_until_complete(
            extract_or_ocr(pdf_path.read_bytes(), pdf_path.name)
        )

    def test_manifesto_keywords_extracted(self):
        """OCR should capture key political terms from the manifesto."""
        text = self._ocr(IMAGE_MANIFESTO)
        found = [kw for kw in MANIFESTO_KEYWORDS if kw.lower() in text.lower()]
        missing = [kw for kw in MANIFESTO_KEYWORDS if kw.lower() not in text.lower()]
        assert len(found) >= 3, (
            f"OCR missed too many keywords. Found: {found}, Missing: {missing}"
        )

    def test_poster_keywords_extracted(self):
        """OCR should capture candidate name and key proposals from poster."""
        text = self._ocr(IMAGE_POSTER)
        found = [kw for kw in POSTER_KEYWORDS if kw.lower() in text.lower()]
        missing = [kw for kw in POSTER_KEYWORDS if kw.lower() not in text.lower()]
        assert len(found) >= 2, (
            f"OCR missed too many poster keywords. Found: {found}, Missing: {missing}"
        )

    def test_handwritten_keywords_extracted(self):
        """OCR should handle handwriting-style text."""
        text = self._ocr(SCANNED_HANDWRITTEN)
        found = [kw for kw in HANDWRITTEN_KEYWORDS if kw.lower() in text.lower()]
        missing = [kw for kw in HANDWRITTEN_KEYWORDS if kw.lower() not in text.lower()]
        assert len(found) >= 2, (
            f"OCR missed handwritten keywords. Found: {found}, Missing: {missing}"
        )

    def test_manifesto_ocr_has_numbers(self):
        """OCR should preserve numerical data (500, 10 000, etc.)."""
        text = self._ocr(IMAGE_MANIFESTO)
        # Check at least some numbers are preserved
        has_500 = "500" in text
        has_10000 = "10 000" in text or "10000" in text or "10,000" in text
        has_40 = "40" in text
        numbers_found = sum([has_500, has_10000, has_40])
        assert numbers_found >= 2, f"OCR should preserve numbers. Text: {text[:500]}"


# ---------------------------------------------------------------------------
# Full pipeline integration (PDF → extract → chunk → metadata)
# ---------------------------------------------------------------------------

class TestOCRPipelineIntegration:
    """Test that image PDFs work through the full chunking pipeline."""

    def setup_method(self):
        _skip_if_no_fixtures()
        _skip_if_no_google_key()

    def test_image_pdf_through_chunking_pipeline(self):
        """An image-only PDF should produce valid chunks after OCR."""
        from src.services.chunking import create_documents_from_text

        # Extract via OCR
        text = asyncio.get_event_loop().run_until_complete(
            extract_or_ocr(IMAGE_MANIFESTO.read_bytes(), "image_only_manifesto.pdf")
        )
        assert len(text.strip()) > 100, "OCR must return text for pipeline test"

        # Chunk it
        docs = create_documents_from_text(
            text,
            namespace="test_party",
            source_document="election_manifesto",
            party_ids=["test_party"],
            party_name="Ensemble pour Notre Ville",
        )

        assert len(docs) >= 1, "Should produce at least 1 chunk"
        for doc in docs:
            assert len(doc.page_content.strip()) >= 30
            assert doc.metadata.get("namespace") == "test_party"
            assert doc.metadata.get("source_document") == "election_manifesto"

    def test_poster_pdf_through_theme_classification(self):
        """An image poster should get a theme after OCR + classification."""
        from src.services.theme_classifier import classify_theme

        text = asyncio.get_event_loop().run_until_complete(
            extract_or_ocr(IMAGE_POSTER.read_bytes(), "image_only_poster.pdf")
        )
        assert len(text.strip()) > 50

        result = classify_theme(text)
        # The poster mentions logement, transport, environnement, éducation
        # Keyword classifier should pick up at least one theme
        if result.theme is not None:
            assert result.method == "keyword"
            assert result.theme in [
                "logement", "transport", "environnement", "education",
                "institutions",
            ]
