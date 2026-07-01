import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { closeIssue, decideEscalation as decideEscalationRequest, decideIssue } from './operationsApi'
import { actionsForAlarm, mergeReturnedAuditEvent, useAlarmWorkflow } from './useAlarmWorkflow'
import type { Alarm, ApiAlert, AuditEvent, EscalationItem } from './types'

vi.mock('./operationsApi', () => ({
  closeIssue: vi.fn(),
  confirmAlert: vi.fn(),
  decideEscalation: vi.fn(),
  decideIssue: vi.fn(),
  diagnoseIssue: vi.fn(),
  diagnosePayload: vi.fn(),
  escalateIssue: vi.fn(),
  isolateNode: vi.fn()
}))

const closeIssueMock = vi.mocked(closeIssue)
const decideIssueMock = vi.mocked(decideIssue)
const decideEscalationMock = vi.mocked(decideEscalationRequest)

function jsonResponse(body: unknown, ok = true) {
  return new Response(JSON.stringify(body), {
    status: ok ? 200 : 400,
    headers: { 'Content-Type': 'application/json' }
  })
}

function apiAlert(overrides: Partial<ApiAlert> = {}): ApiAlert {
  return {
    id: 1,
    issue_id: 'ALM-1',
    node_code: 'milling-workshop-01',
    alert_type: '主轴温度过高',
    severity: 'high',
    description: '当前值 89 C / 阈值 82 C',
    status: 'contained',
    handled_by: null,
    ...overrides
  }
}

function displayAlarm(alert: ApiAlert): Alarm {
  return {
    id: alert.issue_id ?? `${alert.node_code}-${alert.alert_type}`,
    severity: alert.severity === 'critical' ? 'critical' : alert.severity === 'high' ? 'high' : 'medium',
    machine: alert.node_code,
    title: alert.alert_type,
    value: alert.description,
    status: (alert.status ?? 'unacknowledged') as Alarm['status'],
    rule: `规则引擎：${alert.alert_type}`,
    aiSuggestion: '等待 AI 诊断',
    requiredRole: '车间主管'
  }
}

function auditEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    id: 'audit-1',
    time: '2026-06-06 12:00:00',
    actor: '车间主管',
    role: '车间主管',
    permission: '人工处置',
    subject: 'ALM-1',
    action: '验证关闭',
    result: '问题已关闭',
    status: 'resolved',
    node_code: 'milling-workshop-01',
    issue_id: 'ALM-1',
    source: 'operator-action',
    ...overrides
  }
}

function createWorkflow(initialAlerts: ApiAlert[] = [apiAlert(), apiAlert({ id: 2, issue_id: 'ALM-2', node_code: 'turning-workshop-01' })]) {
  const apiAlerts = ref<ApiAlert[]>(initialAlerts)
  const apiDiagnoses = ref([])
  const escalationQueue = ref<EscalationItem[]>([])
  const escalationConfirmCodes = ref<Record<number, string>>({})
  const auditEvents = ref<AuditEvent[]>([])
  const alarmActionLoading = ref<string | null>(null)
  const aiDiagnosisResult = ref<string | null>(null)
  const alarmFeedback = ref('')
  const selectedAlarmId = ref(initialAlerts[0]?.issue_id ?? '')
  const resolvedEffects = ref<string[]>([])
  const liveLogs = ref<string[]>([])
  const displayAlarms = computed(() => apiAlerts.value.map(displayAlarm))
  const selectedAlarm = computed(() => displayAlarms.value.find((alarm) => alarm.id === selectedAlarmId.value))
  const latestDiagnosisForSelected = computed(() => undefined)
  const loadDashboardState = vi.fn(async () => {})
  const fetchAuditEvents = vi.fn(async () => {})
  const fetchAlarmData = vi.fn(async () => {})
  const playSound = vi.fn()

  const workflow = useAlarmWorkflow({
    selectedAlarm,
    latestDiagnosisForSelected,
    displayAlarms,
    apiAlerts,
    apiDiagnoses,
    escalationQueue,
    escalationConfirmCodes,
    auditEvents,
    alarmActionLoading,
    aiDiagnosisResult,
    alarmFeedback,
    selectedAlarmId,
    resolvedEffects,
    liveLogs,
    loadDashboardState,
    fetchAuditEvents,
    fetchAlarmData,
    currentTime: () => '12:00:00',
    currentOperator: () => 'line-lead',
    playSound
  })

  return {
    workflow,
    apiAlerts,
    escalationQueue,
    escalationConfirmCodes,
    auditEvents,
    alarmFeedback,
    selectedAlarmId,
    resolvedEffects,
    liveLogs,
    loadDashboardState,
    fetchAuditEvents,
    fetchAlarmData,
    playSound
  }
}

