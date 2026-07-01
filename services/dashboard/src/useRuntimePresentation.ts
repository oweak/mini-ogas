import { computed, type Ref } from 'vue'
import type {
  AuditEvent,
  DisplayedWorkOrder,
  HostNode,
  HostWorkOrder,
  MachineState,
  Workshop
} from './types'

type AiSmokeTruth = {
  status: string
  detail: string
  source: string
  isLiveApi: boolean
}

type RuntimePresentationOptions = {
  hostNodes: Ref<HostNode[]>
  hostWorkOrders: Ref<HostWorkOrder[]>
  apiAvailable: Ref<boolean>
  aiSmokeTruth: Ref<AiSmokeTruth>
  auditEvents: Ref<AuditEvent[]>
}

export function normalizeMachineState(status: HostNode['status']): MachineState {
  if (status === 'fault' || status === 'warning' || status === 'maintenance' || status === 'isolated') return status
  return 'running'
}

export function calculateYieldRate(finished?: number, defects?: number, fallback = 100) {
  if (!finished || finished <= 0) return fallback
  return Number(Math.max(0, ((finished - (defects ?? 0)) / finished) * 100).toFixed(1))
}

export function workshopName(code: string) {
  const labels: Record<string, string> = {
    turning: '车削车间',
    milling: '铣削车间',
    grinding: '磨削车间',
    unknown: '未知车间'
  }
  return labels[code] ?? code
}

export function machineTypeLabel(type?: string) {
  const labels: Record<string, string> = {
    turning: '数控车削',
    milling: '数控铣削',
    grinding: '精密磨削'
  }
  return labels[type ?? ''] ?? '后端节点'
}

export function alarmLabel(type: string) {
  const labels: Record<string, string> = {
    SPINDLE_TEMP_HIGH: '主轴温度过高',
    VIBRATION_HIGH: '振动异常',
    COOLANT_FLOW_LOW: '冷却液流量偏低',
    QUALITY_DRIFT: '良品率漂移',
    TOOL_WEAR_WARNING: '刀具/砂轮磨损预警'
  }
  return labels[type] ?? type
}

export function nodeIsConnected(status: HostNode['status']) {
  return !['offline', 'missing'].includes(String(status))
}

