# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Observability module for ChatVote backend.

Provides structured logging, performance metrics collection, request tracing,
and Prometheus-compatible export. Designed for integration with Grafana/Loki
log aggregation and Prometheus/Grafana dashboards.

Architecture:
    - StructuredLogger: JSON-formatted logs with correlation IDs
    - MetricsCollector: In-memory counters, histograms, gauges with ring buffers
    - RequestTracer: Span-based request tracing across Socket.IO events
    - AlertManager: Threshold-based alerting with configurable rules

Usage:
    from src.observability import metrics, logger, tracer

    # Record a metric
    metrics.record_histogram("llm_response_time_ms", 1234, labels={"model": "gemini"})

    # Start a trace span
    with tracer.span("rag_search", trace_id=request_id) as span:
        span.set_attribute("query", user_question)
        results = await search(...)
        span.set_attribute("result_count", len(results))
"""

from src.observability.metrics import MetricsCollector, metrics
from src.observability.structured_logger import StructuredLogger, get_logger
from src.observability.tracer import RequestTracer, tracer
from src.observability.alerts import AlertManager, alert_manager

__all__ = [
    "MetricsCollector",
    "metrics",
    "StructuredLogger",
    "get_logger",
    "RequestTracer",
    "tracer",
    "AlertManager",
    "alert_manager",
]
