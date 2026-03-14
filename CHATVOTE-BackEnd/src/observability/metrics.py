# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
In-memory metrics collector with Prometheus text format export.

Collects counters, histograms, and gauges. Stores time-series data
in ring buffers for dashboard visualization and exports in Prometheus
text exposition format for Grafana scraping.

Metric types:
    - Counter: monotonically increasing (e.g., total_requests)
    - Histogram: distribution of values with configurable buckets (e.g., latency)
    - Gauge: point-in-time value (e.g., active_connections)

Thread-safe via threading.Lock for use from both async and sync contexts.
"""

import os
import time
from collections import defaultdict
from threading import Lock
from typing import Any

# Time-series ring buffer size (one entry per collection interval)
_TS_BUFFER_SIZE = int(os.getenv("OBSERVABILITY_TS_BUFFER_SIZE", "3600"))

# Default histogram buckets (milliseconds for latency metrics)
DEFAULT_LATENCY_BUCKETS = [50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000, 60000]
DEFAULT_TOKEN_BUCKETS = [10, 50, 100, 500, 1000, 5000, 10000]


class _Counter:
    __slots__ = ("name", "help", "labels_values", "_lock")

    def __init__(self, name: str, help_text: str):
        self.name = name
        self.help = help_text
        self.labels_values: dict[tuple, float] = defaultdict(float)
        self._lock = Lock()

    def inc(self, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self.labels_values[key] += value

    def get(self, labels: dict[str, str] | None = None) -> float:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            return self.labels_values[key]

    def get_all(self) -> dict[tuple, float]:
        with self._lock:
            return dict(self.labels_values)


class _Histogram:
    __slots__ = ("name", "help", "buckets", "_data", "_lock")

    def __init__(self, name: str, help_text: str, buckets: list[float] | None = None):
        self.name = name
        self.help = help_text
        self.buckets = sorted(buckets or DEFAULT_LATENCY_BUCKETS)
        self._data: dict[tuple, dict] = {}
        self._lock = Lock()

    def _ensure_key(self, key: tuple) -> dict:
        if key not in self._data:
            self._data[key] = {
                "bucket_counts": [0] * len(self.buckets),
                "inf_count": 0,
                "sum": 0.0,
                "count": 0,
                "min": float("inf"),
                "max": float("-inf"),
                "recent": [],  # last 100 values for percentile calculation
            }
        return self._data[key]

    def observe(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            d = self._ensure_key(key)
            d["sum"] += value
            d["count"] += 1
            d["min"] = min(d["min"], value)
            d["max"] = max(d["max"], value)

            # Update bucket counts
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    d["bucket_counts"][i] += 1
            d["inf_count"] += 1

            # Keep recent values for percentile calculation
            d["recent"].append(value)
            if len(d["recent"]) > 500:
                d["recent"] = d["recent"][-500:]

    def get_stats(self, labels: dict[str, str] | None = None) -> dict:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            d = self._data.get(key)
            if not d or d["count"] == 0:
                return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0,
                        "p50": 0, "p90": 0, "p95": 0, "p99": 0}

            recent = sorted(d["recent"])
            n = len(recent)
            return {
                "count": d["count"],
                "sum": round(d["sum"], 2),
                "avg": round(d["sum"] / d["count"], 2),
                "min": round(d["min"], 2) if d["min"] != float("inf") else 0,
                "max": round(d["max"], 2) if d["max"] != float("-inf") else 0,
                "p50": recent[int(n * 0.5)] if n else 0,
                "p90": recent[int(n * 0.9)] if n else 0,
                "p95": recent[int(n * 0.95)] if n else 0,
                "p99": recent[min(int(n * 0.99), n - 1)] if n else 0,
            }

    def get_all_stats(self) -> dict[str, dict]:
        with self._lock:
            result = {}
            for key, d in self._data.items():
                label_str = ",".join(f"{k}={v}" for k, v in key) if key else "global"
                if d["count"] == 0:
                    continue
                recent = sorted(d["recent"])
                n = len(recent)
                result[label_str] = {
                    "count": d["count"],
                    "sum": round(d["sum"], 2),
                    "avg": round(d["sum"] / d["count"], 2),
                    "min": round(d["min"], 2) if d["min"] != float("inf") else 0,
                    "max": round(d["max"], 2) if d["max"] != float("-inf") else 0,
                    "p50": recent[int(n * 0.5)] if n else 0,
                    "p90": recent[int(n * 0.9)] if n else 0,
                    "p95": recent[int(n * 0.95)] if n else 0,
                    "p99": recent[min(int(n * 0.99), n - 1)] if n else 0,
                }
            return result


class _Gauge:
    __slots__ = ("name", "help", "labels_values", "_lock")

    def __init__(self, name: str, help_text: str):
        self.name = name
        self.help = help_text
        self.labels_values: dict[tuple, float] = {}
        self._lock = Lock()

    def set(self, value: float, labels: dict[str, str] | None = None) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self.labels_values[key] = value

    def inc(self, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self.labels_values[key] = self.labels_values.get(key, 0) + value

    def dec(self, value: float = 1.0, labels: dict[str, str] | None = None) -> None:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            self.labels_values[key] = self.labels_values.get(key, 0) - value

    def get(self, labels: dict[str, str] | None = None) -> float:
        key = tuple(sorted((labels or {}).items()))
        with self._lock:
            return self.labels_values.get(key, 0)

    def get_all(self) -> dict[tuple, float]:
        with self._lock:
            return dict(self.labels_values)


class _TimeSeries:
    """Ring buffer for time-series data points."""
    __slots__ = ("_buffer", "_max_size", "_lock")

    def __init__(self, max_size: int = _TS_BUFFER_SIZE):
        self._buffer: list[tuple[float, float]] = []
        self._max_size = max_size
        self._lock = Lock()

    def add(self, value: float, timestamp: float | None = None) -> None:
        ts = timestamp or time.time()
        with self._lock:
            self._buffer.append((ts, value))
            if len(self._buffer) > self._max_size:
                self._buffer = self._buffer[-self._max_size:]

    def get_range(self, since: float | None = None, until: float | None = None) -> list[tuple[float, float]]:
        with self._lock:
            data = self._buffer[:]
        if since:
            data = [(t, v) for t, v in data if t >= since]
        if until:
            data = [(t, v) for t, v in data if t <= until]
        return data


class MetricsCollector:
    """Central metrics registry."""

    def __init__(self) -> None:
        self._counters: dict[str, _Counter] = {}
        self._histograms: dict[str, _Histogram] = {}
        self._gauges: dict[str, _Gauge] = {}
        self._timeseries: dict[str, _TimeSeries] = {}
        self._lock = Lock()
        self._start_time = time.time()
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register standard ChatVote metrics."""
        # Request counters
        self.counter("chat_requests_total", "Total chat requests received")
        self.counter("chat_requests_errors_total", "Total chat request errors")
        self.counter("socket_connections_total", "Total Socket.IO connections")
        self.counter("socket_disconnections_total", "Total Socket.IO disconnections")
        self.counter("http_requests_total", "Total HTTP API requests")

        # LLM counters
        self.counter("llm_requests_total", "Total LLM API calls")
        self.counter("llm_errors_total", "Total LLM API errors")
        self.counter("llm_failovers_total", "Total LLM failover events")
        self.counter("llm_tokens_total", "Total tokens consumed")

        # RAG counters
        self.counter("rag_searches_total", "Total RAG searches performed")
        self.counter("rag_cache_hits_total", "Total RAG cache hits")
        self.counter("rag_cache_misses_total", "Total RAG cache misses")

        # Latency histograms
        self.histogram("chat_response_time_ms", "Chat response time in ms")
        self.histogram("llm_response_time_ms", "LLM API call time in ms")
        self.histogram("rag_search_time_ms", "RAG search time in ms")
        self.histogram("rag_rerank_time_ms", "RAG reranking time in ms")
        self.histogram("cache_fetch_time_ms", "Cache fetch time in ms")
        self.histogram("socket_event_time_ms", "Socket.IO event handling time in ms")
        self.histogram("ttfb_ms", "Time to first byte (first chunk) in ms")

        # Token histograms
        self.histogram("llm_tokens_per_request", "Tokens per LLM request",
                        buckets=DEFAULT_TOKEN_BUCKETS)

        # Gauges
        self.gauge("active_connections", "Current active Socket.IO connections")
        self.gauge("active_streams", "Currently streaming responses")
        self.gauge("llm_rpm", "Current LLM requests per minute")
        self.gauge("cache_size", "Current cache entry count")

    def counter(self, name: str, help_text: str = "") -> _Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = _Counter(name, help_text)
            return self._counters[name]

    def histogram(self, name: str, help_text: str = "",
                   buckets: list[float] | None = None) -> _Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = _Histogram(name, help_text, buckets)
            return self._histograms[name]

    def gauge(self, name: str, help_text: str = "") -> _Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = _Gauge(name, help_text)
            return self._gauges[name]

    def timeseries(self, name: str) -> _TimeSeries:
        with self._lock:
            if name not in self._timeseries:
                self._timeseries[name] = _TimeSeries()
            return self._timeseries[name]

    # -- Convenience methods --

    def record_histogram(self, name: str, value: float,
                          labels: dict[str, str] | None = None) -> None:
        self.histogram(name).observe(value, labels)
        self.timeseries(name).add(value)

    def inc_counter(self, name: str, value: float = 1.0,
                     labels: dict[str, str] | None = None) -> None:
        self.counter(name).inc(value, labels)

    def set_gauge(self, name: str, value: float,
                   labels: dict[str, str] | None = None) -> None:
        self.gauge(name).set(value, labels)

    # -- Export methods --

    def get_snapshot(self) -> dict[str, Any]:
        """Get a full snapshot of all metrics for the admin dashboard."""
        now = time.time()
        snapshot: dict[str, Any] = {
            "timestamp": now,
            "uptime_seconds": round(now - self._start_time, 1),
        }

        # Counters
        counters = {}
        for name, c in self._counters.items():
            all_vals = c.get_all()
            if len(all_vals) == 1 and () in all_vals:
                counters[name] = all_vals[()]
            else:
                counters[name] = {
                    ",".join(f"{k}={v}" for k, v in key) if key else "total": val
                    for key, val in all_vals.items()
                }
        snapshot["counters"] = counters

        # Histograms
        histograms = {}
        for name, h in self._histograms.items():
            histograms[name] = h.get_all_stats()
        snapshot["histograms"] = histograms

        # Gauges
        gauges = {}
        for name, g in self._gauges.items():
            all_vals = g.get_all()
            if len(all_vals) <= 1:
                gauges[name] = all_vals.get((), 0)
            else:
                gauges[name] = {
                    ",".join(f"{k}={v}" for k, v in key) if key else "value": val
                    for key, val in all_vals.items()
                }
        snapshot["gauges"] = gauges

        return snapshot

    def get_timeseries(self, name: str, since: float | None = None) -> list[dict]:
        """Get time-series data points for a metric."""
        ts = self._timeseries.get(name)
        if not ts:
            return []
        return [{"t": t, "v": round(v, 2)} for t, v in ts.get_range(since=since)]

    def prometheus_export(self) -> str:
        """Export all metrics in Prometheus text exposition format."""
        lines: list[str] = []

        # Counters
        for name, c in self._counters.items():
            lines.append(f"# HELP {name} {c.help}")
            lines.append(f"# TYPE {name} counter")
            for key, val in c.get_all().items():
                label_str = _prom_labels(key)
                lines.append(f"{name}{label_str} {val}")

        # Histograms
        for name, h in self._histograms.items():
            lines.append(f"# HELP {name} {h.help}")
            lines.append(f"# TYPE {name} histogram")
            for key, d in h._data.items():
                label_str = _prom_labels(key)
                cumulative = 0
                for i, bound in enumerate(h.buckets):
                    cumulative += d["bucket_counts"][i]
                    le_label = _prom_labels(key, le=str(bound))
                    lines.append(f"{name}_bucket{le_label} {cumulative}")
                le_label = _prom_labels(key, le="+Inf")
                lines.append(f"{name}_bucket{le_label} {d['inf_count']}")
                lines.append(f"{name}_sum{label_str} {d['sum']}")
                lines.append(f"{name}_count{label_str} {d['count']}")

        # Gauges
        for name, g in self._gauges.items():
            lines.append(f"# HELP {name} {g.help}")
            lines.append(f"# TYPE {name} gauge")
            for key, val in g.get_all().items():
                label_str = _prom_labels(key)
                lines.append(f"{name}{label_str} {val}")

        # Uptime gauge
        lines.append("# HELP chatvote_uptime_seconds Process uptime")
        lines.append("# TYPE chatvote_uptime_seconds gauge")
        lines.append(f"chatvote_uptime_seconds {round(time.time() - self._start_time, 1)}")

        return "\n".join(lines) + "\n"


def _prom_labels(key: tuple, **extra: str) -> str:
    """Format labels for Prometheus text format."""
    parts = list(key) + list(extra.items())
    if not parts:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in parts)
    return "{" + inner + "}"


# Singleton instance
metrics = MetricsCollector()
