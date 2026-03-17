"""Parallel profession de foi indexer using K8s Jobs.

Replaces the sequential CI workflow with a Firestore-backed work queue.
Each K8s pod claims items atomically and processes them independently.

CLI:
    # Step 1: enqueue all communes (builds work queue from pipeline data)
    python -m src.parallel_profession_indexer enqueue --communes 1000 [--run-id custom-id]
    python -m src.parallel_profession_indexer enqueue --force  # skip already-indexed check

    # Step 2: run as worker (each K8s pod executes this)
    python -m src.parallel_profession_indexer worker --run-id <run_id>

    # Check progress
    python -m src.parallel_profession_indexer status --run-id <run_id>

    # Reclaim items from crashed workers
    python -m src.parallel_profession_indexer reclaim --run-id <run_id> [--timeout 30]

    # Launch K8s Job (prints YAML and optionally applies with kubectl)
    python -m src.parallel_profession_indexer launch --run-id <run_id> [--workers 5] [--apply]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import tempfile
import time as _time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PDF download URL template (mirrors professions.py)
# ---------------------------------------------------------------------------
_BASE_URL = "https://programme-candidats.interieur.gouv.fr/elections-municipales-2026"
_PDF_URL_TPL = f"{_BASE_URL}/data-pdf/{{tour}}-{{commune_code}}-{{panneau}}.pdf"

_PDF_CACHE_DIR = Path(tempfile.gettempdir()) / "chatvote_professions_pdfs"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf,*/*",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
    "Referer": f"{_BASE_URL}/",
}

_JOB_TYPE = "profession_index"

# ---------------------------------------------------------------------------
# K8s Job config
# ---------------------------------------------------------------------------
_IMAGE = "rg.fr-par.scw.cloud/chatvote/backend:latest"
_SECRET_NAME = "chatvote-pipeline-env"
_PULL_SECRET = "scaleway-registry"
_NODE_SELECTOR_POOL = "pool-pipeline"
_NAMESPACE = "chatvote"


# ---------------------------------------------------------------------------
# Enqueue subcommand
# ---------------------------------------------------------------------------

async def _get_already_indexed_candidates() -> set[str]:
    """Query Qdrant for candidate_ids that already have profession_de_foi chunks.

    Returns a set of candidate_ids that should be skipped during enqueue.
    """
    from src.vector_store_helper import qdrant_client
    from src.services.candidate_indexer import CANDIDATES_INDEX_NAME
    from qdrant_client.models import (
        Filter,
        FieldCondition,
        MatchValue,
    )

    indexed: set[str] = set()
    try:
        offset = None
        while True:
            result = qdrant_client.scroll(
                collection_name=CANDIDATES_INDEX_NAME,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="metadata.source_document",
                            match=MatchValue(value="profession_de_foi"),
                        ),
                    ]
                ),
                limit=1000,
                offset=offset,
                with_payload=["metadata.namespace"],
                with_vectors=False,
            )
            points, next_offset = result
            for point in points:
                ns = (point.payload or {}).get("metadata", {}).get("namespace", "")
                if ns:
                    indexed.add(ns)
            if next_offset is None:
                break
            offset = next_offset

        logger.info(
            "[enqueue] found %d candidates already indexed in Qdrant — will skip them",
            len(indexed),
        )
    except Exception as exc:
        logger.warning("[enqueue] could not check Qdrant for existing chunks: %s", exc)

    return indexed


async def _enqueue_from_firestore(
    run_id: str | None,
    force: bool = False,
) -> str:
    """Fast enqueue: query Firestore for candidates with a manifesto PDF URL.

    This avoids re-running the full pipeline. The CI job already stored
    the ministry PDF URL on each candidate doc.
    We just need to find which ones are NOT yet indexed in Qdrant.
    """
    from src.firebase_service import async_db

    logger.info("[enqueue] querying Firestore for candidates with manifesto_pdf_url...")
    _t_fsq = _time.monotonic()
    query = async_db.collection("candidates").where("manifesto_pdf_url", "!=", "")
    docs = await query.get()
    logger.info("[profession_worker:timing] firestore_query took %.2fs", _time.monotonic() - _t_fsq)

    all_candidates: list[dict[str, Any]] = []
    for doc in docs:
        doc.to_dict() or {}
        candidate_id = doc.id
        parts = candidate_id.split("-")
        if len(parts) < 3:
            continue

        commune_code = parts[1]
        panneau = parts[2]
        # The manifesto_pdf_url at this stage may be either the ministry URL
        # or the S3 URL. Workers will re-download from ministry anyway.
        pdf_url = _PDF_URL_TPL.format(
            tour="1",
            commune_code=commune_code,
            panneau=panneau,
        )

        all_candidates.append({
            "commune_code": commune_code,
            "candidate_id": candidate_id,
            "panneau": panneau,
            "tour": "1",
            "pdf_url": pdf_url,
        })

    logger.info("[enqueue] found %d candidates with manifesto_pdf_url in Firestore", len(all_candidates))

    # Check which candidates are already indexed in Qdrant
    already_indexed: set[str] = set()
    if not force:
        _t_aidx = _time.monotonic()
        already_indexed = await _get_already_indexed_candidates()
        logger.info("[profession_worker:timing] qdrant_already_indexed took %.2fs", _time.monotonic() - _t_aidx)

    items: list[dict[str, Any]] = []
    skipped = 0

    for item in all_candidates:
        if item["candidate_id"] in already_indexed:
            skipped += 1
            continue
        items.append(item)

    if skipped:
        logger.info("[enqueue] skipped %d already-indexed candidates", skipped)
        print(f"skipped (already indexed): {skipped}")

    if not items:
        print("No new work items to enqueue — all candidates already indexed.")
        print(f"  (checked {len(already_indexed)} existing, skipped {skipped})")
        print("  Use --force to re-index everything.")
        return ""

    logger.info("[enqueue] enqueueing %d new work items...", len(items))

    from src.parallel_runner import enqueue_items
    actual_run_id = await enqueue_items(_JOB_TYPE, items, run_id=run_id)

    print(f"run_id: {actual_run_id}")
    print(f"total items: {len(items)}")
    print(f"skipped (already indexed): {skipped}")
    return actual_run_id


async def _enqueue(top_communes: int, run_id: str | None, force: bool = False) -> str:
    """Enqueue work items for parallel indexing.

    Uses Firestore as source of truth (fast path): queries candidates with
    manifesto_pdf_url is set, skips those already in Qdrant.
    """
    from src.utils import load_env
    load_env()

    return await _enqueue_from_firestore(run_id=run_id, force=force)


# ---------------------------------------------------------------------------
# Worker process_item function
# ---------------------------------------------------------------------------

async def _download_pdf(pdf_url: str) -> bytes | None:
    """Download PDF bytes from ministry URL. Returns None on failure."""
    import aiohttp

    timeout = aiohttp.ClientTimeout(total=60)
    try:
        async with aiohttp.ClientSession(headers=_HEADERS, timeout=timeout) as session:
            async with session.get(pdf_url) as resp:
                if resp.status in (404, 403):
                    logger.warning("[worker] PDF not found (HTTP %d): %s", resp.status, pdf_url)
                    return None
                if resp.status != 200:
                    logger.warning("[worker] HTTP %d fetching %s", resp.status, pdf_url)
                    return None
                content = await resp.read()
                if not content[:4] == b"%PDF":
                    logger.warning("[worker] response is not a PDF for %s", pdf_url)
                    return None
                return content
    except Exception as exc:
        logger.error("[worker] download error for %s: %s", pdf_url, exc)
        return None


async def _process_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Process a single work item: download PDF → upload → index → update Firestore.

    Each K8s pod runs this function per claimed item.  Fully stateless —
    no shared volume or local cache needed between workers.
    """
    candidate_id: str = payload["candidate_id"]
    pdf_url: str = payload["pdf_url"]
    t0 = _time.monotonic()

    logger.info("[worker] processing %s from %s", candidate_id, pdf_url)

    # Step 0: Check if already indexed in Qdrant (another worker may have done it)
    _t_qdrant_check = _time.monotonic()
    try:
        from src.vector_store_helper import qdrant_client
        from src.services.candidate_indexer import CANDIDATES_INDEX_NAME
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        existing = qdrant_client.count(
            collection_name=CANDIDATES_INDEX_NAME,
            count_filter=Filter(
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
            ),
            exact=True,
        )
        logger.info("[profession_worker:timing] qdrant_check(%s) took %.2fs", candidate_id, _time.monotonic() - _t_qdrant_check)
        if existing.count > 0:
            logger.info(
                "[worker] skipping %s — already has %d chunks in Qdrant",
                candidate_id,
                existing.count,
            )
            return {"candidate_id": candidate_id, "skipped": True, "reason": "already_indexed"}
    except Exception as exc:
        logger.debug("[worker] could not check existing chunks for %s: %s", candidate_id, exc)

    # Step 1: Download PDF bytes
    _t_pdf = _time.monotonic()
    pdf_content = await _download_pdf(pdf_url)
    if pdf_content is None:
        raise RuntimeError(f"Failed to download PDF for {candidate_id} from {pdf_url}")
    logger.info("[profession_worker:timing] pdf_download(%s) took %.2fs, %d bytes", candidate_id, _time.monotonic() - _t_pdf, len(pdf_content))

    # Step 2: Load candidate from Firestore
    from src.firebase_service import aget_candidate_by_id
    _t_fs_load = _time.monotonic()
    try:
        candidate = await aget_candidate_by_id(candidate_id)
    except Exception:
        candidate = None
    logger.info("[profession_worker:timing] firestore_load(%s) took %.2fs", candidate_id, _time.monotonic() - _t_fs_load)
    if candidate is None:
        logger.warning(
            "[worker] skipping %s — not fully seeded in Firestore (run seed pipeline first)",
            candidate_id,
        )
        return {"skipped": True, "reason": "not_in_firestore"}

    # Step 3: Upload to S3 (public-assets bucket)
    from src.services.profession_indexer import (
        _upload_to_s3,
        STORAGE_PREFIX,
        _create_documents_from_profession,
        _delete_profession_chunks,
        _update_firestore_url,
    )
    from src.services.manifesto_indexer import extract_pages_from_pdf
    from src.services.profession_indexer import _extract_pages_with_gemini

    commune_code = candidate.municipality_code or (
        candidate_id.split("-")[1] if len(candidate_id.split("-")) >= 3 else "unknown"
    )
    blob_path = f"{STORAGE_PREFIX}/{commune_code}/{candidate_id}.pdf"

    _t_upload = _time.monotonic()
    storage_url = await asyncio.to_thread(_upload_to_s3, pdf_content, blob_path)
    logger.info("[profession_worker:timing] storage_upload(%s) took %.2fs", candidate_id, _time.monotonic() - _t_upload)
    logger.info("[worker] uploaded %s to S3", candidate_id)

    # Step 4: Extract text (page-aware), with Gemini OCR fallback
    _t_extract = _time.monotonic()
    pages = extract_pages_from_pdf(pdf_content)
    if not pages:
        logger.info("[worker] no pypdf text for %s, trying Gemini vision...", candidate_id)
        logger.info("[profession_worker:timing] text_extraction(%s) took %.2fs, %d pages", candidate_id, _time.monotonic() - _t_extract, 0)
        _t_ocr = _time.monotonic()
        pages = await _extract_pages_with_gemini(pdf_content)
        logger.info("[profession_worker:timing] gemini_ocr(%s) took %.2fs, %d pages", candidate_id, _time.monotonic() - _t_ocr, len(pages) if pages else 0)
    else:
        logger.info("[profession_worker:timing] text_extraction(%s) took %.2fs, %d pages", candidate_id, _time.monotonic() - _t_extract, len(pages))

    if not pages:
        logger.warning("[worker] no text extracted for %s — storing URL only", candidate_id)
        await _update_firestore_url(candidate_id, storage_url)
        return {"candidate_id": candidate_id, "chunks": 0, "skipped_no_text": True}

    # Step 5: Create chunked LangChain documents
    _t_create_docs = _time.monotonic()
    documents = _create_documents_from_profession(candidate, pages, storage_url)
    logger.info("[profession_worker:timing] create_documents(%s) took %.2fs, %d docs", candidate_id, _time.monotonic() - _t_create_docs, len(documents) if documents else 0)
    if not documents:
        logger.warning("[worker] no chunks created for %s", candidate_id)
        await _update_firestore_url(candidate_id, storage_url)
        return {"candidate_id": candidate_id, "chunks": 0}

    logger.info("[worker] %d chunks for %s", len(documents), candidate_id)

    # Step 6: Delete existing profession_de_foi chunks (idempotent)
    _t_delete = _time.monotonic()
    await asyncio.to_thread(_delete_profession_chunks, candidate_id)
    logger.info("[profession_worker:timing] delete_chunks(%s) took %.2fs", candidate_id, _time.monotonic() - _t_delete)

    # Step 7: Index into Qdrant
    from src.services.candidate_indexer import _get_candidates_vector_store

    vector_store = _get_candidates_vector_store()
    batch_size = 50
    _t_index = _time.monotonic()
    for i in range(0, len(documents), batch_size):
        batch = documents[i : i + batch_size]
        await vector_store.aadd_documents(batch)
        await asyncio.sleep(0)
    logger.info("[profession_worker:timing] qdrant_index(%s) took %.2fs, %d docs", candidate_id, _time.monotonic() - _t_index, len(documents))

    # Step 8: Update Firestore URL
    _t_fs_url = _time.monotonic()
    await _update_firestore_url(candidate_id, storage_url)
    logger.info("[profession_worker:timing] firestore_url_update(%s) took %.2fs", candidate_id, _time.monotonic() - _t_fs_url)

    elapsed = _time.monotonic() - t0
    logger.info("[worker] done %s: %d chunks in %.1fs", candidate_id, len(documents), elapsed)
    return {"candidate_id": candidate_id, "chunks": len(documents), "elapsed_s": round(elapsed, 1)}


