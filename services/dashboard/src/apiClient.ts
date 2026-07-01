export const API_BASE = import.meta.env.VITE_OGAS_API_BASE ?? 'http://127.0.0.1:8080'

const tokenFromStorage = () => {
  try {
    return window.localStorage.getItem('miniogas_access_token') || ''
  } catch {
    return ''
  }
}

export function getAccessToken() {
  return tokenFromStorage() ?? ''
}

export function clearAccessToken() {
  try {
    window.localStorage.removeItem('miniogas_access_token')
  } catch {
    // Ignore storage errors; the visible session will still be locked by the event below.
  }
}

export function apiHeaders(extra?: HeadersInit): Headers {
  const token = getAccessToken()
  const headers = new Headers(extra)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  return headers
}

export function apiUrl(path: string) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export async function apiFetch(path: string, init: RequestInit = {}) {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: apiHeaders(init.headers)
  })
  if (response.status === 401) {
    clearAccessToken()
    window.dispatchEvent(new CustomEvent('miniogas-auth-expired', { detail: { path } }))
  }
  return response
}
