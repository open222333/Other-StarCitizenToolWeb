// 玩家頁的主分頁定義（MyPlayerView.vue 的分頁列、後台「系統設定」的分頁排序共用）。
// 排列順序：後台設定的順序（app_settings.player_tab_order，/player/me 帶 tab_order）優先，
// 沒列到的分頁（例如之後新增的）照這裡的順序接在後面。
export const PLAYER_TABS = [
  {
    // 原本的「物品庫存／庫存紀錄」合併成一頁，庫存紀錄改成按鈕展開（比照艦隊）
    key: 'warehouse', label: '倉庫',   icon: 'bi bi-box-seam',
  },
  {
    // 原本的「我的藍圖／藍圖資料／批量登記」合併成一頁，後兩個再合併成按鈕展開的「登記藍圖資料」（比照艦隊）
    key: 'blueprints', label: '藍圖',  icon: 'bi bi-diagram-3',
  },
  // 任務資料庫（唯讀），藍圖欄標出自己已登記幾張
  { key: 'missions', label: '任務', icon: 'bi bi-flag' },
  {
    // 原本的「我的艦隊／批量登記」兩個下層分頁合併成一頁；批量登記後來併進按鈕展開的「登記船艦資料」
    key: 'fleet', label: '艦隊',  icon: 'bi bi-rocket-takeoff',
  },
  { key: 'mining',     label: '礦物',   icon: 'bi bi-gem' },
  // 量子航線規劃（多站點、貨運取送順序；見 components/RoutePlanner.vue）
  { key: 'route',      label: '航線',   icon: 'bi bi-signpost-split' },
  {
    // 原本的三個下層分頁合併成一頁，改成上方按鈕點開（SEARCH_SECTIONS）。
    // 原名「查詢」；商品購買地點搬到倉庫後只剩查別人持有的東西，改名「查詢持有資訊」
    key: 'search',    label: '查詢持有資訊',   icon: 'bi bi-search', short: '查詢',
  },
  { key: 'gamelog',   label: 'LOG 解析', icon: 'bi bi-journal-code' },
  { key: 'payout',    label: '酬勞分配', icon: 'bi bi-cash-coin' },
  { key: 'chatcode',  label: '中文轉碼', icon: 'bi bi-translate' },
  { key: 'tools',     label: '工具網站', icon: 'bi bi-link-45deg' },
  { key: 'profile',   label: '個人資料', icon: 'bi bi-person-gear' },
]

/** 依後台設定的順序排列分頁；order 沒列到的照預設順序接在後面。 */
export function orderTabs(tabs, order) {
  const rank = new Map((order || []).map((k, i) => [k, i]))
  return tabs
    .map((t, i) => ({ t, i }))
    .sort((a, b) => (rank.get(a.t.key) ?? 1000 + a.i) - (rank.get(b.t.key) ?? 1000 + b.i))
    .map(x => x.t)
}
