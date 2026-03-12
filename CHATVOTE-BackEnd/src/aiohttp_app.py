# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Backend v2 — commune dashboard, candidate scraping

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
from src.firebase_service import aget_party_by_id, async_db, db
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
UPLOAD_SECRET = os.environ.get("ADMIN_UPLOAD_SECRET", "")


def _check_upload_secret(request: web.Request) -> None:
    """Validate upload secret from header or query param.

    Raises 404 (not 403) to avoid revealing the endpoint exists.
    """
    secret = request.headers.get("X-Upload-Secret") or request.query.get("secret")
    if not UPLOAD_SECRET or secret != UPLOAD_SECRET:
        raise web.HTTPNotFound()


@routes.post(route_prefix + "/admin/upload")
async def admin_upload(request: web.Request) -> web.Response:
    """Upload one or more PDF/TXT files for auto-classification and indexing."""
    _check_upload_secret(request)

    reader = await request.multipart()
    jobs: list[dict] = []

    while True:
        part = await reader.next()
        if part is None:
            break
        if part.filename is None:
            continue  # skip non-file fields

        filename = part.filename
        data = await part.read(decode=False)

        if not data:
            jobs.append({"filename": filename, "error": "Empty file"})
            continue

        job_id = create_job(filename)
        file_size = len(data)

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


@routes.get(route_prefix + "/admin/upload-status")
async def admin_upload_status(request: web.Request) -> web.Response:
    """Return status of all upload jobs."""
    _check_upload_secret(request)
    return web.json_response({"jobs": get_all_jobs()})


@routes.get(route_prefix + "/admin/upload-status/{job_id}")
async def admin_upload_job_status(request: web.Request) -> web.Response:
    """Return status of a single upload job. Supports SSE via Accept header."""
    _check_upload_secret(request)

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
                "vectors_count": collection_info.vectors_count,
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
        # Check if collection exists
        collections = qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]

        if CANDIDATES_INDEX_NAME not in collection_names:
            return web.json_response(
                {
                    "status": "warning",
                    "message": f"Collection {CANDIDATES_INDEX_NAME} does not exist yet",
                    "available_collections": collection_names,
                }
            )

        # Get collection info
        collection_info = qdrant_client.get_collection(CANDIDATES_INDEX_NAME)

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
                "vectors_count": collection_info.vectors_count,
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
        party_id = data.get("party_id", "place-publique")
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
    from src.models.chunk_metadata import THEME_TAXONOMY, Fiabilite
    from collections import defaultdict

    theme_data: dict[str, dict] = {}
    collection_stats = {}
    total_chunks = 0
    classified_chunks = 0

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
                    party = meta.get("party_name") or meta.get("namespace")
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


