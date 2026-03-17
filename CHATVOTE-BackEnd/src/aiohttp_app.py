# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Backend v2 — commune dashboard, candidate scraping, admin auth, pipeline

import argparse
import asyncio
import logging
import os
import json
import time

import aiohttp
from aiohttp import web
import aiohttp_cors
from aiohttp_pydantic.decorator import inject_params

from src.chatbot_async import (
    get_improved_rag_query_voting_behavior,
)
from src.firebase_service import aget_party_by_id, aget_parties, aget_candidates, aget_candidates_by_municipality, async_db, db
from src.llms import reset_all_rate_limits, NON_DETERMINISTIC_LLMS
from src.models.assistant import CHATVOTE_ASSISTANT
from src.services.manifesto_indexer import index_all_parties, index_party_by_id
from src.services.candidate_indexer import (
    index_all_candidates,
    index_candidate_by_id,
)
from src.vector_store_helper import (
    qdrant_client,
    PARTY_INDEX_NAME,
    CANDIDATES_INDEX_NAME,
    embed,
    identify_relevant_docs_combined,
)
from src.services.firestore_listener import (
    start_parties_listener,
    start_candidates_listener,
    is_listener_running,
    is_candidates_listener_running,
)
from src.services.document_upload import (
    create_job,
    get_job,
    get_all_jobs,
    process_upload,
    preview_upload,
    confirm_upload,
)
from src.services.scheduler import create_scheduler
from src.models.dtos import (
    ParliamentaryQuestionDto,
    ParliamentaryQuestionRequestDto,
    Status,
    StatusIndicator,
)
from src.models.vote import Vote
from src.vector_store_helper import identify_relevant_parliamentary_questions
from src.utils import get_cors_allowed_origins
from src.websocket_app import sio

LOGGING_FORMAT = (
    "%(asctime)s - %(name)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s"
)
# Set up default logging configuration
logging.basicConfig(level=logging.INFO, format=LOGGING_FORMAT)

logger = logging.getLogger(__name__)

app = web.Application()

routes = web.RouteTableDef()

route_prefix = "/api/v1"


@web.middleware
async def api_key_middleware(request, handler):
    if request.method == "OPTIONS":
        return await handler(request)

    # TODO: implement authentication here, if needed
    return await handler(request)


@routes.get("/healthz")
async def health_check(request):
    """Kubernetes health check endpoint."""
    return web.json_response({"status": "ok"})


@routes.get("/health")
async def health_check_deep(request):
    """Deep health check verifying all external dependencies."""
    import asyncio

    checks: dict = {}
    overall_ok = True

    # Check Qdrant connectivity
    try:
        qdrant_client.get_collections()
        checks["qdrant"] = {"status": "ok"}
    except Exception as e:
        checks["qdrant"] = {"status": "error", "detail": str(e)}
        overall_ok = False

    # Check Firebase Firestore connectivity
    try:
        await asyncio.wait_for(
            async_db.collection("system_status").document("llm_status").get(),
            timeout=5.0,
        )
        checks["firestore"] = {"status": "ok"}
    except asyncio.TimeoutError:
        checks["firestore"] = {"status": "error", "detail": "timeout after 5s"}
        overall_ok = False
    except Exception as e:
        checks["firestore"] = {"status": "error", "detail": str(e)}
        overall_ok = False

    # Check LLM availability (no API calls — just inspect in-memory state)
    available = [llm.name for llm in NON_DETERMINISTIC_LLMS if not llm.is_at_rate_limit]
    rate_limited = [llm.name for llm in NON_DETERMINISTIC_LLMS if llm.is_at_rate_limit]
    configured = [llm.name for llm in NON_DETERMINISTIC_LLMS]
    if not configured:
        checks["llms"] = {"status": "error", "detail": "no LLMs configured"}
        overall_ok = False
    elif not available:
        checks["llms"] = {
            "status": "error",
            "detail": "all LLMs at rate limit",
            "available": [],
            "rate_limited": rate_limited,
        }
        overall_ok = False
    else:
        checks["llms"] = {
            "status": "ok",
            "available": available,
            "rate_limited": rate_limited,
        }

    # Check Ollama (optional — only if OLLAMA_BASE_URL is configured)
    ollama_url = os.getenv("OLLAMA_BASE_URL")
    if ollama_url:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{ollama_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=3),
                ) as resp:
                    if resp.status < 500:
                        checks["ollama"] = {"status": "ok"}
                    else:
                        checks["ollama"] = {"status": "error", "detail": f"HTTP {resp.status}"}
                        overall_ok = False
        except Exception as e:
            checks["ollama"] = {"status": "error", "detail": str(e)}
            overall_ok = False

    # Stateless API note (informational only)
    checks["stateless"] = {
        "status": "ok",
        "note": "Session state is scoped per Socket.IO sid; no cross-request shared mutable state.",
    }

    status_code = 200 if overall_ok else 503
    return web.json_response(
        {"status": "ok" if overall_ok else "degraded", "checks": checks},
        status=status_code,
    )


@routes.get(f"{route_prefix}/assistant")
async def get_assistant_info(request):
    """Get ChatVote assistant information.

    This returns the assistant's metadata (name, description, logo, etc.)
    without needing to store it in Firestore.
    """
    return web.json_response(CHATVOTE_ASSISTANT.model_dump())


_indexing_status: dict = {"manifestos": None, "candidates": None}


@routes.post(f"{route_prefix}/admin/index-all-manifestos")
async def admin_index_all_manifestos(request):
    """Trigger indexation of all party manifestos (runs in background)."""
    logger.info("Admin triggered: indexing all party manifestos")

    async def _run():
        try:
            _indexing_status["manifestos"] = {"status": "running", "started": True}
            results = await index_all_parties()
            total = sum(results.values())
            _indexing_status["manifestos"] = {
                "status": "done", "total": total, "details": results,
            }
            logger.info(f"Manifesto indexing complete: {total} chunks for {len(results)} parties")
        except Exception as e:
            _indexing_status["manifestos"] = {"status": "error", "message": str(e)}
            logger.error(f"Error indexing manifestos: {e}", exc_info=True)

    asyncio.create_task(_run())
    return web.json_response({"status": "started", "message": "Manifesto indexing started in background. Check /admin/index-status for progress."})


@routes.post(route_prefix + "/admin/index-party-manifesto/{party_id}")
async def admin_index_party_manifesto(request):
    """Admin endpoint to trigger indexation of a specific party's manifesto."""
    party_id = request.match_info["party_id"]
    logger.info(f"Admin triggered: indexing manifesto for party {party_id}")

    try:
        count = await index_party_by_id(party_id)

        if count > 0:
            return web.json_response(
                {
                    "status": "success",
                    "message": f"Indexed {count} chunks for party {party_id}",
                }
            )
        else:
            return web.json_response(
                {
                    "status": "warning",
                    "message": f"No chunks indexed for party {party_id}. Check if manifesto URL exists.",
                }
            )
    except Exception as e:
        logger.error(f"Error indexing manifesto for {party_id}: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500,
        )


@routes.post(f"{route_prefix}/admin/index-all-candidates")
async def admin_index_all_candidates(request):
    """Trigger indexation of all candidate websites (runs in background).

    Query params:
        scraper: "auto" | "firecrawl" | "playwright"
        force: "true" to re-scrape candidates already in Qdrant
    """
    scraper_backend = request.query.get("scraper", "auto")
    force = request.query.get("force", "").lower() == "true"
    logger.info(f"Admin triggered: indexing all candidate websites (scraper={scraper_backend}, force={force})")

    async def _run():
        try:
            _indexing_status["candidates"] = {"status": "running", "started": True}
            results = await index_all_candidates(scraper_backend=scraper_backend, force=force)
            total = sum(results.values())
            successful = sum(1 for v in results.values() if v > 0)
            _indexing_status["candidates"] = {
                "status": "done", "total": total, "successful": successful, "details": results,
            }
            logger.info(f"Candidate indexing complete: {total} chunks for {successful}/{len(results)} candidates")
        except Exception as e:
            _indexing_status["candidates"] = {"status": "error", "message": str(e)}
            logger.error(f"Error indexing candidates: {e}", exc_info=True)

    asyncio.create_task(_run())
    return web.json_response({"status": "started", "message": "Candidate indexing started in background. Check /admin/index-status for progress."})


@routes.get(f"{route_prefix}/admin/index-status")
async def admin_index_status(request):
    """Check status of background indexing tasks."""
    return web.json_response(_indexing_status)


# ---------------------------------------------------------------------------
# Namespace migration: rename old national-election manifesto namespaces
# (la-france-insoumise, renaissance, place-publique) to current Firestore
# party_ids (lfi, union_centre, union_gauche).
# ---------------------------------------------------------------------------
NAMESPACE_MIGRATION_MAP: dict[str, str] = {
    "la-france-insoumise": "lfi",
    "renaissance": "union_centre",
    "place-publique": "union_gauche",
}


@routes.post(f"{route_prefix}/admin/migrate-manifesto-namespaces")
async def admin_migrate_manifesto_namespaces(request):
    """Rename old manifesto namespaces in Qdrant to match current Firestore party_ids.

    Body (JSON):
      dry_run: bool (default true) — preview without modifying anything
      only: str|null — if set, only migrate this one old namespace (e.g. "la-france-insoumise")
      snapshot: bool (default true) — create a Qdrant snapshot before migrating
    """
    from qdrant_client.models import (
        Filter, FieldCondition, MatchValue,
    )

    data = await request.json() if request.can_read_body else {}
    dry_run = data.get("dry_run", True)
    only = data.get("only")
    do_snapshot = data.get("snapshot", True)

    migration_map = NAMESPACE_MIGRATION_MAP
    if only:
        if only not in migration_map:
            return web.json_response(
                {"error": f"Unknown old namespace '{only}'. Valid: {list(migration_map.keys())}"},
                status=400,
            )
        migration_map = {only: migration_map[only]}

    report: dict = {"dry_run": dry_run, "snapshot": None, "migrations": []}

    # --- Step 0: Snapshot ---
    if do_snapshot and not dry_run:
        try:
            snapshot_info = qdrant_client.create_snapshot(
                collection_name=PARTY_INDEX_NAME,
            )
            report["snapshot"] = {
                "status": "created",
                "name": snapshot_info.name,
                "collection": PARTY_INDEX_NAME,
            }
            logger.info(f"Pre-migration snapshot created: {snapshot_info.name}")
        except Exception as e:
            logger.error(f"Snapshot failed: {e}", exc_info=True)
            return web.json_response(
                {"error": f"Snapshot failed — aborting migration: {e}"},
                status=500,
            )
    elif dry_run:
        report["snapshot"] = {"status": "skipped (dry_run)"}

    # --- Step 1: For each old→new mapping, count and optionally rename ---
    for old_ns, new_ns in migration_map.items():
        ns_filter = Filter(must=[
            FieldCondition(key="metadata.namespace", match=MatchValue(value=old_ns)),
        ])

        # Count points with old namespace
        count = qdrant_client.count(
            collection_name=PARTY_INDEX_NAME,
            count_filter=ns_filter,
            exact=True,
        ).count

        entry: dict = {
            "old_namespace": old_ns,
            "new_namespace": new_ns,
            "points_found": count,
            "status": "skipped" if count == 0 else ("would_migrate" if dry_run else "pending"),
        }

        if count > 0 and not dry_run:
            try:
                # Scroll matching points and update metadata in-place.
                # After each batch, updated points no longer match the
                # old_ns filter, so we always scroll from offset=None.
                migrated = 0
                while True:
                    points, _ = qdrant_client.scroll(
                        collection_name=PARTY_INDEX_NAME,
                        scroll_filter=ns_filter,
                        limit=100,
                        with_payload=True,
                        with_vectors=False,
                    )
                    if not points:
                        break
                    for p in points:
                        meta = (p.payload or {}).get("metadata", {})
                        meta["namespace"] = new_ns
                        meta["party_ids"] = [new_ns]
                        qdrant_client.set_payload(
                            collection_name=PARTY_INDEX_NAME,
                            payload={"metadata": meta},
                            points=[p.id],
                        )
                    migrated += len(points)
                entry["status"] = "migrated"
                entry["points_migrated"] = migrated
                logger.info(f"Migrated {migrated} points: {old_ns} → {new_ns}")
            except Exception as e:
                entry["status"] = f"error: {e}"
                logger.error(f"Migration failed for {old_ns} → {new_ns}: {e}", exc_info=True)

        report["migrations"].append(entry)

    # --- Step 2: Invalidate namespace cache ---
    if not dry_run:
        import src.vector_store_helper as _vsh
        _vsh._manifesto_namespaces = None
        report["cache_invalidated"] = True

    return web.json_response(report)


@routes.post(route_prefix + "/admin/index-candidate-website/{candidate_id}")
async def admin_index_candidate_website(request):
    """Admin endpoint to trigger indexation of a specific candidate's website."""
    candidate_id = request.match_info["candidate_id"]
    logger.info(f"Admin triggered: indexing website for candidate {candidate_id}")

    try:
        count = await index_candidate_by_id(candidate_id)

        if count > 0:
            return web.json_response(
                {
                    "status": "success",
                    "message": f"Indexed {count} chunks for candidate {candidate_id}",
                }
            )
        else:
            return web.json_response(
                {
                    "status": "warning",
                    "message": f"No chunks indexed for candidate {candidate_id}. Check if website URL exists.",
                }
            )
    except Exception as e:
        logger.error(f"Error indexing website for {candidate_id}: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500,
        )


