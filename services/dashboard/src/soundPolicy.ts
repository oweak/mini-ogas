export type SoundKind = 'notice' | 'warning' | 'critical' | 'success' | 'error' | 'step'

export type SoundPattern = Array<[frequency: number, offset: number, duration: number]>

export const soundPatterns: Record<SoundKind, SoundPattern> = {
  notice: [[660, 0, 0.08]],
  warning: [[650, 0, 0.1], [840, 0.14, 0.12]],
  critical: [[860, 0, 0.1], [1080, 0.13, 0.1], [860, 0.26, 0.14]],
  success: [[520, 0, 0.08], [760, 0.1, 0.16]],
  error: [[220, 0, 0.16], [180, 0.19, 0.18]],
  step: [[430, 0, 0.09], [610, 0.11, 0.09], [790, 0.22, 0.12]]
}

export type IssueSoundInput = {
  id: string
  severity: string
}

export function alertSoundForNewIssues(issues: IssueSoundInput[], knownIssueIds: Set<string>): SoundKind | null {
  const newIssues = issues.filter((issue) => !knownIssueIds.has(issue.id))
  if (!newIssues.length) return null
  if (newIssues.some((issue) => issue.severity === '高危' || issue.severity === 'critical')) return 'critical'
  if (newIssues.some((issue) => ['高', '预警', 'warning', 'high'].includes(issue.severity))) return 'warning'
  return 'notice'
}

export function soundGain(kind: SoundKind): number {
  if (kind === 'critical') return 0.09
  if (kind === 'warning') return 0.065
  return 0.045
}
