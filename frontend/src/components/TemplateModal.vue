<template>
  <div class="modal fade" ref="modalEl" tabindex="-1">
    <div class="modal-dialog">
      <div class="modal-content border-0 shadow">

        <div class="modal-header">
          <h5 class="modal-title">{{ editId ? '編輯使用者模板' : '新增使用者模板' }}</h5>
          <button type="button" class="btn-close" @click="hide"></button>
        </div>

        <div class="modal-body">
          <Transition name="alert-slide">
            <div v-if="error" class="alert alert-danger py-2 mb-3">{{ error }}</div>
          </Transition>

          <div class="mb-3">
            <label class="form-label small fw-semibold">
              模板名稱 <span class="text-danger">*</span>
            </label>
            <input v-model="form.name" type="text" class="form-control" autocomplete="off" required>
          </div>

          <div class="mb-3">
            <label class="form-label small fw-semibold">
              角色 <span class="text-danger">*</span>
            </label>
            <select v-model="form.role" class="form-select" :disabled="isSystem">
              <option value="viewer">檢視者（viewer）</option>
              <option value="operator">操作員（operator）</option>
              <option value="admin">管理員（admin）</option>
            </select>
            <Transition name="alert-slide">
              <div v-if="showRoleWarn" class="form-text text-warning">
                <i class="bi bi-exclamation-triangle me-1"></i>
                修改角色將自動同步所有持有此模板的使用者
              </div>
            </Transition>
          </div>

          <div class="mb-1">
            <label class="form-label small fw-semibold">說明</label>
            <input v-model="form.description" type="text" class="form-control" autocomplete="off">
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
import { ref, reactive, computed, onMounted } from 'vue'
import { Modal } from 'bootstrap'
import { userApi } from '@/api'

const emit = defineEmits(['saved'])

const modalEl = ref(null)
let   bsModal = null

const editId   = ref('')
const isSystem = ref(false)
const origRole = ref('viewer')
const saving   = ref(false)
const error    = ref('')
const form     = reactive({ name: '', role: 'viewer', description: '' })

// 編輯中且角色已更改 → 顯示同步警告
const showRoleWarn = computed(
  () => !!editId.value && !isSystem.value && form.role !== origRole.value
)

onMounted(() => { bsModal = new Modal(modalEl.value) })

function open(tmpl = null) {
  editId.value      = tmpl?._id        || ''
  isSystem.value    = tmpl?.is_system  || false
  origRole.value    = tmpl?.role       || 'viewer'
  error.value       = ''
  form.name         = tmpl?.name        || ''
  form.role         = tmpl?.role        || 'viewer'
  form.description  = tmpl?.description || ''
  bsModal.show()
}

function hide() { bsModal.hide() }

async function save() {
  error.value = ''
  if (!form.name.trim()) { error.value = '模板名稱不得為空'; return }

  saving.value = true
  try {
    const payload = { name: form.name.trim(), role: form.role, description: form.description }
    const res = editId.value
      ? await userApi.updateTemplate(editId.value, payload)
      : await userApi.createTemplate(payload)
    if (!res) return
    const data = await res.json()
    if (data.success) {
      hide()
      emit('saved', data.synced_users)   // synced_users 僅 PUT 有值
    } else {
      error.value = data.message || '儲存失敗'
    }
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