@routes.post(route_prefix + "/admin/index-candidate-profession/{candidate_id}")
async def admin_index_candidate_profession(request):
    """Admin endpoint to re-index a candidate's profession de foi from its PDF URL."""
    candidate_id = request.match_info["candidate_id"]
    logger.info(f"Admin triggered: indexing profession de foi for candidate {candidate_id}")

    try:
        from src.firebase_service import aget_candidate_by_id
        candidate = await aget_candidate_by_id(candidate_id)
        if candidate is None:
            return web.json_response(
                {"status": "error", "message": f"Candidate {candidate_id} not found"},
                status=404,
            )

        pdf_url = getattr(candidate, "manifesto_pdf_url", "") or ""
        if not pdf_url:
            return web.json_response(
                {"status": "warning", "message": f"No manifesto_pdf_url for {candidate_id}"},
            )

        # Download PDF to temp file
        import tempfile
        import aiohttp as _aiohttp
        async with _aiohttp.ClientSession() as session:
            async with session.get(pdf_url) as resp:
                if resp.status != 200:
                    return web.json_response(
                        {"status": "error", "message": f"Failed to download PDF: HTTP {resp.status}"},
                        status=502,
                    )
                pdf_bytes = await resp.read()

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        from src.services.profession_indexer import index_candidate_profession
        count = await index_candidate_profession(candidate_id, tmp_path)

        import os
        os.unlink(tmp_path)

        if count > 0:
            return web.json_response(
                {"status": "success", "message": f"Indexed {count} profession de foi chunks for {candidate_id}"}
            )
        else:
            return web.json_response(
                {"status": "warning", "message": f"No chunks indexed for {candidate_id} profession de foi"}
            )
    except Exception as e:
        logger.error(f"Error indexing profession for {candidate_id}: {e}", exc_info=True)
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@routes.get(f"{route_prefix}/admin/listener-status")
async def admin_listener_status(request):
    """Check if the Firestore listeners are running."""
    return web.json_response(
        {
            "parties_listener_running": is_listener_running(),
            "candidates_listener_running": is_candidates_listener_running(),
        }
    )


@routes.post(f"{route_prefix}/admin/reset-rate-limit")
async def admin_reset_rate_limit(request):
    """Reset the LLM rate limit status (both in memory and Firestore)."""
    logger.info("Admin triggered: resetting LLM rate limit status")
    try:
        await reset_all_rate_limits()
        return web.json_response(
            {
                "status": "success",
                "message": "LLM rate limit status reset (memory + Firestore)",
            }
        )
    except Exception as e:
        logger.error(f"Error resetting rate limit status: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500,
        )


# ---------------------------------------------------------------------------
# Document upload endpoints (secret-protected)
# ---------------------------------------------------------------------------
# In-memory cache for preview file data (cleared after confirm or timeout)
_upload_file_cache: dict[str, bytes] = {}

# Cached set of target commune codes (from municipalities collection)
_target_commune_codes: set[str] | None = None


async def _get_target_commune_codes() -> set[str]:
    """Return the set of municipality codes from the municipalities collection (cached)."""
    global _target_commune_codes
    if _target_commune_codes is not None:
        return _target_commune_codes
    codes: set[str] = set()
    async for doc in async_db.collection("municipalities").select(["code"]).stream():
        d = doc.to_dict() or {}
        code = d.get("code")
        if code:
            codes.add(code)
    _target_commune_codes = codes
    logger.info("[upload-targets] cached %d target commune codes", len(codes))
    return codes


@routes.post(route_prefix + "/admin/upload")
async def admin_upload(request: web.Request) -> web.Response:
    """Upload one or more PDF/TXT files for auto-classification and indexing.

    Supports mode=preview (dry-run) via form field or query param.
    """
    if not _check_admin_secret(request):
        raise web.HTTPNotFound()

    # Check mode from query param first; may be overridden by form field
    mode = request.query.get("mode", "process")  # "preview" or "process"
    source_url: str | None = request.query.get("source_url")
    source_type: str | None = request.query.get("source_type")

    reader = await request.multipart()
    jobs: list[dict] = []

    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "mode":
            mode = (await part.read(decode=True)).decode()
            continue
        if part.name == "source_url":
            source_url = (await part.read(decode=True)).decode()
            continue
        if part.name == "source_type":
            source_type = (await part.read(decode=True)).decode()
            continue
        if part.filename is None:
            continue  # skip non-file fields

        filename = part.filename
        data = await part.read(decode=False)

        if not data:
            jobs.append({"filename": filename, "error": "Empty file"})
            continue

        job_id = create_job(filename)
        file_size = len(data)

        if mode == "preview":
            preview = await preview_upload(job_id, filename, data, source_url=source_url, source_type=source_type)
            _upload_file_cache[job_id] = data
            current = get_job(job_id) or {}
            job_entry: dict = {
                "job_id": job_id,
                "filename": filename,
                "status": current.get("status", "preview"),
                "preview": preview,
            }
            if current.get("error"):
                job_entry["error"] = current["error"]
            jobs.append(job_entry)
        else:
            # Small files (<5MB): process inline; larger ones: background task
            if file_size < 5 * 1024 * 1024:
                try:
                    await process_upload(job_id, filename, data)
                except Exception as e:
                    logger.error(f"Upload processing error for {filename}: {e}", exc_info=True)
            else:
                asyncio.create_task(process_upload(job_id, filename, data))

            current = get_job(job_id) or {}
            jobs.append({"job_id": job_id, "filename": filename, "status": current.get("status", "pending")})

    if not jobs:
        return web.json_response(
            {"status": "error", "message": "No files found in request"},
            status=400,
        )

    return web.json_response({"status": "accepted", "jobs": jobs})


@routes.post(route_prefix + "/admin/upload-text")
async def admin_upload_text(request: web.Request) -> web.Response:
    """Upload raw pasted text for preview and indexing.

    Accepts JSON: {"text": "...", "title": "...", "mode": "preview"|"process"}
    """
    if not _check_admin_secret(request):
        raise web.HTTPNotFound()

    body = await request.json()
    text = body.get("text", "").strip()
    title = body.get("title", "Pasted text").strip() or "Pasted text"
    mode = body.get("mode", "preview")

    if not text or len(text) < 50:
        return web.json_response(
            {"status": "error", "message": "Text is too short (min 50 chars)"},
            status=400,
        )

    # Create a .txt file from the text
    filename = f"{title}.txt"
    data = text.encode("utf-8")

    job_id = create_job(filename)

    if mode == "preview":
        preview = await preview_upload(job_id, filename, data)
        _upload_file_cache[job_id] = data
        current = get_job(job_id) or {}
        return web.json_response({
            "status": "accepted",
            "jobs": [{
                "job_id": job_id,
                "filename": filename,
                "status": current.get("status", "preview"),
                "preview": preview,
            }],
        })
    else:
        await process_upload(job_id, filename, data)
        current = get_job(job_id) or {}
        return web.json_response({
            "status": "accepted",
            "jobs": [{"job_id": job_id, "filename": filename, "status": current.get("status", "pending")}],
        })


@routes.get(route_prefix + "/admin/upload-targets")
async def admin_upload_targets(request: web.Request) -> web.Response:
    """Return available assignment targets for manual source selection."""
    if not _check_admin_secret(request):
        raise web.HTTPNotFound()

    parties = await aget_parties()

    targets = []
    for p in parties:
        targets.append({
            "type": "party",
            "id": p.party_id,
            "name": p.name,
            "abbreviation": getattr(p, "abbreviation", None),
        })

    # Only return candidates from target communes (municipalities collection)
    target_codes = await _get_target_commune_codes()
    candidates = await aget_candidates()
    for c in candidates:
        if c.municipality_code and c.municipality_code in target_codes:
            targets.append({
                "type": "candidate",
                "id": c.candidate_id,
                "name": c.full_name,
                "municipality": c.municipality_name or c.municipality_code or "",
                "party_ids": c.party_ids if hasattr(c, "party_ids") else [],
            })

    return web.json_response({"targets": targets})


@routes.post(route_prefix + "/admin/upload-confirm/{job_id}")
async def admin_upload_confirm(request: web.Request) -> web.Response:
    """Confirm a previewed upload job and proceed with indexing."""
    if not _check_admin_secret(request):
        raise web.HTTPNotFound()

    job_id = request.match_info["job_id"]
    job = get_job(job_id)
    if job is None:
        return web.json_response({"error": "Job not found"}, status=404)

    if job.get("status") != "preview":
        return web.json_response(
            {"error": f"Job is not in preview state (current: {job.get('status')})"},
            status=400,
        )

    data = _upload_file_cache.pop(job_id, None)
    if data is None:
        return web.json_response(
            {"error": "File data expired. Please re-upload."},
            status=410,
        )

    # Parse optional manual override from JSON body
    body: dict = {}
    try:
        body = await request.json()
    except Exception:
        pass

    manual_type = body.get("target_type")
    manual_id = body.get("target_id")
    source_url = body.get("source_url")
    source_type = body.get("source_type")

    filename = job["filename"]

    # Run confirmation in background for large files
    if len(data) < 5 * 1024 * 1024:
        await confirm_upload(job_id, filename, data, manual_type, manual_id, source_url=source_url, source_type=source_type)
    else:
        asyncio.create_task(confirm_upload(job_id, filename, data, manual_type, manual_id, source_url=source_url, source_type=source_type))

    current = get_job(job_id) or {}
    return web.json_response({
        "status": "confirmed",
        "job_id": job_id,
        "current_status": current.get("status"),
    })


@routes.get(route_prefix + "/admin/upload-status")
async def admin_upload_status(request: web.Request) -> web.Response:
    """Return status of all upload jobs."""
    if not _check_admin_secret(request):
        raise web.HTTPNotFound()
    return web.json_response({"jobs": get_all_jobs()})


@routes.get(route_prefix + "/admin/upload-status/{job_id}")
async def admin_upload_job_status(request: web.Request) -> web.Response:
    """Return status of a single upload job. Supports SSE via Accept header."""
    if not _check_admin_secret(request):
        raise web.HTTPNotFound()

    job_id = request.match_info["job_id"]
    job = get_job(job_id)
    if job is None:
        return web.json_response(
            {"status": "error", "message": "Job not found"}, status=404
        )

    # SSE streaming if client requests it
    if "text/event-stream" in request.headers.get("Accept", ""):
        resp = web.StreamResponse()
        resp.content_type = "text/event-stream"
        resp.headers["Cache-Control"] = "no-cache"
        resp.headers["X-Accel-Buffering"] = "no"
        await resp.prepare(request)

        # Poll and stream updates until terminal state
        max_wait = 300  # 5 min timeout
        start = time.monotonic()
        while (time.monotonic() - start) < max_wait:
            current = get_job(job_id)
            if current is None:
                break
            await resp.write(f"data: {json.dumps(current)}\n\n".encode())
            if current["status"] in ("done", "error"):
                break
            await asyncio.sleep(1)

        return resp

    return web.json_response(job)


@routes.get(f"{route_prefix}/admin/debug-qdrant")
async def admin_debug_qdrant(request):
    """Debug endpoint to check Qdrant collection status."""
    try:
        # Get collection info
        collection_info = qdrant_client.get_collection(PARTY_INDEX_NAME)

        # Get a sample of points
        points = qdrant_client.scroll(
            collection_name=PARTY_INDEX_NAME,
            limit=5,
            with_payload=True,
            with_vectors=False,
        )

        sample_docs = []
        for point in points[0]:
            payload = point.payload or {}
            sample_docs.append(
                {
                    "id": str(point.id),
                    "metadata": payload.get("metadata", {}),
                    "content_preview": (payload.get("page_content", "")[:200] + "...")
                    if payload.get("page_content")
                    else "No content",
                }
            )

        return web.json_response(
            {
                "collection_name": PARTY_INDEX_NAME,
                "points_count": collection_info.points_count,
                "vectors_count": getattr(collection_info, "vectors_count", collection_info.points_count),
                "sample_documents": sample_docs,
            }
        )
    except Exception as e:
        logger.error(f"Error debugging Qdrant: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500,
        )


@routes.get(f"{route_prefix}/admin/debug-candidates-qdrant")
async def admin_debug_candidates_qdrant(request):
    """Debug endpoint to check Qdrant candidates collection status."""
    try:
        # Get collection info (get_collection resolves aliases automatically)
        try:
            collection_info = qdrant_client.get_collection(CANDIDATES_INDEX_NAME)
        except Exception:
            collections = qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]
            return web.json_response(
                {
                    "status": "warning",
                    "message": f"Collection {CANDIDATES_INDEX_NAME} does not exist yet",
                    "available_collections": collection_names,
                }
            )

        # Get a sample of points
        points = qdrant_client.scroll(
            collection_name=CANDIDATES_INDEX_NAME,
            limit=10,
            with_payload=True,
            with_vectors=False,
        )

        sample_docs = []
        for point in points[0]:
            payload = point.payload or {}
            metadata = payload.get("metadata", {})
            sample_docs.append(
                {
                    "id": str(point.id),
                    "candidate_name": metadata.get("candidate_name", "Unknown"),
                    "candidate_id": metadata.get("candidate_id", "Unknown"),
                    "municipality_code": metadata.get("municipality_code", ""),
                    "url": metadata.get("url", ""),
                    "content_preview": (payload.get("page_content", "")[:300] + "...")
                    if payload.get("page_content")
                    else "No content",
                }
            )

        return web.json_response(
            {
                "collection_name": CANDIDATES_INDEX_NAME,
                "points_count": collection_info.points_count,
                "vectors_count": getattr(collection_info, "vectors_count", collection_info.points_count),
                "sample_documents": sample_docs,
            }
        )
    except Exception as e:
        logger.error(f"Error debugging candidates Qdrant: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500,
        )


