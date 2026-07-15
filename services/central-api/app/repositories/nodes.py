from __future__ import annotations

import json
from collections.abc import Callable

from ..core.database import get_db
from ..models import Machine, MetricIn, Node, utc_now
from ..persistence_repository import central_fact_repository


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

    def persist_metric(self, metric: MetricIn) -> None:
        with get_db() as db:
            db.execute(
                """INSERT INTO metrics (node_code, cpu_usage, memory_usage, disk_usage,
                   network_in, network_out, db_latency_ms, api_latency_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    metric.node_code,
                    metric.cpu_usage,
                    metric.memory_usage,
                    metric.disk_usage,
                    metric.network_in,
                    metric.network_out,
                    metric.db_latency_ms,
                    metric.api_latency_ms,
                    utc_now().isoformat(),
                ),
            )

    def persist_heartbeat(self, payload: dict[str, object], *, retention_per_node: int) -> int:
        return central_fact_repository.persist_heartbeat(
            {**payload, "_received_at": utc_now().isoformat()},
            retention_per_node=retention_per_node,
        )

    @staticmethod
    def _prune_heartbeats_in_transaction(db: object, limit: int) -> int:
        cursor = db.execute(
            """
            DELETE FROM heartbeat_shadow
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (PARTITION BY node_code ORDER BY id DESC) AS rn
                    FROM heartbeat_shadow
                ) ranked
                WHERE rn > ?
            )
            """,
            (limit,),
        )
        rowcount = getattr(cursor, "rowcount", -1)
        return int(rowcount) if isinstance(rowcount, int) and rowcount >= 0 else 0

    def prune_heartbeats(self, limit: int) -> dict[str, int]:
        with get_db() as db:
            deleted = self._prune_heartbeats_in_transaction(db, limit)
            row = db.execute("SELECT COUNT(*) AS count FROM heartbeat_shadow").fetchone()
            remaining = int(row["count"])
        return {"deleted": deleted, "remaining": remaining}

    def load_latest_heartbeats(
        self,
        limit: int,
        *,
        include_node: Callable[[str], bool],
    ) -> dict[str, tuple[dict[str, object], object]]:
        with get_db() as db:
            rows = db.execute(
                """
                SELECT node_code, payload_json, received_at
                FROM heartbeat_shadow
                ORDER BY received_at DESC, id DESC LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()

        latest: dict[str, tuple[dict[str, object], object]] = {}
        for row in rows:
            data = dict(row)
            node_code = str(data.get("node_code") or "")
            if not node_code or node_code in latest or not include_node(node_code):
                continue
            try:
                payload = json.loads(str(data.get("payload_json") or "{}"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                latest[node_code] = (payload, data.get("received_at"))
        return latest

    def persist_synced_records(
        self,
        node_code: str,
        records: list[dict[str, object]],
        *,
        retention_per_node: int,
    ) -> dict[str, int]:
        return central_fact_repository.persist_synced_node_records(
            node_code,
            records,
            retention_per_node=retention_per_node,
        )
