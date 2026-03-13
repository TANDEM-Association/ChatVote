"""Qdrant daily snapshot → Scaleway Object Storage (S3-compatible).

Runs as a K8s CronJob at 3 AM Paris time, before the indexer at 4 AM.
Creates a snapshot for each collection, uploads to S3, and cleans up
snapshots older than 7 days.

Required env vars:
  QDRANT_URL          - e.g. http://qdrant-internal.chatvote.svc.cluster.local:6333
  QDRANT_API_KEY      - Qdrant service API key
  S3_ENDPOINT_URL     - e.g. https://s3.fr-par.scw.cloud
  S3_BUCKET           - e.g. chatvote-qdrant-snapshots
  S3_ACCESS_KEY       - Scaleway access key
  S3_SECRET_KEY       - Scaleway secret key
  S3_REGION           - e.g. fr-par (default)
"""

import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import boto3
import urllib3
from qdrant_client import QdrantClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("qdrant-snapshot")

# Suppress noisy urllib3 warnings when not using TLS
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_env(key: str, default: str | None = None) -> str:
    val = os.environ.get(key, default)
    if val is None:
        log.error("Missing required env var: %s", key)
        sys.exit(1)
    return val


def create_s3_client() -> "boto3.client":
    return boto3.client(
        "s3",
        endpoint_url=get_env("S3_ENDPOINT_URL"),
        aws_access_key_id=get_env("S3_ACCESS_KEY"),
        aws_secret_access_key=get_env("S3_SECRET_KEY"),
        region_name=get_env("S3_REGION", "fr-par"),
    )


def create_qdrant_client() -> QdrantClient:
    url = get_env("QDRANT_URL")
    api_key = get_env("QDRANT_API_KEY")
    return QdrantClient(url=url, api_key=api_key, timeout=300)


def snapshot_and_upload(
    qdrant: QdrantClient,
    s3: "boto3.client",
    bucket: str,
    collection_name: str,
    date_prefix: str,
) -> bool:
    """Create snapshot, download, upload to S3, delete local copy."""
    log.info("Creating snapshot for collection: %s", collection_name)

    # Create snapshot on Qdrant server
    snapshot_info = qdrant.create_snapshot(collection_name=collection_name)
    snapshot_name = snapshot_info.name
    log.info("Snapshot created: %s", snapshot_name)

    # Download snapshot to temp file
    with tempfile.NamedTemporaryFile(suffix=".snapshot", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        qdrant_url = get_env("QDRANT_URL").rstrip("/")
        api_key = get_env("QDRANT_API_KEY")
        snapshot_url = (
            f"{qdrant_url}/collections/{collection_name}"
            f"/snapshots/{snapshot_name}"
        )

        # Download via urllib3 (qdrant-client's download_snapshot can be flaky)
        http = urllib3.PoolManager()
        resp = http.request(
            "GET",
            snapshot_url,
            headers={"api-key": api_key},
            preload_content=False,
        )

        with open(tmp_path, "wb") as f:
            for chunk in resp.stream(65536):
                f.write(chunk)
        resp.release_conn()

        file_size = os.path.getsize(tmp_path)
        log.info("Downloaded snapshot: %.1f MB", file_size / 1024 / 1024)

        # Upload to S3
        s3_key = f"{date_prefix}/{collection_name}/{snapshot_name}"
        s3.upload_file(tmp_path, bucket, s3_key)
        log.info("Uploaded to s3://%s/%s", bucket, s3_key)

        # Delete snapshot from Qdrant server (save disk)
        qdrant.delete_snapshot(
            collection_name=collection_name, snapshot_name=snapshot_name
        )
        log.info("Deleted server-side snapshot: %s", snapshot_name)

        return True

    except Exception:
        log.exception("Failed snapshot for %s", collection_name)
        return False
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def cleanup_old_snapshots(s3: "boto3.client", bucket: str, days: int = 7) -> None:
    """Delete S3 objects older than `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    log.info("Cleaning up snapshots older than %s", cutoff.date())

    paginator = s3.get_paginator("list_objects_v2")
    to_delete = []

    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            if obj["LastModified"] < cutoff:
                to_delete.append({"Key": obj["Key"]})

    if not to_delete:
        log.info("No old snapshots to clean up")
        return

    # Delete in batches of 1000 (S3 limit)
    for i in range(0, len(to_delete), 1000):
        batch = to_delete[i : i + 1000]
        s3.delete_objects(Bucket=bucket, Delete={"Objects": batch})

    log.info("Deleted %d old snapshot files", len(to_delete))


def main() -> None:
    log.info("Starting Qdrant snapshot job")

    qdrant = create_qdrant_client()
    s3 = create_s3_client()
    bucket = get_env("S3_BUCKET", "chatvote-qdrant-snapshots")
    date_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # List all collections
    collections = qdrant.get_collections().collections
    collection_names = [c.name for c in collections]
    log.info("Found %d collections: %s", len(collection_names), collection_names)

    # Snapshot each collection
    results = {}
    for name in collection_names:
        results[name] = snapshot_and_upload(qdrant, s3, bucket, name, date_prefix)

    # Clean up old snapshots
    cleanup_old_snapshots(s3, bucket)

    # Summary
    succeeded = sum(1 for v in results.values() if v)
    failed = sum(1 for v in results.values() if not v)
    log.info(
        "Snapshot job complete: %d/%d succeeded, %d failed",
        succeeded,
        len(results),
        failed,
    )

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