@routes.post(f"{route_prefix}/admin/test-rag-search")
async def admin_test_rag_search(request):
    """Test RAG search for a party."""
    try:
        data = await request.json()
        party_id = data.get("party_id", "lfi")
        query = data.get("query", "résumé du programme")

        from qdrant_client.models import Filter, FieldCondition, MatchValue

        # Get query vector
        query_vector = await embed.aembed_query(query)

        # Search with filter
        filter_condition = Filter(
            must=[
                FieldCondition(
                    key="metadata.namespace", match=MatchValue(value=party_id)
                )
            ]
        )

        _query_response = qdrant_client.query_points(
            collection_name=PARTY_INDEX_NAME,
            query=query_vector,
            using="dense",
            limit=5,
            with_payload=True,
            query_filter=filter_condition,
            score_threshold=0.3,
        )
        results = _query_response.points

        docs = []
        for point in results:
            payload = point.payload or {}
            docs.append(
                {
                    "score": round(point.score, 4) if point.score is not None else None,
                    "metadata": payload.get("metadata", {}),
                    "content_preview": (payload.get("page_content", "")[:300] + "...")
                    if payload.get("page_content")
                    else "No content",
                }
            )

        return web.json_response(
            {
                "party_id": party_id,
                "query": query,
                "results_count": len(docs),
                "documents": docs,
            }
        )
    except Exception as e:
        logger.error(f"Error testing RAG search: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500,
        )


@routes.get(f"{route_prefix}/admin/municipalities")
async def admin_list_municipalities(request):
    """List all municipalities from Firestore."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    results = []
    async for doc in async_db.collection("municipalities").select(["code", "nom", "name", "population"]).stream():
        d = doc.to_dict() or {}
        results.append({
            "code": d.get("code") or doc.id,
            "name": d.get("nom", d.get("name", "")),
            "population": d.get("population", 0),
        })
    results.sort(key=lambda x: (-x["population"], x["name"]))
    return web.json_response({"municipalities": results})


@routes.post(f"{route_prefix}/admin/multi-query")
async def admin_multi_query(request):
    """Run the same RAG search as the chat across multiple municipalities and report coverage."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        data = await request.json()
    except Exception:
        return web.json_response({"status": "error", "message": "Invalid JSON body"}, status=400)

    query = data.get("query", "")
    if not query:
        return web.json_response({"status": "error", "message": "query is required"}, status=400)

    municipality_codes: list[str] = data.get("municipality_codes") or []
    top_n: int | None = data.get("top_n")
    score_threshold: float = float(data.get("score_threshold", 0.5))

    # Fetch all parties once (needed to build party_ids_to_search per commune)
    all_parties = await aget_parties()

    # If top_n provided without explicit codes, auto-select top N by population
    if not municipality_codes and top_n:
        top_n = min(int(top_n), 100)
        munis = []
        async for muni_doc in (
            async_db.collection("municipalities")
            .order_by("population", direction=firestore.Query.DESCENDING)  # noqa: F821
            .limit(top_n)
            .stream()
        ):
            d = muni_doc.to_dict() or {}
            munis.append(d.get("code") or muni_doc.id)
        municipality_codes = munis

    if not municipality_codes:
        return web.json_response(
            {
                "status": "error",
                "message": "municipality_codes or top_n is required",
            },
            status=400,
        )

    # Improve the query once (same LLM call the chat would do) — skip for speed,
    # just use raw query directly (no reranking requested by spec).
    rag_query = query

    semaphore = asyncio.Semaphore(3)

    async def _process_municipality(municipality_code: str) -> dict:
        async with semaphore:
            try:
                t_muni = time.perf_counter()
                # Fetch candidates for this commune
                candidates = await aget_candidates_by_municipality(municipality_code)

                municipality_name = candidates[0].municipality_name if candidates else ""
                if not municipality_name:
                    # Try to resolve name from Firestore municipalities collection
                    async for muni_doc in (
                        async_db.collection("municipalities")
                        .where("code", "==", municipality_code)
                        .select(["nom", "name"])
                        .limit(1)
                        .stream()
                    ):
                        d = muni_doc.to_dict() or {}
                        municipality_name = d.get("nom", d.get("name", ""))
                        break

                # Determine party_ids_to_search (same logic as websocket_app lines 1016-1027)
                local_party_ids: set[str] = set()
                for candidate in candidates:
                    for pid in candidate.party_ids:
                        local_party_ids.add(pid)
                party_ids_to_search = (
                    list(local_party_ids) if local_party_ids else [p.party_id for p in all_parties]
                )

                # Run combined RAG search (manifesto by party, candidate by candidate_ids)
                candidate_ids_list = [c.candidate_id for c in candidates]

                manifesto_docs, candidate_docs = await identify_relevant_docs_combined(
                    rag_query=rag_query,
                    chat_history="",
                    user_message=query,
                    party_ids=party_ids_to_search,
                    candidate_ids=candidate_ids_list,
                    scope="local",
                    municipality_code=municipality_code,
                    score_threshold=score_threshold,
                )

                # Map candidate chunks back to candidate details
                candidate_chunk_map: dict[str, dict] = {}
                for doc in candidate_docs:
                    meta = doc.metadata if hasattr(doc, "metadata") else {}
                    # candidate_ids is stored as a list in metadata
                    cids = meta.get("candidate_ids", [])
                    cid = cids[0] if cids else meta.get("candidate_id", meta.get("namespace", ""))
                    cname = meta.get("candidate_name", cid)
                    preview = (doc.page_content[:200] + "...") if hasattr(doc, "page_content") and doc.page_content else ""
                    if cid not in candidate_chunk_map:
                        candidate_chunk_map[cid] = {
                            "candidate_id": cid,
                            "candidate_name": cname,
                            "chunk_count": 0,
                            "chunks_preview": [],
                        }
                    candidate_chunk_map[cid]["chunk_count"] += 1
                    if len(candidate_chunk_map[cid]["chunks_preview"]) < 3:
                        candidate_chunk_map[cid]["chunks_preview"].append(preview)

                all_candidate_ids = {c.candidate_id for c in candidates}
                candidates_with_chunks = len(candidate_chunk_map)
                candidates_without_chunks = len(all_candidate_ids) - len(
                    all_candidate_ids & set(candidate_chunk_map.keys())
                )

                # Add candidates without chunks to the details list
                for candidate in candidates:
                    if candidate.candidate_id not in candidate_chunk_map:
                        name = getattr(candidate, "candidate_name", "") or getattr(candidate, "name", "") or candidate.candidate_id
                        candidate_chunk_map[candidate.candidate_id] = {
                            "candidate_id": candidate.candidate_id,
                            "candidate_name": name,
                            "chunk_count": 0,
                            "chunks_preview": [],
                        }

                # Sort: candidates with chunks first, then without
                sorted_details = sorted(
                    candidate_chunk_map.values(),
                    key=lambda x: (-x["chunk_count"], x["candidate_name"]),
                )

                return {
                    "municipality_code": municipality_code,
                    "municipality_name": municipality_name,
                    "total_candidates": len(candidates),
                    "candidates_with_chunks": candidates_with_chunks,
                    "candidates_without_chunks": candidates_without_chunks,
                    "manifesto_chunks": len(manifesto_docs),
                    "candidate_chunks": len(candidate_docs),
                    "candidate_details": sorted_details,
                    "elapsed_seconds": round(time.perf_counter() - t_muni, 2),
                }
            except Exception as e:
                logger.error(f"Error processing municipality {municipality_code}: {e}", exc_info=True)
                return {
                    "municipality_code": municipality_code,
                    "municipality_name": "",
                    "error": str(e),
                }

    # Run in batches of 5 to avoid overwhelming Qdrant/embeddings
    results = []
    batch_size = 5
    for i in range(0, len(municipality_codes), batch_size):
        batch = municipality_codes[i : i + batch_size]
        batch_results = await asyncio.gather(*[_process_municipality(code) for code in batch])
        results.extend(batch_results)

    # Compute aggregate stats
    successful = [r for r in results if "error" not in r]
    communes_with_manifesto = sum(1 for r in successful if r.get("manifesto_chunks", 0) > 0)
    communes_with_candidates = sum(1 for r in successful if r.get("candidate_chunks", 0) > 0)
    communes_with_no_data = sum(1 for r in successful if r.get("manifesto_chunks", 0) == 0 and r.get("candidate_chunks", 0) == 0)
    total_manifesto = sum(r.get("manifesto_chunks", 0) for r in successful)
    total_candidate = sum(r.get("candidate_chunks", 0) for r in successful)
    n = max(len(successful), 1)

    return web.json_response(
        {
            "query": query,
            "score_threshold": score_threshold,
            "total_communes": len(municipality_codes),
            "results": results,
            "aggregate": {
                "communes_with_manifesto": communes_with_manifesto,
                "communes_with_candidates": communes_with_candidates,
                "communes_with_no_data": communes_with_no_data,
                "total_manifesto_chunks": total_manifesto,
                "total_candidate_chunks": total_candidate,
                "avg_manifesto_chunks": round(total_manifesto / n, 1),
                "avg_candidate_chunks": round(total_candidate / n, 1),
                "errors": len(results) - len(successful),
            },
        }
    )


@routes.post(f"{route_prefix}/experiment/search")
async def experiment_search(request):
    """Search Qdrant with full chunk metadata filters (dev/experiment tool)."""
    try:
        data = await request.json()
        query = data.get("query", "")
        if not query:
            return web.json_response(
                {"status": "error", "message": "query is required"}, status=400
            )

        collection = data.get("collection", "parties")
        theme = data.get("theme")
        max_fiabilite = data.get("max_fiabilite", 4)
        party_id = data.get("party_id")
        nuance_politique = data.get("nuance_politique")
        municipality_code = data.get("municipality_code")
        limit = min(data.get("limit", 10), 30)

        from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

        col_name = CANDIDATES_INDEX_NAME if collection == "candidates" else PARTY_INDEX_NAME

        query_vector = await embed.aembed_query(query)

        must_conditions = []
        must_not_conditions = []
        if party_id:
            must_conditions.append(
                FieldCondition(key="metadata.namespace", match=MatchValue(value=party_id))
            )
        if theme:
            must_conditions.append(
                FieldCondition(key="metadata.theme", match=MatchValue(value=theme))
            )
        if nuance_politique:
            must_conditions.append(
                FieldCondition(key="metadata.nuance_politique", match=MatchValue(value=nuance_politique))
            )
        if municipality_code:
            must_conditions.append(
                FieldCondition(key="metadata.municipality_code", match=MatchValue(value=municipality_code))
            )
        if max_fiabilite < 4:
            must_not_conditions.append(
                FieldCondition(key="metadata.fiabilite", range=Range(gt=max_fiabilite))
            )

        query_filter = None
        if must_conditions or must_not_conditions:
            query_filter = Filter(
                must=must_conditions or None,
                must_not=must_not_conditions or None,
            )

        _query_response = qdrant_client.query_points(
            collection_name=col_name,
            query=query_vector,
            using="dense",
            limit=limit,
            with_payload=True,
            query_filter=query_filter,
            score_threshold=0.3,
        )
        results = _query_response.points

        docs = []
        for point in results:
            payload = point.payload or {}
            docs.append({
                "score": round(point.score, 4) if point.score is not None else None,
                "content": payload.get("page_content", ""),
                "metadata": payload.get("metadata", {}),
            })

        return web.json_response({
            "query": query,
            "collection": collection,
            "filters": {
                "theme": theme, "max_fiabilite": max_fiabilite, "party_id": party_id,
                "nuance_politique": nuance_politique, "municipality_code": municipality_code,
            },
            "results_count": len(docs),
            "results": docs,
        })
    except Exception as e:
        logger.error(f"Error in experiment search: {e}", exc_info=True)
        return web.json_response({"status": "error", "message": str(e)}, status=500)


@routes.get(f"{route_prefix}/experiment/metadata-schema")
async def experiment_metadata_schema(request):
    """Return the chunk metadata schema, theme taxonomy, and fiabilite levels."""
    from src.models.chunk_metadata import THEME_TAXONOMY, Fiabilite

    # Get available namespaces and nuance_politique values from both collections
    namespaces = set()
    nuances = set()
    for col_name in [PARTY_INDEX_NAME, CANDIDATES_INDEX_NAME]:
        try:
            points = qdrant_client.scroll(
                collection_name=col_name, limit=100,
                with_payload=["metadata.namespace", "metadata.nuance_politique"], with_vectors=False,
            )
            for p in points[0]:
                meta = (p.payload or {}).get("metadata", {})
                ns = meta.get("namespace")
                if ns:
                    namespaces.add(ns)
                np_val = meta.get("nuance_politique")
                if np_val:
                    nuances.add(np_val)
        except Exception as exc:
            logger.warning(
                f"Failed to scroll {col_name} for metadata schema: "
                f"{type(exc).__name__}: {exc!r}"
            )

    return web.json_response({
        "themes": THEME_TAXONOMY,
        "fiabilite_levels": {str(f.value): f.name for f in Fiabilite},
        "namespaces": sorted(namespaces),
        "nuances_politiques": sorted(nuances),
        "collections": ["parties", "candidates"],
    })


