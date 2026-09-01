<template>
  <div class="scifi-page login-bg d-flex align-items-center justify-content-center vh-100">
    <div class="card scifi-card login-card">
      <div class="card-body p-4">

        <div class="text-center mb-4">
          <i :class="`bi ${appIcon} fs-1`" style="color: var(--sf-accent)"></i>
          <h5 class="mt-2 fw-bold">{{ appTitle }}</h5>
        </div>

        <Transition name="alert-slide">
          <div v-if="error" class="alert alert-danger py-2 mb-3">{{ error }}</div>
        </Transition>

        <form @submit.prevent="handleLogin">
          <div class="mb-3">
            <label class="form-label small fw-semibold">帳號</label>
            <input v-model="form.username" type="text" class="form-control"
              autocomplete="username" required autofocus>
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold">密碼</label>
            <input v-model="form.password" type="password" class="form-control"
              autocomplete="current-password" required>
          </div>
          <div class="mb-4 form-check">
            <input v-model="form.remember_me" class="form-check-input" type="checkbox" id="cb-remember">
            <label class="form-check-label small" for="cb-remember">記住我（30 天）</label>
          </div>
          <button type="submit" class="btn btn-scifi w-100" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
            {{ loading ? '登入中...' : '登入' }}
          </button>
        </form>

        <!-- 只有「星際公民工具」這個 build 開放玩家自助註冊，管理後台不顯示 -->
        <div v-if="showRegisterLink" class="text-center mt-3">
          <span class="small text-muted">還沒有帳號？</span>
          <RouterLink to="/register" class="small">前往註冊</RouterLink>
        </div>

        <!-- 這裡是「後台管理員」登入，玩家常常點錯頁面跑來這裡輸入遊戲ID／密碼
             結果收到帳號或密碼錯誤——加一個明顯的指引導去真正的玩家登入頁。 -->
        <div v-if="showRegisterLink" class="text-center mt-2">
          <span class="small text-muted">你是玩家，不是公會管理員？</span>
          <RouterLink :to="PLAYER_LOGIN_PATH" class="small">前往玩家登入</RouterLink>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { PLAYER_LOGIN_PATH } from '@/router'

const router  = useRouter()
const auth    = useAuthStore()
const loading = ref(false)
const error   = ref('')
const form    = reactive({ username: '', password: '', remember_me: false })

// 兩套 build 的站名不同，見 DashboardLayout.vue 同樣的判斷
const appTitle = import.meta.env.VITE_APP_TITLE || '管理後台'
const appIcon  = appTitle === '管理後台' ? 'bi-shield-lock' : 'bi-rocket-takeoff'
const showRegisterLink = appTitle !== '管理後台'

async function handleLogin() {
  loading.value = true
  error.value   = ''
  try {
    const res  = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    })
    const data = await res.json()
    if (data.success) {
      auth.setAuth({ ...data, username: form.username })
      router.push('/')
    } else {
      error.value = data.message || '帳號或密碼錯誤'
    }
  } catch {
    error.value = '連線失敗，請確認服務是否啟動'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-card {
  width: min(360px, 92vw);
  border-radius: 12px;
}
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-6px); }
</style>
