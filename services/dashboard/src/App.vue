<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiFetch } from './apiClient'
import { demoScenario } from './data'
import StartupGate from './StartupGate.vue'
import { useProtectedPolling } from './protectedPolling'
import { closeIssue, confirmAlert, diagnoseIssue, diagnosePayload, escalateIssue, isolateNode as isolateNodeRequest } from './operationsApi'
import type { Alarm, MachineState } from './types'

type ViewKey = 'factory' | 'orders' | 'alarms' | 'logs' | 'demo'

const activeView = ref<ViewKey>('factory')
const selectedAlarmId = ref('')
const demoMode = ref<'normal' | 'emergency'>('normal')
const emergencyStep = ref(0)
const runtimeTick = ref(0)
const apiAvailable = ref(false)
const hostWorkOrders = ref<any[]>([])
const hostNodes = ref<any[]>([])
const loginOperator = ref('')
const loginPassword = ref('')
const loginFeedback = ref('')
const loginLoading = ref(false)
const systemUnlocked = ref(false)
const gatePhase = ref<'preflight' | 'login'>('preflight')
const preflightLoading = ref(false)
const apiAlerts = ref<any[]>([])
const alarmActionLoading = ref<string | null>(null)
const aiDiagnosisResult = ref<string | null>(null)
const alarmFeedback = ref('')

const displayAlarms = computed<Alarm[]>(() => apiAlerts.value.filter((a: any) => !a.handled_by && a.status !== 'resolved').map((a: any) => ({
  id: a.issue_id ?? String(a.id), severity: (a.severity === 'critical' ? 'critical' : a.severity === 'high' ? 'high' : 'medium') as Alarm['severity'],
  machine: a.node_code, title: a.alert_type, value: a.description,
  status: (a.status === 'confirmed' ? 'confirmed' : a.status === 'diagnosed' ? 'diagnosed' : a.status === 'contained' ? 'contained' : 'observing' as any),
  rule: `${a.alert_type}`, aiSuggestion: '', requiredRole: '车间主管' })))
const selectedAlarm = computed(() => displayAlarms.value.find((a) => a.id === selectedAlarmId.value))
const loginRequired = computed(() => !systemUnlocked.value)

function normalizeMachineState(s: string): MachineState { return s === 'fault' || s === 'warning' || s === 'maintenance' || s === 'isolated' ? s : 'running' }
function workshopName(c: string) { return { turning: '车削车间', milling: '铣削车间', grinding: '磨削车间' }[c] ?? c }
function machineTypeLabel(t?: string) { return { turning: '数控车削', milling: '数控铣削', grinding: '精密磨削' }[t ?? ''] ?? '后端节点' }

const liveWorkshops = computed(() => {
  const groups: Record<string, any[]> = {}
  hostNodes.value.forEach((n: any) => { const k = n.production?.workshop_type ?? n.node_code.split('-')[0] ?? 'unknown'; (groups[k] ??= []).push(n) })
  return Object.entries(groups).map(([code, nodes]) => ({ code, name: workshopName(code), node: nodes.map((n: any) => n.node_code).join(', '),
    status: nodes.some((n: any) => n.status === 'fault') ? 'fault' : nodes.some((n: any) => n.status === 'warning') ? 'warning' : 'running',
    load: Math.round(nodes.reduce((t: number, n: any) => t + Number(n.metrics?.cpu_usage ?? 0), 0) / Math.max(1, nodes.length)),
    machines: nodes.map((node: any) => { const p = node.production ?? {}; return {
      code: p.machine_code ?? node.node_code, name: p.machine_code ?? node.node_code, type: machineTypeLabel(p.workshop_type),
      state: normalizeMachineState(node.status), workOrder: p.active_order ?? '-', process: p.dispatch_policy ?? '-',
      output: Number(p.finished_quantity ?? 0), target: Number(hostWorkOrders.value.find((o: any) => o.id === p.active_order)?.quantity ?? 0),
      yieldRate: Number(p.finished_quantity ?? 0) > 0 ? Math.round(((Number(p.finished_quantity) - Number(p.defect_quantity ?? 0)) / Number(p.finished_quantity)) * 100) : 100,
      oee: Math.max(0, Math.min(100, Math.round(Number(node.metrics?.cpu_usage ?? 0) + 22))),
      toolWear: Math.round(Number(p.tool_wear_level ?? 0)), sync: (node.sync?.pending_records ? 'delayed' : 'online'),
      lastAlarm: node.alarms?.[0]?.type ? node.alarms[0].type : undefined }
    })
  }))
})
const machines = computed(() => liveWorkshops.value.flatMap((w: any) => w.machines))
const operatingSummary = computed(() => { const mc = machines.value; return { running: mc.filter((m: any) => m.state === 'running').length, fault: mc.filter((m: any) => m.state === 'fault').length, warning: mc.filter((m: any) => m.state === 'warning').length, averageOee: mc.length ? Math.round(mc.reduce((t: number, m: any) => t + m.oee, 0) / mc.length) : 0 } })