@routes.get(f"{route_prefix}/experiment/topic-stats")
async def experiment_topic_stats(request):
    """Aggregate theme distribution across all indexed chunks."""
    from collections import defaultdict

    theme_data: dict[str, dict] = {}
    collection_stats = {}
    total_chunks = 0
    classified_chunks = 0
    # Track per-candidate chunk counts (from candidates collection only)
    candidate_chunks: dict[str, int] = {}
    candidate_manifesto_chunks: dict[str, int] = {}
    candidate_uploaded_chunks: dict[str, int] = {}

    for col_name in [PARTY_INDEX_NAME, CANDIDATES_INDEX_NAME]:
        col_total = 0
        col_classified = 0
        try:
            offset = None
            while True:
                points, next_offset = qdrant_client.scroll(
                    collection_name=col_name,
                    limit=256,
                    offset=offset,
                    with_payload=[
                        "metadata.theme", "metadata.sub_theme",
                        "metadata.source_document", "metadata.party_name",
                        "metadata.fiabilite", "metadata.namespace",
                    ],
                    with_vectors=False,
                )
                for p in points:
                    meta = (p.payload or {}).get("metadata", {})
                    col_total += 1
                    # Count chunks per candidate namespace (candidates collection only)
                    if col_name == CANDIDATES_INDEX_NAME:
                        ns = meta.get("namespace", "")
                        if ns:
                            candidate_chunks[ns] = candidate_chunks.get(ns, 0) + 1
                            src_doc = meta.get("source_document")
                            if src_doc == "profession_de_foi":
                                candidate_manifesto_chunks[ns] = candidate_manifesto_chunks.get(ns, 0) + 1
                            elif src_doc == "uploaded_document":
                                candidate_uploaded_chunks[ns] = candidate_uploaded_chunks.get(ns, 0) + 1
                    theme = meta.get("theme")
                    if not theme:
                        continue
                    col_classified += 1

                    if theme not in theme_data:
                        theme_data[theme] = {
                            "theme": theme,
                            "count": 0,
                            "by_party": defaultdict(int),
                            "by_source": defaultdict(int),
                            "by_fiabilite": defaultdict(int),
                            "sub_themes": {},
                        }
                    td = theme_data[theme]
                    td["count"] += 1
                    party = meta.get("namespace") or meta.get("party_name")
                    if party:
                        td["by_party"][party] += 1
                    src = meta.get("source_document")
                    if src:
                        td["by_source"][src] += 1
                    fiab = meta.get("fiabilite")
                    if fiab is not None:
                        td["by_fiabilite"][str(int(fiab))] += 1
                    sub = meta.get("sub_theme")
                    if sub:
                        if sub not in td["sub_themes"]:
                            td["sub_themes"][sub] = {"count": 0, "by_party": defaultdict(int)}
                        td["sub_themes"][sub]["count"] += 1
                        if party:
                            td["sub_themes"][sub]["by_party"][party] += 1

                if next_offset is None:
                    break
                offset = next_offset
        except Exception as e:
            logger.error(f"Error scrolling {col_name}: {e}", exc_info=True)

        total_chunks += col_total
        classified_chunks += col_classified
        collection_stats[col_name] = {"total": col_total, "classified": col_classified}

    themes_list = []
    for td in sorted(theme_data.values(), key=lambda x: x["count"], reverse=True):
        themes_list.append({
            "theme": td["theme"],
            "count": td["count"],
            "percentage": round(td["count"] / classified_chunks * 100, 1) if classified_chunks else 0,
            "by_party": dict(td["by_party"]),
            "by_source": dict(td["by_source"]),
            "by_fiabilite": dict(td["by_fiabilite"]),
            "sub_themes": [
                {"name": st, "count": data["count"], "by_party": dict(data["by_party"])}
                for st, data in sorted(td["sub_themes"].items(), key=lambda x: -x[1]["count"])
            ],
        })

    return web.json_response({
        "total_chunks": total_chunks,
        "classified_chunks": classified_chunks,
        "unclassified_chunks": total_chunks - classified_chunks,
        "themes": themes_list,
        "collections": collection_stats,
        "candidate_chunks": candidate_chunks,
        "candidate_manifesto_chunks": candidate_manifesto_chunks,
        "candidate_uploaded_chunks": candidate_uploaded_chunks,
    })


LEGAL_BOILERPLATE = [
    "mentions légales", "mention légale", "politique de confidentialité",
    "cookies", "rgpd", "cgu", "conditions générales",
    "protection des données", "données personnelles",
    "informations légales", "copyright", "tous droits réservés",
]


@routes.get(f"{route_prefix}/commune/{{code}}/candidate-chunks")
async def commune_candidate_chunks(request):
    """Return per-candidate chunk detail for a given commune (lazy-loaded)."""
    from collections import defaultdict
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    code = request.match_info["code"]
    loop = asyncio.get_event_loop()

    qdrant_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.municipality_code",
                match=MatchValue(value=code),
            )
        ]
    )

    # ── 1. Scroll Qdrant for candidates_websites + all_parties ───────────────
    def _scroll_chunks():
        """Scroll both Qdrant collections and group by namespace."""
        chunks_by_ns: dict[str, list[dict]] = defaultdict(list)

        for col_name in [CANDIDATES_INDEX_NAME, PARTY_INDEX_NAME]:
            try:
                offset = None
                while True:
                    points, next_offset = qdrant_client.scroll(
                        collection_name=col_name,
                        scroll_filter=qdrant_filter,
                        limit=250,
                        offset=offset,
                        with_payload=True,
                        with_vectors=False,
                    )
                    for p in points:
                        payload = p.payload or {}
                        meta = payload.get("metadata", {})
                        ns = meta.get("namespace")
                        if not ns:
                            continue
                        chunks_by_ns[ns].append({
                            "page_content": payload.get("page_content", ""),
                            "source_document": meta.get("source_document", ""),
                            "theme": meta.get("theme"),
                            "fiabilite": meta.get("fiabilite"),
                            "url": meta.get("url", ""),
                            "collection": col_name,
                        })
                    if next_offset is None:
                        break
                    offset = next_offset
            except Exception as exc:
                logger.warning(
                    f"Failed to scroll {col_name} for commune {code}: "
                    f"{type(exc).__name__}: {exc!r}"
                )

        return dict(chunks_by_ns)

    # ── 2. Fetch Firestore candidates for this commune ────────────────────────
    def _fetch_candidates():
        result: dict[str, dict] = {}
        try:
            for doc in db.collection("candidates").where("commune_code", "==", code).stream():
                d = doc.to_dict() or {}
                result[doc.id] = d
        except Exception as exc:
            logger.warning(
                f"Failed to fetch candidates for commune {code}: "
                f"{type(exc).__name__}: {exc!r}"
            )
        return result

    chunks_by_ns, fs_candidates = await asyncio.gather(
        loop.run_in_executor(None, _scroll_chunks),
        loop.run_in_executor(None, _fetch_candidates),
    )

    # ── 2b. Build Drive slug→folder_id map (single API call) ─────────────────
    _drive_root = "1rLVC3BTVKhOxxGu2GzIfq9BOexleIcRE"
    drive_slug_to_id: dict[str, str] = {}
    try:
        from src.services.data_pipeline.crawl_scraper import (
            CrawlScraperNode, _get_crawl_credentials, _slugify_url,
        )
        _creds = _get_crawl_credentials()
        _node = CrawlScraperNode()
        _token = _node._ensure_token(_creds)
        async with aiohttp.ClientSession() as _session:
            _subfolders = await _node._drive_list(
                _session, _drive_root, _token,
                mime_filter="application/vnd.google-apps.folder",
            )
        for sf in _subfolders:
            drive_slug_to_id[sf["name"]] = sf["id"]
    except Exception as exc:
        logger.warning("Drive subfolder listing failed (debug links will use root): %s", exc)

    # ── 3. Compute per-candidate stats ────────────────────────────────────────
    manifesto_keywords = ("profession_de_foi", "election_manifesto")

    def _is_junk(chunk: dict) -> str | None:
        """Return a junk reason string, or None if the chunk is good."""
        fiabilite = chunk.get("fiabilite")
        if fiabilite is not None and int(fiabilite) >= 4:
            return "low_fiabilite"
        if not chunk.get("theme"):
            return "no_theme"
        content = chunk.get("page_content", "")
        if len(content) < 100:
            return "too_short"
        content_lower = content.lower()
        if any(kw in content_lower for kw in LEGAL_BOILERPLATE):
            return "legal_boilerplate"
        return None

    candidates_out: list[dict] = []
    summary_total_chunks = 0
    summary_manifesto_chunks = 0
    summary_website_chunks = 0
    summary_good_chunks = 0
    summary_junk_chunks = 0

    # Union of all namespaces seen in Qdrant + Firestore
    all_ns: set[str] = set(chunks_by_ns.keys()) | set(fs_candidates.keys())

    for ns in sorted(all_ns):
        chunks = chunks_by_ns.get(ns, [])
        fs = fs_candidates.get(ns, {})

        manifesto_chunks = sum(
            1 for c in chunks
            if any(kw in c.get("source_document", "") for kw in manifesto_keywords)
        )
        website_chunks = len(chunks) - manifesto_chunks

        themes: dict[str, int] = defaultdict(int)
        sources: dict[str, int] = defaultdict(int)
        urls: list[str] = []
        junk_samples: list[dict] = []
        junk_count = 0

        for chunk in chunks:
            theme = chunk.get("theme")
            if theme:
                themes[theme] += 1
            src = chunk.get("source_document")
            if src:
                sources[src] += 1
            url = chunk.get("url", "")
            if url and url not in urls:
                urls.append(url)

            reason = _is_junk(chunk)
            if reason:
                junk_count += 1
                if len(junk_samples) < 3:
                    junk_samples.append({
                        "reason": reason,
                        "preview": chunk.get("page_content", "")[:200],
                    })

        good_count = len(chunks) - junk_count

        first_name = fs.get("first_name", "")
        last_name = fs.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or ns

        # Build debug links
        qdrant_url = os.environ["QDRANT_URL"]
        env = os.environ.get("ENV", "dev")
        firebase_project = "chat-vote-prod" if env == "prod" else "chat-vote-dev"
        qdrant_dashboard = f"{qdrant_url}/dashboard#/collections/{CANDIDATES_INDEX_NAME}"
        qdrant_query = f"{qdrant_url}/dashboard#/collections/{CANDIDATES_INDEX_NAME}/points?filter=metadata.namespace%3D%3D{ns}"
        firestore_url = f"https://console.firebase.google.com/project/{firebase_project}/firestore/databases/-default-/data/~2Fcandidates~2F{ns}"
        # Build candidate-level Drive folder link — direct subfolder if found
        website_url = fs.get("website_url") or ""
        drive_folder_url = f"https://drive.google.com/drive/folders/{_drive_root}"
        if website_url and drive_slug_to_id:
            _slug = _slugify_url(website_url)
            # Try exact match, then prefix match, then substring match
            _folder_id = drive_slug_to_id.get(_slug)
            if not _folder_id:
                _folder_id = next(
                    (fid for fname, fid in drive_slug_to_id.items()
                     if fname.startswith(_slug) or _slug in fname),
                    None,
                )
            if _folder_id:
                drive_folder_url = f"https://drive.google.com/drive/folders/{_folder_id}"

        candidates_out.append({
            "candidate_id": ns,
            "name": name,
            "party_label": fs.get("list_label") or fs.get("nuance_label", ""),
            "is_tete_de_liste": fs.get("is_tete_de_liste", False),
            "website_url": fs.get("website_url") or "",
            "manifesto_url": fs.get("manifesto_pdf_url") or fs.get("manifesto_url") or fs.get("election_manifesto_url") or "",
            "manifesto_pdf_path": fs.get("manifesto_pdf_path") or "",
            "has_manifesto": bool(fs.get("manifesto_pdf_url")),
            "has_scraped": fs.get("has_scraped", False),
            "scrape_chars": fs.get("scrape_chars") or 0,
            "total_chunks": len(chunks),
            "manifesto_chunks": manifesto_chunks,
            "website_chunks": website_chunks,
            "good_count": good_count,
            "junk_count": junk_count,
            "themes": dict(themes),
            "sources": dict(sources),
            "urls": urls,
            "junk_samples": junk_samples,
            "debug_links": {
                "qdrant_collection": qdrant_dashboard,
                "qdrant_points": qdrant_query,
                "firestore_doc": firestore_url,
                "drive_folder": drive_folder_url,
            },
        })

        summary_total_chunks += len(chunks)
        summary_manifesto_chunks += manifesto_chunks
        summary_website_chunks += website_chunks
        summary_good_chunks += good_count
        summary_junk_chunks += junk_count

    return web.json_response({
        "commune_code": code,
        "candidates": candidates_out,
        "summary": {
            "total_candidates": len(candidates_out),
            "total_chunks": summary_total_chunks,
            "manifesto_chunks": summary_manifesto_chunks,
            "website_chunks": summary_website_chunks,
            "good_chunks": summary_good_chunks,
            "junk_chunks": summary_junk_chunks,
        },
    })


