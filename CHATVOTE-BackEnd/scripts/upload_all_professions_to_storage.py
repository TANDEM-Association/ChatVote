#!/usr/bin/env python3
"""Upload all cached profession de foi PDFs to Firebase Storage and update Firestore URLs.

This decouples the Firebase Storage upload from the full indexing pipeline,
so ALL candidates get viewable URLs even if they're not fully seeded.

Usage:
    cd CHATVOTE-BackEnd
    poetry run python scripts/upload_all_professions_to_storage.py
"""

import asyncio
import logging
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PDF_CACHE_DIR = Path(tempfile.gettempdir()) / "chatvote_professions_pdfs"
PDF_FILENAME_RE = re.compile(r"^1-(\d+)-(\d+)\.pdf$")

BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET", f"chat-vote-{os.getenv('ENV', 'dev')}.firebasestorage.app")
STORAGE_PREFIX = "public/professions_de_foi"


def _upload_to_storage(data: bytes, blob_path: str) -> str:
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


async def main():
    from src.firebase_service import async_db

    if not PDF_CACHE_DIR.exists():
        logger.error(f"PDF cache dir not found: {PDF_CACHE_DIR}")
        return

    # Collect all PDFs
    pdfs: list[tuple[str, str, Path]] = []  # (candidate_id, commune_code, path)
    for commune_dir in sorted(PDF_CACHE_DIR.iterdir()):
        if not commune_dir.is_dir():
            continue
        commune_code = commune_dir.name
        for pdf_file in sorted(commune_dir.iterdir()):
            m = PDF_FILENAME_RE.match(pdf_file.name)
            if not m or pdf_file.stat().st_size < 100:
                continue
            panneau = m.group(2)
            candidate_id = f"cand-{commune_code}-{panneau}"
            pdfs.append((candidate_id, commune_code, pdf_file))

    logger.info(f"Found {len(pdfs)} PDFs across {len(set(p[1] for p in pdfs))} communes")

    # Check which already have Firebase Storage URLs
    already_uploaded = 0
    to_upload: list[tuple[str, str, Path]] = []

    for candidate_id, commune_code, pdf_path in pdfs:
        doc = await async_db.collection("candidates").document(candidate_id).get()
        if doc.exists:
            url = doc.to_dict().get("manifesto_pdf_url", "")
            if "firebasestorage.googleapis.com" in url:
                already_uploaded += 1
                continue
        to_upload.append((candidate_id, commune_code, pdf_path))

    logger.info(
        f"Already on Firebase Storage: {already_uploaded}, "
        f"to upload: {len(to_upload)}"
    )

    # Upload and update Firestore
    uploaded = 0
    errors = 0
    for i, (candidate_id, commune_code, pdf_path) in enumerate(to_upload):
        try:
            pdf_data = pdf_path.read_bytes()
            blob_path = f"{STORAGE_PREFIX}/{commune_code}/{candidate_id}.pdf"
            storage_url = _upload_to_storage(pdf_data, blob_path)

            # Update Firestore — merge to preserve existing fields
            await async_db.collection("candidates").document(candidate_id).set(
                {"manifesto_pdf_url": storage_url, "has_manifesto": True},
                merge=True,
            )
            uploaded += 1

            if (i + 1) % 25 == 0:
                logger.info(f"  Progress: {i + 1}/{len(to_upload)} uploaded")

        except Exception as e:
            logger.error(f"  {candidate_id}: {e}")
            errors += 1

    logger.info(
        f"\n=== Done ===\n"
        f"Already on Firebase Storage: {already_uploaded}\n"
        f"Newly uploaded: {uploaded}\n"
        f"Errors: {errors}\n"
        f"Total with Firebase Storage URLs: {already_uploaded + uploaded}"
    )


if __name__ == "__main__":
    asyncio.run(main())
