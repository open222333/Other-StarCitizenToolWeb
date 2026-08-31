<!--
  玩家新增／編輯表單（規格書第 4.1 節）。結構比照 UserModal.vue。
  用法（父元件）：
    <PlayerFormModal ref="playerModalRef" @saved="onPlayerSaved" />
    playerModalRef.open()        // 新增
    playerModalRef.open(player)  // 編輯
-->
<template>
  <div class="modal fade" ref="modalEl" tabindex="-1">
    <div class="modal-dialog">
      <div class="modal-content border-0 shadow">

        <div class="modal-header">
          <h5 class="modal-title">{{ editId ? '編輯玩家' : '新增玩家' }}</h5>
          <button type="button" class="btn-close" @click="hide"></button>
        </div>

        <div class="modal-body">
          <Transition name="alert-slide">
            <div v-if="error" class="alert alert-danger py-2 mb-3">{{ error }}</div>
          </Transition>

          <div class="mb-3">
            <label class="form-label small fw-semibold">
              玩家名稱 <span class="text-danger">*</span>
            </label>
            <input v-model="form.player_name" type="text" class="form-control" required>
          </div>

          <div class="mb-3">
            <label class="form-label small fw-semibold">
              Star Citizen ID（遊戲ID） <span class="text-danger">*</span>
            </label>
            <input v-model="form.star_citizen_id" type="text" class="form-control" required>
            <div class="form-text">主要識別資料，須唯一，與 Discord 名稱／ID 分開儲存</div>
          </div>

          <div class="mb-3">
            <label class="form-label small fw-semibold">暱稱</label>
            <input v-model="form.nickname" type="text" class="form-control">
          </div>

          <div class="row">
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">Discord 名稱</label>
              <input v-model="form.discord_name" type="text" class="form-control" placeholder="@player">
            </div>
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">Discord ID</label>
              <input v-model="form.discord_id" type="text" class="form-control">
            </div>
          </div>

          <div class="mb-1">
            <label class="form-label small fw-semibold">備註</label>
            <textarea v-model="form.notes" class="form-control" rows="2"></textarea>
          </div>

          <template v-if="editId">
            <hr>
            <label class="form-label small fw-semibold">重設密碼</label>
            <div class="input-group">
              <input v-model="newPassword" type="password" class="form-control" minlength="6"
                autocomplete="new-password" placeholder="留空表示不變更，至少 6 個字元">
              <button type="button" class="btn btn-outline-secondary"
                :disabled="resettingPassword || newPassword.length < 6" @click="resetPassword">
                <span v-if="resettingPassword" class="spinner-border spinner-border-sm me-1"></span>
                更新密碼
              </button>
            </div>
            <div v-if="passwordMsg" :class="`form-text ${passwordOk ? 'text-success' : 'text-danger'}`">
              {{ passwordMsg }}
            </div>
            <div class="form-text">
              玩家登入「個人資料」頁面用的密碼。忘記密碼時可以在這裡直接設定新的，不需要知道原密碼。
            </div>
          </template>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="hide">取消</button>
          <button type="button" class="btn btn-primary" :disabled="saving" @click="save">
            <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
            儲存
          </button>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Modal } from 'bootstrap'
import { playerApi } from '@/api'

const emit = defineEmits(['saved'])

const modalEl = ref(null)
let   bsModal = null

const editId = ref('')
const saving = ref(false)
const error  = ref('')
const form = reactive({
  player_name: '', star_citizen_id: '', nickname: '', discord_name: '', discord_id: '', notes: '',
})

// ── 重設密碼：獨立於上面的 save()，打的是專門的 API（見 app/player/view.py
//    set_player_password()），不跟一般欄位共用同一個提交按鈕 —— 密碼失敗
//    不該連帶讓暱稱／Discord 這些已經改好的欄位也存不進去。
const newPassword       = ref('')
const resettingPassword = ref(false)
const passwordMsg       = ref('')
const passwordOk        = ref(false)

onMounted(() => { bsModal = new Modal(modalEl.value) })

function open(player = null) {
  editId.value          = player?._id            || ''
  error.value            = ''
  form.player_name       = player?.player_name    || ''
  form.star_citizen_id   = player?.star_citizen_id || ''
  form.nickname          = player?.nickname        || ''
  form.discord_name      = player?.discord_name    || ''
  form.discord_id        = player?.discord_id      || ''
  form.notes             = player?.notes           || ''
  newPassword.value      = ''
  passwordMsg.value      = ''
  bsModal.show()
}

function hide() { bsModal.hide() }

async function save() {
  error.value = ''
  if (!form.player_name.trim())     { error.value = '玩家名稱不得為空'; return }
  if (!form.star_citizen_id.trim()) { error.value = 'Star Citizen ID 不得為空'; return }

  saving.value = true
  try {
    const payload = { ...form }
    const res = editId.value
      ? await playerApi.update(editId.value, payload)
      : await playerApi.create(payload)
    if (!res) return
    const data = await res.json()
    if (data.success) { hide(); emit('saved') }
    else { error.value = data.message || '儲存失敗' }
  } finally {
    saving.value = false
  }
}

async function resetPassword() {
  if (newPassword.value.length < 6) {
    passwordOk.value  = false
    passwordMsg.value = '密碼至少需要 6 個字元'
    return
  }
  resettingPassword.value = true
  passwordMsg.value = ''
  try {
    const res = await playerApi.setPassword(editId.value, newPassword.value)
    if (!res) { passwordOk.value = false; passwordMsg.value = '網路錯誤，請稍後再試'; return }
    const data = await res.json().catch(() => null)
    if (data?.success) {
      passwordOk.value  = true
      passwordMsg.value = '密碼已更新'
      newPassword.value = ''
    } else {
      passwordOk.value  = false
      passwordMsg.value = data?.message || '更新失敗'
    }
  } finally {
    resettingPassword.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>
