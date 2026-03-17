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

from src.firebase_service import aget_parties, aget_candidates
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
        model="gemini-2.5-flash",
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
    """Try to match a party or candidate from the filename."""
    lower_fn = filename.lower()

    # Check national parties
    parties = await aget_parties()
    for party in parties:
        if party.party_id.lower() in lower_fn or party.name.lower() in lower_fn:
            return AssignmentResult(
                target_type="party",
                target_id=party.party_id,
                target_name=party.name,
                collection=PARTY_INDEX_NAME,
                confidence=0.85,
            )
        if hasattr(party, "abbreviation") and party.abbreviation:
            if party.abbreviation.lower() in lower_fn:
                return AssignmentResult(
                    target_type="party",
                    target_id=party.party_id,
                    target_name=party.name,
                    collection=PARTY_INDEX_NAME,
                    confidence=0.80,
                )

    # Check candidates by full name
    candidates = await aget_candidates()
    for c in candidates:
        full = c.full_name.lower()
        last = c.last_name.lower()
        # Match "lastname" (>3 chars to avoid false positives) or "firstname lastname"
        if (len(last) > 3 and last in lower_fn) or full in lower_fn:
            return AssignmentResult(
                target_type="candidate",
                target_id=c.candidate_id,
                target_name=f"{c.full_name} ({c.municipality_name or ''})",
                collection=CANDIDATES_INDEX_NAME,
                confidence=0.80,
            )

    return None


async def _llm_classify(text_excerpt: str, filename: str) -> Optional[AssignmentResult]:
    """Use the LLM to classify which party, candidate, or local list
    a document belongs to. Handles both national parties and local
    municipal electoral lists."""
    from src.llms import DETERMINISTIC_LLMS, get_answer_from_llms

    parties = await aget_parties()
    candidates = await aget_candidates()

    party_list = ", ".join(f"{p.party_id} ({p.name})" for p in parties)

    # Build a concise candidate reference grouped by municipality
    municipalities: dict[str, list] = {}
    for c in candidates:
        key = c.municipality_name or c.municipality_code or "unknown"
        if key not in municipalities:
            municipalities[key] = []
        municipalities[key].append(
            f"{c.candidate_id}: {c.full_name}"
            + (f" [{', '.join(c.party_ids)}]" if c.party_ids else "")
        )

    # Limit to avoid huge prompt — include first 40 municipalities
    candidate_lines = []
    for muni, cands in list(municipalities.items())[:40]:
        candidate_lines.append(f"  {muni}: " + "; ".join(cands[:10]))
    candidate_ref = "\n".join(candidate_lines)

    system_msg = SystemMessage(content=(
        "You are a document classifier for French municipal and national elections. "
        "Given a document, determine which entity it belongs to: a national party, "
        "a local electoral list, or a specific candidate. "
        "Respond ONLY with valid JSON, no markdown."
    ))
    human_msg = HumanMessage(content=(
        f"Filename: {filename}\n\n"
        f"Known national parties: {party_list}\n\n"
        f"Known candidates by municipality:\n{candidate_ref}\n\n"
        f"Text excerpt:\n{text_excerpt[:2000]}\n\n"
        "Determine which entity this document belongs to. Respond with JSON:\n"
        "If it matches a NATIONAL PARTY:\n"
        '  {"type": "party", "id": "<party_id>", "confidence": <0.0-1.0>, "reason": "..."}\n'
        "If it matches a LOCAL CANDIDATE or a local electoral list:\n"
        '  {"type": "candidate", "id": "<candidate_id>", "confidence": <0.0-1.0>, "reason": "..."}\n'
        "For local electoral lists, pick the tête de liste / head candidate from "
        "the same municipality. The type MUST be either \"party\" or \"candidate\".\n"
        "If you can identify the national party affiliation (e.g. LFI, Renaissance) "
        "but no specific candidate, use type=\"party\" with the party_id.\n"
        "If you cannot determine:\n"
        '  {"type": null, "id": null, "confidence": 0.0, "reason": "unable to determine"}'
    ))

    try:
        response = await get_answer_from_llms(DETERMINISTIC_LLMS, [system_msg, human_msg])
        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        result = json.loads(content)
        entity_type = result.get("type")
        entity_id = result.get("id")
        confidence = float(result.get("confidence", 0.0))

        if not entity_type or not entity_id or confidence < 0.3:
            logger.info(f"LLM classification low confidence: {result}")
            return None

        if entity_type == "party":
            party = next((p for p in parties if p.party_id == entity_id), None)
            if not party:
                logger.warning(f"LLM returned unknown party_id: {entity_id}")
                return None
            return AssignmentResult(
                target_type="party",
                target_id=party.party_id,
                target_name=party.name,
                collection=PARTY_INDEX_NAME,
                confidence=confidence,
            )
        elif entity_type == "candidate":
            candidate = next(
                (c for c in candidates if c.candidate_id == entity_id), None
            )
            if not candidate:
                logger.warning(f"LLM returned unknown candidate_id: {entity_id}")
                return None
            return AssignmentResult(
                target_type="candidate",
                target_id=candidate.candidate_id,
                target_name=f"{candidate.full_name} ({candidate.municipality_name or ''})",
                collection=CANDIDATES_INDEX_NAME,
                confidence=confidence,
            )
        else:
            logger.warning(f"LLM returned unknown type: {entity_type}")
            return None

    except Exception as e:
        logger.warning(f"LLM classification failed: {e}")
        return None