describe('actionsForAlarm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('allows only confirmation for unacknowledged alarms', () => {
    expect(actionsForAlarm('unacknowledged')).toEqual({
      confirm: true,
      diagnose: false,
      isolate: false,
      observe: false,
      ignore: false,
      escalate: false,
      close: false
    })
  })

  it('allows diagnosis and escalation only after confirmation', () => {
    expect(actionsForAlarm('confirmed')).toEqual({
      confirm: false,
      diagnose: true,
      isolate: false,
      observe: false,
      ignore: false,
      escalate: true,
      close: false
    })
  })

  it('exposes decision actions after diagnosis and gates isolation on AI recommendation', () => {
    expect(actionsForAlarm('diagnosed', { need_isolation: false } as never).isolate).toBe(false)
    expect(actionsForAlarm('diagnosed', { need_isolation: true } as never)).toMatchObject({
      confirm: false,
      diagnose: false,
      isolate: true,
      observe: true,
      ignore: true,
      escalate: true,
      close: false
    })
  })

  it('allows closure only after containment or observation', () => {
    expect(actionsForAlarm('contained').close).toBe(true)
    expect(actionsForAlarm('observing').close).toBe(true)
    expect(actionsForAlarm('diagnosed').close).toBe(false)
  })

  it('places returned archive events at the top without duplicating existing rows', () => {
    const existing = [
      { id: 'old-1', permission: '人工处置' },
      { id: 'same-1', permission: '旧记录' }
    ] as AuditEvent[]
    const returned = { id: 'same-1', permission: '人工处置', source: 'operator-action' } as AuditEvent

    const merged = mergeReturnedAuditEvent(existing, returned)
    expect(merged).toHaveLength(2)
    expect(merged[0]).toBe(returned)
    expect(merged.map((event) => event.id)).toEqual(['same-1', 'old-1'])
    expect(mergeReturnedAuditEvent(existing, undefined)).toBe(existing)
  })

  it('closes an alarm by removing it from the queue and placing the archive row in logs immediately', async () => {
    const returnedAudit = auditEvent({ id: 'close-audit', action: '维修验证完成并关闭' })
    closeIssueMock.mockResolvedValue(jsonResponse({
      ok: true,
      effect: { verification: { issue_closed: true, alarm_removed: true }, node_code: 'milling-workshop-01' },
      audit_event: returnedAudit
    }))
    const { workflow, apiAlerts, selectedAlarmId, auditEvents, alarmFeedback, resolvedEffects, loadDashboardState, fetchAuditEvents, fetchAlarmData, playSound } = createWorkflow()

    await workflow.closeAlarm(displayAlarm(apiAlerts.value[0]))

    expect(closeIssueMock).toHaveBeenCalledWith('ALM-1', '验证完成并关闭问题', 'line-lead')
    expect(apiAlerts.value.map((alert) => alert.issue_id)).toEqual(['ALM-2'])
    expect(selectedAlarmId.value).toBe('ALM-2')
    expect(auditEvents.value[0]).toEqual(returnedAudit)
    expect(resolvedEffects.value[0]).toContain('验证关闭')
    expect(alarmFeedback.value).toContain('归档到日志管理')
    expect(loadDashboardState).toHaveBeenCalled()
    expect(fetchAuditEvents).toHaveBeenCalled()
    expect(fetchAlarmData).toHaveBeenCalled()
    expect(playSound).toHaveBeenCalledWith('success')
  })

  it('ignores a false alarm and archives the returned decision event before refresh completes', async () => {
    const returnedAudit = auditEvent({ id: 'ignore-audit', status: 'ignored_closed', action: '忽略误报并归档' })
    decideIssueMock.mockResolvedValue(jsonResponse({
      ok: true,
      decision: 'ignore',
      effect: { verification: { issue_closed: true, alarm_removed: true } },
      audit_event: returnedAudit
    }))
    const { workflow, apiAlerts, selectedAlarmId, auditEvents, alarmFeedback, resolvedEffects, fetchAuditEvents } = createWorkflow()

    await workflow.ignoreAlarm(displayAlarm(apiAlerts.value[0]))

    expect(decideIssueMock).toHaveBeenCalledWith('ALM-1', 'ignore', '人工判定 主轴温度过高 为误报或无需处置。', 'line-lead')
    expect(apiAlerts.value.map((alert) => alert.issue_id)).toEqual(['ALM-2'])
    expect(selectedAlarmId.value).toBe('ALM-2')
    expect(auditEvents.value[0]).toEqual(returnedAudit)
    expect(resolvedEffects.value[0]).toContain('忽略关闭')
    expect(alarmFeedback.value).toContain('关闭并归档到日志管理')
    expect(fetchAuditEvents).toHaveBeenCalled()
  })

  it('approves a human escalation, clears the escalation queue, removes the matching alert, and archives the decision', async () => {
    const returnedAudit = auditEvent({ id: 'human-audit', source: 'human-escalation', action: '批准执行' })
    decideEscalationMock.mockResolvedValue(jsonResponse({
      ok: true,
      escalation: { id: 7, issue_id: 'ALM-1' },
      effect: { issue_id: 'ALM-1', verification: { issue_closed: true, alarm_removed: true } },
      notification: { detail: '人工确认已执行：MILL-02 主轴温度过高' },
      audit_event: returnedAudit
    }))
    const {
      workflow,
      apiAlerts,
      escalationQueue,
      escalationConfirmCodes,
      auditEvents,
      selectedAlarmId,
      resolvedEffects,
      liveLogs
    } = createWorkflow()
    escalationQueue.value = [{ id: 7, node_code: 'milling-workshop-01', issue_type: '主轴温度过高', description: '等待确认', status: 'waiting_human' }]
    escalationConfirmCodes.value[7] = 'CONFIRM'

    await workflow.decideEscalation(escalationQueue.value[0], 'approve')

    expect(decideEscalationMock).toHaveBeenCalledWith(7, 'approve', 'CONFIRM', 'line-lead')
    expect(escalationQueue.value).toEqual([])
    expect(apiAlerts.value.map((alert) => alert.issue_id)).toEqual(['ALM-2'])
    expect(selectedAlarmId.value).toBe('ALM-2')
    expect(auditEvents.value[0]).toEqual(returnedAudit)
    expect(escalationConfirmCodes.value[7]).toBeUndefined()
    expect(resolvedEffects.value[0]).toContain('人工确认已执行')
    expect(liveLogs.value[0]).toContain('人工决策完成')
  })
})
