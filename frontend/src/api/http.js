const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1'

export function getToken() {
  return localStorage.getItem('jm_token') || ''
}

export function setToken(token) {
  localStorage.setItem('jm_token', token)
}

export function clearToken() {
  localStorage.removeItem('jm_token')
}

export async function apiRequest(path, options = {}) {
  const token = getToken()
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`
  }

  const resp = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  })

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`
    try {
      const raw = await resp.text()
      if (raw) {
        try {
          const body = JSON.parse(raw)
          detail = body?.detail || JSON.stringify(body)
        } catch {
          detail = raw
        }
      }
    } catch {
      // ignore read error and keep fallback HTTP status
    }
    throw new Error(detail)
  }

  const contentType = resp.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return resp.json()
  }
  return resp
}

export function buildApiPath(path) {
  return `${API_BASE}${path}`
}