async def _run_worker(run_id: str) -> None:
    """Entry point for the K8s pod worker."""
    from src.utils import load_env
    load_env()

    from src.parallel_runner import worker_loop
    processed = await worker_loop(_JOB_TYPE, run_id, _process_item)
    print(f"Worker finished. Processed {processed} items.")


# ---------------------------------------------------------------------------
# Status subcommand
# ---------------------------------------------------------------------------

async def _show_status(run_id: str) -> None:
    from src.utils import load_env
    load_env()

    from src.parallel_runner import get_run_status

    status = await get_run_status(run_id)
    if "error" in status:
        print(f"Error: {status['error']}")
        return

    total = status["total"]
    done = status["done"]
    failed = status["failed"]
    pending = status["pending"]
    processing = status["processing"]
    pct = (done + failed) / total * 100 if total else 0

    bar_len = 40
    filled = int(bar_len * (done + failed) / total) if total else 0
    bar = "#" * filled + "-" * (bar_len - filled)

    eta = status.get("eta_seconds")
    eta_str = f"{eta:.0f}s" if eta is not None else "N/A"

    print(f"\nRun: {status['run_id']}  ({status['job_type']})")
    print(f"Status: {status['status']}")
    print(f"[{bar}] {pct:.1f}%")
    print(
        f"  total={total}  done={done}  failed={failed}  "
        f"pending={pending}  processing={processing}"
    )
    print(f"  elapsed={status['elapsed_s']}s  rate={status['items_per_second']}/s  ETA={eta_str}")


