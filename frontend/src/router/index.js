import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory('/admin/'),
  routes: [
    { path: '/', redirect: '/users' },

    {
      path: '/login',
      component: () => import('@/views/LoginView.vue'),
      meta: { guest: true },
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
})

export default router
