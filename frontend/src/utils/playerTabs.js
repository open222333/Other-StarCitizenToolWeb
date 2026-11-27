// 玩家頁的主分頁定義（MyPlayerView.vue 的分頁列、後台「系統設定」的分頁排序共用）。
// 排列順序：後台設定的順序（app_settings.player_tab_order，/player/me 帶 tab_order）優先，
// 沒列到的分頁（例如之後新增的）照這裡的順序接在後面。
// member: true＝會員功能（要登入，沒登入時整頁是登入提示）；沒標的不登入也能用（後端是 @public_api，見 src/permissions.py）。
export const PLAYER_TABS = [
  {
    // 艦長室：自己登記的倉庫、藍圖、艦隊（原本是三個主分頁，舊網址 ?tab=warehouse|blueprints|fleet 會轉過來）
    key: 'my', label: '艦長室', icon: 'bi bi-person-badge', member: true,
    subTabs: [{ key: 'warehouse', label: '倉庫' }, { key: 'blueprints', label: '藍圖' }, { key: 'fleet', label: '艦隊' }],
  },
  // 新聞：後台或外部程式（API 金鑰）寫入的新聞，不登入也能看（components/NewsBoard.vue）
  { key: 'news', label: '新聞', icon: 'bi bi-newspaper' },
  {
    // 資料庫：遊戲資料（唯讀，不登入也能看）。key 沿用原本「物品」分頁的 items，後台設定與舊網址不用改；
    // 任務原本是主分頁（舊網址 ?tab=missions 會轉過來）
    key: 'items', label: '資料庫', icon: 'bi bi-database',
    subTabs: [
      { key: 'data', label: '物品' }, { key: 'bpdata', label: '藍圖' }, { key: 'vehicles', label: '艦船' },
      // 飛船組件：護盾、發電機、冷卻器、量子引擎、武器、飛彈、雷達…（components/ShipComponentDatabase.vue）
      { key: 'components', label: '飛船組件' },
      { key: 'missions', label: '任務' }, { key: 'factions', label: '勢力' }, { key: 'minerals', label: '礦物' }, { key: 'commodities', label: '商品購買地點' },
    ],
  },
  // 量子航線規劃（多站點；見 components/RoutePlanner.vue）、合約分配（多合約 × 多小隊；見 components/ContractPlanner.vue）
  {
    key: 'route', label: '航線', icon: 'bi bi-signpost-split',
    subTabs: [{ key: 'plan', label: '航線規劃' }, { key: 'contracts', label: '合約分配' }],
  },
  {
    // 工具箱：原本各自是主分頁（舊網址 ?tab=mining|loadout|cargo|payout|gamelog|chatcode 會轉過來）。
    // 下層分頁標 member: true 的（戰術小隊）沒登入時顯示登入提示，其他不用登入。
    //   礦物回波（components/MiningLookup.vue）、配裝模擬（LoadoutSimulator.vue）、戰術小隊（SquadBoards.vue）、
    //   貨艙網格（CargoLoader.vue，資料是 sc-cargo.space 的貨物網格）、貨櫃試算（CrateCalculator.vue，總量拆成幾種貨櫃）、酬勞分配、LOG 解析、中文轉碼
    key: 'toolbox', label: '工具箱', icon: 'bi bi-tools',
    subTabs: [
      { key: 'mining', label: '礦物回波' }, { key: 'loadout', label: '配裝模擬' },
      { key: 'squads', label: '戰術小隊', member: true }, { key: 'cargo', label: '貨艙網格' }, { key: 'crates', label: '貨櫃試算' },
      { key: 'payout', label: '酬勞分配' }, { key: 'gamelog', label: 'LOG 解析' }, { key: 'chatcode', label: '中文轉碼' },
    ],
  },
  {
    // 原名「查詢」；查公會成員持有的物品、藍圖、船艦
    key: 'search',    label: '查詢持有資訊',   icon: 'bi bi-search', short: '查詢', member: true,
  },
  { key: 'tools',     label: '工具網站', icon: 'bi bi-link-45deg' },
  // 「個人資料」不是分頁：點最上方的名字打開視窗（MyPlayerView.vue 的 profileOpen；舊網址 ?tab=profile 會打開它）
]

/** 舊的主分頁 → 現在所在的主分頁與下層分頁（倉庫、藍圖、艦隊併進「艦長室」；任務放進「資料庫」；
 *  礦物、配裝模擬、貨艙網格、酬勞分配、LOG 解析、中文轉碼併進「工具箱」） */
/** 「查詢持有資訊」記在網址上的條件鍵名（components/PlayerHoldersSearch.vue 寫入；MyPlayerView 離開那個分頁時拿掉） */
export const SEARCH_URL_KEYS = ['k', 'q', 'pk', 'pid', 'pn', 'p', 'i_t', 'i_sys', 'i_pl', 'i_loc',
  'b_t', 'f_t', 'f_s', 'f_m', 'f_r']

