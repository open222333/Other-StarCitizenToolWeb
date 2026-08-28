<!-- 庫存管理列表（後台管理主控台，對應 app/inventory/view.py） -->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
      <h5 class="mb-0 fw-bold"><i class="bi bi-box-seam me-2 text-primary"></i>庫存 Inventory</h5>
      <div class="d-flex gap-2 flex-wrap">
        <SearchBox v-model="keyword" placeholder="搜尋物品名稱..." />
        <button v-if="canWrite" class="btn btn-success btn-sm" @click="openAdjust('add')">
          <i class="bi bi-plus-lg me-1"></i>入庫
        </button>
        <button v-if="canWrite" class="btn btn-outline-danger btn-sm" @click="openAdjust('remove')">
          <i class="bi bi-dash-lg me-1"></i>出庫
        </button>
      </div>
    </div>

    <Transition name="alert-slide">
      <div v-if="msg" :class="`alert alert-${msgType} py-2 mb-3`">{{ msg }}</div>
    </Transition>

    <!-- ── 篩選列 ── -->
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="row g-2 align-items-center">
          <div class="col-auto">
            <select class="form-select form-select-sm" v-model="filters.owner_type" @change="onOwnerTypeChange">
              <option value="guild">公會共享庫</option>
              <option value="player">個人庫</option>
            </select>
          </div>
          <div class="col-auto" v-if="filters.owner_type === 'player'">
            <input class="form-control form-control-sm" style="width:180px"
              v-model="filters.player" placeholder="玩家 SCID / RSI handle" @change="load">
          </div>
          <div class="col-auto">
            <select class="form-select form-select-sm" v-model="filters.location" @change="load">
              <option value="">全部位置</option>
              <option v-for="loc in locations" :key="loc" :value="loc">{{ loc }}</option>
            </select>
          </div>
          <div class="col-auto ms-auto small text-muted" v-if="summary">
            共 {{ summary.lines }} 筆 · {{ summary.units }} 件 · {{ summary.total_scu }} SCU
            <span v-if="summary.unknown_volume" class="text-warning">
              （{{ summary.unknown_volume }} 項無體積資料，總 SCU 可能低估）
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">歸屬</th>
                <th>位置</th>
                <th>容器</th>
                <th>物品</th>
                <th>數量</th>
                <th>SCU</th>
                <th style="width:100px" class="pe-3" v-if="canWrite">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td :colspan="canWrite ? 7 : 6" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!filtered.length">
                <td :colspan="canWrite ? 7 : 6" class="text-center py-4 text-muted">尚無庫存資料</td>
              </tr>
              <template v-else>
                <tr v-for="row in filtered" :key="`${row.owner_type}-${row.player}-${row.location}-${row.container}-${row.item_id}`">
                  <td class="ps-3 small">
                    <span v-if="row.owner_type === 'guild'" class="badge bg-secondary">公會</span>
                    <span v-else class="badge bg-info text-dark">{{ row.player || '個人' }}</span>
                  </td>
                  <td class="small">{{ row.location || '—' }}</td>
                  <td class="small text-muted">{{ row.container || '—' }}</td>
                  <td class="fw-semibold small">
                    {{ row.item_name }}
                    <span v-if="row.item_name_zh" class="text-muted">（{{ row.item_name_zh }}）</span>
                    <span v-if="row.item_retired" class="badge bg-warning text-dark ms-1">已下架</span>
                  </td>
                  <td class="small">{{ row.quantity }}</td>
                  <td class="small text-muted">{{ row.total_scu }}</td>
                  <td class="pe-3" v-if="canWrite">
                    <button class="btn btn-sm btn-outline-secondary" @click="openAdjustForRow(row)">
                      <i class="bi bi-sliders"></i>
                    </button>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── 入庫／出庫 調整 Modal ── -->
    <div class="modal fade" ref="adjustModalEl" tabindex="-1">
      <div class="modal-dialog">
        <div class="modal-content border-0 shadow">
          <div class="modal-header border-0 pb-0">
            <h5 class="modal-title">
              <i :class="`bi ${adjustMode === 'add' ? 'bi-plus-lg text-success' : 'bi-dash-lg text-danger'} me-1`"></i>
              {{ adjustMode === 'add' ? '入庫' : '出庫' }}
            </h5>
            <button type="button" class="btn-close" @click="closeAdjust"></button>
          </div>
          <div class="modal-body">
            <div v-if="adjustError" class="alert alert-danger py-2 small">{{ adjustError }}</div>
            <div class="row g-2">
              <div class="col-6">
                <label class="form-label small">歸屬</label>
                <select class="form-select form-select-sm" v-model="adjustForm.owner_type">
                  <option value="guild">公會共享庫</option>
                  <option value="player">個人庫</option>
                </select>
              </div>
              <div class="col-6" v-if="adjustForm.owner_type === 'player'">
                <label class="form-label small">玩家 SCID</label>
                <input class="form-control form-control-sm" v-model="adjustForm.player">
              </div>
              <div class="col-12">
                <label class="form-label small">物品（uuid 或完整名稱）</label>
                <input class="form-control form-control-sm" v-model="adjustForm.item" placeholder="例如 Laser Repeater 或物品 uuid">
              </div>
              <div class="col-6">
                <label class="form-label small">數量</label>
                <input type="number" min="1" class="form-control form-control-sm" v-model.number="adjustForm.quantity">
              </div>
              <div class="col-6">
                <label class="form-label small">位置</label>
                <input class="form-control form-control-sm" v-model="adjustForm.location">
              </div>
              <div class="col-6">
                <label class="form-label small">容器（可留空）</label>
                <input class="form-control form-control-sm" v-model="adjustForm.container">
              </div>
              <div class="col-6">
                <label class="form-label small">備註（可留空）</label>
                <input class="form-control form-control-sm" v-model="adjustForm.note">
              </div>
            </div>
          </div>
          <div class="modal-footer border-0">
            <button type="button" class="btn btn-secondary btn-sm" @click="closeAdjust">取消</button>
            <button type="button"
              :class="`btn btn-sm ${adjustMode === 'add' ? 'btn-success' : 'btn-danger'}`"
              :disabled="adjustSubmitting"
              @click="submitAdjust">
              <span v-if="adjustSubmitting" class="spinner-border spinner-border-sm me-1"></span>
              確認{{ adjustMode === 'add' ? '入庫' : '出庫' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { Modal } from 'bootstrap'
import { useAuthStore } from '@/stores/auth'
import { inventoryApi } from '@/api'
import SearchBox from '@/components/SearchBox.vue'

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')

const rows      = ref([])
const locations = ref([])
const summary   = ref(null)
const loading   = ref(false)
const keyword   = ref('')

const filters = reactive({
  owner_type: 'guild',
  player: '',
  location: '',
})

const msg = ref(''); const msgType = ref('success')
function flash(text, type = 'danger') {
  msg.value = text; msgType.value = type
  setTimeout(() => { msg.value = '' }, 3000)
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return rows.value
  return rows.value.filter(r =>
    (r.item_name || '').toLowerCase().includes(kw) ||
    (r.item_name_zh || '').toLowerCase().includes(kw)
  )
})

function onOwnerTypeChange() {
  if (filters.owner_type === 'guild') filters.player = ''
  load()
}

async function load() {
  // 個人庫沒指定玩家時，先不打 API（後端會回 400）
  if (filters.owner_type === 'player' && !filters.player.trim()) {
    rows.value = []; summary.value = null
    return
  }
  loading.value = true
  const res = await inventoryApi.list({
    owner_type: filters.owner_type,
    player: filters.owner_type === 'player' ? filters.player.trim() : undefined,
    location: filters.location,
    limit: 200,
  })
  if (res) {
    const d = await res.json()
    if (d.success) { rows.value = d.data || []; summary.value = d.summary || null }
    else flash(d.message || '載入失敗')
  }
  loading.value = false
}

async function loadLocations() {
  const res = await inventoryApi.locations()
  if (res) { const d = await res.json(); locations.value = d.data || [] }
}

// ── 入庫／出庫 ──
const adjustModalEl   = ref(null)
let adjustModal        = null
const adjustMode        = ref('add')
const adjustSubmitting  = ref(false)
const adjustError       = ref('')
const adjustForm = reactive({
  owner_type: 'guild', player: '', item: '', quantity: 1,
  location: '', container: '', note: '',
})

function openAdjust(mode) {
  adjustMode.value = mode
  adjustError.value = ''
  Object.assign(adjustForm, {
    owner_type: filters.owner_type, player: filters.player,
    item: '', quantity: 1, location: filters.location, container: '', note: '',
  })
  adjustModal.show()
}

function openAdjustForRow(row) {
  adjustMode.value = 'remove'
  adjustError.value = ''
  Object.assign(adjustForm, {
    owner_type: row.owner_type, player: row.player || '',
    item: row.item_id, quantity: 1, location: row.location || '',
    container: row.container || '', note: '',
  })
  adjustModal.show()
}

function closeAdjust() { adjustModal.hide() }

async function submitAdjust() {
  adjustError.value = ''
  if (!adjustForm.item.trim()) { adjustError.value = '請輸入物品'; return }
  if (!adjustForm.location.trim()) { adjustError.value = '請輸入位置'; return }
  if (!adjustForm.quantity || adjustForm.quantity <= 0) { adjustError.value = '數量必須大於 0'; return }
  if (adjustForm.owner_type === 'player' && !adjustForm.player.trim()) {
    adjustError.value = '個人庫必須指定玩家'; return
  }

  adjustSubmitting.value = true
  const payload = {
    owner_type: adjustForm.owner_type,
    player: adjustForm.owner_type === 'player' ? adjustForm.player.trim() : undefined,
    item: adjustForm.item.trim(),
    quantity: adjustForm.quantity,
    location: adjustForm.location.trim(),
    container: adjustForm.container.trim() || undefined,
    note: adjustForm.note.trim() || undefined,
  }
  const res = adjustMode.value === 'add'
    ? await inventoryApi.add(payload)
    : await inventoryApi.remove(payload)
  adjustSubmitting.value = false

  if (!res) { adjustError.value = '網路錯誤，請稍後再試'; return }
  const data = await res.json()
  if (data.success) {
    closeAdjust()
    flash(adjustMode.value === 'add' ? '入庫成功' : '出庫成功', 'success')
    await load()
    await loadLocations()
  } else {
    adjustError.value = data.message || '操作失敗'
  }
}

onMounted(async () => {
  adjustModal = new Modal(adjustModalEl.value)
  await Promise.all([load(), loadLocations()])
})
</script>

<style scoped>
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>
