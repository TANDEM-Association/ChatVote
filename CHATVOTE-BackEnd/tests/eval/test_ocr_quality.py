"""
DeepEval test for OCR quality on election poster PDFs.

Strategy:
1. Pick PDFs where pypdf extracts good text (ground truth)
2. Convert those PDFs to image-only PDFs (via pdftoppm → img2pdf)
3. Run the image-only PDFs through Gemini OCR
4. Use DeepEval GEval to score how well OCR preserves content

Requires:
    - poppler (pdftoppm): brew install poppler
    - Pillow: poetry add --group dev Pillow
    - GOOGLE_API_KEY for Gemini OCR
    - DEEPEVAL_JUDGE=gemini (or ollama running)

Usage:
    DEEPEVAL_JUDGE=gemini poetry run pytest tests/eval/test_ocr_quality.py -s
"""

import asyncio
import io
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from src.services.document_upload import (
    extract_text_from_pdf_bytes,
    ocr_pdf_with_gemini,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PROJECTS_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
COWORK_OUTPUT = PROJECTS_ROOT / "Chatvote-cowork" / "scraper" / "output"

# Sample PDFs to test (known to have good pypdf text)
SAMPLE_PDFS = [
    "75_Paris/75056_Paris/panneau_2_RP.pdf",
    "94_Val-de-Marne/94079_Villiers-sur-Marne/panneau_2_POUR VOUS_ POUR VILLIERS_ LA GAUCHE_ LES ECOLOGISTES_ LES CI.pdf",
    "13_Bouches-du-Rhône/13055_Marseille/panneau_1_PRINTEMPS MARSEILLAIS.pdf",
    "69_Rhône/69123_Lyon/panneau_1_RL.pdf",
]


def _find_available_pdfs() -> list[Path]:
    """Return paths of sample PDFs that exist on disk."""
    available = []
    for rel in SAMPLE_PDFS:
        path = COWORK_OUTPUT / rel
        if path.exists():
            available.append(path)
    if not available:
        # Fallback: grab first 3 PDFs from any directory
        for pdf in COWORK_OUTPUT.rglob("*.pdf"):
            available.append(pdf)
            if len(available) >= 3:
                break
    return available


def _pdf_to_image_pdf(pdf_path: Path) -> bytes:
    """Convert a PDF to an image-only PDF using pdftoppm + PIL.

    This simulates a scanned document where pypdf cannot extract text.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Render PDF pages as PNG images using poppler
        result = subprocess.run(
            ["pdftoppm", "-png", "-r", "200", str(pdf_path), f"{tmpdir}/page"],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(f"pdftoppm failed: {result.stderr.decode()}")

        # Collect rendered page images
        page_images = sorted(Path(tmpdir).glob("page-*.png"))
        if not page_images:
            raise RuntimeError(f"No pages rendered from {pdf_path}")

        # Reassemble as image-only PDF using PIL
        from PIL import Image

        images = [Image.open(p).convert("RGB") for p in page_images]
        output = io.BytesIO()
        images[0].save(output, format="PDF", save_all=True, append_images=images[1:])
        return output.getvalue()


# ---------------------------------------------------------------------------
# DeepEval OCR accuracy metric
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ocr_accuracy_metric(judge_model):
    """GEval metric comparing OCR output against ground truth text."""
    return GEval(
        name="OCR Accuracy",
        criteria="""Compare the OCR output (actual_output) against the ground truth text
        (expected_output) extracted from the same PDF document. Evaluate:
        1. Content completeness: Does the OCR capture all key information (names, dates,
           policy proposals, list names)?
        2. Structural preservation: Are paragraphs, numbered lists, and headings
           maintained in roughly the same order?
        3. Accuracy: Are names, numbers, and political terms correctly transcribed
           (allow minor accent/encoding differences)?
        4. Readability: Is the OCR output readable and coherent as French text?

        Score 1.0 if OCR output faithfully reproduces all content.
        Score 0.0 if OCR output is unrelated or mostly garbage.
        Minor formatting differences and whitespace variations should not lower
        the score significantly.""",
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=0.7,
        model=judge_model,
    )


@pytest.fixture(scope="session")
def ocr_key_info_metric(judge_model):
    """GEval metric checking if OCR preserves politically critical information."""
    return GEval(
        name="OCR Key Info Preservation",
        criteria="""Check if the OCR output (actual_output) preserves the politically
        critical information from the ground truth (expected_output):
        1. Candidate/list leader names (tête de liste)
        2. Party or list name
        3. Election date and location
        4. Key policy proposals and commitments
        5. Contact info, URLs, or legal mentions

        These are essential for the RAG system to correctly answer voter questions.
        Score 1.0 if all key political information is preserved.
        Score 0.0 if critical names/proposals are missing or garbled.""",
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=0.8,
        model=judge_model,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestOCRQuality:
    """Test suite for OCR quality on election poster PDFs."""

    @pytest.fixture(autouse=True)
    def skip_if_unavailable(self):
        """Skip if required tools/data are missing."""
        # Check pdftoppm
        try:
            subprocess.run(["pdftoppm", "-v"], capture_output=True, timeout=5)
        except FileNotFoundError:
            pytest.skip("pdftoppm (poppler) not installed: brew install poppler")

        # Check Pillow
        try:
            import PIL  # noqa: F401
        except ImportError:
            pytest.skip("Pillow not installed: poetry add --group dev Pillow")

        # Check GOOGLE_API_KEY for OCR
        if not os.environ.get("GOOGLE_API_KEY"):
            pytest.skip("GOOGLE_API_KEY required for Gemini OCR")

        # Check sample PDFs exist
        if not _find_available_pdfs():
            pytest.skip(
                f"No sample PDFs found. Expected at {COWORK_OUTPUT}. "
                "Run the scraper first."
            )

    def _run_ocr_test(self, pdf_path: Path) -> tuple[str, str]:
        """Run the OCR pipeline on a single PDF.

        Returns (ground_truth, ocr_output).
        """
        data = pdf_path.read_bytes()

        # Step 1: Extract ground truth via pypdf
        ground_truth = extract_text_from_pdf_bytes(data)
        if len(ground_truth.strip()) < 200:
            pytest.skip(f"PDF {pdf_path.name} has too little pypdf text for comparison")

        # Step 2: Convert to image-only PDF
        image_pdf_bytes = _pdf_to_image_pdf(pdf_path)

        # Verify pypdf can NOT extract text from image PDF (proving it's image-only)
        image_text = extract_text_from_pdf_bytes(image_pdf_bytes)
        assert len(image_text.strip()) < 100, (
            f"Image PDF still has extractable text ({len(image_text)} chars). "
            "Conversion to image-only failed."
        )

        # Step 3: Run Gemini OCR on the image-only PDF
        ocr_text = asyncio.get_event_loop().run_until_complete(
            ocr_pdf_with_gemini(image_pdf_bytes, pdf_path.name)
        )

        return ground_truth, ocr_text

    def test_ocr_accuracy(self, ocr_accuracy_metric):
        """OCR should faithfully reproduce document content."""
        pdfs = _find_available_pdfs()
        pdf_path = pdfs[0]

        ground_truth, ocr_output = self._run_ocr_test(pdf_path)

        test_case = LLMTestCase(
            input=f"OCR quality test for: {pdf_path.name}",
            actual_output=ocr_output[:3000],  # Limit for LLM judge context
            expected_output=ground_truth[:3000],
        )

        assert_test(test_case, [ocr_accuracy_metric])

    def test_ocr_key_info_preservation(self, ocr_key_info_metric):
        """OCR should preserve politically critical information."""
        pdfs = _find_available_pdfs()
        pdf_path = pdfs[0]

        ground_truth, ocr_output = self._run_ocr_test(pdf_path)

        test_case = LLMTestCase(
            input=f"Key info preservation test for: {pdf_path.name}",
            actual_output=ocr_output[:3000],
            expected_output=ground_truth[:3000],
        )

        assert_test(test_case, [ocr_key_info_metric])

    @pytest.mark.parametrize("pdf_index", [0, 1, 2])
    def test_ocr_across_samples(self, ocr_accuracy_metric, pdf_index):
        """OCR quality should be consistent across different PDFs."""
        pdfs = _find_available_pdfs()
        if pdf_index >= len(pdfs):
            pytest.skip(f"Only {len(pdfs)} sample PDFs available")

        pdf_path = pdfs[pdf_index]
        ground_truth, ocr_output = self._run_ocr_test(pdf_path)

        test_case = LLMTestCase(
            input=f"OCR consistency test for: {pdf_path.name}",
            actual_output=ocr_output[:3000],
            expected_output=ground_truth[:3000],
        )

        assert_test(test_case, [ocr_accuracy_metric])