async def _run_bertopic_analysis(
    user_messages: list[dict],
    session_ids: set[str],
    cache_key: str,
) -> dict:
    """Run BERTopic on user messages with Firestore result caching.

    Checks bertopic_cache/{cache_key} for a previous result. If the set of
    session_ids hasn't changed, returns the cached result. Otherwise re-runs
    BERTopic and stores the new result.
    """
    import asyncio

    try:
        from bertopic import BERTopic  # noqa: F811
    except ImportError:
        return {"status": "error", "message": "bertopic not installed", "topics": []}

    if len(user_messages) < 5:
        return {
            "status": "insufficient_data",
            "message": f"Only {len(user_messages)} user messages found. Need at least 5.",
            "total_messages": len(user_messages),
            "topics": [],
        }

    # ── Check cache ──
    sorted_ids = sorted(session_ids)
    loop = asyncio.get_event_loop()
    try:
        def _read_cache():
            return db.collection("bertopic_cache").document(cache_key).get()

        cache_doc = await loop.run_in_executor(None, _read_cache)
        if cache_doc.exists:
            cached = cache_doc.to_dict() or {}
            if cached.get("session_ids") == sorted_ids:
                logger.info(f"BERTopic cache hit for '{cache_key}' ({len(sorted_ids)} sessions unchanged)")
                return cached.get("result", {})
            else:
                logger.info(
                    f"BERTopic cache miss for '{cache_key}': "
                    f"{len(cached.get('session_ids', []))} cached vs {len(sorted_ids)} current sessions"
                )
    except Exception as e:
        logger.warning(f"BERTopic cache read failed: {e}")

    # ── Run BERTopic ──
    try:
        texts = [m["text"] for m in user_messages]

        def _run():
            from sklearn.feature_extraction.text import CountVectorizer

            topic_model = BERTopic(
                language="french",
                min_topic_size=max(2, len(texts) // 20),
                nr_topics="auto",
                vectorizer_model=CountVectorizer(
                    stop_words="french", ngram_range=(1, 2)
                ),
                calculate_probabilities=False,
            )
            topics, _ = topic_model.fit_transform(texts)
            return topic_model, topics

        loop = asyncio.get_event_loop()
        topic_model, topics = await loop.run_in_executor(None, _run)

        topic_info = topic_model.get_topic_info()
        topics_list = []
        for _, row in topic_info.iterrows():
            topic_id = int(row["Topic"])
            label = "Outliers" if topic_id == -1 else row.get("Name", f"Topic {topic_id}")
            topic_words = topic_model.get_topic(topic_id)
            words = [{"word": w, "weight": round(s, 4)} for w, s in (topic_words or [])]
            doc_indices = [i for i, t in enumerate(topics) if t == topic_id]
            representative_msgs = [
                {
                    "text": user_messages[i]["text"],
                    "session_id": user_messages[i]["session_id"],
                    "chat_title": user_messages[i]["chat_title"],
                }
                for i in doc_indices[:5]
            ]
            party_counts: dict[str, int] = {}
            for i in doc_indices:
                for pid in user_messages[i].get("party_ids", []):
                    party_counts[pid] = party_counts.get(pid, 0) + 1

            topics_list.append({
                "topic_id": topic_id,
                "label": label,
                "count": int(row["Count"]),
                "percentage": round(int(row["Count"]) / len(texts) * 100, 1),
                "words": words[:10],
                "representative_messages": representative_msgs,
                "by_party": party_counts,
            })

        result = {
            "status": "success",
            "total_messages": len(texts),
            "num_topics": len(topics_list),
            "topics": sorted(topics_list, key=lambda x: x["count"], reverse=True),
        }

        # ── Store in cache ──
        try:
            def _write_cache():
                db.collection("bertopic_cache").document(cache_key).set(
                    {"session_ids": sorted_ids, "result": result}
                )

            await loop.run_in_executor(None, _write_cache)
            logger.info(f"BERTopic result cached for '{cache_key}' ({len(sorted_ids)} sessions)")
        except Exception as e:
            logger.warning(f"BERTopic cache write failed: {e}")

        return result

    except Exception as e:
        logger.error(f"BERTopic failed for '{cache_key}': {e}", exc_info=True)
        return {"status": "error", "message": str(e), "topics": []}


@routes.get(f"{route_prefix}/experiment/bertopic-analysis")
async def experiment_bertopic_analysis(request):
    """Run BERTopic clustering on user chat messages from Firestore."""
    # DISABLED: BERTopic triggers Numba JIT which causes SIGABRT crashes on
    # macOS ARM64 when called from async thread executors. Re-enable when Adelin asks for it.
    # user_messages, session_ids = await _collect_user_messages()
    # result = await _run_bertopic_analysis(user_messages, session_ids, cache_key="global")
    result = {"status": "disabled", "message": "BERTopic temporarily disabled", "topics": []}
    return web.json_response(result, status=200)


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
    from src.models.chunk_metadata import THEME_TAXONOMY

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
                        ],
                        with_vectors=False,
                    )
                    for p in points:
                        meta = (p.payload or {}).get("metadata", {})
                        _total += 1
                        theme = meta.get("theme")
                        if not theme:
                            continue
                        list_name = meta.get("party_name") or meta.get("namespace", "")
                        if theme not in _theme_data:
                            _theme_data[theme] = {
                                "theme": theme,
                                "total_count": 0,
                                "by_list": defaultdict(int),
                            }
                        _theme_data[theme]["total_count"] += 1
                        if list_name:
                            _theme_data[theme]["by_list"][list_name] += 1
                    if next_offset is None:
                        break
                    offset = next_offset
            except Exception as e:
                logger.error(f"Error scrolling {col_name} for commune {commune_code}: {e}", exc_info=True)
        return _theme_data, _total

    theme_data, total_chunks = _scroll_qdrant_themes(
        qdrant_filter, [PARTY_INDEX_NAME, CANDIDATES_INDEX_NAME]
    )

    # Fallback: if no commune-specific chunks, use national manifesto data
    if total_chunks == 0:
        logger.info(f"No commune-specific chunks for {commune_code}, falling back to national manifesto data")
        theme_data, total_chunks = _scroll_qdrant_themes(
            None, [PARTY_INDEX_NAME]  # No filter — all national manifesto chunks
        )

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

    # ── 5. BERTopic on commune messages (cached per commune) ────────────────
    # DISABLED: BERTopic triggers Numba JIT which causes SIGABRT crashes on
    # macOS ARM64 when called from async thread executors (concurrent with
    # Socket.IO events). Re-enable when Adelin asks for it.
    # bertopic_result = await _run_bertopic_analysis(
    #     user_messages, session_ids, cache_key=f"commune_{commune_code}"
    # )
    bertopic_result = {"status": "disabled", "message": "BERTopic temporarily disabled", "topics": []}

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
        "bertopic": bertopic_result,
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
    "professions", "seed", "scraper", "crawl_scraper", "indexer",
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


