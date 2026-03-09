"""
Wrapper v8: test each _deferred_init step individually with strict timeouts.
Reports which step hangs via the /health endpoint.
"""
import os
import asyncio
import logging

os.environ["DISABLE_SOCKETIO"] = "1"

from aiohttp import web

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wrapper")

_init_status = {"step": "not started", "error": None, "completed": False}


async def init_health(request):
    return web.json_response(_init_status)


if __name__ == "__main__":
    logger.info("=== wrapper v8: testing each init step ===")

    from src.aiohttp_app import app as real_app
    from src.llms import reset_all_rate_limits
    from src.services.firestore_listener import start_parties_listener, start_candidates_listener
    from src.services.scheduler import create_scheduler

    # Clear original on_startup, add our diagnostic one
    real_app.on_startup.clear()

    # Add diagnostic health endpoint
    real_app.router.add_get("/init-status", init_health)

    async def diagnostic_startup(app):
        global _init_status

        # Step 1: reset_all_rate_limits
        _init_status["step"] = "reset_all_rate_limits"
        logger.info("=== Step 1: reset_all_rate_limits ===")
        try:
            await asyncio.wait_for(reset_all_rate_limits(), timeout=10)
            logger.info("=== Step 1 OK ===")
        except asyncio.TimeoutError:
            logger.error("=== Step 1 TIMED OUT ===")
            _init_status["error"] = "reset_all_rate_limits timed out (10s)"
        except Exception as e:
            logger.error(f"=== Step 1 FAILED: {e} ===")
            _init_status["error"] = f"reset_all_rate_limits failed: {e}"

        # Step 2: start_parties_listener (in thread with timeout)
        _init_status["step"] = "start_parties_listener"
        logger.info("=== Step 2: start_parties_listener ===")
        try:
            loop = asyncio.get_running_loop()
            await asyncio.wait_for(
                loop.run_in_executor(None, lambda: start_parties_listener(event_loop=loop)),
                timeout=15,
            )
            logger.info("=== Step 2 OK ===")
        except asyncio.TimeoutError:
            logger.error("=== Step 2 TIMED OUT ===")
            _init_status["error"] = "start_parties_listener timed out (15s)"
        except Exception as e:
            logger.error(f"=== Step 2 FAILED: {e} ===")
            _init_status["error"] = f"start_parties_listener failed: {e}"

        # Step 3: start_candidates_listener (in thread with timeout)
        _init_status["step"] = "start_candidates_listener"
        logger.info("=== Step 3: start_candidates_listener ===")
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, lambda: start_candidates_listener(event_loop=loop)),
                timeout=15,
            )
            logger.info("=== Step 3 OK ===")
        except asyncio.TimeoutError:
            logger.error("=== Step 3 TIMED OUT ===")
            _init_status["error"] = "start_candidates_listener timed out (15s)"
        except Exception as e:
            logger.error(f"=== Step 3 FAILED: {e} ===")
            _init_status["error"] = f"start_candidates_listener failed: {e}"

        # Step 4: create_scheduler
        _init_status["step"] = "create_scheduler"
        logger.info("=== Step 4: create_scheduler ===")
        try:
            scheduler = create_scheduler()
            scheduler.start()
            logger.info("=== Step 4 OK ===")
        except Exception as e:
            logger.error(f"=== Step 4 FAILED: {e} ===")
            _init_status["error"] = f"create_scheduler failed: {e}"

        _init_status["step"] = "complete"
        _init_status["completed"] = True
        logger.info("=== All steps complete ===")

    # Run as BACKGROUND TASK, not blocking on_startup
    async def bg_startup(app):
        logger.info("=== bg_startup: scheduling diagnostic init ===")
        asyncio.create_task(diagnostic_startup(app))

    real_app.on_startup.append(bg_startup)

    logger.info("=== starting real app on 0.0.0.0:8080 ===")
    web.run_app(real_app, host="0.0.0.0", port=8080)
