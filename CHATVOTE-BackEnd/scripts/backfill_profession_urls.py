"""Backfill metadata.url for profession_de_foi chunks in Qdrant.

Scrolls all points in candidates_websites_prod where:
  - metadata.source_document == "profession_de_foi"
  - metadata.url is null/missing

Constructs the S3 URL from metadata:
  https://chatvote-public-assets.s3.fr-par.scw.cloud/public/professions_de_foi/{municipality_code}/{candidate_id}.pdf

Usage:
    poetry run python scripts/backfill_profession_urls.py --dry-run   # Preview
    poetry run python scripts/backfill_profession_urls.py             # Apply
    poetry run python scripts/backfill_profession_urls.py --namespace cand-75056-8  # Single candidate
"""

import argparse
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

S3_BASE_URL = "https://chatvote-public-assets.s3.fr-par.scw.cloud/public/professions_de_foi"
SCROLL_BATCH = 500
UPDATE_BATCH = 100


def _qdrant_post(qdrant_url: str, api_key: str, path: str, body: dict) -> dict:
    url = f"{qdrant_url.rstrip('/')}{path}"
    headers = {"Content-Type": "application/json", "api-key": api_key}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=60)
    return json.loads(resp.read())


def scroll_profession_chunks_missing_url(
    qdrant_url: str,
    api_key: str,
    collection: str,
    namespace_filter: str | None = None,
) -> list[dict]:
    """Scroll all profession_de_foi points that have no url in metadata."""
    points: list[dict] = []
    offset = None

    must_conditions: list[dict] = [
        {
            "key": "metadata.source_document",
            "match": {"value": "profession_de_foi"},
        },
        # Points where url key is absent or null (is_empty matches both)
        {
            "is_empty": {"key": "metadata.url"},
        },
    ]

    if namespace_filter:
        must_conditions.append(
            {"key": "metadata.namespace", "match": {"value": namespace_filter}}
        )

    while True:
        body: dict = {
            "limit": SCROLL_BATCH,
            "with_payload": ["metadata"],
            "with_vector": False,
            "filter": {"must": must_conditions},
        }
        if offset is not None:
            body["offset"] = offset

        data = _qdrant_post(
            qdrant_url, api_key, f"/collections/{collection}/points/scroll", body
        )
        batch = data["result"]["points"]
        next_offset = data["result"].get("next_page_offset")

        for p in batch:
            meta = p["payload"].get("metadata", {})
            # Double-check: skip if url already present and non-empty
            existing_url = meta.get("url")
            if existing_url:
                continue
            points.append({"id": p["id"], "metadata": meta})

        logger.info(f"Scrolled {len(points)} qualifying points so far...")

        if not next_offset:
            break
        offset = next_offset

    logger.info(f"Total profession_de_foi points missing url: {len(points)}")
    return points


def build_s3_url(municipality_code: str, candidate_id: str) -> str:
    return f"{S3_BASE_URL}/{municipality_code}/{candidate_id}.pdf"


def batch_update_profession_urls(
    qdrant_url: str,
    api_key: str,
    collection: str,
    points: list[dict],
    dry_run: bool,
) -> tuple[int, int]:
    """Set metadata.url for each point. Returns (updated, skipped)."""
    updated = 0
    skipped = 0
    to_update: list[tuple[str | int, dict]] = []

    for p in points:
        meta = p["metadata"]
        municipality_code = meta.get("municipality_code")
        candidate_id = meta.get("namespace")

        if not municipality_code or not candidate_id:
            logger.warning(
                f"[{p['id']}] Missing municipality_code or namespace — skipping "
                f"(municipality_code={municipality_code!r}, namespace={candidate_id!r})"
            )
            skipped += 1
            continue

        s3_url = build_s3_url(municipality_code, candidate_id)
        to_update.append((p["id"], {**meta, "url": s3_url}))
        updated += 1

        if dry_run:
            logger.info(f"  [DRY RUN] {p['id']} → {s3_url}")

    if dry_run:
        logger.info(f"[DRY RUN] Would update {updated} points, skip {skipped}")
        return updated, skipped

    if not to_update:
        return updated, skipped

    # Apply in batches of UPDATE_BATCH
    for batch_start in range(0, len(to_update), UPDATE_BATCH):
        batch = to_update[batch_start : batch_start + UPDATE_BATCH]

        # Use set_payload per point-id batch — group by same new metadata where possible
        # For simplicity, one set_payload call per point to avoid partial overwrites
        # Qdrant supports a single set_payload with a points filter list
        # Build one call per unique URL (grouped by municipality+candidate)
        by_url: dict[str, list] = {}
        for point_id, new_meta in batch:
            url = new_meta["url"]
            by_url.setdefault(url, []).append((point_id, new_meta))

        for url, items in by_url.items():
            # All items with the same URL share the same metadata structure
            # (same municipality_code + candidate_id), so we can batch them
            point_ids = [item[0] for item in items]
            new_meta = items[0][1]

            body = {
                "payload": {"metadata": new_meta},
                "points": point_ids,
            }
            _qdrant_post(
                qdrant_url,
                api_key,
                f"/collections/{collection}/points/payload",
                body,
            )

        logger.info(
            f"Updated batch {batch_start + 1}–{batch_start + len(batch)} / {len(to_update)}"
        )

    return updated, skipped


