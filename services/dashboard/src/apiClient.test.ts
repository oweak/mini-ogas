import { afterEach, describe, expect, it, vi } from 'vitest'
import { API_BASE, apiFetch, apiHeaders, apiUrl, getAccessToken } from './apiClient'

function stubStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial))
  vi.stubGlobal('window', {
    localStorage: {
      getItem: (key: string) => data.get(key) ?? null,
      setItem: (key: string, value: string) => data.set(key, value),
      removeItem: (key: string) => data.delete(key),
      clear: () => data.clear()
    },
    dispatchEvent: vi.fn()
  })
  return data
}

describe('apiClient', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('uses the configured central API base URL', () => {
    expect(API_BASE).toBe('http://127.0.0.1:8080')
    expect(apiUrl('/api/alerts')).toBe('http://127.0.0.1:8080/api/alerts')
    expect(apiUrl('api/alerts')).toBe('http://127.0.0.1:8080/api/alerts')
  })

  it('does not bake in the development token when no token is configured', () => {
    stubStorage()
    expect(getAccessToken()).toBe('')
    expect(apiHeaders().has('Authorization')).toBe(false)
  })

  it('loads the runtime token from localStorage and preserves extra headers', () => {
    stubStorage({ miniogas_access_token: 'runtime-token' })
    const headers = apiHeaders({ Accept: 'application/json' })

    expect(headers.get('Authorization')).toBe('Bearer runtime-token')
    expect(headers.get('Accept')).toBe('application/json')
    expect(headers.get('Content-Type')).toBe('application/json')
  })

  it('sends all API calls through the shared authenticated fetch wrapper', async () => {
    stubStorage({ miniogas_access_token: 'runtime-token' })
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}'))
    vi.stubGlobal('fetch', fetchMock)

    await apiFetch('/api/dashboard-state', { method: 'POST', body: JSON.stringify({ ok: true }) })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    const headers = init?.headers as Headers
    expect(url).toBe('http://127.0.0.1:8080/api/dashboard-state')
    expect(init?.method).toBe('POST')
    expect(headers.get('Authorization')).toBe('Bearer runtime-token')
  })

  it('clears stale auth and broadcasts when the API returns 401', async () => {
    const storage = stubStorage({ miniogas_access_token: 'stale-token' })
    vi.stubGlobal('CustomEvent', class {
      type: string
      detail: unknown

      constructor(type: string, init?: { detail?: unknown }) {
        this.type = type
        this.detail = init?.detail
      }
    })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 401 })))

    const response = await apiFetch('/api/reports/production')

    expect(response.status).toBe(401)
    expect(storage.has('miniogas_access_token')).toBe(false)
    expect(window.dispatchEvent).toHaveBeenCalledTimes(1)
  })
})
