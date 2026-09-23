<!--
  艦船基本資料（唯讀，管理後台）。

  資料來源是 vehicle_master（由 tasks/scdata_sync.py 從 Star Citizen Wiki
  API 同步而來，跟 item_master／blueprint_master 是同一套同步機制），這裡
  只讀不寫，沒有新增/編輯/刪除——遊戲主檔的異動只能透過「系統設定 → 資料
  同步」整批更新，不是在這裡手動改。

  篩選/排序/分頁比照全站搜尋優化計畫（藍圖登記管理那批）的既有做法：
  多選篩選用 MultiSelectFilter，排序欄位在後端 VehicleMaster.SORTABLE_FIELDS
  有白名單擋著，分頁走 limit/offset。

  ⚠️ 沒有中文名稱：vehicle_master 目前沒有 name_zh 欄位（跟 item_master／
  blueprint_master 不同），列表只顯示英文名稱，不是漏做。

  ⚠️ 「建議售價」是 msrp 欄位，數值是遊戲官網的美金標價（真實貨幣，不是
  遊戲內 UEC），例如新手船 100i 是 50（代表 $50 USD）、Idris-P 巡防艦是
  1900（$1,900 USD）——不要跟遊戲內經濟的 UEC 價格搞混。
-->
<template>
  <div>
    <h5 class="mb-3 fw-bold"><i class="bi bi-rocket-takeoff me-2 text-primary"></i>艦船 Vehicle</h5>

    <!-- ── 篩選 ────────────────────────────────────────────── -->
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="nameQuery" type="text" class="form-control form-control-sm"
            style="max-width: 12rem" placeholder="搜尋艦船名稱..." @change="reload(0)">

          <MultiSelectFilter :model-value="selectedCareers" label="Career" :options="careerOptions"
            @update:model-value="onCareersChange">
          </MultiSelectFilter>
          <MultiSelectFilter :model-value="selectedRoles" label="Role" :options="roleOptions"
            @update:model-value="onRolesChange">
          </MultiSelectFilter>
          <MultiSelectFilter :model-value="selectedManufacturers" label="製造商" :options="manufacturerOptions"
            @update:model-value="onManufacturersChange">
          </MultiSelectFilter>
          <MultiSelectFilter :model-value="selectedSizeClasses" label="尺寸" :options="sizeClassOptions"
            @update:model-value="onSizeClassesChange">
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
                  名稱
                  <i v-if="sortBy === 'name'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th>製造商</th>
                <th>Career</th>
                <th>Role</th>
                <th class="sortable-th text-end" role="button" tabindex="0"
                  @click="toggleSort('size_class')" @keydown.enter="toggleSort('size_class')">
                  尺寸
                  <i v-if="sortBy === 'size_class'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th text-end" role="button" tabindex="0"
                  @click="toggleSort('crew_max')" @keydown.enter="toggleSort('crew_max')">
                  載員
                  <i v-if="sortBy === 'crew_max'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th text-end" role="button" tabindex="0"
                  @click="toggleSort('cargo_capacity_scu')" @keydown.enter="toggleSort('cargo_capacity_scu')">
                  貨艙 (SCU)
                  <i v-if="sortBy === 'cargo_capacity_scu'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th text-end" role="button" tabindex="0"
                  @click="toggleSort('mass_hull')" @keydown.enter="toggleSort('mass_hull')">
                  質量 (kg)
                  <i v-if="sortBy === 'mass_hull'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="sortable-th text-end pe-3" role="button" tabindex="0"
                  @click="toggleSort('msrp')" @keydown.enter="toggleSort('msrp')">
                  建議售價 (USD)
                  <i v-if="sortBy === 'msrp'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="8" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="8" class="text-center py-4">
                  <span class="text-warning">
                    <i class="bi bi-exclamation-triangle me-1"></i>讀取艦船資料失敗。
                  </span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!vehicles.length">
                <td colspan="8" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的艦船。' : '尚無艦船資料 —— 請先在「系統設定 → 資料同步」跑一次同步。' }}
                </td>
              </tr>
              <template v-else>
                <tr v-for="v in vehicles" :key="v._id">
                  <td class="ps-3">
                    <span class="fw-semibold">{{ v.name }}</span>
                    <span v-if="v.name_zh" class="ms-1">（{{ v.name_zh }}）</span>
                    <span v-if="v.class_name" class="small text-muted ms-1">{{ v.class_name }}</span>
                  </td>
                  <td class="small">{{ v.manufacturer_name || v.manufacturer_code || '—' }}</td>
                  <td class="small">{{ v.career || '—' }}</td>
                  <td class="small">{{ v.role_zh ? `${v.role_zh}（${v.role}）` : (v.role || '—') }}</td>
                  <td class="text-end small">{{ v.size_class ?? '—' }}</td>
                  <td class="text-end small">{{ crewLabel(v) }}</td>
                  <td class="text-end small">{{ fmtNum(v.cargo_capacity_scu) }}</td>
                  <td class="text-end small">{{ fmtNum(v.mass_hull) }}</td>
                  <td class="text-end small pe-3">{{ v.msrp ? '$' + fmtNum(v.msrp) : '—' }}</td>
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
        <template v-if="total === null">
          搜尋模式下不顯示總筆數{{ vehicles.length >= limit ? '，可能還有下一頁' : '' }}
        </template>
        <template v-else>
          共 {{ total }} 筆<span v-if="total"> · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</span>
        </template>
      </div>
      <div class="btn-group btn-group-sm">
        <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading"
          @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-outline-secondary"
          :disabled="loading || (total === null ? vehicles.length < limit : offset + limit >= total)"
          @click="reload(offset + limit)">下一頁</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { vehicleApi } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'

