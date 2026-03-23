# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Service to index profession de foi PDFs into Qdrant and upload to S3.

Profession de foi = official candidate manifestos from the French interior ministry.
Source: https://programme-candidats.interieur.gouv.fr/elections-municipales-2026/

Pipeline:
1. Read locally cached PDFs (downloaded by professions pipeline node)
2. Upload to S3 public-assets bucket for user-accessible viewing
3. Extract text with pypdf (page-aware)
4. Chunk with RecursiveCharacterTextSplitter
5. Embed and index into candidates_websites Qdrant collection
6. Update Firestore candidate doc with S3 public URL
"""

import asyncio
import logging
import os
from pathlib import Path

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

from src.services.content_processing import is_real_content

logger = logging.getLogger(__name__)

# Backward-compat alias used by scripts/test_profession_indexing.py
_is_real_content = is_real_content


# ---------------------------------------------------------------------------
# OCR tier 2: tesseract (300 DPI, French)
# ---------------------------------------------------------------------------


def _ocr_pdf_tesseract(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """OCR PDF pages with tesseract (fra, 300 DPI) via pymupdf + pytesseract."""
    pages: list[tuple[int, str]] = []
    try:
        import io as _io

        import fitz  # pymupdf
        import pytesseract
        from PIL import Image

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(len(doc)):
            page = doc[page_num]
            mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(_io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img, lang="fra", config="--psm 6")
            if text and text.strip():
                pages.append((page_num + 1, text))
        doc.close()
        logger.info(f"[profession_indexer] tesseract: {len(pages)} pages extracted")
        return pages
    except Exception as e:
        logger.warning(f"[profession_indexer] tesseract OCR failed: {e}")
        return []


# ---------------------------------------------------------------------------
# OCR tier 3: Scaleway vision (Mistral Small 3.2)
# ---------------------------------------------------------------------------


async def _ocr_pdf_scaleway(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """OCR via Scaleway Generative API (Mistral Small 3.2 vision model).

    Uses a single aiohttp session and parallel requests for all pages.
    """
    import base64
    import io

    import aiohttp

    api_key = os.getenv("SCALEWAY_EMBED_API_KEY", "")
    if not api_key:
        logger.warning("[profession_indexer] SCALEWAY_EMBED_API_KEY not set, skipping Scaleway OCR")
        return []

    try:
        import fitz  # pymupdf
        from PIL import Image

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")

        # Render all pages to base64 PNGs first
        page_images: list[tuple[int, str]] = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            mat = fitz.Matrix(300 / 72, 300 / 72)  # 300 DPI
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")
            page_images.append((page_num + 1, img_b64))
        doc.close()

        # OCR all pages in parallel with a single session
        async def _ocr_page(
            session: aiohttp.ClientSession, page_num: int, img_b64: str
        ) -> tuple[int, str] | None:
            async with session.post(
                "https://api.scaleway.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mistral-small-3.2-24b-instruct-2506",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/png;base64,{img_b64}",
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": (
                                        "Extrais le texte complet de cette image de document. "
                                        "Retourne UNIQUEMENT le texte brut, sans commentaire, "
                                        "sans formatage markdown. Préserve la structure des paragraphes."
                                    ),
                                },
                            ],
                        }
                    ],
                    "max_tokens": 8192,
                    "temperature": 0.0,
                },
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(
                        f"[profession_indexer] Scaleway OCR page {page_num}: "
                        f"HTTP {resp.status} — {body[:200]}"
                    )
                    return None
                data = await resp.json()
                text = data["choices"][0]["message"]["content"]
                if text and text.strip():
                    return (page_num, text.strip())
                return None

        async with aiohttp.ClientSession() as session:
            results = await asyncio.gather(
                *[_ocr_page(session, pn, b64) for pn, b64 in page_images]
            )

        pages = sorted([r for r in results if r is not None], key=lambda x: x[0])
        logger.info(f"[profession_indexer] Scaleway OCR: {len(pages)} pages extracted (parallel)")
        return pages

    except Exception as e:
        logger.warning(f"[profession_indexer] Scaleway OCR failed: {e}")
        return []


# ---------------------------------------------------------------------------
# OCR tier 4: Gemini vision (existing)
# ---------------------------------------------------------------------------


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


# Directory where professions pipeline saves PDFs — project-local to survive
# macOS /tmp cleanup between pipeline runs.
_PDF_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "professions_pdfs"

# S3 Storage config (Scaleway Object Storage — public-read bucket)
env = os.getenv("ENV", "dev")
S3_PUBLIC_BUCKET = os.environ.get(
    "S3_PUBLIC_BUCKET", "chatvote-public-assets"
)
S3_PUBLIC_BASE_URL = os.environ.get(
    "S3_PUBLIC_BASE_URL",
    f"https://{S3_PUBLIC_BUCKET}.s3.fr-par.scw.cloud",
)
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
# S3 upload (Scaleway Object Storage — public-read bucket)
# ---------------------------------------------------------------------------

def _upload_to_s3(data: bytes, blob_path: str) -> str:
    """Upload PDF bytes to S3 public-assets bucket and return the public URL."""
    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT_URL", "https://s3.fr-par.scw.cloud"),
        aws_access_key_id=os.environ.get("S3_ACCESS_KEY", ""),
        aws_secret_access_key=os.environ.get("S3_SECRET_KEY", ""),
        region_name=os.environ.get("S3_REGION", "fr-par"),
    )
    s3.put_object(
        Bucket=S3_PUBLIC_BUCKET,
        Key=blob_path,
        Body=data,
        ContentType="application/pdf",
    )
    return f"{S3_PUBLIC_BASE_URL}/{blob_path}"


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
                page_type="profession_de_foi",
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
    2. Upload to S3 public-assets bucket
    3. Extract text, chunk, embed, store in Qdrant
    4. Update Firestore candidate doc with S3 public URL

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
        candidate = None  # incomplete Firestore doc (e.g. only manifesto_pdf_url field)
    if candidate is None:
        logger.warning(
            f"[profession_indexer] skipping {candidate_id} — "
            f"not fully seeded in Firestore (run seed pipeline first)"
        )
        return 0

    # Step 3: Upload to S3 (public-assets bucket)
    # Extract commune_code from candidate or candidate_id
    commune_code = candidate.municipality_code or (
        candidate_id.split("-")[1] if len(candidate_id.split("-")) >= 3 else "unknown"
    )
    blob_path = f"{STORAGE_PREFIX}/{commune_code}/{candidate_id}.pdf"

    # Always compute the expected S3 URL so Qdrant metadata has a URL
    # even when the upload fails (the PDF will be uploaded on retry).
    expected_url = f"{S3_PUBLIC_BASE_URL}/{blob_path}"

    try:
        storage_url = await asyncio.to_thread(
            _upload_to_s3, pdf_content, blob_path
        )
        logger.info(
            f"[profession_indexer] uploaded {candidate_id} to S3: {storage_url}"
        )
    except Exception as e:
        logger.warning(f"Failed to upload PDF to S3 for {candidate_id}: {e}")
        storage_url = expected_url  # use expected URL so metadata is never null

    # Step 4: Extract PDF text — 4-tier OCR cascade with content quality checks
    # Order: pypdf (free/fast) → Scaleway (cleanest OCR) → tesseract (free/local) → Gemini (last resort)
    ocr_method = "none"
    pages: list[tuple[int, str]] = []

    for tier_name, tier_fn in [
        ("pypdf", lambda: extract_pages_from_pdf(pdf_content)),
        ("scaleway", None),  # async — handled specially
        ("tesseract", lambda: _ocr_pdf_tesseract(pdf_content)),
        ("gemini", None),  # async — handled specially
    ]:
        if tier_name == "scaleway":
            pages = await _ocr_pdf_scaleway(pdf_content)
        elif tier_name == "gemini":
            pages = await _extract_pages_with_gemini(pdf_content)
        else:
            pages = tier_fn()

        total_chars = sum(len(t) for _, t in pages) if pages else 0

        if pages and total_chars > 200 and is_real_content(pages):
            ocr_method = tier_name
            logger.info(
                f"[profession_indexer] {tier_name}: {total_chars:,} chars from "
                f"{len(pages)} pages for {candidate_id} (real content)"
            )
            break
        else:
            reason = "metadata/noise" if total_chars > 200 else f"too little text ({total_chars} chars)"
            logger.info(f"[profession_indexer] {tier_name}: {reason} for {candidate_id}, trying next tier...")

    if not pages or ocr_method == "none":
        logger.warning(f"[profession_indexer] No text extracted for {candidate_id} after all OCR tiers — skipping")
        await _update_firestore_url(candidate_id, storage_url)
        return 0

    total_chars = sum(len(t) for _, t in pages)
    logger.info(
        f"[profession_indexer] extracted {total_chars:,} chars from "
        f"{len(pages)} pages for {candidate_id} (method={ocr_method})"
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
        from src.services.theme_classifier import classify_chunks, apply_themes_to_documents

        chunk_texts = [doc.page_content for doc in documents]
        classifications = await classify_chunks(chunk_texts, max_concurrent_llm=5)
        apply_themes_to_documents(documents, classifications)
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

    # Step 8: Update Firestore candidate doc with S3 URL
    await _update_firestore_url(candidate_id, storage_url)

    elapsed = _t.monotonic() - _t0
    logger.info(
        f"[profession_indexer] done {candidate_id}: "
        f"{len(documents)} chunks in {elapsed:.1f}s"
    )
    return len(documents)


async def _update_firestore_url(candidate_id: str, storage_url: str | None) -> None:
    """Update Firestore candidate doc with the S3 public URL.

    Skips the write when ``storage_url`` is None (upload failed) so we don't
    overwrite the original PDF URL that the populate node already stored.
    """
    if not storage_url:
        logger.debug(f"[profession_indexer] no storage URL for {candidate_id}, skipping Firestore update")
        return
    try:
        ref = async_db.collection("candidates").document(candidate_id)
        await ref.set(
            {
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

async def _download_pdf_from_url(url: str, dest: Path) -> bool:
    """Download a PDF from a URL to a local path. Returns True on success."""
    import aiohttp as _aiohttp

    try:
        timeout = _aiohttp.ClientTimeout(total=30)
        async with _aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    logger.warning(
                        f"[profession_indexer] download {url}: HTTP {resp.status}"
                    )
                    return False
                content = await resp.read()
                if not content[:4] == b"%PDF":
                    logger.warning(
                        f"[profession_indexer] download {url}: not a PDF"
                    )
                    return False
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                return True
    except Exception as e:
        logger.warning(f"[profession_indexer] download {url} failed: {e}")
        return False


async def _fetch_commune_pdfs_from_firestore(
    commune_code: str,
) -> list[tuple[str, Path]]:
    """Query Firestore for candidates with manifesto_pdf_url in a commune.

    Downloads each PDF to a temp cache dir. Returns [(candidate_id, local_path), ...].
    The professions pipeline node stores the ministry URL as manifesto_pdf_url
    for every candidate whose profession de foi PDF exists.
    """
    import tempfile

    try:
        # Fetch candidate docs by known ID pattern (cand-{commune_code}-{panneau})
        # to avoid needing a composite Firestore index.
        coll = async_db.collection("candidates")
        doc_refs = [coll.document(f"cand-{commune_code}-{p}") for p in range(1, 31)]
        fetched = await asyncio.gather(*[ref.get() for ref in doc_refs])
        candidates: list[tuple[str, str]] = []
        for snap in fetched:
            if snap.exists:
                data = snap.to_dict() or {}
                url = data.get("manifesto_pdf_url", "")
                if url and "programme-candidats.interieur.gouv.fr" in url:
                    candidates.append((snap.id, url))

        if not candidates:
            logger.info(
                f"[profession_indexer] no Firestore manifesto URLs for commune {commune_code}"
            )
            return []

        logger.info(
            f"[profession_indexer] found {len(candidates)} manifesto URLs in Firestore "
            f"for commune {commune_code}, downloading..."
        )

        tmp_dir = Path(tempfile.gettempdir()) / "profession_pdfs" / commune_code
        results: list[tuple[str, Path]] = []
        for cand_id, url in candidates:
            filename = url.rsplit("/", 1)[-1]  # e.g. 1-75056-5.pdf
            dest = tmp_dir / filename
            if dest.exists() and dest.stat().st_size > 0:
                results.append((cand_id, dest))
            elif await _download_pdf_from_url(url, dest):
                results.append((cand_id, dest))
            else:
                logger.warning(
                    f"[profession_indexer] could not download PDF for {cand_id}: {url}"
                )

        return results

    except Exception as e:
        logger.error(
            f"[profession_indexer] Firestore lookup failed for commune {commune_code}: {e}"
        )
        return []


async def index_commune_professions(commune_code: str) -> dict[str, int]:
    """Index all profession de foi PDFs for a commune.

    Tries local cache first (_PDF_CACHE_DIR/{commune_code}/*.pdf).
    Falls back to downloading PDFs from the ministry URLs stored in
    Firestore by the professions pipeline node — this allows K8s Jobs
    to index professions without needing a local PDF cache.

    Args:
        commune_code: INSEE commune code, e.g. "75056"

    Returns:
        {candidate_id: chunk_count} for each PDF found.
    """
    # --- Strategy 1: local cache (fast, in-process pipeline) ---
    commune_dir = _PDF_CACHE_DIR / commune_code
    pdf_files = list(commune_dir.glob("*.pdf")) if commune_dir.exists() else []

    if pdf_files:
        logger.info(
            f"[profession_indexer] found {len(pdf_files)} PDFs in local cache "
            f"for commune {commune_code}"
        )
        results: dict[str, int] = {}
        for pdf_path in pdf_files:
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

    # --- Strategy 2: download from Firestore manifesto URLs (K8s Jobs) ---
    logger.info(
        f"[profession_indexer] no local cache for commune {commune_code}, "
        f"falling back to Firestore manifesto URLs"
    )
    downloaded = await _fetch_commune_pdfs_from_firestore(commune_code)
    if not downloaded:
        logger.info(
            f"[profession_indexer] no PDFs available for commune {commune_code}"
        )
        return {}

    results = {}
    for candidate_id, pdf_path in downloaded:
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
        description="Index profession de foi PDFs into Qdrant and S3"
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
