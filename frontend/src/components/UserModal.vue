<template>
  <div class="modal fade" ref="modalEl" tabindex="-1">
    <div class="modal-dialog">
      <div class="modal-content border-0 shadow">

        <div class="modal-header">
          <h5 class="modal-title">{{ editId ? '編輯使用者' : '新增使用者' }}</h5>
          <button type="button" class="btn-close" @click="hide"></button>
        </div>

        <div class="modal-body">
          <Transition name="alert-slide">
            <div v-if="error" class="alert alert-danger py-2 mb-3">{{ error }}</div>
          </Transition>

          <div class="mb-3">
            <label class="form-label small fw-semibold">
              帳號 <span class="text-danger">*</span>
            </label>
            <input v-model="form.username" type="text" class="form-control"
              autocomplete="off" :disabled="!!editId" required>
          </div>

          <div class="mb-3">
            <label class="form-label small fw-semibold">
              {{ editId ? '新密碼' : '密碼' }}
              <span v-if="!editId" class="text-danger">*</span>
            </label>
            <input v-model="form.password" type="password" class="form-control"
              autocomplete="new-password">
            <div v-if="editId" class="form-text">留空則不修改密碼</div>
          </div>

          <div class="mb-3">
            <label class="form-label small fw-semibold">
              確認密碼
              <span v-if="!editId" class="text-danger">*</span>
            </label>
            <input v-model="form.confirm" type="password" class="form-control"
              autocomplete="new-password">
          </div>

          <div class="mb-1">
            <label class="form-label small fw-semibold">
              使用者模板 <span class="text-danger">*</span>
            </label>
            <select v-model="form.templateId" class="form-select">
              <option value="">— 請選擇模板 —</option>
              <option v-for="t in templates" :key="t._id" :value="t._id">
                {{ t.name }} ({{ ROLE_LABELS[t.role] || t.role }})
              </option>
            </select>
            <div class="form-text text-muted">角色由模板決定，選擇後自動套用</div>
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
import { userApi } from '@/api'

const props = defineProps({
  templates: { type: Array, default: () => [] },
})
const emit = defineEmits(['saved'])

const ROLE_LABELS = { admin: '管理員', operator: '操作員', viewer: '檢視者' }

const modalEl = ref(null)
let   bsModal = null

const editId = ref('')
const saving = ref(false)
const error  = ref('')
const form   = reactive({ username: '', password: '', confirm: '', templateId: '' })

onMounted(() => { bsModal = new Modal(modalEl.value) })

function open(user = null) {
  editId.value      = user?._id || ''
  error.value       = ''
  form.username     = user?.username    || ''
  form.password     = ''
  form.confirm      = ''
  form.templateId   = user?.template_id || ''
  bsModal.show()
}

function hide() { bsModal.hide() }

async function save() {
  error.value = ''
  if (!editId.value && !form.password) {
    error.value = '密碼不得為空'; return
  }
  if (form.password && form.password !== form.confirm) {
    error.value = '兩次密碼輸入不一致'; return
  }
  if (!form.templateId) {
    error.value = '請選擇使用者模板'; return
  }

  saving.value = true
  try {
    let res
    if (editId.value) {
      const payload = { template_id: form.templateId }
      if (form.password) payload.password = form.password
      res = await userApi.update(editId.value, payload)
    } else {
      const username = form.username.trim()
      if (!username) { error.value = '帳號不得為空'; return }
      res = await userApi.create({ username, password: form.password, template_id: form.templateId })
    }
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
