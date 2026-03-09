"""Check production status of all ChatVote services.

Usage:
    poetry run python scripts/check_prod_status.py
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

import aiohttp

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKEND_URL = "https://chatvoteoan3waxf-backend-prod.functions.fnc.fr-par.scw.cloud"
FRONTEND_URL = "https://app.chatvote.org"
LOKI_URL = os.environ.get(
    "SCALEWAY_COCKPIT_LOGS_URL",
    "https://3160ee03-9475-4793-8f22-748cff072a91.logs.cockpit.fr-par.scw.cloud",
)
LOKI_TOKEN = os.environ.get("SCALEWAY_COCKPIT_LOGS_TOKEN", "")

# Load token from .env if not in environment
if not LOKI_TOKEN:
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.startswith("SCALEWAY_COCKPIT_LOGS_TOKEN="):
                    LOKI_TOKEN = line.strip().split("=", 1)[1]

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


def ok(msg: str) -> str:
    return f"{GREEN}✓{RESET} {msg}"


def fail(msg: str) -> str:
    return f"{RED}✗{RESET} {msg}"


def warn(msg: str) -> str:
    return f"{YELLOW}⚠{RESET} {msg}"


def header(msg: str) -> str:
    return f"\n{BOLD}{CYAN}── {msg} ──{RESET}"


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


async def check_backend_health(session: aiohttp.ClientSession) -> dict:
    """Check backend /health endpoint."""
    try:
        t0 = time.monotonic()
        async with session.get(f"{BACKEND_URL}/health", timeout=aiohttp.ClientTimeout(total=15)) as resp:
            elapsed = time.monotonic() - t0
            data = await resp.json()
            checks = data.get("checks", {})
            return {
                "status": data.get("status") == "ok",
                "latency_ms": int(elapsed * 1000),
                "qdrant": checks.get("qdrant", {}).get("status") == "ok",
                "firestore": checks.get("firestore", {}).get("status") == "ok",
                "llms": checks.get("llms", {}),
            }
    except Exception as e:
        return {"status": False, "error": str(e)}


async def check_frontend(session: aiohttp.ClientSession) -> dict:
    """Check frontend loads."""
    try:
        t0 = time.monotonic()
        async with session.get(FRONTEND_URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            elapsed = time.monotonic() - t0
            text = await resp.text()
            has_content = "ChatVote" in text or "chatvote" in text.lower()
            return {
                "status": resp.status == 200 and has_content,
                "http_status": resp.status,
                "latency_ms": int(elapsed * 1000),
            }
    except Exception as e:
        return {"status": False, "error": str(e)}


async def check_experiment_search(session: aiohttp.ClientSession) -> dict:
    """Check experiment search API works."""
    try:
        t0 = time.monotonic()
        async with session.post(
            f"{FRONTEND_URL}/api/experiment/search",
            json={"query": "environnement", "collection": "all_parties_prod", "limit": 3},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            elapsed = time.monotonic() - t0
            data = await resp.json()
            results = data.get("results", data.get("filtered_results", []))
            top_score = results[0].get("score", 0) if results else 0
            return {
                "status": resp.status == 200 and len(results) > 0,
                "result_count": len(results),
                "top_score": round(top_score, 4),
                "latency_ms": int(elapsed * 1000),
            }
    except Exception as e:
        return {"status": False, "error": str(e)}


async def check_topic_insights(session: aiohttp.ClientSession) -> dict:
    """Check topic insights API."""
    try:
        t0 = time.monotonic()
        async with session.get(
            f"{FRONTEND_URL}/api/experiment/topics",
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            elapsed = time.monotonic() - t0
            data = await resp.json()
            total = data.get("total_chunks", 0)
            classified = data.get("classified_chunks", 0)
            themes = data.get("themes", [])
            return {
                "status": resp.status == 200 and total > 0,
                "total_chunks": total,
                "classified_chunks": classified,
                "theme_count": len(themes),
                "latency_ms": int(elapsed * 1000),
            }
    except Exception as e:
        return {"status": False, "error": str(e)}


async def check_coverage(session: aiohttp.ClientSession) -> dict:
    """Check coverage API."""
    try:
        t0 = time.monotonic()
        async with session.get(
            f"{FRONTEND_URL}/api/coverage",
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            elapsed = time.monotonic() - t0
            data = await resp.json()
            summary = data.get("summary", {})
            parties = data.get("parties", [])
            party_chunks = {p["short_name"]: p["chunk_count"] for p in parties}
            return {
                "status": resp.status == 200,
                "communes": summary.get("total_communes", 0),
                "parties": summary.get("total_parties", 0),
                "candidates": summary.get("total_candidates", 0),
                "total_chunks": summary.get("total_chunks", 0),
                "party_chunks": party_chunks,
                "latency_ms": int(elapsed * 1000),
            }
    except Exception as e:
        return {"status": False, "error": str(e)}


async def check_commune_dashboard(session: aiohttp.ClientSession, code: str = "75056") -> dict:
    """Check commune dashboard API."""
    try:
        t0 = time.monotonic()
        async with session.get(
            f"{FRONTEND_URL}/api/commune/{code}/dashboard",
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            elapsed = time.monotonic() - t0
            data = await resp.json()
            lists = data.get("electoral_lists", [])
            messages = data.get("total_messages", data.get("citizen_questions", {}).get("total", 0))
            return {
                "status": resp.status == 200,
                "list_count": len(lists),
                "message_count": messages,
                "latency_ms": int(elapsed * 1000),
            }
    except Exception as e:
        return {"status": False, "error": str(e)}


async def check_indexing_status(session: aiohttp.ClientSession) -> dict:
    """Check backend indexing status."""
    try:
        async with session.get(
            f"{BACKEND_URL}/api/v1/admin/index-status",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            return await resp.json()
    except Exception as e:
        return {"error": str(e)}


async def check_qdrant_collections(session: aiohttp.ClientSession) -> dict:
    """Check Qdrant collections via diag endpoint."""
    try:
        async with session.get(
            f"{BACKEND_URL}/diag/qdrant",
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            data = await resp.json()
            collections = data.get("qdrant_client", {}).get("collections", [])
            return {
                "status": data.get("qdrant_client", {}).get("ok", False),
                "collections": collections,
            }
    except Exception as e:
        return {"status": False, "error": str(e)}


async def check_crawl_progress(session: aiohttp.ClientSession) -> dict:
    """Check candidate crawling progress from Loki logs."""
    if not LOKI_TOKEN:
        return {"status": None, "error": "No SCALEWAY_COCKPIT_LOGS_TOKEN"}

    import re
    try:
        now = int(time.time())
        start = now - 86400  # last 24h

        # Count completed candidates
        params = {
            "query": '{resource_name="chatvoteoan3waxf-backend-prod"} |~ "Completed .+: \\\\d+ pages"',
            "limit": "500",
            "start": f"{start}000000000",
            "end": f"{now}000000000",
        }
        async with session.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params=params,
            headers={"Authorization": f"Bearer {LOKI_TOKEN}"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()

        completed = set()
        total_pages = 0
        total_chars = 0
        for stream in data.get("data", {}).get("result", []):
            for _ts, line in stream.get("values", []):
                msg = json.loads(line).get("message", "") if line.startswith("{") else line
                m = re.search(r"Completed (.+?): (\d+) pages, (\d+) chars", msg)
                if m:
                    completed.add(m.group(1))
                    total_pages += int(m.group(2))
                    total_chars += int(m.group(3))

        # Get total candidates to crawl
        params2 = {
            "query": '{resource_name="chatvoteoan3waxf-backend-prod"} |~ "Found \\\\d+ candidates with website"',
            "limit": "5",
            "start": f"{start}000000000",
            "end": f"{now}000000000",
        }
        async with session.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params=params2,
            headers={"Authorization": f"Bearer {LOKI_TOKEN}"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data2 = await resp.json()

        total_to_crawl = 0
        for stream in data2.get("data", {}).get("result", []):
            for _ts, line in stream.get("values", []):
                msg = json.loads(line).get("message", "") if line.startswith("{") else line
                m = re.search(r"Found (\d+) candidates with website", msg)
                if m:
                    total_to_crawl = int(m.group(1))

        return {
            "status": True,
            "unique_candidates_crawled": len(completed),
            "total_to_crawl": total_to_crawl,
            "progress_pct": round(len(completed) / total_to_crawl * 100, 1) if total_to_crawl else 0,
            "total_pages": total_pages,
            "total_chars": total_chars,
        }
    except Exception as e:
        return {"status": False, "error": str(e)}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main():
    print(f"\n{BOLD}🔍 ChatVote Production Status Check{RESET}")
    print(f"{DIM}{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}{RESET}")

    async with aiohttp.ClientSession() as session:
        # Run all checks in parallel
        results = await asyncio.gather(
            check_backend_health(session),
            check_frontend(session),
            check_experiment_search(session),
            check_topic_insights(session),
            check_coverage(session),
            check_commune_dashboard(session),
            check_indexing_status(session),
            check_qdrant_collections(session),
            check_crawl_progress(session),
        )

        health, frontend, experiment, topics, coverage, commune, indexing, qdrant, crawl = results

        # ── Backend Health ──
        print(header("Backend Health"))
        if health.get("status"):
            print(ok(f"Backend healthy ({health['latency_ms']}ms)"))
            print(ok("Qdrant connected") if health.get("qdrant") else fail("Qdrant down"))
            print(ok("Firestore connected") if health.get("firestore") else fail("Firestore down"))
            llms = health.get("llms", {})
            available = llms.get("available", [])
            rate_limited = llms.get("rate_limited", [])
            print(ok(f"LLMs: {', '.join(available)}") if available else fail("No LLMs available"))
            if rate_limited:
                print(warn(f"Rate-limited: {', '.join(rate_limited)}"))
        else:
            print(fail(f"Backend DOWN: {health.get('error', 'unknown')}"))

        # ── Frontend ──
        print(header("Frontend"))
        if frontend.get("status"):
            print(ok(f"app.chatvote.org loads ({frontend['latency_ms']}ms)"))
        else:
            print(fail(f"Frontend error: HTTP {frontend.get('http_status', '?')} — {frontend.get('error', '')}"))

        # ── Qdrant Collections ──
        print(header("Qdrant Collections"))
        if qdrant.get("status"):
            for col in qdrant.get("collections", []):
                print(ok(col))
            if "candidates_websites_prod" not in qdrant.get("collections", []):
                print(warn("candidates_websites_prod not yet created (indexing pending)"))
        else:
            print(fail(f"Qdrant diag failed: {qdrant.get('error', '')}"))

        # ── Coverage ──
        print(header("Data Coverage"))
        if coverage.get("status"):
            print(ok(f"{coverage['communes']} communes, {coverage['parties']} parties, {coverage['candidates']} candidates"))
            print(ok(f"{coverage['total_chunks']} total chunks in Qdrant"))
            party_chunks = coverage.get("party_chunks", {})
            for name, count in sorted(party_chunks.items(), key=lambda x: -x[1]):
                print(f"    {name}: {count} chunks")
        else:
            print(fail(f"Coverage API error: {coverage.get('error', '')}"))

        # ── Topic Insights ──
        print(header("Topic Insights"))
        if topics.get("status"):
            print(ok(f"{topics['total_chunks']} chunks, {topics['classified_chunks']} classified, {topics['theme_count']} themes ({topics['latency_ms']}ms)"))
        else:
            print(fail(f"Topics API error: {topics.get('error', '')}"))

        # ── Experiment Search ──
        print(header("Experiment Search"))
        if experiment.get("status"):
            print(ok(f"Search works — {experiment['result_count']} results, top score {experiment['top_score']} ({experiment['latency_ms']}ms)"))
        else:
            print(fail(f"Search error: {experiment.get('error', '')}"))

        # ── Commune Dashboard ──
        print(header("Commune Dashboard (Paris 75056)"))
        if commune.get("status"):
            print(ok(f"{commune['list_count']} electoral lists, {commune['message_count']} citizen messages ({commune['latency_ms']}ms)"))
        else:
            print(fail(f"Dashboard error: {commune.get('error', '')}"))

        # ── Indexing Status ──
        print(header("Indexing Status"))
        if "error" not in indexing:
            for key, val in indexing.items():
                status = val.get("status", "unknown")
                if status == "done":
                    total = val.get("total", val.get("details", {}))
                    print(ok(f"{key}: done — {total}"))
                elif status == "running":
                    print(warn(f"{key}: running..."))
                elif status == "error":
                    print(fail(f"{key}: error — {val.get('message', '')}"))
                else:
                    print(f"  {key}: {status}")
        else:
            print(fail(f"Index status error: {indexing.get('error')}"))

        # ── Candidate Crawling Progress ──
        print(header("Candidate Crawling (last 24h)"))
        if crawl.get("status"):
            pct = crawl["progress_pct"]
            color = GREEN if pct > 80 else YELLOW if pct > 30 else RED
            print(f"  {color}{crawl['unique_candidates_crawled']}/{crawl['total_to_crawl']} unique candidates ({pct}%){RESET}")
            print(f"  {crawl['total_pages']} pages crawled, {crawl['total_chars']:,} chars extracted")
            if pct < 100:
                remaining = crawl["total_to_crawl"] - crawl["unique_candidates_crawled"]
                # Estimate ~2 min per candidate avg at concurrency 3
                est_hours = remaining * 2 / 60
                print(f"  {DIM}Estimated time remaining: ~{est_hours:.1f}h (at ~2 min/candidate){RESET}")
        elif crawl.get("error"):
            print(warn(f"Could not check: {crawl['error']}"))

        # ── Summary ──
        all_ok = all([
            health.get("status"),
            frontend.get("status"),
            experiment.get("status"),
            topics.get("status"),
            coverage.get("status"),
            commune.get("status"),
        ])
        print(header("Summary"))
        if all_ok:
            print(f"  {GREEN}{BOLD}All core services operational ✓{RESET}")
        else:
            print(f"  {RED}{BOLD}Some services have issues ✗{RESET}")


if __name__ == "__main__":
    asyncio.run(main())