@routes.post(f"{route_prefix}/admin/data-sources/run/{{node_id}}")
async def ds_run_node(request):
    """Run a single pipeline node in the background."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    node_id = request.match_info["node_id"]

    from src.services.data_pipeline import PIPELINE_NODES
    node = PIPELINE_NODES.get(node_id)
    if not node:
        return web.json_response({"error": f"Unknown node: {node_id}"}, status=404)

    body = await request.json() if request.content_length else {}
    force = body.get("force", False)

    # Don't start if already running
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
    top_communes = body.get("top_communes")

    from src.services.data_pipeline import PIPELINE_NODES, clear_context
    from src.services.data_pipeline.base import load_config

    # Don't start if a run-all is already in progress
    if "_run_all" in _pipeline_tasks and not _pipeline_tasks["_run_all"].done():
        return web.json_response({"status": "already_running"})

    async def _run_all():
        clear_context()

        # If top_communes is specified, inject it into population settings
        if top_communes is not None:
            from src.services.data_pipeline.base import save_config as _save
            node = PIPELINE_NODES.get("population")
            if node:
                cfg = await load_config("population", node.default_config())
                cfg.settings["top_communes"] = top_communes
                await _save(cfg)

        for node_id in _PIPELINE_ORDER:
            node = PIPELINE_NODES.get(node_id)
            if not node:
                continue
            cfg = await load_config(node_id, node.default_config())
            if not cfg.enabled and not force:
                logger.info("[data-sources] run-all: skipping disabled node %s", node_id)
                continue
            try:
                logger.info("[data-sources] run-all: executing %s", node_id)
                # Register each node as its own task so it can be stopped individually
                node_task = asyncio.create_task(node.execute(force=force))
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
    """Cancel a running pipeline node task."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    node_id = request.match_info["node_id"]

    from src.services.data_pipeline.base import update_status, NodeStatus

    task = _pipeline_tasks.get(node_id)
    if task and not task.done():
        task.cancel()
        _pipeline_tasks.pop(node_id, None)
        await update_status(node_id, NodeStatus.ERROR, last_error="Stopped by admin")
        return web.json_response({"status": "stopped", "node_id": node_id})

    # Also clear stale "running" state from Firestore (e.g. after server restart)
    from src.services.data_pipeline.base import load_config, _config_ref
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
        SHEET_RANGE,
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


@routes.get(f"{route_prefix}/admin/chat-sessions")
async def admin_list_chat_sessions(request: web.Request) -> web.Response:
    """List chat sessions with pagination and filters."""
    if not _check_admin_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)

    limit = min(int(request.query.get("limit", "50")), 200)
    offset = int(request.query.get("offset", "0"))
    status_filter = request.query.get("status")
    municipality = request.query.get("municipality_code")
    since = request.query.get("since")
    sort_by = request.query.get("sort_by", "updated_at")
    order = request.query.get("order", "desc")

    from google.cloud.firestore_v1 import Query as _FsQuery
    query = db.collection("chat_sessions")

    if municipality:
        query = query.where("municipality_code", "==", municipality)
    if status_filter:
        query = query.where("debug.status", "==", status_filter)
    if since:
        from datetime import datetime, timezone
        since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        query = query.where("updated_at", ">=", since_dt)

    direction = _FsQuery.DESCENDING if order == "desc" else _FsQuery.ASCENDING
    query = query.order_by(sort_by, direction=direction)

    docs = query.offset(offset).limit(limit + 1).stream()
    sessions = []
    for doc in docs:
        data = doc.to_dict()
        data["session_id"] = doc.id
        sessions.append(data)

    has_more = len(sessions) > limit
    sessions = sessions[:limit]

    return web.json_response(
        {
            "sessions": sessions,
            "total": len(sessions),
            "has_more": has_more,
            "offset": offset,
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
        candidates = [
            doc.to_dict() | {"id": doc.id}
            async for doc in async_db.collection("candidates").stream()
        ]
        parties = [
            doc.to_dict() | {"id": doc.id}
            async for doc in async_db.collection("parties").stream()
        ]

        no_website = [c for c in candidates if not c.get("has_website")]
        no_manifesto_parties = [p for p in parties if not p.get("manifesto_pdf_url")]

        if no_website:
            data_warnings.append(
                {
                    "severity": "warning",
                    "category": "data",
                    "message": f"{len(no_website)} candidates missing websites",
                    "count": len(no_website),
                    "tab_link": "coverage",
                }
            )
        if no_manifesto_parties:
            data_warnings.append(
                {
                    "severity": "warning",
                    "category": "data",
                    "message": f"{len(no_manifesto_parties)} parties missing manifestos",
                    "count": len(no_manifesto_parties),
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
    web.run_app(app, host=host, port=port)
