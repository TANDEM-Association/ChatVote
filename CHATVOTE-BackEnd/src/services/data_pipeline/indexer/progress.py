"""Shared progress tracking for parallel indexer phases."""
from __future__ import annotations

from typing import Any

from src.services.data_pipeline.base import NodeStatus, update_status


class PhaseTracker:
    """Thread-safe-ish progress tracker for parallel indexer phases.

    Each phase writes its own key in phase_progress/phase_status.
    The merged status is emitted to Firestore for the admin dashboard.
    """

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id
        self.phase_progress: dict[str, dict[str, Any]] = {}
        self.phase_status: dict[str, str] = {}

    async def emit(self) -> None:
        """Emit a merged status update from all phase progress dicts."""
        active = [k for k, v in self.phase_status.items() if v == "running"]
        done = [k for k, v in self.phase_status.items() if v == "done"]
        merged: dict[str, Any] = {
            "phase": "parallel",
            "active_phases": ", ".join(active) if active else "finishing...",
            "completed_phases": ", ".join(done) if done else "",
        }
        for name, progress in self.phase_progress.items():
            for k, v in progress.items():
                merged[f"{name}_{k}"] = v
        await update_status(self.node_id, NodeStatus.RUNNING, counts=merged)

    async def start_phase(self, name: str) -> None:
        self.phase_status[name] = "running"
        await self.emit()

    async def finish_phase(self, name: str) -> None:
        self.phase_status[name] = "done"
        await self.emit()

    async def error_phase(self, name: str) -> None:
        self.phase_status[name] = "error"
        await self.emit()

    def update_progress(self, name: str, data: dict[str, Any]) -> None:
        self.phase_progress[name] = data
