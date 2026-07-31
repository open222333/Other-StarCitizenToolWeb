import { useAuthStore } from '@/stores/auth'
import router from '@/router'

/**
 * 帶 JWT 的 fetch，401 時自動嘗試用 Refresh Token 換發後重試一次。
 * 換發失敗 → 清除登入狀態（頁面由 router guard 跳轉）。
 */
async function apiFetch(path, options = {}, _retry = true) {
  const auth = useAuthStore()
  let res
  try {
    res = await fetch(path, {
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${auth.token}` },
      ...options,
    })
  } catch {
    return null
  }

  if (res.status === 401 && _retry) {
    const ok = await auth.tryRefresh()
    if (ok) return apiFetch(path, options, false)
    auth.clearAuth()
    router.push('/login')
    return null
  }
  return res
}

// ── 使用者 & 模板 API ────────────────────────────────────────────
export const userApi = {
  list:           ()         => apiFetch('/user/'),
  create:         (data)     => apiFetch('/user/',                 { method: 'POST',   body: JSON.stringify(data) }),
  update:         (id, data) => apiFetch(`/user/${id}`,           { method: 'PUT',    body: JSON.stringify(data) }),
  remove:         (id)       => apiFetch(`/user/${id}`,           { method: 'DELETE' }),

  listTemplates:  ()         => apiFetch('/user/templates/'),
  createTemplate: (data)     => apiFetch('/user/templates/',       { method: 'POST',   body: JSON.stringify(data) }),
  updateTemplate: (id, data) => apiFetch(`/user/templates/${id}`, { method: 'PUT',    body: JSON.stringify(data) }),
  removeTemplate: (id)       => apiFetch(`/user/templates/${id}`, { method: 'DELETE' }),
}

// ── 操作紀錄 API ─────────────────────────────────────────────────
export const logApi = {
  list: () => apiFetch('/log/'),
}
