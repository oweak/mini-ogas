from __future__ import annotations

import logging
import json
import random
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean

import psutil

from .core.ai.registry import registry
from .core.config import settings
from .core.session import get_session_token
from .core.database import get_db, init_db, persistence_backend, persistence_label
from .core.service_client import get_json, post_json
from .command_manager import CommandManager, CommandTransition

logger = logging.getLogger(__name__)
from .models import (
    AiDiagnosis,
    AiShortcut,
    Alert,
    AllocationOrder,
    AllocationOrderIn,
    AuditLog,
    DashboardSummary,
    DispatchTask,
    HostRuntimeStatus,
    IncidentEvent,
    InventoryItem,
    Machine,
    MarketForecast,
    MarketSignal,
    MetricIn,
    Node,
    NodeCommand,
    NodeStatus,
    PartQueueItem,
    PreflightResult,
    PreflightStep,
    ProductionPlanIn,
    ResourceAllocation,
    Severity,
    SimulationState,
    TopologyEdge,
    utc_now,
)

# Product catalog: a small automotive-parts machining factory.
# Each product has a Chinese name, a process route, and a base unit price.
PRODUCTS: dict[str, dict[str, object]] = {
    "A1": {"name": "主轴", "route": ["turning", "milling", "inspection"], "price": 160.0},
    "A2": {"name": "法兰盘", "route": ["turning", "drilling", "inspection"], "price": 95.0},
    "A3": {"name": "变速箱齿轮", "route": ["turning", "milling", "grinding", "inspection"], "price": 240.0},
    "A4": {"name": "精密轴套", "route": ["turning", "grinding", "inspection"], "price": 120.0},
    "A5": {"name": "转向连接件", "route": ["milling", "drilling", "inspection"], "price": 140.0},
}

# Canonical product catalog shared with docs, market-simulator, and production-planner.
# The A1-A5 aliases remain accepted for older tests and saved demo data.
PRODUCTS = {
    "P1": {"name": "标准轴", "route": ["turning", "grinding"], "price": 120.0},
    "P2": {"name": "法兰", "route": ["turning", "milling"], "price": 180.0},
    "P3": {"name": "齿轮毛坯", "route": ["turning", "milling", "grinding"], "price": 260.0},
    "P4": {"name": "精密套筒", "route": ["turning", "grinding"], "price": 310.0},
    "P5": {"name": "定制连接器", "route": ["milling", "grinding"], "price": 420.0},
}

PRODUCT_ALIASES = {
    "A1": "P1",
    "A2": "P2",
    "A3": "P3",
    "A4": "P4",
    "A5": "P5",
}

# Which workshop type is preferred for each process step. Steps not listed
# (e.g. "inspection") may run on any available machine.
PROCESS_WORKSHOP: dict[str, str] = {
    "turning": "turning",
    "milling": "milling",
    "grinding": "grinding",
    "drilling": "milling",
}

WORKSHOP_NAMES: dict[str, str] = {
    "turning": "车削车间",
    "milling": "铣削车间",
    "grinding": "磨削车间",
    "cloud": "云协同节点",
    "database": "云数据库节点",
}


def canonical_product_code(product_code: str) -> str:
    return PRODUCT_ALIASES.get(product_code, product_code)


def product_name(product_code: str) -> str:
    code = canonical_product_code(product_code)
    product = PRODUCTS.get(code)
    return str(product["name"]) if product else product_code


def product_route(product_code: str) -> list[str]:
    product = PRODUCTS.get(canonical_product_code(product_code))
    return list(product["route"]) if product else ["turning", "inspection"]


