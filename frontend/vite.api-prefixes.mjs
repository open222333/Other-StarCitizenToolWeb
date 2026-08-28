// Flask 後端所有 API 的 URL 前綴 —— 單一事實來源。
//
// 這份清單有三個消費者，過去各自維護一份、然後漂移：
//   1. vite.config.js       的 dev proxy（後台 /admin/ build）
//   2. vite.config.web.js   的 dev proxy（公開站 build）
//   3. conf/nginx-web/default.conf 的 location 正則（公開站的生產環境代理）
//
// 漂移的後果是無聲的：漏掉的前綴會落到 SPA 的 index.html fallback，
// 前端拿到一份 HTML 卻以為是 JSON，畫面顯示「沒有資料」而不是錯誤。
// 這個 bug 已經發生兩次（先是 /item 與 /inventory 漏在 nginx，
// 後來又漏在 vite.config.js），所以把清單集中在這裡。
//
// ⚠️ 新增 Flask blueprint 時，除了這裡也要同步更新 conf/nginx-web/default.conf。
//    tests/test_permissions.py 的 test_no_admin_route_is_left_unguarded
//    會列出所有已註冊的路由，可以拿來核對。

export const API_PREFIXES = [
  '/auth',
  '/user',
  '/log',
  '/device',
  '/player',
  '/blueprint',
  '/item',
  '/inventory',
]

/** 產生 Vite dev server 的 proxy 設定物件。 */
export function makeProxy(target = 'http://localhost:5000') {
  return Object.fromEntries(
    API_PREFIXES.map(prefix => [prefix, { target, changeOrigin: true }]),
  )
}
