from __future__ import annotations

from ..models import Machine, MetricIn, Node


class NodeRepository:
    """Own the rebuildable node, machine, heartbeat, and metric projections."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.metrics: list[MetricIn] = []
        self.runtime_metrics: dict[str, MetricIn] = {}
        self.machines: list[Machine] = []
        self.db_size_bytes: dict[str, int] = {}
        self.db_size_sources: dict[str, str] = {}
        self.heartbeats_v2: dict[str, dict[str, object]] = {}
        self.record_sync_ids: set[str] = set()