export function useRuntimePresentation(options: RuntimePresentationOptions) {
  const liveWorkshops = computed<Workshop[]>(() => {
    const groups: Record<string, HostNode[]> = {}
    options.hostNodes.value.forEach((node) => {
      const key = node.production?.workshop_type ?? node.node_code.split('-')[0] ?? 'unknown'
      groups[key] = [...(groups[key] ?? []), node]
    })
    return Object.entries(groups).map(([code, nodes]) => ({
      code,
      name: workshopName(code),
      node: nodes.map((item) => item.node_code).join(', '),
      status: normalizeMachineState(nodes.some((node) => node.status === 'fault') ? 'fault' : nodes.some((node) => node.status === 'warning') ? 'warning' : 'running'),
      load: Math.round(nodes.reduce((total, node) => total + Number(node.metrics?.cpu_usage ?? 0), 0) / Math.max(1, nodes.length)),
      machines: nodes.map((node) => {
        const production = node.production ?? {}
        const alarmType = node.alarms?.[0]?.type
        return {
          code: production.machine_code ?? node.node_code,
          name: production.machine_code ?? node.node_code,
          type: machineTypeLabel(production.workshop_type),
          state: normalizeMachineState(node.status),
          workOrder: production.active_order ?? '未派发',
          process: production.dispatch_policy ?? '后端心跳',
          output: Number(production.finished_quantity ?? 0),
          target: Number(options.hostWorkOrders.value.find((order) => order.id === production.active_order)?.quantity ?? 0),
          yieldRate: calculateYieldRate(production.finished_quantity, production.defect_quantity, 100),
          oee: Math.max(0, Math.min(100, Math.round(Number(node.metrics?.cpu_usage ?? 0) + 22))),
          toolWear: Math.round(Number(production.tool_wear_level ?? 0)),
          targetRate: production.target_rate,
          actualRate: production.actual_rate,
          utilization: production.utilization,
          defectRate: production.defect_rate,
          sync: (node.sync?.pending_records ? 'delayed' : 'online') as 'online' | 'delayed' | 'offline',
          lastAlarm: alarmType ? alarmLabel(alarmType) : undefined
        }
      })
    }))
  })

  const machines = computed(() => liveWorkshops.value.flatMap((workshop) => workshop.machines))
  const nodeConnectionSummary = computed(() => {
    const total = options.hostNodes.value.length
    const connected = options.hostNodes.value.filter((node) => nodeIsConnected(node.status)).length
    return {
      connected,
      total,
      label: `${connected}/${total} 个节点已接入`
    }
  })
  const backendOrderProgress = computed(() => {
    const progress: Record<string, number> = {}
    options.hostNodes.value.forEach((node) => {
      const production = node.production ?? {}
      const orderId = production.active_order
      if (!orderId) return
      progress[orderId] = (progress[orderId] ?? 0) + Number(production.finished_quantity ?? 0)
    })
    return progress
  })
  const displayedWorkOrders = computed<DisplayedWorkOrder[]>(() => {
    return options.hostWorkOrders.value.map((order) => ({
      id: order.id,
      product: order.product,
      route: order.route,
      priority: order.priority,
      quantity: order.quantity,
      completed: Math.min(order.quantity, Math.max(0, Math.round(backendOrderProgress.value[order.id] ?? 0))),
      due: order.id.endsWith('004') ? '17:10' : order.id.endsWith('005') ? '16:30' : '18:00',
      status: order.status as DisplayedWorkOrder['status']
    }))
  })
  const nodeRuntimeRows = computed(() => options.hostNodes.value.map((node) => ({
    node_code: node.node_code,
    machine_code: node.production?.machine_code ?? '',
    status: node.status,
    deployment_mode: node.runtime?.deployment_mode ?? node.deployment_mode ?? 'unknown',
    simulation_mode: node.runtime?.simulation_mode ?? node.simulation_mode ?? 'unknown',
    host: node.runtime?.host ?? '',
    pid: node.runtime?.pid ?? '',
    heartbeat_sec: node.runtime?.heartbeat_sec ?? '',
    run_id: node.runtime?.run_id ?? '',
    scenario_id: node.runtime?.scenario_id ?? '',
    simulation_time: node.runtime?.simulation_time ?? '',
    simulation_speed: node.runtime?.simulation_speed ?? '',
    simulation_engine: node.runtime?.simulation_engine ?? '',
    runtime_source: node.runtime?.runtime_source ?? (node.runtime ? 'live' : '未上报'),
    last_seen_sec: node.last_seen_sec,
    sync_records: node.sync?.pending_records ?? 0
  })))
  const controlServiceRows = computed(() => [
    {
      code: 'central-api',
      name: '父节点 API',
      role: 'REST 调度、规则引擎、审计归档',
      status: options.apiAvailable.value ? 'online' : 'degraded',
      metric: options.apiAvailable.value ? 'API 在线' : 'API 不可用',
      boundary: '所有前端管理动作必须写入 central-api'
    },
    {
      code: 'edge-heartbeat',
      name: '子节点心跳',
      role: '机床状态、产量、报警、同步缓存',
      status: nodeConnectionSummary.value.connected ? 'online' : 'degraded',
      metric: nodeConnectionSummary.value.label,
      boundary: '以前端实时收到的后端心跳为准'
    },
    {
      code: 'ai-runtime',
      name: 'AI 运行证明',
      role: '登录解锁、启动烟测、诊断来源标记',
      status: options.aiSmokeTruth.value.isLiveApi ? 'online' : 'degraded',
      metric: options.aiSmokeTruth.value.status,
      boundary: options.aiSmokeTruth.value.detail
    },
    {
      code: 'audit',
      name: '日志归档',
      role: '问题处置、调度审批、自动脚本结果',
      status: 'online',
      metric: `${options.auditEvents.value.length} 条归档`,
      boundary: '解决后的问题必须从队列消失并进入日志'
    }
  ])

  return {
    liveWorkshops,
    machines,
    nodeConnectionSummary,
    backendOrderProgress,
    displayedWorkOrders,
    nodeRuntimeRows,
    controlServiceRows
  }
}
