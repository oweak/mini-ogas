from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Severity(str, Enum):
    info = "info"
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class NodeStatus(str, Enum):
    online = "online"
    offline = "offline"
    degraded = "degraded"
    isolated = "isolated"


# Dispatch task statuses are kept as plain strings so the dashboard and tests
# can match against them directly: "scheduled", "queued", "blocked".


# ---------------------------------------------------------------------------
# Nodes (workshops) and metrics
# ---------------------------------------------------------------------------

class MetricIn(BaseModel):
    node_code: str
    workshop_type: str | None = None
    cpu_usage: float = Field(ge=0, le=100)
    memory_usage: float = Field(ge=0, le=100)
    disk_usage: float = Field(ge=0, le=100)
    network_in: int = Field(ge=0)
    network_out: int = Field(ge=0)
    db_latency_ms: int = Field(ge=0)
    api_latency_ms: int = Field(ge=0)
    finished_quantity: int = Field(default=0, ge=0)
    defect_quantity: int = Field(default=0, ge=0)


class Node(BaseModel):
    node_code: str
    node_name: str
    workshop_type: str
    status: NodeStatus = NodeStatus.online
    last_heartbeat: datetime = Field(default_factory=utc_now)


class Machine(BaseModel):
    machine_code: str
    node_code: str
    machine_type: str
    status: str = "running"
    load_rate: float = Field(default=0, ge=0, le=100)
    tool_wear_level: float = Field(default=0, ge=0, le=100)
    today_output: int = Field(default=0, ge=0)
    defect_count: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Market and inventory
# ---------------------------------------------------------------------------

class MarketSignal(BaseModel):
    product_code: str
    product_name: str
    current_price: float
    competitor_price: float
    demand_index: float
    season_factor: float
    inventory_pressure: float


class MarketForecast(BaseModel):
    product_code: str
    product_name: str
    month: str
    baseline_demand: int
    forecast_demand: int
    competitor_pressure: float


class InventoryItem(BaseModel):
    product_code: str
    product_name: str
    current_stock: int
    safety_stock: int
    pressure_score: float
    expected_days: float


# ---------------------------------------------------------------------------
# Production planning and dispatch
# ---------------------------------------------------------------------------

class ProductionPlanIn(BaseModel):
    product_code: str
    target_quantity: int = Field(ge=0)
    priority: int = Field(default=5, ge=1, le=10)
    route: list[str] = Field(default_factory=list)
    reason: str = ""


# A submitted plan and a generated plan share the same shape.
ProductionPlan = ProductionPlanIn


class DispatchTask(BaseModel):
    id: int
    product_code: str
    product_name: str
    route: list[str] = Field(default_factory=list)
    assigned_node: str = ""
    assigned_machine: str = ""
    quantity: int = Field(default=0, ge=0)
    priority: int = Field(default=5, ge=1, le=10)
    status: str = "scheduled"
    reason: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class PartQueueItem(BaseModel):
    part_id: str
    parent_part_id: str = ""
    order_id: str
    product_code: str = ""
    current_step: str = "milling"
    status: str = "ready"
    source_node: str = "turning-workshop-01"
    target_node: str = "milling-workshop-01"
    claimed_by: str = ""
    claim_token: str = ""
    claim_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ResourceAllocation(BaseModel):
    node_code: str
    workshop_type: str
    available_machines: int
    running_machines: int
    avg_load_rate: float
    planned_quantity: int
    bottleneck: str
    recommendation: str


class AllocationOrderIn(BaseModel):
    product_code: str
    required_quantity: int = Field(ge=1)
    priority: int = Field(default=3, ge=1, le=10)
    deadline_hours: int = Field(default=24, ge=1)
    assigned_cloud_role: str = "辅助调配"
    source_unit: str = "上级调度中心"
    reason: str = ""


class AllocationOrder(BaseModel):
    order_id: str
    source_unit: str
    product_code: str
    product_name: str
    required_quantity: int
    priority: int
    deadline_hours: int
    assigned_cloud_role: str
    status: str = "received"
    reason: str = ""
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Alerts / audit / commands / events
# ---------------------------------------------------------------------------

class Alert(BaseModel):
    id: int
    node_code: str
    alert_type: str
    severity: Severity
    description: str
    handled_by: str | None = None
    status: str = "open"
    created_at: datetime = Field(default_factory=utc_now)


class AuditLog(BaseModel):
    id: int
    actor: str
    action: str
    resource_type: str
    resource_id: str
    result: str
    created_at: datetime = Field(default_factory=utc_now)


class NodeCommand(BaseModel):
    id: int
    node_code: str
    command_type: str
    risk_level: str
    status: str
    operator: str
    parameters: dict[str, object] = Field(default_factory=dict)
    claimed_by: str = ""
    result_message: str = ""
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class IncidentEvent(BaseModel):
    id: int
    node_code: str
    stage: str
    severity: Severity
    message: str
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# AI diagnosis and assistant
# ---------------------------------------------------------------------------

