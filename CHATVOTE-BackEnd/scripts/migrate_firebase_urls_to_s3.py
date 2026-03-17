"""Migrate Qdrant metadata URLs from Firebase Storage to S3 (one-time patch).

Rewrites `metadata.url` for all points in `candidates_websites_prod` that
still reference `firebasestorage.googleapis.com`, converting them to the
equivalent path on the `chatvote-public-assets` S3 bucket.

Firebase URL pattern:
  https://firebasestorage.googleapis.com/v0/b/<bucket>/o/public%2Fprofessions_de_foi%2F<commune>%2F<candidate>.pdf?alt=media&token=...

S3 URL pattern:
  https://chatvote-public-assets.s3.fr-par.scw.cloud/public/professions_de_foi/<commune>/<candidate>.pdf

Usage:
  # Dry run (default)
  poetry run python scripts/migrate_firebase_urls_to_s3.py

  # Actually apply changes
  poetry run python scripts/migrate_firebase_urls_to_s3.py --apply

Env vars:
  QDRANT_URL      - Qdrant endpoint
  QDRANT_API_KEY  - Qdrant API key
"""

import argparse
import logging
import os
import re
import sys
from urllib.parse import unquote

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchText,
    SetPayloadOperation,
    PointIdsList,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("migrate-urls")

S3_BASE = "https://chatvote-public-assets.s3.fr-par.scw.cloud"
COLLECTION = "candidates_websites_prod"
BATCH_SIZE = 100

# Matches the /o/<path>?alt=media part of a Firebase Storage URL
_FIREBASE_PATH_RE = re.compile(r"/o/(.+?)\?alt=media")


def firebase_url_to_s3(url: str) -> str | None:
    """Convert a Firebase Storage URL to the equivalent S3 public URL."""
    m = _FIREBASE_PATH_RE.search(url)
    if not m:
        return None
    # The path is URL-encoded (%2F → /)
    path = unquote(m.group(1))
    return f"{S3_BASE}/{path}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write changes")
    args = parser.parse_args()

    qdrant_url = os.environ.get("QDRANT_URL", "")
    api_key = os.environ.get("QDRANT_API_KEY", "")
    if not qdrant_url:
        log.error("QDRANT_URL not set")
        sys.exit(1)

    # Detect HTTPS endpoints (Scaleway managed) vs HTTP (K8s internal / local)
    use_https = qdrant_url.startswith("https://")
    client = QdrantClient(
        url=qdrant_url,
        api_key=api_key,
        timeout=120,
        prefer_grpc=False,
        https=use_https,
        **({"port": 443} if use_https else {}),
    )

    fb_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.url",
                match=MatchText(text="firebasestorage"),
            )
        ]
    )

    # Scroll through all matching points
    total = 0
    converted = 0
    failed = 0
    offset = None

    while True:
        points, offset = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=fb_filter,
            limit=BATCH_SIZE,
            with_payload=True,
            offset=offset,
        )

        if not points:
            break

        ids_to_update: list[tuple] = []  # (point_id, new_url)

        for p in points:
            total += 1
            old_url = p.payload.get("metadata", {}).get("url", "")
            new_url = firebase_url_to_s3(old_url)

            if new_url:
                ids_to_update.append((p.id, new_url))
                if total <= 5:
                    log.info("Sample: %s → %s", old_url[:80], new_url[:80])
            else:
                failed += 1
                log.warning("Could not convert: %s", old_url[:120])

        if args.apply and ids_to_update:
            # Update in sub-batches
            for point_id, new_url in ids_to_update:
                client.set_payload(
                    collection_name=COLLECTION,
                    payload={"metadata": {"url": new_url}},
                    points=[point_id],
                )
                converted += 1

            log.info("Updated %d points (total so far: %d)", len(ids_to_update), converted)
        else:
            converted += len(ids_to_update)

        if offset is None:
            break

    mode = "APPLIED" if args.apply else "DRY RUN"
    log.info(
        "[%s] Done. Total scanned: %d, convertible: %d, failed: %d",
        mode, total, converted, failed,
    )


if __name__ == "__main__":
    main()
