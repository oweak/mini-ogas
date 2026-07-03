export type MachineState = 'running' | 'idle' | 'warning' | 'fault' | 'isolated' | 'maintenance'

export type Machine = {
  code: string
  name: string
  type: string
  state: MachineState
  workOrder: string
  process: string
  output: number
  target: number
  yieldRate: number
  oee: number
  toolWear: number
  targetRate?: number
  actualRate?: number
  utilization?: number
  defectRate?: number
  sync: 'online' | 'delayed' | 'offline'
  lastAlarm?: string
}

export type Workshop = {
  code: string
  name: string
  node: string
  status: MachineState
  load: number
  machines: Machine[]
}

export type WorkOrder = {
  id: string
  product: string
  route: string[]
  priority: 'P1' | 'P2' | 'P3'
  quantity: number
  completed: number
  due: string
  status: 'scheduled' | 'in_progress' | 'blocked' | 'waiting'
}

export type DisplayedWorkOrder = {
  id: string
  product: string
  route: string[]
  priority: string
  quantity: number
  completed: number
  due: string
  status: 'scheduled' | 'in_progress' | 'blocked' | 'waiting'
}

export type HostWorkOrder = {
  id: string
  product: string
  quantity: number
  priority: string
  route: string[]
  assigned_node: string
  status: string
}

export type NodeRuntime = {
  deployment_mode?: string
  simulation_mode?: string
  simulation_engine?: string
  host?: string
  pid?: number
  heartbeat_sec?: number
  run_id?: string
  scenario_id?: string
  simulation_time?: string
  simulation_speed?: number
  runtime_source?: string
}

export type HostNode = {
  node_code: string
  status: MachineState | 'online' | 'running' | 'fault' | 'warning' | 'maintenance' | 'isolated' | 'offline' | 'missing'
  last_seen_sec?: number
  deployment_mode?: string
  simulation_mode?: string
  metrics?: {
    cpu_usage?: number
    memory_usage?: number
    disk_usage?: number
    network_latency_ms?: number
    db_latency_ms?: number
  }
  production?: {
    machine_code?: string
    workshop_type?: string
    dispatch_policy?: string
    active_order?: string
    active_part_id?: string
    finished_quantity?: number
    defect_quantity?: number
    tool_wear_level?: number
    spindle_temp?: number
    wip_input?: number
    wip_output?: number
    target_rate?: number
    actual_rate?: number
    utilization?: number
    defect_rate?: number
  }
  alarms?: Array<{ type: string; severity?: string; status?: string }>
  sync?: { pending_records?: number }
  runtime?: NodeRuntime
}

export type AuthRuntime = {
  status: string
  provider: string
  model: string
  source: string
  vault_present: boolean
  vault_unlocked: boolean
  unlocked_by?: string
}

export type PreflightCheck = {
  id: string
  label: string
  status: string
  detail: string
  visualStatus?: string
}

export type PreflightNode = {
  node_code: string
  connected: boolean
  status: string
  machine_code: string
  active_order: string
  alarms: string[]
  pending_records: number
  runtime?: NodeRuntime
}

export type PreflightState = {
  ok: boolean
  status: string
  checks: PreflightCheck[]
  nodes: PreflightNode[]
  ai_runtime: AuthRuntime
}

export type AiSmokeState = {
  ok: boolean
  source: string
  status: string
  provider: string
  model: string
  summary?: string
  error?: string
}

export type DispatchPlan = {
  id: string
  status: string
  summary: string
  source_order: string
  from_node: string
  to_node: string
  risk: string
  steps: string[]
  confirmation_code_hint?: string
  result?: string
}

export type Alarm = {
  id: string
  severity: 'medium' | 'high' | 'critical'
  machine: string
  title: string
  value: string
  status: 'unacknowledged' | 'confirmed' | 'diagnosed' | 'contained' | 'observing'
  rule: string
  aiSuggestion: string
  requiredRole: string
}

export type ApiAlert = {
  id: number
  issue_id?: string
  node_code: string
  alert_type: string
  severity: string
  description: string
  status?: string
  handled_by: string | null
}

export type AiDecisionOption = {
  label: string
  rationale?: string
  risk?: string
  automation?: boolean
}

export type AiDecision = {
  status?: string
  source?: string
  provider?: string
  model?: string
  generated_at?: string
  summary?: string
  risk_assessment?: string
  requires_human?: boolean
  automation_allowed?: boolean
  confidence?: number
  evidence?: string[]
  options?: AiDecisionOption[]
  questions_to_operator?: string[]
  root_cause_hypotheses?: string[]
  recommended_plan?: string[]
}

export type ApiDiagnosis = {
  id: number
  alert_id: number | string
  issue_id?: string
  node_code: string
  root_cause: string
  recommended_action: string
  confidence: number
  need_isolation: boolean
  model_name: string
  source?: string
  provider?: string
  status?: string
  generated_at?: string
  risk_assessment?: string
  requires_human?: boolean
  automation_allowed?: boolean
  evidence?: string[]
  options?: AiDecisionOption[]
  questions_to_operator?: string[]
  decision?: AiDecision
}

export type EscalationItem = {
  id?: number
  node_code: string
  issue_type: string
  description: string
  status: string
}

export type LogLevel = 'info' | 'notice' | 'success' | 'warning' | 'danger' | 'error' | 'critical'

export type EventLog = {
  time: string
  source: string
  message: string
  level: LogLevel
}

export type AuditEvent = {
  id: string
  time: string
  actor: string
  role: string
  permission: string
  subject: string
  action: string
  result: string
  status: string
  node_code?: string
  issue_id?: string
  severity?: string
  source: string
  effect?: Record<string, unknown>
}

