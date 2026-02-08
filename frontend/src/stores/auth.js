import { reactive } from 'vue'
import { apiRequest, clearToken, getToken, setToken } from '../api/http'

export const authState = reactive({
  token: getToken(),
  me: null,
  loading: false,
})

export async function login(username, password) {
  authState.loading = true
  try {
    const data = await apiRequest('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    })

    setToken(data.access_token)
    authState.token = data.access_token
    await refreshMe()
    return authState.me
  } finally {
    authState.loading = false
  }
}

export function logout() {
  clearToken()
  authState.token = ''
  authState.me = null
}

export async function refreshMe() {
  if (!authState.token) {
    authState.me = null
    return null
  }

  const me = await apiRequest('/auth/me')
  authState.me = me
  return me
}
