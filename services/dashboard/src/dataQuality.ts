export type QualityCode = 'good' | 'uncertain' | 'bad' | 'missing' | string

export type TelemetrySignal = {
  signal_code: string
  display_name: string
  unit: string
  value: number | string | boolean | null
  source: string | null
  source_id: string | null
  equipment_code?: string | null
  source_timestamp: string | null
  freshness_age_ms: number | null
  quality_code: QualityCode
  quality_reason: string
}

export type QualitySummary = {
  generated_at: string
  source_of_truth: string
  counts: Record<string, number>
  signals: TelemetrySignal[]
}

export type ProjectionStatus = {
  provider: string
  available: boolean
  active_generation: string | null
  authority: string
}

export function qualityPresentation(code: QualityCode, reason = '') {
  if (code === 'good') return { label: '鑹ソ', tone: 'good' }
  if (code === 'uncertain') {
    return { label: reason === 'stale' ? '鏁版嵁闄堟棫' : '寰呯‘璁?, tone: 'uncertain' }
  }
  if (code === 'missing' || reason === 'missing') return { label: '鏈笂鎶?, tone: 'missing' }
  return { label: '寮傚父', tone: 'bad' }
}

export function freshnessLabel(ageMs: number | null) {
  if (ageMs === null || !Number.isFinite(ageMs)) return '鏃犻噰鏍?
  if (ageMs < 1_000) return `${Math.max(0, Math.round(ageMs))} ms`
  if (ageMs < 60_000) return `${(ageMs / 1_000).toFixed(1)} s`
  return `${Math.floor(ageMs / 60_000)} min`
}

export function signalValueLabel(signal: TelemetrySignal) {
  if (signal.value === null) return '鏈笂鎶?
  const value = typeof signal.value === 'number'
    ? signal.value.toLocaleString('zh-CN', { maximumFractionDigits: 3 })
    : String(signal.value)
  return signal.unit ? `${value} ${signal.unit}` : value
}