async def _try_text_search(text: str) -> Optional[AssignmentResult]:
    """Search document text for candidate names, family names, and city names.

    Scores each candidate by how many identifiers appear in the text:
    - last_name (weight 2), first_name (weight 1), municipality (weight 2)
    - full_name exact match (weight 5)
    Returns the highest-scoring candidate if score >= 3.
    """
    import re

    lower_text = text[:5000].lower()  # search first 5000 chars
    candidates = await aget_candidates()

    best_candidate = None
    best_score = 0

    for c in candidates:
        score = 0
        last = c.last_name.lower()
        first = c.first_name.lower()
        full = c.full_name.lower()

        # Full name match is strongest signal
        if full in lower_text:
            score += 5
        else:
            # Last name (only if >3 chars to avoid false positives like "Le")
            if len(last) > 3 and re.search(r'\b' + re.escape(last) + r'\b', lower_text):
                score += 2
            # First name (only counted alongside last name presence)
            if score > 0 and re.search(r'\b' + re.escape(first) + r'\b', lower_text):
                score += 1

        # Municipality match
        if c.municipality_name and len(c.municipality_name) > 3:
            muni = c.municipality_name.lower()
            if re.search(r'\b' + re.escape(muni) + r'\b', lower_text):
                score += 2

        if score > best_score:
            best_score = score
            best_candidate = c

    if best_candidate and best_score >= 3:
        confidence = min(0.95, 0.5 + best_score * 0.08)
        logger.info(
            f"Text search match: {best_candidate.full_name} "
            f"({best_candidate.municipality_name}) score={best_score}"
        )
        return AssignmentResult(
            target_type="candidate",
            target_id=best_candidate.candidate_id,
            target_name=f"{best_candidate.full_name} ({best_candidate.municipality_name or ''})",
            collection=CANDIDATES_INDEX_NAME,
            confidence=confidence,
        )

    # Also check party names in text
    parties = await aget_parties()
    for party in parties:
        name = party.name.lower()
        if len(name) > 4 and re.search(r'\b' + re.escape(name) + r'\b', lower_text):
            return AssignmentResult(
                target_type="party",
                target_id=party.party_id,
                target_name=party.name,
                collection=PARTY_INDEX_NAME,
                confidence=0.75,
            )

    return None


