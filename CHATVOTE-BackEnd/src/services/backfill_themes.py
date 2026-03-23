# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Backfill theme + sub_theme for existing Qdrant points that are missing them.

Usage:
    poetry run python -m src.services.backfill_themes [--collection candidates|manifestos|all]
                                                       [--batch-size 50]
                                                       [--max-concurrent-llm 5]
                                                       [--dry-run]

Examples:
    # Backfill both collections (default)
    poetry run python -m src.services.backfill_themes

    # Dry-run: classify but don't write to Qdrant
    poetry run python -m src.services.backfill_themes --dry-run

    # Only candidates, larger batches
    poetry run python -m src.services.backfill_themes --collection candidates --batch-size 100
"""

import argparse
import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import SetPayloadOperation, SetPayload

from src.services.theme_classifier import classify_chunks, ThemeResult

logger = logging.getLogger(__name__)

# Default collection names (without env suffix)
_DEFAULT_CANDIDATES = "candidates_websites"
_DEFAULT_PARTIES = "all_parties"

# Module-level client holder — set by main() before any work happens
_state: dict[str, Any] = {}


def _get_client() -> QdrantClient:
    return _state["qdrant_client"]


def _make_qdrant_client(url: str) -> QdrantClient:
    """Create a standalone QdrantClient without importing the full app stack."""
    force_rest = url.startswith("https://")
    return QdrantClient(
        url=url,
        api_key=os.getenv("QDRANT_API_KEY"),
        prefer_grpc=False,
        https=force_rest,
        port=443 if force_rest else 6333,
        timeout=30,
        check_compatibility=False,
    )


def _resolve_collection_name(base: str, env: str) -> str:
    """Compute collection name with env suffix."""
    suffix = f"_{env}" if env in ("prod", "dev") else "_dev"
    return f"{base}{suffix}"


# ---------------------------------------------------------------------------
# Stats dataclass
# ---------------------------------------------------------------------------

@dataclass
class BackfillStats:
    collection: str
    total_points: int = 0
    already_had_theme: int = 0
    processed: int = 0
    classified: int = 0
    no_theme: int = 0
    errors: int = 0
    skipped_empty: int = 0


# ---------------------------------------------------------------------------
# Core backfill logic
# ---------------------------------------------------------------------------

async def _scroll_all_points(collection_name: str) -> list[Any]:
    """Scroll through ALL points in a collection and return them."""
    all_points: list[Any] = []
    offset = None

    while True:
        points, next_offset = _get_client().scroll(
            collection_name=collection_name,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    return all_points


def _needs_theme(point: Any) -> bool:
    """Return True if this point is missing a theme in its nested metadata."""
    payload = point.payload or {}
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        return True
    theme = metadata.get("theme")
    return theme is None or theme == ""


def _has_stale_top_level_keys(point: Any) -> bool:
    """Return True if a previous backfill wrote theme at the wrong level."""
    payload = point.payload or {}
    return "metadata.theme" in payload or "metadata.sub_theme" in payload


async def _backfill_collection(
    collection_name: str,
    batch_size: int,
    max_concurrent_llm: int,
    dry_run: bool,
) -> BackfillStats:
    stats = BackfillStats(collection=collection_name)

    logger.info(f"Scrolling all points in '{collection_name}'...")
    all_points = await asyncio.get_event_loop().run_in_executor(
        None, lambda: _scroll_all_points_sync(collection_name)
    )

    stats.total_points = len(all_points)
    logger.info(f"Total points in '{collection_name}': {stats.total_points}")

    # Split into points that need theme vs those that already have one
    needs_theme_points = []
    for point in all_points:
        if _needs_theme(point):
            needs_theme_points.append(point)
        else:
            stats.already_had_theme += 1

    # Fix stale top-level keys from a previous broken backfill:
    # Move "metadata.theme" / "metadata.sub_theme" into the nested metadata dict
    # and delete the top-level keys.
    stale_points = [p for p in all_points if _has_stale_top_level_keys(p)]
    if stale_points:
        logger.info(
            f"Fixing {len(stale_points)} points with stale top-level "
            f"'metadata.theme' keys in '{collection_name}'"
        )
        if not dry_run:
            from qdrant_client.models import DeletePayloadOperation, DeletePayload

            set_ops: list[SetPayloadOperation] = []
            del_ops: list[DeletePayloadOperation] = []
            for point in stale_points:
                payload = point.payload or {}
                existing_metadata = dict(payload.get("metadata", {}))
                top_theme = payload.get("metadata.theme")
                top_sub = payload.get("metadata.sub_theme")
                if top_theme and not existing_metadata.get("theme"):
                    existing_metadata["theme"] = top_theme
                if top_sub and not existing_metadata.get("sub_theme"):
                    existing_metadata["sub_theme"] = top_sub
                set_ops.append(
                    SetPayloadOperation(
                        set_payload=SetPayload(
                            payload={"metadata": existing_metadata},
                            points=[point.id],
                        )
                    )
                )
                del_ops.append(
                    DeletePayloadOperation(
                        delete_payload=DeletePayload(
                            keys=["metadata.theme", "metadata.sub_theme"],
                            points=[point.id],
                        )
                    )
                )
            _get_client().batch_update_points(
                collection_name=collection_name,
                update_operations=set_ops + del_ops,
                wait=True,
            )
        logger.info(f"Fixed {len(stale_points)} stale points")

        # Re-evaluate which points still need themes after migration
        needs_theme_points = [p for p in all_points if _needs_theme(p) and not _has_stale_top_level_keys(p)]
        # Points that had stale keys but now have theme in metadata count as already_had
        stats.already_had_theme = stats.total_points - len(needs_theme_points)

    stats.processed = len(needs_theme_points)
    logger.info(
        f"'{collection_name}': {stats.already_had_theme} already have theme, "
        f"{stats.processed} need classification"
    )

    if stats.processed == 0:
        logger.info(f"Nothing to backfill in '{collection_name}'.")
        return stats

    # Process in batches
    total_batches = (stats.processed + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        batch_start = batch_idx * batch_size
        batch_end = min(batch_start + batch_size, stats.processed)
        batch_points = needs_theme_points[batch_start:batch_end]

        # Extract page_content for classification
        chunks: list[str] = []
        valid_point_indices: list[int] = []

        for i, point in enumerate(batch_points):
            payload = point.payload or {}
            content = payload.get("page_content", "").strip()
            if content:
                chunks.append(content)
                valid_point_indices.append(i)
            else:
                stats.skipped_empty += 1

        if not chunks:
            logger.info(f"Batch {batch_idx + 1}/{total_batches}: all points had empty content, skipping")
            continue

        # Classify
        try:
            theme_results: list[ThemeResult] = await classify_chunks(
                chunks,
                use_llm=True,
                keyword_fast_path=True,
                max_concurrent_llm=max_concurrent_llm,
            )
        except Exception as e:
            logger.error(f"Batch {batch_idx + 1}/{total_batches}: classification failed: {e}")
            stats.errors += len(chunks)
            continue

        # Count results
        batch_classified = sum(1 for r in theme_results if r.theme is not None)
        batch_no_theme = len(theme_results) - batch_classified
        stats.classified += batch_classified
        stats.no_theme += batch_no_theme

        logger.info(
            f"Batch {batch_idx + 1}/{total_batches}: "
            f"classified {batch_classified}/{len(chunks)} chunks "
            f"({batch_no_theme} no theme / legal/nav)"
        )

        if dry_run:
            continue

        # Write back to Qdrant — batch all updates in a single API call
        ops: list[SetPayloadOperation] = []
        for point_idx, result in zip(valid_point_indices, theme_results):
            if result.theme is None:
                continue

            point = batch_points[point_idx]
            existing_metadata = dict(
                (point.payload or {}).get("metadata", {})
            )
            existing_metadata["theme"] = result.theme
            existing_metadata["sub_theme"] = result.sub_theme or ""
            ops.append(
                SetPayloadOperation(
                    set_payload=SetPayload(
                        payload={"metadata": existing_metadata},
                        points=[point.id],
                    )
                )
            )

        if ops:
            try:
                _get_client().batch_update_points(
                    collection_name=collection_name,
                    update_operations=ops,
                    wait=True,
                )
            except Exception as e:
                logger.error(
                    f"Batch set_payload failed for {len(ops)} points in '{collection_name}': {e}"
                )
                stats.errors += len(ops)

    return stats


def _scroll_all_points_sync(collection_name: str) -> list[Any]:
    """Synchronous version of scroll (runs in executor)."""
    all_points: list[Any] = []
    offset = None

    while True:
        points, next_offset = _get_client().scroll(
            collection_name=collection_name,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    return all_points


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def _print_summary(stats: BackfillStats, dry_run: bool) -> None:
    suffix = " (DRY RUN — no writes)" if dry_run else ""
    print(f"\n=== Backfill Summary{suffix} ===")
    print(f"Collection:        {stats.collection}")
    print(f"Total points:      {stats.total_points}")
    print(f"Already had theme: {stats.already_had_theme}")
    print(f"Processed:         {stats.processed}")
    print(f"  Classified:      {stats.classified}")
    print(f"  No theme (legal/nav): {stats.no_theme}")
    print(f"  Empty content:   {stats.skipped_empty}")
    print(f"  Errors:          {stats.errors}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def main(
    collections_to_process: list[str],
    batch_size: int,
    max_concurrent_llm: int,
    dry_run: bool,
) -> None:
    for coll_name in collections_to_process:
        logger.info(f"Starting backfill for collection: {coll_name}")
        stats = await _backfill_collection(
            collection_name=coll_name,
            batch_size=batch_size,
            max_concurrent_llm=max_concurrent_llm,
            dry_run=dry_run,
        )
        _print_summary(stats, dry_run=dry_run)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Backfill theme + sub_theme for Qdrant points missing them."
    )
    parser.add_argument(
        "--collection",
        choices=["candidates", "manifestos", "all"],
        default="all",
        help="Which collection to backfill (default: all)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of chunks per LLM classification batch (default: 50)",
    )
    parser.add_argument(
        "--max-concurrent-llm",
        type=int,
        default=5,
        help="Max concurrent LLM calls within a batch (default: 5)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify but do not write results to Qdrant",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help="Override QDRANT_URL (default: from env or localhost:6333)",
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Override ENV for collection name suffix (dev/prod)",
    )

    args = parser.parse_args()

    env = args.env or os.getenv("ENV", "dev")
    qdrant_url = args.qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")

    # Initialize standalone Qdrant client
    _state["qdrant_client"] = _make_qdrant_client(qdrant_url)

    # Resolve collection names with env suffix
    candidates_coll = _resolve_collection_name(_DEFAULT_CANDIDATES, env)
    parties_coll = _resolve_collection_name(_DEFAULT_PARTIES, env)

    collections: list[str] = []
    if args.collection in ("candidates", "all"):
        collections.append(candidates_coll)
    if args.collection in ("manifestos", "all"):
        collections.append(parties_coll)

    print(f"ENV: {env}")
    print(f"QDRANT_URL: {qdrant_url}")
    print(f"Collections: {collections}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'WRITE'}")

    asyncio.run(
        main(
            collections_to_process=collections,
            batch_size=args.batch_size,
            max_concurrent_llm=args.max_concurrent_llm,
            dry_run=args.dry_run,
        )
    )
