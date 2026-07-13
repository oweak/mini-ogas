import type {
  AuditEvent,
  DashboardSnapshot,
  EventLog,
  HostNode,
  HostWorkOrder,
  LogEvent,
  LogLevel,
  RuntimeDashboardState,
  SnapshotSummary
} from './types'

export type FetchSlot<T> = {
  ok: boolean
  data?: T
}

export function normalizeAuditEvents(payload: unknown): AuditEvent[] {
  const rows = Array.isArray(payload)
    ? payload
    : (payload && typeof payload === 'object' && Array.isArray((payload as { events?: unknown[] }).events)
        ? (payload as { events: unknown[] }).events
        : [])

  return rows
    .filter((row): row is Record<string, unknown> => Boolean(row && typeof row === 'object'))
    .map((row) => {
      if (typeof row.time === 'string' && typeof row.permission === 'string') {
        return row as AuditEvent
      }
      const timestamp = String(row.timestamp ?? '')
      const detail = row.detail && typeof row.detail === 'object'
        ? row.detail as Record<string, unknown>
        : undefined
      return {
        id: String(row.id ?? ''),
        time: timestamp ? timestamp.replace('T', ' ').slice(0, 19) : '',
        actor: String(row.actor ?? 'system'),
        role: String(row.source_type ?? 'system'),
        permission: String(row.action ?? 'audit:read'),
        subject: String(row.message ?? `${row.resource_type ?? 'event'} ${row.resource_id ?? ''}`).trim(),
        action: String(row.action ?? ''),
        result: String(row.result ?? 'recorded'),
        status: String(row.result ?? 'recorded'),
        node_code: String(row.node_code ?? ''),
        severity: String(row.severity ?? 'info'),
        source: String(row.source_type ?? 'audit'),
        effect: detail
      }
    })
}

export type JsonResponseLike<T> = {
  ok: boolean
  json: () => Promise<T>
}

export type AlarmFetchMerge<TAlert, TDiagnosis, TEscalation> = {
  alerts?: TAlert[]
  diagnoses?: TDiagnosis[]
  escalations?: TEscalation[]
  apiAvailable: boolean
}

export async function responseToFetchSlot<T>(response: JsonResponseLike<T> | null): Promise<FetchSlot<T>> {
  if (!response?.ok) return { ok: false }
  try {
    return { ok: true, data: await response.json() }
  } catch {
    return { ok: false }
  }
}

export function mergeAlarmFetchResults<TAlert, TDiagnosis, TEscalation>(
  alerts: FetchSlot<TAlert[]>,
  diagnoses: FetchSlot<TDiagnosis[]>,
  escalations: FetchSlot<TEscalation[]>
): AlarmFetchMerge<TAlert, TDiagnosis, TEscalation> {
  return {
    alerts: alerts.ok ? alerts.data ?? [] : undefined,
    diagnoses: diagnoses.ok ? diagnoses.data ?? [] : undefined,
    escalations: escalations.ok ? escalations.data ?? [] : undefined,
    apiAvailable: alerts.ok || diagnoses.ok || escalations.ok
  }
}

export type BackendLogEvent = {
  time: string
  level: string
  source: string
  message: string
}

const knownLogLevels = new Set<LogLevel>(['info', 'notice', 'success', 'warning', 'danger', 'error', 'critical'])

export function normalizeLogLevel(level: string | undefined): LogLevel {
  const normalized = String(level ?? '').trim().toLowerCase()
  if (knownLogLevels.has(normalized as LogLevel)) return normalized as LogLevel
  if (normalized === 'warn') return 'warning'
  if (normalized === 'fatal' || normalized === 'panic') return 'critical'
  if (normalized === 'failed' || normalized === 'failure') return 'error'
  return 'info'
}

export function visibleRuntimeEvents(logEvents: BackendLogEvent[], liveLogs: string[]): EventLog[] {
  if (logEvents.length) {
    return logEvents.slice(0, 8).map((event) => ({
      ...event,
      level: normalizeLogLevel(event.level)
    }))
  }
  return liveLogs.map((log) => ({
    time: log.slice(0, 8),
    level: 'info',
    source: 'central-api',
    message: log.slice(9)
  }))
}

