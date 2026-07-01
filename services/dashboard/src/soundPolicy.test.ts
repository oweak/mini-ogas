import { describe, expect, it } from 'vitest'
import { alertSoundForNewIssues, soundGain, soundPatterns, type SoundKind } from './soundPolicy'

describe('alertSoundForNewIssues', () => {
  it('returns null when no issue is new', () => {
    expect(alertSoundForNewIssues([{ id: 'ALM-1', severity: '高危' }], new Set(['ALM-1']))).toBeNull()
  })

  it('uses critical sound for new critical issues', () => {
    expect(alertSoundForNewIssues([{ id: 'ALM-2', severity: '高危' }], new Set())).toBe('critical')
    expect(alertSoundForNewIssues([{ id: 'ALM-3', severity: 'critical' }], new Set())).toBe('critical')
  })

  it('uses warning sound for new warning and high issues', () => {
    expect(alertSoundForNewIssues([{ id: 'ALM-4', severity: '预警' }], new Set())).toBe('warning')
    expect(alertSoundForNewIssues([{ id: 'ALM-5', severity: 'high' }], new Set())).toBe('warning')
  })

  it('falls back to notice for low-priority new notifications', () => {
    expect(alertSoundForNewIssues([{ id: 'NOTICE-1', severity: '通知' }], new Set())).toBe('notice')
  })
})

describe('sound policy', () => {
  it('defines a playable pattern for every sound kind', () => {
    const kinds: SoundKind[] = ['notice', 'warning', 'critical', 'success', 'error', 'step']
    expect(kinds.every((kind) => soundPatterns[kind].length > 0)).toBe(true)
  })

  it('makes critical louder than warning and warning louder than notice', () => {
    expect(soundGain('critical')).toBeGreaterThan(soundGain('warning'))
    expect(soundGain('warning')).toBeGreaterThan(soundGain('notice'))
  })
})