async def _collect_user_messages(
    municipality_code: str | None = None,
) -> tuple[list[dict], set[str]]:
    """Collect user messages from Firestore, optionally filtered by commune.

    Returns (messages, session_ids) where each message has text, session_id,
    party_ids, chat_title.
    """
    def _sync_collect():
        query = db.collection("chat_sessions")
        if municipality_code:
            query = query.where("municipality_code", "==", municipality_code)

        session_ids: set[str] = set()
        user_messages: list[dict] = []
        for session in query.stream():
            session_data = session.to_dict() or {}
            session_id = session.id
            session_ids.add(session_id)
            party_ids = session_data.get("party_ids", [])
            title = session_data.get("title", "")

            messages_ref = (
                db.collection("chat_sessions")
                .document(session_id)
                .collection("messages")
                .order_by("created_at")
            )
            for msg_doc in messages_ref.stream():
                msg_data = msg_doc.to_dict() or {}
                if msg_data.get("role") != "user":
                    continue
                for item in msg_data.get("messages", []):
                    content = item.get("content", "").strip()
                    if content and len(content) > 10:
                        user_messages.append({
                            "text": content,
                            "session_id": session_id,
                            "party_ids": party_ids,
                            "chat_title": title,
                        })
        return user_messages, session_ids

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_collect)




@routes.get(f"{route_prefix}/experiment/candidate-coverage")
async def experiment_candidate_coverage(request):
    """Return chunk counts per candidate from Qdrant for RAG coverage tracking."""
    from src.services.candidate_indexer import _get_indexed_candidate_counts

    loop = asyncio.get_event_loop()
    counts = await loop.run_in_executor(None, _get_indexed_candidate_counts)
    return web.json_response({"candidate_chunks": counts})


# Keyword mapping for citizen message classification (commune dashboard)
_CITIZEN_THEME_KEYWORDS: dict[str, list[str]] = {
    "economie": ["économie", "economie", "impôt", "impot", "fiscal", "budget", "dette", "emploi", "chômage", "chomage", "salaire", "pouvoir d'achat", "inflation", "entreprise", "commerce", "travail"],
    "education": ["école", "ecole", "éducation", "education", "enseignant", "professeur", "université", "universite", "lycée", "lycee", "collège", "college", "scolaire", "formation", "étudiant", "etudiant"],
    "environnement": ["environnement", "écologie", "ecologie", "climat", "pollution", "déchet", "recyclage", "énergie", "energie", "renouvelable", "carbone", "vert", "biodiversité", "biodiversite"],
    "sante": ["santé", "sante", "hôpital", "hopital", "médecin", "medecin", "soins", "maladie", "vaccination", "pharmacie", "urgence", "infirmier"],
    "securite": ["sécurité", "securite", "police", "délinquance", "delinquance", "criminalité", "criminalite", "violence", "cambriolage", "vol", "agression", "gendarmerie"],
    "immigration": ["immigration", "immigré", "immigre", "migrant", "frontière", "frontiere", "étranger", "etranger", "asile", "régularisation", "regularisation", "intégration", "integration"],
    "culture": ["culture", "musée", "musee", "théâtre", "theatre", "cinéma", "cinema", "bibliothèque", "bibliotheque", "art", "patrimoine", "festival", "spectacle"],
    "logement": ["logement", "loyer", "immobilier", "HLM", "habitation", "propriétaire", "proprietaire", "locataire", "construction", "rénovation", "renovation", "appartement", "maison"],
    "transport": ["transport", "métro", "metro", "bus", "tramway", "vélo", "velo", "voiture", "route", "autoroute", "train", "mobilité", "mobilite", "circulation", "stationnement", "parking"],
    "numerique": ["numérique", "numerique", "internet", "digital", "fibre", "technologie", "données", "donnees", "cybersécurité", "cybersecurite", "IA", "intelligence artificielle"],
    "agriculture": ["agriculture", "agriculteur", "ferme", "paysan", "bio", "pesticide", "alimentaire", "PAC", "élevage", "elevage", "récolte", "recolte"],
    "justice": ["justice", "tribunal", "juge", "loi", "droit", "prison", "peine", "avocat", "procès", "proces", "juridique", "magistrat"],
    "international": ["international", "Europe", "UE", "OTAN", "diplomatie", "guerre", "paix", "défense", "defense", "armée", "armee", "géopolitique", "geopolitique"],
    "institutions": ["institution", "démocratie", "democratie", "élection", "election", "vote", "référendum", "referendum", "parlement", "sénat", "senat", "assemblée", "assemblee", "constitution", "maire", "conseil municipal"],
}


@routes.get(f"{route_prefix}/commune/{{commune_code}}/dashboard")
async def commune_dashboard(request):
    """Return aggregated dashboard data for a single commune."""
    from collections import defaultdict
    from qdrant_client.models import Filter, FieldCondition, MatchValue

    commune_code = request.match_info["commune_code"]

    # ── 1 & 2. Commune info + electoral lists from Firestore (sync in executor)
    commune_info: dict = {"code": commune_code}
    lists: list[dict] = []

    def _sync_firestore_lookups():
        info: dict = {}
        el_lists: list[dict] = []

        try:
            muni_query = db.collection("municipalities").where(
                "code", "==", commune_code
            )
            for doc in muni_query.stream():
                data = doc.to_dict() or {}
                info["name"] = data.get("nom", data.get("name", ""))
                postal_codes = data.get("codesPostaux", [])
                info["postal_code"] = postal_codes[0] if postal_codes else data.get("postal_code", "")
                epci = data.get("epci", {})
                info["epci_nom"] = epci.get("nom", "") if isinstance(epci, dict) else data.get("epci_nom", "")
                break
        except Exception as e:
            logger.warning(f"Could not fetch municipality {commune_code}: {e}")

        try:
            el_doc = db.collection("electoral_lists").document(commune_code).get()
            if el_doc.exists:
                el_data = el_doc.to_dict() or {}
                raw_lists = el_data.get("lists", [])
                el_lists = [
                    {
                        "panel_number": item.get("panel_number"),
                        "list_label": item.get("list_label", ""),
                        "list_short_label": item.get("list_short_label", ""),
                        "head_first_name": item.get("head_first_name", ""),
                        "head_last_name": item.get("head_last_name", ""),
                        "nuance_code": item.get("nuance_code", ""),
                        "nuance_label": item.get("nuance_label", ""),
                    }
                    for item in raw_lists
                ]
        except Exception as e:
            logger.warning(f"Could not fetch electoral_lists for {commune_code}: {e}")

        return info, el_lists

    loop = asyncio.get_event_loop()
    try:
        fs_info, lists = await asyncio.wait_for(
            loop.run_in_executor(None, _sync_firestore_lookups), timeout=30
        )
        commune_info.update(fs_info)
    except asyncio.TimeoutError:
        logger.error(f"Firestore lookup timed out for commune {commune_code}")
        return web.json_response(
            {"error": "Firestore lookup timed out", "commune_code": commune_code},
            status=504,
        )

    commune_info["list_count"] = len(lists)
    commune_info["lists"] = lists

    # ── 3. Chat session user messages ────────────────────────────────────────
    user_messages: list[dict] = []
    session_ids: set[str] = set()
    try:
        user_messages, session_ids = await _collect_user_messages(municipality_code=commune_code)
    except Exception as e:
        logger.warning(f"Could not fetch chat sessions for {commune_code}: {e}")

    # ── 3b. Keyword-classify citizen messages by theme ────────────────────────
    citizen_theme_counts: dict[str, int] = defaultdict(int)
    for msg in user_messages:
        text_lower = msg["text"].lower()
        for theme, keywords in _CITIZEN_THEME_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                citizen_theme_counts[theme] += 1

    citizen_total = sum(citizen_theme_counts.values()) or 1
    citizen_themes = [
        {
            "theme": theme,
            "count": citizen_theme_counts.get(theme, 0),
            "percentage": round(citizen_theme_counts.get(theme, 0) / citizen_total * 100, 1),
        }
        for theme in sorted(citizen_theme_counts.keys(), key=lambda t: -citizen_theme_counts.get(t, 0))
    ]

    # ── 4. Qdrant taxonomy (scroll filtered by municipality_code) ────────────
    #    Falls back to national party manifesto data when no commune-specific
    #    chunks exist, since national manifestos are relevant to all communes.

    # Build party_id → list_label mapping from Firestore candidates so we can
    # key by_list by the electoral list label the frontend expects.
    # Coalition parties map specific parties to broad coalition IDs used by
    # candidates.  E.g. a candidate with party_ids=["extreme_droite"] covers
    # Qdrant namespace "reconquete" because Reconquête is part of that coalition.
    _COALITION_MEMBERS: dict[str, list[str]] = {
        "extreme_droite": ["reconquete", "rn"],
        "extreme_gauche": [],
        "union_gauche": ["ps", "europe-ecologie-les-verts"],
        "union_droite": ["lr"],
        "union_centre": ["union_centre"],
    }

    party_to_list_label: dict[str, str] = {}
    # Also collect candidate info keyed by list_label (head candidate)
    list_candidate_info: dict[str, dict] = {}

    def _fetch_candidate_party_mapping():
        mapping: dict[str, str] = {}
        cand_info: dict[str, dict] = {}
        try:
            cands_query = db.collection("candidates").where(
                "commune_code", "==", commune_code
            )
            for doc in cands_query.stream():
                d = doc.to_dict() or {}
                label = d.get("list_label", "")
                website = d.get("website_url", "")
                manifesto = d.get("manifesto_url", "") or d.get("election_manifesto_url", "")
                if label:
                    cand_info[label] = {
                        "website_url": website,
                        "manifesto_url": manifesto,
                    }
                for pid in d.get("party_ids", []):
                    if pid and label:
                        mapping[pid] = label
                        # Also map member parties of this coalition
                        for member in _COALITION_MEMBERS.get(pid, []):
                            if member not in mapping:
                                mapping[member] = label
        except Exception as e:
            logger.warning(f"Could not fetch candidate party mapping for {commune_code}: {e}")
        return mapping, cand_info

    party_to_list_label, list_candidate_info = await loop.run_in_executor(
        None, _fetch_candidate_party_mapping
    )

    # Enrich electoral lists with candidate website/manifesto URLs
    for lst in lists:
        label = lst.get("list_label", "")
        cinfo = list_candidate_info.get(label, {})
        lst["website_url"] = cinfo.get("website_url", "")
        lst["manifesto_url"] = cinfo.get("manifesto_url", "")

    qdrant_filter = Filter(
        must=[
            FieldCondition(
                key="metadata.municipality_code",
                match=MatchValue(value=commune_code),
            )
        ]
    )

    def _scroll_qdrant_themes(scroll_filter, collections):
        """Scroll Qdrant collections and aggregate theme data."""
        _theme_data: dict[str, dict] = {}
        _total = 0
        for col_name in collections:
            try:
                offset = None
                while True:
                    points, next_offset = qdrant_client.scroll(
                        collection_name=col_name,
                        scroll_filter=scroll_filter,
                        limit=256,
                        offset=offset,
                        with_payload=[
                            "metadata.theme",
                            "metadata.party_name",
                            "metadata.namespace",
                            "metadata.party_ids",
                        ],
                        with_vectors=False,
                    )
                    for p in points:
                        meta = (p.payload or {}).get("metadata", {})
                        _total += 1
                        theme = meta.get("theme")
                        if not theme:
                            continue

                        # Resolve the list label: try party_ids mapping first,
                        # then namespace, then party_name.
                        namespace = meta.get("namespace", "")
                        chunk_party_ids = meta.get("party_ids", [])
                        list_label = ""
                        # Try party_ids from the chunk
                        for pid in (chunk_party_ids or []):
                            if pid in party_to_list_label:
                                list_label = party_to_list_label[pid]
                                break
                        # Try namespace as party_id
                        if not list_label and namespace in party_to_list_label:
                            list_label = party_to_list_label[namespace]
                        # Fallback to namespace (for display when no mapping exists)
                        if not list_label:
                            list_label = namespace or meta.get("party_name", "")

                        if theme not in _theme_data:
                            _theme_data[theme] = {
                                "theme": theme,
                                "total_count": 0,
                                "by_list": defaultdict(int),
                            }
                        _theme_data[theme]["total_count"] += 1
                        if list_label:
                            _theme_data[theme]["by_list"][list_label] += 1
                    if next_offset is None:
                        break
                    offset = next_offset
            except Exception as e:
                logger.error(f"Error scrolling {col_name} for commune {commune_code}: {e}", exc_info=True)
        return _theme_data, _total

    # Always include national manifesto data (relevant to all communes),
    # then layer commune-specific candidate chunks on top.
    theme_data, total_chunks = _scroll_qdrant_themes(
        None, [PARTY_INDEX_NAME]  # National manifesto data (no filter)
    )
    # Add commune-specific candidate chunks
    candidate_theme_data, candidate_chunks = _scroll_qdrant_themes(
        qdrant_filter, [CANDIDATES_INDEX_NAME]
    )
    # Merge candidate data into theme_data
    for theme, td in candidate_theme_data.items():
        if theme not in theme_data:
            theme_data[theme] = td
        else:
            theme_data[theme]["total_count"] += td["total_count"]
            for list_name, count in td["by_list"].items():
                theme_data[theme]["by_list"][list_name] = (
                    theme_data[theme]["by_list"].get(list_name, 0) + count
                )
    total_chunks += candidate_chunks

    classified_chunks = sum(td["total_count"] for td in theme_data.values())
    taxonomy_themes = []
    for td in sorted(theme_data.values(), key=lambda x: x["total_count"], reverse=True):
        taxonomy_themes.append({
            "theme": td["theme"],
            "total_count": td["total_count"],
            "percentage": round(td["total_count"] / classified_chunks * 100, 1) if classified_chunks else 0,
            "by_list": dict(td["by_list"]),
        })

    themes_detected = len(theme_data)

    return web.json_response({
        "commune": commune_info,
        "stats": {
            "total_questions": len(user_messages),
            "total_lists": len(lists),
            "total_chunks": total_chunks,
            "themes_detected": themes_detected,
        },
        "taxonomy": {
            "themes": taxonomy_themes,
        },
        "citizen": {
            "total_messages": len(user_messages),
            "classified_messages": sum(citizen_theme_counts.values()),
            "themes": citizen_themes,
        },
    })