function setDemoMode(mode: 'normal' | 'emergency') { demoMode.value = mode; emergencyStep.value = 0; loadDashboardState() }
function switchView(view: ViewKey) { activeView.value = view; if (view === 'alarms') { selectedAlarmId.value = displayAlarms.value[0]?.id ?? ''; fetchAlarmData() } }

async function runPreflight() { gatePhase.value = 'preflight'; preflightLoading.value = true; try { await apiFetch('/api/system/preflight') } catch {} finally { preflightLoading.value = false; setTimeout(() => { if (!systemUnlocked.value) gatePhase.value = 'login' }, 520) } }

async function loginAdmin() { loginLoading.value = true; try { const r = await apiFetch('/api/auth/login', { method: 'POST', body: JSON.stringify({ operator: loginOperator.value || 'operator', password: loginPassword.value }) }); const d = await r.json(); if (r.ok && d.ok) { if (d.api_token) localStorage.setItem('miniogas_token', d.api_token); systemUnlocked.value = true; await loadDashboardState() } else loginFeedback.value = d.error ?? 'fail' } catch { loginFeedback.value = 'offline' } finally { loginLoading.value = false } }

async function loadDashboardState() { try { const r = await apiFetch(`/api/dashboard-state?mode=${demoMode.value}`); if (r.ok) { const s = await r.json(); if (s.nodes) hostNodes.value = s.nodes; if (s.work_orders) hostWorkOrders.value = s.work_orders; apiAvailable.value = true } } catch { apiAvailable.value = false } }
async function fetchAlarmData() { try { const r = await apiFetch('/api/alerts'); if (r.ok) apiAlerts.value = await r.json() } catch {} }

const { startRuntimePolling, stopRuntimePolling, refreshProtectedData } = useProtectedPolling({ systemUnlocked, runtimeTick, loadDashboardState, fetchAlarmData, fetchAuditEvents: async () => {}, appendHeartbeatLog: () => {} })

async function confirmAlarmAction(alarm: Alarm) { alarmActionLoading.value = alarm.id; try { await confirmAlert(alarm.id); apiAlerts.value = apiAlerts.value.map((a: any) => a.issue_id === alarm.id ? { ...a, status: 'confirmed' } : a) } catch {} finally { alarmActionLoading.value = null; await fetchAlarmData() } }
async function runAiDiagnoseAction(alarm: Alarm) { alarmActionLoading.value = alarm.id; try { let r = await diagnoseIssue(alarm.id); if (!r.ok) r = await diagnosePayload({ node_code: alarm.machine, alert_description: alarm.value, alert_type: alarm.title, severity: 'warning' }); if (r.ok) { const d = await r.json(); aiDiagnosisResult.value = r.ok ? `根因: ${d.root_cause || '-'} 置信度: ${Math.round((d.confidence || 0) * 100)}%` : 'fail'; apiAlerts.value = apiAlerts.value.map((a: any) => a.issue_id === alarm.id ? { ...a, status: 'diagnosed' } : a) } } catch {} finally { alarmActionLoading.value = null; await fetchAlarmData() } }
async function isolateNodeAction(alarm: Alarm) { const c = window.prompt('input CONFIRM'); if (!c) return; alarmActionLoading.value = alarm.id; try { await isolateNodeRequest(alarm.machine, c); apiAlerts.value = apiAlerts.value.map((a: any) => a.issue_id === alarm.id ? { ...a, status: 'contained' } : a) } catch {} finally { alarmActionLoading.value = null; await fetchAlarmData() } }
async function escalateToHumanAction(alarm: Alarm) { alarmActionLoading.value = alarm.id; try { await escalateIssue({ nodeCode: alarm.machine, issueType: alarm.title, description: alarm.value }) } catch {} finally { alarmActionLoading.value = null } }
async function closeAlarmAction(alarm: Alarm) { alarmActionLoading.value = alarm.id; try { await closeIssue(alarm.id); apiAlerts.value = apiAlerts.value.filter((a: any) => a.issue_id !== alarm.id); selectedAlarmId.value = displayAlarms.value[0]?.id ?? '' } catch {} finally { alarmActionLoading.value = null } }

const statusLabel: Record<string, string> = { running: 'run', warning: 'warn', fault: 'fault' }
const viewLabels: Record<ViewKey, string> = { factory: '工厂', orders: '工单', alarms: '报警', logs: '日志', demo: '演示' }

onMounted(() => { void runPreflight() })
watch(systemUnlocked, (ul) => { if (ul) { startRuntimePolling(); refreshProtectedData() } else stopRuntimePolling() }, { immediate: true })
onUnmounted(() => { stopRuntimePolling() })
</script>

