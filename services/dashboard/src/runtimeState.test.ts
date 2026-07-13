import { describe, expect, it } from 'vitest'
import { activeDashboardIssues, dashboardSnapshotToState, mergeAlarmFetchResults, normalizeAuditEvents, normalizeLogLevel, responseToFetchSlot, snapshotSummary, visibleRuntimeEvents } from './runtimeState'
import type { DashboardSnapshot, RuntimeDashboardState } from './types'

describe('responseToFetchSlot', () => {
  it('turns a successful response into a data slot', async () => {
    const slot = await responseToFetchSlot({
      ok: true,
      json: async () => [{ issue_id: 'ALM-1' }]
    })

    expect(slot).toEqual({ ok: true, data: [{ issue_id: 'ALM-1' }] })
  })

  it('treats a bad JSON body as only that endpoint failing', async () => {
    const slot = await responseToFetchSlot({
      ok: true,
      json: async () => { throw new Error('bad json') }
    })

    expect(slot).toEqual({ ok: false })
  })

  it('treats null or non-ok responses as failed slots', async () => {
    await expect(responseToFetchSlot(null)).resolves.toEqual({ ok: false })
    await expect(responseToFetchSlot({ ok: false, json: async () => [] })).resolves.toEqual({ ok: false })
  })
})

describe('normalizeAuditEvents', () => {
  it('maps the paginated unified audit contract into dashboard archive rows', () => {
    const events = normalizeAuditEvents({
      total: 1,
      events: [{
        id: 'event-1',
        timestamp: '2026-07-13T06:00:00+00:00',
        actor: 'operator',
        source_type: 'audit_log',
        action: 'issue:close',
        message: 'closed after verification',
        result: 'closed',
        node_code: 'milling-workshop-01',
        severity: 'info',
        detail: { alarm_removed: true }
      }]
    })

    expect(events).toEqual([expect.objectContaining({
      id: 'event-1',
      time: '2026-07-13 06:00:00',
      permission: 'issue:close',
      subject: 'closed after verification',
      status: 'closed',
      source: 'audit_log',
      effect: { alarm_removed: true }
    })])
  })

  it('returns an empty archive for malformed payloads', () => {
    expect(normalizeAuditEvents({ total: 2 })).toEqual([])
  })
})

describe('mergeAlarmFetchResults', () => {
  it('keeps successful alarm data when diagnosis or escalation endpoints fail', () => {
    const result = mergeAlarmFetchResults(
      { ok: true, data: [{ issue_id: 'ALM-1' }] },
      { ok: false },
      { ok: false }
    )

    expect(result.apiAvailable).toBe(true)
    expect(result.alerts).toEqual([{ issue_id: 'ALM-1' }])
    expect(result.diagnoses).toBeUndefined()
    expect(result.escalations).toBeUndefined()
  })

  it('marks API unavailable only when every alarm-related endpoint fails', () => {
    const result = mergeAlarmFetchResults({ ok: false }, { ok: false }, { ok: false })

    expect(result.apiAvailable).toBe(false)
    expect(result.alerts).toBeUndefined()
  })
})

describe('visibleRuntimeEvents', () => {
  it('preserves backend log levels instead of rewriting them as info', () => {
    const events = visibleRuntimeEvents([
      { time: '18:40:01', level: 'error', source: 'central-api', message: '节点超时' },
      { time: '18:40:02', level: 'warning', source: 'node-agent', message: '同步积压' }
    ], [])

    expect(events.map((event) => event.level)).toEqual(['error', 'warning'])
  })

  it('uses info only for local fallback live logs', () => {
    const events = visibleRuntimeEvents([], ['18:40:03 心跳同步：3/3'])

    expect(events).toEqual([
      { time: '18:40:03', level: 'info', source: 'central-api', message: '心跳同步：3/3' }
    ])
  })
})

describe('normalizeLogLevel', () => {
  it('keeps known backend levels and maps common aliases', () => {
    expect(normalizeLogLevel('critical')).toBe('critical')
    expect(normalizeLogLevel('warn')).toBe('warning')
    expect(normalizeLogLevel('fatal')).toBe('critical')
    expect(normalizeLogLevel('failure')).toBe('error')
  })

  it('falls back to info for unknown levels', () => {
    expect(normalizeLogLevel('debug')).toBe('info')
    expect(normalizeLogLevel(undefined)).toBe('info')
  })
})

