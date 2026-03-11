#!/usr/bin/env python3
"""
Migrate candidate website data from local dev Qdrant to prod Qdrant.

Copies all points from candidates_websites_dev to candidates_websites_prod,
skipping namespaces that already exist in prod to avoid duplicates.

Usage:
    python3 scripts/migrate_dev_to_prod_qdrant.py [--dry-run] [--include-overlap]
"""

import logging
import sys

from qdrant_client import QdrantClient, models

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DEV_URL = "http://localhost:6333"
PROD_URL = "https://chatvoteoan3waxf-qdrant-prod.functions.fnc.fr-par.scw.cloud"
DEV_COLLECTION = "candidates_websites_dev"
PROD_COLLECTION = "candidates_websites_prod"
BATCH_SIZE = 20  # Small batches — 3072-dim vectors are large over HTTP


def get_namespaces(client: QdrantClient, collection: str, exclude_prefix: str | None = None) -> dict[str, int]:
    """Get all namespaces and their point counts."""
    ns_counts: dict[str, int] = {}
    offset = None
    while True:
        results, offset = client.scroll(
            collection_name=collection, limit=100, offset=offset,
            with_payload=True, with_vectors=False,
        )
        for p in results:
            ns = p.payload.get("metadata", {}).get("namespace", "")
            if exclude_prefix and ns.startswith(exclude_prefix):
                continue
            ns_counts[ns] = ns_counts.get(ns, 0) + 1
        if not results or offset is None:
            break
    return ns_counts


def migrate_namespace(dev: QdrantClient, prod: QdrantClient, namespace: str, dry_run: bool = False) -> int:
    """Migrate all points for a namespace from dev to prod. Returns count."""
    offset = None
    total = 0
    while True:
        results, offset = dev.scroll(
            collection_name=DEV_COLLECTION, limit=BATCH_SIZE, offset=offset,
            with_payload=True, with_vectors=True,
            scroll_filter=models.Filter(must=[
                models.FieldCondition(
                    key="metadata.namespace",
                    match=models.MatchValue(value=namespace),
                )
            ]),
        )
        if not results:
            break

        if not dry_run:
            points = []
            for p in results:
                # Extract the dense vector
                vector = p.vector
                if isinstance(vector, dict):
                    vector = vector.get("dense", vector)
                points.append(models.PointStruct(
                    id=p.id,
                    vector={"dense": vector} if not isinstance(vector, dict) else vector,
                    payload=p.payload,
                ))
            prod.upsert(collection_name=PROD_COLLECTION, points=points)

        total += len(results)
        if offset is None:
            break

    return total


def main():
    dry_run = "--dry-run" in sys.argv
    include_overlap = "--include-overlap" in sys.argv

    dev = QdrantClient(url=DEV_URL)
    prod = QdrantClient(url=PROD_URL, prefer_grpc=False, https=True, port=443, timeout=120)

    logger.info("Collecting dev namespaces...")
    dev_ns = get_namespaces(dev, DEV_COLLECTION)
    logger.info(f"Dev: {len(dev_ns)} namespaces, {sum(dev_ns.values())} points")

    logger.info("Collecting prod namespaces (non-poster)...")
    prod_ns = get_namespaces(prod, PROD_COLLECTION, exclude_prefix="poster_")
    logger.info(f"Prod: {len(prod_ns)} namespaces, {sum(prod_ns.values())} points")

    overlap = set(dev_ns) & set(prod_ns)
    to_migrate = set(dev_ns) - set(prod_ns) if not include_overlap else set(dev_ns)
    skip = overlap if not include_overlap else set()

    logger.info(f"Overlap: {len(overlap)} namespaces")
    if skip:
        logger.info(f"Skipping: {sorted(skip)}")
    logger.info(f"To migrate: {len(to_migrate)} namespaces, ~{sum(dev_ns[ns] for ns in to_migrate)} points")

    if dry_run:
        logger.info("[DRY RUN] Would migrate the above. Exiting.")
        return

    migrated_ns = 0
    migrated_pts = 0
    failed_ns = []
    for i, ns in enumerate(sorted(to_migrate), 1):
        try:
            count = migrate_namespace(dev, prod, ns, dry_run=dry_run)
            migrated_ns += 1
            migrated_pts += count
        except Exception as e:
            logger.error(f"Failed {ns}: {e}")
            failed_ns.append(ns)
        if i % 10 == 0 or i == len(to_migrate):
            logger.info(f"Progress: {i}/{len(to_migrate)} namespaces, {migrated_pts} points migrated")

    if failed_ns:
        logger.warning(f"Failed namespaces ({len(failed_ns)}): {failed_ns}")
    logger.info(f"\nDone! Migrated {migrated_ns} namespaces, {migrated_pts} points, {len(failed_ns)} failed")


if __name__ == "__main__":
    main()
