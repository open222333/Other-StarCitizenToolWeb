import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePlayerAuthStore } from '@/stores/playerAuth'

// admin build（vite.config.js）沒設定這個變數時，維持原本的 /admin/ 前綴；
// web build（vite.config.web.js）會把它 define 成 '/'，讓路由掛在根路徑。
const ROUTER_BASE = import.meta.env.VITE_ROUTER_BASE || '/admin/'
const HOME_REDIRECT = ROUTER_BASE === '/' ? '/players' : '/users'

const router = createRouter({
  history: createWebHistory(ROUTER_BASE),
  routes: [
    { path: '/', redirect: HOME_REDIRECT },

    {
      path: '/login',
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
      // 玩家登入（跟後台 /login 分開的身分體系，見 stores/playerAuth.js）
      path: '/player-login',
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
          path: 'loot',
          name: 'loot',
          component: () => import('@/views/LootListView.vue'),
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
  if (to.meta.requiresAuth && !auth.isLoggedIn) return '/login'

  // 已登入卻訪問 guest-only 頁面 → 首頁
  if (to.meta.guest && auth.isLoggedIn) return '/'

  // 需要 admin 但不是 admin → 操作紀錄（最低權限頁）
  if (to.meta.requiresAdmin && !auth.isAdmin) return '/logs'

  // 玩家個人頁：需要玩家自己的登入狀態（跟後台 admin 登入分開）
  if (to.meta.requiresPlayerAuth) {
    const playerAuth = usePlayerAuthStore()
    if (!playerAuth.isLoggedIn) return '/player-login'
  }
})

export default router