export type LogEvent = {
  time: string
  level: 'debug' | 'info' | 'warning' | 'error' | string
  source: string
  message: string
  request_id?: string
}

export type NodeSyncRecord = {
  node_code: string
  synced_at: string
  record: {
    status?: string
    production?: {
      machine_code?: string
      active_order?: string
      spindle_temp?: number
    }
    alarms?: Array<{ type?: string; severity?: string; status?: string }>
  }
}

export type DashboardSnapshotRun = {
  run_id: string
  scenario_id: string
  simulation_time?: string
  simulation_speed?: number
  simulation_engine?: string
}

export type DashboardSnapshotSystem = {
  status: string
  nodes_connected: number
  nodes_expected: number
  ai_runtime?: AuthRuntime
}

export type DashboardSnapshotNode = HostNode & {
  machine_code?: string
  active_order?: string
  workshop_type?: string
  runtime_source?: string
}

export type DashboardSnapshotAlert = {
  id: string
  severity: string
  title: string
  detail: string
  status?: string
  actions?: string[]
}

export type RuleEvidence = {
  field: string
  operator: string
  value: number | string
  threshold: number | string
  detail: string
}

export type RuleConclusion = {
  schema_version: string
  conclusion_id: string
  rule_id: string
  type: 'bottleneck_alert' | 'starvation_alert' | string
  node_code: string
  machine_code: string
  risk_level: 'low' | 'medium' | 'high' | 'critical' | string
  severity: 'low' | 'medium' | 'high' | 'critical' | string
  title: string
  summary: string
  evidence: RuleEvidence[]
  recommended_actions: string[]
  source: {
    data_source?: string
    run_id?: string
    scenario_id?: string
    simulation_time?: string
    simulation_engine?: string
  }
  read_only: boolean
}

export type AiRuleExplanation = {
  schema_version: string
  status: 'steady' | 'explained' | 'fallback' | string
  source: 'api' | 'steady-state' | 'rule-fallback' | string
  provider: string
  model: string
  used_live_ai: boolean
  rule_count: number
  prompt_digest: string
  summary: string
  reasoning: string[]
  recommended_actions: string[]
  evidence: string[]
  conclusion_ids: string[]
  raw_text?: string
}

export type DashboardSnapshotWorkOrder = Partial<HostWorkOrder> & {
  id: string
  product: string
  route?: string[]
  priority?: string
  quantity: number
  completed?: number
  due?: string
  status?: string
}

export type PartQueueItem = {
  part_id: string
  order_id: string
  product_code: string
  current_step: string
  status: 'ready' | 'claimed' | 'completed' | 'interrupted' | string
  source_node: string
  target_node: string
  claimed_by?: string
  claim_token?: string
  claim_expires_at?: string | null
  created_at: string
  updated_at: string
}

export type PartQueueSnapshot = {
  counts: Record<string, number>
  items: PartQueueItem[]
}

export type ReplayRunSummary = {
  run_id: string
  scenario_ids: string[]
  node_codes: string[]
  node_count: number
  heartbeat_count: number
  started_at: string
  ended_at: string
  latest_simulation_time?: string | null
}

export type ReplayRunsResponse = {
  status: string
  backend?: string
  runs: ReplayRunSummary[]
  sampled_heartbeat_rows?: number
  reason?: string
  error?: string
}

export type ReplayTimelineItem = {
  time: string
  kind: 'heartbeat' | 'command' | 'part_queue' | 'audit' | 'alert' | 'ai_diagnosis' | string
  node_code?: string
  title?: string
  status?: string
  detail?: Record<string, unknown>
}

export type ReplayRunDetail = {
  status: string
  backend?: string
  run_id: string
  scenario_ids: string[]
  node_codes: string[]
  started_at: string
  ended_at: string
  counts: {
    heartbeats: number
    commands: number
    part_queue: number
    audit_events: number
    alerts: number
    ai_diagnoses: number
    timeline: number
  }
  heartbeats: Array<Record<string, unknown>>
  commands: Array<Record<string, unknown>>
  part_queue: Array<Record<string, unknown>>
  audit_events: Array<Record<string, unknown>>
  alerts: Array<Record<string, unknown>>
  ai_diagnoses: Array<Record<string, unknown>>
  timeline: ReplayTimelineItem[]
  reason?: string
  error?: string
}

export type DashboardSnapshot = {
  schema_version: string
  generated_at: string
  data_source: 'live' | 'fallback' | 'fixture' | string
  run: DashboardSnapshotRun
  system: DashboardSnapshotSystem
  nodes: DashboardSnapshotNode[]
  work_orders: DashboardSnapshotWorkOrder[]
  part_queue?: PartQueueSnapshot
  alerts: DashboardSnapshotAlert[]
  notifications?: DashboardSnapshotAlert[]
  rule_conclusions?: RuleConclusion[]
  dispatch_plan?: DispatchPlan
  audit?: {
    recent_events?: Array<{
      id?: number | string
      node_code?: string
      stage?: string
      severity?: string
      message?: string
      created_at?: string
    }>
  }
  timeline?: {
    recent_logs?: string[]
  }
}

export type RuntimeDashboardState = {
  issues: DashboardSnapshotAlert[]
  notifications?: DashboardSnapshotAlert[]
  logs: string[]
  log_events?: LogEvent[]
  nodes?: HostNode[]
  work_orders?: HostWorkOrder[]
  dispatch_plan?: DispatchPlan
  audit_events?: AuditEvent[]
  node_sync_records?: NodeSyncRecord[]
  snapshot?: DashboardSnapshot
}

export type SnapshotSummary = {
  schemaVersion: string
  dataSource: string
  generatedAt: string
  runId: string
  scenarioId: string
  simulationTime: string
  simulationSpeed: number | string
  simulationEngine: string
  nodesConnected: number
  nodesExpected: number
}