def verify_sample(
    qdrant_url: str,
    api_key: str,
    collection: str,
    points: list[dict],
    sample_size: int = 5,
) -> None:
    """Re-fetch a sample of updated points and verify url is set."""
    if not points:
        return

    sample = points[:sample_size]
    sample_ids = [p["id"] for p in sample]

    body = {
        "ids": sample_ids,
        "with_payload": ["metadata"],
        "with_vector": False,
    }
    data = _qdrant_post(
        qdrant_url, api_key, f"/collections/{collection}/points", body
    )
    fetched = data.get("result", [])

    print(f"\n{'=' * 60}")
    print(f"Verification sample ({len(fetched)} points)")
    print(f"{'=' * 60}")
    all_ok = True
    for p in fetched:
        meta = p["payload"].get("metadata", {})
        url = meta.get("url")
        candidate_id = meta.get("namespace", "?")
        municipality = meta.get("municipality_code", "?")
        status = "OK" if url else "MISSING"
        if not url:
            all_ok = False
        print(f"  [{status}] {candidate_id} / {municipality} → {url or '(none)'}")

    if all_ok:
        print("\nAll sampled points have url set correctly.")
    else:
        print("\nWARNING: Some points still missing url after update!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill metadata.url for profession_de_foi chunks in Qdrant"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be updated without writing",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default=None,
        help="Restrict to a single candidate namespace (e.g. cand-75056-8)",
    )
    parser.add_argument(
        "--qdrant-url",
        default=os.getenv("QDRANT_URL", "http://212.47.245.238:6333"),
        help="Qdrant base URL",
    )
    parser.add_argument(
        "--qdrant-api-key",
        default=os.getenv(
            "QDRANT_API_KEY",
            "7384d5cc296a254996640081df3a08f824a2f999bb1fb98d91929d811ddc22cb",
        ),
        help="Qdrant API key",
    )
    parser.add_argument(
        "--collection",
        default="candidates_websites_prod",
        help="Qdrant collection name",
    )
    args = parser.parse_args()

    mode = "DRY RUN" if args.dry_run else "LIVE"
    logger.info(f"Starting profession URL backfill [{mode}]")
    logger.info(f"Qdrant: {args.qdrant_url} / collection: {args.collection}")

    # Step 1: Scroll qualifying points
    points = scroll_profession_chunks_missing_url(
        args.qdrant_url,
        args.qdrant_api_key,
        args.collection,
        args.namespace,
    )

    if not points:
        logger.info("No profession_de_foi points missing url — nothing to do.")
        return

    # Step 2: Preview sample in dry-run
    if args.dry_run:
        print(f"\nFirst 10 points that would be updated:")
        for p in points[:10]:
            meta = p["metadata"]
            mc = meta.get("municipality_code", "?")
            cid = meta.get("namespace", "?")
            print(f"  id={p['id']}  candidate={cid}  municipality={mc}  → {build_s3_url(mc, cid)}")

    # Step 3: Apply (or preview) updates
    updated, skipped = batch_update_profession_urls(
        args.qdrant_url,
        args.qdrant_api_key,
        args.collection,
        points,
        dry_run=args.dry_run,
    )

    # Step 4: Verify sample (only after real run)
    if not args.dry_run and updated > 0:
        updated_points = [
            p for p in points
            if p["metadata"].get("municipality_code") and p["metadata"].get("namespace")
        ]
        verify_sample(args.qdrant_url, args.qdrant_api_key, args.collection, updated_points)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Profession URL Backfill Summary ({mode})")
    print(f"{'=' * 60}")
    print(f"Points scanned:   {len(points):,}")
    print(f"Updated:          {updated:,}")
    print(f"Skipped (bad meta): {skipped:,}")
    if args.dry_run:
        print("\nRe-run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