# ---------------------------------------------------------------------------
# Reclaim subcommand
# ---------------------------------------------------------------------------

async def _reclaim(run_id: str, timeout_minutes: int) -> None:
    from src.utils import load_env
    load_env()

    from src.parallel_runner import reclaim_stale_items
    count = await reclaim_stale_items(run_id, timeout_minutes=timeout_minutes)
    print(f"Reclaimed {count} stale items for run {run_id}")


# ---------------------------------------------------------------------------
# Launch subcommand — generate K8s Job YAML and optionally apply it
# ---------------------------------------------------------------------------

def _build_job_manifest(run_id: str, workers: int) -> str:
    job_name = f"profession-indexer-{run_id[:8]}"
    return f"""\
apiVersion: batch/v1
kind: Job
metadata:
  name: {job_name}
  namespace: {_NAMESPACE}
  labels:
    app.kubernetes.io/managed-by: chatvote-admin
    chatvote/job-type: profession-indexer
    chatvote/run-id: "{run_id[:63]}"
spec:
  parallelism: {workers}
  # No 'completions' — work-queue pattern: each pod loops until queue empty
  activeDeadlineSeconds: 86400
  ttlSecondsAfterFinished: 3600
  backoffLimit: 0
  template:
    metadata:
      labels:
        app.kubernetes.io/managed-by: chatvote-admin
        chatvote/job-type: profession-indexer
    spec:
      restartPolicy: Never
      nodeSelector:
        k8s.scaleway.com/pool-name: {_NODE_SELECTOR_POOL}
      imagePullSecrets:
        - name: {_PULL_SECRET}
      containers:
        - name: profession-indexer
          image: {_IMAGE}
          command:
            - python
            - -m
            - src.parallel_profession_indexer
            - worker
            - --run-id
            - "{run_id}"
          envFrom:
            - secretRef:
                name: {_SECRET_NAME}
          resources:
            requests:
              memory: "1Gi"
              cpu: "500m"
            limits:
              memory: "4Gi"
              cpu: "2000m"
"""


