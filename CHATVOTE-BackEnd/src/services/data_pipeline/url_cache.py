"""URL-level HTTP response cache — local filesystem or S3.

Each fetched URL is stored keyed by sha256(url).

Backend selection:
  - **Local** (default when S3_ACCESS_KEY is absent): files under
    ``<project>/.cache/url_cache/<hex_digest>`` — fast for dev.
  - **S3** (when S3_ACCESS_KEY is set): objects in an S3-compatible bucket
    (Scaleway Object Storage in prod).

Env vars (S3 mode, shared with qdrant_snapshot.py):
    S3_ENDPOINT_URL  - e.g. https://s3.fr-par.scw.cloud
    S3_ACCESS_KEY    - Scaleway access key
    S3_SECRET_KEY    - Scaleway secret key
    S3_REGION        - e.g. fr-par (default)
    S3_CACHE_BUCKET  - bucket for URL cache (default: chatvote-url-cache)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    import boto3 as boto3_type

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Local filesystem cache directory
# ---------------------------------------------------------------------------
_LOCAL_CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "url_cache"

# ---------------------------------------------------------------------------
# S3 client (lazy singleton)
# ---------------------------------------------------------------------------
_s3_client: "boto3_type.client | None | bool" = False  # False = not yet initialised


def _use_s3() -> bool:
    """Return True when S3 credentials are available."""
    return bool(os.environ.get("S3_ACCESS_KEY", ""))


def _get_s3_client():
    """Lazy singleton S3 client. Returns None if S3_ACCESS_KEY is not set."""
    global _s3_client
    if _s3_client is not False:
        return _s3_client

    access_key = os.environ.get("S3_ACCESS_KEY", "")
    if not access_key:
        _s3_client = None
        return None

    try:
        import boto3

        _s3_client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            aws_access_key_id=access_key,
            aws_secret_access_key=os.environ.get("S3_SECRET_KEY", ""),
            region_name=os.environ.get("S3_REGION", "fr-par"),
        )
        logger.info("[url_cache] S3 backend initialised (bucket=%s)", _bucket())
    except Exception as exc:
        logger.warning("[url_cache] Failed to create S3 client: %s", exc)
        _s3_client = None

    return _s3_client


def _cache_key(url: str) -> str:
    """Return the cache key for a given URL (sha256 hex digest)."""
    return sha256(url.encode()).hexdigest()


def _bucket() -> str:
    return os.environ.get("S3_CACHE_BUCKET", "chatvote-url-cache")


# ---------------------------------------------------------------------------
# Local filesystem helpers
# ---------------------------------------------------------------------------
def _local_get(key: str) -> bytes | None:
    path = _LOCAL_CACHE_DIR / key
    if path.exists():
        return path.read_bytes()
    return None


def _local_put(key: str, body: bytes, url: str, content_type: str) -> None:
    _LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = _LOCAL_CACHE_DIR / key
    path.write_bytes(body)
    # Store metadata alongside
    meta_path = _LOCAL_CACHE_DIR / f"{key}.meta.json"
    meta_path.write_text(json.dumps({
        "url": url,
        "content_type": content_type,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "size_bytes": len(body),
    }))


# ---------------------------------------------------------------------------
# Core fetch with caching
# ---------------------------------------------------------------------------
async def cached_fetch(
    session: aiohttp.ClientSession,
    url: str,
    *,
    headers: dict | None = None,
    skip_cache: bool = False,
) -> bytes | None:
    """Fetch a URL with caching (local filesystem or S3).

    Returns the response body as bytes, or None on non-200 responses.
    Cache misses and backend errors degrade silently to a normal network fetch.
    """
    loop = asyncio.get_event_loop()
    key = _cache_key(url)

    if not skip_cache:
        if _use_s3():
            # --- S3 cache check ---
            s3 = _get_s3_client()
            if s3 is not None:
                try:
                    obj = await loop.run_in_executor(
                        None, lambda: s3.get_object(Bucket=_bucket(), Key=key)
                    )
                    body = obj["Body"].read()
                    logger.debug("[url_cache] S3 HIT %s", url)
                    return body
                except Exception:
                    logger.debug("[url_cache] S3 MISS %s", url)
        else:
            # --- Local cache check ---
            cached = _local_get(key)
            if cached is not None:
                logger.debug("[url_cache] LOCAL HIT %s", url)
                return cached
            logger.debug("[url_cache] LOCAL MISS %s", url)

    # --- Network fetch with retry + exponential backoff for rate limits ---
    max_retries = 5
    body: bytes | None = None
    content_type = ""
    for attempt in range(max_retries + 1):
        try:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 429 or resp.status >= 500:
                    retry_after = float(resp.headers.get("Retry-After", 0))
                    backoff = max(retry_after, 2 ** attempt)
                    if attempt < max_retries:
                        logger.warning(
                            "[url_cache] %d for %s — retry %d/%d in %.1fs",
                            resp.status, url, attempt + 1, max_retries, backoff,
                        )
                        await asyncio.sleep(backoff)
                        continue
                    logger.warning("[url_cache] %d for %s — exhausted retries", resp.status, url)
                    return None
                if resp.status != 200:
                    err_body = (await resp.read())[:500].decode("utf-8", errors="replace")
                    logger.warning("[url_cache] non-200 (%d) for %s — %s", resp.status, url, err_body)
                    return None
                body = await resp.read()
                content_type = resp.content_type or ""
                break
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            backoff = 2 ** attempt
            if attempt < max_retries:
                logger.warning(
                    "[url_cache] fetch error for %s: %s — retry %d/%d in %.1fs",
                    url, exc, attempt + 1, max_retries, backoff,
                )
                await asyncio.sleep(backoff)
                continue
            logger.warning("[url_cache] fetch failed for %s after %d retries: %s", url, max_retries, exc)
            return None
        except Exception as exc:
            logger.warning("[url_cache] fetch failed for %s: %s", url, exc)
            return None
    if body is None:
        return None

    # --- Store in cache ---
    if not skip_cache:
        if _use_s3():
            s3 = _get_s3_client()
            if s3 is not None:
                metadata = {
                    "url": url[:1024],
                    "content_type": content_type,
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }
                try:
                    await loop.run_in_executor(
                        None,
                        lambda: s3.put_object(
                            Bucket=_bucket(), Key=key, Body=body, Metadata=metadata,
                        ),
                    )
                    logger.debug("[url_cache] S3 STORED %s (%d bytes)", url, len(body))
                except Exception as exc:
                    logger.warning("[url_cache] S3 store failed for %s: %s", url, exc)
        else:
            try:
                _local_put(key, body, url, content_type)
                logger.debug("[url_cache] LOCAL STORED %s (%d bytes)", url, len(body))
            except Exception as exc:
                logger.warning("[url_cache] local store failed for %s: %s", url, exc)

    return body


async def cached_fetch_text(
    session: aiohttp.ClientSession,
    url: str,
    *,
    headers: dict | None = None,
    encoding: str = "utf-8",
    skip_cache: bool = False,
) -> str | None:
    """Fetch a URL and decode the response as text."""
    data = await cached_fetch(session, url, headers=headers, skip_cache=skip_cache)
    if data is None:
        return None
    return data.decode(encoding, errors="replace")


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------
async def bust_cache(prefix: str = "") -> dict:
    """Delete all cached URL responses.

    Returns {"deleted": count, "backend": "s3"|"local"}.
    """
    if _use_s3():
        return await _bust_s3(prefix)
    return _bust_local()


async def _bust_s3(prefix: str = "") -> dict:
    loop = asyncio.get_event_loop()
    s3 = _get_s3_client()
    if s3 is None:
        return {"deleted": 0, "backend": "s3", "reason": "S3 client init failed"}

    bucket = _bucket()

    def _delete_all() -> int:
        paginator = s3.get_paginator("list_objects_v2")
        kwargs: dict = {"Bucket": bucket}
        if prefix:
            kwargs["Prefix"] = prefix

        to_delete = []
        for page in paginator.paginate(**kwargs):
            for obj in page.get("Contents", []):
                to_delete.append({"Key": obj["Key"]})

        if not to_delete:
            return 0

        deleted = 0
        for i in range(0, len(to_delete), 1000):
            batch = to_delete[i : i + 1000]
            s3.delete_objects(Bucket=bucket, Delete={"Objects": batch})
            deleted += len(batch)
        return deleted

    try:
        count = await loop.run_in_executor(None, _delete_all)
        logger.info("[url_cache] bust S3 cache: deleted %d objects", count)
        return {"deleted": count, "backend": "s3"}
    except Exception as exc:
        logger.error("[url_cache] bust S3 cache failed: %s", exc)
        return {"deleted": 0, "backend": "s3", "error": str(exc)}


def _bust_local() -> dict:
    if not _LOCAL_CACHE_DIR.exists():
        return {"deleted": 0, "backend": "local"}
    count = sum(1 for f in _LOCAL_CACHE_DIR.iterdir() if not f.name.endswith(".meta.json"))
    shutil.rmtree(_LOCAL_CACHE_DIR, ignore_errors=True)
    logger.info("[url_cache] bust local cache: deleted %d files from %s", count, _LOCAL_CACHE_DIR)
    return {"deleted": count, "backend": "local", "path": str(_LOCAL_CACHE_DIR)}


async def cache_stats() -> dict:
    """Return statistics about the URL cache."""
    if _use_s3():
        return await _stats_s3()
    return _stats_local()


async def _stats_s3() -> dict:
    loop = asyncio.get_event_loop()
    s3 = _get_s3_client()
    if s3 is None:
        return {"total_objects": 0, "total_size_mb": 0.0, "backend": "s3", "enabled": False}

    bucket = _bucket()

    def _stats() -> tuple[int, float]:
        paginator = s3.get_paginator("list_objects_v2")
        total_objects = 0
        total_bytes = 0
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                total_objects += 1
                total_bytes += obj.get("Size", 0)
        return total_objects, total_bytes / (1024 * 1024)

    try:
        total_objects, total_size_mb = await loop.run_in_executor(None, _stats)
        return {
            "total_objects": total_objects,
            "total_size_mb": round(total_size_mb, 2),
            "backend": "s3",
            "bucket": bucket,
            "enabled": True,
        }
    except Exception as exc:
        logger.error("[url_cache] S3 stats failed: %s", exc)
        return {"total_objects": 0, "total_size_mb": 0.0, "backend": "s3", "enabled": True, "error": str(exc)}


def _stats_local() -> dict:
    if not _LOCAL_CACHE_DIR.exists():
        return {"total_objects": 0, "total_size_mb": 0.0, "backend": "local", "path": str(_LOCAL_CACHE_DIR), "enabled": True}

    total_objects = 0
    total_bytes = 0
    for f in _LOCAL_CACHE_DIR.iterdir():
        if not f.name.endswith(".meta.json"):
            total_objects += 1
            total_bytes += f.stat().st_size
    return {
        "total_objects": total_objects,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
        "backend": "local",
        "path": str(_LOCAL_CACHE_DIR),
        "enabled": True,
    }
