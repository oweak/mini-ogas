import { describe, expect, it } from 'vitest'
import { freshnessLabel, qualityPresentation, signalValueLabel } from './dataQuality'

describe('data quality presentation', () => {
  it('keeps stale telemetry distinct from bad measurements', () => {
    expect(qualityPresentation('uncertain', 'stale')).toEqual({
      label: '数据陈旧',
      tone: 'uncertain'
    })
    expect(qualityPresentation('bad', 'range_violation')).toEqual({
      label: '异常',
      tone: 'bad'
    })
  })

  it('formats freshness without hiding missing samples', () => {
    expect(freshnessLabel(null)).toBe('无采样')
    expect(freshnessLabel(480)).toBe('480 ms')
    expect(freshnessLabel(12_500)).toBe('12.5 s')
    expect(freshnessLabel(125_000)).toBe('2 min')
  })

  it('shows the typed unit with the observed value', () => {
    expect(signalValueLabel({
      signal_code: 'SPINDLE-TEMPERATURE',
      display_name: 'Spindle temperature',
      unit: 'Cel',
      value: 61.25,
      source: 'simulated',
      source_id: 'turning-workshop-01',
      source_timestamp: '2026-07-14T00:00:00Z',
      freshness_age_ms: 500,
      quality_code: 'good',
      quality_reason: ''
    })).toBe('61.25 Cel')
  })
})
