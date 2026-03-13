# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Service to index profession de foi PDFs into Qdrant and upload to Firebase Storage.

Profession de foi = official candidate manifestos from the French interior ministry.
Source: https://programme-candidats.interieur.gouv.fr/elections-municipales-2026/

Pipeline:
1. Read locally cached PDFs (downloaded by professions pipeline node)
2. Upload to Firebase Storage for user-accessible viewing
3. Extract text with pypdf (page-aware)
4. Chunk with RecursiveCharacterTextSplitter
5. Embed and index into candidates_websites Qdrant collection
6. Update Firestore candidate doc with Firebase Storage URL
"""

import asyncio
import logging
import os
from pathlib import Path
import tempfile

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client.models import (
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
)

from src.firebase_service import aget_candidate_by_id, async_db
from src.models.candidate import Candidate
from src.models.chunk_metadata import ChunkMetadata
from src.services.candidate_indexer import (
    CANDIDATES_INDEX_NAME,
    _ensure_candidates_collection_exists,
    _get_candidates_vector_store,
)
from src.services.manifesto_indexer import extract_pages_from_pdf
from src.vector_store_helper import qdrant_client

logger = logging.getLogger(__name__)


async def _extract_pages_with_gemini(pdf_content: bytes) -> list[tuple[int, str]]:
    """Extract text from image-only PDFs using Gemini vision via LangChain.

    Sends the PDF to Gemini which can natively read scanned/image PDFs
    with much higher accuracy than traditional OCR.

    Returns [(1-indexed page_num, text), ...] or empty list on failure.
    """
    import base64

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        logger.warning("[profession_indexer] langchain-google-genai not installed, skipping Gemini OCR")
        return []

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("[profession_indexer] GOOGLE_API_KEY not set, skipping Gemini OCR")
        return []

    try:
        from langchain_core.messages import HumanMessage

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=api_key,
            temperature=0.0,
            max_output_tokens=8192,
        )

        pdf_b64 = base64.standard_b64encode(pdf_content).decode("utf-8")

        message = HumanMessage(
            content=[
                {
                    "type": "media",
                    "mime_type": "application/pdf",
                    "data": pdf_b64,
                },
                {
                    "type": "text",
                    "text": (
                        "Extrais le texte complet de ce document PDF page par page. "
                        "Pour chaque page, commence par '=== PAGE N ===' (N = numéro de page). "
                        "Retranscris fidèlement tout le texte visible, sans résumer ni reformuler. "
                        "Conserve la structure (titres, listes, paragraphes)."
                    ),
                },
            ]
        )

        response = await llm.ainvoke([message])
        response_text = response.content if hasattr(response, "content") else str(response)

        if not response_text:
            return []

        # Parse pages from response
        pages: list[tuple[int, str]] = []
        current_page = 1
        current_text: list[str] = []

        for line in response_text.split("\n"):
            if line.strip().startswith("=== PAGE"):
                # Save previous page
                if current_text:
                    text = "\n".join(current_text).strip()
                    if text:
                        pages.append((current_page, text))

                # Parse page number
                try:
                    page_str = line.strip().replace("=== PAGE", "").replace("===", "").strip()
                    current_page = int(page_str)
                except ValueError:
                    current_page = len(pages) + 1
                current_text = []
            else:
                current_text.append(line)

        # Don't forget last page
        if current_text:
            text = "\n".join(current_text).strip()
            if text:
                pages.append((current_page, text))

        # If no page markers found, treat entire response as page 1
        if not pages and response_text.strip():
            pages = [(1, response_text.strip())]

        return pages

    except Exception as e:
        logger.error(f"[profession_indexer] Gemini OCR failed: {e}")
        return []


# Directory where professions pipeline saves PDFs
_PDF_CACHE_DIR = Path(tempfile.gettempdir()) / "chatvote_professions_pdfs"

# Firebase Storage config
env = os.getenv("ENV", "dev")
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET", f"chat-vote-{env}.firebasestorage.app")
STORAGE_PREFIX = "public/professions_de_foi"

# Text splitter — same config as candidate_indexer and manifesto_indexer
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP,
    length_function=len,
    separators=["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""],
)


# ---------------------------------------------------------------------------
# Firebase Storage upload
# ---------------------------------------------------------------------------

def _upload_to_storage(data: bytes, blob_path: str) -> str:
    """Upload PDF bytes to Firebase Storage and return a download URL."""
    from firebase_admin import storage

    bucket = storage.bucket(BUCKET_NAME)
    blob = bucket.blob(blob_path)
    blob.metadata = {"firebaseStorageDownloadTokens": blob_path.replace("/", "_")}
    blob.upload_from_string(data, content_type="application/pdf")
    token = blob.metadata["firebaseStorageDownloadTokens"]
    return (
        f"https://firebasestorage.googleapis.com/v0/b/{bucket.name}"
        f"/o/{blob_path.replace('/', '%2F')}?alt=media&token={token}"
    )


# ---------------------------------------------------------------------------
# Document creation
# ---------------------------------------------------------------------------

def _create_documents_from_profession(
    candidate: Candidate,
    pages: list[tuple[int, str]],
    storage_url: str,
) -> list[Document]:
    """Chunk PDF pages into LangChain Documents with ChunkMetadata."""
    documents = []
    chunk_index = 0

    for page_num, page_text in pages:
        chunks = text_splitter.split_text(page_text)
        for chunk in chunks:
            if len(chunk.strip()) < 30:
                continue

            cm = ChunkMetadata(
                namespace=candidate.candidate_id,
                source_document="profession_de_foi",
                party_ids=candidate.party_ids or [],
                candidate_ids=[candidate.candidate_id],
                candidate_name=candidate.full_name,
                municipality_code=candidate.municipality_code or "",
                municipality_name=candidate.municipality_name or "",
                election_type_id=candidate.election_type_id,
                is_tete_de_liste=(candidate.position == "Tête de liste") or None,
                document_name=f"{candidate.full_name} - Profession de foi",
                url=storage_url,
                page_type="pdf_transcription",
                page=page_num,
                chunk_index=chunk_index,
                total_chunks=0,  # filled below
                fiabilite=1,  # Fiabilite.GOVERNMENT — official ministry document
            )
            doc = Document(page_content=chunk, metadata=cm.to_qdrant_payload())
            documents.append(doc)
            chunk_index += 1

    for doc in documents:
        doc.metadata["total_chunks"] = len(documents)

    return documents


# ---------------------------------------------------------------------------
# Qdrant: delete existing profession_de_foi chunks for a candidate
# ---------------------------------------------------------------------------

def _delete_profession_chunks(candidate_id: str) -> None:
    """Delete existing profession_de_foi chunks for a candidate from Qdrant.

    Only deletes chunks with source_document=profession_de_foi, leaving
    website chunks for the same candidate intact.
    """
    try:
        _ensure_candidates_collection_exists()
        qdrant_client.delete(
            collection_name=CANDIDATES_INDEX_NAME,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.namespace",
                            match=MatchValue(value=candidate_id),
                        ),
                        FieldCondition(
                            key="metadata.source_document",
                            match=MatchValue(value="profession_de_foi"),
                        ),
                    ]
                )
            ),
        )
        logger.info(f"Deleted existing profession_de_foi chunks for {candidate_id}")
    except Exception as e:
        logger.error(
            f"Error deleting profession_de_foi chunks for {candidate_id}: {e}"
        )


# ---------------------------------------------------------------------------
# Core indexing function
# ---------------------------------------------------------------------------

async def index_candidate_profession(candidate_id: str, pdf_path: str) -> int:
    """Index a single profession de foi PDF for a candidate.

    Steps:
    1. Read PDF from local path (already downloaded by professions pipeline node)
    2. Upload to Firebase Storage
    3. Extract text, chunk, embed, store in Qdrant
    4. Update Firestore candidate doc with Firebase Storage URL

    Args:
        candidate_id: e.g. "cand-75056-1"
        pdf_path: local filesystem path to the downloaded PDF

    Returns:
        Number of chunks indexed. 0 on failure.
    """
    import time as _t

    _t0 = _t.monotonic()
    logger.info(f"[profession_indexer] indexing {candidate_id} from {pdf_path}")

    # Step 1: Read PDF bytes
    try:
        pdf_content = Path(pdf_path).read_bytes()
    except Exception as e:
        logger.error(f"Could not read PDF for {candidate_id} at {pdf_path}: {e}")
        return 0

    # Step 2: Load candidate from Firestore — must be fully seeded
    try:
        candidate = await aget_candidate_by_id(candidate_id)
    except Exception:
        candidate = None  # incomplete Firestore doc (e.g. only has_manifesto fields)
    if candidate is None:
        logger.warning(
            f"[profession_indexer] skipping {candidate_id} — "
            f"not fully seeded in Firestore (run seed pipeline first)"
        )
        return 0

    # Step 3: Upload to Firebase Storage
    # Extract commune_code from candidate or candidate_id
    commune_code = candidate.municipality_code or (
        candidate_id.split("-")[1] if len(candidate_id.split("-")) >= 3 else "unknown"
    )
    blob_path = f"{STORAGE_PREFIX}/{commune_code}/{candidate_id}.pdf"

    try:
        storage_url = await asyncio.to_thread(
            _upload_to_storage, pdf_content, blob_path
        )
        logger.info(
            f"[profession_indexer] uploaded {candidate_id} to Firebase Storage: {storage_url}"
        )
    except Exception as e:
        logger.error(f"Failed to upload PDF to Firebase Storage for {candidate_id}: {e}")
        return 0

    # Step 4: Extract PDF text (page-aware), with OCR fallback for image PDFs
    pages = extract_pages_from_pdf(pdf_content)
    if not pages:
        logger.info(f"[profession_indexer] no text from pypdf for {candidate_id}, trying Gemini vision...")
        pages = await _extract_pages_with_gemini(pdf_content)
    if not pages:
        logger.warning(f"No text extracted from PDF for {candidate_id} (even with Gemini) — skipping indexing")
        # Still update Firestore with the storage URL
        await _update_firestore_url(candidate_id, storage_url)
        return 0

    total_chars = sum(len(t) for _, t in pages)
    logger.info(
        f"[profession_indexer] extracted {total_chars} chars from "
        f"{len(pages)} pages for {candidate_id}"
    )

    # Step 5: Create documents (chunks with real page numbers)
    documents = _create_documents_from_profession(candidate, pages, storage_url)
    if not documents:
        logger.warning(f"No chunks created for {candidate_id}")
        await _update_firestore_url(candidate_id, storage_url)
        return 0

    logger.info(f"[profession_indexer] created {len(documents)} chunks for {candidate_id}")

    # Step 5.5: Classify themes (optional — degrades gracefully)
    try:
        from src.services.chunk_classifier import classify_chunks_themes

        chunk_texts = [doc.page_content for doc in documents]
        classifications = await classify_chunks_themes(chunk_texts)
        for doc, cls in zip(documents, classifications):
            if cls.theme:
                doc.metadata["theme"] = cls.theme
            if cls.sub_theme:
                doc.metadata["sub_theme"] = cls.sub_theme
        classified = sum(1 for c in classifications if c.theme)
        logger.info(
            f"[profession_indexer] classified {classified}/{len(documents)} "
            f"chunks with themes for {candidate_id}"
        )
    except Exception as e:
        logger.warning(f"[profession_indexer] theme classification failed for {candidate_id}: {e}")

    # Step 6: Delete existing profession_de_foi chunks (keep website chunks)
    await asyncio.to_thread(_delete_profession_chunks, candidate_id)

    # Step 7: Index into Qdrant in batches
    vector_store = _get_candidates_vector_store()
    batch_size = 50
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        await vector_store.aadd_documents(batch)
        await asyncio.sleep(0)  # yield to event loop between batches
        logger.debug(
            f"[profession_indexer] uploaded batch {i // batch_size + 1} "
            f"({len(batch)} docs) for {candidate_id}"
        )

    # Step 8: Update Firestore candidate doc with Firebase Storage URL
    await _update_firestore_url(candidate_id, storage_url)

    elapsed = _t.monotonic() - _t0
    logger.info(
        f"[profession_indexer] done {candidate_id}: "
        f"{len(documents)} chunks in {elapsed:.1f}s"
    )
    return len(documents)


async def _update_firestore_url(candidate_id: str, storage_url: str) -> None:
    """Update Firestore candidate doc with the Firebase Storage URL."""
    try:
        ref = async_db.collection("candidates").document(candidate_id)
        await ref.set(
            {
                "has_manifesto": True,
                "manifesto_pdf_url": storage_url,
            },
            merge=True,
        )
        logger.debug(f"[profession_indexer] Firestore updated for {candidate_id}")
    except Exception as e:
        logger.error(f"Failed to update Firestore for {candidate_id}: {e}")


# ---------------------------------------------------------------------------
# Commune-level and full-batch functions
# ---------------------------------------------------------------------------

async def index_commune_professions(commune_code: str) -> dict[str, int]:
    """Index all profession de foi PDFs for a commune from the local cache.

    Expects PDFs in _PDF_CACHE_DIR/{commune_code}/ with filenames
    matching the pattern {tour}-{commune_code}-{panneau}.pdf.
    candidate_id is derived as cand-{commune_code}-{panneau}.

    Args:
        commune_code: INSEE commune code, e.g. "75056"

    Returns:
        {candidate_id: chunk_count} for each PDF found.
    """
    commune_dir = _PDF_CACHE_DIR / commune_code
    if not commune_dir.exists():
        logger.warning(
            f"[profession_indexer] no PDF cache dir for commune {commune_code}: {commune_dir}"
        )
        return {}

    pdf_files = list(commune_dir.glob("*.pdf"))
    if not pdf_files:
        logger.info(f"[profession_indexer] no PDFs found for commune {commune_code}")
        return {}

    logger.info(
        f"[profession_indexer] found {len(pdf_files)} PDFs for commune {commune_code}"
    )

    results: dict[str, int] = {}
    for pdf_path in pdf_files:
        # Filename pattern: {tour}-{commune_code}-{panneau}.pdf
        # e.g. 1-75056-3.pdf -> panneau=3, candidate_id=cand-75056-3
        stem = pdf_path.stem  # e.g. "1-75056-3"
        parts = stem.split("-")
        if len(parts) < 3:
            logger.warning(
                f"[profession_indexer] unexpected filename format: {pdf_path.name}, skipping"
            )
            continue

        panneau = parts[-1]
        candidate_id = f"cand-{commune_code}-{panneau}"

        try:
            count = await index_candidate_profession(candidate_id, str(pdf_path))
            results[candidate_id] = count
        except Exception as e:
            logger.error(
                f"[profession_indexer] error indexing {candidate_id} "
                f"({pdf_path.name}): {e}"
            )
            results[candidate_id] = 0

    return results


async def index_all_professions() -> dict[str, int]:
    """Index all profession de foi PDFs across all communes in the local cache.

    Iterates all commune directories in _PDF_CACHE_DIR and calls
    index_commune_professions for each one.

    Returns:
        Aggregated {candidate_id: chunk_count} across all communes.
    """
    if not _PDF_CACHE_DIR.exists():
        logger.warning(
            f"[profession_indexer] PDF cache directory does not exist: {_PDF_CACHE_DIR}"
        )
        return {}

    commune_dirs = [d for d in _PDF_CACHE_DIR.iterdir() if d.is_dir()]
    if not commune_dirs:
        logger.info(f"[profession_indexer] no commune directories found in {_PDF_CACHE_DIR}")
        return {}

    logger.info(
        f"[profession_indexer] found {len(commune_dirs)} commune directories to process"
    )

    all_results: dict[str, int] = {}
    for commune_dir in sorted(commune_dirs):
        commune_code = commune_dir.name
        try:
            results = await index_commune_professions(commune_code)
            all_results.update(results)
        except Exception as e:
            logger.error(
                f"[profession_indexer] error processing commune {commune_code}: {e}"
            )

    total_chunks = sum(all_results.values())
    successful = sum(1 for v in all_results.values() if v > 0)
    logger.info(
        f"[profession_indexer] all done — {total_chunks} total chunks "
        f"for {successful}/{len(all_results)} candidates"
    )

    return all_results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point to index all profession de foi PDFs."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Index profession de foi PDFs into Qdrant and Firebase Storage"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--commune",
        metavar="CODE",
        help="Index only a specific commune (e.g. 75056)",
    )
    group.add_argument(
        "--candidate",
        metavar="CANDIDATE_ID",
        help="Index a single candidate (e.g. cand-75056-1)",
    )
    parser.add_argument(
        "--pdf",
        metavar="PATH",
        help="Path to a specific PDF to index (used with --candidate)",
    )
    args = parser.parse_args()

    try:
        if args.candidate and args.pdf:
            result = asyncio.run(index_candidate_profession(args.candidate, args.pdf))
            print(f"Indexed {result} chunks for {args.candidate}")
        elif args.commune:
            results = asyncio.run(index_commune_professions(args.commune))
            print(f"\nResults for commune {args.commune}:")
            for candidate_id, count in sorted(results.items()):
                status = "OK" if count > 0 else "FAILED"
                print(f"  [{status}] {candidate_id}: {count} chunks")
            total = sum(results.values())
            print(f"\nTotal: {total} chunks for {len(results)} candidates")
        else:
            results = asyncio.run(index_all_professions())
            print("\nResults:")
            for candidate_id, count in sorted(results.items()):
                status = "OK" if count > 0 else "FAILED"
                print(f"  [{status}] {candidate_id}: {count} chunks")
            total = sum(results.values())
            successful = sum(1 for v in results.values() if v > 0)
            print(
                f"\nTotal: {total} chunks indexed for {successful}/{len(results)} candidates"
            )
    except Exception as e:
        logger.error(f"Indexation failed: {e}", exc_info=True)
        print(f"Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()
