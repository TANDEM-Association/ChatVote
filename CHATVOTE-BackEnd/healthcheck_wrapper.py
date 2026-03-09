"""
Wrapper v6: use the REAL app but strip on_startup handlers.
If this works, the issue is in on_startup. If not, it's in CORS/middleware.
"""
import os
import logging

os.environ["DISABLE_SOCKETIO"] = "1"

from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wrapper")

if __name__ == "__main__":
    logger.info("=== wrapper v6: using REAL app, stripping on_startup ===")

    from src.aiohttp_app import app as real_app

    # Log app state
    logger.info(f"Middlewares: {len(real_app.middlewares)}")
    for i, mw in enumerate(real_app.middlewares):
        logger.info(f"  middleware[{i}]: {mw}")
    logger.info(f"on_startup handlers: {len(real_app.on_startup)}")
    for i, h in enumerate(real_app.on_startup):
        logger.info(f"  on_startup[{i}]: {h.__name__}")
    logger.info(f"Routes: {len(list(real_app.router.routes()))}")

    # Clear on_startup handlers — they try to connect to Firestore
    real_app.on_startup.clear()
    logger.info("Cleared on_startup handlers")

    logger.info("=== wrapper: starting REAL app (no on_startup, no sio) on 0.0.0.0:8080 ===")
    web.run_app(real_app, host="0.0.0.0", port=8080)
