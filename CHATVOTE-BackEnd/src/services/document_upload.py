"""
Service to handle document uploads, auto-classify them to a party/candidate,
and index into Qdrant.

Supported formats: PDF, TXT (DOCX planned for later).

Pipeline:
1. Extract text from uploaded file
2. Auto-assign to a party or candidate (filename heuristics, then LLM classification)
3. Chunk the text
4. Embed and index into Qdrant
"""

import asyncio
import io
import json
import logging
import os
import time
import uuid
from typing import Any, Optional

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from src.firebase_service import aget_parties
from src.models.chunk_metadata import ChunkMetadata
from src.vector_store_helper import (
    get_qdrant_vector_store,
    get_candidates_vector_store,
    PARTY_INDEX_NAME,
    CANDIDATES_INDEX_NAME,
)

logger = logging.getLogger(__name__)

# Text splitter — same config as manifesto_indexer
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""],
)

# ---------------------------------------------------------------------------
# Job tracking (in-memory)
# ---------------------------------------------------------------------------
_upload_jobs: dict[str, dict[str, Any]] = {}


def create_job(filename: str) -> str:
    """Create a new upload job and return its ID."""
    job_id = uuid.uuid4().hex[:12]
    _upload_jobs[job_id] = {
        "status": "pending",
        "progress": 0,
        "filename": filename,
        "assigned_to": None,
        "collection": None,
        "chunks_indexed": 0,
        "error": None,
        "created_at": time.time(),
    }
    return job_id


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    return _upload_jobs.get(job_id)


def get_all_jobs() -> dict[str, dict[str, Any]]:
    return dict(_upload_jobs)


def _update_job(job_id: str, **kwargs: Any) -> None:
    if job_id in _upload_jobs:
        _upload_jobs[job_id].update(kwargs)


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

# Minimum chars from pypdf before falling back to OCR.
# Scanned PDFs often have a small footer (printer info, ~100 chars)
# but no real content — 200 chars catches these.
_MIN_TEXT_LENGTH = 200


def extract_text_from_pdf_bytes(data: bytes) -> str:
    """Extract text from in-memory PDF bytes."""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text and text.strip():
                pages.append(text)
        return "\n\n".join(pages)
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        raise


async def ocr_pdf_with_gemini(data: bytes, filename: str) -> str:
    """OCR a PDF using Gemini vision (for image-based / scanned PDFs).

    Sends the raw PDF to Gemini 2.0 Flash which can read images and
    extract text from scanned documents.
    """
    import base64
    from google import genai

    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY required for OCR")

    client = genai.Client(api_key=api_key)

    pdf_b64 = base64.standard_b64encode(data).decode("utf-8")

    logger.info(f"[OCR] Sending {filename} ({len(data):,} bytes) to Gemini for OCR")

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


def extract_text_from_txt_bytes(data: bytes) -> str:
    """Decode TXT file bytes to string."""
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not decode TXT file with utf-8 or latin-1")


async def extract_text(filename: str, data: bytes) -> str:
    """Dispatch text extraction based on file extension.

    For PDFs: tries pypdf first, falls back to Gemini OCR for image PDFs.
    """
    lower = filename.lower()
    if lower.endswith(".pdf"):
        text = extract_text_from_pdf_bytes(data)
        if len(text.strip()) >= _MIN_TEXT_LENGTH:
            return text
        # Image-based PDF — fall back to Gemini OCR
        logger.info(
            f"pypdf extracted only {len(text.strip())} chars from {filename}, "
            f"falling back to Gemini OCR"
        )
        return await ocr_pdf_with_gemini(data, filename)
    elif lower.endswith(".txt"):
        return extract_text_from_txt_bytes(data)
    else:
        raise ValueError(f"Unsupported file type: {filename}. Supported: .pdf, .txt")


# ---------------------------------------------------------------------------
# Auto-assignment
# ---------------------------------------------------------------------------

class AssignmentResult:
    """Result of auto-assigning a document to a party or candidate."""

    def __init__(
        self,
        target_type: str,       # "party" or "candidate"
        target_id: str,
        target_name: str,
        collection: str,        # Qdrant collection name
        confidence: float,
    ):
        self.target_type = target_type
        self.target_id = target_id
        self.target_name = target_name
        self.collection = collection
        self.confidence = confidence

    def to_dict(self) -> dict:
        return {
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "collection": self.collection,
            "confidence": self.confidence,
        }


async def _try_filename_match(filename: str) -> Optional[AssignmentResult]:
    """Try to match a party from the filename."""
    parties = await aget_parties()
    lower_fn = filename.lower()

    for party in parties:
        # Check party_id and name in filename
        if party.party_id.lower() in lower_fn or party.name.lower() in lower_fn:
            return AssignmentResult(
                target_type="party",
                target_id=party.party_id,
                target_name=party.name,
                collection=PARTY_INDEX_NAME,
                confidence=0.85,
            )
        # Also check common abbreviations if stored
        if hasattr(party, "abbreviation") and party.abbreviation:
            if party.abbreviation.lower() in lower_fn:
                return AssignmentResult(
                    target_type="party",
                    target_id=party.party_id,
                    target_name=party.name,
                    collection=PARTY_INDEX_NAME,
                    confidence=0.80,
                )
    return None


