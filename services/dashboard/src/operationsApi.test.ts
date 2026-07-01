import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  approveDispatchPlan,
  closeIssue,
  confirmAlert,
  decideIssue,
  decideEscalation,
  diagnoseIssue,
  diagnosePayload,
  escalateIssue,
  isolateNode,
  recalculateDispatchPlan
} from './operationsApi'

function stubRuntime() {
  vi.stubGlobal('window', {
    localStorage: {
      getItem: (key: string) => (key === 'miniogas_access_token' ? 'runtime-token' : null)
    }
  })
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}'))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>) {
  const [url, init] = fetchMock.mock.calls.at(-1) ?? []
  return { url: String(url), init: init as RequestInit, headers: init?.headers as Headers }
}

describe('operationsApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('uses distinct routes for dispatch recalculate and approval', async () => {
    const fetchMock = stubRuntime()

    await recalculateDispatchPlan()
    expect(lastCall(fetchMock).url).toBe('http://127.0.0.1:8080/api/ops/dispatch-plan/recalculate')
    expect(lastCall(fetchMock).init.method).toBe('POST')

    await approveDispatchPlan('CONFIRM')
    const approval = lastCall(fetchMock)
    expect(approval.url).toBe('http://127.0.0.1:8080/api/ops/dispatch-plan/approve')
    expect(JSON.parse(String(approval.init.body))).toEqual({ actor: '车间主管', confirmation_code: 'CONFIRM' })
  })

  it('keeps alert confirmation separate from human escalation', async () => {
    const fetchMock = stubRuntime()

    await confirmAlert('milling-workshop-01-SPINDLE_TEMP_HIGH')
    const confirm = lastCall(fetchMock)
    expect(confirm.url).toBe('http://127.0.0.1:8080/api/alerts/milling-workshop-01-SPINDLE_TEMP_HIGH/confirm')
    expect(JSON.parse(String(confirm.init.body)).action).toBe('确认真实报警')

    await escalateIssue({
      nodeCode: 'milling-workshop-01',
      issueType: '主轴温度过高',
      description: '人工升级：温度 91 C'
    })
    const escalation = lastCall(fetchMock)
    expect(escalation.url).toContain('/api/ops/escalate?')
    expect(decodeURIComponent(escalation.url)).toContain('issue_type=主轴温度过高')
    expect(escalation.init.method).toBe('POST')
  })

  it('calls concrete node control and close routes without NL command routing', async () => {
    const fetchMock = stubRuntime()

    await isolateNode('milling-workshop-01', 'CONFIRM')
    const isolated = lastCall(fetchMock)
    expect(isolated.url).toBe('http://127.0.0.1:8080/api/nodes/milling-workshop-01/isolate')
    expect(JSON.parse(String(isolated.init.body))).toEqual({
      decision: 'approve',
      actor: '车间主管',
      confirmation_code: 'CONFIRM'
    })

    await closeIssue('milling-workshop-01-SPINDLE_TEMP_HIGH')
    const closed = lastCall(fetchMock)
    expect(closed.url).toBe('http://127.0.0.1:8080/api/issues/milling-workshop-01-SPINDLE_TEMP_HIGH/actions')
    expect(JSON.parse(String(closed.init.body)).action).toBe('验证完成并关闭问题')
  })

  it('covers AI diagnosis and human escalation decisions', async () => {
    const fetchMock = stubRuntime()

    await diagnoseIssue('grinding-workshop-01-VIBRATION_HIGH')
    expect(lastCall(fetchMock).url).toBe('http://127.0.0.1:8080/api/ai/diagnose/grinding-workshop-01-VIBRATION_HIGH')

    await diagnosePayload({
      node_code: 'turning-workshop-01',
      alert_description: '良品率漂移',
      alert_type: 'QUALITY_DRIFT',
      severity: 'warning'
    })
    expect(lastCall(fetchMock).url).toBe('http://127.0.0.1:8080/api/ai/diagnose')

    await decideEscalation(7, 'approve', 'CONFIRM')
    const decision = lastCall(fetchMock)
    expect(decision.url).toBe('http://127.0.0.1:8080/api/ops/escalations/7/decision')
    expect(JSON.parse(String(decision.init.body))).toEqual({
      actor: '车间主管',
      decision: 'approve',
      confirmation_code: 'CONFIRM'
    })
  })

  it('routes observe and ignore decisions to the issue decision endpoint', async () => {
    const fetchMock = stubRuntime()

    await decideIssue('milling-workshop-01-SPINDLE_TEMP_HIGH', 'observe', '保持运行观察')
    const observe = lastCall(fetchMock)
    expect(observe.url).toBe('http://127.0.0.1:8080/api/issues/milling-workshop-01-SPINDLE_TEMP_HIGH/decision')
    expect(JSON.parse(String(observe.init.body))).toEqual({
      decision: 'observe',
      operator: '车间主管',
      note: '保持运行观察'
    })

    await decideIssue('milling-workshop-01-SPINDLE_TEMP_HIGH', 'ignore', '人工判定误报')
    const ignore = lastCall(fetchMock)
    expect(ignore.url).toBe('http://127.0.0.1:8080/api/issues/milling-workshop-01-SPINDLE_TEMP_HIGH/decision')
    expect(JSON.parse(String(ignore.init.body)).decision).toBe('ignore')
  })

  it('adds the runtime token to every operation request', async () => {
    const fetchMock = stubRuntime()

    await confirmAlert('issue-1')
    expect(lastCall(fetchMock).headers.get('Authorization')).toBe('Bearer runtime-token')
  })
})