class AiDiagnosis(BaseModel):
    id: int
    alert_id: int
    node_code: str
    model_name: str = "deepseek-chat"
    root_cause: str
    recommended_action: str
    confidence: float = Field(ge=0, le=1)
    need_isolation: bool = False
    raw_response: str = ""
    created_at: datetime = Field(default_factory=utc_now)


class AiDiagnoseRequest(BaseModel):
    alert_id: int | None = None
    node_code: str = "cloud-workshop-01"
    question: str | None = None
    provider: str = "auto"  # "auto" = chain fallback, or name a specific provider
    # Frontend-provided fields (used to enrich the diagnosis prompt)
    alert_description: str | None = None
    alert_type: str | None = None
    severity: str | None = None


class AiProviderStatus(BaseModel):
    name: str
    available: bool
    in_chain: bool
    fallback: bool


class AiStatus(BaseModel):
    enabled: bool
    configured: bool
    provider: str = "auto"
    active_provider: str = ""
    model: str = ""
    base_url: str = ""
    mode: str = ""
    providers: list[AiProviderStatus] = []
    tip: str = ""


class AiChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str


class AiChatRequest(BaseModel):
    messages: list[AiChatMessage]
    node_code: str = "cloud-workshop-01"
    use_context: bool = True


class AiChatResponse(BaseModel):
    accepted: bool
    used_deepseek: bool
    status: str
    model: str
    answer: str


class AiShortcut(BaseModel):
    id: str
    label: str
    description: str
    prompt: str
    action_hint: str
    risk_level: str


# ---------------------------------------------------------------------------
# Preflight / self-check
# ---------------------------------------------------------------------------

class PreflightStep(BaseModel):
    key: str
    label: str
    status: str = "pending"  # pending | running | pass | fail
    detail: str = ""
    elapsed_ms: int = 0


class PreflightResult(BaseModel):
    all_pass: bool
    steps: list[PreflightStep]
    message: str


# ---------------------------------------------------------------------------
# Admin login (pre-dashboard verification)
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    ok: bool
    role: str = ""
    message: str = ""


# ---------------------------------------------------------------------------
# Natural-language control
# ---------------------------------------------------------------------------

class ControlCommandRequest(BaseModel):
    text: str
    execute: bool = False
    confirm: str | None = None


class ControlCommandPlan(BaseModel):
    action: str
    target_node: str | None = None
    risk_level: str
    requires_confirmation: bool
    reason: str


class ControlCommandResponse(BaseModel):
    accepted: bool
    executed: bool
    used_deepseek: bool
    status: str
    plan: ControlCommandPlan
    result: dict[str, object] | None = None
    message: str
    safety: dict[str, object] | None = None


# ---------------------------------------------------------------------------
# Topology and hosts
# ---------------------------------------------------------------------------

class TopologyEdge(BaseModel):
    source: str
    target: str
    protocol: str
    status: str
    latency_ms: int = Field(ge=0)


class HostRuntimeStatus(BaseModel):
    host_code: str
    host_name: str
    role: str
    location: str
    status: str
    connection: str
    node_code: str | None = None
    node_status: str | None = None
    last_seen: datetime | None = None
    cpu_usage: float | None = None
    memory_usage: float | None = None
    disk_usage: float | None = None
    api_latency_ms: int | None = None
    database: str
    service: str


# ---------------------------------------------------------------------------
# Cross-node transfer self-test
# ---------------------------------------------------------------------------

class TransferDataTestIn(BaseModel):
    target_node: str = "cloud-workshop-01"
    batch_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    records: list[dict[str, str | int | float]] = Field(max_length=1000)


class TransferFileTestIn(BaseModel):
    target_node: str = "cloud-workshop-01"
    file_name: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,80}$")
    content_base64: str


class TransferTestResult(BaseModel):
    accepted: bool
    transfer_type: str
    target_node: str
    route: list[str]
    bytes_received: int
    checksum_sha256: str
    saved_to: str | None = None
    message: str
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Simulation control
# ---------------------------------------------------------------------------

class SimulationControl(BaseModel):
    running: bool | None = None
    speed: float | None = Field(default=None, ge=0.2, le=5)
    anomaly_rate: float | None = Field(default=None, ge=0, le=1)


class SimulationState(BaseModel):
    running: bool
    tick: int
    speed: float
    anomaly_rate: float
    last_tick_at: datetime | None = None
    generated_orders: int = 0
    generated_events: int = 0
    mode: str = "realtime-demo"


class DemoScenario(BaseModel):
    scenario: str = Field(pattern="^(normal|common_fault|complex_fault|market_shift|hostile_attack)$")


# ---------------------------------------------------------------------------
# Dashboard summary
# ---------------------------------------------------------------------------

class DashboardSummary(BaseModel):
    node_count: int
    online_count: int
    isolated_count: int
    alert_count: int
    critical_alert_count: int
    total_finished_quantity: int
    defect_rate: float
    avg_cpu_usage: float
    avg_memory_usage: float
    avg_disk_usage: float
