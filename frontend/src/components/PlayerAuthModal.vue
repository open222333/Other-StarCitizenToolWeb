<!--
  玩家登入／註冊視窗（玩家頁右上角的「登入」「註冊」按鈕打開；舊網址 /player/login、/player/register
  會導到 /player/me?login=1／?register=1 打開這個視窗）。跟後台管理員登入（LoginView.vue）分開的身分體系，
  用遊戲ID（Star Citizen ID）＋密碼（stores/playerAuth.js）。
  v-model:open、v-model:mode（login／register）。登入成功發 done（上層整頁重新載入，會員資料一次讀齊）；
  註冊成功切到登入、遊戲ID 帶好。
-->
<template>
  <Teleport to="body">
    <div class="scifi-page pam-host">
      <SfModal id="player-auth" :open="open" :title="mode === 'login' ? '玩家登入' : '玩家註冊'"
        :icon="mode === 'login' ? 'bi bi-box-arrow-in-right' : 'bi bi-person-plus'" width="440px"
        @update:open="v => emit('update:open', v)">
        <div class="btn-group w-100 mb-3" role="tablist" aria-label="登入或註冊">
          <button type="button" class="btn btn-subtab" :class="{ active: mode === 'login' }" role="tab"
            :aria-selected="mode === 'login'" @click="setMode('login')"><i class="bi bi-box-arrow-in-right me-1"></i>登入</button>
          <button type="button" class="btn btn-subtab" :class="{ active: mode === 'register' }" role="tab"
            :aria-selected="mode === 'register'" @click="setMode('register')"><i class="bi bi-person-plus me-1"></i>註冊</button>
        </div>

        <div v-if="notice" class="alert alert-success py-2 mb-3"><i class="bi bi-check-circle me-1"></i>{{ notice }}</div>
        <div v-if="error" class="alert alert-danger py-2 mb-3" role="alert">{{ error }}</div>

        <!-- 登入 -->
        <form v-if="mode === 'login'" @submit.prevent="login">
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="pam-scid">遊戲ID（Star Citizen ID）</label>
            <input id="pam-scid" v-model.trim="loginForm.star_citizen_id" type="text" class="form-control" required
              autocomplete="username" placeholder="你的 Star Citizen 帳號 ID" :disabled="submitting">
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="pam-pw">密碼</label>
            <input id="pam-pw" v-model="loginForm.password" type="password" class="form-control" required
              autocomplete="current-password" :disabled="submitting">
          </div>
          <div class="mb-3 form-check">
            <input id="pam-remember" v-model="loginForm.remember_me" class="form-check-input" type="checkbox">
            <label class="form-check-label" for="pam-remember">記住我（30 天）</label>
          </div>
          <button type="submit" class="btn btn-scifi w-100" :disabled="submitting">
            <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>登入</button>
        </form>

        <!-- 註冊 -->
        <form v-else @submit.prevent="register">
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="pam-nick">暱稱 <span class="text-danger">*</span></label>
            <input id="pam-nick" v-model.trim="regForm.nickname" type="text" class="form-control" required
              placeholder="例如：喔噴" :disabled="submitting">
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="pam-rscid">遊戲ID（Star Citizen ID） <span class="text-danger">*</span></label>
            <input id="pam-rscid" v-model.trim="regForm.star_citizen_id" type="text" class="form-control" required
              autocomplete="username" placeholder="你的 Star Citizen 帳號 ID" :disabled="submitting">
            <div class="form-text">要唯一，之後用來對應你的倉庫、藍圖，請填正確</div>
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="pam-rpw">密碼 <span class="text-danger">*</span></label>
            <input id="pam-rpw" v-model="regForm.password" type="password" class="form-control" required minlength="6"
              autocomplete="new-password" placeholder="至少 6 個字元" :disabled="submitting">
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="pam-rpw2">確認密碼 <span class="text-danger">*</span></label>
            <input id="pam-rpw2" v-model="regForm.password_confirm" type="password" class="form-control" required minlength="6"
              autocomplete="new-password" :disabled="submitting">
          </div>
          <button type="submit" class="btn btn-scifi w-100" :disabled="submitting">
            <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>註冊</button>
        </form>
      </SfModal>
    </div>
  </Teleport>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import SfModal from '@/components/SfModal.vue'
import { loginPlayer, registerPlayer } from '@/api'
import { usePlayerAuthStore } from '@/stores/playerAuth'

const props = defineProps({
  open: { type: Boolean, default: false },
  mode: { type: String, default: 'login' },
})
const emit = defineEmits(['update:open', 'update:mode', 'done'])
const playerAuth = usePlayerAuthStore()

const loginForm = reactive({ star_citizen_id: '', password: '', remember_me: true })   // 預設記住 30 天
const regForm = reactive({ nickname: '', star_citizen_id: '', password: '', password_confirm: '' })
const submitting = ref(false)
const error = ref('')
const notice = ref('')
function setMode(m) {
  error.value = ''
  emit('update:mode', m)
}
watch(() => props.open, (v) => { if (v) { error.value = ''; notice.value = '' } })

async function login() {
  error.value = ''
  submitting.value = true
  try {
    const res = await loginPlayer({ ...loginForm })
    if (!res) { error.value = '網路錯誤，請稍後再試'; return }
    const data = await res.json().catch(() => null)
    if (res.ok && data?.success) {
      playerAuth.setAuth(data)
      emit('done')
    } else {
      error.value = data?.message || '登入失敗，請確認遊戲ID與密碼'
    }
  } finally {
    submitting.value = false
  }
}

async function register() {
  error.value = ''
  const { nickname, star_citizen_id: scid, password, password_confirm: confirm } = regForm
  if (!nickname) { error.value = '暱稱不得為空'; return }
  if (!scid) { error.value = '遊戲ID 不得為空'; return }
  if (password.length < 6) { error.value = '密碼至少需要 6 個字元'; return }
  if (password !== confirm) { error.value = '兩次輸入的密碼不一致'; return }
  submitting.value = true
  try {
    const res = await registerPlayer({ nickname, star_citizen_id: scid, password })
    if (!res) { error.value = '網路錯誤，請稍後再試'; return }
    const data = await res.json().catch(() => null)
    if (res.ok && data?.success !== false) {
      // 註冊完直接切到登入，遊戲ID 帶好
      loginForm.star_citizen_id = scid
      loginForm.password = ''
      Object.assign(regForm, { nickname: '', star_citizen_id: '', password: '', password_confirm: '' })
      emit('update:mode', 'login')
      notice.value = '註冊成功，請輸入密碼登入。'
    } else {
      error.value = data?.message || (res.status === 409 ? '這個遊戲ID已經被註冊過了' : '註冊失敗，請稍後再試')
    }
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.pam-host { display: contents; }
</style>
