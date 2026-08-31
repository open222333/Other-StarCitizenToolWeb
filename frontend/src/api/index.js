import { useAuthStore } from '@/stores/auth'
import router from '@/router'

/**
 * 帶 JWT 的 fetch，401 時自動嘗試用 Refresh Token 換發後重試一次。
 * 換發失敗 → 清除登入狀態（頁面由 router guard 跳轉）。
 */
export async function apiFetch(path, options = {}, _retry = true) {
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

// ── 玩家 API ─────────────────────────────────────────────────────
// 對應規格書第 15.1 節 players 資料表；後端 Flask blueprint 待實作（建議路由 /player/）
export const playerApi = {
  list:   ()         => apiFetch('/player/'),
  get:    (id)        => apiFetch(`/player/${id}`),
  create: (data)      => apiFetch('/player/',      { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data)  => apiFetch(`/player/${id}`, { method: 'PUT',  body: JSON.stringify(data) }),
  remove: (id)        => apiFetch(`/player/${id}`, { method: 'DELETE' }),
  // 後台重設玩家密碼：不需要舊密碼（role 本身就是背書），獨立路由、
  // 不走 update() —— 詳見 app/player/view.py 的 set_player_password()。
  setPassword: (id, newPassword) => apiFetch(`/player/${id}/password`, {
    method: 'PUT', body: JSON.stringify({ new_password: newPassword }),
  }),
}

// ── 玩家自助註冊 / 登入（公開，不需要登入）────────────────────────
// 跟上面 playerApi 不同：這裡故意不走 apiFetch()，因為 apiFetch 會帶著（可能是空的）
// 後台 admin JWT，401 時還會嘗試 refresh 並導去 /login，那套邏輯是給已登入的後台
// 操作用的，不適合給未登入的訪客，也不適合玩家自己的 token（玩家 token 是另一套
// 身分體系，見 app/player/view.py 的 additional_claims.type == 'player'）。
export async function registerPlayer({ nickname, star_citizen_id, password }) {
  try {
    const res = await fetch('/player/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // player_name 目前後端仍要求必填，註冊頁面只收暱稱／遊戲ID／密碼，都帶給後端，
      // 若後端改成允許只填 nickname，前端這裡不用改。
      body: JSON.stringify({ nickname, star_citizen_id, password, player_name: nickname }),
    })
    return res
  } catch {
    return null
  }
}

export async function loginPlayer({ star_citizen_id, password }) {
  try {
    const res = await fetch('/player/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ star_citizen_id, password }),
    })
    return res
  } catch {
    return null
  }
}

// ── 藍圖 API ─────────────────────────────────────────────────────
// 對應規格書第 15.3 節 blueprints 資料表；後端待實作（建議路由 /blueprint/）
export const blueprintApi = {
  // ── 玩家藍圖名冊（誰擁有哪張藍圖，人填的）──
  list:   (params)   => apiFetch(`/blueprint/${qs(params)}`),
  get:    (id)        => apiFetch(`/blueprint/${id}`),
  create: (data)      => apiFetch('/blueprint/',      { method: 'POST', body: JSON.stringify(data) }),
  update: (id, data)  => apiFetch(`/blueprint/${id}`, { method: 'PUT',  body: JSON.stringify(data) }),
  remove: (id)        => apiFetch(`/blueprint/${id}`, { method: 'DELETE' }),

  // ── 製造藍圖主檔（遊戲資料，1,600+ 筆配方，唯讀）──
  // 由 tasks/scdata_sync.py 從 Star Citizen Wiki API 同步進 blueprint_master。
  // 跟上面的名冊是兩種不同性質的資料，見 app/blueprint/view.py 檔頭。
  masterList:     (params) => apiFetch(`/blueprint/master${qs(params)}`),
  masterSearch:   (q, limit = 25) => apiFetch(`/blueprint/master/search${qs({ q, limit })}`),
  masterTypes:    ()       => apiFetch('/blueprint/master/types'),
  masterGet:      (uuid)   => apiFetch(`/blueprint/master/${uuid}`),
  masterForItem:  (itemUuid) => apiFetch(`/blueprint/master/for-item/${itemUuid}`),
}

// ── 戰利品（Loot）API ────────────────────────────────────────────
// 對應規格書第 15.4 節 loot_records 資料表；後端待實作（建議路由 /loot/）
export const lootApi = {
  list:       (params)  => apiFetch(`/loot/${qs(params)}`),
  get:        (id)       => apiFetch(`/loot/${id}`),
  create:     (data)     => apiFetch('/loot/',      { method: 'POST', body: JSON.stringify(data) }),
  update:     (id, data) => apiFetch(`/loot/${id}`, { method: 'PUT',  body: JSON.stringify(data) }),
  remove:     (id)       => apiFetch(`/loot/${id}`, { method: 'DELETE' }),
  // 第 6.6 節：戰利品分配
  distribute: (id, data) => apiFetch(`/loot/${id}/distribute`, { method: 'POST', body: JSON.stringify(data) }),
  // 第 12.1 節：全域搜尋（跨玩家／藍圖／Loot）
  search:     (keyword)  => apiFetch(`/loot/search${qs({ q: keyword })}`),
}

// ── 庫存 API ─────────────────────────────────────────────────────
// 對應 app/inventory/view.py，管理主控台可操作任何歸屬（guild／player），
// 寫入（add/remove/move）需要 admin 或 operator 角色。
export const inventoryApi = {
  list:      (params)  => apiFetch(`/inventory/${qs(params)}`),
  locations: ()         => apiFetch('/inventory/locations'),
  whereItem: (itemId)   => apiFetch(`/inventory/where/${itemId}`),
  capacity:  (params)   => apiFetch(`/inventory/capacity${qs(params)}`),
  history:   (params)   => apiFetch(`/inventory/history${qs(params)}`),
  add:       (data)     => apiFetch('/inventory/add',    { method: 'POST', body: JSON.stringify(data) }),
  remove:    (data)     => apiFetch('/inventory/remove', { method: 'POST', body: JSON.stringify(data) }),
  move:      (data)     => apiFetch('/inventory/move',   { method: 'POST', body: JSON.stringify(data) }),
}

// ── 遊戲主檔同步 API ─────────────────────────────────────────────
// 對應 app/item/view.py 的 /item/sync-status、/item/sync、/item/sync-schedule
export const itemApi = {
  syncStatus:         ()     => apiFetch('/item/sync-status'),
  syncNow:            (data) => apiFetch('/item/sync', { method: 'POST', body: JSON.stringify(data || {}) }),
  getSyncSchedule:    ()     => apiFetch('/item/sync-schedule'),
  updateSyncSchedule: (data) => apiFetch('/item/sync-schedule', { method: 'PUT', body: JSON.stringify(data || {}) }),
}

// ── 共用：把物件轉成 query string（略過 undefined／空字串） ──────
function qs(params) {
  if (!params) return ''
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  if (!entries.length) return ''
  return '?' + new URLSearchParams(entries).toString()
}
