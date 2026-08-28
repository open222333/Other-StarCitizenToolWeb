<!--
  玩家自助註冊頁（公開頁面，不需要登入）。
  只收「暱稱」與「遊戲ID（Star Citizen ID，須唯一）」兩個欄位；
  其餘玩家欄位（Discord、備註等）維持由後台的 PlayerFormModal 管理。
-->
<template>
  <div class="scifi-page register-page d-flex align-items-center justify-content-center">
    <div class="card scifi-card register-card">
      <div class="card-body p-4 p-sm-5">
        <div class="text-center mb-4">
          <i class="bi bi-person-plus-fill fs-1" style="color: var(--sf-accent)"></i>
          <h4 class="fw-bold mt-2 mb-1">玩家註冊</h4>
          <p class="small mb-0" style="color: var(--sf-text-muted)">登記你的暱稱與遊戲ID，加入戰利品收藏庫</p>
        </div>

        <Transition name="alert-slide">
          <div v-if="error" class="alert alert-danger py-2 mb-3">{{ error }}</div>
        </Transition>

        <Transition name="alert-slide">
          <div v-if="success" class="alert alert-success py-2 mb-3">
            <i class="bi bi-check-circle me-1"></i>註冊成功！
          </div>
        </Transition>

        <form @submit.prevent="submit">
          <div class="mb-3">
            <label class="form-label small fw-semibold">
              暱稱 <span class="text-danger">*</span>
            </label>
            <input v-model="form.nickname" type="text" class="form-control" required
              placeholder="例如：喔噴" :disabled="success">
          </div>

          <div class="mb-3">
            <label class="form-label small fw-semibold">
              遊戲ID（Star Citizen ID） <span class="text-danger">*</span>
            </label>
            <input v-model="form.star_citizen_id" type="text" class="form-control" required
              placeholder="你的 Star Citizen 帳號 ID" :disabled="success">
            <div class="form-text">須唯一，之後拿來對應戰利品／藍圖的取得紀錄，請填正確</div>
          </div>

          <div class="mb-3">
            <label class="form-label small fw-semibold">
              密碼 <span class="text-danger">*</span>
            </label>
            <input v-model="form.password" type="password" class="form-control" required
              minlength="6" placeholder="至少 6 個字元" :disabled="success">
            <div class="form-text">之後可以用遊戲ID＋密碼登入，查看／管理自己的戰利品與藍圖</div>
          </div>

          <div class="mb-4">
            <label class="form-label small fw-semibold">
              確認密碼 <span class="text-danger">*</span>
            </label>
            <input v-model="form.password_confirm" type="password" class="form-control" required
              minlength="6" placeholder="再輸入一次密碼" :disabled="success">
          </div>

          <button type="submit" class="btn btn-scifi w-100" :disabled="submitting || success">
            <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
            {{ success ? '已完成註冊' : '註冊' }}
          </button>
        </form>

        <div class="text-center mt-3">
          <RouterLink to="/player-login" class="small">已經有帳號？前往登入</RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { registerPlayer } from '@/api'

const form = reactive({ nickname: '', star_citizen_id: '', password: '', password_confirm: '' })
const submitting = ref(false)
const success     = ref(false)
const error       = ref('')

async function submit() {
  error.value = ''
  const nickname = form.nickname.trim()
  const scid     = form.star_citizen_id.trim()
  const password = form.password
  if (!nickname) { error.value = '暱稱不得為空'; return }
  if (!scid)     { error.value = '遊戲ID 不得為空'; return }
  if (password.length < 6) { error.value = '密碼至少需要 6 個字元'; return }
  if (password !== form.password_confirm) { error.value = '兩次輸入的密碼不一致'; return }

  submitting.value = true
  try {
    const res = await registerPlayer({ nickname, star_citizen_id: scid, password })
    if (!res) { error.value = '網路錯誤，請稍後再試'; return }
    const data = await res.json().catch(() => null)
    if (res.ok && data?.success !== false) {
      success.value = true
    } else if (res.status === 409) {
      // 唯一性檢查：後端偵測到重複的 star_citizen_id
      error.value = data?.message || '這個遊戲ID已經被註冊過了'
    } else {
      error.value = data?.message || '註冊失敗，請稍後再試'
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
