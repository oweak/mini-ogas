import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { approveDispatchPlan as approveDispatchPlanRequest, recalculateDispatchPlan as recalculateDispatchPlanRequest } from './operationsApi'
import type { AuditEvent, DispatchPlan, HostWorkOrder } from './types'
import { useDispatchWorkflow } from './useDispatchWorkflow'

vi.mock('./operationsApi', () => ({
  approveDispatchPlan: vi.fn(),
  recalculateDispatchPlan: vi.fn()
}))

const recalculateMock = vi.mocked(recalculateDispatchPlanRequest)
const approveMock = vi.mocked(approveDispatchPlanRequest)

function jsonResponse(body: unknown, ok = true) {
  return new Response(JSON.stringify(body), {
    status: ok ? 200 : 400,
    headers: { 'Content-Type': 'application/json' }
  })
}

function pendingPlan(overrides: Partial<DispatchPlan> = {}): DispatchPlan {
  return {
    id: 'dispatch-1',
    status: 'waiting_approval',
    summary: '重排受阻铣削产量',
    source_order: 'WO-1',
    from_node: 'milling-workshop-01',
    to_node: 'turning-workshop-01',
    risk: 'medium',
    steps: ['转移剩余产量'],
    ...overrides
  }
}

function createWorkflow(dispatchPlan = ref<DispatchPlan | null>(null)) {
  const hostWorkOrders = ref<HostWorkOrder[]>([])
  const auditEvents = ref<AuditEvent[]>([])
  const resolvedEffects = ref<string[]>([])
  const liveLogs = ref<string[]>([])
  const playSound = vi.fn()
  const loadDashboardState = vi.fn(async () => {})
  const fetchAlarmData = vi.fn(async () => {})
  const fetchAuditEvents = vi.fn(async () => {})
  const workflow = useDispatchWorkflow({
    dispatchPlan,
    hostWorkOrders,
    auditEvents,
    resolvedEffects,
    liveLogs,
    currentTime: () => '10:30:00',
    currentOperator: () => 'line-lead',
    playSound,
    loadDashboardState,
    fetchAlarmData,
    fetchAuditEvents
  })
  return {
    workflow,
    dispatchPlan,
    hostWorkOrders,
    auditEvents,
    resolvedEffects,
    liveLogs,
    playSound,
    loadDashboardState,
    fetchAlarmData,
    fetchAuditEvents
  }
}

describe('useDispatchWorkflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('recalculates a dispatch plan and exposes the approval state', async () => {
    const nextPlan = pendingPlan()
    const workOrders = [{ id: 'WO-1', product: '阀体', quantity: 20, priority: 'P1', route: ['milling'], assigned_node: 'milling-workshop-01', status: 'in_progress' }]
    recalculateMock.mockResolvedValue(jsonResponse({ ok: true, dispatch_plan: nextPlan, work_orders: workOrders }))
    const { workflow, dispatchPlan, hostWorkOrders, liveLogs, playSound } = createWorkflow()

    await workflow.recalculateDispatchPlan()

    expect(dispatchPlan.value).toEqual(nextPlan)
    expect(hostWorkOrders.value).toEqual(workOrders)
    expect(workflow.dispatchAwaitingApproval.value).toBe(true)
    expect(workflow.dispatchFeedback.value).toContain('等待车间主管确认')
    expect(liveLogs.value[0]).toContain('调度方案已重算')
    expect(playSound).toHaveBeenCalledWith('notice')
  })

  it('blocks approval when no dispatch plan is waiting', async () => {
    const { workflow, playSound } = createWorkflow(ref(pendingPlan({ status: 'no_action' })))

    await workflow.approveDispatchPlan()

    expect(approveMock).not.toHaveBeenCalled()
    expect(workflow.dispatchFeedbackKind.value).toBe('error')
    expect(workflow.dispatchFeedback.value).toContain('当前没有等待审批')
    expect(playSound).toHaveBeenCalledWith('error')
  })

  it('archives and refreshes state after approval succeeds', async () => {
    const auditEvent = {
      id: 'audit-1',
      time: '2026-06-03T10:30:00',
      actor: '车间主管',
      role: 'supervisor',
      permission: 'dispatch.approve',
      subject: 'dispatch',
      action: 'approve',
      result: 'executed',
      status: 'closed',
      source: 'dispatch'
    }
    approveMock.mockResolvedValue(jsonResponse({
      ok: true,
      dispatch_plan: pendingPlan({ status: 'approved_executed', result: '已转移剩余产量' }),
      work_orders: [],
      audit_event: auditEvent
    }))
    const {
      workflow,
      auditEvents,
      resolvedEffects,
      liveLogs,
      playSound,
      loadDashboardState,
      fetchAlarmData,
      fetchAuditEvents
    } = createWorkflow(ref(pendingPlan()))
    workflow.dispatchConfirmCode.value = 'CONFIRM'

    await workflow.approveDispatchPlan()

    expect(approveMock).toHaveBeenCalledWith('CONFIRM', 'line-lead')
    expect(workflow.dispatchConfirmCode.value).toBe('')
    expect(workflow.dispatchFeedbackKind.value).toBe('success')
    expect(workflow.dispatchFeedback.value).toContain('已归档至日志管理')
    expect(auditEvents.value[0]).toEqual(auditEvent)
    expect(resolvedEffects.value[0]).toContain('调度变更已执行')
    expect(liveLogs.value[0]).toContain('调度批准执行')
    expect(playSound).toHaveBeenCalledWith('success')
    expect(loadDashboardState).toHaveBeenCalled()
    expect(fetchAlarmData).toHaveBeenCalled()
    expect(fetchAuditEvents).toHaveBeenCalled()
  })

  it('does not archive a dispatch while the node and verifier are still running', async () => {
    approveMock.mockResolvedValue(jsonResponse({
      ok: true,
      dispatch_plan: pendingPlan({
        status: 'approved_executing',
        result: 'waiting for the bound node agent and Verifier evidence'
      }),
      work_orders: []
    }))
    const { workflow, resolvedEffects } = createWorkflow(ref(pendingPlan()))
    workflow.dispatchConfirmCode.value = 'CONFIRM'

    await workflow.approveDispatchPlan()

    expect(workflow.dispatchFeedback.value).toContain('waiting for the bound node agent')
    expect(workflow.dispatchPanelTitle.value).toContain('等待节点执行与验证')
    expect(resolvedEffects.value).toEqual([])
  })
})
