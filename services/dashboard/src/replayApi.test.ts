import { afterEach, describe, expect, it, vi } from 'vitest'
import { getReplayRun, listReplayRuns } from './replayApi'

function stubRuntime(body: unknown = { status: 'ok' }) {
  vi.stubGlobal('window', {
    localStorage: {
      getItem: (key: string) => (key === 'miniogas_access_token' ? 'runtime-token' : null)
    },
    dispatchEvent: vi.fn()
  })
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function lastCall(fetchMock: ReturnType<typeof vi.fn>) {
  const [url, init] = fetchMock.mock.calls.at(-1) ?? []
  return { url: String(url), init: init as RequestInit, headers: init?.headers as Headers }
}

describe('replayApi', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('lists replay runs through the protected API client', async () => {
    const fetchMock = stubRuntime({ status: 'ok', runs: [] })

    const payload = await listReplayRuns(8)

    expect(payload.status).toBe('ok')
    expect(lastCall(fetchMock).url).toBe('http://127.0.0.1:8080/api/replay/runs?limit=8')
    expect(lastCall(fetchMock).headers.get('Authorization')).toBe('Bearer runtime-token')
  })

  it('loads one encoded run detail with bounded rows', async () => {
    const fetchMock = stubRuntime({ status: 'ok', run_id: 'RUN A/1' })

    await getReplayRun('RUN A/1', 120)

    expect(lastCall(fetchMock).url).toBe('http://127.0.0.1:8080/api/replay/runs/RUN%20A%2F1?max_rows=120')
  })

  it('throws a readable error when the replay API rejects a request', async () => {
    stubRuntime()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('nope', { status: 404 })))

    await expect(getReplayRun('missing-run')).rejects.toThrow('replay detail HTTP 404')
  })
})
