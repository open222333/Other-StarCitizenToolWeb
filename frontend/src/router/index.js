import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePlayerAuthStore } from '@/stores/playerAuth'

// admin build（vite.config.js）沒設定這個變數時，維持原本的 /admin/ 前綴；
// web build（vite.config.web.js）會把它 define 成 '/'，讓路由掛在根路徑。
const ROUTER_BASE = import.meta.env.VITE_ROUTER_BASE || '/admin/'

// 這個 build 是不是玩家站（web build，掛在網域根路徑）
const PLAYER_BUILD = ROUTER_BASE === '/'

// 後台登入成功後要去哪。玩家站上也有完整的後台頁面（同一份 SPA），
// 所以兩套 build 都要有一個「後台首頁」，不能用 '/'（見下面 HOME_REDIRECT）。
export const ADMIN_HOME = PLAYER_BUILD ? '/players' : '/users'

// 根路徑導向。
//
// ⚠️ 玩家站的根路徑導到 /me（玩家自己的頁面），不是後台首頁 ——
// 原本兩套 build 都導到後台頁面（/players），而那個路由掛在 requiresAuth 底下，
// 所以任何人打開 https://<玩家網域>/ 都會被 guard 丟到**後台登入頁**。
// 玩家站的訪客十個有九個是玩家，讓他們第一眼看到管理員登入畫面是錯的
// （這也是 README 先前標註的待修 UX 問題）。
// 現在：未登入的玩家 → /me → requiresPlayerAuth → 玩家登入頁；
//       管理員請直接走 /admin/login（兩個登入頁互相有連結）。
const HOME_REDIRECT = PLAYER_BUILD ? '/me' : '/users'

// 後台登入頁的路徑：createWebHistory 的 base 會直接接在路徑前面，
// admin build 的 base 已經是 /admin/，路徑維持 '/login' 最終網址就是
// /admin/login，不用再疊一層；web build 的 base 是 '/'，所以這裡改成
// '/admin/login'，讓兩套 build 最終看到的網址一致，也跟玩家登入頁
// 在網址上就有明顯區隔，不會有人以為 /login 是玩家登入。
export const ADMIN_LOGIN_PATH = ROUTER_BASE === '/' ? '/admin/login' : '/login'

// 玩家登入頁的路徑：web build 上面 /login 已經讓給後台改用 /admin/login
// 空出來了，玩家平常用的這個網域就把玩家登入放回最直覺的 /login；
// admin build 的 /login 還是後台在用，玩家登入在那個網域本來就用不到，
// 維持原本的 /player-login 就好，避免跟後台登入路徑撞在一起。
export const PLAYER_LOGIN_PATH = ROUTER_BASE === '/' ? '/login' : '/player-login'

const router = createRouter({
  history: createWebHistory(ROUTER_BASE),
  routes: [
    { path: '/', redirect: HOME_REDIRECT },

    {
      path: ADMIN_LOGIN_PATH,
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true },
    },

    {
      // 公開自助註冊頁，不需要登入，也不因為已登入而被導開
      path: '/register',
      name: 'register',
      component: () => import('@/views/RegisterView.vue'),
    },

    {
      // 玩家登入（跟後台登入分開的身分體系，見 stores/playerAuth.js）
      path: PLAYER_LOGIN_PATH,
      name: 'player-login',
      component: () => import('@/views/PlayerLoginView.vue'),
    },

    {
      // 玩家個人頁，需要玩家自己登入（不是後台 admin/operator/viewer 登入）
      path: '/me',
      name: 'my-player',
      component: () => import('@/views/MyPlayerView.vue'),
      meta: { requiresPlayerAuth: true },
    },

    {
      // 需登入的頁面共用 DashboardLayout
      path: '/',
      component: () => import('@/layouts/DashboardLayout.vue'),
      meta: { requiresAuth: true },
      children: [
        {
          path: 'users',
          name: 'users',
          component: () => import('@/views/UsersView.vue'),
          meta: { requiresAdmin: true },
        },
        {
          path: 'logs',
          name: 'logs',
          component: () => import('@/views/LogsView.vue'),
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/views/SettingsView.vue'),
        },

        // ── 玩家／藍圖／戰利品管理（規格書第 4、5、6 節）───────────
        {
          path: 'players',
          name: 'players',
          component: () => import('@/views/PlayerListView.vue'),
        },
        {
          path: 'players/:id',
          name: 'player-detail',
          component: () => import('@/views/PlayerDetailView.vue'),
        },
        {
          path: 'blueprints',
          name: 'blueprints',
          component: () => import('@/views/BlueprintListView.vue'),
        },
        {
          // 藍圖材料試算（同一個元件也掛在玩家頁的「試算」分頁）
          path: 'blueprint-calc',
          name: 'blueprint-calc',
          component: () => import('@/views/BlueprintCalcView.vue'),
        },
        {
          path: 'inventory',
          name: 'inventory',
          component: () => import('@/views/InventoryListView.vue'),
        },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  // 尚未登入 → 導向登入頁
  if (to.meta.requiresAuth && !auth.isLoggedIn) return ADMIN_LOGIN_PATH

  // 已登入卻訪問 guest-only 頁面（後台登入頁）→ 後台首頁。
  // 不能用 '/'：玩家站的 '/' 現在導到 /me，會把已登入的管理員丟到玩家登入頁。
  if (to.meta.guest && auth.isLoggedIn) return ADMIN_HOME

  // 需要 admin 但不是 admin → 操作紀錄（最低權限頁）
  if (to.meta.requiresAdmin && !auth.isAdmin) return '/logs'

  // 玩家個人頁：需要玩家自己的登入狀態（跟後台 admin 登入分開）
  if (to.meta.requiresPlayerAuth) {
    const playerAuth = usePlayerAuthStore()
    if (!playerAuth.isLoggedIn) return PLAYER_LOGIN_PATH
  }
})

export default router
