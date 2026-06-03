from __future__ import annotations

import logging
import random
import threading
from datetime import datetime, timedelta, timezone
from statistics import mean

import psutil

from .core.ai.registry import registry
from .core.config import settings
from .core.session import get_session_token
from .core.database import get_db, init_db
from .core.service_client import get_json

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


def product_name(product_code: str) -> str:
    product = PRODUCTS.get(product_code)
    return str(product["name"]) if product else product_code


def product_route(product_code: str) -> list[str]:
    product = PRODUCTS.get(product_code)
    return list(product["route"]) if product else ["turning", "inspection"]


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
        # Alerts / audit / commands / events / diagnoses
        self.alerts: list[Alert] = []
        self.audit_logs: list[AuditLog] = []
        self.commands: list[NodeCommand] = []
        self.incident_events: list[IncidentEvent] = []
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

    # ------------------------------------------------------------------
    # Persistence (optional, off by default)
    # ------------------------------------------------------------------

    def _persisting(self) -> bool:
        return settings.persist_enabled and not self._suspend_persist

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
            logger.warning("SQLite persistence warning (metric): %s", exc)

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
            logger.warning("SQLite persistence warning (alert): %s", exc)

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
            logger.warning("SQLite persistence warning (command): %s", exc)

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
        except Exception as exc:  # pragma: no cover
            logger.warning("SQLite persistence warning (event): %s", exc)

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
                     int(diagnosis.need_isolation), diagnosis.model_name, None,
                     diagnosis.created_at.isoformat()),
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("SQLite persistence warning (ai_diagnosis): %s", exc)

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
        self.alerts.clear()
        self.audit_logs.clear()
        self.commands.clear()
        self.incident_events.clear()
        self.ai_diagnoses.clear()
        self.allocation_orders.clear()
        self.dispatch_tasks.clear()
        self.dispatch_seq = 0
        self.order_seq = 0
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
            product_code="A3", required_quantity=120, priority=2, deadline_hours=18,
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

    def add_command(self, node_code: str, command_type: str, risk_level: str, status: str,
                    operator: str) -> NodeCommand:
        with self._lock:
            command = NodeCommand(id=len(self.commands) + 1, node_code=node_code,
                                  command_type=command_type, risk_level=risk_level,
                                  status=status, operator=operator)
            self.commands.append(command)
            self.commands = self.commands[-100:]
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
                         session_token: str = "") -> dict[str, object]:
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
        return {
            "accepted": True,
            "node_code": node_code,
            "agent_version": agent_version,
            "uptime_seconds": uptime_seconds,
            "local_db_size_bytes": local_db_size_bytes,
            "status": status,
            "session_verified": not token_mismatch,
        }

    def check_heartbeat_timeout(self) -> int:
        """Mark nodes as offline if their last heartbeat is older than the timeout.

        Returns the number of nodes that were marked offline.
        """
        timeout_seconds = settings.heartbeat_timeout_seconds
        cutoff = utc_now() - timedelta(seconds=timeout_seconds)
        expired = 0
        with self._lock:
            for node in self.nodes.values():
                if node.status in {NodeStatus.online, NodeStatus.degraded} and node.last_heartbeat < cutoff:
                    node.status = NodeStatus.offline
                    expired += 1
                    self.add_event(node.node_code, "heartbeat-timeout", Severity.high,
                                   f"节点 {node.node_code} 心跳超时（>{timeout_seconds}s），自动标记为离线。")
        return expired

    # ------------------------------------------------------------------
    # Metric recording + rule-based fault handling
    # ------------------------------------------------------------------

    def record_metric(self, metric: MetricIn, evaluate: bool = True) -> list[Alert]:
        with self._lock:
            workshop_type = metric.workshop_type or self.infer_workshop_type(metric.node_code)
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

    # ------------------------------------------------------------------
    # Approvals / escalation
    # ------------------------------------------------------------------

    def pending_commands_for_node(self, node_code: str) -> list[NodeCommand]:
        return [c for c in self.commands if c.node_code == node_code and c.status in {"pending", "queued"}]

    def record_command_result(self, node_code: str, command_id: int, status: str,
                              message: str) -> dict[str, object]:
        for c in self.commands:
            if c.id == command_id and c.node_code == node_code:
                c.status = status
                break
        self.add_event(node_code, "command-result", Severity.info,
                       f"command_id={command_id} status={status}: {message}")
        return {"accepted": True, "command_id": command_id, "status": status, "message": message}

    def pending_approvals(self) -> list[NodeCommand]:
        return [c for c in self.commands if c.status == "waiting_approval"]

    def approve_command(self, command_id: int, actor: str) -> dict[str, object]:
        for c in self.commands:
            if c.id == command_id:
                if c.status != "waiting_approval":
                    raise ValueError(f"command {command_id} is not waiting approval (current: {c.status})")
                c.status = "pending"
                c.operator = actor
                self.add_event(c.node_code, "command-approved", Severity.info,
                               f"运维人员 {actor} 审批通过命令 #{command_id} ({c.command_type})。")
                return {"accepted": True, "command_id": command_id, "status": "pending", "actor": actor}
        raise ValueError(f"command {command_id} not found")

    def reject_command(self, command_id: int, actor: str, reason: str = "") -> dict[str, object]:
        for c in self.commands:
            if c.id == command_id:
                if c.status != "waiting_approval":
                    raise ValueError(f"command {command_id} is not waiting approval (current: {c.status})")
                c.status = "rejected"
                c.operator = actor
                self.add_event(c.node_code, "command-rejected", Severity.medium,
                               f"运维人员 {actor} 拒绝命令 #{command_id} ({c.command_type})。原因: {reason or '未提供'}。")
                return {"accepted": True, "command_id": command_id, "status": "rejected",
                        "actor": actor, "reason": reason}
        raise ValueError(f"command {command_id} not found")

    def escalate_to_human(self, node_code: str, issue_type: str, description: str) -> dict[str, object]:
        self.add_event(node_code, "escalation", Severity.high, f"[需人工介入] {issue_type}: {description}")
        self.create_alert(node_code, issue_type, Severity.high, description, handled_by="human-required")
        return {"escalated": True, "node_code": node_code, "issue_type": issue_type}

    def pending_escalations(self) -> list[IncidentEvent]:
        return [e for e in self.incident_events if e.stage == "escalation"][-20:]

    # ------------------------------------------------------------------
    # Market and inventory
    # ------------------------------------------------------------------

    def refresh_market_via_service(self) -> None:
        """Optionally pull the latest market snapshot from the market-simulator
        microservice. No-op (and offline edge) when microservices are disabled."""
        if not settings.microservices_enabled:
            self.update_integration_edge("market-simulator", False)
            return
        ok, _ = get_json(f"{settings.market_simulator_url}/health")
        self.update_integration_edge("market-simulator", ok)

    # ------------------------------------------------------------------
    # Production planning and dispatch
    # ------------------------------------------------------------------

    def generate_production_plan(self) -> list[ProductionPlanIn]:
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
        order = AllocationOrder(
            order_id=f"AO-{self.order_seq:03d}", source_unit=order_in.source_unit,
            product_code=order_in.product_code, product_name=product_name(order_in.product_code),
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
            "ai_shortcuts": self.ai_shortcuts,
            "simulation": self.simulation_state(),
            "integrations": integrations,
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
            target = self.rng.choice([nc for nc, _ in nodes_snapshot])
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
