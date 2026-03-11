"""Base framework for data pipeline nodes.

Each node:
- Has a unique ``node_id`` and human-readable ``label``
- Stores its config/status/checkpoints in Firestore ``data_pipeline_config/{node_id}``
- Implements ``run(force)`` for the actual work
- Tracks incremental checkpoints so the same data isn't processed twice
"""
from __future__ import annotations

import enum
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from google.cloud.firestore_v1 import AsyncDocumentReference

logger = logging.getLogger(__name__)

CONFIG_COLLECTION = "data_pipeline_config"


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------
class NodeStatus(str, enum.Enum):
    IDLE = "idle"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Node config (mirrors Firestore document)
# ---------------------------------------------------------------------------
@dataclass
class NodeConfig:
    node_id: str
    label: str
    enabled: bool = True
    status: NodeStatus = NodeStatus.IDLE
    last_run_at: str | None = None
    last_duration_s: float | None = None
    last_error: str | None = None
    counts: dict[str, Any] = field(default_factory=dict)
    settings: dict[str, Any] = field(default_factory=dict)
    checkpoints: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "enabled": self.enabled,
            "status": self.status.value if isinstance(self.status, NodeStatus) else self.status,
            "last_run_at": self.last_run_at,
            "last_duration_s": self.last_duration_s,
            "last_error": self.last_error,
            "counts": self.counts,
            "settings": self.settings,
            "checkpoints": self.checkpoints,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NodeConfig:
        status_raw = data.get("status", "idle")
        try:
            status = NodeStatus(status_raw)
        except ValueError:
            status = NodeStatus.IDLE
        return cls(
            node_id=data["node_id"],
            label=data.get("label", data["node_id"]),
            enabled=data.get("enabled", True),
            status=status,
            last_run_at=data.get("last_run_at"),
            last_duration_s=data.get("last_duration_s"),
            last_error=data.get("last_error"),
            counts=data.get("counts", {}),
            settings=data.get("settings", {}),
            checkpoints=data.get("checkpoints", {}),
        )


# ---------------------------------------------------------------------------
# Firestore helpers (async)
# ---------------------------------------------------------------------------
def _config_ref(node_id: str) -> AsyncDocumentReference:
    from src.firebase_service import async_db
    return async_db.collection(CONFIG_COLLECTION).document(node_id)


async def load_config(node_id: str, defaults: NodeConfig) -> NodeConfig:
    """Load node config from Firestore, creating it with *defaults* if missing."""
    ref = _config_ref(node_id)
    snap = await ref.get()
    if snap.exists:
        return NodeConfig.from_dict(snap.to_dict())
    # First run — seed Firestore with defaults
    await ref.set(defaults.to_dict())
    return defaults


async def save_config(cfg: NodeConfig) -> None:
    await _config_ref(cfg.node_id).set(cfg.to_dict())


async def update_status(node_id: str, status: NodeStatus, **extra: Any) -> None:
    data: dict[str, Any] = {"status": status.value}
    data.update(extra)
    await _config_ref(node_id).update(data)


async def save_checkpoint(node_id: str, checkpoints: dict[str, Any]) -> None:
    await _config_ref(node_id).update({"checkpoints": checkpoints})


# ---------------------------------------------------------------------------
# Incremental helpers
# ---------------------------------------------------------------------------
def content_hash(data: bytes, *, sample_size: int = 10240) -> str:
    """SHA-256 of first *sample_size* bytes + total length (fast fingerprint)."""
    h = hashlib.sha256()
    h.update(data[:sample_size])
    h.update(str(len(data)).encode())
    return f"sha256:{h.hexdigest()}"


def should_skip(current_hash: str, stored_hash: str | None) -> bool:
    return current_hash == stored_hash


# ---------------------------------------------------------------------------
# Abstract base node
# ---------------------------------------------------------------------------
class DataSourceNode(ABC):
    node_id: str
    label: str
    default_settings: dict[str, Any] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    def default_config(self) -> NodeConfig:
        return NodeConfig(
            node_id=self.node_id,
            label=self.label,
            settings={**self.default_settings},
        )

    async def execute(self, *, force: bool = False) -> NodeConfig:
        """Run the node with status tracking and error handling."""
        cfg = await load_config(self.node_id, self.default_config())

        if not cfg.enabled and not force:
            logger.info(f"[{self.node_id}] disabled, skipping")
            return cfg

        logger.info(f"[{self.node_id}] starting (force={force})")
        await update_status(self.node_id, NodeStatus.RUNNING)
        t0 = time.monotonic()

        try:
            cfg = await self.run(cfg, force=force)
            elapsed = round(time.monotonic() - t0, 2)
            cfg.status = NodeStatus.SUCCESS
            cfg.last_run_at = datetime.now(timezone.utc).isoformat()
            cfg.last_duration_s = elapsed
            cfg.last_error = None
            await save_config(cfg)
            logger.info(f"[{self.node_id}] done in {elapsed}s — counts={cfg.counts}")
        except Exception as exc:
            elapsed = round(time.monotonic() - t0, 2)
            cfg.status = NodeStatus.ERROR
            cfg.last_run_at = datetime.now(timezone.utc).isoformat()
            cfg.last_duration_s = elapsed
            cfg.last_error = str(exc)
            await save_config(cfg)
            logger.exception(f"[{self.node_id}] failed after {elapsed}s")
            raise

        return cfg

    @abstractmethod
    async def run(self, cfg: NodeConfig, *, force: bool = False) -> NodeConfig:
        """Override with actual work.  Must return the updated *cfg*."""
        ...


# ---------------------------------------------------------------------------
# Pipeline context — shared data bus between nodes
# ---------------------------------------------------------------------------
_pipeline_context: dict[str, Any] = {}


def put_context(key: str, value: Any) -> None:
    """Store a value in the pipeline context (keyed by node_id or any string)."""
    _pipeline_context[key] = value


def get_context(key: str) -> Any | None:
    """Retrieve a value from the pipeline context, or None."""
    return _pipeline_context.get(key)


def clear_context() -> None:
    """Reset the pipeline context (e.g. between full runs)."""
    _pipeline_context.clear()


# ---------------------------------------------------------------------------
# Node registry
# ---------------------------------------------------------------------------
PIPELINE_NODES: dict[str, DataSourceNode] = {}


def register_node(node: DataSourceNode) -> DataSourceNode:
    PIPELINE_NODES[node.node_id] = node
    return node
