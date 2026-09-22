<!-- 藍圖管理列表（規格書第 5 節；篩選/排序/分頁見全站搜尋優化計畫第 2 項） -->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold"><i class="bi bi-journal-bookmark me-2 text-primary"></i>藍圖 Blueprint</h5>
      <button class="btn btn-primary btn-sm" @click="bpModalRef.open()">
        <i class="bi bi-plus-lg me-1"></i>新增藍圖
      </button>
    </div>

    <Transition name="alert-slide">
      <div v-if="msg" :class="`alert alert-${msgType} py-2 mb-3`">{{ msg }}</div>
    </Transition>

    <!-- ── 篩選 ────────────────────────────────────────────── -->
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="nameQuery" type="text" class="form-control form-control-sm"
            style="max-width: 12rem" placeholder="搜尋 Blueprint 名稱..." @change="reload(0)">
          <input v-model="locationQuery" type="text" class="form-control form-control-sm"
            style="max-width: 12rem" placeholder="搜尋取得地點..." @change="reload(0)">

          <MultiSelectFilter :model-value="selectedMethods" label="取得方式" :options="methodOptions"
            @update:model-value="onMethodsChange">
          </MultiSelectFilter>
          <MultiSelectFilter :model-value="selectedStatuses" label="狀態" :options="statusOptions"
            @update:model-value="onStatusesChange">
          </MultiSelectFilter>
          <MultiSelectFilter :model-value="selectedPlayers" label="取得玩家" :options="playerOptions"
            @update:model-value="onPlayersChange">
          </MultiSelectFilter>

          <button v-if="hasActiveFilters" type="button" class="btn btn-sm btn-link" @click="resetFilters">
            清除全部篩選
          </button>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3 sortable-th" role="button" tabindex="0"
                  @click="toggleSort('name')" @keydown.enter="toggleSort('name')">
                  Blueprint 名稱
                  <i v-if="sortBy === 'name'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleSort('acquisition_method')" @keydown.enter="toggleSort('acquisition_method')">
                  取得方式
                  <i v-if="sortBy === 'acquisition_method'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleSort('acquisition_location')" @keydown.enter="toggleSort('acquisition_location')">
                  取得地點
                  <i v-if="sortBy === 'acquisition_location'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th>取得玩家</th>
                <th class="sortable-th" role="button" tabindex="0"
                  @click="toggleSort('unlock_status')" @keydown.enter="toggleSort('unlock_status')">
                  狀態
                  <i v-if="sortBy === 'unlock_status'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th style="width:140px" class="pe-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="6" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="6" class="text-center py-4">
                  <span class="text-warning">
                    <i class="bi bi-exclamation-triangle me-1"></i>讀取藍圖失敗。
                  </span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!blueprints.length">
                <td colspan="6" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的藍圖。' : '尚無藍圖資料' }}
                </td>
              </tr>
              <template v-else>
                <tr v-for="bp in blueprints" :key="bp._id">
                  <td class="ps-3 fw-semibold">{{ bp.name }}</td>
                  <td class="small">{{ bp.acquisition_method || '未知' }}</td>
                  <td class="small">{{ bp.acquisition_location || '—' }}</td>
                  <td class="small">{{ playerName(bp.player_id) }}</td>
                  <td><StatusBadge :status="bp.unlock_status" /></td>
                  <td class="pe-3">
                    <button class="btn btn-sm btn-outline-secondary me-1" @click="bpModalRef.open(bp)">
                      <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" @click="handleDelete(bp)">
                      <i class="bi bi-trash"></i>
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

    <BlueprintFormModal ref="bpModalRef" :players="playerStore.players" @saved="reload(offset)" />
    <ConfirmModal       ref="confirmModalRef" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { usePlayerStore } from '@/stores/player'
import { blueprintApi } from '@/api'
import StatusBadge         from '@/components/StatusBadge.vue'
import BlueprintFormModal   from '@/components/BlueprintFormModal.vue'
import ConfirmModal          from '@/components/ConfirmModal.vue'
import MultiSelectFilter     from '@/components/MultiSelectFilter.vue'

