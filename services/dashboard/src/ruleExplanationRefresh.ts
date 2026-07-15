import type { DashboardSnapshot } from './types'

type RefreshGateOptions = {
  cooldownMs?: number
  now?: () => number
}

export function ruleExplanationSignature(snapshot: DashboardSnapshot) {
  const conclusions = [...(snapshot.rule_conclusions ?? [])]
    .map((item) => ({
      id: item.conclusion_id,
      rule_id: item.rule_id,
      type: item.type,
      node_code: item.node_code,
      machine_code: item.machine_code,
      severity: item.severity,
      risk_level: item.risk_level,
      evidence_shape: (item.evidence ?? []).map((evidence) => ({
        field: evidence.field,
        operator: evidence.operator,
        threshold: evidence.threshold,
      })),
      recommended_actions: item.recommended_actions ?? [],
    }))
    .sort((left, right) => left.id.localeCompare(right.id))

  return JSON.stringify({
    run_id: snapshot.run?.run_id,
    scenario_id: snapshot.run?.scenario_id,
    conclusions,
  })
}

export function createRuleExplanationRefreshGate(options: RefreshGateOptions = {}) {
  const cooldownMs = options.cooldownMs ?? 60_000
  const now = options.now ?? Date.now
  let inFlight = false
  let lastSuccessfulSignature = ''
  let lastAttemptSignature = ''
  let lastAttemptAt = Number.NEGATIVE_INFINITY

  function begin(signature: string, force = false) {
    if (inFlight) return false
    const currentTime = now()
    if (!force && signature === lastSuccessfulSignature) return false
    if (!force && signature === lastAttemptSignature && currentTime - lastAttemptAt < cooldownMs) return false
    inFlight = true
    lastAttemptSignature = signature
    lastAttemptAt = currentTime
    return true
  }

  function finish(signature: string, succeeded: boolean) {
    inFlight = false
    if (succeeded) lastSuccessfulSignature = signature
  }

  function reset() {
    inFlight = false
    lastSuccessfulSignature = ''
    lastAttemptSignature = ''
    lastAttemptAt = Number.NEGATIVE_INFINITY
  }

  return { begin, finish, reset }
}
