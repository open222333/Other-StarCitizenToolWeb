<!--
  後台「物品」：物品資料庫（item_master，唯讀）。

  資料由 tasks/scdata_sync.py 的「物品」同步項目從 Star Citizen Wiki API 同步（跟艦船、藍圖同一套），
  遊戲資料只能透過同步整批更新，這裡唯一能改的是「玩家頁面顯示」（PlayerVisibleToggle，
  src/models/visibility.py 的 items；名稱是佔位／測試用的自動不顯示）。

  列表：GET /item/?with_prices=1（後端分頁、多選篩選、排序白名單見 ItemMaster.SORTABLE_FIELDS），
  遊戲內價格來自 UEX（src/models/uex_item_price.py，「UEX 價格」同步項目，需 token）：
  最低購買價、最高收購價與地點數。點名稱展開詳細資料（components/ItemDetail.vue：
  基本欄位、遊戲內說明的數值、購買／收購地點）。
-->
<template>
  <div>
    <h5 class="mb-3 fw-bold"><i class="bi bi-database me-2 text-primary"></i>物品 Item</h5>

    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="nameQuery" type="search" class="form-control form-control-sm" style="max-width: 14rem"
            placeholder="搜尋物品名稱..." aria-label="搜尋物品名稱">
          <MultiSelectFilter :model-value="selectedTypes" label="類型" :options="facets.types" searchable
            @update:model-value="v => { selectedTypes = v; reload(0) }" />
          <MultiSelectFilter :model-value="selectedSubTypes" label="子類型" :options="facets.sub_types" searchable
            @update:model-value="v => { selectedSubTypes = v; reload(0) }" />
          <MultiSelectFilter :model-value="selectedManufacturers" label="製造商" :options="facets.manufacturers" searchable
            @update:model-value="v => { selectedManufacturers = v; reload(0) }" />
          <MultiSelectFilter :model-value="selectedSizes" label="尺寸" :options="sizeOptions"
            @update:model-value="v => { selectedSizes = v; reload(0) }" />
          <MultiSelectFilter :model-value="selectedGrades" label="等級" :options="gradeOptions"
            @update:model-value="v => { selectedGrades = v; reload(0) }" />
          <MultiSelectFilter :model-value="selectedAcquire" label="取得方式" :options="ITEM_ACQUIRE_OPTIONS"
            @update:model-value="v => { selectedAcquire = v; reload(0) }" />
          <select v-model="playerVisible" class="form-select form-select-sm w-auto" aria-label="玩家頁面顯示"
            @change="reload(0)">
            <option value="">玩家頁面：全部</option>
            <option value="1">玩家頁面：顯示</option>
            <option value="0">玩家頁面：不顯示</option>
          </select>
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
                <th v-for="c in COLUMNS" :key="c.label" :class="[c.cls, 'text-nowrap', c.sort ? 'sortable-th' : '']"
                  :role="c.sort ? 'button' : undefined" :tabindex="c.sort ? 0 : undefined"
                  @click="c.sort && toggleSort(c.sort)" @keydown.enter="c.sort && toggleSort(c.sort)">
                  {{ c.label }}
                  <i v-if="c.sort && sortBy === c.sort" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td :colspan="COLUMNS.length" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td :colspan="COLUMNS.length" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取物品資料失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!items.length">
                <td :colspan="COLUMNS.length" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的物品。' : '尚無物品資料（到「資料同步排程」同步物品）。' }}
                </td>
              </tr>
              <template v-else>
              <template v-for="it in items" :key="it._id">
                <tr>
                  <td class="ps-3">
                    <button type="button" class="btn btn-link p-0 text-start fw-semibold text-decoration-none"
                      :aria-expanded="openId === it._id ? 'true' : 'false'" @click="openId = openId === it._id ? '' : it._id">
                      <i class="bi me-1" :class="openId === it._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>{{ it.name }}
                    </button>
                    <span v-if="it.name_zh" class="ms-1">（{{ it.name_zh }}）</span>
                    <div class="small text-muted">{{ it.class_name }}</div>
                  </td>
                  <td class="small">{{ it.type || '—' }}<div v-if="it.sub_type" class="text-muted">{{ it.sub_type }}</div></td>
                  <td class="text-end small">{{ it.size ?? '—' }}</td>
                  <td class="text-end small">{{ it.grade ?? '—' }}</td>
                  <td class="small">{{ it.manufacturer_name || it.manufacturer_code || '—' }}</td>
                  <td class="text-end small text-nowrap">{{ it.volume_scu ? fmtNum(it.volume_scu) : '—' }}</td>
                  <td class="text-end small text-nowrap">
                    <template v-if="it.uex_price?.buy_min">{{ fmtAuec(it.uex_price.buy_min) }}
                      <div class="text-muted">{{ it.uex_price.buy_count }} 處</div></template>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td class="text-end small text-nowrap">
                    <template v-if="it.uex_price?.sell_max">{{ fmtAuec(it.uex_price.sell_max) }}
                      <div class="text-muted">{{ it.uex_price.sell_count }} 處</div></template>
                    <span v-else class="text-muted">—</span>
                  </td>
                  <td class="pe-3"><PlayerVisibleToggle dataset="items" :doc-id="it._id" :row="it" /></td>
                </tr>
                <tr v-if="openId === it._id">
                  <td :colspan="COLUMNS.length" class="ps-3 pe-3 py-2 detail-cell">
                    <ItemDetail :item="it" />
                  </td>
                </tr>
              </template>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-2">
      <div class="small text-muted">
        共 {{ total }} 筆<span v-if="total"> · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</span>
      </div>
      <div class="btn-group btn-group-sm">
        <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading"
          @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-outline-secondary" :disabled="loading || offset + limit >= total"
          @click="reload(offset + limit)">下一頁</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { itemApi } from '@/api'
