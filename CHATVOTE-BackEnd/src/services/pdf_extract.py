"""
Unified PDF text extraction.

Single source of truth for extracting text from PDF documents.
Consolidates the three previous implementations:
- manifesto_indexer.extract_pages_from_pdf (page-aware)
- document_upload.extract_text_from_pdf_bytes (flat concat)
- candidate_website_scraper._download_pdf (inline)

Usage:
    from src.services.pdf_extract import extract_pages, extract_text, extract_or_ocr

    # Page-aware extraction (for manifestos, posters)
    pages = extract_pages(pdf_bytes)  # [(1, "text..."), (2, "text...")]

    # Flat extraction (when page numbers don't matter)
    text = extract_text(pdf_bytes)

    # With OCR fallback (for scanned/image PDFs)
    text = await extract_or_ocr(pdf_bytes, filename="poster.pdf")
"""

import asyncio
import base64
import io
import logging
import os
from typing import Optional

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# Minimum chars from pypdf before falling back to OCR.
# Scanned PDFs often have a small footer (~100 chars) but no real content.
MIN_TEXT_FOR_OCR_FALLBACK = 200


def extract_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Extract text from PDF, preserving page boundaries.

    Returns a list of (1-indexed_page_number, page_text) tuples.
    Pages with no extractable text are omitted.
    """
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text and text.strip():
                pages.append((page_num, text))
        return pages
    except Exception as e:
        logger.error(f"Error extracting pages from PDF: {e}")
        return []


def extract_text(pdf_bytes: bytes) -> str:
    """Extract all text from PDF as a single string.

    Pages are joined with double newlines.
    """
    pages = extract_pages(pdf_bytes)
    return "\n\n".join(text for _, text in pages)


async def ocr_with_gemini(pdf_bytes: bytes, filename: str = "document.pdf") -> str:
    """OCR a PDF using Gemini 2.0 Flash vision.

    Sends the raw PDF to Gemini which can read images and extract text
    from scanned documents. Requires GOOGLE_API_KEY.
    """
    from google import genai

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY required for OCR")

    client = genai.Client(api_key=api_key)
    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode("utf-8")

    logger.info(f"[OCR] Sending {filename} ({len(pdf_bytes):,} bytes) to Gemini")

    response = await asyncio.to_thread(
        client.models.generate_content,
        model="gemini-2.0-flash",
        contents=[
            {
                "parts": [
                    {"inline_data": {"mime_type": "application/pdf", "data": pdf_b64}},
                    {"text": (
                        "Extract ALL text from this scanned PDF document. "
                        "Return ONLY the extracted text, preserving paragraph structure. "
                        "If there are multiple pages, separate them with blank lines. "
                        "Do not add any commentary or formatting — just the raw text content."
                    )},
                ]
            }
        ],
    )

    text = response.text.strip() if response.text else ""
    logger.info(f"[OCR] Gemini extracted {len(text)} chars from {filename}")
    return text


async def extract_or_ocr(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    *,
    min_text_length: int = MIN_TEXT_FOR_OCR_FALLBACK,
) -> str:
    """Extract text from PDF, falling back to Gemini OCR for scanned documents.

    If pypdf extracts fewer than `min_text_length` chars, assumes the PDF
    is image-based and sends it to Gemini for OCR.
    """
    text = extract_text(pdf_bytes)
    if len(text.strip()) >= min_text_length:
        return text

    logger.info(
        f"pypdf extracted only {len(text.strip())} chars from {filename}, "
        f"falling back to Gemini OCR"
    )
    return await ocr_with_gemini(pdf_bytes, filename)


async def extract_or_ocr_pages(
    pdf_bytes: bytes,
    filename: str = "document.pdf",
    *,
    min_text_length: int = MIN_TEXT_FOR_OCR_FALLBACK,
) -> list[tuple[int, str]]:
    """Page-aware extraction with OCR fallback.

    If pypdf extracts enough text, returns real page boundaries.
    If OCR is needed, returns all OCR text as a single page (1, text).
    """
    pages = extract_pages(pdf_bytes)
    total_chars = sum(len(t) for _, t in pages)

    if total_chars >= min_text_length:
        return pages

    logger.info(
        f"pypdf extracted only {total_chars} chars from {filename}, "
        f"falling back to Gemini OCR"
    )
    ocr_text = await ocr_with_gemini(pdf_bytes, filename)
    if ocr_text.strip():
        return [(1, ocr_text)]
    return []


def extract_text_from_txt_bytes(data: bytes) -> str:
    """Decode TXT file bytes to string (utf-8, latin-1 fallback)."""
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode TXT file with utf-8 or latin-1")


async def extract_file(filename: str, data: bytes) -> str:
    """Dispatch text extraction based on file extension.

    Supports: .pdf (with OCR fallback), .txt
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return await extract_or_ocr(data, filename)
    elif lower.endswith(".txt"):
        return extract_text_from_txt_bytes(data)
    else:
        raise ValueError(f"Unsupported file type: {filename}. Supported: .pdf, .txt")