<template>
  <div class="shell" :class="{ locked: loginRequired }">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark"></span><div><strong>Mini-OGAS</strong><span>控制台</span></div></div>
      <nav class="nav-list"><button v-for="(label,key) in viewLabels" :key="key" class="nav-button" :class="{active:activeView===key}" @click="switchView(key)">{{label}}</button></nav>
    </aside>
    <main class="workspace">
      <Transition name="modal-shell"><StartupGate v-if="loginRequired" v-model:login-operator="loginOperator" v-model:login-password="loginPassword" :gate-phase="gatePhase" :checks="[]" :startup-checks="[]" :boot-progress="0" :preflight-loading="preflightLoading" :preflight="null" :login-feedback="loginFeedback" :login-loading="loginLoading" @run-preflight="runPreflight" @login="loginAdmin"/></Transition>
      <template v-if="!loginRequired">
        <header class="topbar"><h1>{{viewLabels[activeView]}}</h1></header>
        <section class="summary-grid"><article class="summary-tile"><span>设备</span><strong>{{operatingSummary.running}}/{{machines.length}}</strong></article><article class="summary-tile"><span>故障</span><strong>{{operatingSummary.fault}}</strong></article></section>

        <section v-if="activeView==='factory'" class="panel"><div class="workshop-list"><article v-for="w in liveWorkshops" :key="w.code" class="workshop-block"><header><strong>{{w.name}}</strong> {{w.load}}%</header><div class="machine-grid"><article v-for="m in w.machines" :key="m.code" class="machine-card" :class="m.state"><div class="machine-head"><strong>{{m.code}}</strong><span class="state-pill" :class="m.state">{{statusLabel[m.state] || m.state}}</span></div><dl class="machine-metrics"><div><dt>工单</dt><dd>{{m.workOrder}}</dd></div><div><dt>产量</dt><dd>{{m.output}}/{{m.target}}</dd></div><div><dt>良品率</dt><dd>{{m.yieldRate}}%</dd></div><div><dt>刀具</dt><dd>{{m.toolWear}}%</dd></div></dl></article></div></article></div></section>

        <section v-else-if="activeView==='orders'" class="panel"><article v-for="o in hostWorkOrders" :key="o.id" class="machine-card running"><div class="machine-head"><strong>{{o.product}}</strong> {{o.id}} <span class="state-pill running">{{o.status}}</span></div><dl class="machine-metrics"><div><dt>优先级</dt><dd>{{o.priority}}</dd></div><div><dt>数量</dt><dd>{{o.quantity}}</dd></div></dl></article></section>

        <section v-else-if="activeView==='alarms'" style="display:grid;grid-template-columns:1fr 1fr;gap:1rem"><div class="panel"><article v-for="a in displayAlarms" :key="a.id" class="machine-card" :class="a.severity==='critical'?'fault':a.severity==='high'?'warning':'running'" style="cursor:pointer" @click="selectedAlarmId=a.id"><div class="machine-head"><strong>{{a.title}}</strong> {{a.machine}} <span class="state-pill">{{a.severity}}</span></div><p>{{a.value}}</p></article></div><div v-if="selectedAlarm" class="panel"><h2>{{selectedAlarm.title}}</h2><div style="display:flex;gap:0.5rem;flex-wrap:wrap"><button class="secondary-action" :disabled="!!alarmActionLoading" @click="confirmAlarmAction(selectedAlarm)">确认</button><button class="secondary-action" :disabled="!!alarmActionLoading" @click="runAiDiagnoseAction(selectedAlarm)">诊断</button><button class="secondary-action" :disabled="!!alarmActionLoading" @click="isolateNodeAction(selectedAlarm)">隔离</button><button class="secondary-action" :disabled="!!alarmActionLoading" @click="escalateToHumanAction(selectedAlarm)">升级</button><button class="primary-action" :disabled="!!alarmActionLoading" @click="closeAlarmAction(selectedAlarm)">关闭</button></div><p v-if="alarmFeedback">{{alarmFeedback}}</p><p v-if="aiDiagnosisResult" class="panel">{{aiDiagnosisResult}}</p></div></section>

        <section v-else-if="activeView==='logs'" class="panel"><h2>日志</h2><p>审计与运行日志。</p></section>

        <section v-else-if="activeView==='demo'" class="panel"><div style="display:flex;gap:0.5rem;margin-bottom:1rem"><button :class="{active:demoMode==='normal'}" @click="setDemoMode('normal')">正常</button><button :class="{active:demoMode==='emergency'}" @click="setDemoMode('emergency')">紧急</button></div><article class="panel"><h2>{{demoScenario[demoMode].title}}</h2><p>{{demoScenario[demoMode].summary}}</p></article></section>
      </template>
    </main>
  </div>
</template>