def _launch(run_id: str, workers: int, apply: bool) -> None:
    manifest = _build_job_manifest(run_id, workers)
    print(manifest)

    if apply:
        import subprocess
        import tempfile as _tf

        with _tf.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(manifest)
            tmp_path = f.name

        result = subprocess.run(
            ["kubectl", "apply", "-f", tmp_path],
            capture_output=True,
            text=True,
        )
        os.unlink(tmp_path)

        if result.returncode == 0:
            print(result.stdout)
            print(f"Job launched with {workers} worker(s) for run {run_id}")
        else:
            print("kubectl error:", result.stderr, file=sys.stderr)
            sys.exit(result.returncode)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


def main() -> None:
    _configure_logging()

    parser = argparse.ArgumentParser(
        description="Parallel profession de foi indexer using K8s Jobs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # enqueue
    p_enqueue = sub.add_parser("enqueue", help="Build work queue from pipeline data")
    p_enqueue.add_argument(
        "--communes",
        type=int,
        required=True,
        metavar="N",
        help="Number of top communes to process (required)",
    )
    p_enqueue.add_argument(
        "--run-id",
        default=None,
        metavar="ID",
        help="Custom run ID (auto-generated if omitted)",
    )
    p_enqueue.add_argument(
        "--force",
        action="store_true",
        help="Re-index all candidates even if already indexed in Qdrant",
    )

    # worker
    p_worker = sub.add_parser("worker", help="Run as K8s pod worker")
    p_worker.add_argument("--run-id", required=True, metavar="ID", help="Run ID to consume")

    # status
    p_status = sub.add_parser("status", help="Show run progress")
    p_status.add_argument("--run-id", required=True, metavar="ID")

    # reclaim
    p_reclaim = sub.add_parser("reclaim", help="Reset stale items from crashed workers")
    p_reclaim.add_argument("--run-id", required=True, metavar="ID")
    p_reclaim.add_argument(
        "--timeout",
        type=int,
        default=30,
        metavar="MINUTES",
        help="Items claimed for longer than this are reclaimed (default: 30)",
    )

    # launch
    p_launch = sub.add_parser("launch", help="Generate K8s Job YAML (and optionally apply)")
    p_launch.add_argument("--run-id", required=True, metavar="ID")
    p_launch.add_argument(
        "--workers",
        type=int,
        default=3,
        metavar="N",
        help="Number of parallel worker pods (default: 3)",
    )
    p_launch.add_argument(
        "--apply",
        action="store_true",
        help="Apply the manifest with kubectl (requires kubectl in PATH)",
    )

    args = parser.parse_args()

    if args.command == "enqueue":
        try:
            asyncio.run(_enqueue(args.communes, args.run_id, force=args.force))
        except Exception:
            logger.exception("enqueue failed")
            sys.exit(1)

    elif args.command == "worker":
        try:
            asyncio.run(_run_worker(args.run_id))
        except Exception:
            logger.exception("worker failed")
            sys.exit(1)

    elif args.command == "status":
        try:
            asyncio.run(_show_status(args.run_id))
        except Exception:
            logger.exception("status check failed")
            sys.exit(1)

    elif args.command == "reclaim":
        try:
            asyncio.run(_reclaim(args.run_id, args.timeout))
        except Exception:
            logger.exception("reclaim failed")
            sys.exit(1)

    elif args.command == "launch":
        _launch(args.run_id, args.workers, args.apply)


if __name__ == "__main__":
    main()
