<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiFetch } from './apiClient'
import AlarmManagementView from './AlarmManagementView.vue'
import DataQualityView from './DataQualityView.vue'
import FactoryRuntimeView from './FactoryRuntimeView.vue'
import LogManagementView from './LogManagementView.vue'
import OrderDispatchView from './OrderDispatchView.vue'
import ProductionReportView from './ProductionReportView.vue'
import ReplayTimelineView from './ReplayTimelineView.vue'
import StartupGate from './StartupGate.vue'
import { useProtectedPolling } from './protectedPolling'
import { createRuleExplanationRefreshGate, ruleExplanationSignature } from './ruleExplanationRefresh'
import { closeIssue } from './operationsApi'
import type { AiRuleExplanation, Alarm, ApiAlert, ApiDiagnosis, AuditEvent, DashboardSnapshot, DispatchPlan, EscalationItem, HostNode, HostWorkOrder, LogEvent, MachineState, NodeSyncRecord, PartQueueSnapshot, RuleConclusion, RuntimeDashboardState } from './types'
import { activeDashboardIssues, dashboardSnapshotToState, mergeAlarmFetchResults, normalizeAuditEvents, responseToFetchSlot, snapshotSummary, visibleRuntimeEvents } from './runtimeState'
import { alertSoundForNewIssues, soundGain, soundPatterns, type SoundKind } from './soundPolicy'
import { useAlarmWorkflow } from './useAlarmWorkflow'
import { useDispatchWorkflow } from './useDispatchWorkflow'
import { useEmergencyDemoWorkflow } from './useEmergencyDemoWorkflow'
import { useRuntimePresentation } from './useRuntimePresentation'
import { useStartupWorkflow } from './useStartupWorkflow'
import { verificationSummary } from './verification'

type ViewKey = 'factory' | 'orders' | 'alarms' | 'quality' | 'logs' | 'replay' | 'reports' | 'demo'

const activeView = ref<ViewKey>('factory')
const selectedAlarmId = ref('')
const runtimeTick = ref(0)
const apiIssues = ref<IssuePopup[] | null>(null)
const apiAvailable = ref(false)
const resolvedEffects = ref<string[]>([])
const hostWorkOrders = ref<HostWorkOrder[]>([])
const hostNodes = ref<HostNode[]>([])
const dispatchPlan = ref<DispatchPlan | null>(null)
const runtimeSnapshot = ref<DashboardSnapshot | null>(null)
const aiRuleExplanation = ref<AiRuleExplanation | null>(null)
const aiRuleExplanationLoading = ref(false)
const ruleExplanationRefreshGate = createRuleExplanationRefreshGate()
const escalationConfirmCodes = ref<Record<number, string>>({})
// --- alarm page real data ---
const apiAlerts = ref<ApiAlert[]>([])
const apiDiagnoses = ref<ApiDiagnosis[]>([])
const escalationQueue = ref<EscalationItem[]>([])
const auditEvents = ref<AuditEvent[]>([])
const alarmActionLoading = ref<string | null>(null)
const aiDiagnosisResult = ref<string | null>(null)
const alarmFeedback = ref('')
const logEvents = ref<LogEvent[]>([])
const nodeSyncRecords = ref<NodeSyncRecord[]>([])
const soundArmed = ref(false)
let audioContext: AudioContext | null = null
let knownIssueIds = new Set<string>()
const liveLogs = ref(['--:--:-- 等待 central-api 运行日志'])

const {
  demoMode,
  aiGuideVisible,
  emergencyStep,
  handledActions,
  dismissedIssues,
  demoScenario,
  emergencyGuideStages,
  activeDemo,
  liveOutput,
  liveTemp,
  liveWear,
  pendingRecords,
  heartbeatStatus,
  setDemoMode,
  selectTreatment,
  advanceEmergencyStep,
  clearEmergencyTimer
} = useEmergencyDemoWorkflow({
  runtimeTick,
  liveLogs,
  currentTime,
  playSound,
  loadDashboardState
})

const {
  loginOperator,
  loginPassword,
  loginFeedback,
  loginLoading,
  systemUnlocked,
  gatePhase,
  authRuntime,
  preflightLoading,
  preflight,
  loginRequired,
  startupChecks,
  animatedStartupChecks,
  bootProgress,
  aiRuntimeLabel,
  aiSmokeTruth,
  fetchAuthStatus,
  runPreflight,
  loginAdmin,
  lockSystem,
  clearPreflightTimer
} = useStartupWorkflow({
  apiAvailable,
  liveLogs,
  soundArmed,
  currentTime,
  playSound,
  ensureAudioContext,
  loadDashboardState
})

