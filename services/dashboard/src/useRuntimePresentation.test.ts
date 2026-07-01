import { ref } from 'vue'
import { describe, expect, it } from 'vitest'
import type { AuditEvent, HostNode, HostWorkOrder } from './types'
import { alarmLabel, calculateYieldRate, nodeIsConnected, normalizeMachineState, useRuntimePresentation } from './useRuntimePresentation'

function createRuntimePresentation(hostNodes: HostNode[], hostWorkOrders: HostWorkOrder[]) {
  return useRuntimePresentation({
    hostNodes: ref(hostNodes),
    hostWorkOrders: ref(hostWorkOrders),
    apiAvailable: ref(true),
    aiSmokeTruth: ref({
      status: '真实 API 已验证',
      detail: 'deepseek / deepseek-v4-pro 启动烟测成功',
      source: 'api',
      isLiveApi: true
    }),
    auditEvents: ref([{ id: 'audit-1' } as AuditEvent])
  })
}

describe('runtime presentation helpers', () => {
  it('normalizes machine status, yield, and alarm labels', () => {
    expect(normalizeMachineState('fault')).toBe('fault')
    expect(normalizeMachineState('running')).toBe('running')
    expect(calculateYieldRate(100, 3)).toBe(97)
    expect(calculateYieldRate(0, 0, 99)).toBe(99)
    expect(nodeIsConnected('running')).toBe(true)
    expect(nodeIsConnected('offline')).toBe(false)
    expect(alarmLabel('SPINDLE_TEMP_HIGH')).toBe('主轴温度过高')
    expect(alarmLabel('CUSTOM_ALARM')).toBe('CUSTOM_ALARM')
  })

  it('maps live backend nodes into workshop and machine rows', () => {
    const runtime = createRuntimePresentation([
      {
        node_code: 'milling-workshop-01',
        status: 'warning',
        metrics: { cpu_usage: 71 },
        production: {
          machine_code: 'MILL-02',
          workshop_type: 'milling',
          active_order: 'WO-1',
          dispatch_policy: '后端心跳',
          finished_quantity: 80,
          defect_quantity: 2,
          tool_wear_level: 64,
          target_rate: 1,
          actual_rate: 0.87,
          utilization: 0.78,
          defect_rate: 0.025
        },
        alarms: [{ type: 'TOOL_WEAR_WARNING' }],
        sync: { pending_records: 2 },
        runtime: {
          deployment_mode: 'process',
          simulation_mode: 'normal',
          host: 'local',
          pid: 123,
          heartbeat_sec: 5,
          run_id: 'RUN-20260613-001',
          scenario_id: 'SCN-NORMAL-MIXED-001',
          simulation_time: '2026-06-13T10:20:00+08:00',
          simulation_speed: 12,
          simulation_engine: 'simpy',
          runtime_source: 'node-agent'
        },
        last_seen_sec: 1
      }
    ], [
      { id: 'WO-1', product: '阀体', quantity: 160, priority: 'P1', route: ['milling'], assigned_node: 'milling-workshop-01', status: 'in_progress' }
    ])

    expect(runtime.liveWorkshops.value).toHaveLength(1)
    expect(runtime.liveWorkshops.value[0]).toMatchObject({
      code: 'milling',
      name: '铣削车间',
      status: 'warning',
      load: 71
    })
    expect(runtime.machines.value[0]).toMatchObject({
      code: 'MILL-02',
      state: 'warning',
      output: 80,
      target: 160,
      yieldRate: 97.5,
      targetRate: 1,
      actualRate: 0.87,
      utilization: 0.78,
      defectRate: 0.025,
      sync: 'delayed',
      lastAlarm: '刀具/砂轮磨损预警'
    })
    expect(runtime.displayedWorkOrders.value[0]).toMatchObject({
      id: 'WO-1',
      completed: 80,
      status: 'in_progress'
    })
    expect(runtime.nodeRuntimeRows.value[0]).toMatchObject({
      node_code: 'milling-workshop-01',
      deployment_mode: 'process',
      run_id: 'RUN-20260613-001',
      scenario_id: 'SCN-NORMAL-MIXED-001',
      simulation_time: '2026-06-13T10:20:00+08:00',
      simulation_speed: 12,
      simulation_engine: 'simpy',
      runtime_source: 'node-agent',
      sync_records: 2
    })
  })

  it('summarizes central API, node heartbeat, AI, and audit service status', () => {
    const runtime = createRuntimePresentation([], [])

    expect(runtime.controlServiceRows.value).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: 'central-api', status: 'online', metric: 'API 在线' }),
      expect.objectContaining({ code: 'edge-heartbeat', status: 'degraded', metric: '0/0 个节点已接入' }),
      expect.objectContaining({ code: 'ai-runtime', status: 'online', metric: '真实 API 已验证' }),
      expect.objectContaining({ code: 'audit', metric: '1 条归档' })
    ]))
  })

  it('counts connected nodes from dashboard nodes without assuming a fixed total', () => {
    const runtime = createRuntimePresentation([
      { node_code: 'turning-workshop-01', status: 'running' },
      { node_code: 'milling-workshop-01', status: 'warning' },
      { node_code: 'grinding-workshop-01', status: 'offline' },
      { node_code: 'kali-redteam', status: 'running' }
    ], [])

    expect(runtime.nodeConnectionSummary.value).toEqual({
      connected: 3,
      total: 4,
      label: '3/4 个节点已接入'
    })
    expect(runtime.controlServiceRows.value).toEqual(expect.arrayContaining([
      expect.objectContaining({ code: 'edge-heartbeat', status: 'online', metric: '3/4 个节点已接入' })
    ]))
  })

  it('reads process runtime fields from dashboard state', () => {
    const runtime = createRuntimePresentation([
      {
        node_code: 'turning-workshop-01',
        status: 'running',
        deployment_mode: 'native-process',
        simulation_mode: 'normal',
        production: { machine_code: 'LATHE-01', workshop_type: 'turning' },
        last_seen_sec: 2
      }
    ], [])

    expect(runtime.nodeRuntimeRows.value[0]).toMatchObject({
      node_code: 'turning-workshop-01',
      deployment_mode: 'native-process',
      simulation_mode: 'normal'
    })
  })

  it('marks runtime source as missing when backend heartbeat has no runtime block', () => {
    const runtime = createRuntimePresentation([
      {
        node_code: 'legacy-workshop-01',
        status: 'running',
        production: { machine_code: 'LEGACY-01', workshop_type: 'milling' }
      }
    ], [])

    expect(runtime.nodeRuntimeRows.value[0]).toMatchObject({
      node_code: 'legacy-workshop-01',
      run_id: '',
      scenario_id: '',
      simulation_time: '',
      runtime_source: '未上报'
    })
  })
})
