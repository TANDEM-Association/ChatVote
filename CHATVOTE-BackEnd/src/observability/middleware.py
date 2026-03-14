# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
aiohttp middleware for HTTP request observability.

Automatically instruments all HTTP requests with:
    - Structured logging (method, path, status, duration)
    - Metrics collection (counters, latency histograms)
    - Correlation ID propagation (via X-Correlation-ID header)
    - Request tracing
"""

import time
import uuid

from aiohttp import web

from src.observability.metrics import metrics
from src.observability.structured_logger import set_correlation_id


@web.middleware
async def observability_middleware(request: web.Request, handler):
    """Middleware that instruments all HTTP requests."""
    # Extract or generate correlation ID
    cid = request.headers.get("X-Correlation-ID") or uuid.uuid4().hex[:16]
    set_correlation_id(cid)

    start = time.perf_counter()
    method = request.method
    path = request.path

    # Skip metrics endpoint to avoid recursion
    if path == "/metrics":
        return await handler(request)

    status_code = 500
    try:
        response = await handler(request)
        status_code = response.status
        # Add correlation ID to response headers
        response.headers["X-Correlation-ID"] = cid
        return response
    except web.HTTPException as e:
        status_code = e.status_code
        raise
    except Exception:
        status_code = 500
        raise
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000

        # Record metrics
        labels = {"method": method, "status": str(status_code)}
        metrics.inc_counter("http_requests_total", labels=labels)
        metrics.record_histogram("http_request_duration_ms", elapsed_ms, labels=labels)

        # Don't log health checks at info level (too noisy)
        if path not in ("/healthz", "/health"):
            import logging
            logger = logging.getLogger("http.access")
            logger.info(
                "HTTP %s %s → %d (%.1fms)",
                method, path, status_code, elapsed_ms,
                extra={"data": {
                    "method": method,
                    "path": path,
                    "status": status_code,
                    "duration_ms": round(elapsed_ms, 1),
                    "correlation_id": cid,
                }},
            )
