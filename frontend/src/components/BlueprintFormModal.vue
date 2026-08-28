<!--
  藍圖新增／編輯表單（規格書第 5.1 節）。
  用法：<BlueprintFormModal ref="bpModalRef" :players="players" @saved="onSaved" />
-->
<template>
  <div class="modal fade" ref="modalEl" tabindex="-1">
    <div class="modal-dialog">
      <div class="modal-content border-0 shadow">

        <div class="modal-header">
          <h5 class="modal-title">{{ editId ? '編輯藍圖' : '新增藍圖' }}</h5>
          <button type="button" class="btn-close" @click="hide"></button>
        </div>

        <div class="modal-body">
          <Transition name="alert-slide">
            <div v-if="error" class="alert alert-danger py-2 mb-3">{{ error }}</div>
          </Transition>

          <div class="mb-3">
            <label class="form-label small fw-semibold">Blueprint 名稱 <span class="text-danger">*</span></label>
            <input v-model="form.name" type="text" class="form-control" required>
          </div>

          <div class="row">
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">取得方式</label>
              <select v-model="form.acquisition_method" class="form-select">
                <option value="">— 未知 —</option>
                <option v-for="m in METHOD_OPTIONS" :key="m" :value="m">{{ m }}</option>
              </select>
            </div>
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">狀態</label>
              <select v-model="form.unlock_status" class="form-select">
                <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
              </select>
            </div>
          </div>

          <div class="mb-3">
            <label class="form-label small fw-semibold">取得地點</label>
            <input v-model="form.acquisition_location" type="text" class="form-control">
          </div>

          <div class="mb-3">
            <label class="form-label small fw-semibold">取得玩家</label>
            <select v-model="form.player_id" class="form-select">
              <option value="">— 選擇玩家 —</option>
              <option v-for="p in players" :key="p._id" :value="p._id">{{ p.player_name }}</option>
            </select>
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
import { blueprintApi } from '@/api'

defineProps({
  players: { type: Array, default: () => [] },
})
const emit = defineEmits(['saved'])

// 第 5.3 節：Blueprint 取得方式分類
const METHOD_OPTIONS = ['任務', 'NPC 掉落', '寶箱', '探索', '活動', '商店', '聲望獎勵', '特殊事件', '玩家取得', '未知']
// 第 5.2 節：Blueprint 狀態
const STATUS_OPTIONS = [
  { value: 'locked',       label: '🔒 未取得' },
  { value: 'obtained',     label: '📘 已取得' },
  { value: 'unlocked',     label: '✅ 已解鎖' },
  { value: 'unconfirmed',  label: '❓ 未確認' },
  { value: 'outdated',     label: '⚠️ 已過時' },
]

const modalEl = ref(null)
let   bsModal = null

const editId = ref('')
const saving = ref(false)
const error  = ref('')
const form = reactive({
  name: '', acquisition_method: '', acquisition_location: '',
  player_id: '', unlock_status: 'locked', notes: '',
})

onMounted(() => { bsModal = new Modal(modalEl.value) })

function open(bp = null) {
  editId.value               = bp?._id                  || ''
  error.value                 = ''
  form.name                   = bp?.name                  || ''
  form.acquisition_method    = bp?.acquisition_method    || ''
  form.acquisition_location = bp?.acquisition_location  || ''
  form.player_id              = bp?.player_id             || ''
  form.unlock_status          = bp?.unlock_status         || 'locked'
  form.notes                  = bp?.notes                 || ''
  bsModal.show()
}

function hide() { bsModal.hide() }

async function save() {
  error.value = ''
  if (!form.name.trim()) { error.value = 'Blueprint 名稱不得為空'; return }

  saving.value = true
  try {
    const payload = { ...form }
    const res = editId.value
      ? await blueprintApi.update(editId.value, payload)
      : await blueprintApi.create(payload)
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
