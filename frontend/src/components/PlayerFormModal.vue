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

defineExpose({ open })
</script>

<style scoped>
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>
