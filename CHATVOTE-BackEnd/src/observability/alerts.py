# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
"""
Alert manager for threshold-based monitoring alerts.

Defines alert rules that are evaluated against current metrics.
Alerts are stored in-memory and queryable via the admin API.
Supports:
    - Threshold-based alerts (metric > value)
    - Rate-based alerts (error rate > percentage)
    - Cooldown periods (avoid alert storms)
    - Severity levels (critical, warning, info)
"""

import time
from collections import deque
from enum import Enum
from threading import Lock
from typing import Any, Callable


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertState(str, Enum):
    FIRING = "firing"
    RESOLVED = "resolved"


class AlertRule:
    """A configured alert rule."""

    __slots__ = (
        "name", "description", "severity", "check_fn", "cooldown_seconds",
        "_last_fired", "_state", "labels",
    )

    def __init__(
        self,
        name: str,
        description: str,
        severity: AlertSeverity,
        check_fn: Callable[[], bool],
        cooldown_seconds: int = 300,
        labels: dict[str, str] | None = None,
    ):
        self.name = name
        self.description = description
        self.severity = severity
        self.check_fn = check_fn
        self.cooldown_seconds = cooldown_seconds
        self._last_fired: float = 0
        self._state = AlertState.RESOLVED
        self.labels = labels or {}

    def evaluate(self) -> bool:
        """Check if the alert should fire."""
        try:
            is_firing = self.check_fn()
        except Exception:
            return False

        now = time.time()
        if is_firing:
            self._state = AlertState.FIRING
            if now - self._last_fired >= self.cooldown_seconds:
                self._last_fired = now
                return True
        else:
            self._state = AlertState.RESOLVED
        return False

    @property
    def state(self) -> AlertState:
        return self._state

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "state": self._state.value,
            "last_fired": self._last_fired if self._last_fired > 0 else None,
            "cooldown_seconds": self.cooldown_seconds,
            "labels": self.labels,
        }


class Alert:
    """A fired alert instance."""

    __slots__ = ("rule_name", "severity", "message", "timestamp", "labels", "value")

    def __init__(
        self,
        rule_name: str,
        severity: AlertSeverity,
        message: str,
        labels: dict[str, str] | None = None,
        value: Any = None,
    ):
        self.rule_name = rule_name
        self.severity = severity
        self.message = message
        self.timestamp = time.time()
        self.labels = labels or {}
        self.value = value

    def to_dict(self) -> dict:
        return {
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp,
            "labels": self.labels,
            "value": self.value,
        }


class AlertManager:
    """Central alert management."""

    def __init__(self) -> None:
        self._rules: dict[str, AlertRule] = {}
        self._fired_alerts: deque[Alert] = deque(maxlen=500)
        self._lock = Lock()

    def register_rule(self, rule: AlertRule) -> None:
        with self._lock:
            self._rules[rule.name] = rule

    def fire_alert(
        self,
        rule_name: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.WARNING,
        labels: dict[str, str] | None = None,
        value: Any = None,
    ) -> None:
        """Manually fire an alert."""
        alert = Alert(rule_name, severity, message, labels, value)
        with self._lock:
            self._fired_alerts.append(alert)

    def evaluate_all(self) -> list[Alert]:
        """Evaluate all registered rules and return newly fired alerts."""
        fired = []
        for rule in list(self._rules.values()):
            if rule.evaluate():
                alert = Alert(
                    rule.name, rule.severity, rule.description, rule.labels,
                )
                with self._lock:
                    self._fired_alerts.append(alert)
                fired.append(alert)
        return fired

    def get_rules(self) -> list[dict]:
        """Get all registered alert rules with current state."""
        return [r.to_dict() for r in self._rules.values()]

    def get_fired_alerts(
        self,
        limit: int = 100,
        severity: str | None = None,
        since: float | None = None,
    ) -> list[dict]:
        """Get fired alert history."""
        with self._lock:
            alerts = list(self._fired_alerts)

        if since:
            alerts = [a for a in alerts if a.timestamp >= since]
        if severity:
            alerts = [a for a in alerts if a.severity.value == severity]

        return [a.to_dict() for a in reversed(alerts)][:limit]

    def get_summary(self) -> dict:
        """Get current alert status summary."""
        rules = list(self._rules.values())
        firing = [r for r in rules if r.state == AlertState.FIRING]
        with self._lock:
            recent = [
                a for a in self._fired_alerts
                if time.time() - a.timestamp < 3600
            ]
        return {
            "total_rules": len(rules),
            "firing_count": len(firing),
            "firing_rules": [r.to_dict() for r in firing],
            "recent_alerts_1h": len(recent),
            "recent_alerts": [a.to_dict() for a in reversed(recent)][:20],
        }


