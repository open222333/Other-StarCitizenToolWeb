<template>
  <div class="layout-wrapper">

    <!-- ── Top Navbar ── -->
    <nav :class="['navbar', theme.isLight ? 'navbar-light' : 'navbar-dark', 'px-4', 'top-navbar']">
      <div class="d-flex align-items-center gap-2">
        <button class="btn btn-sm btn-outline-secondary hamburger-btn"
          @click="sidebarOpen = !sidebarOpen" aria-label="選單">
          <i class="bi bi-list fs-5"></i>
        </button>
        <span class="navbar-brand fw-bold mb-0" style="color: var(--nb-brand)">
          <i class="bi bi-shield-lock me-2"></i>後台管理
        </span>
      </div>
      <div class="d-flex align-items-center gap-2">
        <i class="bi bi-person-circle d-none d-sm-inline" style="color: var(--nb-text)"></i>
        <span class="small" style="color: var(--nb-text)">
          {{ auth.username }}
          <span :class="`badge bg-${roleColor} ms-1`">{{ roleLabel }}</span>
        </span>
        <button class="btn btn-outline-danger btn-sm ms-2" @click="logout">
          <i class="bi bi-box-arrow-right me-1"></i>
          <span class="d-none d-sm-inline">登出</span>
        </button>
      </div>
    </nav>

    <!-- ── Sidebar backdrop (mobile) ── -->
    <Transition name="fade">
      <div v-if="sidebarOpen" class="sidebar-backdrop" @click="sidebarOpen = false"></div>
    </Transition>

    <div class="main-body">
      <!-- ── Sidebar ── -->
      <aside class="sidebar" :class="{ open: sidebarOpen }">
        <div class="d-flex align-items-center justify-content-between px-3 pt-3 pb-1 d-md-none">
          <span class="small fw-semibold" style="color: var(--sb-section)">選單</span>
          <button class="btn btn-sm btn-outline-secondary" @click="sidebarOpen = false">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>

        <div class="nav-section">管理</div>
        <RouterLink v-if="auth.isAdmin"
          class="nav-link" to="/users" @click="sidebarOpen = false">
          <i class="bi bi-people"></i>使用者管理
        </RouterLink>
        <RouterLink class="nav-link" to="/logs" @click="sidebarOpen = false">
          <i class="bi bi-journal-text"></i>操作紀錄
        </RouterLink>

        <div class="nav-section">系統</div>
        <RouterLink class="nav-link" to="/settings" @click="sidebarOpen = false">
          <i class="bi bi-palette"></i>系統設定
        </RouterLink>

        <div class="sidebar-footer">
          <i class="bi bi-circle-fill text-success me-1" style="font-size:.5rem"></i>
          服務運行中
        </div>
      </aside>

      <!-- ── Main content ── -->
      <div class="content-area">
        <RouterView />
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore } from '@/stores/theme'

const router      = useRouter()
const auth        = useAuthStore()
const theme       = useThemeStore()
const sidebarOpen = ref(false)


const ROLE_LABELS = { admin: '管理員', operator: '操作員', viewer: '檢視者' }
const ROLE_COLORS = { admin: 'danger',  operator: 'warning',  viewer: 'secondary' }
const roleLabel = computed(() => ROLE_LABELS[auth.role] || auth.role)
const roleColor = computed(() => ROLE_COLORS[auth.role] || 'secondary')

function logout() {
  auth.clearAuth()
  router.push('/login')
}
</script>

<style scoped>
.layout-wrapper {
  display: flex; flex-direction: column;
  height: 100vh; background-color: var(--content-bg, #f5f6fa);
}
.top-navbar {
  flex-shrink: 0;
  background: var(--nb-bg, #212529) !important;
  box-shadow: 0 2px 8px rgba(0,0,0,.2);
}
.main-body { display: flex; flex: 1; overflow: hidden; }

/* ── Sidebar ── */
.sidebar {
  width: 220px; flex-shrink: 0;
  background: var(--sb-bg, #1e2130);
  display: flex; flex-direction: column; overflow-y: auto;
  transition: background .25s;
}
.sidebar .nav-link {
  color: var(--sb-link, #9aa0b4);
  padding: .65rem 1.25rem;
  font-size: .9rem; display: flex; align-items: center; gap: .55rem;
  text-decoration: none; transition: background .15s, color .15s;
}
.sidebar .nav-link:hover {
  background: var(--sb-hover-bg, rgba(255,255,255,.06));
  color: var(--sb-active-color, #6384ff);
}
.sidebar .nav-link.router-link-active {
  background: var(--sb-active-bg, rgba(99,132,255,.15));
  color: var(--sb-active-color, #6384ff);
  font-weight: 600;
}
.sidebar .nav-section {
  font-size: .7rem; text-transform: uppercase; letter-spacing: .08em;
  color: var(--sb-section, #555e7a);
  padding: 1.1rem 1.25rem .4rem;
}
.sidebar-footer {
  margin-top: auto; padding: 1rem 1.25rem;
  border-top: 1px solid var(--sb-footer-bd, rgba(255,255,255,.07));
  font-size: .85rem; color: var(--sb-link, #9aa0b4);
}

.content-area {
  flex: 1; overflow-y: auto; padding: 1.75rem;
  background: var(--content-bg, #f5f6fa);
}

/* ── Mobile ── */
.hamburger-btn  { display: none; }
.sidebar-backdrop {
  position: fixed; inset: 0;
  background: rgba(0,0,0,.5); z-index: 1040;
}
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to       { opacity: 0; }

@media (max-width: 767px) {
  .hamburger-btn { display: flex; }
  .sidebar {
    position: fixed; top: 0; left: 0;
    width: 260px; height: 100vh; z-index: 1050;
    transform: translateX(-100%); transition: transform .25s ease;
  }
  .sidebar.open  { transform: translateX(0); }
  .content-area  { padding: 1rem .75rem; }
}
</style>