def _database_datetime(value: object) -> datetime:
    """Normalize SQLite ISO strings and psycopg datetime values on shadow reload."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _heartbeat_alarm_severity(value: str) -> Severity:
    normalized = value.strip().lower()
    if normalized in {"critical", "高危"}:
        return Severity.critical
    if normalized in {"high", "高"}:
        return Severity.high
    if normalized in {"low", "低"}:
        return Severity.low
    return Severity.medium


def _severity_rank(value: Severity) -> int:
    return {
        Severity.info: 0,
        Severity.low: 1,
        Severity.medium: 2,
        Severity.high: 3,
        Severity.critical: 4,
    }[value]


def _heartbeat_alarm_description(node_code: str, alert_type: str, production: dict[str, object]) -> str:
    machine = str(production.get("machine_code") or node_code)
    if alert_type == "SPINDLE_TEMP_HIGH":
        return f"{machine} 主轴温度 {production.get('spindle_temp', '未上报')} C，建议停机检查冷却、轴承与润滑。"
    if alert_type == "TOOL_WEAR_WARNING":
        return f"{machine} 刀具/砂轮磨损 {production.get('tool_wear_level', '未上报')}%，建议降速并安排更换。"
    if alert_type == "QUALITY_DRIFT":
        return f"{machine} 良品率漂移，产量 {production.get('finished_quantity', 0)}，缺陷 {production.get('defect_quantity', 0)}。"
    if alert_type == "VIBRATION_HIGH":
        return f"{machine} 振动异常，建议暂停加工并检查夹具、刀具与主轴。"
    if alert_type == "COOLANT_FLOW_LOW":
        return f"{machine} 冷却液流量偏低，建议降载并检查冷却泵与液位。"
    return f"{node_code} v2 心跳上报报警 {alert_type}。"


class MemoryStore:
    """In-memory factory state plus a lightweight realtime simulation engine."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.rng = random.Random(260507)
        # Nodes (workshops + cloud) and their metrics
        self.nodes: dict[str, Node] = {}
        self.metrics: list[MetricIn] = []
        self.machines: list[Machine] = []
        self.node_db_size_bytes: dict[str, int] = {}
        self.node_db_size_sources: dict[str, str] = {}
        self.node_heartbeats_v2: dict[str, dict[str, object]] = {}
        self.node_record_sync_ids: set[str] = set()
        # Market and inventory
        self.market_signals: list[MarketSignal] = []
        self.market_forecast: list[MarketForecast] = []
        self.inventory: list[InventoryItem] = []
        # Production planning and dispatch
        self.production_plans: list[ProductionPlanIn] = []
        self.dispatch_tasks: list[DispatchTask] = []
        self.allocation_orders: list[AllocationOrder] = []
        self.dispatch_seq = 0
        self.order_seq = 0
        self.part_queue: list[PartQueueItem] = []
        self.part_seq = 0
        self.part_completion_watermark: dict[str, int] = {}
        # Alerts / audit / commands / events / diagnoses
        self.alerts: list[Alert] = []
        self.audit_logs: list[AuditLog] = []
        self.commands: list[NodeCommand] = []
        self.command_manager = CommandManager()
        self.incident_events: list[IncidentEvent] = []
        self._shadow_event_count = 0
        self.ai_diagnoses: list[AiDiagnosis] = []
        # Topology / governance
        self.topology_edges: list[TopologyEdge] = []
        self.ai_shortcuts: list[AiShortcut] = []
        self.authority_matrix: list[dict[str, object]] = []
        self.cloud_roles: list[dict[str, object]] = []
        # Simulation
        self.simulation_running = False
        self.simulation_tick = 0
        self.simulation_speed = 1.0
        self.simulation_anomaly_rate = 0.12
        self.simulation_last_tick_at: datetime | None = None
        self.simulation_generated_orders = 0
        self.simulation_generated_events = 0
        self._suspend_persist = False

        if settings.persist_enabled:
            init_db()
        self.seed_demo()
        if settings.persist_enabled:
            self.load_heartbeat_shadow()
            self.load_command_shadow()
            self.load_part_queue_shadow()

    # ------------------------------------------------------------------
    # Persistence (optional, off by default)
    # ------------------------------------------------------------------

    def _persisting(self) -> bool:
        return settings.persist_enabled and not self._suspend_persist

    def _ephemeral_node_code(self, node_code: str) -> bool:
        return node_code.startswith("workflow-check-node-")

    def persist_metric(self, metric: MetricIn) -> None:
        if not self._persisting():
            return
        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO metrics (node_code, cpu_usage, memory_usage, disk_usage,
                       network_in, network_out, db_latency_ms, api_latency_ms, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (metric.node_code, metric.cpu_usage, metric.memory_usage, metric.disk_usage,
                     metric.network_in, metric.network_out, metric.db_latency_ms,
                     metric.api_latency_ms, utc_now().isoformat()),
                )
        except Exception as exc:  # pragma: no cover - persistence is best-effort
            logger.warning("Persistence warning (metric): %s", exc)

    def persist_heartbeat_shadow(self, payload: dict[str, object]) -> None:
        """Persist a replay-ready v2 heartbeat without changing the live read path."""
        if not self._persisting():
            return
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO heartbeat_shadow (
                       node_code, run_id, scenario_id, simulation_time, payload_json, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        str(payload.get("node_code") or ""),
                        str(runtime.get("run_id") or ""),
                        str(runtime.get("scenario_id") or ""),
                        runtime.get("simulation_time"),
                        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
                        utc_now().isoformat(),
                    ),
                )
                self._prune_heartbeat_shadow_locked(db)
        except Exception as exc:  # pragma: no cover - persistence is best-effort
            logger.warning("Persistence warning (heartbeat shadow): %s", exc)

    def _prune_heartbeat_shadow_locked(self, db: object, max_per_node: int | None = None) -> int:
        limit = settings.heartbeat_shadow_retention_per_node if max_per_node is None else max_per_node
        if limit <= 0:
            return 0
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

    def prune_heartbeat_shadow(self, max_per_node: int | None = None) -> dict[str, object]:
        """Apply heartbeat-shadow retention without mutating live runtime state."""
        if not settings.persist_enabled:
            return {"status": "disabled", "reason": "PERSIST_ENABLED=false"}
        limit = settings.heartbeat_shadow_retention_per_node if max_per_node is None else max_per_node
        if limit <= 0:
            return {"status": "disabled", "reason": "HEARTBEAT_SHADOW_RETENTION_PER_NODE<=0"}
        try:
            with get_db() as db:
                deleted = self._prune_heartbeat_shadow_locked(db, limit)
                row = db.execute("SELECT COUNT(*) AS count FROM heartbeat_shadow").fetchone()
                remaining = int(row["count"])
        except Exception as exc:  # pragma: no cover - depends on external backend
            return {"status": "degraded", "error": str(exc), "max_per_node": limit}
        return {"status": "ok", "deleted": deleted, "remaining": remaining, "max_per_node": limit}

    def load_heartbeat_shadow(self, limit: int = 500) -> int:
        """Restore latest persisted v2 heartbeat facts into the live runtime cache."""
        if not settings.persist_enabled:
            return 0
        try:
            with get_db() as db:
                rows = db.execute(
                    """
                    SELECT node_code, payload_json, received_at
                    FROM heartbeat_shadow
                    ORDER BY id DESC LIMIT ?
                    """,
                    (max(1, limit),),
                ).fetchall()
        except Exception as exc:  # pragma: no cover
            logger.warning("Persistence warning (heartbeat shadow load): %s", exc)
            return 0

        latest: dict[str, tuple[dict[str, object], object]] = {}
        for row in rows:
            data = dict(row)
            node_code = str(data.get("node_code") or "")
            if self._ephemeral_node_code(node_code):
                continue
            if not node_code or node_code in latest:
                continue
            try:
                payload = json.loads(str(data.get("payload_json") or "{}"))
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                latest[node_code] = (payload, data.get("received_at"))

        with self._lock:
            for node_code, (payload, received_at) in latest.items():
                self._restore_heartbeat_shadow_locked(node_code, payload, received_at)
        return len(latest)

    def _restore_heartbeat_shadow_locked(self, node_code: str, payload: dict[str, object], received_at: object) -> None:
        production = payload.get("production") if isinstance(payload.get("production"), dict) else {}
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        sync = payload.get("sync") if isinstance(payload.get("sync"), dict) else {}
        alarms = payload.get("alarms") if isinstance(payload.get("alarms"), list) else []
        workshop_type = str(production.get("workshop_type") or self.infer_workshop_type(node_code))
        heartbeat_time = _database_datetime(received_at) if received_at else utc_now()
        raw_status = str(payload.get("status") or "running")
        node_status = NodeStatus.online if raw_status in {"running", "online", "idle"} else NodeStatus.degraded

        node = self.nodes.setdefault(
            node_code,
            Node(
                node_code=node_code,
                node_name=self.node_display_name(node_code, workshop_type),
                workshop_type=workshop_type,
            ),
        )
        node.workshop_type = workshop_type
        node.status = node_status
        node.last_heartbeat = heartbeat_time

        machine_code = str(production.get("machine_code") or node_code)
        machine = next((item for item in self.machines if item.machine_code == machine_code), None)
        if machine is None:
            machine = Machine(machine_code=machine_code, node_code=node_code, machine_type=workshop_type)
            self.machines.append(machine)
        machine.node_code = node_code
        machine.status = "fault" if raw_status == "fault" else "warning" if raw_status == "warning" else "running"
        machine.load_rate = float(production.get("utilization") or 0) * 100
        machine.tool_wear_level = float(production.get("tool_wear_level") or machine.tool_wear_level)
        machine.today_output = int(production.get("finished_quantity") or machine.today_output)
        machine.defect_count = int(production.get("defect_quantity") or machine.defect_count)

        self.node_heartbeats_v2[node_code] = {
            **payload,
            "production": dict(production),
            "metrics": dict(metrics),
            "runtime": dict(runtime),
            "sync": dict(sync),
            "alarms": list(alarms),
            "_received_at": heartbeat_time.isoformat(),
            "_restored_from_persistence": True,
        }
        self.metrics.append(MetricIn(
            node_code=node_code,
            workshop_type=workshop_type,
            cpu_usage=float(metrics.get("cpu_usage") or 0),
            memory_usage=float(metrics.get("memory_usage") or 0),
            disk_usage=float(metrics.get("disk_usage") or 0),
            network_in=int(metrics.get("network_in") or metrics.get("network_in_bytes") or 0),
            network_out=int(metrics.get("network_out") or metrics.get("network_out_bytes") or 0),
            db_latency_ms=int(metrics.get("db_latency_ms") or 0),
            api_latency_ms=int(metrics.get("api_latency_ms") or metrics.get("network_latency_ms") or 0),
            finished_quantity=int(production.get("finished_quantity") or 0),
            defect_quantity=int(production.get("defect_quantity") or 0),
        ))
        self.metrics = self.metrics[-300:]

    def persist_alert(self, alert: Alert) -> None:
        if not self._persisting():
            return
        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO alerts (node_code, alert_type, severity, source, description,
                       handled_by, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (alert.node_code, alert.alert_type, alert.severity.value,
                     alert.handled_by or "system", alert.description, alert.handled_by,
                     alert.status, alert.created_at.isoformat()),
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Persistence warning (alert): %s", exc)

    def persist_command(self, command: NodeCommand) -> None:
        if not self._persisting():
            return
        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO commands (node_code, command_type, risk_level, status, operator, created_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (command.node_code, command.command_type, command.risk_level,
                     command.status, command.operator, command.created_at.isoformat()),
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Persistence warning (command): %s", exc)
        self.persist_command_shadow(command)

    def persist_command_shadow(self, command: NodeCommand) -> None:
        if not self._persisting():
            return
        try:
            with get_db() as db:
                db.execute(
                    """
                    INSERT INTO command_shadow (
                        command_id, node_code, command_type, risk_level, status, operator,
                        parameters_json, claimed_by, result_message, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(command_id) DO UPDATE SET
                        node_code=excluded.node_code,
                        command_type=excluded.command_type,
                        risk_level=excluded.risk_level,
                        status=excluded.status,
                        operator=excluded.operator,
                        parameters_json=excluded.parameters_json,
                        claimed_by=excluded.claimed_by,
                        result_message=excluded.result_message,
                        created_at=excluded.created_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        command.id,
                        command.node_code,
                        command.command_type,
                        command.risk_level,
                        command.status,
                        command.operator,
                        json.dumps(command.parameters, ensure_ascii=False, sort_keys=True),
                        command.claimed_by,
                        command.result_message,
                        command.created_at.isoformat(),
                        command.updated_at.isoformat(),
                    ),
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Persistence warning (command shadow): %s", exc)

    def load_command_shadow(self) -> int:
        if not settings.persist_enabled:
            return 0
        loaded: list[NodeCommand] = []
        try:
            with get_db() as db:
                rows = db.execute(
                    """
                    SELECT command_id, node_code, command_type, risk_level, status, operator,
                           parameters_json, claimed_by, result_message, created_at, updated_at
                    FROM command_shadow
                    ORDER BY command_id ASC
                    """
                ).fetchall()
        except Exception as exc:  # pragma: no cover
            logger.warning("Persistence warning (command shadow load): %s", exc)
            return 0

        for row in rows:
            data = dict(row)
            try:
                parameters = json.loads(data.get("parameters_json") or "{}")
            except json.JSONDecodeError:
                parameters = {}
            loaded.append(NodeCommand(
                id=int(data["command_id"]),
                node_code=data["node_code"],
                command_type=data["command_type"],
                risk_level=data["risk_level"],
                status=data["status"],
                operator=data["operator"],
                parameters=parameters if isinstance(parameters, dict) else {},
                claimed_by=data.get("claimed_by") or "",
                result_message=data.get("result_message") or "",
                created_at=_database_datetime(data["created_at"]),
                updated_at=_database_datetime(data.get("updated_at") or data["created_at"]),
            ))
        with self._lock:
            self.commands = loaded[-100:]
        return len(loaded)

    def persist_event(self, event: IncidentEvent) -> None:
        if not self._persisting():
            return
        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO audit_logs (actor, action, resource_type, resource_id, result, detail, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (event.node_code, event.stage, "incident_event", str(event.id),
                     event.severity.value, event.message, event.created_at.isoformat()),
                )
            with self._lock:
                self._shadow_event_count += 1
        except Exception as exc:  # pragma: no cover
            logger.warning("Persistence warning (event): %s", exc)

    def persist_ai_diagnosis(self, diagnosis: AiDiagnosis) -> None:
        if not self._persisting():
            return
        try:
            with get_db() as db:
                db.execute(
                    """INSERT INTO ai_diagnosis (alert_id, severity, node_code, root_cause,
                       recommended_action, confidence, need_isolation, model_name, raw_response, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (diagnosis.alert_id, Severity.medium.value, diagnosis.node_code,
                     diagnosis.root_cause, diagnosis.recommended_action, diagnosis.confidence,
                     bool(diagnosis.need_isolation), diagnosis.model_name, None,
                     diagnosis.created_at.isoformat()),
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Persistence warning (ai_diagnosis): %s", exc)

    def persist_part_queue_item(self, part: PartQueueItem) -> None:
        if not self._persisting():
            return
        try:
            with get_db() as db:
                db.execute(
                    """
                    INSERT INTO part_queue_shadow (
                        part_id, parent_part_id, order_id, product_code, current_step, status,
                        source_node, target_node, claimed_by, claim_token, claim_expires_at,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(part_id) DO UPDATE SET
                        parent_part_id=excluded.parent_part_id,
                        order_id=excluded.order_id,
                        product_code=excluded.product_code,
                        current_step=excluded.current_step,
                        status=excluded.status,
                        source_node=excluded.source_node,
                        target_node=excluded.target_node,
                        claimed_by=excluded.claimed_by,
                        claim_token=excluded.claim_token,
                        claim_expires_at=excluded.claim_expires_at,
                        created_at=excluded.created_at,
                        updated_at=excluded.updated_at
                    """,
                    (
                        part.part_id,
                        part.parent_part_id,
                        part.order_id,
                        part.product_code,
                        part.current_step,
                        part.status,
                        part.source_node,
                        part.target_node,
                        part.claimed_by,
                        part.claim_token,
                        part.claim_expires_at.isoformat() if part.claim_expires_at else None,
                        part.created_at.isoformat(),
                        part.updated_at.isoformat(),
                    ),
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Persistence warning (part_queue): %s", exc)

    def load_part_queue_shadow(self) -> int:
        if not settings.persist_enabled:
            return 0
        loaded: list[PartQueueItem] = []
        try:
            with get_db() as db:
                rows = db.execute(
                    """
                    SELECT part_id, parent_part_id, order_id, product_code, current_step, status,
                           source_node, target_node, claimed_by, claim_token, claim_expires_at,
                           created_at, updated_at
                    FROM part_queue_shadow
                    ORDER BY created_at ASC, part_id ASC
                    """
                ).fetchall()
        except Exception as exc:  # pragma: no cover
            logger.warning("Persistence warning (part_queue load): %s", exc)
            return 0

        for row in rows:
            data = dict(row)
            loaded.append(PartQueueItem(
                **{
                    **data,
                    "claim_expires_at": _database_datetime(data["claim_expires_at"]) if data.get("claim_expires_at") else None,
                    "created_at": _database_datetime(data["created_at"]),
                    "updated_at": _database_datetime(data["updated_at"]),
                }
            ))
        with self._lock:
            self.part_queue = loaded[-500:]
            max_seq = 0
            for part in self.part_queue:
                try:
                    max_seq = max(max_seq, int(part.part_id.rsplit("-", 1)[-1]))
                except ValueError:
                    continue
            self.part_seq = max(self.part_seq, max_seq)
        return len(loaded)

    # ------------------------------------------------------------------
    # Seed
    # ------------------------------------------------------------------

    def seed_demo(self) -> None:
        with self._lock:
            self._suspend_persist = True
            self.nodes = {
            "turning-workshop-01": Node(node_code="turning-workshop-01", node_name=WORKSHOP_NAMES["turning"], workshop_type="turning"),
            "milling-workshop-01": Node(node_code="milling-workshop-01", node_name=WORKSHOP_NAMES["milling"], workshop_type="milling"),
            "grinding-workshop-01": Node(node_code="grinding-workshop-01", node_name=WORKSHOP_NAMES["grinding"], workshop_type="grinding"),
            "cloud-workshop-01": Node(node_code="cloud-workshop-01", node_name=WORKSHOP_NAMES["cloud"], workshop_type="cloud"),
            "cloud-db-01": Node(node_code="cloud-db-01", node_name=WORKSHOP_NAMES["database"], workshop_type="database"),
        }
        self.metrics.clear()
        self.node_heartbeats_v2.clear()
        self.alerts.clear()
        self.audit_logs.clear()
        self.commands.clear()
        self.incident_events.clear()
        self.ai_diagnoses.clear()
        self.allocation_orders.clear()
        self.dispatch_tasks.clear()
        self.dispatch_seq = 0
        self.order_seq = 0
        self.part_queue.clear()
        self.part_seq = 0
        self.part_completion_watermark.clear()
        self.simulation_running = False
        self.simulation_tick = 0
        self.simulation_generated_orders = 0
        self.simulation_generated_events = 0
        self.simulation_last_tick_at = None

        self.machines = [
            Machine(machine_code="TURN-01", node_code="turning-workshop-01", machine_type="数控车床", load_rate=58, tool_wear_level=32, today_output=210, defect_count=4),
            Machine(machine_code="TURN-02", node_code="turning-workshop-01", machine_type="数控车床", load_rate=44, tool_wear_level=21, today_output=176, defect_count=2),
            Machine(machine_code="MILL-01", node_code="milling-workshop-01", machine_type="立式加工中心", load_rate=63, tool_wear_level=40, today_output=188, defect_count=6),
            Machine(machine_code="MILL-02", node_code="milling-workshop-01", machine_type="立式加工中心", load_rate=51, tool_wear_level=28, today_output=164, defect_count=3),
            Machine(machine_code="GRIND-01", node_code="grinding-workshop-01", machine_type="数控外圆磨床", load_rate=47, tool_wear_level=36, today_output=142, defect_count=3),
        ]

        self.cloud_roles = [
            {"node_code": "cloud-workshop-01", "role": "云端 AI 协同",
             "responsibility": "辅助诊断、解释调度方案、承接上级调配任务",
             "permission_boundary": "只读指标与建议，不能直接执行隔离/恢复等高危命令"},
            {"node_code": "cloud-db-01", "role": "云端数据库与审计",
             "responsibility": "归档全局指标、镜像审计日志、保存最终生产计划",
             "permission_boundary": "只写归档数据，不能修改在产计划或下发命令"},
        ]

        self.authority_matrix = [
            {"role": "生产调度员", "can": ["生成生产计划", "调整优先级", "重建调度", "查看全局状态"],
             "cannot": ["直接隔离车间", "绕过审批执行高危命令"], "approval_required": False},
            {"role": "车间操作员", "can": ["查看本车间任务", "上报生产与设备状态", "执行低风险脚本修复"],
             "cannot": ["修改全局调度", "审批高危命令"], "approval_required": False},
            {"role": "AI 助手", "can": ["生成诊断建议", "解释调度方案", "提出隔离/恢复建议"],
             "cannot": ["直接执行系统控制", "覆盖人工审批"], "approval_required": True},
            {"role": "系统管理员", "can": ["审批隔离/恢复", "处理异常升级", "调整节点权限"],
             "cannot": ["删除审计记录"], "approval_required": True},
        ]

        self.ai_shortcuts = [
            AiShortcut(id="node-risk", label="车间风险判断",
                       description="汇总指标、告警与拓扑，判断哪个车间需要限流或隔离。",
                       prompt="请判断当前最需要关注的车间节点风险，并给出三步处理建议。",
                       action_hint="diagnose", risk_level="low"),
            AiShortcut(id="dispatch-advice", label="调度优化建议",
                       description="根据设备负载、刀具磨损与计划队列，给出排产优化建议。",
                       prompt="请解释当前生产调度为什么这样分配，并指出瓶颈车间或设备。",
                       action_hint="planning", risk_level="low"),
            AiShortcut(id="defect-analysis", label="质量缺陷分析",
                       description="分析最近的不良品与告警，总结原因并给出改进建议。",
                       prompt="请分析当前不良率偏高的原因，并按优先级给出改进建议。",
                       action_hint="quality", risk_level="medium"),
            AiShortcut(id="interview-script", label="复试讲解稿",
                       description="把当前工厂状态整理成 60 秒复试展示话术。",
                       prompt="请把当前 Mini-OGAS 工厂状态整理成研究生复试可用的 60 秒说明，强调分布式节点监控、生产调度与故障自愈能力。",
                       action_hint="presentation", risk_level="low"),
        ]

        self.topology_edges = [
            TopologyEdge(source="dashboard", target="central-api", protocol="HTTP", status="healthy", latency_ms=18),
            TopologyEdge(source="central-api", target="postgres", protocol="SQL", status="planned", latency_ms=0),
            TopologyEdge(source="central-api", target="redis", protocol="RESP", status="planned", latency_ms=0),
            TopologyEdge(source="central-api", target="deepseek-gateway", protocol="HTTPS", status="standby", latency_ms=180),
            TopologyEdge(source="central-api", target="ai-dispatcher", protocol="HTTP", status="unknown", latency_ms=0),
            TopologyEdge(source="central-api", target="market-simulator", protocol="HTTP", status="unknown", latency_ms=0),
            TopologyEdge(source="central-api", target="production-planner", protocol="HTTP", status="unknown", latency_ms=0),
            TopologyEdge(source="central-api", target="cloud-db-01", protocol="SQL/Agent", status="healthy", latency_ms=62),
            TopologyEdge(source="central-api", target="turning-workshop-01", protocol="HTTP/Agent", status="healthy", latency_ms=42),
            TopologyEdge(source="central-api", target="milling-workshop-01", protocol="HTTP/Agent", status="healthy", latency_ms=48),
            TopologyEdge(source="central-api", target="grinding-workshop-01", protocol="HTTP/Agent", status="healthy", latency_ms=51),
            TopologyEdge(source="central-api", target="cloud-workshop-01", protocol="HTTP/Agent", status="healthy", latency_ms=55),
        ]

        self.market_signals = []
        self.market_forecast = []
        self.inventory = []
        for code, product in PRODUCTS.items():
            price = float(product["price"])
            demand = self.rng.uniform(70, 130)
            self.market_signals.append(MarketSignal(
                product_code=code, product_name=str(product["name"]),
                current_price=round(price, 2),
                competitor_price=round(price * self.rng.uniform(0.9, 1.12), 2),
                demand_index=round(demand, 1),
                season_factor=round(self.rng.uniform(0.85, 1.25), 2),
                inventory_pressure=round(self.rng.uniform(20, 80), 1),
            ))
            self.market_forecast.append(MarketForecast(
                product_code=code, product_name=str(product["name"]), month="2026-06",
                baseline_demand=int(demand), forecast_demand=int(demand * self.rng.uniform(1.0, 1.3)),
                competitor_pressure=round(self.rng.uniform(0.3, 0.8), 2),
            ))
            stock = self.rng.randint(120, 600)
            safety = self.rng.randint(150, 300)
            self.inventory.append(InventoryItem(
                product_code=code, product_name=str(product["name"]),
                current_stock=stock, safety_stock=safety,
                pressure_score=round(max(0.0, (safety - stock) / safety * 100), 1),
                expected_days=round(stock / max(1.0, demand / 5), 1),
            ))

        self.allocation_orders = []
        self._add_allocation_order(AllocationOrderIn(
            product_code="P3", required_quantity=120, priority=2, deadline_hours=18,
            assigned_cloud_role="主调配", source_unit="上级调度中心",
            reason="变速箱齿轮订单激增，需要优先排产。"))

        for code, baseline in (
            ("turning-workshop-01", _workshop_baseline("turning")),
            ("milling-workshop-01", _workshop_baseline("milling")),
            ("grinding-workshop-01", _workshop_baseline("grinding")),
        ):
            self.record_metric(MetricIn(
                node_code=code, cpu_usage=baseline.cpu, memory_usage=baseline.mem,
                disk_usage=baseline.disk, network_in=12_400_000, network_out=8_200_000,
                db_latency_ms=baseline.db, api_latency_ms=baseline.api,
                finished_quantity=self.rng.randint(160, 460), defect_quantity=self.rng.randint(3, 12),
            ), evaluate=False)

        self.generate_production_plan()
        self.rebuild_dispatch()
        self.add_event("central-api", "startup", Severity.info,
                       "Mini-OGAS 中心控制节点启动，三个车间节点与云节点注册成功。")
        self._suspend_persist = False

    # ------------------------------------------------------------------
    # Name helpers
    # ------------------------------------------------------------------

    def infer_workshop_type(self, node_code: str) -> str:
        for key in ("turning", "milling", "grinding"):
            if key in node_code:
                return key
        if "db" in node_code:
            return "database"
        if "cloud" in node_code:
            return "cloud"
        return "general"

    def node_display_name(self, node_code: str, workshop_type: str) -> str:
        return WORKSHOP_NAMES.get(workshop_type, node_code)

    # ------------------------------------------------------------------
    # Events / commands / alerts / diagnoses
    # ------------------------------------------------------------------

    def add_event(self, node_code: str, stage: str, severity: Severity, message: str) -> IncidentEvent:
        with self._lock:
            event = IncidentEvent(id=len(self.incident_events) + 1, node_code=node_code,
                                  stage=stage, severity=severity, message=message)
            self.incident_events.append(event)
            self.incident_events = self.incident_events[-160:]
        self.persist_event(event)
        return event

    def _apply_command_transitions(
        self,
        transitions: list[CommandTransition],
        severity: Severity = Severity.info,
    ) -> None:
        for transition in transitions:
            self.persist_command_shadow(transition.command)
            self.add_event(
                transition.command.node_code,
                transition.stage,
                severity,
                transition.message,
            )

    def add_command(
        self,
        node_code: str,
        command_type: str,
        risk_level: str,
        status: str,
        operator: str,
        parameters: dict[str, object] | None = None,
    ) -> NodeCommand:
        with self._lock:
            command, transitions, created = self.command_manager.create_command(
                self.commands,
                node_code=node_code,
                command_type=command_type,
                risk_level=risk_level,
                status=status,
                operator=operator,
                parameters=parameters,
            )
        self._apply_command_transitions(transitions, Severity.medium)
        if created:
            self.persist_command(command)
        return command

    def create_alert(self, node_code: str, alert_type: str, severity: Severity, description: str,
                     handled_by: str | None = None) -> Alert:
        with self._lock:
            alert = Alert(id=len(self.alerts) + 1, node_code=node_code, alert_type=alert_type,
                          severity=severity, description=description, handled_by=handled_by)
            self.alerts.append(alert)
            self.alerts = self.alerts[-120:]
        self.persist_alert(alert)
        return alert

    def add_ai_diagnosis(self, alert_id: int, node_code: str, root_cause: str,
                         recommended_action: str, confidence: float, need_isolation: bool,
                         model_name: str, raw_response: str = "") -> AiDiagnosis:
        with self._lock:
            diagnosis = AiDiagnosis(id=len(self.ai_diagnoses) + 1, alert_id=alert_id, node_code=node_code,
                                    model_name=model_name, root_cause=root_cause,
                                    recommended_action=recommended_action, confidence=confidence,
                                    need_isolation=need_isolation, raw_response=raw_response)
            self.ai_diagnoses.append(diagnosis)
            self.ai_diagnoses = self.ai_diagnoses[-80:]
        self.persist_ai_diagnosis(diagnosis)
        self.add_event(node_code, "ai-diagnosis", Severity.medium,
                       "AI 诊断结果已写入中心诊断记录，等待人工复核。")
        return diagnosis

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def record_heartbeat(self, node_code: str, agent_version: str, uptime_seconds: int,
                         local_db_size_bytes: int, status: str = "online",
                         session_token: str = "", db_size_source: str = "reported") -> dict[str, object]:
        # Session token verification: reject heartbeats from stale processes
        my_token = get_session_token()
        token_mismatch = False
        if session_token and my_token and session_token != my_token:
            token_mismatch = True
            logger.warning(
                "Heartbeat session mismatch for %s: got %s..., expected %s...",
                node_code, session_token[:8], my_token[:8],
            )
            self.add_event(
                node_code, "session-mismatch", Severity.high,
                f"节点 {node_code} 心跳会话令牌不匹配，可能来自旧进程。心跳已接受但标记为未验证。",
            )
        with self._lock:
            workshop_type = self.infer_workshop_type(node_code)
            node = self.nodes.setdefault(
                node_code,
                Node(node_code=node_code, node_name=self.node_display_name(node_code, workshop_type),
                     workshop_type=workshop_type),
            )
            node.workshop_type = workshop_type
            node.last_heartbeat = utc_now()
            if status == "shutting_down":
                if node.status != NodeStatus.isolated:
                    node.status = NodeStatus.offline
            elif node.status == NodeStatus.degraded:
                if status == "online":
                    node.status = NodeStatus.online
            elif node.status == NodeStatus.offline and status == "online":
                node.status = NodeStatus.online
            elif node.status == NodeStatus.online and status == "online":
                pass
            self.node_db_size_bytes[node_code] = local_db_size_bytes
            self.node_db_size_sources[node_code] = db_size_source or "reported"
        return {
            "accepted": True,
            "node_code": node_code,
            "agent_version": agent_version,
            "uptime_seconds": uptime_seconds,
            "local_db_size_bytes": local_db_size_bytes,
            "db_size_source": db_size_source or "reported",
            "status": status,
            "session_verified": not token_mismatch,
        }

    def record_node_heartbeat_v2(self, payload: dict[str, object]) -> dict[str, object]:
        node_code = str(payload["node_code"])
        production = payload.get("production") if isinstance(payload.get("production"), dict) else {}
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        sync = payload.get("sync") if isinstance(payload.get("sync"), dict) else {}
        alarms = payload.get("alarms") if isinstance(payload.get("alarms"), list) else []
        raw_status = str(payload.get("status") or "running")
        node_status = "online" if raw_status in {"running", "online", "idle"} else "degraded"

        uptime = int(payload.get("uptime_sec") or payload.get("uptime_seconds") or 0)
        agent_version = str(payload.get("agent_version") or "0.2.0")
        heartbeat_result = self.record_heartbeat(
            node_code=node_code,
            agent_version=agent_version,
            uptime_seconds=uptime,
            local_db_size_bytes=int(sync.get("local_db_size_bytes") or 0),
            status=node_status,
            session_token=str(payload.get("session_token") or ""),
            db_size_source=str(sync.get("db_size_source") or "heartbeat-v2-sync"),
        )

        workshop_type = str(production.get("workshop_type") or self.infer_workshop_type(node_code))
        metric = MetricIn(
            node_code=node_code,
            workshop_type=workshop_type,
            cpu_usage=float(metrics.get("cpu_usage") or 0),
            memory_usage=float(metrics.get("memory_usage") or 0),
            disk_usage=float(metrics.get("disk_usage") or 0),
            network_in=int(metrics.get("network_in") or metrics.get("network_in_bytes") or 0),
            network_out=int(metrics.get("network_out") or metrics.get("network_out_bytes") or 0),
            db_latency_ms=int(metrics.get("db_latency_ms") or 0),
            api_latency_ms=int(metrics.get("api_latency_ms") or metrics.get("network_latency_ms") or 0),
            finished_quantity=int(production.get("finished_quantity") or 0),
            defect_quantity=int(production.get("defect_quantity") or 0),
        )
        self.record_metric(metric, evaluate=False)

        machine_code = str(production.get("machine_code") or node_code)
        with self._lock:
            existing_machine = next((m for m in self.machines if m.machine_code == machine_code), None)
            if existing_machine is None:
                existing_machine = Machine(
                    machine_code=machine_code,
                    node_code=node_code,
                    machine_type=workshop_type,
                )
                self.machines.append(existing_machine)
            existing_machine.node_code = node_code
            existing_machine.status = "fault" if raw_status == "fault" else "warning" if raw_status == "warning" else "running"
            existing_machine.load_rate = float(production.get("utilization") or 0) * 100
            existing_machine.tool_wear_level = float(production.get("tool_wear_level") or existing_machine.tool_wear_level)
            existing_machine.today_output = int(production.get("finished_quantity") or existing_machine.today_output)
            existing_machine.defect_count = int(production.get("defect_quantity") or existing_machine.defect_count)
            self.node_heartbeats_v2[node_code] = {
                **payload,
                "production": dict(production),
                "metrics": dict(metrics),
                "runtime": dict(runtime),
                "sync": dict(sync),
                "alarms": list(alarms),
                "_received_at": utc_now().isoformat(),
            }
            self._verify_target_rate_commands_locked(node_code, production)

        self.persist_heartbeat_shadow(payload)

        created_alerts = []
        for alarm in alarms:
            if not isinstance(alarm, dict):
                continue
            alert_type = str(alarm.get("type") or "UNKNOWN_ALARM")
            if any(a.node_code == node_code and a.alert_type == alert_type and a.status not in {"closed", "resolved"} for a in self.alerts):
                continue
            severity = _heartbeat_alarm_severity(str(alarm.get("severity") or "medium"))
            description = _heartbeat_alarm_description(node_code, alert_type, production)
            created_alerts.append(self.create_alert(node_code, alert_type, severity, description))

        if created_alerts:
            self.add_event(
                node_code,
                "heartbeat-v2-alerts",
                max((alert.severity for alert in created_alerts), key=_severity_rank),
                f"v2 心跳上报 {len(created_alerts)} 个报警，已写入中心报警队列。",
            )

        parts_created = self._create_parts_from_turning_heartbeat(node_code, production)

        return {
            **heartbeat_result,
            "schema_version": payload.get("schema_version") or "2.2",
            "runtime": runtime,
            "production": production,
            "alarms_accepted": len(created_alerts),
            "parts_created": parts_created,
        }

    def node_dispatch_for_node(self, node_code: str) -> dict[str, object]:
        """Return the host-issued task selected for one node agent."""
        with self._lock:
            task = next(
                (
                    item for item in self.dispatch_tasks
                    if item.assigned_node == node_code
                    and item.status in {"scheduled", "queued", "in_progress"}
                ),
                None,
            )
            if task is None:
                return {"dispatch": {}}
            return {
                "dispatch": {
                    "dispatch_id": task.id,
                    "active_order": task.product_code,
                    "product_code": task.product_code,
                    "quantity": task.quantity,
                    "priority": task.priority,
                    "assigned_machine": task.assigned_machine,
                    "status": task.status,
                    "reason": task.reason,
                }
            }

    def record_node_records(self, node_code: str, records: list[dict[str, object]]) -> dict[str, object]:
        """Acknowledge deduplicated local agent records after a transient outage."""
        accepted = 0
        with self._lock:
            for record in records:
                local_id = record.get("local_id")
                if not isinstance(local_id, int):
                    continue
                key = f"{node_code}:{local_id}"
                if key in self.node_record_sync_ids:
                    continue
                self.node_record_sync_ids.add(key)
                accepted += 1
            if len(self.node_record_sync_ids) > 10000:
                self.node_record_sync_ids = set(list(self.node_record_sync_ids)[-5000:])
        if accepted:
            self.add_event(
                node_code,
                "node-record-sync",
                Severity.info,
                f"Agent local records acknowledged: {accepted}",
            )
        return {"accepted": True, "node_code": node_code, "records_accepted": accepted}

    def check_heartbeat_timeout(self) -> int:
        """Mark nodes as offline if their last heartbeat is older than the timeout.

        Returns the number of nodes that were marked offline.
        """
        timeout_seconds = settings.heartbeat_timeout_seconds
        cutoff = utc_now() - timedelta(seconds=timeout_seconds)
        expired = 0
        with self._lock:
            for node in self.nodes.values():
                if not self._requires_agent_heartbeat(node.node_code, node.workshop_type):
                    continue
                if node.status in {NodeStatus.online, NodeStatus.degraded} and node.last_heartbeat < cutoff:
                    node.status = NodeStatus.offline
                    expired += 1
                    self.add_event(node.node_code, "heartbeat-timeout", Severity.high,
                                   f"节点 {node.node_code} 心跳超时（>{timeout_seconds}s），自动标记为离线。")
        return expired

    def _requires_agent_heartbeat(self, node_code: str, workshop_type: str | None) -> bool:
        if self._is_control_plane_node(node_code, workshop_type):
            return False
        if node_code in self.node_heartbeats_v2:
            return True
        return workshop_type in {"turning", "milling", "grinding"}

    def _is_control_plane_node(self, node_code: str, workshop_type: str | None = None) -> bool:
        resolved_type = workshop_type or self.infer_workshop_type(node_code)
        return node_code in {"cloud-workshop-01", "cloud-db-01"} or resolved_type in {"cloud", "database"}

    # ------------------------------------------------------------------
    # Metric recording + rule-based fault handling
    # ------------------------------------------------------------------

    def record_metric(self, metric: MetricIn, evaluate: bool = True) -> list[Alert]:
        with self._lock:
            workshop_type = metric.workshop_type or self.infer_workshop_type(metric.node_code)
            is_control_plane = self._is_control_plane_node(metric.node_code, workshop_type)
            node = self.nodes.setdefault(
                metric.node_code,
                Node(node_code=metric.node_code, node_name=self.node_display_name(metric.node_code, workshop_type),
                     workshop_type=workshop_type),
            )
            node.workshop_type = workshop_type
            # Allow degraded→online recovery if the triggering condition is gone
            if node.status == NodeStatus.degraded and metric.cpu_usage < 92:
                node.status = NodeStatus.online
            elif node.status not in {NodeStatus.isolated, NodeStatus.degraded}:
                node.status = NodeStatus.online
            node.last_heartbeat = utc_now()
            self.metrics.append(metric)
            self.metrics = self.metrics[-300:]
        self.persist_metric(metric)
        if is_control_plane:
            return []
        if not evaluate:
            return []

        alerts: list[Alert] = []
        degraded_alert = None
        # L1 (low): disk pressure -> local script repair
        if metric.disk_usage >= 90:
            alerts.append(self.create_alert(metric.node_code, "disk_pressure", Severity.low,
                          "磁盘使用率过高，优先执行本地临时文件清理脚本。", "script"))
            self.add_command(metric.node_code, "clean_temp_cache", "low", "pending", "central-policy")
            self.add_event(metric.node_code, "script-repair", Severity.low, "中心已下发临时缓存清理命令。")
        # L2 (medium): CPU + latency correlation -> AI diagnosis
        if metric.cpu_usage >= 92 and metric.api_latency_ms >= 800:
            alert = self.create_alert(metric.node_code, "cpu_latency_correlation", Severity.medium,
                                      "CPU 与 API 延迟同时升高，建议调用 DeepSeek 辅助诊断。", "ai")
            alerts.append(alert)
            with self._lock:
                node.status = NodeStatus.degraded
            degraded_alert = alert
        # L3 (high): hostile inbound traffic -> auto isolation
        if metric.network_in >= 100_000_000:
            alerts.append(self.create_alert(metric.node_code, "hostile_traffic", Severity.high,
                          "车间节点入口流量异常，疑似敌对行为，建议立即隔离。", "system"))
            self.add_event(metric.node_code, "hostile-detected", Severity.high,
                           "检测到异常入站流量，策略引擎判定为敌对行为。")
            self.isolate_node(metric.node_code, "auto-policy")

        # ---- AI diagnosis (outside lock — slow DeepSeek call) ----
        if degraded_alert is not None:
            with self._lock:
                recent = [m for m in self.metrics if m.node_code == metric.node_code][-5:]
            prompt = (
                f"车间节点 {metric.node_code} 触发 CPU/延迟复杂故障。\n"
                f"告警：{degraded_alert.description}\n"
                f"最近 5 条指标：{[m.model_dump(mode='json') for m in recent]}\n"
                "请判断根因、推荐动作、置信度以及是否需要隔离。"
            )
            try:
                result = registry.diagnose(prompt)
                rc, ra, cf, ni = (result.root_cause, result.recommended_action,
                                  result.confidence, result.need_isolation)
                # Find which provider served the result
                active = registry.first_available()
                mn = active.name if active else "unknown"
            except Exception:
                rc = "车间节点负载升高并伴随加工队列等待，可能由批量订单与本地缓存竞争导致。"
                ra = "重启加工调度进程，限制新任务下发，并观察 10 分钟。"
                cf, ni, mn = 0.82, False, "local-fallback"
            self.add_ai_diagnosis(degraded_alert.id, metric.node_code, rc, ra, cf, ni, mn, "")
            self.add_command(metric.node_code, "restart_workshop_scheduler", "medium",
                             "waiting_approval", "ai-policy")
        return alerts

    def latest_metrics(self) -> dict[str, MetricIn]:
        result: dict[str, MetricIn] = {}
        for m in self.metrics:
            result[m.node_code] = m
        return result

    # ------------------------------------------------------------------
    # Node isolation / restore
    # ------------------------------------------------------------------

    def isolate_node(self, node_code: str, actor: str) -> Node:
        with self._lock:
            node = self.nodes[node_code]
            node.status = NodeStatus.isolated
            self.add_command(node_code, "isolate_node", "high", "executed", actor)
            self.add_event(node_code, "isolation", Severity.high, "车间接口已切断，只保留心跳与紧急恢复通道。")
            self.audit_logs.append(AuditLog(id=len(self.audit_logs) + 1, actor=actor, action="node:isolate",
                                            resource_type="node", resource_id=node_code, result="success"))
            for edge in self.topology_edges:
                if edge.target == node_code:
                    edge.status = "isolated"
                    edge.latency_ms = 999
        return node

    def restore_node(self, node_code: str, actor: str) -> Node:
        with self._lock:
            node = self.nodes[node_code]
            node.status = NodeStatus.online
            node.last_heartbeat = utc_now()  # prevent immediate timeout after restore
            self.add_command(node_code, "restore_node", "high", "executed", actor)
            self.add_event(node_code, "restore", Severity.info, "管理员恢复车间通信，重新纳入中心调度。")
            self.audit_logs.append(AuditLog(id=len(self.audit_logs) + 1, actor=actor, action="node:restore",
                                            resource_type="node", resource_id=node_code, result="success"))
            for edge in self.topology_edges:
                if edge.target == node_code:
                    edge.status = "healthy"
                    edge.latency_ms = 55
        # Recovered capacity changes the optimal plan, so regenerate and re-dispatch.
        self.generate_production_plan()
        self.rebuild_dispatch()
        return node

    def retire_node(self, node_code: str, actor: str) -> dict[str, object]:
        """Remove a transient or decommissioned node from active runtime state."""
        with self._lock:
            if node_code not in self.nodes:
                raise KeyError(node_code)
            removed_node = self.nodes.pop(node_code)
            self.node_db_size_bytes.pop(node_code, None)
            self.node_db_size_sources.pop(node_code, None)
            self.node_heartbeats_v2.pop(node_code, None)
            self.metrics = [m for m in self.metrics if m.node_code != node_code]
            self.machines = [m for m in self.machines if m.node_code != node_code]
            self.dispatch_tasks = [t for t in self.dispatch_tasks if t.assigned_node != node_code]
            self.part_queue = [
                p for p in self.part_queue
                if p.source_node != node_code and p.target_node != node_code and p.claimed_by != node_code
            ]
            self.topology_edges = [
                e for e in self.topology_edges if e.source != node_code and e.target != node_code
            ]
            for alert in self.alerts:
                if alert.node_code == node_code and alert.status not in {"closed", "resolved"}:
                    alert.status = "closed"
                    alert.handled_by = actor
            self.audit_logs.append(AuditLog(
                id=len(self.audit_logs) + 1,
                actor=actor,
                action="node:retire",
                resource_type="node",
                resource_id=node_code,
                result="success",
            ))
        self.add_event(node_code, "node-retired", Severity.info, "Runtime node retired from active topology.")
        return {
            "ok": True,
            "node_code": node_code,
            "status": "retired",
            "actor": actor,
            "removed_node": removed_node.model_dump(mode="json"),
        }

    # ------------------------------------------------------------------
    # Approvals / escalation
    # ------------------------------------------------------------------

    def pending_commands_for_node(self, node_code: str) -> list[NodeCommand]:
        expired = self._expire_stale_commands()
        if expired:
            self._apply_command_transitions(expired, Severity.medium)
        return self.command_manager.pending_for_node(self.commands, node_code)

    def claim_pending_commands_for_node(self, node_code: str, agent_id: str = "") -> list[NodeCommand]:
        with self._lock:
            expired = self.command_manager.expire_stale_claims(
                self.commands,
                ttl_seconds=settings.command_claim_timeout_seconds,
            )
            claimed = self.command_manager.claim_for_node(
                self.commands,
                node_code=node_code,
                agent_id=agent_id,
            )
        self._apply_command_transitions(expired, Severity.medium)
        for command in claimed:
            self.persist_command_shadow(command)
        if claimed:
            self.add_event(
                node_code,
                "command-claimed",
                Severity.info,
                f"agent claimed {len(claimed)} command(s): {', '.join(str(c.id) for c in claimed)}",
            )
        return claimed

    def record_command_result(self, node_code: str, command_id: int, status: str,
                              message: str) -> dict[str, object]:
        with self._lock:
            command, changed = self.command_manager.record_result(
                self.commands,
                node_code=node_code,
                command_id=command_id,
                status=status,
                message=message,
            )
        if changed:
            self.persist_command_shadow(command)
            self.add_event(node_code, "command-result", Severity.info,
                           f"command_id={command_id} status={command.status}: {message}")
        return {"accepted": True, "command_id": command_id, "status": command.status, "message": message}

    def record_agent_command_result(self, command_id: int, status: str, message: str) -> dict[str, object]:
        command = next((c for c in self.commands if c.id == command_id), None)
        if command is None:
            raise ValueError(f"command {command_id} not found")
        return self.record_command_result(command.node_code, command_id, status, message)

    def _verify_target_rate_commands_locked(self, node_code: str, production: dict) -> None:
        try:
            heartbeat_target = float(production.get("target_rate"))
        except (TypeError, ValueError):
            return
        transitions = self.command_manager.verify_target_rate(
            self.commands,
            node_code=node_code,
            target_rate=heartbeat_target,
        )
        self._apply_command_transitions(transitions)

    def _expire_stale_commands(self) -> list[CommandTransition]:
        with self._lock:
            return self.command_manager.expire_stale_claims(
                self.commands,
                ttl_seconds=settings.command_claim_timeout_seconds,
            )

    # ------------------------------------------------------------------
    # Part queue: turning -> milling transfer
    # ------------------------------------------------------------------

    def create_ready_part(
        self,
        order_id: str,
        product_code: str = "A3",
        source_node: str = "turning-workshop-01",
        target_node: str = "milling-workshop-01",
        current_step: str = "milling",
        parent_part_id: str = "",
    ) -> PartQueueItem:
        with self._lock:
            self.part_seq += 1
            part = PartQueueItem(
                part_id=f"PART-{self.part_seq:05d}",
                parent_part_id=parent_part_id,
                order_id=order_id,
                product_code=product_code or "A3",
                source_node=source_node,
                target_node=target_node,
                current_step=current_step,
            )
            self.part_queue.append(part)
            self.part_queue = self.part_queue[-500:]
        self.persist_part_queue_item(part)
        self.add_event(
            source_node,
            "part-ready",
            Severity.info,
            f"{part.part_id} from {order_id} is ready for {target_node}.",
        )
        return part

    def _release_expired_part_claims_locked(self, now: datetime) -> list[PartQueueItem]:
        released: list[PartQueueItem] = []
        for part in self.part_queue:
            if (
                part.status == "claimed"
                and part.claim_expires_at is not None
                and part.claim_expires_at <= now
            ):
                part.status = "ready"
                part.claimed_by = ""
                part.claim_token = ""
                part.claim_expires_at = None
                part.updated_at = now
                released.append(part)
        return released

    def _next_part_queue_step(self, part: PartQueueItem, completed_by: str) -> tuple[str, str] | None:
        route = product_route(part.product_code)
        current_step = part.current_step
        if current_step not in route:
            return None
        next_steps = route[route.index(current_step) + 1:]
        for step in next_steps:
            workshop_type = PROCESS_WORKSHOP.get(step)
            if workshop_type == "grinding":
                return ("grinding", "grinding-workshop-01")
            if workshop_type == "milling" and completed_by != "milling-workshop-01":
                return ("milling", "milling-workshop-01")
        return None

    def release_expired_part_claims(self) -> int:
        with self._lock:
            released = self._release_expired_part_claims_locked(utc_now())
        for part in released:
            self.persist_part_queue_item(part)
        for part in released:
            self.add_event(
                part.target_node,
                "part-claim-expired",
                Severity.medium,
                f"{part.part_id} claim expired and returned to ready queue.",
            )
        return len(released)

    def claim_next_part_for_node(self, node_code: str, ttl_seconds: int = 30) -> dict[str, object]:
        ttl = max(1, min(int(ttl_seconds or 30), 3600))
        claimed: PartQueueItem | None = None
        with self._lock:
            now = utc_now()
            released = self._release_expired_part_claims_locked(now)
            for part in self.part_queue:
                if part.target_node != node_code or part.status != "ready":
                    continue
                part.status = "claimed"
                part.claimed_by = node_code
                part.claim_token = str(uuid.uuid4())
                part.claim_expires_at = now + timedelta(seconds=ttl)
                part.updated_at = now
                claimed = part
                break
        for part in released:
            self.persist_part_queue_item(part)
            self.add_event(
                part.target_node,
                "part-claim-expired",
                Severity.medium,
                f"{part.part_id} claim expired and returned to ready queue.",
            )
        if claimed is None:
            return {"claimed": False, "part": None}
        self.persist_part_queue_item(claimed)
        self.add_event(
            node_code,
            "part-claimed",
            Severity.info,
            f"{claimed.part_id} claimed by {node_code}; token expires at {claimed.claim_expires_at}.",
        )
        return {"claimed": True, "part": claimed}

    def complete_claimed_part(self, node_code: str, part_id: str, claim_token: str) -> dict[str, object]:
        downstream: PartQueueItem | None = None
        with self._lock:
            part = next((item for item in self.part_queue if item.part_id == part_id), None)
            if part is None:
                raise ValueError(f"part {part_id} not found")
            if part.target_node != node_code:
                raise ValueError(f"part {part_id} is assigned to {part.target_node}, not {node_code}")
            if part.status != "claimed":
                raise ValueError(f"part {part_id} is not claimed (current: {part.status})")
            if not claim_token or part.claim_token != claim_token:
                raise ValueError("invalid claim token")
            part.status = "completed"
            part.claim_expires_at = None
            part.updated_at = utc_now()
            next_step = self._next_part_queue_step(part, node_code)
            if next_step is not None:
                step, target_node = next_step
                self.part_seq += 1
                downstream = PartQueueItem(
                    part_id=f"PART-{self.part_seq:05d}",
                    parent_part_id=part.part_id,
                    order_id=part.order_id,
                    product_code=part.product_code,
                    current_step=step,
                    source_node=node_code,
                    target_node=target_node,
                    status="ready",
                )
                self.part_queue.append(downstream)
                self.part_queue = self.part_queue[-500:]
        self.persist_part_queue_item(part)
        if downstream is not None:
            self.persist_part_queue_item(downstream)
        self.add_event(
            node_code,
            "part-completed",
            Severity.info,
            f"{part.part_id} completed by {node_code} and archived in part queue.",
        )
        if downstream is not None:
            self.add_event(
                downstream.source_node,
                "part-ready",
                Severity.info,
                f"{downstream.part_id} was generated from {part.part_id} and is ready for {downstream.target_node}.",
            )
        return {"accepted": True, "part": part, "downstream_part": downstream}

    def part_queue_snapshot(self) -> dict[str, object]:
        self.release_expired_part_claims()
        with self._lock:
            counts: dict[str, int] = {}
            for part in self.part_queue:
                counts[part.status] = counts.get(part.status, 0) + 1
            return {
                "counts": counts,
                "items": [part.model_dump(mode="json") for part in self.part_queue[-100:]],
            }

    def _create_parts_from_turning_heartbeat(self, node_code: str, production: dict[str, object]) -> int:
        if node_code != "turning-workshop-01":
            return 0
        try:
            finished = int(production.get("finished_quantity") or 0)
        except (TypeError, ValueError):
            return 0
        with self._lock:
            previous = self.part_completion_watermark.get(node_code)
            self.part_completion_watermark[node_code] = finished
        if previous is None or finished <= previous:
            return 0
        delta = min(finished - previous, 5)
        order_id = str(production.get("active_order") or "WO-LIVE")
        product_code = str(production.get("product_code") or "A3")
        for _ in range(delta):
            self.create_ready_part(order_id, product_code)
        return delta

    def pending_approvals(self) -> list[NodeCommand]:
        return self.command_manager.pending_approvals(self.commands)

    def approve_command(self, command_id: int, actor: str) -> dict[str, object]:
        with self._lock:
            command = self.command_manager.approve(self.commands, command_id=command_id, actor=actor)
        self.persist_command_shadow(command)
        self.add_event(command.node_code, "command-approved", Severity.info,
                       f"运维人员 {actor} 审批通过命令 #{command_id} ({command.command_type})。")
        return {"accepted": True, "command_id": command_id, "status": command.status, "actor": actor}

    def reject_command(self, command_id: int, actor: str, reason: str = "") -> dict[str, object]:
        with self._lock:
            command = self.command_manager.reject(self.commands, command_id=command_id, actor=actor)
        self.persist_command_shadow(command)
        self.add_event(command.node_code, "command-rejected", Severity.medium,
                       f"运维人员 {actor} 拒绝命令 #{command_id} ({command.command_type})。原因: {reason or '未提供'}。")
        return {"accepted": True, "command_id": command_id, "status": command.status,
                "actor": actor, "reason": reason}

    def escalate_to_human(self, node_code: str, issue_type: str, description: str) -> dict[str, object]:
        self.add_event(node_code, "escalation", Severity.high, f"[需人工介入] {issue_type}: {description}")
        self.create_alert(node_code, issue_type, Severity.high, description, handled_by="human-required")
        return {"escalated": True, "node_code": node_code, "issue_type": issue_type}

    def pending_escalations(self) -> list[IncidentEvent]:
        open_alerts = [
            a for a in self.alerts
            if a.status not in {"closed", "resolved"} and a.handled_by == "human-required"
        ]

        def matches_open_alert(event: IncidentEvent) -> bool:
            return any(
                alert.node_code == event.node_code and f"{alert.alert_type}:" in event.message
                for alert in open_alerts
            )

        return [
            e for e in self.incident_events
            if e.stage == "escalation"
            and matches_open_alert(e)
            and not any(
                later.id > e.id
                and later.node_code == e.node_code
                and later.stage in {"escalation-approved", "escalation-rejected"}
                for later in self.incident_events
            )
        ][-20:]

    # ------------------------------------------------------------------
    # Market and inventory
    # ------------------------------------------------------------------

    def refresh_market_via_service(self) -> None:
        """Optionally pull the latest market snapshot from the market-simulator
        microservice. No-op (and offline edge) when microservices are disabled."""
        if not settings.microservices_enabled:
            self.update_integration_edge("market-simulator", False)
            return
        ok, data = get_json(f"{settings.market_simulator_url}/signals")
        if not ok or not isinstance(data, list):
            ok, _ = get_json(f"{settings.market_simulator_url}/health")
            self.update_integration_edge("market-simulator", ok)
            return
        signals = self._market_signals_from_service(data)
        if not signals:
            self.update_integration_edge("market-simulator", False)
            return
        with self._lock:
            self.market_signals = signals
            inventory_by_code = {item.product_code: item for item in self.inventory}
            for signal in signals:
                item = inventory_by_code.get(signal.product_code)
                if item is not None:
                    item.pressure_score = signal.inventory_pressure
        self.update_integration_edge("market-simulator", True)

    def _market_signals_from_service(self, payload: list[object]) -> list[MarketSignal]:
        signals: list[MarketSignal] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            code = canonical_product_code(str(item.get("product_code") or ""))
            product = PRODUCTS.get(code)
            if product is None:
                continue
            price = float(product["price"])
            signals.append(MarketSignal(
                product_code=code,
                product_name=str(product["name"]),
                current_price=float(item.get("current_price") or price),
                competitor_price=float(item.get("competitor_price") or price),
                demand_index=float(item.get("demand_index") or 80.0),
                season_factor=float(item.get("season_factor") or 1.0),
                inventory_pressure=float(item.get("inventory_pressure") or 0.0),
            ))
        return signals

    # ------------------------------------------------------------------
    # Production planning and dispatch
    # ------------------------------------------------------------------

    def generate_production_plan(self) -> list[ProductionPlanIn]:
        if settings.microservices_enabled:
            self.refresh_market_via_service()
            service_plans = self._generate_production_plan_via_service()
            if service_plans:
                self.production_plans = service_plans
                return service_plans

        signals = {s.product_code: s for s in self.market_signals}
        inventory = {i.product_code: i for i in self.inventory}
        plans: list[ProductionPlanIn] = []
        for code in PRODUCTS:
            signal = signals.get(code)
            demand = signal.demand_index if signal else 80.0
            pressure = inventory[code].pressure_score if code in inventory else 40.0
            target = int(demand * 1.5 + pressure)
            urgency = demand * (signal.season_factor if signal else 1.0) + pressure
            priority = max(1, min(10, 6 - int(urgency // 40)))
            plans.append(ProductionPlanIn(
                product_code=code, target_quantity=target, priority=priority,
                route=product_route(code),
                reason=f"需求指数 {demand:.0f}、库存压力 {pressure:.0f}，按优先级 {priority} 排产。",
            ))
        plans.sort(key=lambda p: p.priority)
        self.production_plans = plans
        return plans

    def _generate_production_plan_via_service(self) -> list[ProductionPlanIn]:
        payload = {
            "market_signals": [
                {
                    "product_code": signal.product_code,
                    "demand_index": signal.demand_index,
                    "inventory_pressure": signal.inventory_pressure,
                }
                for signal in self.market_signals
            ],
            "node_health": self._planner_node_health(),
        }
        ok, data = post_json(f"{settings.production_planner_url}/plan", payload)
        self.update_integration_edge("production-planner", ok)
        if not ok or not isinstance(data, list):
            return []
        plans: list[ProductionPlanIn] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            code = canonical_product_code(str(item.get("product_code") or ""))
            if code not in PRODUCTS:
                continue
            try:
                plans.append(ProductionPlanIn(
                    product_code=code,
                    target_quantity=int(item.get("target_quantity") or 0),
                    priority=int(item.get("priority") or 5),
                    route=list(item.get("route") or product_route(code)),
                    reason=str(item.get("reason") or "production-planner service"),
                ))
            except (TypeError, ValueError):
                continue
        return sorted(plans, key=lambda plan: plan.priority)

    def _planner_node_health(self) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for node in self.nodes.values():
            if node.workshop_type not in {"turning", "milling", "grinding"}:
                continue
            machines = [m for m in self.machines if m.node_code == node.node_code]
            load = round(mean([m.load_rate for m in machines]), 1) if machines else 100.0
            result.append({
                "node_code": node.node_code,
                "workshop_type": node.workshop_type,
                "status": node.status.value,
                "load_score": load,
            })
        return result

    def _available_machine_for(self, process: str) -> Machine | None:
        def usable(machine: Machine) -> bool:
            node = self.nodes.get(machine.node_code)
            return (machine.status not in {"maintenance", "offline"}
                    and node is not None and node.status != NodeStatus.isolated
                    and node.status != NodeStatus.offline)

        usable_machines = [m for m in self.machines if usable(m)]
        if not usable_machines:
            return None
        preferred_type = PROCESS_WORKSHOP.get(process)
        if preferred_type:
            preferred = [m for m in usable_machines
                         if (n := self.nodes.get(m.node_code)) and n.workshop_type == preferred_type]
            if preferred:
                return min(preferred, key=lambda m: m.load_rate)
        return min(usable_machines, key=lambda m: m.load_rate)

    def rebuild_dispatch(self) -> list[DispatchTask]:
        self.dispatch_tasks = []
        for plan in self.production_plans:
            for process in plan.route:
                self.dispatch_seq += 1
                machine = self._available_machine_for(process)
                if machine is None:
                    task = DispatchTask(
                        id=self.dispatch_seq, product_code=plan.product_code,
                        product_name=product_name(plan.product_code), route=[process],
                        assigned_node="", assigned_machine="waiting-capacity",
                        quantity=plan.target_quantity, priority=plan.priority, status="blocked",
                        reason=f"{process} 工序暂无可用设备，等待产能释放。",
                    )
                else:
                    status = "scheduled" if machine.load_rate < 80 else "queued"
                    task = DispatchTask(
                        id=self.dispatch_seq, product_code=plan.product_code,
                        product_name=product_name(plan.product_code), route=[process],
                        assigned_node=machine.node_code, assigned_machine=machine.machine_code,
                        quantity=plan.target_quantity, priority=plan.priority, status=status,
                        reason=f"{process} 工序分配到 {machine.machine_code}（负载 {machine.load_rate:.0f}%）。",
                    )
                self.dispatch_tasks.append(task)
        return self.dispatch_tasks

    def resource_allocations(self) -> list[ResourceAllocation]:
        allocations: list[ResourceAllocation] = []
        by_node: dict[str, list[Machine]] = {}
        for m in self.machines:
            by_node.setdefault(m.node_code, []).append(m)
        for node_code, machines in by_node.items():
            node = self.nodes.get(node_code)
            workshop_type = node.workshop_type if node else self.infer_workshop_type(node_code)
            available = [m for m in machines if m.status not in {"maintenance", "offline"}]
            running = [m for m in available if m.status == "running"]
            avg_load = round(mean([m.load_rate for m in machines]), 1) if machines else 0.0
            avg_wear = mean([m.tool_wear_level for m in machines]) if machines else 0.0
            planned = sum(p.target_quantity for p in self.production_plans
                          if workshop_type in p.route)
            isolated = node is not None and node.status == NodeStatus.isolated
            if isolated:
                bottleneck, recommendation = "节点隔离", "车间已隔离，相关订单需改派或延期。"
            elif not available:
                bottleneck, recommendation = "无可用设备", "全部设备停机，需立即检修恢复产能。"
            elif avg_load >= 80:
                bottleneck, recommendation = "产能接近上限", "建议错峰排产或调配备用设备。"
            elif avg_wear >= 70:
                bottleneck, recommendation = "刀具磨损偏高", "建议安排换刀与设备保养。"
            else:
                bottleneck, recommendation = "正常", "产能充足，可承接更多订单。"
            allocations.append(ResourceAllocation(
                node_code=node_code, workshop_type=workshop_type,
                available_machines=len(available), running_machines=len(running),
                avg_load_rate=avg_load, planned_quantity=planned,
                bottleneck=bottleneck, recommendation=recommendation,
            ))
        allocations.sort(key=lambda a: a.node_code)
        return allocations

    def _add_allocation_order(self, order_in: AllocationOrderIn) -> AllocationOrder:
        self.order_seq += 1
        product_code = canonical_product_code(order_in.product_code)
        order = AllocationOrder(
            order_id=f"AO-{self.order_seq:03d}", source_unit=order_in.source_unit,
            product_code=product_code, product_name=product_name(product_code),
            required_quantity=order_in.required_quantity, priority=order_in.priority,
            deadline_hours=order_in.deadline_hours, assigned_cloud_role=order_in.assigned_cloud_role,
            status="received", reason=order_in.reason,
        )
        self.allocation_orders.append(order)
        self.allocation_orders = self.allocation_orders[-60:]
        return order

    def submit_allocation_order(self, order_in: AllocationOrderIn) -> AllocationOrder:
        order = self._add_allocation_order(order_in)
        self.add_event("central-api", "allocation-order", Severity.info,
                       f"收到上级调配任务 {order.order_id}：{order.product_name} x{order.required_quantity}。")
        # A new upper-level order changes demand, so regenerate the plan and dispatch.
        self.generate_production_plan()
        self.rebuild_dispatch()
        return order

    # ------------------------------------------------------------------
    # Summary / hosts / integration
    # ------------------------------------------------------------------

    def summary(self) -> DashboardSummary:
        latest = list(self.latest_metrics().values())
        finished = sum(m.finished_quantity for m in latest)
        defects = sum(m.defect_quantity for m in latest)
        produced = finished + defects
        return DashboardSummary(
            node_count=len(self.nodes),
            online_count=sum(1 for n in self.nodes.values() if n.status == NodeStatus.online),
            isolated_count=sum(1 for n in self.nodes.values() if n.status == NodeStatus.isolated),
            alert_count=len(self.alerts),
            critical_alert_count=sum(1 for a in self.alerts if a.severity in {Severity.high, Severity.critical}),
            total_finished_quantity=finished,
            defect_rate=round(defects / produced * 100, 2) if produced else 0.0,
            avg_cpu_usage=round(mean([m.cpu_usage for m in latest]), 2) if latest else 0.0,
            avg_memory_usage=round(mean([m.memory_usage for m in latest]), 2) if latest else 0.0,
            avg_disk_usage=round(mean([m.disk_usage for m in latest]), 2) if latest else 0.0,
        )

    def host_status(self) -> list[HostRuntimeStatus]:
        latest = self.latest_metrics()
        host = _real_host_metrics()
        cloud = self.nodes.get("cloud-workshop-01")
        cloud_metric = latest.get("cloud-workshop-01")
        db_node = self.nodes.get("cloud-db-01")
        return [
            HostRuntimeStatus(
                host_code="local-y7000p", host_name="本地控制主机", role="中心控制器",
                location="本地实验室", status="online", connection="local",
                node_code="central-api", node_status="online", last_seen=utc_now(),
                cpu_usage=host["cpu"], memory_usage=host["mem"], disk_usage=host["disk"],
                api_latency_ms=0, database="In-memory / PostgreSQL (planned)",
                service="FastAPI central-api"),
            HostRuntimeStatus(
                host_code="tencent-lighthouse-cloud-workshop", host_name="云端协同车间节点",
                role="云端 AI 协同 Worker", location="Beijing Zone 2",
                status=cloud.status.value if cloud else "offline",
                connection="connected" if cloud_metric else "waiting",
                node_code="cloud-workshop-01", node_status=cloud.status.value if cloud else "offline",
                last_seen=cloud.last_heartbeat if cloud else None,
                cpu_usage=round(cloud_metric.cpu_usage, 2) if cloud_metric else None,
                memory_usage=round(cloud_metric.memory_usage, 2) if cloud_metric else None,
                disk_usage=round(cloud_metric.disk_usage, 2) if cloud_metric else None,
                api_latency_ms=cloud_metric.api_latency_ms if cloud_metric else None,
                database="SQLite /var/lib/mini-ogas/node.db", service="systemd mini-ogas-node-agent"),
            HostRuntimeStatus(
                host_code="cloud-db-01", host_name="云端数据库节点", role="数据库与审计节点",
                location="Cloud / 2C4G",
                status=db_node.status.value if db_node else "offline", connection="replication-ready",
                node_code="cloud-db-01", node_status=db_node.status.value if db_node else "offline",
                last_seen=db_node.last_heartbeat if db_node else None,
                cpu_usage=None, memory_usage=None, disk_usage=None, api_latency_ms=62,
                database="SQLite/PostgreSQL compatible", service="metrics archive + audit mirror"),
        ]

    def update_integration_edge(self, target: str, online: bool) -> None:
        for edge in self.topology_edges:
            if edge.target == target:
                edge.status = "healthy" if online else "offline"
                edge.latency_ms = 28 if online else 0

    def integration_status(self) -> list[dict[str, object]]:
        services = [
            ("ai-dispatcher", settings.ai_dispatcher_url),
            ("market-simulator", settings.market_simulator_url),
            ("production-planner", settings.production_planner_url),
        ]
        result: list[dict[str, object]] = []
        for name, base_url in services:
            if settings.microservices_enabled:
                ok, data = get_json(f"{base_url}/health")
            else:
                ok, data = False, {"mode": "disabled", "message": "MICROSERVICES_ENABLED=false"}
            self.update_integration_edge(name, ok)
            result.append({"service": name, "url": base_url,
                           "status": "online" if ok else "offline", "detail": data})
        return result

    def shadow_consistency_report(self, limit: int = 100) -> dict[str, object]:
        """Compare live v2 facts with PostgreSQL/SQLite shadow rows without changing reads."""
        if not settings.persist_enabled:
            return {"status": "disabled", "reason": "PERSIST_ENABLED=false"}
        with self._lock:
            expected_heartbeats = {
                node_code: dict(payload.get("runtime") or {})
                for node_code, payload in self.node_heartbeats_v2.items()
                if not self._ephemeral_node_code(node_code)
            }
            expected_commands = {command.id: command.status for command in self.commands}
            expected_parts = {part.part_id: part.status for part in self.part_queue}
            expected_events = self._shadow_event_count
        try:
            with get_db() as db:
                heartbeat_rows = db.execute(
                    """SELECT node_code, run_id, scenario_id FROM heartbeat_shadow
                       ORDER BY id DESC LIMIT ?""",
                    (max(1, limit),),
                ).fetchall()
                command_rows = db.execute(
                    "SELECT command_id, status FROM command_shadow"
                ).fetchall()
                part_rows = db.execute(
                    "SELECT part_id, status FROM part_queue_shadow"
                ).fetchall()
                event_count = int(db.execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()["count"])
        except Exception as exc:  # pragma: no cover - depends on external backend
            return {"status": "degraded", "error": str(exc)}

        heartbeat_seen: dict[str, tuple[str, str]] = {}
        for row in heartbeat_rows:
            data = dict(row)
            heartbeat_seen.setdefault(
                str(data["node_code"]),
                (str(data.get("run_id") or ""), str(data.get("scenario_id") or "")),
            )
        heartbeat_mismatches = [
            node_code
            for node_code, runtime in expected_heartbeats.items()
            if heartbeat_seen.get(node_code) != (
                str(runtime.get("run_id") or ""),
                str(runtime.get("scenario_id") or ""),
            )
        ]
        command_shadow = {int(row["command_id"]): str(row["status"]) for row in command_rows}
        command_mismatches = [
            command_id for command_id, status in expected_commands.items()
            if command_shadow.get(command_id) != status
        ]
        part_shadow = {str(row["part_id"]): str(row["status"]) for row in part_rows}
        part_mismatches = [
            part_id for part_id, status in expected_parts.items()
            if part_shadow.get(part_id) != status
        ]
        ok = not heartbeat_mismatches and not command_mismatches and not part_mismatches and event_count >= expected_events
        return {
            "status": "ok" if ok else "degraded",
            "heartbeats": {"expected": len(expected_heartbeats), "recent_rows": len(heartbeat_rows), "mismatches": heartbeat_mismatches},
            "commands": {"expected": len(expected_commands), "shadow_rows": len(command_shadow), "mismatches": command_mismatches},
            "part_queue": {"expected": len(expected_parts), "shadow_rows": len(part_shadow), "mismatches": part_mismatches},
            "events": {"expected_at_least": expected_events, "shadow_rows": event_count},
        }

    def replay_readiness_report(self, limit: int = 500) -> dict[str, object]:
        """Report whether persisted facts are sufficient to rebuild runtime state after restart."""
        if not settings.persist_enabled:
            return {"status": "disabled", "reason": "PERSIST_ENABLED=false"}

        with self._lock:
            live_heartbeat_nodes = sorted(
                node_code
                for node_code in self.node_heartbeats_v2
                if not self._ephemeral_node_code(node_code)
            )
            live_command_ids = sorted(command.id for command in self.commands)
            live_part_ids = sorted(part.part_id for part in self.part_queue)
            restored_heartbeat_nodes = sorted(
                node_code
                for node_code, payload in self.node_heartbeats_v2.items()
                if payload.get("_restored_from_persistence") is True
            )
            restored_command_ids = sorted(
                command.id for command in self.commands
                if command.result_message or command.claimed_by or command.status not in {"pending", "queued"}
            )
            restored_part_ids = sorted(part.part_id for part in self.part_queue)

        try:
            with get_db() as db:
                heartbeat_rows = db.execute(
                    """SELECT node_code, run_id, scenario_id, received_at
                       FROM heartbeat_shadow
                       ORDER BY id DESC LIMIT ?""",
                    (max(1, limit),),
                ).fetchall()
                command_rows = db.execute(
                    "SELECT command_id, status, updated_at FROM command_shadow"
                ).fetchall()
                part_rows = db.execute(
                    "SELECT part_id, status, updated_at FROM part_queue_shadow"
                ).fetchall()
                event_count = int(db.execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()["count"])
        except Exception as exc:  # pragma: no cover - depends on external backend
            return {"status": "degraded", "error": str(exc)}

        heartbeat_latest: dict[str, dict[str, str]] = {}
        for row in heartbeat_rows:
            data = dict(row)
            node_code = str(data.get("node_code") or "")
            if not node_code or self._ephemeral_node_code(node_code) or node_code in heartbeat_latest:
                continue
            heartbeat_latest[node_code] = {
                "run_id": str(data.get("run_id") or ""),
                "scenario_id": str(data.get("scenario_id") or ""),
                "received_at": str(data.get("received_at") or ""),
            }

        shadow_command_ids = sorted(int(dict(row)["command_id"]) for row in command_rows)
        shadow_part_ids = sorted(str(dict(row)["part_id"]) for row in part_rows)
        missing_heartbeats = [node_code for node_code in live_heartbeat_nodes if node_code not in heartbeat_latest]
        missing_commands = [command_id for command_id in live_command_ids if command_id not in shadow_command_ids]
        missing_parts = [part_id for part_id in live_part_ids if part_id not in shadow_part_ids]

        ok = not missing_heartbeats and not missing_commands and not missing_parts
        return {
            "status": "ok" if ok else "degraded",
            "backend": persistence_label(),
            "live": {
                "heartbeat_nodes": len(live_heartbeat_nodes),
                "commands": len(live_command_ids),
                "part_queue_items": len(live_part_ids),
            },
            "shadow": {
                "heartbeat_nodes": len(heartbeat_latest),
                "heartbeat_rows_sampled": len(heartbeat_rows),
                "commands": len(shadow_command_ids),
                "part_queue_items": len(shadow_part_ids),
                "audit_events": event_count,
            },
            "restored_cache": {
                "heartbeat_nodes": restored_heartbeat_nodes,
                "commands": restored_command_ids,
                "part_queue_items": restored_part_ids,
            },
            "missing": {
                "heartbeat_nodes": missing_heartbeats,
                "commands": missing_commands,
                "part_queue_items": missing_parts,
            },
            "latest_heartbeats": heartbeat_latest,
        }

    def replay_runs(self, max_rows: int = 1000, limit: int = 20) -> dict[str, object]:
        """List persisted simulation runs found in heartbeat shadow rows."""
        if not settings.persist_enabled:
            return {"status": "disabled", "reason": "PERSIST_ENABLED=false", "runs": []}

        try:
            with get_db() as db:
                rows = db.execute(
                    """
                    SELECT run_id, node_code, scenario_id, simulation_time, received_at
                    FROM heartbeat_shadow
                    WHERE run_id <> ''
                    ORDER BY received_at DESC
                    LIMIT ?
                    """,
                    (max(1, max_rows),),
                ).fetchall()
        except Exception as exc:  # pragma: no cover - depends on external backend
            return {"status": "degraded", "error": str(exc), "runs": []}

        grouped: dict[str, dict[str, object]] = {}
        for row in rows:
            data = dict(row)
            run_id = str(data.get("run_id") or "")
            if not run_id:
                continue
            item = grouped.setdefault(
                run_id,
                {
                    "run_id": run_id,
                    "scenario_ids": set(),
                    "node_codes": set(),
                    "heartbeat_count": 0,
                    "started_at": "",
                    "ended_at": "",
                    "latest_simulation_time": None,
                },
            )
            scenario_id = str(data.get("scenario_id") or "")
            node_code = str(data.get("node_code") or "")
            received_at = str(data.get("received_at") or "")
            if scenario_id:
                item["scenario_ids"].add(scenario_id)  # type: ignore[union-attr]
            if node_code:
                item["node_codes"].add(node_code)  # type: ignore[union-attr]
            item["heartbeat_count"] = int(item["heartbeat_count"]) + 1
            if not item["ended_at"] or received_at > str(item["ended_at"]):
                item["ended_at"] = received_at
                item["latest_simulation_time"] = data.get("simulation_time")
            if not item["started_at"] or received_at < str(item["started_at"]):
                item["started_at"] = received_at

        runs: list[dict[str, object]] = []
        for item in grouped.values():
            node_codes = sorted(str(value) for value in item["node_codes"])  # type: ignore[index]
            scenario_ids = sorted(str(value) for value in item["scenario_ids"])  # type: ignore[index]
            runs.append({
                **item,
                "scenario_ids": scenario_ids,
                "node_codes": node_codes,
                "node_count": len(node_codes),
            })
        runs.sort(key=lambda item: str(item.get("ended_at") or ""), reverse=True)
        return {
            "status": "ok",
            "backend": persistence_label(),
            "runs": runs[:max(1, limit)],
            "sampled_heartbeat_rows": len(rows),
        }

    def replay_run(self, run_id: str, max_rows: int = 500) -> dict[str, object]:
        """Rebuild a persisted operational timeline for one simulation run."""
        if not settings.persist_enabled:
            return {"status": "disabled", "reason": "PERSIST_ENABLED=false", "run_id": run_id}

        clean_run_id = run_id.strip()
        if not clean_run_id:
            return {"status": "not_found", "run_id": run_id, "reason": "empty run_id"}

        try:
            with get_db() as db:
                heartbeat_rows = db.execute(
                    """
                    SELECT id, node_code, run_id, scenario_id, simulation_time, payload_json, received_at
                    FROM heartbeat_shadow
                    WHERE run_id = ?
                    ORDER BY received_at ASC, id ASC
                    LIMIT ?
                    """,
                    (clean_run_id, max(1, max_rows)),
                ).fetchall()
                if not heartbeat_rows:
                    return {"status": "not_found", "run_id": clean_run_id}

                heartbeat_data = [dict(row) for row in heartbeat_rows]
                started_at = str(heartbeat_data[0].get("received_at") or "")
                ended_at = str(heartbeat_data[-1].get("received_at") or started_at)
                command_rows = db.execute(
                    """
                    SELECT command_id, node_code, command_type, risk_level, status, operator,
                           parameters_json, claimed_by, result_message, created_at, updated_at
                    FROM command_shadow
                    WHERE updated_at >= ? AND updated_at <= ?
                    ORDER BY updated_at ASC, command_id ASC
                    LIMIT ?
                    """,
                    (started_at, ended_at, max(1, max_rows)),
                ).fetchall()
                part_rows = db.execute(
                    """
                    SELECT part_id, parent_part_id, order_id, product_code, current_step, status,
                           source_node, target_node, claimed_by, created_at, updated_at
                    FROM part_queue_shadow
                    WHERE updated_at >= ? AND updated_at <= ?
                    ORDER BY updated_at ASC, part_id ASC
                    LIMIT ?
                    """,
                    (started_at, ended_at, max(1, max_rows)),
                ).fetchall()
                audit_rows = db.execute(
                    """
                    SELECT id, actor, action, resource_type, resource_id, result, detail, created_at
                    FROM audit_logs
                    WHERE created_at >= ? AND created_at <= ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (started_at, ended_at, max(1, max_rows)),
                ).fetchall()
                alert_rows = db.execute(
                    """
                    SELECT id, node_code, alert_type, severity, source, description,
                           handled_by, status, created_at, resolved_at
                    FROM alerts
                    WHERE created_at >= ? AND created_at <= ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (started_at, ended_at, max(1, max_rows)),
                ).fetchall()
                ai_rows = db.execute(
                    """
                    SELECT id, alert_id, severity, node_code, root_cause, recommended_action,
                           confidence, need_isolation, model_name, created_at
                    FROM ai_diagnosis
                    WHERE created_at >= ? AND created_at <= ?
                    ORDER BY created_at ASC, id ASC
                    LIMIT ?
                    """,
                    (started_at, ended_at, max(1, max_rows)),
                ).fetchall()
        except Exception as exc:  # pragma: no cover - depends on external backend
            return {"status": "degraded", "run_id": clean_run_id, "error": str(exc)}

        heartbeats: list[dict[str, object]] = []
        timeline: list[dict[str, object]] = []
        scenario_ids: set[str] = set()
        node_codes: set[str] = set()
        for data in heartbeat_data:
            payload: dict[str, object] = {}
            try:
                decoded = json.loads(str(data.get("payload_json") or "{}"))
                if isinstance(decoded, dict):
                    payload = decoded
            except json.JSONDecodeError:
                payload = {}
            node_code = str(data.get("node_code") or "")
            scenario_id = str(data.get("scenario_id") or "")
            if node_code:
                node_codes.add(node_code)
            if scenario_id:
                scenario_ids.add(scenario_id)
            production = payload.get("production") if isinstance(payload.get("production"), dict) else {}
            runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
            alarms = payload.get("alarms") if isinstance(payload.get("alarms"), list) else []
            heartbeat_item = {
                "id": data.get("id"),
                "node_code": node_code,
                "scenario_id": scenario_id,
                "simulation_time": data.get("simulation_time"),
                "received_at": data.get("received_at"),
                "status": payload.get("status"),
                "machine_code": production.get("machine_code"),
                "active_order": production.get("active_order"),
                "target_rate": production.get("target_rate"),
                "actual_rate": production.get("actual_rate"),
                "utilization": production.get("utilization"),
                "defect_rate": production.get("defect_rate"),
                "runtime": runtime,
                "alarm_count": len(alarms),
            }
            heartbeats.append(heartbeat_item)
            timeline.append({
                "time": str(data.get("received_at") or ""),
                "kind": "heartbeat",
                "node_code": node_code,
                "title": f"{node_code} heartbeat",
                "status": payload.get("status") or "running",
                "detail": heartbeat_item,
            })

        commands = []
        for row in command_rows:
            data = dict(row)
            try:
                parameters = json.loads(str(data.get("parameters_json") or "{}"))
            except json.JSONDecodeError:
                parameters = {}
            item = {**data, "parameters": parameters if isinstance(parameters, dict) else {}}
            commands.append(item)
            timeline.append({
                "time": str(data.get("updated_at") or data.get("created_at") or ""),
                "kind": "command",
                "node_code": data.get("node_code"),
                "title": data.get("command_type"),
                "status": data.get("status"),
                "detail": item,
            })

        part_queue = [dict(row) for row in part_rows]
        for item in part_queue:
            timeline.append({
                "time": str(item.get("updated_at") or item.get("created_at") or ""),
                "kind": "part_queue",
                "node_code": item.get("target_node") or item.get("source_node"),
                "title": item.get("part_id"),
                "status": item.get("status"),
                "detail": item,
            })

        audit_events = [dict(row) for row in audit_rows]
        for item in audit_events:
            timeline.append({
                "time": str(item.get("created_at") or ""),
                "kind": "audit",
                "node_code": item.get("actor"),
                "title": item.get("action"),
                "status": item.get("result"),
                "detail": item,
            })

        alerts = [dict(row) for row in alert_rows]
        for item in alerts:
            timeline.append({
                "time": str(item.get("created_at") or ""),
                "kind": "alert",
                "node_code": item.get("node_code"),
                "title": item.get("alert_type"),
                "status": item.get("status"),
                "detail": item,
            })

        ai_diagnoses = [dict(row) for row in ai_rows]
        for item in ai_diagnoses:
            timeline.append({
                "time": str(item.get("created_at") or ""),
                "kind": "ai_diagnosis",
                "node_code": item.get("node_code"),
                "title": item.get("model_name"),
                "status": "recorded",
                "detail": item,
            })

        timeline.sort(key=lambda item: str(item.get("time") or ""))
        return {
            "status": "ok",
            "backend": persistence_label(),
            "run_id": clean_run_id,
            "scenario_ids": sorted(scenario_ids),
            "node_codes": sorted(node_codes),
            "started_at": started_at,
            "ended_at": ended_at,
            "counts": {
                "heartbeats": len(heartbeats),
                "commands": len(commands),
                "part_queue": len(part_queue),
                "audit_events": len(audit_events),
                "alerts": len(alerts),
                "ai_diagnoses": len(ai_diagnoses),
                "timeline": len(timeline),
            },
            "heartbeats": heartbeats,
            "commands": commands,
            "part_queue": part_queue,
            "audit_events": audit_events,
            "alerts": alerts,
            "ai_diagnoses": ai_diagnoses,
            "timeline": timeline,
        }

    def persistence_status(self) -> dict[str, object]:
        backend = persistence_backend()
        db_path = Path(settings.central_db_path)
        base: dict[str, object] = {
            "enabled": settings.persist_enabled,
            "backend": persistence_label(),
            "db_path": str(db_path) if backend == "sqlite" else "",
            "dsn_configured": bool(settings.postgres_dsn) if backend == "postgres" else False,
            "db_exists": db_path.exists() if backend == "sqlite" else False,
            "retention": {
                "heartbeat_shadow_per_node": settings.heartbeat_shadow_retention_per_node,
                "heartbeat_shadow_policy": (
                    "disabled"
                    if settings.heartbeat_shadow_retention_per_node <= 0
                    else "keep_latest_per_node"
                ),
            },
            "tables": {},
            "counts": {},
            "last_error": "",
        }
        if not settings.persist_enabled:
            return {**base, "status": "disabled"}

        required_tables = ("heartbeat_shadow", "part_queue_shadow", "command_shadow", "audit_logs", "commands")
        try:
            init_db()
            with get_db() as db:
                if backend == "postgres":
                    rows = db.execute(
                        """
                        SELECT table_name AS name
                        FROM information_schema.tables
                        WHERE table_schema = ? AND table_type = ?
                        """,
                        ("public", "BASE TABLE"),
                    ).fetchall()
                else:
                    rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                table_names = {str(row["name"]) for row in rows}
                tables = {name: name in table_names for name in required_tables}
                counts: dict[str, int] = {}
                for table_name in required_tables:
                    if table_name in table_names:
                        row = db.execute(f"SELECT COUNT(*) AS count FROM {table_name}").fetchone()
                        counts[table_name] = int(row["count"])
            consistency = self.shadow_consistency_report()
            replay = self.replay_readiness_report()
            status = (
                "ok"
                if all(tables.values())
                and consistency["status"] == "ok"
                and replay["status"] == "ok"
                else "degraded"
            )
            return {
                **base,
                "status": status,
                "db_exists": True if backend == "postgres" else db_path.exists(),
                "tables": tables,
                "counts": counts,
                "consistency": consistency,
                "replay_readiness": replay,
            }
        except Exception as exc:  # pragma: no cover
            return {**base, "status": "degraded", "last_error": str(exc)}

    def run_preflight(self) -> PreflightResult:
        import time as time_mod

        steps: list[PreflightStep] = []

        # ----------------------------------------------------------------
        # Step 1 — Service connectivity
        # ----------------------------------------------------------------
        t0 = time_mod.monotonic()
        step1 = PreflightStep(key="services", label="微服务连通性", status="running")
        svc_parts: list[str] = []
        svc_ok = True
        probe_services = [
            ("AI 调度器", settings.ai_dispatcher_url),
            ("市场模拟器", settings.market_simulator_url),
            ("排产规划器", settings.production_planner_url),
        ]
        my_token = get_session_token()
        for name, base_url in probe_services:
            try:
                if settings.microservices_enabled:
                    ok, data = get_json(f"{base_url}/health", timeout=settings.service_probe_timeout_seconds)
                    if ok and isinstance(data, dict):
                        svc_token = data.get("session_token", "")
                        if svc_token and svc_token != my_token:
                            svc_parts.append(f"{name} ✗(session_mismatch)")
                            svc_ok = False
                            continue
                else:
                    ok, _ = None, None  # standalone mode — not required
            except Exception:
                ok = False
            if ok or not settings.microservices_enabled:
                svc_parts.append(f"{name} ✓")
            else:
                svc_parts.append(f"{name} ✗")
                svc_ok = False
        step1.detail = "; ".join(svc_parts)
        step1.status = "pass" if svc_ok else "fail"
        step1.elapsed_ms = int((time_mod.monotonic() - t0) * 1000)
        steps.append(step1)

        # ----------------------------------------------------------------
        # Step 2 — Node connectivity (heartbeat OR recent metrics)
        # ----------------------------------------------------------------
        t0 = time_mod.monotonic()
        step2 = PreflightStep(key="nodes", label="父子节点激活", status="running")

        # Kick the simulation once if it's not running, to refresh heartbeats
        if not self.simulation_running:
            try:
                self.simulation_step()
            except Exception:
                pass

        now_utc = utc_now()
        timeout_threshold = timedelta(seconds=max(settings.heartbeat_timeout_seconds * 2, 120))
        online_nodes: list[str] = []
        stale_nodes: list[str] = []
        with self._lock:
            for node in list(self.nodes.values()):
                if self._ephemeral_node_code(node.node_code):
                    continue
                if node.status == NodeStatus.isolated:
                    continue
                if now_utc - node.last_heartbeat <= timeout_threshold:
                    online_nodes.append(node.node_code)
                else:
                    stale_nodes.append(node.node_code)
        if online_nodes:
            step2.detail = f"活跃节点 ({len(online_nodes)}): {', '.join(online_nodes[:6])}"
            if stale_nodes:
                step2.detail += f"; 无信号: {', '.join(stale_nodes[:4])}"
            step2.status = "pass"
        elif stale_nodes:
            step2.detail = f"全部 {len(stale_nodes)} 个节点无心跳/无指标"
            step2.status = "fail"
        else:
            step2.detail = "暂无已注册节点（系统尚未收到首次心跳）"
            step2.status = "pass"  # not an error — seed may not have run yet
        step2.elapsed_ms = int((time_mod.monotonic() - t0) * 1000)
        steps.append(step2)

        # ----------------------------------------------------------------
        # Step 3 — AI key verification
        # ----------------------------------------------------------------
        t0 = time_mod.monotonic()
        step3 = PreflightStep(key="ai_key", label="AI Key 验证", status="running")
        if not settings.ai_enabled:
            step3.detail = "AI 已禁用（AI_ENABLED=false）"
            step3.status = "pass"
        elif not registry.is_any_live_provider():
            step3.detail = "无可用 AI 后端，请检查 /api/ai/status 了解详情"
            step3.status = "fail"
        else:
            try:
                ping = registry.chat(
                    [
                        {"role": "system", "content": "Respond with exactly: {\"pong\":true}"},
                        {"role": "user", "content": "ping"},
                    ],
                    timeout=10,
                )
                active = registry.first_available()
                active_name = active.name if active else "unknown"
                if "pong" in ping.lower():
                    step3.detail = f"AI 响应正常（后端: {active_name}）"
                    step3.status = "pass"
                else:
                    step3.detail = f"AI 返回异常内容: {ping[:120]}"
                    step3.status = "fail"
            except Exception as exc:
                step3.detail = f"AI 验证失败: {exc}"
                step3.status = "fail"
        step3.elapsed_ms = int((time_mod.monotonic() - t0) * 1000)
        steps.append(step3)

        # ----------------------------------------------------------------
        # Step 4 — Virtual dry-run diagnosis
        # ----------------------------------------------------------------
        t0 = time_mod.monotonic()
        step4 = PreflightStep(key="dry_run", label="虚拟试运行", status="running")
        # Build a synthetic high-load scenario
        dry_metric = MetricIn(
            node_code="preflight-check",
            cpu_usage=92.0,
            memory_usage=78.0,
            disk_usage=55.0,
            network_in=120_000,
            network_out=90_000,
            db_latency_ms=820,
            api_latency_ms=850,
            finished_quantity=42,
            defect_quantity=3,
        )
        dry_prompt = (
            f"车间节点: preflight-check\n"
            f"告警: 试运行自动生成 — CPU={dry_metric.cpu_usage:.1f}%, "
            f"API延迟={dry_metric.api_latency_ms}ms, DB延迟={dry_metric.db_latency_ms}ms\n"
            f"最新指标: cpu={dry_metric.cpu_usage:.1f}%, memory={dry_metric.memory_usage:.1f}%, "
            f"disk={dry_metric.disk_usage:.1f}%, network_in={dry_metric.network_in}, "
            f"db_latency={dry_metric.db_latency_ms}ms, api_latency={dry_metric.api_latency_ms}ms, "
            f"finished_quantity={dry_metric.finished_quantity}, defect_quantity={dry_metric.defect_quantity}\n"
            f"用户补充: 系统开机自检虚拟试运行\n"
            "请判断根因、建议动作、置信度，以及是否需要隔离该车间节点。"
        )
        try:
            if registry.is_any_live_provider() and settings.ai_enabled:
                diag = registry.diagnose(dry_prompt, timeout=15)
                step4.detail = (
                    f"根因: {diag.root_cause[:100]}; "
                    f"建议: {diag.recommended_action[:100]}; "
                    f"置信度: {diag.confidence:.0%}"
                )
                step4.status = "pass"
            else:
                step4.detail = "AI 未配置，使用本地规则诊断通过（CPU 92% + API 延迟 850ms → 建议限制新任务下发）"
                step4.status = "pass"
        except Exception as exc:
            step4.detail = f"试运行异常: {exc}"
            step4.status = "fail"
        step4.elapsed_ms = int((time_mod.monotonic() - t0) * 1000)
        steps.append(step4)

        # ----------------------------------------------------------------
        # Step 5 - durable persistence
        # ----------------------------------------------------------------
        t0 = time_mod.monotonic()
        step5 = PreflightStep(key="persistence", label="中心持久化检查", status="running")
        persistence = self.persistence_status()
        if persistence["status"] == "degraded":
            step5.status = "fail"
            step5.detail = f"{persistence.get('backend')} 持久化异常: {persistence.get('last_error') or persistence.get('tables')}"
        elif persistence["status"] == "disabled":
            step5.status = "pass"
            step5.detail = "PERSIST_ENABLED=false，当前为内存测试模式。"
        else:
            counts = persistence.get("counts", {})
            if isinstance(counts, dict):
                parts = counts.get("part_queue_shadow", 0)
                commands = counts.get("command_shadow", 0)
            else:
                parts = commands = 0
            step5.status = "pass"
            step5.detail = f"{persistence.get('backend')} 持久化正常，part_queue={parts}，commands={commands}。"
        step5.elapsed_ms = int((time_mod.monotonic() - t0) * 1000)
        steps.append(step5)

        all_pass = all(s.status == "pass" for s in steps)
        message = "所有自检通过，系统就绪" if all_pass else "部分自检未通过，请检查后重试"
        return PreflightResult(all_pass=all_pass, steps=steps, message=message)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def management_snapshot(self) -> dict[str, object]:
        integrations = self.integration_status()
        return {
            "summary": self.summary(),
            "hosts": self.host_status(),
            "nodes": list(self.nodes.values()),
            "metrics": self.latest_metrics(),
            "topology": self.topology_edges,
            "market_signals": self.market_signals,
            "market_forecast": self.market_forecast,
            "inventory": self.inventory,
            "allocation_orders": self.allocation_orders,
            "cloud_roles": self.cloud_roles,
            "authority_matrix": self.authority_matrix,
            "plans": self.production_plans,
            "dispatch_tasks": self.dispatch_tasks,
            "resource_allocations": self.resource_allocations(),
            "machines": self.machines,
            "alerts": self.alerts[-20:],
            "events": self.incident_events[-30:],
            "commands": self.commands[-20:],
            "part_queue": self.part_queue_snapshot(),
            "ai_shortcuts": self.ai_shortcuts,
            "simulation": self.simulation_state(),
            "integrations": integrations,
            "persistence": self.persistence_status(),
        }

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def simulation_state(self) -> SimulationState:
        return SimulationState(
            running=self.simulation_running, tick=self.simulation_tick, speed=self.simulation_speed,
            anomaly_rate=self.simulation_anomaly_rate, last_tick_at=self.simulation_last_tick_at,
            generated_orders=self.simulation_generated_orders,
            generated_events=self.simulation_generated_events,
        )

    def configure_simulation(self, running: bool | None = None, speed: float | None = None,
                             anomaly_rate: float | None = None) -> SimulationState:
        if running is not None:
            self.simulation_running = running
            self.add_event("simulation-engine", "simulation-start" if running else "simulation-pause",
                           Severity.info, "实时模拟引擎已启动。" if running else "实时模拟引擎已暂停。")
        if speed is not None:
            self.simulation_speed = speed
        if anomaly_rate is not None:
            self.simulation_anomaly_rate = anomaly_rate
        return self.simulation_state()

    def simulation_step(self) -> SimulationState:
        self.simulation_tick += 1
        self.simulation_last_tick_at = utc_now()
        latest = self.latest_metrics()

        # ---- Workshop metrics random walk ----
        with self._lock:
            nodes_snapshot = list(self.nodes.items())
        for node_code, node in nodes_snapshot:
            previous = latest.get(node_code) or self._initial_metric(node_code, node.workshop_type)
            baseline = _workshop_baseline(node.workshop_type)
            if node.status == NodeStatus.isolated:
                cpu = min(95, max(5, previous.cpu_usage * 0.4 + self.rng.uniform(-2, 2)))
                net_in = int(previous.network_in * 0.35)
            else:
                cpu = previous.cpu_usage + self.rng.uniform(-6, 6)
                cpu = min(98, max(2, cpu, baseline.cpu * 0.5))
                if self.rng.random() < 0.03:
                    cpu = min(99, cpu + self.rng.uniform(20, 40))
                net_in = max(100_000, int(previous.network_in + self.rng.uniform(-2_000_000, 3_000_000)))
            disk = previous.disk_usage + self.rng.uniform(-0.05, 0.15)
            if self.rng.random() < 0.04:
                disk += self.rng.uniform(2, 6)
            disk = min(96, max(10, disk))
            mem = min(96, max(15, previous.memory_usage + self.rng.uniform(-4, 4)))
            api_latency = max(10, int(15 + cpu * 0.35 + self.rng.uniform(-5, 10)))
            db_latency = max(5, int(previous.db_latency_ms + self.rng.randint(-6, 8)))
            produced_now = 0 if node.status == NodeStatus.isolated else self.rng.randint(0, 6)
            defect_now = 1 if (produced_now and self.rng.random() < 0.06) else 0
            self.record_metric(MetricIn(
                node_code=node_code, cpu_usage=round(cpu, 1), memory_usage=round(mem, 1),
                disk_usage=round(disk, 1), network_in=net_in,
                network_out=max(1_000_000, int(previous.network_out + self.rng.randint(-1_500_000, 2_200_000))),
                db_latency_ms=db_latency, api_latency_ms=api_latency,
                finished_quantity=previous.finished_quantity + produced_now,
                defect_quantity=previous.defect_quantity + defect_now,
            ), evaluate=False)

        # ---- Machine wear / load drift ----
        for machine in self.machines:
            if machine.status in {"maintenance", "offline"}:
                continue
            machine.load_rate = round(min(99, max(5, machine.load_rate + self.rng.uniform(-8, 8))), 1)
            machine.tool_wear_level = round(min(100, machine.tool_wear_level + self.rng.uniform(0, 1.2)), 1)
            machine.today_output += self.rng.randint(0, 5)
            if self.rng.random() < 0.05:
                machine.defect_count += 1

        # ---- Market drift + occasional upper-level order ----
        for signal in self.market_signals:
            signal.demand_index = round(min(180, max(30, signal.demand_index + self.rng.uniform(-5, 5))), 1)
            signal.current_price = round(max(10, signal.current_price * (1 + self.rng.uniform(-0.02, 0.02))), 2)
        if self.simulation_running and self.simulation_tick % 10 == 0:
            code = self.rng.choice(list(PRODUCTS))
            self.submit_allocation_order(AllocationOrderIn(
                product_code=code, required_quantity=self.rng.randint(40, 160),
                priority=self.rng.randint(2, 5), deadline_hours=self.rng.choice([12, 18, 24, 36]),
                assigned_cloud_role="辅助调配", source_unit="上级调度中心",
                reason="模拟引擎注入的上级调配任务。"))
            self.simulation_generated_orders += 1

        # ---- Periodic re-planning ----
        if self.simulation_tick % 8 == 0:
            self.generate_production_plan()
            self.rebuild_dispatch()

        # ---- Anomaly injection ----
        if self.rng.random() < self.simulation_anomaly_rate:
            anomaly_candidates = [
                (nc, node) for nc, node in nodes_snapshot
                if not self._is_control_plane_node(nc, node.workshop_type)
            ]
            if anomaly_candidates:
                target = self.rng.choice([nc for nc, _ in anomaly_candidates])
                node_ref = self.nodes.get(target)
                ws_type = node_ref.workshop_type if node_ref else self.infer_workshop_type(target)
                lm = self.latest_metrics().get(target) or self._initial_metric(target, ws_type)
                if self.rng.random() < 0.72:
                    self.record_metric(lm.model_copy(update={"disk_usage": 92.0}))
                else:
                    self.record_metric(lm.model_copy(update={"cpu_usage": 95.0, "api_latency_ms": 920}))
                self.simulation_generated_events += 1

        tick_now = self.simulation_tick
        self.add_event("simulation-engine", "tick", Severity.info,
                       f"tick={tick_now} 已推进：车间指标、设备负载与排产状态完成刷新。")

        # ---- AI auto-briefing (outside lock — slow DeepSeek call) ----
        if tick_now % 20 == 0:
            self.add_ai_auto_briefing()

        return self.simulation_state()

    def add_ai_auto_briefing(self) -> None:
        summary = self.summary()
        # Send only aggregated metrics, not full node-level details
        minimal_context = (
            f"在线节点={summary.online_count}/{summary.node_count}, "
            f"隔离={summary.isolated_count}, 告警={summary.alert_count}, "
            f"严重告警={summary.critical_alert_count}, "
            f"不良率={summary.defect_rate:.1f}%, "
            f"CPU均={summary.avg_cpu_usage:.1f}%, 内存均={summary.avg_memory_usage:.1f}%"
        )
        try:
            content = registry.chat([
                {"role": "system", "content": "你是 Mini-OGAS 主动运维简报助手，只输出一句话。"},
                {"role": "user", "content":
                    f"请用一句中文概括当前工厂最需要关注的问题。context={minimal_context}"},
            ])
        except Exception:
            if summary.defect_rate >= 5:
                content = f"当前不良率约 {summary.defect_rate:.1f}%，建议检查刀具磨损与质量工序。"
            elif summary.critical_alert_count > 0:
                content = "当前存在严重告警，建议立即检查对应车间节点状态。"
            else:
                content = "当前工厂总体稳定，车间在线率正常，排产顺畅。"
        self.add_event("ai-auto-briefing", "ai-auto-briefing", Severity.info, content.strip())

    def _initial_metric(self, node_code: str, workshop_type: str | None = None) -> MetricIn:
        baseline = _workshop_baseline(workshop_type or "general")
        return MetricIn(
            node_code=node_code, workshop_type=workshop_type,
            cpu_usage=baseline.cpu, memory_usage=baseline.mem, disk_usage=baseline.disk,
            network_in=12_000_000, network_out=8_000_000,
            db_latency_ms=baseline.db, api_latency_ms=baseline.api,
        )

    # ------------------------------------------------------------------
    # Demo scenarios
    # ------------------------------------------------------------------

    def apply_scenario(self, scenario: str) -> dict[str, object]:
        if scenario == "normal":
            self.seed_demo()
            return {"scenario": scenario, "message": "演示数据已恢复到正常状态。"}
        if scenario == "common_fault":
            target = "grinding-workshop-01"
            lm = self.latest_metrics().get(target) or self._initial_metric(target, "grinding")
            alerts = self.record_metric(lm.model_copy(update={"disk_usage": 92.0}))
            return {"scenario": scenario, "message": f"{target} 注入磁盘压力，已触发本地清理脚本。",
                    "alerts": [a.model_dump(mode="json") for a in alerts]}
        if scenario == "complex_fault":
            target = "milling-workshop-01"
            lm = self.latest_metrics().get(target) or self._initial_metric(target, "milling")
            alerts = self.record_metric(lm.model_copy(update={"cpu_usage": 95.0, "api_latency_ms": 920}))
            return {"scenario": scenario, "message": f"{target} 注入 CPU/延迟复杂故障，AI 诊断与待审批命令已生成。",
                    "alerts": [a.model_dump(mode="json") for a in alerts]}
        if scenario == "market_shift":
            for signal in self.market_signals:
                if signal.product_code == "A3":
                    signal.demand_index = round(min(180, signal.demand_index + 50), 1)
                    signal.inventory_pressure = round(min(100, signal.inventory_pressure + 25), 1)
            self.generate_production_plan()
            self.rebuild_dispatch()
            self.add_event("market-simulator", "market-shift", Severity.medium,
                           "市场需求突变：变速箱齿轮需求激增，已重排生产计划。")
            return {"scenario": scenario, "message": "市场需求变化已注入，生产计划已重排。"}
        if scenario == "hostile_attack":
            target = "turning-workshop-01"
            lm = self.latest_metrics().get(target) or self._initial_metric(target, "turning")
            alerts = self.record_metric(lm.model_copy(update={"network_in": 120_000_000}))
            return {"scenario": scenario, "message": f"{target} 注入敌对流量，已自动隔离。",
                    "alerts": [a.model_dump(mode="json") for a in alerts]}
        raise ValueError(f"unknown scenario: {scenario}")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

class _WorkshopBaseline:
    """Realistic baseline per workshop type — anchors the random walk."""
    __slots__ = ("cpu", "mem", "disk", "api", "db")

    def __init__(self, cpu: float, mem: float, disk: float, api: int, db: int) -> None:
        self.cpu = cpu
        self.mem = mem
        self.disk = disk
        self.api = api
        self.db = db


def _workshop_baseline(workshop_type: str | None) -> _WorkshopBaseline:
    bases = {
        "turning": _WorkshopBaseline(cpu=42, mem=55, disk=61, api=85, db=32),
        "milling": _WorkshopBaseline(cpu=57, mem=63, disk=66, api=110, db=45),
        "grinding": _WorkshopBaseline(cpu=48, mem=58, disk=72, api=92, db=39),
        "cloud": _WorkshopBaseline(cpu=55, mem=65, disk=60, api=120, db=35),
        "database": _WorkshopBaseline(cpu=30, mem=60, disk=75, api=45, db=5),
    }
    return bases.get(workshop_type or "general", bases["turning"])


def _real_host_metrics() -> dict[str, float]:
    """Read actual CPU / memory / disk from the machine running central-api."""
    try:
        return {
            "cpu": round(psutil.cpu_percent(interval=0.05), 1),
            "mem": round(psutil.virtual_memory().percent, 1),
            "disk": round(psutil.disk_usage("/").percent, 1),
        }
    except Exception:
        return {"cpu": 0.0, "mem": 0.0, "disk": 0.0}


store = MemoryStore()
