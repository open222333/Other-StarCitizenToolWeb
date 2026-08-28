<!--
  玩家登入頁（公開頁面）。跟後台管理員登入（LoginView.vue）分開，
  用遊戲ID（Star Citizen ID）＋密碼登入，取得玩家專用 JWT（stores/playerAuth.js）。
-->
<template>
  <div class="scifi-page register-page d-flex align-items-center justify-content-center">
    <div class="card scifi-card register-card">
      <div class="card-body p-4 p-sm-5">
        <div class="text-center mb-4">
          <i class="bi bi-rocket-takeoff fs-1" style="color: var(--sf-accent)"></i>
          <h4 class="fw-bold mt-2 mb-1">玩家登入</h4>
          <p class="small mb-0" style="color: var(--sf-text-muted)">查看／管理你自己的戰利品與藍圖</p>
        </div>

        <Transition name="alert-slide">
          <div v-if="error" class="alert alert-danger py-2 mb-3">{{ error }}</div>
        </Transition>

        <form @submit.prevent="submit">
          <div class="mb-3">
            <label class="form-label small fw-semibold">遊戲ID（Star Citizen ID）</label>
            <input v-model="form.star_citizen_id" type="text" class="form-control" required
              placeholder="你的 Star Citizen 帳號 ID" :disabled="submitting">
          </div>

          <div class="mb-4">
            <label class="form-label small fw-semibold">密碼</label>
            <input v-model="form.password" type="password" class="form-control" required
              placeholder="密碼" :disabled="submitting">
          </div>

          <button type="submit" class="btn btn-scifi w-100" :disabled="submitting">
            <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
            登入
          </button>
        </form>

        <div class="text-center mt-3">
          <span class="small text-muted">還沒有帳號？</span>
          <RouterLink to="/register" class="small">前往註冊</RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { loginPlayer } from '@/api'
import { usePlayerAuthStore } from '@/stores/playerAuth'

const router     = useRouter()
const playerAuth = usePlayerAuthStore()

const form = reactive({ star_citizen_id: '', password: '' })
const submitting = ref(false)
const error       = ref('')

async function submit() {
  error.value = ''
  submitting.value = true
  try {
    const res = await loginPlayer({
      star_citizen_id: form.star_citizen_id.trim(),
      password: form.password,
    })
    if (!res) { error.value = '網路錯誤，請稍後再試'; return }
    const data = await res.json().catch(() => null)
    if (res.ok && data?.success) {
      playerAuth.setAuth(data)
      router.push('/me')
    } else {
      error.value = data?.message || '登入失敗，請確認遊戲ID與密碼'
    }
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.register-card { max-width: 420px; width: 100%; border-radius: .75rem; }

.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>
