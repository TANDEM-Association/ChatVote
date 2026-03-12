# SPDX-FileCopyrightText: 2025 chatvote
#
# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

"""
Backfill party_ids and municipality_name for existing Qdrant points
that are missing them, using Firestore candidate records as source of truth.

Usage:
    # Dry-run (default) — report what would change, no writes
    poetry run python -m src.services.backfill_metadata

    # Write mode — actually patch Qdrant
    poetry run python -m src.services.backfill_metadata --write

    # Single namespace test
    poetry run python -m src.services.backfill_metadata --write --namespace cand-13055-6

    # Audit only — report fill rates, no patching
    poetry run python -m src.services.backfill_metadata --audit

    # Audit with custom sample size
    poetry run python -m src.services.backfill_metadata --audit --audit-limit 1000
"""

import argparse
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from qdrant_client.models import PointIdsList

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill party_ids + municipality_name from Firestore into Qdrant."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Actually write to Qdrant (default is dry-run)",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        default=None,
        help="Only process a single namespace (e.g. cand-13055-6)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Only run audit (fill rate report), no backfill",
    )
    parser.add_argument(
        "--audit-limit",
        type=int,
        default=500,
        help="Number of points to sample for audit (default: 500)",
    )
    parser.add_argument(
        "--max-patches",
        type=int,
        default=0,
        help="Stop after N patches (0 = unlimited). Use for staged rollout.",
    )
    parser.add_argument(
        "--cross-check",
        action="store_true",
        help="Cross-check Qdrant candidate_id & municipality_code against Firestore",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Override Qdrant collection name (e.g. candidates_websites_prod)",
    )
    parser.add_argument(
        "--env",
        type=str,
        default=None,
        help="Override ENV for Firestore (dev/prod/local). Does NOT affect collection name unless --collection is omitted.",
    )
    parser.add_argument(
        "--qdrant-url",
        type=str,
        default=None,
        help="Override QDRANT_URL. Sets before module imports.",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@dataclass
class PatchEntry:
    """One planned or applied patch."""
    point_id: str
    namespace: str
    candidate_id: str
    fields: dict[str, Any]  # {"party_ids": [...], "municipality_name": "..."}


@dataclass
class BackfillStats:
    total_points: int = 0
    already_ok: int = 0
    patched: int = 0
    skipped_poster: int = 0
    skipped_no_candidate: int = 0
    firestore_miss: int = 0
    errors: int = 0
    patches: list[PatchEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Qdrant helpers
# ---------------------------------------------------------------------------

def scroll_all_points(
    collection_name: str,
    namespace_filter: str | None = None,
) -> list[Any]:
    """Scroll all points in a collection, optionally filtering by namespace prefix."""
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    all_points: list[Any] = []
    offset = None
    scroll_filter = None

    if namespace_filter:
        scroll_filter = Filter(
            must=[
                FieldCondition(
                    key="metadata.namespace",
                    match=MatchValue(value=namespace_filter),
                )
            ]
        )

    while True:
        points, next_offset = _qdrant_client.scroll(
            collection_name=collection_name,
            limit=500,
            offset=offset,
            with_payload=True,
            with_vectors=False,
            scroll_filter=scroll_filter,
        )
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    return all_points


def _is_poster_namespace(point: Any) -> bool:
    metadata = (point.payload or {}).get("metadata", {})
    ns = metadata.get("namespace", "")
    return ns.startswith("poster_")


def _needs_backfill(point: Any) -> bool:
    """Return True if party_ids or municipality_name is missing/empty."""
    metadata = (point.payload or {}).get("metadata", {})
    party_ids = metadata.get("party_ids", [])
    municipality_name = metadata.get("municipality_name", "")
    return (not party_ids) or (not municipality_name)


def _extract_candidate_id(point: Any) -> str | None:
    """Extract candidate_id from the point's metadata."""
    metadata = (point.payload or {}).get("metadata", {})
    candidate_ids = metadata.get("candidate_ids", [])
    if candidate_ids and len(candidate_ids) > 0:
        return candidate_ids[0]
    # Fallback: try namespace (cand-XXXXX-N → candidate doc ID)
    ns = metadata.get("namespace", "")
    if ns.startswith("cand-"):
        return ns
    return None


# ---------------------------------------------------------------------------
# Firestore candidate lookup (sync, uses the already-initialized db)
# ---------------------------------------------------------------------------

def _build_candidate_cache() -> dict[str, dict[str, Any]]:
    """Load all candidates from Firestore into a dict keyed by candidate_id.

    Returns {candidate_id: {"party_ids": [...], "municipality_name": "..."}}.
    """
    from src.firebase_service import db

    cache: dict[str, dict[str, Any]] = {}
    for doc in db.collection("candidates").stream():
        data = doc.to_dict()
        cid = data.get("candidate_id", doc.id)
        cache[cid] = {
            "party_ids": data.get("party_ids", []),
            "municipality_name": data.get("municipality_name", ""),
            "municipality_code": data.get("municipality_code", ""),
        }
    logger.info(f"Loaded {len(cache)} candidates from Firestore")
    return cache


# ---------------------------------------------------------------------------
# Backfill logic
# ---------------------------------------------------------------------------

def backfill(
    collection_name: str,
    candidate_cache: dict[str, dict[str, Any]],
    dry_run: bool = True,
    namespace: str | None = None,
    max_patches: int = 0,
) -> BackfillStats:
    stats = BackfillStats()

    logger.info(
        f"Scrolling '{collection_name}'"
        + (f" namespace={namespace}" if namespace else " (all namespaces)")
        + " ..."
    )
    all_points = scroll_all_points(collection_name, namespace_filter=namespace)
    stats.total_points = len(all_points)
    logger.info(f"Total points: {stats.total_points}")

    for i, point in enumerate(all_points):
        if _is_poster_namespace(point):
            stats.skipped_poster += 1
            continue

        if not _needs_backfill(point):
            stats.already_ok += 1
            continue

        candidate_id = _extract_candidate_id(point)
        if not candidate_id:
            stats.skipped_no_candidate += 1
            continue

        candidate_data = candidate_cache.get(candidate_id)
        if not candidate_data:
            stats.firestore_miss += 1
            if stats.firestore_miss <= 5:
                logger.warning(f"Candidate '{candidate_id}' not found in Firestore")
            continue

        # Read full existing metadata, merge new fields
        existing_metadata = dict((point.payload or {}).get("metadata", {}))
        patch_fields: dict[str, Any] = {}

        if not existing_metadata.get("party_ids") and candidate_data["party_ids"]:
            existing_metadata["party_ids"] = candidate_data["party_ids"]
            patch_fields["party_ids"] = candidate_data["party_ids"]

        if not existing_metadata.get("municipality_name") and candidate_data["municipality_name"]:
            existing_metadata["municipality_name"] = candidate_data["municipality_name"]
            patch_fields["municipality_name"] = candidate_data["municipality_name"]

        # Also backfill municipality_code if missing
        if not existing_metadata.get("municipality_code") and candidate_data["municipality_code"]:
            existing_metadata["municipality_code"] = candidate_data["municipality_code"]
            patch_fields["municipality_code"] = candidate_data["municipality_code"]

        if not patch_fields:
            stats.already_ok += 1
            continue

        ns = existing_metadata.get("namespace", "")
        entry = PatchEntry(
            point_id=str(point.id),
            namespace=ns,
            candidate_id=candidate_id,
            fields=patch_fields,
        )
        stats.patches.append(entry)

        if not dry_run:
            try:
                _qdrant_client.set_payload(
                    collection_name=collection_name,
                    payload={"metadata": existing_metadata},
                    points=PointIdsList(points=[point.id]),
                )
            except Exception as e:
                logger.error(f"Failed to patch point {point.id}: {e}")
                stats.errors += 1
                continue

        stats.patched += 1

        if max_patches and stats.patched >= max_patches:
            logger.info(f"Reached max_patches={max_patches}, stopping early.")
            break

        if stats.patched % 500 == 0:
            logger.info(f"Progress: {stats.patched} patched so far...")

    return stats


# ---------------------------------------------------------------------------
# Audit — check fill rates
# ---------------------------------------------------------------------------

def audit(collection_name: str, limit: int = 500) -> None:
    """Scroll up to `limit` points and report metadata fill rates."""
    all_points: list[Any] = []
    offset = None

    while len(all_points) < limit:
        batch_limit = min(500, limit - len(all_points))
        points, next_offset = _qdrant_client.scroll(
            collection_name=collection_name,
            limit=batch_limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    total = len(all_points)
    if total == 0:
        print(f"\n=== Audit: '{collection_name}' is EMPTY ===")
        return

    # Count fill rates
    fields = ["party_ids", "municipality_name", "municipality_code", "theme", "sub_theme",
              "candidate_name", "namespace", "fiabilite", "source_document"]
    counts: dict[str, int] = {f: 0 for f in fields}
    poster_count = 0
    cand_count = 0

    for point in all_points:
        metadata = (point.payload or {}).get("metadata", {})
        ns = metadata.get("namespace", "")
        if ns.startswith("poster_"):
            poster_count += 1
        elif ns.startswith("cand-"):
            cand_count += 1

        for f in fields:
            val = metadata.get(f)
            if f == "party_ids":
                if val and len(val) > 0:
                    counts[f] += 1
            elif val is not None and val != "" and val != []:
                counts[f] += 1

    print(f"\n=== Audit: '{collection_name}' ({total} points sampled) ===")
    print(f"  Namespace breakdown: {cand_count} cand-*, {poster_count} poster_*, {total - cand_count - poster_count} other")
    print()
    for f in fields:
        pct = counts[f] / total * 100
        bar = "#" * int(pct / 2) + "." * (50 - int(pct / 2))
        print(f"  {f:25s} {counts[f]:5d}/{total:5d}  ({pct:5.1f}%)  [{bar}]")
    print()


def cross_check(collection_name: str, candidate_cache: dict[str, dict[str, Any]], limit: int = 500) -> None:
    """Cross-check Qdrant candidate_id and municipality_code against Firestore."""
    all_points: list[Any] = []
    offset = None

    while len(all_points) < limit:
        batch_limit = min(500, limit - len(all_points))
        points, next_offset = _qdrant_client.scroll(
            collection_name=collection_name,
            limit=batch_limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        all_points.extend(points)
        if next_offset is None:
            break
        offset = next_offset

    # Only check cand-* points
    cand_points = [p for p in all_points
                   if (p.payload or {}).get("metadata", {}).get("namespace", "").startswith("cand-")]

    total = len(cand_points)
    if total == 0:
        print("\n=== Cross-Check: no cand-* points found ===")
        return

    matched = 0
    mismatched_code = 0
    mismatched_party = 0
    missing_in_firestore = 0
    no_candidate_id = 0
    mismatches: list[dict[str, Any]] = []

    for point in cand_points:
        metadata = (point.payload or {}).get("metadata", {})
        candidate_id = _extract_candidate_id(point)
        if not candidate_id:
            no_candidate_id += 1
            continue

        fs_data = candidate_cache.get(candidate_id)
        if not fs_data:
            missing_in_firestore += 1
            continue

        qdrant_code = metadata.get("municipality_code", "")
        fs_code = fs_data.get("municipality_code", "")
        qdrant_party = metadata.get("party_ids", [])
        fs_party = fs_data.get("party_ids", [])

        code_ok = (not qdrant_code and not fs_code) or qdrant_code == fs_code
        party_ok = (not qdrant_party and not fs_party) or sorted(qdrant_party) == sorted(fs_party)

        if code_ok and party_ok:
            matched += 1
        else:
            if not code_ok:
                mismatched_code += 1
            if not party_ok:
                mismatched_party += 1
            if len(mismatches) < 10:
                mismatches.append({
                    "candidate_id": candidate_id,
                    "namespace": metadata.get("namespace", ""),
                    "qdrant_code": qdrant_code,
                    "fs_code": fs_code,
                    "qdrant_party": qdrant_party,
                    "fs_party": fs_party,
                    "code_ok": code_ok,
                    "party_ok": party_ok,
                })

    print(f"\n=== Cross-Check: Qdrant vs Firestore ({total} cand-* points) ===")
    print(f"  Matched:              {matched}")
    print(f"  municipality_code mismatch: {mismatched_code}")
    print(f"  party_ids mismatch:   {mismatched_party}")
    print(f"  Not in Firestore:     {missing_in_firestore}")
    print(f"  No candidate_id:      {no_candidate_id}")

    if mismatches:
        print(f"\n  Sample mismatches (first {len(mismatches)}):")
        for m in mismatches:
            print(f"    {m['namespace']} ({m['candidate_id']}):")
            if not m["code_ok"]:
                print(f"      municipality_code: qdrant={m['qdrant_code']!r} vs firestore={m['fs_code']!r}")
            if not m["party_ok"]:
                print(f"      party_ids: qdrant={m['qdrant_party']} vs firestore={m['fs_party']}")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(stats: BackfillStats, dry_run: bool) -> None:
    suffix = " (DRY RUN — no writes)" if dry_run else ""
    print(f"\n=== Backfill Summary{suffix} ===")
    print(f"Total points:          {stats.total_points}")
    print(f"Already OK:            {stats.already_ok}")
    print(f"Patched:               {stats.patched}")
    print(f"Skipped (poster_*):    {stats.skipped_poster}")
    print(f"Skipped (no cand ID):  {stats.skipped_no_candidate}")
    print(f"Firestore miss:        {stats.firestore_miss}")
    print(f"Errors:                {stats.errors}")

    if stats.patches:
        # Group patches by namespace for readable output
        by_ns: dict[str, list[PatchEntry]] = {}
        for p in stats.patches:
            by_ns.setdefault(p.namespace, []).append(p)

        print(f"\n=== Patch List ({len(stats.patches)} points across {len(by_ns)} namespaces) ===")
        for ns in sorted(by_ns.keys()):
            entries = by_ns[ns]
            print(f"\n  [{ns}] — {len(entries)} points")
            # Show what fields will be sent for this namespace (from first entry as sample)
            sample = entries[0]
            field_names = list(sample.fields.keys())
            print(f"    candidate: {sample.candidate_id}")
            print(f"    fields to patch: {', '.join(field_names)}")
            for e in entries[:3]:
                parts = []
                for k, v in e.fields.items():
                    parts.append(f"{k}={v}")
                print(f"      point {e.point_id[:12]}…  {' | '.join(parts)}")
            if len(entries) > 3:
                print(f"      ... and {len(entries) - 3} more points with same fields")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _make_qdrant_client(url: str) -> Any:
    """Create a standalone QdrantClient without importing the full app stack."""
    from qdrant_client import QdrantClient

    force_rest = url.startswith("https://")
    return QdrantClient(
        url=url,
        api_key=os.getenv("QDRANT_API_KEY"),
        prefer_grpc=False,
        https=force_rest,
        port=443 if force_rest else 6333,
        timeout=30,
    )


def _resolve_collection_name(env: str) -> str:
    """Compute candidates collection name from ENV without importing src.*."""
    suffix = f"_{env}" if env in ("prod", "dev") else "_dev"
    return f"candidates_websites{suffix}"


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    args = _parse_args()

    # Resolve env and qdrant URL from CLI args or .env defaults
    env = args.env or os.getenv("ENV", "dev")
    qdrant_url = args.qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333")
    collection = args.collection or _resolve_collection_name(env)

    print(f"Collection: {collection}")
    print(f"ENV: {env}")
    print(f"QDRANT_URL: {qdrant_url}")

    global _qdrant_client

    # For audit-only, create a lightweight Qdrant client (no app imports needed)
    if args.audit and not args.cross_check:
        _qdrant_client = _make_qdrant_client(qdrant_url)
        audit(collection, limit=args.audit_limit)
        return

    # For cross-check, need Qdrant + Firestore (but lightweight Qdrant client)
    if args.cross_check:
        _qdrant_client = _make_qdrant_client(qdrant_url)
        # Need Firestore — set env vars and import
        if args.env:
            os.environ["ENV"] = args.env
        os.environ["API_NAME"] = "chatvote-api"
        candidate_cache = _build_candidate_cache()
        cross_check(collection, candidate_cache, limit=args.audit_limit)
        return

    # For backfill, we need Qdrant + Firestore (but NOT embeddings/LLMs)
    _qdrant_client = _make_qdrant_client(qdrant_url)

    # Firestore init
    if args.env:
        os.environ["ENV"] = args.env
    os.environ["API_NAME"] = "chatvote-api"

    dry_run = not args.write
    if dry_run:
        print("Mode: DRY RUN (pass --write to apply changes)")
    else:
        print("Mode: WRITE (changes will be applied to Qdrant)")

    candidate_cache = _build_candidate_cache()
    stats = backfill(
        collection_name=collection,
        candidate_cache=candidate_cache,
        dry_run=dry_run,
        namespace=args.namespace,
        max_patches=args.max_patches,
    )
    print_summary(stats, dry_run=dry_run)

    # Always run audit after backfill
    print("\n--- Post-backfill audit ---")
    audit(collection, limit=args.audit_limit)


# Module-level client — set by main() before any work happens
_qdrant_client: Any = None


if __name__ == "__main__":
    main()
