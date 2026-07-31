<template>
  <div class="login-bg d-flex align-items-center justify-content-center vh-100">
    <div class="card shadow-lg login-card">
      <div class="card-body p-4">

        <div class="text-center mb-4">
          <i class="bi bi-shield-lock fs-1 text-primary"></i>
          <h5 class="mt-2 fw-bold">後台管理</h5>
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
          <button type="submit" class="btn btn-primary w-100" :disabled="loading">
            <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
            {{ loading ? '登入中...' : '登入' }}
          </button>
        </form>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router  = useRouter()
const auth    = useAuthStore()
const loading = ref(false)
const error   = ref('')
const form    = reactive({ username: '', password: '', remember_me: false })

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
.login-bg {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
}
.login-card {
  width: min(360px, 92vw);
  border: none;
  border-radius: 12px;
}
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-6px); }
</style>