const playerStore = usePlayerStore()

// 跟 BlueprintFormModal.vue 用同一份列舉值 —— 那邊也是照抄規格書第 5.2／5.3
// 節寫死的常數，這裡刻意保持一樣的重複而不是抽共用檔，理由見那個檔案的
// 註解：欄位很少改動，多一個共用模組換來的維護成本不值得。
const METHOD_OPTIONS = ['任務', 'NPC 掉落', '寶箱', '探索', '活動', '商店', '聲望獎勵', '特殊事件', '玩家取得', '未知']
const STATUS_OPTIONS = [
  { value: 'locked',      label: '🔒 未取得' },
  { value: 'obtained',    label: '📘 已取得' },
  { value: 'unlocked',    label: '✅ 已解鎖' },
  { value: 'unconfirmed', label: '❓ 未確認' },
  { value: 'outdated',    label: '⚠️ 已過時' },
]

const blueprints  = ref([])
const total       = ref(0)
const limit       = 50
const offset      = ref(0)
const loading     = ref(false)
const loadFailed  = ref(false)
const bpModalRef       = ref(null)
const confirmModalRef  = ref(null)
const msg = ref(''); const msgType = ref('success')

const methodOptions = METHOD_OPTIONS
const statusOptions = STATUS_OPTIONS
const playerOptions = computed(() =>
  playerStore.players.map((p) => ({ value: p._id, label: p.player_name })))

const selectedMethods  = ref([])
const selectedStatuses = ref([])
const selectedPlayers  = ref([])
const nameQuery     = ref('')
const locationQuery = ref('')
const sortBy  = ref('name')
const sortDir = ref('asc')

const hasActiveFilters = computed(() =>
  selectedMethods.value.length || selectedStatuses.value.length ||
  selectedPlayers.value.length || nameQuery.value || locationQuery.value)

function playerName(id) {
  return id ? (playerStore.byId(id)?.player_name || '') : '—'
}

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

// 跟 LogsView.vue 同一個理由：明確的 change handler 一次做完
// 「更新選取狀態」跟「重新查詢」，不靠 v-model + watch。
function onMethodsChange(values) {
  selectedMethods.value = values
  reload(0)
}
function onStatusesChange(values) {
  selectedStatuses.value = values
  reload(0)
}
function onPlayersChange(values) {
  selectedPlayers.value = values
  reload(0)
}

function resetFilters() {
  selectedMethods.value = []
  selectedStatuses.value = []
  selectedPlayers.value = []
  nameQuery.value = ''
  locationQuery.value = ''
  reload(0)
}

async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  const res = await blueprintApi.list({
    acquisition_method:  selectedMethods.value,
    unlock_status:       selectedStatuses.value,
    player_id:           selectedPlayers.value,
    q:                    nameQuery.value,
    acquisition_location: locationQuery.value,
    sort_by:  sortBy.value,
    sort_dir: sortDir.value,
    limit, offset: newOffset,
  })
  if (res && res.ok) {
    const body = await res.json()
    blueprints.value = body.data || []
    total.value = body.total || 0
  } else {
    blueprints.value = []
    loadFailed.value = true
  }
  loading.value = false
}

async function handleDelete(bp) {
  const ok = await confirmModalRef.value.confirm(
    `確定要刪除藍圖 <strong>${escHtml(bp.name)}</strong>？`
  )
  if (!ok) return
  const res = await blueprintApi.remove(bp._id)
  if (!res) return
  const data = await res.json()
  if (data.success) reload(offset.value)
  else flash(data.message || '刪除失敗')
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

onMounted(async () => {
  await reload(0)
  if (!playerStore.players.length) await playerStore.load()
})
</script>

<style scoped>
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
.sortable-th { cursor: pointer; user-select: none; }
.sortable-th:hover { color: var(--bs-primary); }
</style>