const {
  dispatchConfirmCode,
  dispatchFeedback,
  dispatchFeedbackKind,
  dispatchLoading,
  dispatchAwaitingApproval,
  dispatchPanelTitle,
  dispatchApprovalLabel,
  recalculateDispatchPlan,
  approveDispatchPlan
} = useDispatchWorkflow({
  dispatchPlan,
  hostWorkOrders,
  auditEvents,
  resolvedEffects,
  liveLogs,
  currentTime,
  currentOperator: () => loginOperator.value || '车间主管',
  playSound,
  loadDashboardState,
  fetchAlarmData,
  fetchAuditEvents
})

type IssuePopup = {
  id: string
  severity: string
  title: string
  detail: string
  actions: string[]
  status?: string
}

const displayAlarms = computed<Alarm[]>(() => {
  return apiAlerts.value
    .filter((a) => {
      const issueKey = String(a.issue_id ?? a.id ?? '')
      return (
        !a.handled_by &&
        a.status !== 'resolved' &&
        !/^(NOTICE|RESULT|HUMAN|DISPATCH)-/.test(issueKey)
      )
    })
    .map((a) => ({
      id: a.issue_id ?? String(a.id),
      severity: (a.severity === 'critical' ? 'critical' : a.severity === 'warning' ? 'high' : 'medium') as Alarm['severity'],
      machine: a.node_code,
      title: a.alert_type,
      value: a.description,
      status: normalizeAlarmStatus(a.status),
      rule: buildRuleText(a),
      aiSuggestion: '',
      requiredRole: a.severity === 'critical' ? '车间主管' : '操作员'
    }))
})

function normalizeAlarmStatus(status?: string): Alarm['status'] {
  if (status === 'confirmed') return 'confirmed'
  if (status === 'diagnosed') return 'diagnosed'
  if (status === 'contained') return 'contained'
  if (status === 'observing') return 'observing'
  return 'unacknowledged'
}

function buildRuleText(alert: ApiAlert) {
  const title = alert.alert_type
  if (title.includes('主轴温度')) return '规则：主轴温度超过设备阈值，且持续心跳未恢复，必须进入人工确认。'
  if (title.includes('冷却液')) return '规则：冷却回路流量低于工艺下限，先降载并检查泵路与液位。'
  if (title.includes('良品率')) return '规则：良品率低于工单质量窗口，触发首件复检、刀补复核与抽检。'
  if (title.includes('振动')) return '规则：振动超过安全阈值，可能涉及夹具、刀具或轴承风险。'
  if (title.includes('磨损')) return '规则：刀具/砂轮磨损超过预警阈值，限制进给并安排维护。'
  if (title.includes('同步')) return '规则：本地缓存积压超过阈值，触发通信链路检查与补传策略。'
  return `规则：${title} 已由节点心跳触发，等待诊断与处置。`
}

const selectedAlarm = computed<Alarm | undefined>(() =>
  displayAlarms.value.find((a) => a.id === selectedAlarmId.value)
)

const diagnosisForSelected = computed(() => {
  return apiDiagnoses.value.filter((d) => String(d.issue_id ?? d.alert_id) === selectedAlarmId.value)
})
const latestDiagnosisForSelected = computed(() => diagnosisForSelected.value[0])
const {
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
} = useAlarmWorkflow({
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
  currentTime,
  currentOperator: () => loginOperator.value || '车间主管',
  playSound
})
const aiRuntimeTruthLabel = computed(() => {
  const item = latestDiagnosisForSelected.value
  const source = item?.source ?? item?.decision?.source ?? authRuntime.value?.source ?? 'unknown'
  if (source === 'api') return '真实模型 API'
  if (source === 'rule_fallback') return '规则回退'
  return source
})

const {
  liveWorkshops,
  machines,
  displayedWorkOrders,
  nodeConnectionSummary,
  nodeRuntimeRows,
  controlServiceRows
} = useRuntimePresentation({
  hostNodes,
  hostWorkOrders,
  apiAvailable,
  aiSmokeTruth,
  auditEvents
})

const activeIssuePopups = computed(() => {
  return (apiIssues.value ?? []).filter((issue) => !dismissedIssues.value.includes(issue.id))
})