async def _llm_classify(text_excerpt: str) -> Optional[AssignmentResult]:
    """Use the LLM to classify which party/candidate a document belongs to."""
    from src.llms import DETERMINISTIC_LLMS, get_answer_from_llms

    parties = await aget_parties()
    party_list = ", ".join(
        f"{p.party_id} ({p.name})" for p in parties
    )

    system_msg = SystemMessage(content=(
        "You are a document classifier for French political elections. "
        "Given a text excerpt, determine which political party or candidate "
        "this document belongs to. Respond ONLY with valid JSON, no markdown."
    ))
    human_msg = HumanMessage(content=(
        f"Known parties: {party_list}\n\n"
        f"Text excerpt:\n{text_excerpt[:2000]}\n\n"
        "Respond with JSON: "
        '{"party_id": "<id>", "confidence": <0.0-1.0>, "reason": "<brief reason>"}\n'
        "If you cannot determine the party, respond with: "
        '{"party_id": null, "confidence": 0.0, "reason": "unable to determine"}'
    ))

    try:
        response = await get_answer_from_llms(DETERMINISTIC_LLMS, [system_msg, human_msg])
        content = response.content.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        result = json.loads(content)
        party_id = result.get("party_id")
        confidence = float(result.get("confidence", 0.0))

        if not party_id or confidence < 0.3:
            logger.info(f"LLM classification low confidence: {result}")
            return None

        # Verify party_id exists
        party = next((p for p in parties if p.party_id == party_id), None)
        if not party:
            logger.warning(f"LLM returned unknown party_id: {party_id}")
            return None

        return AssignmentResult(
            target_type="party",
            target_id=party.party_id,
            target_name=party.name,
            collection=PARTY_INDEX_NAME,
            confidence=confidence,
        )
    except Exception as e:
        logger.warning(f"LLM classification failed: {e}")
        return None


async def auto_assign(filename: str, text: str) -> Optional[AssignmentResult]:
    """Auto-assign a document to a party or candidate.

    Strategy:
    1. Try filename heuristics first (fast, high confidence)
    2. Fall back to LLM classification of text excerpt
    """
    # Step 1: filename match
    result = await _try_filename_match(filename)
    if result:
        logger.info(
            f"Filename match: {filename} -> {result.target_name} "
            f"(confidence={result.confidence})"
        )
        return result

    # Step 2: LLM classification
    result = await _llm_classify(text)
    if result:
        logger.info(
            f"LLM classification: {filename} -> {result.target_name} "
            f"(confidence={result.confidence})"
        )
        return result

    logger.warning(f"Could not auto-assign document: {filename}")
    return None


# ---------------------------------------------------------------------------
# Indexing pipeline
# ---------------------------------------------------------------------------

def _create_documents(
    text: str,
    assignment: AssignmentResult,
    filename: str,
) -> list[Document]:
    """Chunk text and create LangChain Documents with ChunkMetadata."""
    chunks = text_splitter.split_text(text)
    documents = []

    for chunk_index, chunk in enumerate(chunks):
        if len(chunk.strip()) < 30:
            continue

        cm = ChunkMetadata(
            namespace=assignment.target_id,
            source_document="uploaded_document",
            party_ids=[assignment.target_id] if assignment.target_type == "party" else [],
            candidate_ids=[assignment.target_id] if assignment.target_type == "candidate" else [],
            party_name=assignment.target_name if assignment.target_type == "party" else None,
            candidate_name=assignment.target_name if assignment.target_type == "candidate" else None,
            document_name=filename,
            chunk_index=chunk_index,
            total_chunks=0,  # filled below
        )
        doc = Document(page_content=chunk, metadata=cm.to_qdrant_payload())
        documents.append(doc)

    # Fill total_chunks
    for doc in documents:
        doc.metadata["total_chunks"] = len(documents)

    return documents


async def _index_documents(
    documents: list[Document],
    assignment: AssignmentResult,
) -> int:
    """Index documents into the appropriate Qdrant collection."""
    if assignment.target_type == "party":
        vector_store = get_qdrant_vector_store()
    else:
        vector_store = get_candidates_vector_store()

    batch_size = 50
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        await vector_store.aadd_documents(batch)

    return len(documents)


# ---------------------------------------------------------------------------
# Main processing function
# ---------------------------------------------------------------------------

async def process_upload(job_id: str, filename: str, data: bytes) -> None:
    """Full pipeline: extract -> classify -> chunk -> index.

    Updates job status throughout. Intended to run as a background task.
    """
    try:
        # Stage 1: Extract text (may use Gemini OCR for image PDFs)
        _update_job(job_id, status="extracting", progress=10)
        text = await extract_text(filename, data)
        if not text or len(text.strip()) < 50:
            _update_job(job_id, status="error", error="Extracted text is too short or empty")
            return

        logger.info(f"[{job_id}] Extracted {len(text)} chars from {filename}")

        # Stage 2: Auto-assign
        _update_job(job_id, status="classifying", progress=25)
        assignment = await auto_assign(filename, text)
        if not assignment:
            _update_job(
                job_id,
                status="error",
                error="Could not determine which party/candidate this document belongs to",
            )
            return

        _update_job(
            job_id,
            assigned_to=assignment.to_dict(),
            collection=assignment.collection,
            progress=40,
        )
        logger.info(
            f"[{job_id}] Assigned to {assignment.target_type}: "
            f"{assignment.target_name} ({assignment.target_id})"
        )

        # Stage 3: Chunk
        _update_job(job_id, status="chunking", progress=50)
        documents = _create_documents(text, assignment, filename)
        if not documents:
            _update_job(job_id, status="error", error="No chunks created from document")
            return

        logger.info(f"[{job_id}] Created {len(documents)} chunks")

        # Stage 4: Embed + Index
        _update_job(job_id, status="embedding", progress=60)
        _update_job(job_id, status="indexing", progress=75)
        count = await _index_documents(documents, assignment)

        # Done
        _update_job(
            job_id,
            status="done",
            progress=100,
            chunks_indexed=count,
        )
        logger.info(f"[{job_id}] Indexed {count} chunks for {filename}")

    except Exception as e:
        logger.error(f"[{job_id}] Upload processing failed: {e}", exc_info=True)
        _update_job(job_id, status="error", error=str(e))
