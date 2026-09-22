<!-- 庫存管理列表（後台管理主控台，對應 app/inventory/view.py） -->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
      <h5 class="mb-0 fw-bold"><i class="bi bi-box-seam me-2 text-primary"></i>庫存 Inventory</h5>
      <div class="d-flex gap-2 flex-wrap">
        <SearchBox v-model="nameQuery" placeholder="搜尋物品名稱..." />
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
        <div class="d-flex flex-wrap align-items-center gap-2">
          <select class="form-select form-select-sm" style="width:auto" v-model="filters.owner_type" @change="onOwnerTypeChange">
            <option value="guild">公會共享庫</option>
            <option value="player">個人庫</option>
          </select>
          <input v-if="filters.owner_type === 'player'" class="form-control form-control-sm" style="width:180px"
            v-model="filters.player" placeholder="玩家 SCID / RSI handle" @change="reload(0)">

          <MultiSelectFilter :model-value="selectedLocations" label="位置" :options="locations"
            @update:model-value="onLocationsChange">
          </MultiSelectFilter>
          <input v-model="containerQuery" type="text" class="form-control form-control-sm"
            style="max-width: 10rem" placeholder="搜尋容器..." @change="reload(0)">

          <button v-if="hasActiveFilters" type="button" class="btn btn-sm btn-link" @click="resetFilters">
            清除全部篩選
          </button>

          <div class="ms-auto small text-muted" v-if="summary">
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
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleSort('location')" @keydown.enter="toggleSort('location')">
                  位置
                  <i v-if="sortBy === 'location'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleSort('container')" @keydown.enter="toggleSort('container')">
                  容器
                  <i v-if="sortBy === 'container'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleSort('item_name')" @keydown.enter="toggleSort('item_name')">
                  物品
                  <i v-if="sortBy === 'item_name'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleSort('quantity')" @keydown.enter="toggleSort('quantity')">
                  數量
                  <i v-if="sortBy === 'quantity'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleSort('total_scu')" @keydown.enter="toggleSort('total_scu')">
                  SCU
                  <i v-if="sortBy === 'total_scu'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th style="width:100px" class="pe-3" v-if="canWrite">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td :colspan="canWrite ? 7 : 6" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td :colspan="canWrite ? 7 : 6" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的庫存。' : '尚無庫存資料' }}
                </td>
              </tr>
              <template v-else>
                <tr v-for="row in rows" :key="`${row.owner_type}-${row.player}-${row.location}-${row.container}-${row.item_id}`">
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

    <!-- ── 分頁 ────────────────────────────────────────────── -->
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-2">
      <div class="small text-muted">
        共 {{ total }} 筆<span v-if="total"> · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</span>
      </div>
      <div class="btn-group btn-group-sm">
        <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading"
          @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-outline-secondary" :disabled="offset + limit >= total || loading"
          @click="reload(offset + limit)">下一頁</button>
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
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { Modal } from 'bootstrap'
import { useAuthStore } from '@/stores/auth'
import { inventoryApi } from '@/api'
import SearchBox          from '@/components/SearchBox.vue'
import MultiSelectFilter  from '@/components/MultiSelectFilter.vue'

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')

const rows      = ref([])
const total     = ref(0)
const limit     = 50
const offset    = ref(0)
const locations = ref([])
const summary   = ref(null)
const loading   = ref(false)

const filters = reactive({
  owner_type: 'guild',
  player: '',
})

// ── 篩選（位置多選、容器/物品關鍵字、排序）──────────────────────────
// 物品名稱關鍵字改成真的送去後端查（見 app/inventory/view.py 的 q 參數），
// 不再是「只在目前這一頁裡用 JS 過濾」—— 舊寫法在庫存超過一頁時，
// 篩選結果會漏掉沒被載入的那些頁，是會讓使用者以為「搜尋結果就這些」的
// 隱性錯誤，比 400/500 更難發現。
const selectedLocations = ref([])
const containerQuery    = ref('')
const nameQuery         = ref('')
const sortBy  = ref('item_name')
const sortDir = ref('asc')

const hasActiveFilters = computed(() =>
  selectedLocations.value.length || containerQuery.value.trim() || nameQuery.value.trim())

const msg = ref(''); const msgType = ref('success')
function flash(text, type = 'danger') {
  msg.value = text; msgType.value = type
  setTimeout(() => { msg.value = '' }, 3000)
}

function toggleSort(field) {
  if (sortBy.value === field) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortBy.value = field
    sortDir.value = 'asc'
  }
  reload(0)
}

function onLocationsChange(values) {
  selectedLocations.value = values
  reload(0)
}

function resetFilters() {
  selectedLocations.value = []
  containerQuery.value = ''
  nameQuery.value = ''
  reload(0)
}

function onOwnerTypeChange() {
  if (filters.owner_type === 'guild') filters.player = ''
  reload(0)
}

// 物品名稱是這頁唯一「邊打邊搜」的欄位（SearchBox 沒有像 Blueprint/Log
// 頁那些次要篩選一樣等 blur 才送出的 @change），所以要 debounce，
// 不然每敲一個字就打一次後端。
let nameDebounceTimer = null
watch(nameQuery, () => {
  clearTimeout(nameDebounceTimer)
  nameDebounceTimer = setTimeout(() => reload(0), 350)
})
onBeforeUnmount(() => clearTimeout(nameDebounceTimer))

async function reload(newOffset = 0) {
  // 個人庫沒指定玩家時，先不打 API（後端會回 400）
  if (filters.owner_type === 'player' && !filters.player.trim()) {
    rows.value = []; summary.value = null; total.value = 0
    return
  }
  offset.value = newOffset
  loading.value = true
  const res = await inventoryApi.list({
    owner_type: filters.owner_type,
    player: filters.owner_type === 'player' ? filters.player.trim() : undefined,
    location: selectedLocations.value,
    container: containerQuery.value.trim(),
    q: nameQuery.value.trim(),
    sort_by: sortBy.value,
    sort_dir: sortDir.value,
    limit, offset: newOffset,
  })
  if (res) {
    const d = await res.json()
    if (d.success) {
      rows.value = d.data || []
      summary.value = d.summary || null
      total.value = d.total || 0
    } else {
      flash(d.message || '載入失敗')
      rows.value = []; total.value = 0
    }
  } else {
    flash('網路錯誤，請稍後再試')
    rows.value = []; total.value = 0
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
    item: '', quantity: 1, location: '', container: '', note: '',
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
    await reload(offset.value)
    await loadLocations()
  } else {
    adjustError.value = data.message || '操作失敗'
  }
}

onMounted(async () => {
  adjustModal = new Modal(adjustModalEl.value)
  await Promise.all([reload(0), loadLocations()])
})
</script>

<style scoped>
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }

.sortable-th { cursor: pointer; user-select: none; }
.sortable-th:hover { color: var(--bs-primary); }
</style>
