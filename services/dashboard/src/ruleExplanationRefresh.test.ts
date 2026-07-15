import { describe, expect, it } from 'vitest'
import { createRuleExplanationRefreshGate, ruleExplanationSignature } from './ruleExplanationRefresh'
import type { DashboardSnapshot } from './types'

function snapshot(value: number, severity = 'high'): DashboardSnapshot {
  return {
    schema_version: '2.2',
    generated_at: '2026-07-13T10:00:00+08:00',
    data_source: 'live',
    run: {
      run_id: 'RUN-1',
      scenario_id: 'SCN-NORMAL',
    },
    system: {
      status: 'running',
      nodes_connected: 3,
      nodes_expected: 3,
    },
    nodes: [],
    work_orders: [],
    alerts: [],
    notifications: [],
    rule_conclusions: [
      {
        schema_version: '2.2',
        conclusion_id: 'CONC-1',
        rule_id: 'RULE-BOTTLENECK',
        type: 'bottleneck_alert',
        node_code: 'milling-workshop-01',
        machine_code: 'MILL-02',
        risk_level: severity,
        severity,
        title: 'Milling bottleneck',
        summary: 'Milling backlog is above the operating band.',
        evidence: [{
          field: 'production.wip_input - production.wip_output',
          operator: '>=',
          value,
          threshold: 12,
          detail: 'Input WIP is accumulating.',
        }],
        recommended_actions: ['Throttle upstream release.'],
        source: { data_source: 'live', run_id: 'RUN-1', scenario_id: 'SCN-NORMAL' },
        read_only: true,
      },
    ],
    timeline: { recent_logs: [] },
  }
}

describe('rule explanation refresh policy', () => {
  it('ignores continuously changing evidence values while the rule facts remain the same', () => {
    expect(ruleExplanationSignature(snapshot(14))).toBe(ruleExplanationSignature(snapshot(18)))
    expect(ruleExplanationSignature(snapshot(14))).not.toBe(ruleExplanationSignature(snapshot(18, 'critical')))
  })

  it('allows one in-flight request and remembers a successful semantic signature', () => {
    const gate = createRuleExplanationRefreshGate()

    expect(gate.begin('RULE-A')).toBe(true)
    expect(gate.begin('RULE-A')).toBe(false)
    expect(gate.begin('RULE-B', true)).toBe(false)

    gate.finish('RULE-A', true)
    expect(gate.begin('RULE-A')).toBe(false)
    expect(gate.begin('RULE-B')).toBe(true)
  })

  it('backs off failed retries for the same signature without delaying a new rule set', () => {
    let now = 1_000
    const gate = createRuleExplanationRefreshGate({ cooldownMs: 60_000, now: () => now })

    expect(gate.begin('RULE-A')).toBe(true)
    gate.finish('RULE-A', false)
    expect(gate.begin('RULE-A')).toBe(false)
    expect(gate.begin('RULE-B')).toBe(true)
    gate.finish('RULE-B', false)

    now += 60_001
    expect(gate.begin('RULE-A')).toBe(true)
  })

  it('resets cached request state when the operator locks the console', () => {
    const gate = createRuleExplanationRefreshGate()

    expect(gate.begin('RULE-A')).toBe(true)
    gate.finish('RULE-A', true)
    expect(gate.begin('RULE-A')).toBe(false)

    gate.reset()
    expect(gate.begin('RULE-A')).toBe(true)
  })
})