describe('dashboardSnapshotToState', () => {
  it('adapts v2.2 snapshot nodes into the existing runtime presentation shape', () => {
    const snapshot: DashboardSnapshot = {
      schema_version: '2.2',
      generated_at: '2026-06-13T08:40:00Z',
      data_source: 'live',
      run: {
        run_id: 'RUN-LOCAL-20260613-001',
        scenario_id: 'SCN-MILLING-SIMPY-SINGLE-001',
        simulation_time: '2026-06-13T08:40:30Z',
        simulation_speed: 1,
        simulation_engine: 'simpy'
      },
      system: {
        status: 'ok',
        nodes_connected: 3,
        nodes_expected: 3
      },
      nodes: [{
        node_code: 'milling-workshop-01',
        status: 'online',
        workshop_type: 'milling',
        machine_code: 'MILL-02',
        active_order: 'WO-1',
        runtime: {
          deployment_mode: 'process',
          simulation_mode: 'normal',
          simulation_engine: 'simpy',
          run_id: 'RUN-LOCAL-20260613-001',
          scenario_id: 'SCN-MILLING-SIMPY-SINGLE-001',
          runtime_source: 'node-agent'
        },
        production: {
          wip_input: 14,
          wip_output: 2,
          target_rate: 1,
          actual_rate: 0.62,
          utilization: 0.62,
          defect_rate: 0
        }
      }],
      work_orders: [{
        id: 'WO-1',
        product: 'valve',
        quantity: 160,
        route: ['milling'],
        priority: 'P1',
        status: 'in_progress'
      }],
      alerts: [],
      notifications: [{
        id: 'HUMAN-1',
        severity: 'notice',
        title: 'manual handling complete',
        detail: 'archived by supervisor',
        actions: ['acknowledge']
      }],
      timeline: { recent_logs: ['08:40:01 snapshot live'] }
    }

    const state = dashboardSnapshotToState(snapshot)

    expect(state.nodes?.[0].production).toMatchObject({
      machine_code: 'MILL-02',
      workshop_type: 'milling',
      active_order: 'WO-1',
      actual_rate: 0.62
    })
    expect(state.work_orders?.[0]).toMatchObject({
      id: 'WO-1',
      quantity: 160,
      status: 'in_progress'
    })
    expect(state.logs).toEqual(['08:40:01 snapshot live'])
    expect(state.notifications?.[0]).toMatchObject({
      id: 'HUMAN-1',
      title: 'manual handling complete'
    })
    expect(snapshotSummary(snapshot)).toMatchObject({
      dataSource: 'live',
      runId: 'RUN-LOCAL-20260613-001',
      scenarioId: 'SCN-MILLING-SIMPY-SINGLE-001',
      simulationEngine: 'simpy',
      nodesConnected: 3,
      nodesExpected: 3
    })
  })

  it('keeps only active alerts and current-run result notifications', () => {
    const state = {
      issues: [
        { id: 'ALM-OPEN', severity: 'high', title: 'open', detail: 'active', status: 'diagnosed' },
        { id: 'ALM-CLOSED', severity: 'high', title: 'closed', detail: 'archived', status: 'closed' }
      ],
      notifications: [
        { id: 'HUMAN-CURRENT', severity: 'notice', title: 'done', detail: 'current', status: 'unacknowledged', run_id: 'RUN-2' },
        { id: 'HUMAN-OLD', severity: 'notice', title: 'done', detail: 'old', status: 'unacknowledged', run_id: 'RUN-1' },
        { id: 'HUMAN-ACK', severity: 'notice', title: 'done', detail: 'ack', status: 'acknowledged', run_id: 'RUN-2' }
      ],
      logs: [],
      snapshot: { run: { run_id: 'RUN-2' } }
    } as unknown as RuntimeDashboardState

    expect(activeDashboardIssues(state).map((issue) => issue.id)).toEqual(['ALM-OPEN', 'HUMAN-CURRENT'])
  })
})
