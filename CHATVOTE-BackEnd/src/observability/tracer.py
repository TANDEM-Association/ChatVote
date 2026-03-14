# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Request tracer for tracking operations across the ChatVote pipeline.

Provides span-based tracing similar to OpenTelemetry but lightweight,
storing traces in-memory for dashboard visualization. Each trace
represents a full request lifecycle (e.g., a chat_answer_request)
and contains multiple spans (e.g., rag_search, llm_call, rerank).

Compatible with distributed tracing concepts:
    - trace_id: Unique identifier for the full request
    - span_id: Unique identifier for each operation within the request
    - parent_span_id: Links child spans to parent spans

Traces are stored in a ring buffer and queryable via the admin API.
"""

import time
import uuid
from collections import deque
from contextlib import contextmanager
from threading import Lock
from typing import Any, Generator

_TRACE_BUFFER_SIZE = 1000  # Keep last 1000 traces


class Span:
    """A single operation within a trace."""

    __slots__ = (
        "span_id", "trace_id", "parent_span_id", "name",
        "start_time", "end_time", "attributes", "status", "events",
    )

    def __init__(
        self,
        name: str,
        trace_id: str,
        parent_span_id: str | None = None,
    ):
        self.span_id = uuid.uuid4().hex[:12]
        self.trace_id = trace_id
        self.parent_span_id = parent_span_id
        self.name = name
        self.start_time = time.time()
        self.end_time: float | None = None
        self.attributes: dict[str, Any] = {}
        self.status = "ok"
        self.events: list[dict] = []

    def set_attribute(self, key: str, value: Any) -> "Span":
        self.attributes[key] = value
        return self

    def add_event(self, name: str, attributes: dict | None = None) -> "Span":
        self.events.append({
            "name": name,
            "timestamp": time.time(),
            "attributes": attributes or {},
        })
        return self

    def set_error(self, error: Exception | str) -> "Span":
        self.status = "error"
        self.attributes["error"] = str(error)
        if isinstance(error, Exception):
            self.attributes["error_type"] = type(error).__name__
        return self

    def end(self) -> "Span":
        self.end_time = time.time()
        return self

    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.time()
        return round((end - self.start_time) * 1000, 2)

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id,
            "name": self.name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "status": self.status,
            "events": self.events,
        }


class Trace:
    """A collection of spans representing a full request lifecycle."""

    __slots__ = ("trace_id", "root_name", "spans", "start_time", "end_time",
                 "attributes", "status")

    def __init__(self, trace_id: str, root_name: str):
        self.trace_id = trace_id
        self.root_name = root_name
        self.spans: list[Span] = []
        self.start_time = time.time()
        self.end_time: float | None = None
        self.attributes: dict[str, Any] = {}
        self.status = "ok"

    def add_span(self, span: Span) -> None:
        self.spans.append(span)
        if span.status == "error":
            self.status = "error"

    def end(self) -> None:
        self.end_time = time.time()

    @property
    def duration_ms(self) -> float:
        end = self.end_time or time.time()
        return round((end - self.start_time) * 1000, 2)

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "root_name": self.root_name,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "status": self.status,
            "span_count": len(self.spans),
            "spans": [s.to_dict() for s in self.spans],
        }

    def to_summary(self) -> dict:
        """Compact representation without individual span details."""
        return {
            "trace_id": self.trace_id,
            "root_name": self.root_name,
            "start_time": self.start_time,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "span_count": len(self.spans),
            "attributes": self.attributes,
        }


class RequestTracer:
    """Central trace registry with in-memory storage."""

    def __init__(self) -> None:
        self._traces: deque[Trace] = deque(maxlen=_TRACE_BUFFER_SIZE)
        self._active_traces: dict[str, Trace] = {}
        self._lock = Lock()

    def start_trace(self, name: str, trace_id: str | None = None,
                     attributes: dict | None = None) -> Trace:
        """Start a new trace."""
        tid = trace_id or uuid.uuid4().hex[:16]
        trace = Trace(tid, name)
        if attributes:
            trace.attributes.update(attributes)
        with self._lock:
            self._active_traces[tid] = trace
        return trace

    def end_trace(self, trace_id: str) -> Trace | None:
        """End a trace and move it to the completed buffer."""
        with self._lock:
            trace = self._active_traces.pop(trace_id, None)
            if trace:
                trace.end()
                self._traces.append(trace)
            return trace

    @contextmanager
    def span(self, name: str, trace_id: str,
             parent_span_id: str | None = None) -> Generator[Span, None, None]:
        """Context manager for creating and auto-ending a span."""
        s = Span(name, trace_id, parent_span_id)
        try:
            yield s
        except Exception as e:
            s.set_error(e)
            raise
        finally:
            s.end()
            with self._lock:
                trace = self._active_traces.get(trace_id)
                if trace:
                    trace.add_span(s)

    def add_span_to_trace(self, trace_id: str, span: Span) -> None:
        """Manually add a completed span to a trace."""
        with self._lock:
            trace = self._active_traces.get(trace_id)
            if trace:
                trace.add_span(span)

    def get_traces(
        self,
        limit: int = 50,
        status: str | None = None,
        name: str | None = None,
        since: float | None = None,
    ) -> list[dict]:
        """Query completed traces."""
        with self._lock:
            traces = list(self._traces)

        if since:
            traces = [t for t in traces if t.start_time >= since]
        if status:
            traces = [t for t in traces if t.status == status]
        if name:
            traces = [t for t in traces if name in t.root_name]

        # Most recent first
        traces = list(reversed(traces))[:limit]
        return [t.to_summary() for t in traces]

    def get_trace(self, trace_id: str) -> dict | None:
        """Get a single trace with full span details."""
        with self._lock:
            # Check active first
            if trace_id in self._active_traces:
                return self._active_traces[trace_id].to_dict()
            # Then check completed
            for t in reversed(self._traces):
                if t.trace_id == trace_id:
                    return t.to_dict()
        return None

    def get_active_traces(self) -> list[dict]:
        """Get all currently active (in-progress) traces."""
        with self._lock:
            return [t.to_summary() for t in self._active_traces.values()]

    def get_stats(self) -> dict:
        """Get aggregate trace statistics."""
        with self._lock:
            traces = list(self._traces)
            active = len(self._active_traces)

        if not traces:
            return {
                "total_traces": 0,
                "active_traces": active,
                "error_rate": 0,
                "avg_duration_ms": 0,
                "p95_duration_ms": 0,
            }

        durations = [t.duration_ms for t in traces]
        errors = sum(1 for t in traces if t.status == "error")
        durations_sorted = sorted(durations)
        n = len(durations_sorted)

        return {
            "total_traces": len(traces),
            "active_traces": active,
            "error_count": errors,
            "error_rate": round(errors / len(traces) * 100, 1) if traces else 0,
            "avg_duration_ms": round(sum(durations) / n, 1),
            "p50_duration_ms": durations_sorted[int(n * 0.5)],
            "p95_duration_ms": durations_sorted[int(n * 0.95)],
            "p99_duration_ms": durations_sorted[min(int(n * 0.99), n - 1)],
        }


# Singleton instance
tracer = RequestTracer()
