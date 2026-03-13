#!/usr/bin/env python3
"""
Upload election poster PDFs to Firebase Storage and update Qdrant URLs.

Finds all Qdrant points with programme-candidats.interieur.gouv.fr URLs,
downloads the PDFs, uploads to Firebase Storage (dev bucket), and updates
the metadata URL so the frontend PDF viewer can proxy them.

Usage:
    GOOGLE_APPLICATION_CREDENTIALS=~/Downloads/chat-vote-dev-firebase-adminsdk-fbsvc-*.json \
    python3 scripts/upload_poster_pdfs_to_storage.py [--dry-run]
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

import firebase_admin
from firebase_admin import credentials, storage
from qdrant_client import QdrantClient, models
import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Config
QDRANT_URL = os.environ.get("QDRANT_URL", "https://chatvoteoan3waxf-qdrant-prod.functions.fnc.fr-par.scw.cloud")
COLLECTION = "candidates_websites_prod"
EXTERNAL_DOMAIN = "programme-candidats.interieur.gouv.fr"
# Firebase Storage bucket — env-aware
BUCKET_NAME = os.getenv("FIREBASE_STORAGE_BUCKET", f"chat-vote-{os.getenv('ENV', 'dev')}.firebasestorage.app")
STORAGE_PREFIX = "public/posters"  # e.g. public/posters/37261/panneau_1.pdf
DOWNLOAD_SEMAPHORE = asyncio.Semaphore(20)  # max concurrent downloads


def init_firebase():
    cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not cred_path:
        logger.error("Set GOOGLE_APPLICATION_CREDENTIALS to dev Firebase Admin SDK JSON")
        sys.exit(1)

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {"storageBucket": BUCKET_NAME})
    logger.info(f"Firebase initialized, bucket: {BUCKET_NAME}")


def get_qdrant_client():
    return QdrantClient(url=QDRANT_URL, prefer_grpc=False, https=True, port=443)


def find_external_url_points(client: QdrantClient) -> list:
    """Find all points with external programme-candidats URLs."""
    all_points = []
    offset = None
    while True:
        results, offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(must=[
                models.FieldCondition(
                    key="metadata.url",
                    match=models.MatchText(text=EXTERNAL_DOMAIN),
                )
            ]),
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(results)
        if not results or offset is None:
            break
    return all_points


async def download_pdf(http_client: httpx.AsyncClient, url: str) -> bytes | None:
    """Download a PDF from external URL."""
    async with DOWNLOAD_SEMAPHORE:
        try:
            resp = await http_client.get(url, follow_redirects=True)
            if resp.status_code == 200:
                return resp.content
            logger.warning(f"HTTP {resp.status_code} for {url}")
            return None
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return None


def upload_to_storage(data: bytes, blob_path: str) -> str:
    """Upload PDF to Firebase Storage and return download URL.

    Uses Firebase Storage download URL format (with token) since the bucket
    has uniform bucket-level access enabled (no legacy ACLs).
    """
    bucket = storage.bucket()
    blob = bucket.blob(blob_path)
    blob.metadata = {"firebaseStorageDownloadTokens": blob_path.replace("/", "_")}
    blob.upload_from_string(data, content_type="application/pdf")
    token = blob.metadata["firebaseStorageDownloadTokens"]
    return (
        f"https://firebasestorage.googleapis.com/v0/b/{BUCKET_NAME}"
        f"/o/{blob_path.replace('/', '%2F')}?alt=media&token={token}"
    )


def get_storage_path(url: str, metadata: dict) -> str:
    """Generate Firebase Storage path from metadata.

    e.g. public/posters/37261/panneau_1.pdf
    """
    commune_code = metadata.get("municipality_code", "unknown")
    namespace = metadata.get("namespace", "")
    # namespace format: poster_37261_1 -> panneau_1
    panneau = namespace.split("_")[-1] if namespace else "unknown"
    return f"{STORAGE_PREFIX}/{commune_code}/panneau_{panneau}.pdf"


async def main():
    dry_run = "--dry-run" in sys.argv

    init_firebase()
    client = get_qdrant_client()

    logger.info("Finding points with external URLs...")
    points = find_external_url_points(client)
    logger.info(f"Found {len(points)} points with {EXTERNAL_DOMAIN} URLs")

    if not points:
        logger.info("Nothing to do!")
        return

    # Group by URL to avoid downloading the same PDF multiple times
    url_to_points: dict[str, list] = {}
    for point in points:
        url = point.payload.get("metadata", {}).get("url", "")
        if EXTERNAL_DOMAIN in url:
            url_to_points.setdefault(url, []).append(point)

    logger.info(f"Unique PDFs to upload: {len(url_to_points)}")

    uploaded = 0
    updated = 0
    failed = 0

    async def process_one(http_client: httpx.AsyncClient, url: str, point_group: list) -> tuple[int, int, int]:
        """Download one PDF, upload to Storage, update Qdrant points. Returns (uploaded, updated, failed)."""
        metadata = point_group[0].payload.get("metadata", {})
        blob_path = get_storage_path(url, metadata)
        party_name = metadata.get("party_name", "?")
        commune = metadata.get("municipality_name", "?")

        if dry_run:
            logger.info(f"[DRY RUN] Would upload {url} -> {blob_path} ({len(point_group)} points)")
            return 0, 0, 0

        # Download
        data = await download_pdf(http_client, url)
        if not data:
            logger.error(f"Failed to download: {url}")
            return 0, 0, 1

        # Upload to Firebase Storage
        try:
            storage_url = upload_to_storage(data, blob_path)
            logger.info(f"[UPLOADED] {commune} / {party_name} -> {storage_url}")
        except Exception as e:
            logger.error(f"Failed to upload {blob_path}: {e}")
            return 0, 0, 1

        # Update all Qdrant points with this URL
        pt_updated = 0
        for point in point_group:
            point_metadata = point.payload.get("metadata", {})
            point_metadata["url"] = storage_url
            client.set_payload(
                collection_name=COLLECTION,
                payload={"metadata": point_metadata},
                points=[point.id],
            )
            pt_updated += 1

        return 1, pt_updated, 0

    async with httpx.AsyncClient(timeout=30) as http_client:
        tasks = [
            process_one(http_client, url, point_group)
            for url, point_group in sorted(url_to_points.items())
        ]
        results = await asyncio.gather(*tasks)

    for u, p, f in results:
        uploaded += u
        updated += p
        failed += f

    logger.info(f"\nDone! Uploaded: {uploaded}, Points updated: {updated}, Failed: {failed}")


if __name__ == "__main__":
    asyncio.run(main())
