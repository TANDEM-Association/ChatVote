"""
Production wrapper: skip startup Firestore listeners and rate limit reset.
The server serves HTTP requests immediately. Listeners can be started
manually via admin endpoints if needed.
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
    logger.info("=== production wrapper: importing app ===")

    from src.aiohttp_app import app

    # Remove all on_startup handlers — they try async Firestore operations
    # that block the gRPC event loop on Scaleway serverless containers.
    app.on_startup.clear()
    logger.info("Cleared on_startup handlers (Firestore listeners skipped)")

    logger.info("=== starting app on 0.0.0.0:8080 ===")
    web.run_app(app, host="0.0.0.0", port=8080)
