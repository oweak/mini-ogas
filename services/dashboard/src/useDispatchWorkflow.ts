import { computed, ref, type Ref } from 'vue'
import {
  approveDispatchPlan as approveDispatchPlanRequest,
  recalculateDispatchPlan as recalculateDispatchPlanRequest
} from './operationsApi'
import type { AuditEvent, DispatchPlan, HostWorkOrder } from './types'
import type { SoundKind } from './soundPolicy'

type DispatchFeedbackKind = 'info' | 'success' | 'error'
type DispatchLoading = 'recalculate' | 'approve' | null

type DispatchWorkflowOptions = {
  dispatchPlan: Ref<DispatchPlan | null>
  hostWorkOrders: Ref<HostWorkOrder[]>
  auditEvents: Ref<AuditEvent[]>
  resolvedEffects: Ref<string[]>
  liveLogs: Ref<string[]>
  currentTime: () => string
  currentOperator: () => string
  playSound: (kind: SoundKind) => void
  loadDashboardState: () => Promise<void>
  fetchAlarmData: () => Promise<void>
  fetchAuditEvents: () => Promise<void>
}

type DispatchApiResponse = {
  ok?: boolean
  error?: string
  message?: string
  dispatch_plan?: DispatchPlan
  work_orders?: HostWorkOrder[]
  audit_event?: AuditEvent
}

async function parseDispatchResponse(response: Response): Promise<DispatchApiResponse> {
  return await response.json()
}

export function useDispatchWorkflow(options: DispatchWorkflowOptions) {
  const dispatchConfirmCode = ref('')
  const dispatchFeedback = ref('')
  const dispatchFeedbackKind = ref<DispatchFeedbackKind>('info')
  const dispatchLoading = ref<DispatchLoading>(null)

  const dispatchAwaitingApproval = computed(() => options.dispatchPlan.value?.status === 'waiting_approval')
  const dispatchPanelTitle = computed(() => {
    if (options.dispatchPlan.value?.status === 'waiting_approval') return '待批准调度变更'
    if (options.dispatchPlan.value?.status === 'approved_executing') return '已批准，等待节点执行与验证'
    if (options.dispatchPlan.value?.status === 'approved_executed') return '调度变更已执行并验证'
    if (options.dispatchPlan.value?.status === 'no_action') return '当前无需调度变更'
    return '调度状态评估'
  })
  const dispatchApprovalLabel = computed(() => {
    if (dispatchAwaitingApproval.value) return '审批：需要系统管理员输入确认码'
    if (options.dispatchPlan.value?.status === 'approved_executing') {
      return '执行：节点领取后由 Verifier 判断实际效果'
    }
    return '审批：暂无待批准方案'
  })

  async function recalculateDispatchPlan() {
    dispatchLoading.value = 'recalculate'
    dispatchFeedback.value = ''
    dispatchFeedbackKind.value = 'info'
    try {
      const res = await recalculateDispatchPlanRequest()
      const data = await parseDispatchResponse(res)
      if (!res.ok || !data.ok || !data.dispatch_plan) throw new Error(data.error ?? '调度重算失败')
      options.dispatchPlan.value = data.dispatch_plan
      options.hostWorkOrders.value = data.work_orders ?? options.hostWorkOrders.value
      dispatchFeedback.value = options.dispatchPlan.value.status === 'waiting_approval'
        ? '调度方案已重新计算，等待车间主管确认。'
        : (options.dispatchPlan.value.result ?? '当前工况稳定，无需调度变更。')
      dispatchFeedbackKind.value = options.dispatchPlan.value.status === 'waiting_approval' ? 'info' : 'success'
      options.liveLogs.value.unshift(`${options.currentTime()} 调度方案已重算：${options.dispatchPlan.value.summary}`)
      options.playSound('notice')
    } catch (error) {
      dispatchFeedback.value = error instanceof Error ? error.message : '调度重算失败'
      dispatchFeedbackKind.value = 'error'
      options.playSound('error')
    } finally {
      dispatchLoading.value = null
    }
  }

  async function approveDispatchPlan() {
    if (!dispatchAwaitingApproval.value) {
      dispatchFeedback.value = '当前没有等待审批的调度方案，请先重新计算计划。'
      dispatchFeedbackKind.value = 'error'
      options.playSound('error')
      return
    }
    dispatchLoading.value = 'approve'
    dispatchFeedback.value = ''
    dispatchFeedbackKind.value = 'info'
    try {
      const res = await approveDispatchPlanRequest(dispatchConfirmCode.value, options.currentOperator())
      const data = await parseDispatchResponse(res)
      if (!res.ok || !data.ok || !data.dispatch_plan) {
        dispatchFeedback.value = data.message ?? data.error ?? '调度批准失败'
        dispatchFeedbackKind.value = 'error'
        options.playSound('error')
        return
      }
      options.dispatchPlan.value = data.dispatch_plan
      options.hostWorkOrders.value = data.work_orders ?? options.hostWorkOrders.value
      if (data.audit_event) {
        options.auditEvents.value = [
          data.audit_event,
          ...options.auditEvents.value.filter((event) => event.id !== data.audit_event?.id)
        ]
      }
      dispatchConfirmCode.value = ''
      dispatchFeedback.value = data.dispatch_plan.status === 'approved_executing'
        ? (data.dispatch_plan.result ?? '调度变更已批准，等待节点领取、执行和效果验证。')
        : `${data.dispatch_plan.result ?? '调度变更已执行并验证。'} 已归档至日志管理。`
      dispatchFeedbackKind.value = 'success'
      if (data.dispatch_plan.status !== 'approved_executing') {
        options.resolvedEffects.value.unshift(`${options.currentTime()} 调度变更已执行：${dispatchFeedback.value}`)
        options.resolvedEffects.value = options.resolvedEffects.value.slice(0, 3)
      }
      options.liveLogs.value.unshift(`${options.currentTime()} 调度批准执行：${dispatchFeedback.value}`)
      options.playSound('success')
      await options.loadDashboardState()
      await options.fetchAlarmData()
      await options.fetchAuditEvents()
    } catch {
      dispatchFeedback.value = '调度批准失败，后端无法连接'
      dispatchFeedbackKind.value = 'error'
      options.playSound('error')
    } finally {
      dispatchLoading.value = null
    }
  }

  return {
    dispatchConfirmCode,
    dispatchFeedback,
    dispatchFeedbackKind,
    dispatchLoading,
    dispatchAwaitingApproval,
    dispatchPanelTitle,
    dispatchApprovalLabel,
    recalculateDispatchPlan,
    approveDispatchPlan
  }
}
