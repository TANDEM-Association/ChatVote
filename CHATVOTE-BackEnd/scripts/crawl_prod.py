#!/usr/bin/env python3
"""
Crawl and index candidate websites into PROD Qdrant.

Sets prod env vars before importing any modules that read them.

Usage:
    GOOGLE_APPLICATION_CREDENTIALS=~/Downloads/chat-vote-prod-firebase-adminsdk-fbsvc-*.json \
    python3 scripts/crawl_prod.py [--force]
"""
import os
import sys

# Set prod env BEFORE any imports that read .env
os.environ["API_NAME"] = "chatvote-api"
os.environ["ENV"] = "prod"
os.environ["QDRANT_URL"] = "https://chatvoteoan3waxf-qdrant-prod.functions.fnc.fr-par.scw.cloud"

# Keep GOOGLE_API_KEY from .env if not already set
from dotenv import dotenv_values
env_file = dotenv_values(os.path.join(os.path.dirname(__file__), "..", ".env"))
if "GOOGLE_API_KEY" not in os.environ and "GOOGLE_API_KEY" in env_file:
    os.environ["GOOGLE_API_KEY"] = env_file["GOOGLE_API_KEY"]

# Firebase prod credentials — GOOGLE_APPLICATION_CREDENTIALS is auto-detected
# by firebase_admin.initialize_app() in firebase_service.py
cred_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
if not cred_path:
    print("ERROR: GOOGLE_APPLICATION_CREDENTIALS not set")
    sys.exit(1)

# Now import everything (they'll see prod env vars)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import logging
import time

from src.services.candidate_indexer import index_candidate_website
from src.services.candidate_website_scraper import CandidateWebsiteScraper
from src.firebase_service import aget_candidates_with_website
from src.vector_store_helper import qdrant_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MAX_CONCURRENT = int(os.getenv("CRAWL_CONCURRENCY", "10"))
FORCE = "--force" in sys.argv


def get_indexed_namespaces() -> set[str]:
    """Return set of namespaces already in Qdrant."""
    try:
        namespaces = set()
        offset = None
        while True:
            results, offset = qdrant_client.scroll(
                collection_name="candidates_websites_prod",
                limit=100,
                offset=offset,
                with_payload=["metadata.namespace"],
                with_vectors=False,
            )
            if not results:
                break
            for point in results:
                ns = point.payload.get("metadata", {}).get("namespace", "")
                if ns:
                    namespaces.add(ns)
            if offset is None:
                break
        return namespaces
    except Exception as e:
        logger.warning(f"Could not check existing index: {e}")
        return set()


async def crawl_and_index_one(candidate, scraper, semaphore, results):
    async with semaphore:
        cid = candidate.candidate_id
        name = candidate.full_name
        city = candidate.municipality_name or "?"
        url = candidate.website_url
        logger.info(f"[START] {cid} — {name} ({city}) — {url}")
        t0 = time.time()
        try:
            scraped = await scraper.scrape_candidate_website(candidate)
            if scraped and scraped.is_successful:
                count = await index_candidate_website(candidate, scraped)
                elapsed = time.time() - t0
                logger.info(f"[OK]    {cid} — {count} chunks indexed ({elapsed:.1f}s)")
                results[cid] = {"status": "ok", "chunks": count, "time": elapsed}
            else:
                elapsed = time.time() - t0
                err = scraped.error if scraped else "no result"
                logger.warning(f"[FAIL]  {cid} — scrape failed: {err} ({elapsed:.1f}s)")
                results[cid] = {"status": "scrape_failed", "error": str(err), "time": elapsed}
        except Exception as e:
            elapsed = time.time() - t0
            logger.error(f"[ERROR] {cid} — {e} ({elapsed:.1f}s)")
            results[cid] = {"status": "error", "error": str(e), "time": elapsed}


async def main():
    logger.info(f"=== PROD Candidate Website Crawler (concurrency={MAX_CONCURRENT}, force={FORCE}) ===")
    logger.info(f"ENV={os.environ.get('ENV')}, QDRANT_URL={os.environ.get('QDRANT_URL')}")

    candidates = await aget_candidates_with_website()
    logger.info(f"Found {len(candidates)} candidates with websites in Firestore")

    if not candidates:
        logger.warning("No candidates to crawl!")
        return

    # Check which are already indexed
    if not FORCE:
        indexed = get_indexed_namespaces()
        already = [c for c in candidates if c.candidate_id in indexed]
        candidates = [c for c in candidates if c.candidate_id not in indexed]
        logger.info(f"Already indexed: {len(already)}, to crawl: {len(candidates)}")

    if not candidates:
        logger.info("All candidates already indexed! Nothing to do.")
        return

    logger.info(f"Will crawl {len(candidates)} candidates")

    scraper = CandidateWebsiteScraper()
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    results = {}

    t_start = time.time()
    tasks = [crawl_and_index_one(c, scraper, semaphore, results) for c in candidates]
    await asyncio.gather(*tasks)
    total_time = time.time() - t_start

    ok = sum(1 for r in results.values() if r["status"] == "ok")
    failed = sum(1 for r in results.values() if r["status"] != "ok")
    total_chunks = sum(r.get("chunks", 0) for r in results.values())

    print(f"\n{'='*60}")
    print(f"CRAWL COMPLETE in {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"  OK: {ok}/{len(results)} candidates")
    print(f"  Failed: {failed}/{len(results)}")
    print(f"  Total chunks indexed: {total_chunks}")
    print(f"{'='*60}")

    if failed:
        print("\nFailed candidates:")
        for cid, r in sorted(results.items()):
            if r["status"] != "ok":
                print(f"  [{r['status']}] {cid}: {r.get('error', '?')}")


if __name__ == "__main__":
    asyncio.run(main())
