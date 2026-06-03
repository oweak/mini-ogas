export const API_BASE = import.meta.env.VITE_OGAS_API_BASE ?? 'http://127.0.0.1:8080'

const tokenFromStorage = () => {
  try {
    return window.localStorage.getItem('miniogas_token') || ''
  } catch {
    return ''
  }
}

export function getApiToken() {
  return import.meta.env.VITE_OGAS_TOKEN ?? tokenFromStorage() ?? ''
}

export function apiHeaders(extra?: HeadersInit): Headers {
  const token = getApiToken()
  const headers = new Headers(extra)
  if (token) headers.set('X-OGAS-Token', token)
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  return headers
}

export function apiUrl(path: string) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export function apiFetch(path: string, init: RequestInit = {}) {
  return fetch(apiUrl(path), {
    ...init,
    headers: apiHeaders(init.headers)
  })
}
