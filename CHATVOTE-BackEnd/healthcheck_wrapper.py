"""
Production wrapper: skip startup Firestore listeners and rate limit reset.
The server serves HTTP requests immediately. Listeners can be started
manually via admin endpoints if needed.
"""
import os
import logging

# Socket.IO re-enabled now that Firestore uses sync client in run_in_executor

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

    # ── Diagnostic endpoint to test Firestore connectivity ──
    import asyncio

    async def firestore_diag(request):
        """Test Firestore sync client connectivity with timeout."""
        import time
        from src.firebase_service import db as sync_db

        results = {}

        # Test 1: simple document read with timeout
        def _test_read():
            start = time.monotonic()
            try:
                doc = sync_db.collection("municipalities").document("75056").get()
                elapsed = round(time.monotonic() - start, 3)
                return {"ok": True, "exists": doc.exists, "elapsed_s": elapsed}
            except Exception as e:
                elapsed = round(time.monotonic() - start, 3)
                return {"ok": False, "error": str(e), "elapsed_s": elapsed}

        loop = asyncio.get_event_loop()
        try:
            results["sync_read"] = await asyncio.wait_for(
                loop.run_in_executor(None, _test_read), timeout=15
            )
        except asyncio.TimeoutError:
            results["sync_read"] = {"ok": False, "error": "timeout after 15s"}

        return web.json_response(results)

    app.router.add_get("/diag/firestore", firestore_diag)

    logger.info("=== starting app on 0.0.0.0:8080 ===")
    web.run_app(app, host="0.0.0.0", port=8080)