async def auto_assign(filename: str, text: str) -> Optional[AssignmentResult]:
    """Auto-assign a document to a party, candidate, or local electoral list.

    Strategy:
    1. Try filename heuristics (national parties + candidate names)
    2. Search document text for candidate names, family names, city names
    3. Fall back to LLM classification with full context (parties + candidates)
    """
    # Step 1: filename match
    result = await _try_filename_match(filename)
    if result:
        logger.info(
            f"Filename match: {filename} -> {result.target_name} "
            f"(confidence={result.confidence})"
        )
        return result

    # Step 2: text search for candidate/party identifiers
    result = await _try_text_search(text)
    if result:
        logger.info(
            f"Text search: {filename} -> {result.target_name} "
            f"(confidence={result.confidence})"
        )
        return result

    # Step 3: LLM classification (includes both parties and candidates)
    result = await _llm_classify(text, filename)
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
    source_url: Optional[str] = None,
    source_type: Optional[str] = None,
) -> list[Document]:
    """Chunk text and create LangChain Documents with ChunkMetadata."""
    chunks = text_splitter.split_text(text)
    documents = []

    for chunk_index, chunk in enumerate(chunks):
        if len(chunk.strip()) < 30:
            continue

        cm = ChunkMetadata(
            namespace=assignment.target_id,
            source_document=source_type or "uploaded_document",
            party_ids=[assignment.target_id] if assignment.target_type == "party" else [],
            candidate_ids=[assignment.target_id] if assignment.target_type == "candidate" else [],
            party_name=assignment.target_name if assignment.target_type == "party" else None,
            candidate_name=assignment.target_name if assignment.target_type == "candidate" else None,
            document_name=filename,
            url=source_url,
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


# ---------------------------------------------------------------------------
# Preview / confirm pipeline
# ---------------------------------------------------------------------------

async def preview_upload(
    job_id: str,
    filename: str,
    data: bytes,
    source_url: Optional[str] = None,
    source_type: Optional[str] = None,
) -> dict[str, Any]:
    """Preview pipeline: extract -> classify -> chunk (no indexing).

    Returns preview data for admin review before confirmation.
    """
    try:
        _update_job(job_id, status="extracting", progress=10)
        text = await extract_text(filename, data)
        if not text or len(text.strip()) < 50:
            _update_job(job_id, status="error", error="Extracted text is too short or empty")
            return {"error": "Extracted text is too short or empty"}

        logger.info(f"[{job_id}] Preview: extracted {len(text)} chars from {filename}")

        _update_job(job_id, status="classifying", progress=25)
        assignment = await auto_assign(filename, text)

        _update_job(job_id, status="chunking", progress=50)
        # Use a placeholder for preview purposes if auto-assign failed
        preview_assignment = assignment
        if not preview_assignment:
            preview_assignment = AssignmentResult(
                target_type="unknown",
                target_id="unassigned",
                target_name="Unassigned",
                collection="",
                confidence=0.0,
            )

        documents = _create_documents(text, preview_assignment, filename, source_url=source_url, source_type=source_type)

        preview = {
            "text_length": len(text),
            "text_preview": text[:500],
            "chunks_count": len(documents),
            "chunk_previews": [
                {
                    "index": i,
                    "content": doc.page_content,
                    "length": len(doc.page_content),
                    "metadata": doc.metadata,
                }
                for i, doc in enumerate(documents[:5])
            ],
            "auto_assignment": assignment.to_dict() if assignment else None,
        }

        _update_job(
            job_id,
            status="preview",
            progress=60,
            assigned_to=assignment.to_dict() if assignment else None,
            preview=preview,
        )

        return preview

    except Exception as e:
        logger.error(f"[{job_id}] Preview failed: {e}", exc_info=True)
        _update_job(job_id, status="error", error=str(e))
        return {"error": str(e)}


async def _resolve_manual_target(target_type: str, target_id: str) -> Optional[AssignmentResult]:
    """Resolve a manually selected target to an AssignmentResult."""
    if target_type == "party":
        parties = await aget_parties()
        party = next((p for p in parties if p.party_id == target_id), None)
        if party:
            return AssignmentResult(
                target_type="party",
                target_id=party.party_id,
                target_name=party.name,
                collection=PARTY_INDEX_NAME,
                confidence=1.0,
            )
    elif target_type == "candidate":
        candidates = await aget_candidates()
        candidate = next((c for c in candidates if c.candidate_id == target_id), None)
        if candidate:
            return AssignmentResult(
                target_type="candidate",
                target_id=candidate.candidate_id,
                target_name=f"{candidate.full_name} ({candidate.municipality_name or ''})",
                collection=CANDIDATES_INDEX_NAME,
                confidence=1.0,
            )
    return None


async def confirm_upload(
    job_id: str,
    filename: str,
    data: bytes,
    manual_target_type: Optional[str] = None,
    manual_target_id: Optional[str] = None,
    source_url: Optional[str] = None,
    source_type: Optional[str] = None,
) -> None:
    """Confirm and index a previewed upload, optionally with manual assignment override."""
    try:
        _update_job(job_id, status="extracting", progress=10)
        text = await extract_text(filename, data)
        if not text or len(text.strip()) < 50:
            _update_job(job_id, status="error", error="Extracted text is too short or empty")
            return

        # Use manual override or auto-assign
        assignment: Optional[AssignmentResult] = None
        if manual_target_type and manual_target_id:
            _update_job(job_id, status="classifying", progress=25)
            assignment = await _resolve_manual_target(manual_target_type, manual_target_id)

        if not assignment:
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

        _update_job(job_id, status="chunking", progress=50)
        documents = _create_documents(text, assignment, filename, source_url=source_url, source_type=source_type)
        if not documents:
            _update_job(job_id, status="error", error="No chunks created from document")
            return

        _update_job(job_id, status="embedding", progress=60)
        _update_job(job_id, status="indexing", progress=75)
        count = await _index_documents(documents, assignment)

        _update_job(
            job_id,
            status="done",
            progress=100,
            chunks_indexed=count,
        )
        logger.info(f"[{job_id}] Indexed {count} chunks for {filename}")

    except Exception as e:
        logger.error(f"[{job_id}] Confirm upload failed: {e}", exc_info=True)
        _update_job(job_id, status="error", error=str(e))