def register_default_alerts(alert_mgr: AlertManager, metrics_collector: Any) -> None:
    """Register default ChatVote alert rules.

    Called once at startup after the metrics collector is initialized.
    """
    from src.observability.metrics import metrics

    # High error rate
    alert_mgr.register_rule(AlertRule(
        name="high_error_rate",
        description="Chat error rate exceeds 10%",
        severity=AlertSeverity.CRITICAL,
        check_fn=lambda: _check_error_rate(metrics, threshold=0.10),
        cooldown_seconds=300,
        labels={"component": "chat"},
    ))

    # High response time
    alert_mgr.register_rule(AlertRule(
        name="high_response_time",
        description="P95 response time exceeds 30 seconds",
        severity=AlertSeverity.WARNING,
        check_fn=lambda: _check_p95_latency(metrics, "chat_response_time_ms", 30000),
        cooldown_seconds=600,
        labels={"component": "chat"},
    ))

    # LLM all providers failing
    alert_mgr.register_rule(AlertRule(
        name="all_llm_providers_failing",
        description="All LLM providers are rate-limited or erroring",
        severity=AlertSeverity.CRITICAL,
        check_fn=lambda: _check_all_llms_failing(metrics),
        cooldown_seconds=120,
        labels={"component": "llm"},
    ))

    # High LLM RPM
    alert_mgr.register_rule(AlertRule(
        name="high_llm_rpm",
        description="LLM requests per minute exceeds 80",
        severity=AlertSeverity.WARNING,
        check_fn=lambda: metrics.gauge("llm_rpm").get() > 80,
        cooldown_seconds=300,
        labels={"component": "llm"},
    ))

    # No connections (potential outage)
    alert_mgr.register_rule(AlertRule(
        name="zero_connections",
        description="No active Socket.IO connections (potential outage)",
        severity=AlertSeverity.INFO,
        check_fn=lambda: metrics.gauge("active_connections").get() == 0,
        cooldown_seconds=900,
        labels={"component": "socket"},
    ))

    # High cache miss rate
    alert_mgr.register_rule(AlertRule(
        name="high_cache_miss_rate",
        description="Cache miss rate exceeds 80%",
        severity=AlertSeverity.WARNING,
        check_fn=lambda: _check_cache_miss_rate(metrics, threshold=0.80),
        cooldown_seconds=600,
        labels={"component": "cache"},
    ))


def _check_error_rate(m: Any, threshold: float) -> bool:
    total = m.counter("chat_requests_total").get()
    errors = m.counter("chat_requests_errors_total").get()
    if total < 10:
        return False
    return (errors / total) > threshold


def _check_p95_latency(m: Any, metric_name: str, threshold_ms: float) -> bool:
    stats = m.histogram(metric_name).get_stats()
    if stats["count"] < 5:
        return False
    return stats["p95"] > threshold_ms


def _check_all_llms_failing(m: Any) -> bool:
    errors = m.counter("llm_errors_total").get()
    total = m.counter("llm_requests_total").get()
    if total < 5:
        return False
    return (errors / total) > 0.9


def _check_cache_miss_rate(m: Any, threshold: float) -> bool:
    hits = m.counter("rag_cache_hits_total").get()
    misses = m.counter("rag_cache_misses_total").get()
    total = hits + misses
    if total < 10:
        return False
    return (misses / total) > threshold


# Singleton instance
alert_manager = AlertManager()