import ItemDetail from '@/components/ItemDetail.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import PlayerVisibleToggle from '@/components/PlayerVisibleToggle.vue'
import { fmtAuec, ITEM_ACQUIRE_OPTIONS } from '@/utils/uexCommodity'

const COLUMNS = [
  { label: '名稱', cls: 'ps-3', sort: 'name' },
  { label: '類型', sort: 'type' },
  { label: '尺寸', cls: 'text-end', sort: 'size' },
  { label: '等級', cls: 'text-end', sort: 'grade' },
  { label: '製造商' },
  { label: '體積 (SCU)', cls: 'text-end', sort: 'volume_uscu' },
  { label: '最低購買', cls: 'text-end text-nowrap' },
  { label: '最高收購', cls: 'text-end text-nowrap' },
  { label: '玩家頁面', cls: 'pe-3 text-nowrap' },
]

const items = ref([])
const total = ref(0)
const limit = 50
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const openId = ref('')

const facets = ref({ types: [], sub_types: [], manufacturers: [], sizes: [], grades: [] })
const sizeOptions = computed(() => facets.value.sizes.map(n => ({ value: String(n), label: `Size ${n}` })))
const gradeOptions = computed(() => facets.value.grades.map(n => ({ value: String(n), label: `等級 ${n}` })))

const nameQuery = ref('')
const selectedTypes = ref([])
const selectedSubTypes = ref([])
const selectedManufacturers = ref([])
const selectedSizes = ref([])
const selectedGrades = ref([])
const selectedAcquire = ref([])
const playerVisible = ref('')
const sortBy = ref('name')
const sortDir = ref('asc')

const hasActiveFilters = computed(() => !!(nameQuery.value.trim() || selectedTypes.value.length
  || selectedSubTypes.value.length || selectedManufacturers.value.length || selectedSizes.value.length
  || selectedGrades.value.length || selectedAcquire.value.length || playerVisible.value))

function fmtNum(v) {
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: 6 })
}

function toggleSort(field) {
  if (sortBy.value === field) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  else { sortBy.value = field; sortDir.value = 'asc' }
  reload(0)
}

function resetFilters() {
  nameQuery.value = ''
  selectedTypes.value = []
  selectedSubTypes.value = []
  selectedManufacturers.value = []
  selectedSizes.value = []
  selectedGrades.value = []
  selectedAcquire.value = []
  playerVisible.value = ''
  reload(0)
}

let seq = 0
async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  const mine = ++seq
  const res = await itemApi.list({
    q: nameQuery.value.trim(),
    type: selectedTypes.value,
    sub_type: selectedSubTypes.value,
    manufacturer_code: selectedManufacturers.value,
    size: selectedSizes.value,
    grade: selectedGrades.value,
    acquire: selectedAcquire.value,
    player_visible: playerVisible.value,
    sort_by: sortBy.value,
    sort_dir: sortDir.value,
    with_prices: 1,
    limit, offset: newOffset,
  })
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (mine !== seq) return
  loading.value = false
  if (!body?.success) {
    items.value = []
    total.value = 0
    loadFailed.value = true
    return
  }
  items.value = body.data || []
  total.value = body.total || 0
  openId.value = ''
}

let timer = null
watch(nameQuery, () => {
  clearTimeout(timer)
  timer = setTimeout(() => reload(0), 350)
})
onBeforeUnmount(() => clearTimeout(timer))

onMounted(async () => {
  reload(0)
  const res = await itemApi.facets()
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (body?.success) facets.value = { ...facets.value, ...body.data }
})
</script>

<style scoped>
.sortable-th { cursor: pointer; user-select: none; }
.sortable-th:hover { color: var(--bs-primary); }
.detail-cell { background: var(--bs-tertiary-bg); }
</style>
