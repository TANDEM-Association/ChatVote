"""
Wrapper: temporarily disable Socket.IO and start the real app.
This helps diagnose if Socket.IO is causing HTTP requests to hang.
"""
import os
import logging

# Disable Socket.IO before importing the app
os.environ["DISABLE_SOCKETIO"] = "1"

from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wrapper")

if __name__ == "__main__":
    logger.info("=== wrapper: importing real app (Socket.IO disabled) ===")

    from src.aiohttp_app import app

    logger.info(f"=== wrapper: app loaded, {len(app.on_startup)} on_startup handlers ===")
    logger.info("=== wrapper: starting app on 0.0.0.0:8080 ===")
    web.run_app(app, host="0.0.0.0", port=8080)