export const LEGACY_TABS = {
  warehouse: { tab: 'my', sub: 'warehouse' },
  blueprints: { tab: 'my', sub: 'blueprints' },
  fleet: { tab: 'my', sub: 'fleet' },
  missions: { tab: 'items', sub: 'missions' },
  mining: { tab: 'toolbox', sub: 'mining' },
  loadout: { tab: 'toolbox', sub: 'loadout' },
  cargo: { tab: 'toolbox', sub: 'cargo' },
  payout: { tab: 'toolbox', sub: 'payout' },
  gamelog: { tab: 'toolbox', sub: 'gamelog' },
  chatcode: { tab: 'toolbox', sub: 'chatcode' },
}

/** 整個內容都是從舊分頁併進來的新分頁：舊分頁全部藏起來時，新分頁也藏 */
const MERGED_TABS = ['my', 'toolbox']

/** 後台存的分頁順序／玩家存的隱藏分頁：舊分頁換成新的主分頁、去掉重複 */
export function normalizeTabKeys(keys) {
  const out = []
  for (const k of keys || []) {
    const key = LEGACY_TABS[k]?.tab || k
    if (!out.includes(key)) out.push(key)
  }
  return out
}

/** 下層分頁（子功能）在後台設定裡的代號：「主分頁.下層分頁」，例如 items.data、toolbox.loadout。
 *  順序跟主分頁存在同一個 tab_order 清單、開放狀態存在同一個 tab_access（下層分頁只有開放／不開放）。 */
export const subKey = (tab, sub) => `${tab}.${sub}`

/** 後台存的開放狀態 {分頁: hidden|closed}：「艦長室」自己沒設就沿用舊的倉庫／藍圖／艦隊；
 *  搬進「資料庫」「工具箱」的舊分頁設成不開放的，換成那個下層分頁不開放（例如 loadout → toolbox.loadout）；
 *  不會讓整個「資料庫」「工具箱」關掉。下層分頁沒有「預設不顯示」，舊的 hidden 當成開放。 */
export function normalizeTabAccess(access) {
  const out = {}
  const entries = Object.entries(access || {})
  for (const [k, v] of entries) if (!LEGACY_TABS[k]) out[k] = v
  for (const [k, v] of entries) {
    const legacy = LEGACY_TABS[k]
    if (!legacy) continue
    if (legacy.tab === 'my') {
      if (!('my' in out)) out.my = v
    } else if (v === 'closed') {
      const key = subKey(legacy.tab, legacy.sub)
      if (!(key in out)) out[key] = v
    }
  }
  return out
}

/** 某個主分頁的下層分頁，照後台排的順序（tab_order 裡的「主分頁.下層分頁」；沒列到的照程式順序接在後面） */
export function orderSubTabs(tab, order) {
  const subs = tab?.subTabs || []
  const prefix = `${tab?.key}.`
  const rank = new Map((order || []).filter(k => typeof k === 'string' && k.startsWith(prefix))
    .map((k, i) => [k.slice(prefix.length), i]))
  return subs
    .map((s, i) => ({ s, i }))
    .sort((a, b) => (rank.get(a.s.key) ?? 1000 + a.i) - (rank.get(b.s.key) ?? 1000 + b.i))
    .map(x => x.s)
}

/** 玩家勾掉不顯示的分頁：舊的倉庫、藍圖、艦隊三個都勾掉才藏「艦長室」，舊的工具分頁全部勾掉才藏「工具箱」；
 *  任務不影響「資料庫」 */
export function normalizeHiddenTabs(keys) {
  const list = (keys || []).filter(k => typeof k === 'string')
  const out = list.filter(k => !LEGACY_TABS[k])
  for (const tab of MERGED_TABS) {
    const old = Object.keys(LEGACY_TABS).filter(k => LEGACY_TABS[k].tab === tab)
    if (old.every(k => list.includes(k)) && !out.includes(tab)) out.push(tab)
  }
  return out
}

/** 依後台設定的順序排列分頁；order 沒列到的照預設順序接在後面。 */
export function orderTabs(tabs, order) {
  const rank = new Map(normalizeTabKeys(order).map((k, i) => [k, i]))
  return tabs
    .map((t, i) => ({ t, i }))
    .sort((a, b) => (rank.get(a.t.key) ?? 1000 + a.i) - (rank.get(b.t.key) ?? 1000 + b.i))
    .map(x => x.t)
}

/** 後台設成「不開放」（tab_access 的 closed）：主分頁本身、某個下層分頁，或主分頁的下層分頁全部不開放。
 *  玩家頁不顯示，說明頁（views/PlayerHelpView.vue）也不寫。access 先經過 normalizeTabAccess。 */
export function isTabClosed(access, tab, sub = '') {
  if (!tab) return false
  if (access?.[tab] === 'closed') return true
  if (sub) return access?.[subKey(tab, sub)] === 'closed'
  const t = PLAYER_TABS.find(x => x.key === tab)
  return !!t?.subTabs?.length && t.subTabs.every(s => access?.[subKey(tab, s.key)] === 'closed')
}

/** 有開放的下層分頁（照後台排的順序） */
export function openSubTabs(access, tabKey, order) {
  const tab = PLAYER_TABS.find(x => x.key === tabKey)
  if (!tab || isTabClosed(access, tabKey)) return []
  return orderSubTabs(tab, order).filter(s => !isTabClosed(access, tabKey, s.key))
}
