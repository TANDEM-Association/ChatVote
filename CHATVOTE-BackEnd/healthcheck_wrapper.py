"""
Wrapper that starts a quick health-check server, imports the real app,
then switches to serving it. This lets us see diagnostic output if import fails.
"""
import asyncio
import logging
import sys
import traceback

from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wrapper")


def import_real_app():
    """Import the real application module and return its app."""
    logger.info(">>> Step 1: importing src.utils ...")
    from src import utils
    logger.info(">>> Step 1 OK")

    logger.info(">>> Step 2: importing src.firebase_service ...")
    from src import firebase_service
    logger.info(">>> Step 2 OK")

    logger.info(">>> Step 3: importing src.llms ...")
    from src import llms
    logger.info(">>> Step 3 OK")

    logger.info(">>> Step 4: importing src.vector_store_helper ...")
    from src import vector_store_helper
    logger.info(">>> Step 4 OK")

    logger.info(">>> Step 5: importing src.chatbot_async ...")
    from src import chatbot_async
    logger.info(">>> Step 5 OK")

    logger.info(">>> Step 6: importing src.aiohttp_app ...")
    from src import aiohttp_app
    logger.info(">>> Step 6 OK")

    logger.info(">>> Step 7: importing src.websocket_app (sio) ...")
    from src.websocket_app import sio
    logger.info(">>> Step 7 OK")

    return aiohttp_app.app


if __name__ == "__main__":
    logger.info("=== healthcheck_wrapper starting ===")

    try:
        real_app = import_real_app()
        logger.info("=== All imports succeeded, starting real app on 0.0.0.0:8080 ===")
        web.run_app(real_app, host="0.0.0.0", port=8080)
    except Exception as e:
        logger.error(f"=== FATAL: Failed to start real app: {e} ===")
        logger.error(traceback.format_exc())

        # Fall back to a minimal error server
        async def error_health(request):
            return web.json_response(
                {"status": "error", "error": str(e), "traceback": traceback.format_exc()},
                status=500,
            )

        fallback = web.Application()
        fallback.router.add_get("/healthz", error_health)
        fallback.router.add_get("/health", error_health)
        fallback.router.add_route("*", "/{path:.*}", error_health)
        logger.info("=== Starting fallback error server on 0.0.0.0:8080 ===")
        web.run_app(fallback, host="0.0.0.0", port=8080)