function uniqueIssues(items: IssuePopup[]) {
  const seen = new Set<string>()
  return items.filter((item) => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
}

function isResultNotification(issueId: string) {
  return /^(NOTICE|RESULT|HUMAN|DISPATCH)-/.test(issueId)
}

function ensureAudioContext() {
  const audioWindow = window as Window & typeof globalThis & { webkitAudioContext?: typeof AudioContext }
  const AudioContextClass = window.AudioContext || audioWindow.webkitAudioContext
  if (!AudioContextClass) return null
  if (!audioContext) audioContext = new AudioContextClass()
  if (audioContext.state === 'suspended') void audioContext.resume()
  return audioContext
}

function playTone(ctx: AudioContext, frequency: number, start: number, duration: number, gainValue: number) {
  const oscillator = ctx.createOscillator()
  const gain = ctx.createGain()
  oscillator.type = 'sine'
  oscillator.frequency.setValueAtTime(frequency, start)
  gain.gain.setValueAtTime(0.0001, start)
  gain.gain.exponentialRampToValueAtTime(gainValue, start + 0.015)
  gain.gain.exponentialRampToValueAtTime(0.0001, start + duration)
  oscillator.connect(gain)
  gain.connect(ctx.destination)
  oscillator.start(start)
  oscillator.stop(start + duration + 0.02)
}

function playSound(kind: SoundKind) {
  if (!soundArmed.value) return
  const ctx = ensureAudioContext()
  if (!ctx) return
  const now = ctx.currentTime
  soundPatterns[kind].forEach(([frequency, offset, duration]) => {
    playTone(ctx, frequency, now + offset, duration, soundGain(kind))
  })
}
const operatingSummary = computed(() => {
  const running = machines.value.filter((machine) => machine.state === 'running').length
  const fault = machines.value.filter((machine) => machine.state === 'fault').length
  const warning = machines.value.filter((machine) => machine.state === 'warning').length
  const reportedOee = machines.value
    .map((machine) => machine.oee)
    .filter((value): value is number => value !== null)
  const averageOee = reportedOee.length
    ? Math.round(reportedOee.reduce((total, value) => total + value, 0) / reportedOee.length)
    : null

  return { running, fault, warning, averageOee }
})
const systemStateSummary = computed(() => {
  if (operatingSummary.value.fault > 0) {
    return {
      dot: 'fault',
      title: '异常运行',
      detail: `${operatingSummary.value.fault} 个故障，${operatingSummary.value.warning} 个预警，等待处置`
    }
  }
  if (operatingSummary.value.warning > 0) {
    return {
      dot: 'warning',
      title: '关注运行',
      detail: `${operatingSummary.value.warning} 个预警，生产与调度能力可用`
    }
  }
  return {
    dot: 'running',
    title: '正常运行',
    detail: '父子节点在线，暂无活动故障'
  }
})
const runtimeSnapshotSummary = computed(() => snapshotSummary(runtimeSnapshot.value))
const ruleConclusions = computed<RuleConclusion[]>(() => runtimeSnapshot.value?.rule_conclusions ?? [])
const partQueue = computed<PartQueueSnapshot | null>(() => runtimeSnapshot.value?.part_queue ?? null)

const statusLabel: Record<MachineState, string> = {
  running: '运行中',
  idle: '空闲',
  warning: '预警',
  fault: '故障',
  isolated: '已隔离',
  maintenance: '维护中'
}

const workOrderStatusLabel = {
  scheduled: '已排程',
  in_progress: '进行中',
  blocked: '受阻',
  waiting: '等待'
} as const

const alarmStatusLabel = {
  unacknowledged: '未确认',
  confirmed: '已确认',
  diagnosed: '已诊断',
  contained: '已控制',
  observing: '观察中'
} as const


const severityLabel = {
  medium: '中',
  high: '高',
  critical: '严重'
} as const

const syncLabel = {
  online: '在线',
  delayed: '延迟',
  offline: '离线'
} as const

const viewLabels = {
  factory: '工厂拓扑',
  orders: '工单调度',
  alarms: '报警处置',
  quality: '数据质量',
  logs: '日志管理',
  replay: '运行回放',
  reports: '生产报告',
  demo: '演示指挥'
} as const

async function handleIssue(issueId: string, action: string) {
  const issue = (apiIssues.value ?? []).find((item) => item.id === issueId)
  const issueText = `${issueId} ${issue?.title ?? ''} ${issue?.detail ?? ''} ${action}`
  if (issueText.includes('SPINDLE_TEMP_HIGH') || issueText.includes('主轴温度') || issueText.includes('应急引导')) {
    activeView.value = 'demo'
    setDemoMode('emergency')
    aiGuideVisible.value = true
  }

  try {
    const response = await closeIssue(issueId, action, loginOperator.value || '车间主管')
    const data = await response.json()
    if (!response.ok || !data.ok) {
      throw new Error(data.message ?? data.error ?? `action failed: ${response.status}`)
    }
    apiAvailable.value = true
    dismissedIssues.value.push(issueId)
    apiIssues.value = (apiIssues.value ?? []).filter((issue) => issue.id !== issueId)
    if (data.audit_event) auditEvents.value = [data.audit_event, ...auditEvents.value.filter((event) => event.id !== data.audit_event.id)]
    const summary = verificationSummary(data.effect)
    resolvedEffects.value.unshift(`${currentTime()} 已解决：${issueId} / ${action}${summary ? ` / ${summary}` : ''}`)
    resolvedEffects.value = resolvedEffects.value.slice(0, 3)
    liveLogs.value.unshift(`${currentTime()} 问题已处置：${issueId} / ${action}`)
    playSound('success')
    await loadDashboardState()
    await fetchAuditEvents()
  } catch (error) {
    const message = error instanceof Error ? error.message : '后端未响应'
    liveLogs.value.unshift(`${currentTime()} 处置失败：${issueId} / ${message}`)
    playSound('error')
  } finally {
    await fetchAlarmData()
  }
}

async function dismissIssue(issueId: string) {
  dismissedIssues.value.push(issueId)
  apiIssues.value = (apiIssues.value ?? []).filter((issue) => issue.id !== issueId)
  liveLogs.value.unshift(`${currentTime()} 问题弹窗已确认关闭：${issueId}`)
  playSound('notice')
  if (isResultNotification(issueId)) {
    try {
      await closeIssue(issueId, '关闭结果通知', loginOperator.value || '车间主管')
      await fetchAuditEvents()
    } catch {
      liveLogs.value.unshift(`${currentTime()} 结果通知后端归档失败：${issueId}`)
    }
  }
}

function switchView(view: ViewKey) {
  activeView.value = view
  if (view === 'alarms') {
    selectedAlarmId.value = displayAlarms.value[0]?.id ?? ''
    alarmFeedback.value = ''
    aiDiagnosisResult.value = null
    void fetchAlarmData()
  }
  if (view === 'logs') void fetchAuditEvents()
  if (view === 'reports') liveLogs.value.unshift(`${currentTime()} 打开生产报告：读取 central-api 结构化报告`)
  if (view !== 'demo') {
    aiGuideVisible.value = false
  }
}

function currentTime() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

// ── protected runtime API helpers ──
async function fetchAuditEvents() {
  try {
    const res = await apiFetch('/api/audit/events')
    if (!res.ok) throw new Error('audit unavailable')
    auditEvents.value = normalizeAuditEvents(await res.json())
    apiAvailable.value = true
  } catch {
    liveLogs.value.unshift(`${currentTime()} 审计日志暂不可用：保留当前节点、工单与 VM 状态，等待日志接口恢复。`)
  }
}

async function refreshAiRuleExplanation(snapshot = runtimeSnapshot.value, force = false) {
  if (!snapshot) return
  const signature = ruleExplanationSignature(snapshot)
  if (!ruleExplanationRefreshGate.begin(signature, force)) return
  aiRuleExplanationLoading.value = true
  let succeeded = false
  try {
    const useLive = (snapshot.rule_conclusions?.length ?? 0) > 0
    const response = await apiFetch(
      `/api/ai/rule-explanation?mode=${demoMode.value}&use_live=${useLive ? 'true' : 'false'}&refresh=${force ? 'true' : 'false'}`
    )
    if (!response.ok) throw new Error('rule explanation unavailable')
    aiRuleExplanation.value = await response.json() as AiRuleExplanation
    succeeded = true
  } catch (error) {
    const message = error instanceof Error ? error.message : 'AI 解释接口未响应'
    liveLogs.value.unshift(`${currentTime()} AI 规则解释失败：${message}`)
  } finally {
    ruleExplanationRefreshGate.finish(signature, succeeded)
    aiRuleExplanationLoading.value = false
  }
}

function forceRefreshAiRuleExplanation() {
  void refreshAiRuleExplanation(runtimeSnapshot.value, true)
}

async function fetchAlarmData() {
  try {
    const results = await Promise.allSettled([
      apiFetch('/api/alerts'),
      apiFetch('/api/audit/diagnoses'),
      apiFetch('/api/ops/escalations'),
    ])
    const [aRes, dRes, eRes] = results.map((result) => result.status === 'fulfilled' ? result.value : null)
    const [alertsSlot, diagnosesSlot, escalationsSlot] = await Promise.all([
      responseToFetchSlot<ApiAlert[]>(aRes),
      responseToFetchSlot<ApiDiagnosis[]>(dRes),
      responseToFetchSlot<EscalationItem[]>(eRes)
    ])
    const merged = mergeAlarmFetchResults<ApiAlert, ApiDiagnosis, EscalationItem>(
      alertsSlot,
      diagnosesSlot,
      escalationsSlot
    )
    if (merged.alerts) apiAlerts.value = merged.alerts
    if (merged.diagnoses) apiDiagnoses.value = merged.diagnoses
    if (merged.escalations) escalationQueue.value = merged.escalations
    if (!displayAlarms.value.some((alarm) => alarm.id === selectedAlarmId.value)) {
      selectedAlarmId.value = displayAlarms.value[0]?.id ?? ''
      aiDiagnosisResult.value = null
    }
    apiAvailable.value = merged.apiAvailable
  } catch {
    apiAvailable.value = false
    liveLogs.value.unshift(`${currentTime()} 报警数据刷新失败：保留当前报警、诊断与审批队列。`)
  }
}

async function loadDashboardState() {
  try {
    let state: RuntimeDashboardState
    const snapshotResponse = await apiFetch(`/api/dashboard/snapshot?mode=${demoMode.value}`)
    if (snapshotResponse.ok) {
      const snapshot = (await snapshotResponse.json()) as DashboardSnapshot
      runtimeSnapshot.value = snapshot
      state = dashboardSnapshotToState(snapshot)
      void refreshAiRuleExplanation(snapshot)
    } else {
      const response = await apiFetch(`/api/dashboard-state?mode=${demoMode.value}`)
      if (!response.ok) throw new Error('api unavailable')
      state = (await response.json()) as RuntimeDashboardState
      runtimeSnapshot.value = null
    }
    apiIssues.value = uniqueIssues(activeDashboardIssues(state).map((issue) => ({
      ...issue,
      actions: issue.actions ?? []
    })))
    if (state.nodes) hostNodes.value = state.nodes
    if (state.work_orders) hostWorkOrders.value = state.work_orders
    if (state.dispatch_plan) dispatchPlan.value = state.dispatch_plan
    if (state.audit_events) auditEvents.value = state.audit_events
    if (state.node_sync_records) nodeSyncRecords.value = state.node_sync_records
    if (state.log_events) logEvents.value = state.log_events
    liveLogs.value = state.logs.length ? state.logs : liveLogs.value
    apiAvailable.value = true
  } catch {
    apiAvailable.value = false
  }
}

function appendBackendHeartbeatLog() {
  if (!hostNodes.value.length) {
    liveLogs.value.unshift(`${currentTime()} 后端在线，但尚未收到子节点心跳`)
    liveLogs.value = liveLogs.value.slice(0, 8)
    return
  }
  const mostRecent = [...hostNodes.value].sort((left, right) =>
    Number(left.last_seen_sec ?? 999999) - Number(right.last_seen_sec ?? 999999)
  )[0]
  const production = mostRecent.production ?? {}
  const temp = typeof production.spindle_temp === 'number' ? `${production.spindle_temp} C` : '无温度指标'
  const order = production.active_order ?? '未派发工单'
  const age = typeof mostRecent.last_seen_sec === 'number' ? `${Math.round(mostRecent.last_seen_sec)}s` : '未知'
  liveLogs.value.unshift(
    `${currentTime()} 心跳同步：${mostRecent.node_code} / ${order} / ${temp} / ${age} 前`
  )
  liveLogs.value = liveLogs.value.slice(0, 8)
}

const { refreshProtectedData, startRuntimePolling, stopRuntimePolling } = useProtectedPolling({
  systemUnlocked,
  runtimeTick,
  loadDashboardState,
  fetchAlarmData,
  fetchAuditEvents,
  appendHeartbeatLog: appendBackendHeartbeatLog,
})

onMounted(() => {
  void fetchAuthStatus()
  void runPreflight()
  window.addEventListener('miniogas-auth-expired', handleAuthExpired)
})

watch(systemUnlocked, (unlocked) => {
  if (unlocked) {
    startRuntimePolling()
    void refreshProtectedData()
  } else {
    stopRuntimePolling()
    ruleExplanationRefreshGate.reset()
    aiRuleExplanation.value = null
    aiRuleExplanationLoading.value = false
  }
}, { immediate: true })

watch(activeIssuePopups, (issues) => {
  const current = new Set(issues.map((issue) => issue.id))
  const sound = alertSoundForNewIssues(issues, knownIssueIds)
  knownIssueIds = current
  if (sound) playSound(sound)
}, { immediate: true })

onUnmounted(() => {
  stopRuntimePolling()
  clearEmergencyTimer()
  clearPreflightTimer()
  window.removeEventListener('miniogas-auth-expired', handleAuthExpired)
})

function handleAuthExpired() {
  lockSystem()
  stopRuntimePolling()
}
</script>

<template>
  <div class="shell" :class="{ locked: loginRequired }">
    <aside class="sidebar" aria-label="Mini-OGAS navigation">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"></span>
        <div>
          <strong>Mini-OGAS</strong>
          <span>工业控制台</span>
        </div>
      </div>

      <nav class="nav-list" aria-label="Primary">
        <button
          v-for="(label, key) in viewLabels"
          :key="key"
          class="nav-button"
          :class="{ active: activeView === key }"
          type="button"
          @click="switchView(key)"
        >
          {{ label }}
        </button>
      </nav>

      <section class="operator-card" aria-label="当前操作员">
        <span>当前登录</span>
        <strong>车间主管</strong>
        <small>{{ aiRuntimeLabel }}</small>
      </section>
    </aside>

    <main class="workspace">
      <Transition name="modal-shell">
        <StartupGate
          v-if="loginRequired"
          v-model:login-operator="loginOperator"
          v-model:login-password="loginPassword"
          :gate-phase="gatePhase"
          :checks="animatedStartupChecks"
          :startup-checks="startupChecks"
          :boot-progress="bootProgress"
          :preflight-loading="preflightLoading"
          :preflight="preflight"
          :login-feedback="loginFeedback"
          :login-loading="loginLoading"
          @run-preflight="runPreflight"
          @login="loginAdmin"
        />
      </Transition>

      <template v-if="!loginRequired">
      <header class="topbar">
        <div>
          <p class="eyebrow">分布式机加工工厂</p>
          <h1>{{ viewLabels[activeView] }}</h1>
        </div>
        <div class="system-state">
          <span class="status-dot" :class="systemStateSummary.dot" aria-hidden="true"></span>
          <div>
            <strong>{{ systemStateSummary.title }}</strong>
            <span>{{ systemStateSummary.detail }}</span>
          </div>
        </div>
      </header>

      <section class="summary-grid" aria-label="Operating summary">
        <article class="summary-tile">
          <span>运行设备</span>
          <strong>{{ operatingSummary.running }}/{{ machines.length }}</strong>
        </article>
        <article class="summary-tile">
          <span>活动故障</span>
          <strong>{{ operatingSummary.fault }}</strong>
        </article>
        <article class="summary-tile">
          <span>预警数量</span>
          <strong>{{ operatingSummary.warning }}</strong>
        </article>
        <article class="summary-tile">
          <span>平均 OEE</span>
          <strong>{{ operatingSummary.averageOee === null ? '未上报' : `${operatingSummary.averageOee}%` }}</strong>
        </article>
      </section>

      <FactoryRuntimeView
        v-if="activeView === 'factory'"
        :control-service-rows="controlServiceRows"
        :live-workshops="liveWorkshops"
        :status-label="statusLabel"
        :sync-label="syncLabel"
        :ai-smoke-truth="aiSmokeTruth"
        :auth-runtime="authRuntime"
        :host-connected-node-count="runtimeSnapshotSummary?.nodesConnected ?? nodeConnectionSummary.connected"
        :host-node-count="runtimeSnapshotSummary?.nodesExpected ?? nodeConnectionSummary.total"
        :node-runtime-rows="nodeRuntimeRows"
        :runtime-events="visibleRuntimeEvents(logEvents, liveLogs)"
        :snapshot-summary="runtimeSnapshotSummary"
        :part-queue="partQueue"
        :rule-conclusions="ruleConclusions"
        :ai-rule-explanation="aiRuleExplanation"
        :ai-rule-explanation-loading="aiRuleExplanationLoading"
        @refresh-rule-explanation="forceRefreshAiRuleExplanation"
      />

      <section v-else-if="activeView === 'demo'" class="demo-page" aria-label="独立演示指挥页面">
        <div class="demo-header panel">
          <div>
            <p class="eyebrow">独立演示页面</p>
            <h2>云端车间节点运行与 AI 应急引导</h2>
          </div>
          <div class="segmented-control" aria-label="演示模式">
            <button
              type="button"
              :class="{ active: demoMode === 'normal' }"
              @click="setDemoMode('normal')"
            >
              正常运行
            </button>
            <button
              type="button"
              :class="{ active: demoMode === 'emergency' }"
              @click="setDemoMode('emergency')"
            >
              紧急情况
            </button>
          </div>
        </div>

        <section class="demo-grid">
          <article class="panel backend-state-panel">
            <p class="eyebrow">后端连接</p>
            <h2>{{ apiAvailable ? 'central-api 已接入' : '后端未连接，实时管理停用' }}</h2>
            <span class="state-pill" :class="apiAvailable ? 'running' : 'warning'">
              {{ apiAvailable ? 'API 在线' : '等待后端' }}
            </span>
          </article>

          <article class="panel edge-node-panel">
            <p class="eyebrow">云服务器角色</p>
            <h2>{{ demoScenario.edgeNode.role }}</h2>
            <div class="live-strip">
              <span class="flow-dot" aria-hidden="true"></span>
              <strong>运行中</strong>
              <small>第 {{ runtimeTick }} 秒 / 心跳持续同步</small>
            </div>
            <dl class="demo-facts">
              <div>
                <dt>节点编号</dt>
                <dd>{{ demoScenario.edgeNode.code }}</dd>
              </div>
              <div>
                <dt>部署位置</dt>
                <dd>{{ demoScenario.edgeNode.deployment }}</dd>
              </div>
              <div>
                <dt>心跳频率</dt>
                <dd>{{ demoScenario.edgeNode.heartbeat }}</dd>
              </div>
              <div>
                <dt>本地数据库</dt>
                <dd>{{ demoScenario.edgeNode.localDb }}</dd>
              </div>
              <div>
                <dt>同步目标</dt>
                <dd>{{ demoScenario.edgeNode.syncTarget }}</dd>
              </div>
            </dl>
          </article>

          <article class="panel scenario-panel" :class="demoMode">
            <div class="panel-heading">
              <div>
                <p class="eyebrow">当前演示状态</p>
                <h2>{{ activeDemo.title }}</h2>
              </div>
              <span class="state-pill" :class="demoMode === 'normal' ? 'running' : 'fault'">
                {{ activeDemo.machineState }}
              </span>
            </div>
            <p>{{ activeDemo.summary }}</p>
            <div class="scenario-states">
              <div>
                <span>AI 状态</span>
                <strong>{{ activeDemo.aiState }}</strong>
              </div>
              <div>
                <span>人工动作</span>
                <strong>{{ activeDemo.operatorAction }}</strong>
              </div>
            </div>
            <ol class="scenario-steps">
              <li v-for="record in activeDemo.records" :key="record">{{ record }}</li>
            </ol>
          </article>

          <article class="panel heartbeat-panel">
            <p class="eyebrow">心跳包摘要</p>
            <h2>边缘节点上传到主机的数据</h2>
            <pre>{
  "node_code": "milling-workshop-01",
  "status": "{{ heartbeatStatus }}",
  "machine": "MILL-02",
  "finished_quantity": {{ liveOutput }},
  "tool_wear_level": {{ liveWear }},
  "spindle_temp": {{ liveTemp }},
  "pending_records": {{ pendingRecords }}
}</pre>
            <div class="telemetry-flow" aria-label="实时指标流">
              <span :style="{ width: `${Math.min(100, liveTemp)}%` }"></span>
            </div>
            <small class="telemetry-caption">温度、磨损、待同步记录会随处置阶段动态变化</small>
          </article>

          <article class="panel basis-panel">
            <p class="eyebrow">科学性约束</p>
            <h2>真实公开数据驱动的模拟原则</h2>
            <ul>
              <li v-for="basis in demoScenario.scientificBasis" :key="basis">{{ basis }}</li>
            </ul>
          </article>

          <article class="panel live-log-panel">
            <p class="eyebrow">运行日志</p>
            <h2>问题与处置结果实时上报</h2>
            <ol>
              <li v-for="(log, i) in liveLogs" :key="`log-${i}-${log.slice(0, 8)}`">{{ log }}</li>
            </ol>
          </article>

          <article v-if="resolvedEffects.length" class="panel resolved-panel">
            <p class="eyebrow">处置反馈</p>
            <h2>已解决问题</h2>
            <TransitionGroup name="resolved-list" tag="ol">
              <li v-for="(effect, i) in resolvedEffects" :key="`eff-${i}-${effect.slice(0, 8)}`">{{ effect }}</li>
            </TransitionGroup>
          </article>
        </section>

        <button
          v-if="demoMode === 'emergency' && !aiGuideVisible"
          class="reopen-guide"
          type="button"
          @click="aiGuideVisible = true"
        >
          打开 AI 应急引导
        </button>

        <Transition name="modal-shell">
          <div
            v-if="demoMode === 'emergency' && aiGuideVisible"
            class="modal-backdrop"
            role="presentation"
            @click.self="aiGuideVisible = false"
          >
            <aside class="ai-popup" role="dialog" aria-modal="true" aria-label="AI 应急引导">
              <div class="ai-popup-header">
                <span class="status-dot fault" aria-hidden="true"></span>
                <div>
                  <strong>AI 应急引导</strong>
                  <span>MILL-02 主轴温度与刀具磨损联合越限</span>
                </div>
                <button class="icon-close" type="button" aria-label="关闭 AI 应急引导" @click="aiGuideVisible = false">
                  ×
                </button>
              </div>

            <div class="guide-status">
              <span>当前阶段</span>
              <strong>
                {{
                  emergencyStep >= emergencyGuideStages.length
                    ? '处置完成，正在恢复正常运行'
                    : emergencyGuideStages[emergencyStep].title
                }}
              </strong>
              <small v-if="emergencyStep < emergencyGuideStages.length">{{
                emergencyGuideStages[emergencyStep].goal
              }}</small>
            </div>

            <div class="maintenance-callout">
              <strong>现场维修建议</strong>
              <p>
                主轴温度过高属于物理设备风险。建议立即派遣维修工人到 MILL-02，
                执行停机挂牌，检查冷却液循环、主轴轴承、润滑状态与刀具磨损。
              </p>
            </div>

            <ol class="guide-steps">
              <li
                v-for="(stage, index) in emergencyGuideStages"
                :key="stage.title"
                :class="{ done: index < emergencyStep, active: index === emergencyStep }"
              >
                <span>{{ index + 1 }}</span>
                <p>{{ stage.title }}</p>
              </li>
            </ol>

            <div v-if="emergencyStep < emergencyGuideStages.length" class="treatment-options">
              <strong>本阶段可选处置</strong>
              <button
                v-for="option in emergencyGuideStages[emergencyStep].options"
                :key="option"
                type="button"
                :class="{ selected: handledActions.includes(option) }"
                @click="selectTreatment(option)"
              >
                {{ option }}
              </button>
            </div>

            <div class="guide-audit">
              <strong>系统约束</strong>
              <span>AI 只提供建议；隔离、停机、调度重排必须由车间主管确认并写入审计日志。</span>
            </div>

            <div class="action-bar">
              <button class="secondary-action" type="button" @click="aiGuideVisible = false">仅记录建议</button>
              <button
                class="danger-action"
                type="button"
                :disabled="emergencyStep >= emergencyGuideStages.length"
                @click="advanceEmergencyStep"
              >
                {{ emergencyStep >= emergencyGuideStages.length ? '恢复中' : '确认并执行下一阶段' }}
              </button>
            </div>
            </aside>
          </div>
        </Transition>
      </section>

      <OrderDispatchView
        v-else-if="activeView === 'orders'"
        :orders="displayedWorkOrders"
        :dispatch-plan="dispatchPlan"
        :dispatch-panel-title="dispatchPanelTitle"
        :dispatch-approval-label="dispatchApprovalLabel"
        :dispatch-awaiting-approval="dispatchAwaitingApproval"
        :dispatch-confirm-code="dispatchConfirmCode"
        :dispatch-feedback="dispatchFeedback"
        :dispatch-feedback-kind="dispatchFeedbackKind"
        :dispatch-loading="dispatchLoading"
        :work-order-status-label="workOrderStatusLabel"
        @recalculate="recalculateDispatchPlan"
        @approve="approveDispatchPlan"
        @update-confirm-code="dispatchConfirmCode = $event"
      />

      <LogManagementView
        v-else-if="activeView === 'logs'"
        :audit-events="auditEvents"
        :node-sync-records="nodeSyncRecords"
        :verification-summary="verificationSummary"
        @refresh="fetchAuditEvents"
      />

      <DataQualityView
        v-else-if="activeView === 'quality'"
      />

      <ProductionReportView
        v-else-if="activeView === 'reports'"
      />

      <ReplayTimelineView
        v-else-if="activeView === 'replay'"
      />

      <AlarmManagementView
        v-else
        :alarms="displayAlarms"
        :selected-alarm="selectedAlarm"
        :selected-alarm-id="selectedAlarmId"
        :alarm-status-label="alarmStatusLabel"
        :severity-label="severityLabel"
        :alarm-actions="alarmActions"
        :diagnosis-for-selected="diagnosisForSelected"
        :latest-diagnosis-for-selected="latestDiagnosisForSelected"
        :ai-runtime-truth-label="aiRuntimeTruthLabel"
        :ai-diagnosis-result="aiDiagnosisResult"
        :alarm-feedback="alarmFeedback"
        :alarm-action-loading="alarmActionLoading"
        :escalation-queue="escalationQueue"
        :escalation-confirm-codes="escalationConfirmCodes"
        :resolved-effects="resolvedEffects"
        @refresh="fetchAlarmData"
        @select-alarm="selectAlarm"
        @update-escalation-code="updateEscalationCode"
        @confirm-alarm="confirmAlarm"
        @run-ai-diagnose="runAiDiagnose"
        @isolate-node="isolateNode"
        @observe-alarm="observeAlarm"
        @ignore-alarm="ignoreAlarm"
        @escalate-to-human="escalateToHuman"
        @close-alarm="closeAlarm"
        @decide-escalation="decideEscalation"
      />

      <TransitionGroup
        v-if="activeIssuePopups.length"
        name="issue-list"
        tag="aside"
        class="issue-popups"
        aria-label="问题弹窗中心"
      >
        <article
          v-for="issue in activeIssuePopups"
          :key="issue.id"
          class="issue-popup"
          :class="{ critical: issue.severity === '高危' }"
        >
          <div class="issue-popup-head">
            <span>{{ issue.severity }}</span>
            <button type="button" aria-label="关闭问题弹窗" @click="dismissIssue(issue.id)">×</button>
          </div>
          <strong>{{ issue.title }}</strong>
          <p>{{ issue.detail }}</p>
          <div class="issue-actions">
            <button
              v-for="action in issue.actions"
              :key="action"
              class="secondary-action"
              type="button"
              @click="handleIssue(issue.id, action)"
            >
              {{ action }}
            </button>
          </div>
        </article>
      </TransitionGroup>
      </template>
    </main>
  </div>
</template>