function normalizeSnapshotNode(node: DashboardSnapshot['nodes'][number]): HostNode {
  const production = node.production ?? {}
  return {
    ...node,
    runtime: node.runtime,
    deployment_mode: node.deployment_mode ?? node.runtime?.deployment_mode,
    simulation_mode: node.simulation_mode ?? node.runtime?.simulation_mode,
    production: {
      ...production,
      machine_code: production.machine_code ?? node.machine_code,
      workshop_type: production.workshop_type ?? node.workshop_type,
      active_order: production.active_order ?? node.active_order
    }
  }
}

function normalizeSnapshotWorkOrder(order: DashboardSnapshot['work_orders'][number]): HostWorkOrder {
  return {
    id: order.id,
    product: order.product,
    quantity: Number(order.quantity ?? 0),
    priority: String(order.priority ?? 'P2'),
    route: order.route ?? [],
    assigned_node: order.assigned_node ?? '',
    status: String(order.status ?? 'scheduled')
  }
}

function snapshotEvents(snapshot: DashboardSnapshot): LogEvent[] {
  const events = snapshot.audit?.recent_events ?? []
  return events.slice(-12).map((event) => ({
    time: String(event.created_at ?? snapshot.generated_at).slice(11, 19),
    level: String(event.severity ?? 'info'),
    source: String(event.node_code ?? event.stage ?? 'central-api'),
    message: String(event.message ?? event.stage ?? 'snapshot event')
  }))
}

export function dashboardSnapshotToState(snapshot: DashboardSnapshot): RuntimeDashboardState {
  return {
    issues: snapshot.alerts ?? [],
    notifications: snapshot.notifications ?? [],
    logs: snapshot.timeline?.recent_logs?.length
      ? snapshot.timeline.recent_logs
      : [`${String(snapshot.generated_at).slice(11, 19)} snapshot ${snapshot.data_source} ${snapshot.run.run_id}`],
    log_events: snapshotEvents(snapshot),
    nodes: (snapshot.nodes ?? []).map(normalizeSnapshotNode),
    work_orders: (snapshot.work_orders ?? []).map(normalizeSnapshotWorkOrder),
    dispatch_plan: snapshot.dispatch_plan,
    snapshot
  }
}

const terminalIssueStatuses = new Set(['closed', 'resolved', 'archived', 'acknowledged'])

export function activeDashboardIssues(state: RuntimeDashboardState): DashboardSnapshot['alerts'] {
  const currentRunId = state.snapshot?.run.run_id ?? ''
  const activeAlerts = (state.issues ?? []).filter((issue) =>
    !terminalIssueStatuses.has(String(issue.status ?? '').toLowerCase())
  )
  const pendingNotifications = (state.notifications ?? []).filter((notification) => {
    if (terminalIssueStatuses.has(String(notification.status ?? '').toLowerCase())) return false
    return !currentRunId || !notification.run_id || notification.run_id === currentRunId
  })

  const seen = new Set<string>()
  return [...activeAlerts, ...pendingNotifications].filter((issue) => {
    if (seen.has(issue.id)) return false
    seen.add(issue.id)
    return true
  })
}

export function snapshotSummary(snapshot: DashboardSnapshot | null): SnapshotSummary | null {
  if (!snapshot) return null
  return {
    schemaVersion: snapshot.schema_version,
    dataSource: snapshot.data_source,
    generatedAt: snapshot.generated_at,
    runId: snapshot.run.run_id,
    scenarioId: snapshot.run.scenario_id,
    simulationTime: snapshot.run.simulation_time ?? '',
    simulationSpeed: snapshot.run.simulation_speed ?? '',
    simulationEngine: snapshot.run.simulation_engine ?? 'unknown',
    nodesConnected: Number(snapshot.system?.nodes_connected ?? 0),
    nodesExpected: Number(snapshot.system?.nodes_expected ?? 0)
  }
}
