import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// 玩家登入狀態，跟後台 admin 的 useAuthStore（stores/auth.js）分開存放，
// 兩邊 JWT 是不同身分體系，key 也刻意不同，避免互相覆蓋。
const KEYS = {
  token:   'sc_player_token',
  refresh: 'sc_player_refresh_token',
  scid:    'sc_player_star_citizen_id',
  nickname: 'sc_player_nickname',
}

export const usePlayerAuthStore = defineStore('playerAuth', () => {
  const token          = ref(localStorage.getItem(KEYS.token)    || '')
  const refreshToken   = ref(localStorage.getItem(KEYS.refresh)  || '')
  const starCitizenId  = ref(localStorage.getItem(KEYS.scid)     || '')
  const nickname       = ref(localStorage.getItem(KEYS.nickname) || '')

  const isLoggedIn = computed(() => !!token.value)

  function setAuth(data) {
    token.value         = data.token           || ''
    starCitizenId.value = data.star_citizen_id || ''
    nickname.value      = data.nickname        || ''
    localStorage.setItem(KEYS.token,    token.value)
    localStorage.setItem(KEYS.scid,     starCitizenId.value)
    localStorage.setItem(KEYS.nickname, nickname.value)
    if (data.refresh_token) {
      refreshToken.value = data.refresh_token
      localStorage.setItem(KEYS.refresh, data.refresh_token)
    }
  }

  function clearAuth() {
    token.value = refreshToken.value = starCitizenId.value = nickname.value = ''
    Object.values(KEYS).forEach(k => localStorage.removeItem(k))
  }

  // 進行中的 refresh。多個請求同時 401 時共用同一個 promise，
  // 否則畫面上七八支 API 一起過期就會送出七八個 /player/refresh ——
  // 那支端點有「30 per minute」限速，同一個 NAT 底下開幾個分頁就會撞到
  // 429，tryRefresh 全部回 false，使用者被無故登出。
  let refreshing = null

  async function tryRefresh() {
    if (!refreshToken.value) return false
    if (refreshing) return refreshing

    refreshing = (async () => {
      try {
        const res = await fetch('/player/refresh', {
          method: 'POST',
          headers: { 'Authorization': `Bearer ${refreshToken.value}` },
        })
        if (!res.ok) return false
        const data = await res.json()
        if (!data.success) return false
        token.value = data.token
        localStorage.setItem(KEYS.token, data.token)
        return true
      } catch {
        return false
      } finally {
        refreshing = null
      }
    })()
    return refreshing
  }

  async function playerFetch(path, options = {}, _retry = true) {
    let res
    try {
      // ⚠️ headers 要在展開 options 之後再合併：反過來寫的話，呼叫端只要
      // 自帶 headers（例如上傳檔案時改 Content-Type）就會整欄蓋掉，
      // Authorization 跟著消失 → 認證靜默失效，兩次 401 後直接被登出。
      const { headers: extraHeaders, ...rest } = options
      res = await fetch(path, {
        ...rest,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token.value}`,
          ...(extraHeaders || {}),
        },
      })
    } catch {
      return null
    }
    if (res.status === 401 && _retry) {
      const ok = await tryRefresh()
      if (ok) return playerFetch(path, options, false)
      clearAuth()
      return null
    }
    return res
  }

  return {
    token, refreshToken, starCitizenId, nickname,
    isLoggedIn, setAuth, clearAuth, tryRefresh, playerFetch,
  }
})
