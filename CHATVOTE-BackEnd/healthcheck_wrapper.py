"""
Wrapper that starts a health-check server immediately, then imports the real app.
This ensures the container responds to health checks while the heavy app loads.
"""
import asyncio
import logging
import sys

from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("wrapper")

_real_app = None
_import_error = None


async def health(request):
    if _import_error:
        return web.json_response({"status": "error", "error": str(_import_error)}, status=500)
    if _real_app is None:
        return web.json_response({"status": "starting"}, status=503)
    return web.json_response({"status": "ok"})


async def proxy_handler(request):
    """Forward all non-health requests to the real app once loaded."""
    if _real_app is None:
        return web.json_response({"status": "starting", "message": "App is still loading"}, status=503)
    # For now just return a simple message — the real app will be attached later
    return web.json_response({"error": "proxy not yet implemented"}, status=503)


async def load_real_app():
    """Import the real application in the background."""
    global _real_app, _import_error
    try:
        logger.info(">>> Importing src.aiohttp_app ...")
        # Step-by-step import to identify where it hangs
        logger.info("Step 1: importing src.utils ...")
        from src import utils
        logger.info("Step 1 OK")

        logger.info("Step 2: importing src.firebase_service ...")
        from src import firebase_service
        logger.info("Step 2 OK")

        logger.info("Step 3: importing src.llms ...")
        from src import llms
        logger.info("Step 3 OK")

        logger.info("Step 4: importing src.vector_store_helper ...")
        from src import vector_store_helper
        logger.info("Step 4 OK")

        logger.info("Step 5: importing src.chatbot_async ...")
        from src import chatbot_async
        logger.info("Step 5 OK")

        logger.info("Step 6: importing src.aiohttp_app ...")
        from src import aiohttp_app
        logger.info("Step 6 OK — real app loaded!")
        _real_app = aiohttp_app.app

    except Exception as e:
        logger.error(f"Failed to import real app: {e}", exc_info=True)
        _import_error = e


async def on_startup(app):
    logger.info("Health-check wrapper started, loading real app in background...")
    asyncio.create_task(load_real_app())


wrapper_app = web.Application()
wrapper_app.router.add_get("/healthz", health)
wrapper_app.router.add_get("/health", health)
wrapper_app.on_startup.append(on_startup)

if __name__ == "__main__":
    logger.info("Starting health-check wrapper on 0.0.0.0:8080")
    web.run_app(wrapper_app, host="0.0.0.0", port=8080)
