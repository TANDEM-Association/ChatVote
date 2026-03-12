"""CLI entrypoint for K8s CronJobs and admin-launched Jobs.

Usage:
    python -m src.job_runner crawl_scraper
    python -m src.job_runner indexer

Environment variables:
    PIPELINE_FORCE  Set to "true", "1", or "yes" to force re-execution even if
                    the node is up-to-date.  CronJobs always pass force=True;
                    admin-launched jobs set this env var explicitly.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


async def _run(node_id: str) -> None:
    # Import pipeline modules AFTER env vars are loaded so that firebase_service
    # initialises with the correct credentials.
    from src.services.data_pipeline.base import PIPELINE_NODES

    # Import the node modules to trigger their register_node() calls.
    import src.services.data_pipeline.crawl_scraper  # noqa: F401
    import src.services.data_pipeline.indexer  # noqa: F401

    node = PIPELINE_NODES.get(node_id)
    if node is None:
        logging.error("Unknown node_id %r. Available: %s", node_id, list(PIPELINE_NODES))
        sys.exit(1)

    force = os.getenv("PIPELINE_FORCE", "").lower() in ("true", "1", "yes")
    await node.execute(force=force)


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    node_id = sys.argv[1]

    _configure_logging()

    # Load .env before importing anything that touches Firebase.
    from src.utils import load_env
    load_env()

    try:
        asyncio.run(_run(node_id))
    except Exception:
        logging.exception("Job %r failed", node_id)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
