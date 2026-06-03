export type FetchSlot<T> = {
  ok: boolean
  data?: T
}

export type AlarmFetchMerge<TAlert, TDiagnosis, TEscalation> = {
  alerts?: TAlert[]
  diagnoses?: TDiagnosis[]
  escalations?: TEscalation[]
  apiAvailable: boolean
}

export function mergeAlarmFetchResults<TAlert, TDiagnosis, TEscalation>(
  alerts: FetchSlot<TAlert[]>,
  diagnoses: FetchSlot<TDiagnosis[]>,
  escalations: FetchSlot<TEscalation[]>
): AlarmFetchMerge<TAlert, TDiagnosis, TEscalation> {
  return {
    alerts: alerts.ok ? alerts.data ?? [] : undefined,
    diagnoses: diagnoses.ok ? diagnoses.data ?? [] : undefined,
    escalations: escalations.ok ? escalations.data ?? [] : undefined,
    apiAvailable: alerts.ok || diagnoses.ok || escalations.ok
  }
}

export type BackendLogEvent = {
  time: string
  level: string
  source: string
  message: string
}

export function visibleRuntimeEvents(logEvents: BackendLogEvent[], liveLogs: string[]): BackendLogEvent[] {
  if (logEvents.length) return logEvents.slice(0, 8)
  return liveLogs.map((log) => ({
    time: log.slice(0, 8),
    level: 'info',
    source: 'central-api',
    message: log.slice(9)
  }))
}