const vehicles   = ref([])
const total      = ref(0)
const limit      = 50
const offset     = ref(0)
const loading    = ref(false)
const loadFailed = ref(false)

const careerOptions       = ref([])
const roleOptions         = ref([])
const manufacturerOptions = ref([])
const sizeClassOptions    = ref([])

const selectedCareers       = ref([])
const selectedRoles         = ref([])
const selectedManufacturers = ref([])
const selectedSizeClasses   = ref([])
const nameQuery = ref('')
const sortBy  = ref('name')
const sortDir = ref('asc')

const hasActiveFilters = computed(() =>
  selectedCareers.value.length || selectedRoles.value.length ||
  selectedManufacturers.value.length || selectedSizeClasses.value.length || nameQuery.value)

function crewLabel(v) {
  if (!v.crew_max) return '—'
  if (v.crew_min && v.crew_min !== v.crew_max) return `${v.crew_min}–${v.crew_max}`
  return String(v.crew_max)
}

function fmtNum(v) {
  if (v === null || v === undefined) return '—'
  return Math.round(v).toLocaleString('en-US')
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

// 跟 BlueprintListView.vue 同一個理由：明確的 change handler 一次做完
// 「更新選取狀態」跟「重新查詢」，不靠 v-model + watch。
function onCareersChange(values) { selectedCareers.value = values; reload(0) }
function onRolesChange(values) { selectedRoles.value = values; reload(0) }
function onManufacturersChange(values) { selectedManufacturers.value = values; reload(0) }
function onSizeClassesChange(values) { selectedSizeClasses.value = values; reload(0) }

function resetFilters() {
  selectedCareers.value = []
  selectedRoles.value = []
  selectedManufacturers.value = []
  selectedSizeClasses.value = []
  nameQuery.value = ''
  reload(0)
}

async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  const res = await vehicleApi.list({
    career: selectedCareers.value,
    role: selectedRoles.value,
    manufacturer_code: selectedManufacturers.value,
    size_class: selectedSizeClasses.value,
    q: nameQuery.value,
    sort_by: sortBy.value,
    sort_dir: sortDir.value,
    limit, offset: newOffset,
  })
  if (res && res.ok) {
    const body = await res.json()
    vehicles.value = body.data || []
    total.value = body.total ?? null   // q 帶關鍵字且無其他篩選時後端回 null（見 app/item/view.py）
  } else {
    vehicles.value = []
    loadFailed.value = true
  }
  loading.value = false
}

onMounted(async () => {
  await reload(0)
  const [careersRes, rolesRes, manufacturersRes, sizeClassesRes] = await Promise.all([
    vehicleApi.careers(), vehicleApi.facets(), vehicleApi.manufacturers(), vehicleApi.sizeClasses(),
  ])
  if (careersRes?.ok) careerOptions.value = (await careersRes.json()).data || []
  // 角色選項用 facets 的 [{value, label}]，label 含中文（見 VehicleMaster.role_options）
  if (rolesRes?.ok) roleOptions.value = ((await rolesRes.json()).data || {}).roles || []
  if (manufacturersRes?.ok) manufacturerOptions.value = (await manufacturersRes.json()).data || []
  if (sizeClassesRes?.ok) {
    const sizes = (await sizeClassesRes.json()).data || []
    sizeClassOptions.value = sizes.map(n => ({ value: String(n), label: `Size ${n}` }))
  }
})
</script>

<style scoped>
.sortable-th { cursor: pointer; user-select: none; }
.sortable-th:hover { color: var(--bs-primary); }
</style>
