import { apiFetch } from './apiClient'

export type ActorPayload = {
  actor?: string
  operator?: string
}

export function recalculateDispatchPlan() {
  return apiFetch('/api/ops/dispatch-plan/recalculate', { method: 'POST' })
}

export function approveDispatchPlan(confirmationCode: string, actor = '车间主管') {
  return apiFetch('/api/ops/dispatch-plan/approve', {
    method: 'POST',
    body: JSON.stringify({ actor, confirmation_code: confirmationCode })
  })
}

export function confirmAlert(issueId: string, operator = '车间主管') {
  return apiFetch(`/api/alerts/${encodeURIComponent(issueId)}/confirm`, {
    method: 'POST',
    body: JSON.stringify({ action: '确认真实报警', operator })
  })
}

export function diagnoseIssue(issueId: string) {
  return apiFetch(`/api/ai/diagnose/${encodeURIComponent(issueId)}`, { method: 'POST' })
}

export function diagnosePayload(payload: {
  node_code: string
  alert_description: string
  alert_type: string
  severity: string
}) {
  return apiFetch('/api/ai/diagnose', {
    method: 'POST',
    body: JSON.stringify(payload)
  })
}

export function isolateNode(nodeCode: string, confirmationCode: string, actor = '车间主管') {
  return apiFetch(`/api/nodes/${encodeURIComponent(nodeCode)}/isolate`, {
    method: 'POST',
    body: JSON.stringify({ decision: 'approve', actor, confirmation_code: confirmationCode })
  })
}

export function escalateIssue(params: {
  nodeCode: string
  issueType: string
  description: string
  actor?: string
}) {
  const query = new URLSearchParams({
    node_code: params.nodeCode,
    issue_type: params.issueType,
    description: params.description,
    actor: params.actor ?? '车间主管'
  })
  return apiFetch(`/api/ops/escalate?${query.toString()}`, { method: 'POST' })
}

export function closeIssue(issueId: string, action = '验证完成并关闭问题', operator = '车间主管') {
  return apiFetch(`/api/issues/${encodeURIComponent(issueId)}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action, operator })
  })
}

export function decideIssue(
  issueId: string,
  decision: 'observe' | 'ignore',
  note = '',
  operator = '车间主管'
) {
  return apiFetch(`/api/issues/${encodeURIComponent(issueId)}/decision`, {
    method: 'POST',
    body: JSON.stringify({ decision, operator, note })
  })
}

export function decideEscalation(
  escalationId: number,
  decision: 'approve' | 'reject',
  confirmationCode: string,
  actor = '车间主管'
) {
  return apiFetch(`/api/ops/escalations/${escalationId}/decision`, {
    method: 'POST',
    body: JSON.stringify({ actor, decision, confirmation_code: confirmationCode })
  })
}
