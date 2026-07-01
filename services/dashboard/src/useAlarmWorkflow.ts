import { computed, type ComputedRef, type Ref } from 'vue'
import {
  closeIssue,
  confirmAlert,
  decideEscalation as decideEscalationRequest,
  decideIssue,
  diagnoseIssue,
  diagnosePayload,
  escalateIssue,
  isolateNode as isolateNodeRequest
} from './operationsApi'
import type { Alarm, ApiAlert, ApiDiagnosis, AuditEvent, EscalationItem } from './types'
import { verificationSummary } from './verification'
import type { SoundKind } from './soundPolicy'

export type AlarmActions = {
  confirm: boolean
  diagnose: boolean
  isolate: boolean
  observe: boolean
  ignore: boolean
  escalate: boolean
  close: boolean
}

export type AlarmWorkflowContext = {
  selectedAlarm: ComputedRef<Alarm | undefined>
  latestDiagnosisForSelected: ComputedRef<ApiDiagnosis | undefined>
  displayAlarms: ComputedRef<Alarm[]>
  apiAlerts: Ref<ApiAlert[]>
  apiDiagnoses: Ref<ApiDiagnosis[]>
  escalationQueue: Ref<EscalationItem[]>
  escalationConfirmCodes: Ref<Record<number, string>>
  auditEvents: Ref<AuditEvent[]>
  alarmActionLoading: Ref<string | null>
  aiDiagnosisResult: Ref<string | null>
  alarmFeedback: Ref<string>
  selectedAlarmId: Ref<string>
  resolvedEffects: Ref<string[]>
  liveLogs: Ref<string[]>
  loadDashboardState: () => Promise<void>
  fetchAuditEvents: () => Promise<void>
  fetchAlarmData: () => Promise<void>
  currentTime: () => string
  currentOperator: () => string
  playSound: (kind: SoundKind) => void
  promptForConfirmation?: (message: string) => string | null
}

const disabledActions: AlarmActions = {
  confirm: false,
  diagnose: false,
  isolate: false,
  observe: false,
  ignore: false,
  escalate: false,
  close: false
}

export function actionsForAlarm(status: Alarm['status'] | undefined, diagnosis?: ApiDiagnosis): AlarmActions {
  if (!status) return { ...disabledActions }
  const confirm = status === 'unacknowledged'
  const diagnose = status === 'confirmed'
  const decide = status === 'diagnosed'
  const isolate = decide && Boolean(diagnosis?.need_isolation)
  const observe = decide
  const ignore = decide || status === 'observing'
  const close = status === 'contained' || status === 'observing'
  const escalate = status === 'confirmed' || status === 'diagnosed' || status === 'observing'
  return { confirm, diagnose, isolate, observe, ignore, escalate, close }
}

export function mergeReturnedAuditEvent(events: AuditEvent[], event?: AuditEvent): AuditEvent[] {
  if (!event) return events
  return [event, ...events.filter((item) => item.id !== event.id)]
}

function pushResolvedEffect(effects: string[], message: string): string[] {
  return [message, ...effects].slice(0, 3)
}

