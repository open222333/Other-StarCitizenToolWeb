import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const KEYS = {
  token:   'admin_token',
  refresh: 'admin_refresh_token',
  user:    'admin_username',
  role:    'admin_role',
}

const PERMS = {
  admin:    ['user:read', 'user:write', 'template:write', 'log:read'],
  operator: ['log:read'],
  viewer:   ['log:read'],
}

export const useAuthStore = defineStore('auth', () => {
  const token        = ref(localStorage.getItem(KEYS.token)   || '')
  const refreshToken = ref(localStorage.getItem(KEYS.refresh) || '')
  const username     = ref(localStorage.getItem(KEYS.user)    || '')
  const role         = ref(localStorage.getItem(KEYS.role)    || '')

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin    = computed(() => role.value === 'admin')
  const can        = (action) => (PERMS[role.value] || []).includes(action)

  function setAuth(data) {
    token.value    = data.token        || ''
    username.value = data.username     || ''
    role.value     = data.role         || 'viewer'
    localStorage.setItem(KEYS.token, token.value)
    localStorage.setItem(KEYS.user,  username.value)
    localStorage.setItem(KEYS.role,  role.value)
    if (data.refresh_token) {
      refreshToken.value = data.refresh_token
      localStorage.setItem(KEYS.refresh, data.refresh_token)
    }
  }

  function clearAuth() {
    token.value = refreshToken.value = username.value = role.value = ''
    Object.values(KEYS).forEach(k => localStorage.removeItem(k))
  }

  async function tryRefresh() {
    if (!refreshToken.value) return false
    try {
      const res = await fetch('/auth/refresh', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${refreshToken.value}` },
      })
      if (!res.ok) return false
      const data = await res.json()
      if (!data.success) return false
      token.value = data.token
      localStorage.setItem(KEYS.token, data.token)
      if (data.role) { role.value = data.role; localStorage.setItem(KEYS.role, data.role) }
      return true
    } catch { return false }
  }

  return { token, refreshToken, username, role, isLoggedIn, isAdmin, can, setAuth, clearAuth, tryRefresh }
})
