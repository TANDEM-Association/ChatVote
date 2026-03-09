"""
Diagnostic wrapper v4: import real app WITHOUT Socket.IO, test if HTTP works.
"""
import asyncio
import logging
import traceback

from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wrapper")


if __name__ == "__main__":
    logger.info("=== wrapper v4: importing app WITHOUT Socket.IO ===")

    try:
        # Import the module but DON'T use its app (which has sio.attach)
        # Instead, rebuild a fresh app with the same routes
        from src.aiohttp_app import routes, api_key_middleware, on_startup

        fresh_app = web.Application(middlewares=[api_key_middleware])
        fresh_app.router.add_routes(routes)

        # Skip Socket.IO, skip CORS — just test if raw aiohttp works

        # Add the on_startup handler with timeout protection
        async def safe_startup(app):
            logger.info("=== safe_startup: running on_startup with 15s timeout ===")
            try:
                await asyncio.wait_for(on_startup(app), timeout=15)
                logger.info("=== safe_startup: on_startup completed ===")
            except asyncio.TimeoutError:
                logger.error("=== safe_startup: on_startup TIMED OUT (15s) ===")
            except Exception as e:
                logger.error(f"=== safe_startup: on_startup FAILED: {e} ===")

        fresh_app.on_startup.append(safe_startup)

        logger.info("=== wrapper: starting fresh app (no sio, no cors) on 0.0.0.0:8080 ===")
        web.run_app(fresh_app, host="0.0.0.0", port=8080)

    except Exception as e:
        logger.error(f"=== FATAL: {e} ===")
        logger.error(traceback.format_exc())

        async def error_health(request):
            return web.json_response({"status": "error", "error": str(e)}, status=500)

        fallback = web.Application()
        fallback.router.add_route("*", "/{path:.*}", error_health)
        web.run_app(fallback, host="0.0.0.0", port=8080)
