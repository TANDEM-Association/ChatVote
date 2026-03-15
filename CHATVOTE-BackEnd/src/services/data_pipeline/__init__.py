# Data Sources Pipeline — node registry and public API
from __future__ import annotations

from src.services.data_pipeline.base import (
    DataSourceNode,
    NodeStatus,
    PIPELINE_NODES,
    register_node,
    put_context,
    get_context,
    clear_context,
)

__all__ = [
    "DataSourceNode",
    "NodeStatus",
    "PIPELINE_NODES",
    "register_node",
    "put_context",
    "get_context",
    "clear_context",
]


def _register_builtin_nodes() -> None:
    """Import node modules so they self-register."""
    from src.services.data_pipeline import population  # noqa: F401
    from src.services.data_pipeline import candidatures  # noqa: F401
    from src.services.data_pipeline import websites  # noqa: F401
    from src.services.data_pipeline import pourquituvotes  # noqa: F401
    from src.services.data_pipeline import populate  # noqa: F401
    from src.services.data_pipeline import professions  # noqa: F401
    from src.services.data_pipeline import scraper  # noqa: F401
    from src.services.data_pipeline import crawl_scraper  # noqa: F401
    from src.services.data_pipeline import indexer  # noqa: F401 (now a package)


_register_builtin_nodes()