@routes.post(f"{route_prefix}/get-parliamentary-question")
@inject_params
async def get_parliamentary_question(body: ParliamentaryQuestionRequestDto):
    party = await aget_party_by_id(body.party_id)

    if not party:
        return web.json_response(
            ParliamentaryQuestionDto(
                request_id=body.request_id,
                status=Status(
                    indicator=StatusIndicator.ERROR,
                    message="Could not find party with the provided ID",
                ),
                parliamentary_questions=[],
                rag_query=None,
            ).model_dump()
        )

    improved_rag_query = await get_improved_rag_query_voting_behavior(
        party, body.last_user_message, body.last_assistant_message
    )
    logger.debug(f"Improved RAG query: {improved_rag_query}")
    relevant_parliamentary_questions = await identify_relevant_parliamentary_questions(
        body.party_id, improved_rag_query
    )

    logger.debug(
        f"Relevant parliamentary questions: {relevant_parliamentary_questions}"
    )

    parliamentary_questions: list[Vote] = []
    for vote_doc in relevant_parliamentary_questions:
        vote_data_json_str = vote_doc.metadata.get("vote_data_json_str", "{}")
        vote_data = json.loads(vote_data_json_str)
        parliamentary_question = Vote(**vote_data)
        parliamentary_questions.append(parliamentary_question)

    parliamentary_question_dto = ParliamentaryQuestionDto(
        request_id=body.request_id,
        status=Status(indicator=StatusIndicator.SUCCESS, message="Success"),
        parliamentary_questions=parliamentary_questions,
        rag_query=improved_rag_query,
    )

    return web.json_response(parliamentary_question_dto.model_dump())


# ==================== Data Sources Pipeline API ====================

# Track running pipeline tasks so we can cancel them
_pipeline_tasks: dict[str, asyncio.Task] = {}

# DAG execution order for run-all
_PIPELINE_ORDER = [
    "population", "candidatures", "websites", "pourquituvotes",
    "professions", "populate", "scraper", "crawl_scraper", "indexer",
]


def _check_admin_secret(request: web.Request) -> bool:
    """Validate X-Admin-Secret header if ADMIN_SECRET env var is set."""
    expected = os.getenv("ADMIN_SECRET")
    if not expected:
        return True  # no secret configured — allow all
    return request.headers.get("X-Admin-Secret") == expected


@routes.get(f"{route_prefix}/admin/data-sources/status")
async def ds_status(request):
    """Return current config/status for all pipeline nodes."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from src.services.data_pipeline import PIPELINE_NODES
    from src.services.data_pipeline.base import load_config

    result = {}
    for node_id, node in PIPELINE_NODES.items():
        cfg = await load_config(node_id, node.default_config())
        result[node_id] = cfg.to_dict()
    return web.json_response(result)


# Nodes that are too heavy to run in-process and must run as K8s Jobs.
_K8S_JOB_NODES = frozenset({"indexer", "crawl_scraper"})


@routes.post(f"{route_prefix}/admin/data-sources/run/{{node_id}}")
async def ds_run_node(request):
    """Run a single pipeline node in the background.

    For heavy nodes (indexer, crawl_scraper) running inside K8s, a Job is
    created instead of running the node in-process, to avoid starving the
    event loop and crashing health-checks.
    """
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    node_id = request.match_info["node_id"]

    from src.services.data_pipeline import PIPELINE_NODES
    node = PIPELINE_NODES.get(node_id)
    if not node:
        return web.json_response({"error": f"Unknown node: {node_id}"}, status=404)

    body = await request.json() if request.content_length else {}
    force = body.get("force", False)
    # mode: "auto" (default — K8s for heavy nodes when in cluster),
    #        "k8s" (force K8s Job), "in-process" (force in-process)
    exec_mode = body.get("mode", "auto")

    # Decide whether to use K8s Job
    use_k8s = False
    if exec_mode == "k8s":
        use_k8s = True
    elif exec_mode == "auto" and node_id in _K8S_JOB_NODES:
        use_k8s = True

    if use_k8s:
        from src.services.k8s_job_launcher import is_running_in_k8s, create_pipeline_job
        if is_running_in_k8s():
            try:
                job_meta = await create_pipeline_job(node_id, force=force)
            except Exception as exc:
                logger.error("[data-sources] failed to create K8s job for %s: %s", node_id, exc)
                return web.json_response(
                    {"error": f"Failed to create K8s job: {exc}"}, status=500
                )
            return web.json_response({
                "status": "started",
                "node_id": node_id,
                "mode": "k8s-job",
                "job_name": job_meta.get("name"),
            })
        elif exec_mode == "k8s":
            return web.json_response(
                {"error": "K8s mode requested but not running inside a cluster"},
                status=400,
            )

    # Don't start if already running (in-process fallback or non-K8s nodes)
    if node_id in _pipeline_tasks and not _pipeline_tasks[node_id].done():
        return web.json_response({"status": "already_running", "node_id": node_id})

    async def _run():
        try:
            await node.execute(force=force)
        except asyncio.CancelledError:
            logger.info("[data-sources] node %s stopped by admin", node_id)
        except Exception as exc:
            logger.error("[data-sources] node %s failed: %s", node_id, exc, exc_info=True)
        finally:
            _pipeline_tasks.pop(node_id, None)

    task = asyncio.create_task(_run())
    _pipeline_tasks[node_id] = task
    return web.json_response({"status": "started", "node_id": node_id})


@routes.put(f"{route_prefix}/admin/data-sources/config/{{node_id}}")
async def ds_update_config(request):
    """Update a node's enabled flag and/or settings."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    node_id = request.match_info["node_id"]

    from src.services.data_pipeline import PIPELINE_NODES
    from src.services.data_pipeline.base import load_config, save_config

    node = PIPELINE_NODES.get(node_id)
    if not node:
        return web.json_response({"error": f"Unknown node: {node_id}"}, status=404)

    body = await request.json()
    cfg = await load_config(node_id, node.default_config())

    if "enabled" in body:
        cfg.enabled = body["enabled"]
    if "settings" in body:
        cfg.settings.update(body["settings"])

    await save_config(cfg)
    return web.json_response(cfg.to_dict())


@routes.post(f"{route_prefix}/admin/data-sources/bust-cache")
async def ds_bust_cache(request):
    """Clear the in-memory pipeline context cache."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from src.services.data_pipeline import clear_context
    clear_context()
    return web.json_response({"status": "ok", "message": "Pipeline context cleared"})


@routes.post(f"{route_prefix}/admin/data-sources/bust-url-cache")
async def ds_bust_url_cache(request):
    """Clear the URL response cache (local filesystem or S3)."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from src.services.data_pipeline.url_cache import bust_cache
    result = await bust_cache()
    return web.json_response(result)


@routes.get(f"{route_prefix}/admin/data-sources/url-cache-stats")
async def ds_url_cache_stats(request):
    """Return URL cache statistics."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from src.services.data_pipeline.url_cache import cache_stats
    result = await cache_stats()
    return web.json_response(result)


@routes.post(f"{route_prefix}/admin/data-sources/clear-all")
async def ds_clear_all(request):
    """Reset all pipeline node configs in Firestore to defaults."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from src.services.data_pipeline import PIPELINE_NODES, clear_context
    from src.services.data_pipeline.base import save_config

    cleared = []
    for node_id, node in PIPELINE_NODES.items():
        await save_config(node.default_config())
        cleared.append(node_id)

    clear_context()
    logger.info("[data-sources] cleared all node configs: %s", cleared)
    return web.json_response({"status": "ok", "cleared": cleared})


@routes.post(f"{route_prefix}/admin/data-sources/run-all")
async def ds_run_all(request):
    """Run all enabled nodes in DAG order (background task)."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    body = await request.json() if request.content_length else {}
    force = body.get("force", False)
    settings_overrides: dict = body.get("settings", {})

    from src.services.data_pipeline import PIPELINE_NODES, clear_context
    from src.services.data_pipeline.base import load_config

    # Don't start if a run-all is already in progress
    if "_run_all" in _pipeline_tasks and not _pipeline_tasks["_run_all"].done():
        return web.json_response({"status": "already_running"})

    async def _run_all():
        clear_context()

        for node_id in _PIPELINE_ORDER:
            node = PIPELINE_NODES.get(node_id)
            if not node:
                continue
            cfg = await load_config(node_id, node.default_config())
            if not cfg.enabled and not force:
                logger.info("[data-sources] run-all: skipping disabled node %s", node_id)
                continue
            try:
                node_overrides = settings_overrides.get(node_id)
                logger.info("[data-sources] run-all: executing %s%s", node_id,
                            f" (overrides: {node_overrides})" if node_overrides else "")
                # Register each node as its own task so it can be stopped individually
                node_task = asyncio.create_task(node.execute(force=force, settings_override=node_overrides))
                _pipeline_tasks[node_id] = node_task
                await node_task
            except asyncio.CancelledError:
                logger.info("[data-sources] run-all: node %s stopped by admin", node_id)
            except Exception as exc:
                logger.error("[data-sources] run-all: %s failed: %s", node_id, exc, exc_info=True)
            finally:
                _pipeline_tasks.pop(node_id, None)
        _pipeline_tasks.pop("_run_all", None)

    task = asyncio.create_task(_run_all())
    _pipeline_tasks["_run_all"] = task
    return web.json_response({"status": "started", "order": _PIPELINE_ORDER})


@routes.post(f"{route_prefix}/admin/data-sources/stop/{{node_id}}")
async def ds_stop_node(request):
    """Cancel a running pipeline node task (in-process or K8s Job)."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    node_id = request.match_info["node_id"]

    from src.services.data_pipeline.base import update_status, NodeStatus

    # When running in K8s, attempt to delete the Job for heavy nodes.
    if node_id in _K8S_JOB_NODES:
        from src.services.k8s_job_launcher import is_running_in_k8s, delete_pipeline_job
        if is_running_in_k8s():
            deleted = await delete_pipeline_job(node_id)
            await update_status(node_id, NodeStatus.ERROR, last_error="Stopped by admin")
            return web.json_response({
                "status": "stopped" if deleted else "not_running",
                "node_id": node_id,
                "mode": "k8s-job",
            })

    task = _pipeline_tasks.get(node_id)
    if task and not task.done():
        task.cancel()
        _pipeline_tasks.pop(node_id, None)
        await update_status(node_id, NodeStatus.ERROR, last_error="Stopped by admin")
        return web.json_response({"status": "stopped", "node_id": node_id})

    # Also clear stale "running" state from Firestore (e.g. after server restart)
    from src.services.data_pipeline.base import load_config
    from src.services.data_pipeline import PIPELINE_NODES
    node = PIPELINE_NODES.get(node_id)
    if node:
        cfg = await load_config(node_id, node.default_config())
        if cfg.status == NodeStatus.RUNNING:
            await update_status(node_id, NodeStatus.ERROR, last_error="Stopped by admin")
            return web.json_response({"status": "stopped", "node_id": node_id, "note": "cleared stale state"})

    return web.json_response({"status": "not_running", "node_id": node_id})


