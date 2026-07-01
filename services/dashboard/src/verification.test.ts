import { describe, expect, it } from 'vitest'
import { verificationSummary } from './verification'

describe('verificationSummary', () => {
  it('returns an empty string when no verification snapshot exists', () => {
    expect(verificationSummary()).toBe('')
    expect(verificationSummary({})).toBe('')
    expect(verificationSummary({ verification: null })).toBe('')
  })

  it('summarizes closed issue, removed alarm, node status, and order status', () => {
    expect(verificationSummary({
      verification: {
        issue_closed: true,
        alarm_removed: true,
        node_status_after: 'running',
        order_status_after: 'rescheduled'
      }
    })).toBe('问题已关闭 / 报警已移除 / 节点=running / 工单=rescheduled')
  })

  it('keeps failed close and lingering alarm visible in the summary', () => {
    expect(verificationSummary({
      verification: {
        issue_closed: false,
        alarm_removed: false
      }
    })).toBe('问题未关闭 / 报警仍存在')
  })
})
