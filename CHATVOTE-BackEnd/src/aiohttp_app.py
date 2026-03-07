# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0

import argparse
import asyncio
import logging
import os
import json

import aiohttp
from aiohttp import web
import aiohttp_cors
from aiohttp_pydantic.decorator import inject_params

from src.chatbot_async import (
    get_improved_rag_query_voting_behavior,
)
from src.firebase_service import aget_party_by_id, async_db
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


@routes.post(f"{route_prefix}/admin/index-all-manifestos")
async def admin_index_all_manifestos(request):
    """
    Admin endpoint to trigger indexation of all party manifestos.

    This should be called once to index existing parties, or to re-index all.
    """
    logger.info("Admin triggered: indexing all party manifestos")

    try:
        results = await index_all_parties()
        total = sum(results.values())

        return web.json_response(
            {
                "status": "success",
                "message": f"Indexed {total} chunks for {len(results)} parties",
                "details": results,
            }
        )
    except Exception as e:
        logger.error(f"Error indexing manifestos: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500,
        )


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
    """
    Admin endpoint to trigger indexation of all candidate websites.

    This will scrape and index all candidates with a website_url.
    """
    logger.info("Admin triggered: indexing all candidate websites")

    try:
        results = await index_all_candidates()
        total = sum(results.values())
        successful = sum(1 for v in results.values() if v > 0)

        return web.json_response(
            {
                "status": "success",
                "message": f"Indexed {total} chunks for {successful}/{len(results)} candidates",
                "details": results,
            }
        )
    except Exception as e:
        logger.error(f"Error indexing candidate websites: {e}", exc_info=True)
        return web.json_response(
            {"status": "error", "message": str(e)},
            status=500,
        )


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

        results = qdrant_client.search(
            collection_name=PARTY_INDEX_NAME,
            query_vector=("dense", query_vector),
            limit=5,
            with_payload=True,
            query_filter=filter_condition,
            score_threshold=0.3,
        )

        docs = []
        for point in results:
            payload = point.payload or {}
            docs.append(
                {
                    "score": point.score,
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

        results = qdrant_client.search(
            collection_name=col_name,
            query_vector=("dense", query_vector),
            limit=limit,
            with_payload=True,
            query_filter=query_filter,
            score_threshold=0.3,
        )

        docs = []
        for point in results:
            payload = point.payload or {}
            docs.append({
                "score": round(point.score, 4),
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
        except Exception:
            pass

    return web.json_response({
        "themes": THEME_TAXONOMY,
        "fiabilite_levels": {str(f.value): f.name for f in Fiabilite},
        "namespaces": sorted(namespaces),
        "nuances_politiques": sorted(nuances),
        "collections": ["parties", "candidates"],
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

sio.attach(app)


# Start Firestore listeners for automatic indexation
async def on_startup(app):
    """Called when the application starts."""
    # Reset rate limit flag on startup
    logger.info("Resetting LLM rate limit flags on startup...")
    try:
        await reset_all_rate_limits()
        logger.info("LLM rate limit flags reset successfully")
    except Exception as e:
        logger.error(f"Failed to reset rate limit flags: {e}")

    # Get the current event loop for thread-safe async execution
    event_loop = asyncio.get_running_loop()

    # Start Firestore listener for parties (manifesto indexation)
    logger.info("Starting Firestore parties listener...")
    try:
        start_parties_listener(event_loop=event_loop)
        logger.info("Firestore parties listener started successfully")
    except Exception as e:
        logger.error(f"Failed to start Firestore parties listener: {e}")

    # Start Firestore listener for candidates (website indexation)
    logger.info("Starting Firestore candidates listener...")
    try:
        start_candidates_listener(event_loop=event_loop)
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


app.on_startup.append(on_startup)


# Instantiate the argument parser
parser = argparse.ArgumentParser()

# Add arguments to parser
parser.add_argument("--host", type=str, nargs=1, default=["127.0.0.1"])
parser.add_argument("--port", type=int, nargs=1, default=[8080])
parser.add_argument("--debug", action="store_true", default=False)

# Start the server
if __name__ == "__main__":
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
