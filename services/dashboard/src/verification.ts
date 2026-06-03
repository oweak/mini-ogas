export type VerificationSnapshot = {
  verified_at?: string
  issue_closed?: boolean
  alarm_removed?: boolean
  node_status_after?: string
  order_status_after?: string
  audit_expected?: boolean
}

export type EffectWithVerification = {
  verification?: VerificationSnapshot
} & Record<string, unknown>

export function verificationFromEffect(effect?: Record<string, unknown> | null): VerificationSnapshot | null {
  const raw = effect?.verification
  return raw && typeof raw === 'object' ? raw as VerificationSnapshot : null
}

export function verificationSummary(effect?: Record<string, unknown> | null): string {
  const verification = verificationFromEffect(effect)
  if (!verification) return ''
  const closed = verification.issue_closed ? '问题已关闭' : '问题未关闭'
  const alarm = verification.alarm_removed ? '报警已移除' : '报警仍存在'
  const node = verification.node_status_after ? `节点=${verification.node_status_after}` : ''
  const order = verification.order_status_after ? `工单=${verification.order_status_after}` : ''
  return [closed, alarm, node, order].filter(Boolean).join(' / ')
}