@routes.post(f"{route_prefix}/admin/data-sources/stop-all")
async def ds_stop_all(request):
    """Cancel all running pipeline tasks."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from src.services.data_pipeline.base import update_status, NodeStatus

    stopped = []
    for key, task in list(_pipeline_tasks.items()):
        if not task.done():
            task.cancel()
            if key != "_run_all":
                await update_status(key, NodeStatus.ERROR, last_error="Cancelled by admin")
            stopped.append(key)
    _pipeline_tasks.clear()
    return web.json_response({"status": "ok", "stopped": stopped})


@routes.post(f"{route_prefix}/admin/data-sources/trigger-crawl")
async def ds_trigger_crawl(request):
    """Send pending candidates to the external crawl service for immediate processing."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    crawl_url = os.getenv("CRAWL_SERVICE_URL", "").rstrip("/")
    crawl_secret = os.getenv("CRAWL_API_SECRET", "")
    if not crawl_url:
        return web.json_response({"error": "CRAWL_SERVICE_URL not configured"}, status=400)

    from src.services.data_pipeline.crawl_scraper import (
        CrawlScraperNode,
        _get_crawl_credentials,
        COL_CANDIDATE_ID,
        COL_WEBSITE_URL,
        COL_STATUS,
        _row_get,
    )

    # Read pending URLs from the Google Sheet
    try:
        creds = _get_crawl_credentials()
        node = CrawlScraperNode()
        settings = node.default_settings
        sheet_id = settings["sheet_id"]

        async with aiohttp.ClientSession() as session:
            rows = await node._fetch_sheet_rows(session, sheet_id, creds.token)
            pending = []
            for row in rows[1:]:
                cid = _row_get(row, COL_CANDIDATE_ID)
                url = _row_get(row, COL_WEBSITE_URL)
                status = _row_get(row, COL_STATUS)
                if cid and url and status.upper() != "PROCESSED":
                    pending.append({"candidate_id": cid, "url": url})

            if not pending:
                return web.json_response({"status": "no_pending", "message": "All candidates already processed"})

            # Call external crawl service
            trigger_headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {crawl_secret}",
            }
            payload = {"urls": [p["url"] for p in pending]}
            trigger_url = f"{crawl_url}/api/crawl"

            async with session.post(trigger_url, headers=trigger_headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp_text = await resp.text()
                if resp.ok:
                    return web.json_response({
                        "status": "triggered",
                        "candidates": len(pending),
                        "crawl_response": resp_text[:500],
                    })
                else:
                    return web.json_response({
                        "status": "crawl_error",
                        "http_status": resp.status,
                        "response": resp_text[:500],
                    }, status=502)

    except Exception as exc:
        logger.error("[trigger-crawl] failed: %s", exc, exc_info=True)
        return web.json_response({"error": str(exc)}, status=500)


@routes.get(f"{route_prefix}/admin/data-sources/preview/{{node_id}}")
async def ds_preview(request):
    """Return a preview of data produced by a pipeline node."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    node_id = request.match_info["node_id"]

    from src.services.data_pipeline import PIPELINE_NODES
    from src.services.data_pipeline.base import load_config

    node = PIPELINE_NODES.get(node_id)
    if not node:
        return web.json_response({"error": f"Unknown node: {node_id}"}, status=404)

    cfg = await load_config(node_id, node.default_config())

    # Return checkpoints and counts as preview data
    preview: dict = {
        "node_id": node_id,
        "status": cfg.status.value if hasattr(cfg.status, "value") else cfg.status,
        "counts": cfg.counts,
        "checkpoints": cfg.checkpoints,
        "settings": cfg.settings,
    }

    # For specific nodes, add extra preview data
    if node_id == "population":
        from src.services.data_pipeline.population import get_top_communes
        communes = get_top_communes()
        preview["sample"] = communes[:10] if communes else []
        preview["total"] = len(communes) if communes else 0
    elif node_id == "candidatures":
        from src.services.data_pipeline.candidatures import get_candidatures
        cands = get_candidatures()
        preview["total"] = len(cands) if cands else 0
        preview["sample"] = cands[:5] if cands else []
    elif node_id == "websites":
        from src.services.data_pipeline.websites import get_websites
        sites = get_websites()
        preview["total"] = len(sites) if sites else 0
        preview["sample"] = list(sites.items())[:5] if sites else []

    return web.json_response(preview)


@routes.post(f"{route_prefix}/admin/data-sources/drive-cleanup")
async def ds_drive_cleanup(request):
    """Detect (and optionally trash) failed crawl folders on Google Drive.

    Query params:
        dry_run=true (default) — only report failed folders
        dry_run=false — move failed folders to Drive trash (recoverable)
    """
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    dry_run = request.query.get("dry_run", "true").lower() != "false"

    from src.services.data_pipeline.crawl_scraper import detect_failed_drive_folders
    result = await detect_failed_drive_folders(dry_run=dry_run)
    return web.json_response(result)


@routes.get(f"{route_prefix}/admin/data-sources/k8s-status")
async def ds_k8s_status(request):
    """Return K8s cluster status: pods, jobs, cronjobs, statefulsets."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from src.services.k8s_job_launcher import get_k8s_cluster_status
    status = await get_k8s_cluster_status()
    return web.json_response(status)


@routes.get(f"{route_prefix}/admin/chat-sessions")
async def admin_list_chat_sessions(request: web.Request) -> web.Response:
    """List chat sessions with pagination and filters."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    limit = min(int(request.query.get("limit", "50")), 200)
    status_filter = request.query.get("status")
    municipality = request.query.get("municipality_code")
    since = request.query.get("since")
    sort_by = request.query.get("sort_by", "updated_at")
    order = request.query.get("order", "desc")
    cursor_after = request.query.get("cursor_after")

    from google.cloud.firestore_v1 import AsyncQuery as _FsQuery
    query = async_db.collection("chat_sessions")

    if since:
        from datetime import datetime
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        query = query.where("updated_at", ">=", since_dt)

    direction = _FsQuery.DESCENDING if order == "desc" else _FsQuery.ASCENDING
    query = query.order_by(sort_by, direction=direction)

    if municipality:
        query = query.where("municipality_code", "==", municipality)
    if status_filter:
        query = query.where("debug.status", "==", status_filter)

    # Cursor-based pagination (avoids slow offset scans)
    if cursor_after:
        cursor_doc = await async_db.collection("chat_sessions").document(cursor_after).get()
        if cursor_doc.exists:
            query = query.start_after(cursor_doc)

    sessions = []
    async for doc in query.limit(limit + 1).stream():
        data = doc.to_dict()
        data["session_id"] = doc.id
        sessions.append(data)

    has_more = len(sessions) > limit
    sessions = sessions[:limit]
    next_cursor = sessions[-1]["session_id"] if has_more and sessions else None

    return web.json_response(
        {
            "sessions": sessions,
            "total": len(sessions),
            "has_more": has_more,
            "next_cursor": next_cursor,
            "limit": limit,
        },
        dumps=lambda obj: json.dumps(obj, default=str),
    )


@routes.get(f"{route_prefix}/admin/chat-sessions/{{session_id}}")
async def admin_get_chat_session(request: web.Request) -> web.Response:
    """Get full chat session detail including messages subcollection."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    session_id = request.match_info["session_id"]
    doc = await async_db.collection("chat_sessions").document(session_id).get()
    if not doc.exists:
        return web.json_response({"error": "Not found"}, status=404)

    session_data = doc.to_dict()
    session_data["session_id"] = doc.id

    messages = []
    msgs_ref = (
        async_db.collection("chat_sessions")
        .document(session_id)
        .collection("messages")
        .order_by("created_at")
    )
    async for msg_doc in msgs_ref.stream():
        msg_data = msg_doc.to_dict()
        msg_data["id"] = msg_doc.id
        messages.append(msg_data)

    session_data["messages"] = messages
    return web.Response(
        content_type="application/json",
        text=json.dumps(session_data, default=str),
    )


@routes.get(f"{route_prefix}/admin/dashboard/warnings")
async def admin_dashboard_warnings(request: web.Request) -> web.Response:
    """Aggregate warnings across data completeness, ops, and chat quality."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    from datetime import datetime, timedelta, timezone
    from google.cloud.firestore_v1 import Query as _FsQuery

    hours = int(request.query.get("hours", "24"))
    since = datetime.now(timezone.utc) - timedelta(hours=hours) if hours > 0 else None

    data_warnings: list = []
    ops_warnings: list = []
    chat_warnings: list = []

    try:
        # --- Data completeness ---
        # Only fetch the fields we actually check, to minimise data transfer
        candidates_no_website_count = 0
        async for doc in async_db.collection("candidates").select(["website_url"]).stream():
            d = doc.to_dict() or {}
            if not d.get("website_url"):
                candidates_no_website_count += 1

        no_manifesto_count = 0
        async for doc in async_db.collection("parties").select(["manifesto_pdf_url"]).stream():
            d = doc.to_dict() or {}
            if not d.get("manifesto_pdf_url"):
                no_manifesto_count += 1

        if candidates_no_website_count:
            data_warnings.append(
                {
                    "severity": "warning",
                    "category": "data",
                    "message": f"{candidates_no_website_count} candidates missing websites",
                    "count": candidates_no_website_count,
                    "tab_link": "coverage",
                }
            )
        if no_manifesto_count:
            data_warnings.append(
                {
                    "severity": "warning",
                    "category": "data",
                    "message": f"{no_manifesto_count} parties missing manifestos",
                    "count": no_manifesto_count,
                    "tab_link": "coverage",
                }
            )

        # Qdrant collection checks
        try:
            for col_name in [PARTY_INDEX_NAME, CANDIDATES_INDEX_NAME]:
                info = qdrant_client.get_collection(col_name)
                if info.points_count == 0:
                    data_warnings.append(
                        {
                            "severity": "critical",
                            "category": "data",
                            "message": f"Qdrant collection {col_name} is empty",
                            "count": 0,
                            "tab_link": "pipeline",
                        }
                    )
        except Exception:
            pass

        # --- Ops warnings: pipeline node status ---
        async for node_doc in async_db.collection("pipeline_nodes").stream():
            node = node_doc.to_dict()
            if node.get("status") == "error":
                ops_warnings.append(
                    {
                        "severity": "critical",
                        "category": "ops",
                        "message": (
                            f"Pipeline node '{node_doc.id}' in error state: "
                            f"{node.get('last_error', 'unknown')}"
                        ),
                        "count": 1,
                        "tab_link": "pipeline",
                    }
                )
            last_run = node.get("last_run_at")
            if last_run and hasattr(last_run, "timestamp"):
                age_hours = (
                    datetime.now(timezone.utc)
                    - last_run.replace(tzinfo=timezone.utc)
                ).total_seconds() / 3600
                if age_hours > 48:
                    ops_warnings.append(
                        {
                            "severity": "warning",
                            "category": "ops",
                            "message": (
                                f"Pipeline node '{node_doc.id}' last ran "
                                f"{int(age_hours)}h ago"
                            ),
                            "count": 1,
                            "tab_link": "pipeline",
                        }
                    )

        # --- Chat quality ---
        error_count = 0
        zero_source_count = 0
        slow_count = 0
        total_sessions = 0

        chat_query = async_db.collection("chat_sessions")
        if since is not None:
            chat_query = (
                chat_query.where("updated_at", ">=", since)
                .order_by("updated_at", direction=_FsQuery.DESCENDING)
            )
        chat_query = chat_query.limit(500)

        async for chat_doc in chat_query.stream():
            total_sessions += 1
            chat = chat_doc.to_dict()
            debug = chat.get("debug", {})
            if debug.get("status") == "error":
                error_count += 1
            if debug.get("source_count", -1) == 0:
                zero_source_count += 1
            if debug.get("response_time_ms", 0) > 30000:
                slow_count += 1

        if error_count > 0:
            chat_warnings.append(
                {
                    "severity": (
                        "critical"
                        if total_sessions and error_count > total_sessions * 0.1
                        else "warning"
                    ),
                    "category": "chat",
                    "message": f"{error_count} chat errors in last {hours}h",
                    "count": error_count,
                    "tab_link": "chats",
                }
            )
        if zero_source_count > 0:
            chat_warnings.append(
                {
                    "severity": "warning",
                    "category": "chat",
                    "message": (
                        f"{zero_source_count} questions returned zero sources "
                        f"in last {hours}h"
                    ),
                    "count": zero_source_count,
                    "tab_link": "chats",
                }
            )
        if slow_count > 0:
            chat_warnings.append(
                {
                    "severity": "info",
                    "category": "chat",
                    "message": f"{slow_count} slow responses (>30s) in last {hours}h",
                    "count": slow_count,
                    "tab_link": "chats",
                }
            )

    except Exception as e:
        logger.error(f"Error computing dashboard warnings: {e}", exc_info=True)

    all_warnings = data_warnings + ops_warnings + chat_warnings
    counts = {
        "critical": sum(1 for w in all_warnings if w["severity"] == "critical"),
        "warning": sum(1 for w in all_warnings if w["severity"] == "warning"),
        "info": sum(1 for w in all_warnings if w["severity"] == "info"),
    }

    return web.json_response(
        {
            "data": data_warnings,
            "ops": ops_warnings,
            "chat": chat_warnings,
            "counts": counts,
        }
    )


@routes.get(f"{route_prefix}/admin/dashboard/data-consistency")
async def admin_dashboard_data_consistency(request: web.Request) -> web.Response:
    """Cross-reference data consistency checks between Firestore and Qdrant."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        # --- Firestore counts (minimal field selection to reduce data transfer) ---
        # Parties: only need doc IDs for cross-reference checks
        party_ids_fs: set[str] = set()
        async for doc in async_db.collection("parties").select([]).stream():
            party_ids_fs.add(doc.id)

        # Candidates: need IDs + website_url for counts
        candidate_ids_fs: set[str] = set()
        candidates_with_website_count = 0
        async for doc in async_db.collection("candidates").select(["website_url"]).stream():
            candidate_ids_fs.add(doc.id)
            d = doc.to_dict() or {}
            if d.get("website_url"):
                candidates_with_website_count += 1

        # Municipalities: only need doc IDs for cross-reference checks
        municipality_codes_fs: set[str] = set()
        async for doc in async_db.collection("municipalities").select([]).stream():
            municipality_codes_fs.add(doc.id)

        firestore_info = {
            "parties": len(party_ids_fs),
            "candidates": len(candidate_ids_fs),
            "municipalities": len(municipality_codes_fs),
            "candidates_with_website": candidates_with_website_count,
        }

        # --- Qdrant: manifesto collection ---
        manifesto_info = qdrant_client.get_collection(PARTY_INDEX_NAME)
        manifesto_points = manifesto_info.points_count or 0

        manifesto_namespaces: set[str] = set()
        offset = None
        while True:
            results, next_offset = qdrant_client.scroll(
                collection_name=PARTY_INDEX_NAME,
                limit=256,
                offset=offset,
                with_payload=["metadata.namespace"],
                with_vectors=False,
            )
            if not results:
                break
            for p in results:
                meta = (p.payload or {}).get("metadata", {})
                ns = meta.get("namespace", "")
                if ns:
                    manifesto_namespaces.add(ns)
            if next_offset is None:
                break
            offset = next_offset

        # --- Qdrant: candidates collection ---
        candidates_info = qdrant_client.get_collection(CANDIDATES_INDEX_NAME)
        candidate_points = candidates_info.points_count or 0

        candidate_namespaces: set[str] = set()
        candidate_party_ids_qdrant: set[str] = set()
        candidate_munis_qdrant: set[str] = set()

        # Fields for metadata quality sampling
        sample_points: list[dict] = []
        offset = None
        while True:
            results, next_offset = qdrant_client.scroll(
                collection_name=CANDIDATES_INDEX_NAME,
                limit=256,
                offset=offset,
                with_payload=[
                    "metadata.namespace",
                    "metadata.party_ids",
                    "metadata.municipality_code",
                    "metadata.theme",
                    "metadata.sub_theme",
                    "metadata.source_document",
                    "metadata.fiabilite",
                ],
                with_vectors=False,
            )
            if not results:
                break
            for p in results:
                meta = (p.payload or {}).get("metadata", {})
                ns = meta.get("namespace", "")
                if ns:
                    candidate_namespaces.add(ns)
                for pid in meta.get("party_ids", []):
                    if pid:
                        candidate_party_ids_qdrant.add(pid)
                muni = meta.get("municipality_code", "")
                if muni:
                    candidate_munis_qdrant.add(muni)
                if len(sample_points) < 100:
                    sample_points.append(meta)
            if next_offset is None:
                break
            offset = next_offset

        candidate_municipalities_qdrant = sorted(candidate_munis_qdrant)

        qdrant_info = {
            "manifesto_points": manifesto_points,
            "manifesto_namespaces": sorted(manifesto_namespaces),
            "candidate_points": candidate_points,
            "candidate_namespaces_count": len(candidate_namespaces),
            "candidate_municipalities": candidate_municipalities_qdrant,
        }

        # --- Cross-references ---
        orphan_candidate_ns = sorted(
            candidate_namespaces - candidate_ids_fs
        )
        orphan_manifesto_ns = sorted(
            manifesto_namespaces - party_ids_fs
        )
        missing_party_ids = sorted(
            candidate_party_ids_qdrant - party_ids_fs
        )
        missing_municipality_codes = sorted(
            candidate_munis_qdrant - municipality_codes_fs
        )

        cross_references = {
            "all_candidate_party_ids_in_firestore": len(missing_party_ids) == 0,
            "all_candidate_munis_in_firestore": len(missing_municipality_codes) == 0,
            "all_candidate_namespaces_in_firestore": len(orphan_candidate_ns) == 0,
            "all_manifesto_namespaces_in_firestore": len(orphan_manifesto_ns) == 0,
            "orphan_candidate_namespaces": orphan_candidate_ns,
            "orphan_manifesto_namespaces": orphan_manifesto_ns,
            "missing_party_ids": missing_party_ids,
            "missing_municipality_codes": missing_municipality_codes,
        }

        # --- Metadata quality (sample up to 100 candidate points) ---
        sample_size = len(sample_points)
        if sample_size > 0:
            party_ids_pop = sum(
                1 for m in sample_points if m.get("party_ids")
            )
            muni_pop = sum(
                1 for m in sample_points if m.get("municipality_code")
            )
            theme_pop = sum(
                1 for m in sample_points if m.get("theme")
            )
            sub_theme_pop = sum(
                1 for m in sample_points if m.get("sub_theme")
            )
            source_doc_pop = sum(
                1 for m in sample_points if m.get("source_document")
            )
            fiabilite_pop = sum(
                1 for m in sample_points if m.get("fiabilite")
            )
            metadata_quality = {
                "sample_size": sample_size,
                "party_ids_populated_pct": round(
                    party_ids_pop / sample_size * 100
                ),
                "municipality_code_populated_pct": round(
                    muni_pop / sample_size * 100
                ),
                "theme_populated_pct": round(
                    theme_pop / sample_size * 100
                ),
                "sub_theme_populated_pct": round(
                    sub_theme_pop / sample_size * 100
                ),
                "source_document_populated_pct": round(
                    source_doc_pop / sample_size * 100
                ),
                "fiabilite_populated_pct": round(
                    fiabilite_pop / sample_size * 100
                ),
            }
        else:
            metadata_quality = {"sample_size": 0}

        # --- Build issues list ---
        issues: list[dict] = []

        if orphan_candidate_ns:
            issues.append({
                "severity": "warning",
                "message": (
                    f"{len(orphan_candidate_ns)} candidate namespace(s) in Qdrant "
                    f"not found in Firestore: {orphan_candidate_ns}"
                ),
            })
        if orphan_manifesto_ns:
            issues.append({
                "severity": "warning",
                "message": (
                    f"{len(orphan_manifesto_ns)} manifesto namespace(s) in Qdrant "
                    f"not found in Firestore: {orphan_manifesto_ns}"
                ),
            })
        if missing_party_ids:
            issues.append({
                "severity": "critical",
                "message": (
                    f"{len(missing_party_ids)} party_id(s) referenced in Qdrant "
                    f"candidates not found in Firestore: {missing_party_ids}"
                ),
            })
        if missing_municipality_codes:
            issues.append({
                "severity": "critical",
                "message": (
                    f"{len(missing_municipality_codes)} municipality code(s) in Qdrant "
                    f"not found in Firestore: {missing_municipality_codes}"
                ),
            })
        if candidate_points == 0:
            issues.append({
                "severity": "critical",
                "message": "Qdrant candidates collection is empty",
            })
        if manifesto_points == 0:
            issues.append({
                "severity": "critical",
                "message": "Qdrant manifesto collection is empty",
            })
        if sample_size > 0:
            if metadata_quality.get("theme_populated_pct", 0) < 50:
                issues.append({
                    "severity": "warning",
                    "message": (
                        f"Only {metadata_quality['theme_populated_pct']}% of sampled "
                        f"candidate points have theme metadata"
                    ),
                })
            if metadata_quality.get("sub_theme_populated_pct", 0) < 50:
                issues.append({
                    "severity": "warning",
                    "message": (
                        f"Only {metadata_quality['sub_theme_populated_pct']}% of sampled "
                        f"candidate points have sub_theme metadata"
                    ),
                })

        return web.json_response({
            "status": "ok",
            "firestore": firestore_info,
            "qdrant": qdrant_info,
            "cross_references": cross_references,
            "metadata_quality": metadata_quality,
            "issues": issues,
        })

    except Exception as e:
        logger.error(
            f"Error in data-consistency check: {e}", exc_info=True
        )
        return web.json_response(
            {"status": "error", "error": str(e)}, status=500
        )


@routes.get(f"{route_prefix}/admin/crawler/status")
async def admin_crawler_status(request: web.Request) -> web.Response:
    """Proxy the K8s crawler status API, keeping the crawler secret server-side."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    crawl_api_url = os.getenv("CRAWL_API_URL", "http://51.159.25.158:4000")
    crawl_api_secret = os.getenv("CRAWL_API_SECRET", "")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{crawl_api_url}/api/status",
                params={"secret": crawl_api_secret},
                headers={"x-forwarded-proto": "https"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                return web.json_response(data, status=resp.status)
    except Exception as e:
        logger.error("Error proxying crawler status: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=502)


# ---------------------------------------------------------------------------
# Maintenance mode endpoints
# ---------------------------------------------------------------------------

@routes.get(f"{route_prefix}/maintenance")
async def public_maintenance_status(request: web.Request) -> web.Response:
    """Public endpoint — check whether maintenance mode is active."""
    try:
        doc = await async_db.collection("settings").document("maintenance").get()
        if doc.exists:
            data = doc.to_dict()
            return web.json_response({
                "enabled": bool(data.get("enabled", False)),
                "message": data.get("message", ""),
            })
    except Exception as e:
        logger.warning("Could not read maintenance doc: %s", e)
    return web.json_response({"enabled": False, "message": ""})


@routes.get(f"{route_prefix}/admin/maintenance")
async def admin_get_maintenance(request: web.Request) -> web.Response:
    """Admin — get full maintenance status including updated_at."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        doc = await async_db.collection("settings").document("maintenance").get()
        if doc.exists:
            data = doc.to_dict()
            updated_at = data.get("updated_at")
            return web.json_response({
                "enabled": bool(data.get("enabled", False)),
                "message": data.get("message", ""),
                "updated_at": updated_at.isoformat() if updated_at else None,
            })
    except Exception as e:
        logger.error("Error reading maintenance status: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)

    return web.json_response({"enabled": False, "message": "", "updated_at": None})


@routes.put(f"{route_prefix}/admin/maintenance")
async def admin_set_maintenance(request: web.Request) -> web.Response:
    """Admin — enable or disable maintenance mode."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON body"}, status=400)

    enabled = bool(body.get("enabled", False))
    message = str(body.get("message", ""))

    from google.cloud.firestore_v1 import SERVER_TIMESTAMP
    try:
        await async_db.collection("settings").document("maintenance").set({
            "enabled": enabled,
            "message": message,
            "updated_at": SERVER_TIMESTAMP,
        })
        logger.info("Maintenance mode set to %s by admin", enabled)
        return web.json_response({
            "enabled": enabled,
            "message": message,
            "updated_at": None,  # SERVER_TIMESTAMP not yet resolved
        })
    except Exception as e:
        logger.error("Error setting maintenance status: %s", e, exc_info=True)
        return web.json_response({"error": str(e)}, status=500)


app = web.Application(middlewares=[api_key_middleware])

# Add routes to the app
app.router.add_routes(routes)

# Configure CORS
# Configure default CORS settings.
default_resource_options = aiohttp_cors.ResourceOptions(
    allow_credentials=True,
    expose_headers="*",
    allow_headers="*",
    allow_methods="*",
)
cors_allowed_origins = get_cors_allowed_origins(os.getenv("ENV"))
cors_config = {}
if type(cors_allowed_origins) is str:
    cors_config[cors_allowed_origins] = default_resource_options
else:
    for origin in cors_allowed_origins:
        cors_config[origin] = default_resource_options


logger.info(f"CORS allowed origins: {cors_config}")

cors = aiohttp_cors.setup(
    app,
    # defaults=cors_config,
)


# Configure CORS on all routes
for route in list(app.router.routes()):
    logger.info(f"Adding CORS to route {route}")
    cors.add(route, cors_config)

# Attach Socket.IO only when not explicitly disabled (for debugging)
if os.environ.get("DISABLE_SOCKETIO") != "1":
    sio.attach(app)
    logger.info("Socket.IO attached to app")
else:
    logger.warning("Socket.IO DISABLED (DISABLE_SOCKETIO=1)")


# Background initialization (non-blocking) so the HTTP server starts immediately
async def _deferred_init():
    """Run slow initialization tasks in the background after server starts."""
    logger.info("=== _deferred_init BEGIN ===")

    # Reset rate limit flag on startup (with timeout to prevent hanging)
    logger.info("Resetting LLM rate limit flags...")
    try:
        await asyncio.wait_for(reset_all_rate_limits(), timeout=10)
        logger.info("LLM rate limit flags reset successfully")
    except asyncio.TimeoutError:
        logger.error("Timed out resetting rate limit flags (10s) — skipping")
    except Exception as e:
        logger.error(f"Failed to reset rate limit flags: {e}")

    # Get the current event loop for thread-safe async execution
    event_loop = asyncio.get_running_loop()

    # Skip Firestore indexation listeners in local dev — seeding triggers them
    # and causes heavy scraping/embedding (Gemini API calls) on every restart.
    env = os.environ.get("ENV", "local")
    if env == "local":
        logger.info(
            "Skipping Firestore indexation listeners (ENV=local). "
            "Use /admin/index-* endpoints to trigger manually."
        )
    else:
        # Start Firestore listener for parties (manifesto indexation)
        logger.info("Starting Firestore parties listener...")
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: start_parties_listener(event_loop=event_loop)
            )
            logger.info("Firestore parties listener started successfully")
        except Exception as e:
            logger.error(f"Failed to start Firestore parties listener: {e}")

        # Start Firestore listener for candidates (website indexation)
        logger.info("Starting Firestore candidates listener...")
        try:
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: start_candidates_listener(event_loop=event_loop)
            )
            logger.info("Firestore candidates listener started successfully")
        except Exception as e:
            logger.error(f"Failed to start Firestore candidates listener: {e}")

    # Start the scheduler for periodic tasks
    logger.info("Starting scheduler for periodic tasks...")
    try:
        scheduler = create_scheduler()
        scheduler.start()
        logger.info("Scheduler started successfully")
    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

    logger.info("=== _deferred_init END ===")


async def on_startup(app):
    """Called when the application starts. Schedules init in background so server starts fast."""
    logger.info("=== on_startup: scheduling deferred init in background ===")
    asyncio.create_task(_deferred_init())


app.on_startup.append(on_startup)


# Instantiate the argument parser
parser = argparse.ArgumentParser()

# Add arguments to parser
parser.add_argument("--host", type=str, nargs=1, default=["127.0.0.1"])
parser.add_argument("--port", type=int, nargs=1, default=[8080])
parser.add_argument("--debug", action="store_true", default=False)

# Start the server
if __name__ == "__main__":
    logger.info("=== __main__ starting ===")
    args = parser.parse_args()
    host = args.host[0]
    port = args.port[0]
    debug = args.debug
    socketio_logger = logging.getLogger("socketio.asyncserver")
    if debug:
        socketio_logger.setLevel(logging.INFO)
        logging.basicConfig(level=logging.INFO, format=LOGGING_FORMAT)
        loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
        # Set all loggers in the src package to debug
        for logger in loggers:
            if logger.name.startswith("src"):
                logger.setLevel(logging.DEBUG)
    else:
        socketio_logger.setLevel(logging.WARN)
        logging.basicConfig(level=logging.INFO, format=LOGGING_FORMAT)
    web.run_app(app, host=host, port=port, reuse_address=True, shutdown_timeout=5.0)
