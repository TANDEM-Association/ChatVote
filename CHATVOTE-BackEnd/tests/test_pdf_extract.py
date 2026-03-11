"""Tests for src.services.pdf_extract."""

import io
import pytest
from unittest.mock import AsyncMock, patch

from pypdf import PdfWriter

from src.services.pdf_extract import (
    extract_pages,
    extract_text,
    extract_text_from_txt_bytes,
    extract_file,
    extract_or_ocr,
    extract_or_ocr_pages,
    MIN_TEXT_FOR_OCR_FALLBACK,
)

FIXTURES = "tests/fixtures"


# ── helpers ──────────────────────────────────────────────────────────────────


def _make_pdf(*page_texts: str) -> bytes:
    """Build a minimal in-memory PDF with the given page texts."""
    writer = PdfWriter()
    for text in page_texts:
        writer.add_blank_page(width=72, height=72)
        page = writer.pages[-1]
        # Inject text via a simple content stream
        from pypdf.generic import (
            ArrayObject,
            DecodedStreamObject,
            DictionaryObject,
            NameObject,
            NumberObject,
        )

        font_dict = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        resources = DictionaryObject(
            {
                NameObject("/Font"): DictionaryObject(
                    {NameObject("/F1"): font_dict}
                )
            }
        )
        page[NameObject("/Resources")] = resources

        stream = DecodedStreamObject()
        # Escape parentheses in the text for the PDF content stream
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 10 50 Td ({escaped}) Tj ET".encode())
        page[NameObject("/Contents")] = stream
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _blank_pdf(num_pages: int = 1) -> bytes:
    """Build a PDF whose pages have no text at all."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=72, height=72)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


# ── extract_pages ────────────────────────────────────────────────────────────


class TestExtractPages:
    def test_returns_page_tuples(self):
        pdf = _make_pdf("Hello page one", "Hello page two")
        pages = extract_pages(pdf)
        assert len(pages) == 2
        assert pages[0][0] == 1
        assert pages[1][0] == 2
        assert "Hello page one" in pages[0][1]
        assert "Hello page two" in pages[1][1]

    def test_skips_blank_pages(self):
        pdf = _blank_pdf(3)
        pages = extract_pages(pdf)
        assert pages == []

    def test_handles_corrupt_bytes(self):
        pages = extract_pages(b"this is not a pdf at all")
        assert pages == []

    def test_real_text_manifesto(self):
        with open(f"{FIXTURES}/text_manifesto.pdf", "rb") as f:
            pdf_bytes = f.read()
        pages = extract_pages(pdf_bytes)
        assert len(pages) > 0
        assert all(isinstance(p, tuple) and len(p) == 2 for p in pages)
        assert all(isinstance(num, int) and isinstance(txt, str) for num, txt in pages)

    def test_image_only_pdf_returns_empty_or_minimal(self):
        with open(f"{FIXTURES}/image_only_manifesto.pdf", "rb") as f:
            pdf_bytes = f.read()
        pages = extract_pages(pdf_bytes)
        total_chars = sum(len(t) for _, t in pages)
        # Image-only PDFs should yield very little text from pypdf
        assert total_chars < MIN_TEXT_FOR_OCR_FALLBACK


# ── extract_text ─────────────────────────────────────────────────────────────


class TestExtractText:
    def test_joins_pages_with_double_newlines(self):
        pdf = _make_pdf("Page A", "Page B")
        text = extract_text(pdf)
        assert "\n\n" in text
        assert "Page A" in text
        assert "Page B" in text

    def test_empty_for_blank_pdf(self):
        pdf = _blank_pdf()
        text = extract_text(pdf)
        assert text == ""

    def test_empty_for_corrupt_bytes(self):
        text = extract_text(b"\x00\x01\x02")
        assert text == ""


# ── extract_text_from_txt_bytes ──────────────────────────────────────────────


class TestExtractTextFromTxtBytes:
    def test_utf8(self):
        data = "Bonjour le monde".encode("utf-8")
        assert extract_text_from_txt_bytes(data) == "Bonjour le monde"

    def test_latin1_fallback(self):
        # \xe9 is 'e-acute' in latin-1 but invalid as a standalone in utf-8
        data = b"caf\xe9"
        result = extract_text_from_txt_bytes(data)
        assert result == "caf\xe9"

    def test_raises_on_garbage(self):
        # latin-1 accepts all byte values, so the raise path is only hit
        # if both decodings somehow fail. We test it by wrapping the function
        # with a patched decode loop that always raises.
        original_fn = extract_text_from_txt_bytes.__wrapped__ if hasattr(extract_text_from_txt_bytes, "__wrapped__") else None

        # Directly test the raise path: create a subclass whose decode always fails
        class BadBytes(bytes):
            def decode(self, encoding="utf-8", errors="strict"):
                raise UnicodeDecodeError(encoding, b"", 0, 1, "forced failure")

        # Patch the function to receive our BadBytes
        bad = BadBytes(b"\xff\xfe")
        # The function iterates encodings and calls data.decode(encoding).
        # BadBytes.decode always raises, so it should hit the ValueError.
        with pytest.raises(ValueError, match="Could not decode"):
            extract_text_from_txt_bytes(bad)


# ── extract_file ─────────────────────────────────────────────────────────────


class TestExtractFile:
    @pytest.mark.asyncio
    async def test_dispatches_pdf(self):
        # Use enough text to stay above OCR threshold
        long_text = "extracted content " * 20
        pdf = _make_pdf(long_text)
        with patch("src.services.pdf_extract.ocr_with_gemini", new_callable=AsyncMock) as mock_ocr:
            result = await extract_file("test.pdf", pdf)
        assert "extracted content" in result
        mock_ocr.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatches_txt(self):
        data = b"plain text content"
        result = await extract_file("notes.txt", data)
        assert result == "plain text content"

    @pytest.mark.asyncio
    async def test_raises_on_unsupported(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            await extract_file("image.png", b"data")

    @pytest.mark.asyncio
    async def test_case_insensitive_extension(self):
        data = b"uppercase extension"
        result = await extract_file("NOTES.TXT", data)
        assert result == "uppercase extension"


# ── extract_or_ocr ───────────────────────────────────────────────────────────


class TestExtractOrOcr:
    @pytest.mark.asyncio
    async def test_returns_pypdf_text_when_above_threshold(self):
        long_text = "A" * (MIN_TEXT_FOR_OCR_FALLBACK + 100)
        pdf = _make_pdf(long_text)
        with patch("src.services.pdf_extract.ocr_with_gemini", new_callable=AsyncMock) as mock_ocr:
            result = await extract_or_ocr(pdf)
        mock_ocr.assert_not_called()
        assert "A" * 50 in result

    @pytest.mark.asyncio
    async def test_falls_back_to_ocr_when_below_threshold(self):
        pdf = _blank_pdf()
        with patch("src.services.pdf_extract.ocr_with_gemini", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "OCR extracted text from scanned PDF"
            result = await extract_or_ocr(pdf, filename="scan.pdf")
        mock_ocr.assert_called_once_with(pdf, "scan.pdf")
        assert result == "OCR extracted text from scanned PDF"

    @pytest.mark.asyncio
    async def test_custom_min_text_length(self):
        pdf = _make_pdf("short")
        with patch("src.services.pdf_extract.ocr_with_gemini", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "ocr result"
            result = await extract_or_ocr(pdf, min_text_length=99999)
        mock_ocr.assert_called_once()
        assert result == "ocr result"

    @pytest.mark.asyncio
    async def test_real_image_only_pdf_triggers_ocr(self):
        with open(f"{FIXTURES}/image_only_manifesto.pdf", "rb") as f:
            pdf_bytes = f.read()
        with patch("src.services.pdf_extract.ocr_with_gemini", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "OCR text from image PDF"
            result = await extract_or_ocr(pdf_bytes)
        mock_ocr.assert_called_once()
        assert result == "OCR text from image PDF"


# ── extract_or_ocr_pages ────────────────────────────────────────────────────


class TestExtractOrOcrPages:
    @pytest.mark.asyncio
    async def test_returns_real_pages_when_above_threshold(self):
        long_text = "B" * (MIN_TEXT_FOR_OCR_FALLBACK + 50)
        pdf = _make_pdf(long_text, "page two text")
        with patch("src.services.pdf_extract.ocr_with_gemini", new_callable=AsyncMock) as mock_ocr:
            pages = await extract_or_ocr_pages(pdf)
        mock_ocr.assert_not_called()
        assert len(pages) >= 1
        assert all(isinstance(p, tuple) for p in pages)

    @pytest.mark.asyncio
    async def test_falls_back_to_ocr_single_page(self):
        pdf = _blank_pdf()
        with patch("src.services.pdf_extract.ocr_with_gemini", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "OCR page content"
            pages = await extract_or_ocr_pages(pdf, filename="scan.pdf")
        mock_ocr.assert_called_once()
        assert pages == [(1, "OCR page content")]

    @pytest.mark.asyncio
    async def test_ocr_returns_empty_on_blank_result(self):
        pdf = _blank_pdf()
        with patch("src.services.pdf_extract.ocr_with_gemini", new_callable=AsyncMock) as mock_ocr:
            mock_ocr.return_value = "   "
            pages = await extract_or_ocr_pages(pdf)
        assert pages == []