export function useAlarmWorkflow(ctx: AlarmWorkflowContext) {
  const alarmActions = computed(() => actionsForAlarm(ctx.selectedAlarm.value?.status, ctx.latestDiagnosisForSelected.value))

  function updateEscalationCode(id: number, code: string) {
    ctx.escalationConfirmCodes.value[id] = code
  }

  function selectAlarm(alarmId: string) {
    ctx.selectedAlarmId.value = alarmId
    ctx.alarmFeedback.value = ''
    ctx.aiDiagnosisResult.value = null
  }

  async function confirmAlarm(alarm: Alarm) {
    ctx.alarmActionLoading.value = alarm.id
    ctx.alarmFeedback.value = ''
    try {
      const res = await confirmAlert(alarm.id, ctx.currentOperator())
      const data = await res.json()
      if (res.ok && data.ok) {
        ctx.apiAlerts.value = ctx.apiAlerts.value.map((item) => item.issue_id === alarm.id ? { ...item, status: 'confirmed' } : item)
        ctx.liveLogs.value.unshift(`${ctx.currentTime()} 已确认报警：${alarm.title}`)
        ctx.alarmFeedback.value = '报警已确认为真实事件，下一步可执行 AI 诊断或升级人工处理。'
        ctx.playSound('notice')
      } else {
        ctx.alarmFeedback.value = data.message ?? data.error ?? `确认失败 (${res.status})`
        ctx.playSound('error')
      }
    } catch {
      ctx.alarmFeedback.value = '确认失败，后端无法连接'
      ctx.playSound('error')
    } finally {
      ctx.alarmActionLoading.value = null
      await ctx.fetchAlarmData()
    }
  }

  async function runAiDiagnose(alarm: Alarm) {
    ctx.alarmActionLoading.value = alarm.id
    ctx.aiDiagnosisResult.value = null
    ctx.alarmFeedback.value = ''
    try {
      let res = await diagnoseIssue(alarm.id)
      let data = res.ok ? await res.json() : null
      if (!res.ok || data?.ok === false) {
        res = await diagnosePayload({
          node_code: alarm.machine,
          alert_description: alarm.value,
          alert_type: alarm.title,
          severity: alarm.severity === 'critical' ? 'critical' : 'warning'
        })
        data = res.ok ? await res.json() : null
      }
      if (res.ok) {
        const decision = data.decision ?? data
        const rootCause = data.root_cause ?? decision.root_cause_hypotheses?.slice(0, 2).join('；')
        const recommended = data.recommended_action ?? decision.recommended_plan?.slice(0, 2).join('；')
        const sourceLabel = decision.source === 'api' ? '真实模型 API' : '规则回退'
        ctx.aiDiagnosisResult.value = `来源：${sourceLabel} / ${decision.provider || data.provider || 'unknown'} / ${decision.model || data.model_name || 'unknown'} ~ 根因：${rootCause || '分析中...'} ~ 建议：${recommended || '等待诊断结果...'} ~ 置信度：${Math.round((decision.confidence || data.confidence || 0) * 100)}%`
        ctx.liveLogs.value.unshift(`${ctx.currentTime()} AI 诊断完成：${alarm.title}`)
        ctx.alarmFeedback.value = 'AI 诊断已完成'
        ctx.apiAlerts.value = ctx.apiAlerts.value.map((item) => item.issue_id === alarm.id ? { ...item, status: 'diagnosed' } : item)
        ctx.playSound('success')
      } else {
        const errText = await res.text().catch(() => '')
        ctx.alarmFeedback.value = `AI 诊断失败 (${res.status}): ${errText || '请重试'}`
        ctx.playSound('error')
      }
    } catch {
      ctx.alarmFeedback.value = 'AI 诊断失败，后端无法连接'
      ctx.playSound('error')
    } finally {
      ctx.alarmActionLoading.value = null
      await ctx.fetchAlarmData()
    }
  }

  async function isolateNode(alarm: Alarm) {
    ctx.alarmActionLoading.value = alarm.id
    ctx.alarmFeedback.value = ''
    const ask = ctx.promptForConfirmation ?? window.prompt
    const confirmationCode = ask(`隔离 ${alarm.machine} 需要确认码，请输入 CONFIRM。`)
    if (confirmationCode === null) {
      ctx.alarmActionLoading.value = null
      return
    }
    try {
      const res = await isolateNodeRequest(alarm.machine, confirmationCode, ctx.currentOperator())
      const data = await res.json()
      if (res.ok && data.ok) {
        ctx.apiAlerts.value = ctx.apiAlerts.value.map((item) => item.issue_id === alarm.id ? { ...item, status: 'contained' } : item)
        ctx.auditEvents.value = mergeReturnedAuditEvent(ctx.auditEvents.value, data.audit_event)
        ctx.liveLogs.value.unshift(`${ctx.currentTime()} 节点隔离已执行：${alarm.machine}`)
        ctx.alarmFeedback.value = '隔离已执行，结果已归档；请验证后关闭问题。'
        ctx.playSound('critical')
        await ctx.loadDashboardState()
        await ctx.fetchAuditEvents()
      } else {
        ctx.alarmFeedback.value = data.message ?? data.error ?? `隔离操作失败 (${res.status})`
        ctx.playSound('error')
      }
    } catch {
      ctx.alarmFeedback.value = '隔离操作失败，后端无法连接'
      ctx.playSound('error')
    } finally {
      ctx.alarmActionLoading.value = null
      await ctx.fetchAlarmData()
    }
  }

  async function escalateToHuman(alarm: Alarm) {
    ctx.alarmActionLoading.value = alarm.id
    ctx.alarmFeedback.value = ''
    try {
      const res = await escalateIssue({
        nodeCode: alarm.machine,
        issueType: alarm.title,
        description: `人工升级：${alarm.value}`,
        actor: ctx.currentOperator()
      })
      if (res.ok) {
        ctx.liveLogs.value.unshift(`${ctx.currentTime()} 已升级到人工处理：${alarm.title}`)
        ctx.alarmFeedback.value = '已升级到人工处理队列'
        ctx.playSound('warning')
      } else {
        const errText = await res.text().catch(() => '')
        ctx.alarmFeedback.value = `升级失败 (${res.status}): ${errText || '请重试'}`
        ctx.playSound('error')
      }
    } catch {
      ctx.alarmFeedback.value = '升级失败，后端无法连接'
      ctx.playSound('error')
    } finally {
      ctx.alarmActionLoading.value = null
      await ctx.fetchAlarmData()
    }
  }

  async function observeAlarm(alarm: Alarm) {
    ctx.alarmActionLoading.value = alarm.id
    ctx.alarmFeedback.value = ''
    try {
      const res = await decideIssue(alarm.id, 'observe', `继续观察 ${alarm.machine}，保留后续验证入口。`, ctx.currentOperator())
      const data = await res.json()
      if (!res.ok || !data.ok) {
        ctx.alarmFeedback.value = data.message ?? data.error ?? '观察决策失败'
        ctx.playSound('error')
        return
      }
      ctx.apiAlerts.value = ctx.apiAlerts.value.map((item) => item.issue_id === alarm.id ? { ...item, status: 'observing' } : item)
      ctx.auditEvents.value = mergeReturnedAuditEvent(ctx.auditEvents.value, data.audit_event)
      ctx.alarmFeedback.value = '已进入观察状态，节点保持运行；后续仍需验证关闭或升级处置。'
      ctx.liveLogs.value.unshift(`${ctx.currentTime()} 观察决策：${alarm.title} / ${alarm.machine}`)
      ctx.playSound('notice')
      await ctx.fetchAuditEvents()
    } catch {
      ctx.alarmFeedback.value = '观察决策失败，后端无法连接'
      ctx.playSound('error')
    } finally {
      ctx.alarmActionLoading.value = null
      await ctx.fetchAlarmData()
    }
  }

  async function ignoreAlarm(alarm: Alarm) {
    ctx.alarmActionLoading.value = alarm.id
    ctx.alarmFeedback.value = ''
    try {
      const res = await decideIssue(alarm.id, 'ignore', `人工判定 ${alarm.title} 为误报或无需处置。`, ctx.currentOperator())
      const data = await res.json()
      if (!res.ok || !data.ok) {
        ctx.alarmFeedback.value = data.message ?? data.error ?? '忽略失败'
        ctx.playSound('error')
        return
      }
      ctx.apiAlerts.value = ctx.apiAlerts.value.filter((item) => item.issue_id !== alarm.id)
      ctx.selectedAlarmId.value = ctx.displayAlarms.value[0]?.id ?? ''
      ctx.auditEvents.value = mergeReturnedAuditEvent(ctx.auditEvents.value, data.audit_event)
      ctx.resolvedEffects.value = pushResolvedEffect(
        ctx.resolvedEffects.value,
        `${ctx.currentTime()} 已归档：${alarm.title} / ${alarm.machine} / 忽略关闭`
      )
      ctx.alarmFeedback.value = '已按误报/无需处置关闭并归档到日志管理。'
      ctx.liveLogs.value.unshift(`${ctx.currentTime()} 忽略并归档：${alarm.title} / ${alarm.machine}`)
      ctx.playSound('success')
      await ctx.loadDashboardState()
      await ctx.fetchAuditEvents()
    } catch {
      ctx.alarmFeedback.value = '忽略失败，后端无法连接'
      ctx.playSound('error')
    } finally {
      ctx.alarmActionLoading.value = null
      await ctx.fetchAlarmData()
    }
  }

  async function closeAlarm(alarm: Alarm) {
    ctx.alarmActionLoading.value = alarm.id
    ctx.alarmFeedback.value = ''
    try {
      const response = await closeIssue(alarm.id, '验证完成并关闭问题', ctx.currentOperator())
      const data = await response.json()
      if (!response.ok || !data.ok) {
        ctx.alarmFeedback.value = data.message ?? data.error ?? '关闭失败'
        ctx.playSound('error')
        return
      }
      ctx.apiAlerts.value = ctx.apiAlerts.value.filter((item) => item.issue_id !== alarm.id)
      ctx.selectedAlarmId.value = ctx.displayAlarms.value[0]?.id ?? ''
      ctx.auditEvents.value = mergeReturnedAuditEvent(ctx.auditEvents.value, data.audit_event)
      ctx.alarmFeedback.value = `问题已关闭并归档到日志管理。${verificationSummary(data.effect) || ''}`
      ctx.resolvedEffects.value = pushResolvedEffect(
        ctx.resolvedEffects.value,
        `${ctx.currentTime()} 已归档：${alarm.title} / ${alarm.machine} / 验证关闭`
      )
      ctx.playSound('success')
      await ctx.loadDashboardState()
      await ctx.fetchAuditEvents()
    } catch {
      ctx.alarmFeedback.value = '关闭失败，后端无法连接'
      ctx.playSound('error')
    } finally {
      ctx.alarmActionLoading.value = null
      await ctx.fetchAlarmData()
    }
  }

  async function decideEscalation(item: EscalationItem, decision: 'approve' | 'reject') {
    if (!item.id) return
    ctx.alarmActionLoading.value = `escalation-${item.id}`
    ctx.alarmFeedback.value = ''
    try {
      const res = await decideEscalationRequest(
        item.id,
        decision,
        ctx.escalationConfirmCodes.value[item.id] ?? '',
        ctx.currentOperator()
      )
      const data = await res.json()
      if (!res.ok || !data.ok) {
        ctx.alarmFeedback.value = data.message ?? data.error ?? '人工决策失败'
        ctx.playSound('error')
        return
      }
      const result = data.notification?.detail ?? (decision === 'approve' ? '人工确认已执行' : '人工驳回已关闭')
      ctx.alarmFeedback.value = `${result}${verificationSummary(data.effect) ? ` / ${verificationSummary(data.effect)}` : ''}`
      const resolvedIssueId = data.effect?.issue_id ?? data.escalation?.issue_id
      ctx.escalationQueue.value = ctx.escalationQueue.value.filter((entry) => entry.id !== item.id)
      ctx.apiAlerts.value = ctx.apiAlerts.value.filter((alert) => {
        const sameIssue = resolvedIssueId && alert.issue_id === resolvedIssueId
        const sameNodeAndTitle = alert.node_code === item.node_code && alert.alert_type === item.issue_type
        return !(sameIssue || sameNodeAndTitle)
      })
      ctx.selectedAlarmId.value = ctx.displayAlarms.value[0]?.id ?? ''
      ctx.resolvedEffects.value.unshift(`${ctx.currentTime()} ${ctx.alarmFeedback.value}`)
      ctx.resolvedEffects.value = ctx.resolvedEffects.value.slice(0, 3)
      ctx.auditEvents.value = mergeReturnedAuditEvent(ctx.auditEvents.value, data.audit_event)
      delete ctx.escalationConfirmCodes.value[item.id]
      ctx.liveLogs.value.unshift(`${ctx.currentTime()} 人工决策完成：${item.issue_type} / ${decision === 'approve' ? '批准' : '驳回'}`)
      ctx.playSound(decision === 'approve' ? 'success' : 'notice')
      await ctx.loadDashboardState()
      await ctx.fetchAuditEvents()
    } catch {
      ctx.alarmFeedback.value = '人工决策失败，后端无法连接'
      ctx.playSound('error')
    } finally {
      ctx.alarmActionLoading.value = null
      await ctx.fetchAlarmData()
    }
  }

  return {
    alarmActions,
    updateEscalationCode,
    selectAlarm,
    confirmAlarm,
    runAiDiagnose,
    isolateNode,
    escalateToHuman,
    observeAlarm,
    ignoreAlarm,
    closeAlarm,
    decideEscalation
  }
}
