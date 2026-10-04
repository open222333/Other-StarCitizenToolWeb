<!--
  後台「艦船」頁，兩個分頁：艦船資料庫（下面這些）、玩家擁有艦船
  （components/FleetOwnersBrowser.vue，玩家登記的船，唯讀）。

  艦船基本資料（管理後台）。

  資料來源是 vehicle_master（由 tasks/scdata_sync.py 從 Star Citizen Wiki
  API 同步而來，跟 item_master／blueprint_master 是同一套同步機制），遊戲
  資料本身只能透過同步整批更新，不在這裡改。

  後台可以改的只有兩個（都存在主檔的另外欄位，重新同步不會蓋掉）：
    - 玩家頁面顯示（PlayerVisibleToggle，見 src/models/visibility.py）
    - （自動，不能改）系統說明 system_note：同名變體多出來的 class_name 部分（例如
      ANVL_Lightning_F8C_Plat →「Plat」），同步後由 VehicleMaster.apply_system_notes() 算
    - 手寫說明 note（PUT /item/vehicles/<id>/note，最多 1000 字；玩家頁的艦隊、
      持有船艦、批量登記會顯示，換行照原樣）

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

    <ul class="nav nav-tabs mb-3">
      <li class="nav-item">
        <button type="button" class="nav-link" :class="{ active: tab === 'master' }" @click="tab = 'master'">
          艦船資料庫
        </button>
      </li>
      <li class="nav-item">
        <button type="button" class="nav-link" :class="{ active: tab === 'owned' }" @click="tab = 'owned'">
          玩家擁有艦船
        </button>
      </li>
    </ul>

    <div v-show="tab === 'master'">

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
                <th class="sortable-th text-end" role="button" tabindex="0"
                  @click="toggleSort('msrp')" @keydown.enter="toggleSort('msrp')">
                  建議售價 (USD)
                  <i v-if="sortBy === 'msrp'" class="bi ms-1"
                    :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th class="text-nowrap">玩家頁面</th>
                <th class="pe-3">說明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="10" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="10" class="text-center py-4">
                  <span class="text-warning">
                    <i class="bi bi-exclamation-triangle me-1"></i>讀取艦船資料失敗。
                  </span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!vehicles.length">
                <td colspan="10" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的艦船。' : '尚無艦船資料 —— 請先在「系統設定 → 資料同步」跑一次同步。' }}
                </td>
              </tr>
              <template v-else>
                <template v-for="v in vehicles" :key="v._id">
                <tr>
                  <td class="ps-3">
                    <span class="fw-semibold">{{ v.name }}</span>
                    <span v-if="v.name_zh" class="ms-1">（{{ v.name_zh }}）</span>
                    <span v-if="v?.system_note" class="badge bg-info text-dark ms-1" title="系統說明：同名變體的區別">{{ v.system_note }}</span>
                    <span v-if="v.class_name" class="small text-muted ms-1">{{ v.class_name }}</span>
                  </td>
                  <td class="small">{{ v.manufacturer_name || v.manufacturer_code || '—' }}</td>
                  <td class="small">{{ v.career || '—' }}</td>
                  <td class="small">{{ v.role_zh ? `${v.role_zh}（${v.role}）` : (v.role || '—') }}</td>
                  <td class="text-end small">{{ v.size_class ?? '—' }}</td>
                  <td class="text-end small">{{ crewLabel(v) }}</td>
                  <td class="text-end small">{{ fmtNum(v.cargo_capacity_scu) }}</td>
                  <td class="text-end small">{{ fmtNum(v.mass_hull) }}</td>
                  <td class="text-end small">{{ v.msrp ? '$' + fmtNum(v.msrp) : '—' }}</td>
                  <td><PlayerVisibleToggle dataset="vehicles" :doc-id="v._id" :row="v" /></td>
                  <td class="pe-3 small note-cell">
                    <span v-if="v.note" class="note-text" :title="v.note">{{ v.note }}</span>
                    <span v-if="!v.note && !canWrite" class="text-muted">—</span>
                    <button v-if="canWrite && editingId !== v._id" type="button" class="btn btn-link btn-sm p-0 ms-1"
                      :aria-label="`編輯 ${v.name} 的說明`" @click="startEdit(v)">
                      <i class="bi bi-pencil"></i>
                    </button>
                  </td>
                </tr>
                <tr v-if="editingId === v._id">
                  <td colspan="10" class="ps-3 pe-3 py-2 edit-cell">
                    <label class="form-label small fw-semibold mb-1" :for="`note-${v._id}`">說明</label>
                    <textarea :id="`note-${v._id}`" v-model="noteDraft" class="form-control form-control-sm" rows="3"
                      :maxlength="NOTE_MAX"></textarea>
                    <div class="small text-muted text-end">{{ noteDraft.length }} / {{ NOTE_MAX }}</div>
                    <div class="d-flex align-items-center gap-2 mt-2">
                      <button type="button" class="btn btn-primary btn-sm" :disabled="savingNote"
                        @click="saveNote(v)">儲存</button>
                      <button type="button" class="btn btn-outline-secondary btn-sm" :disabled="savingNote"
                        @click="editingId = ''">取消</button>
                      <span v-if="noteError" class="small text-danger">{{ noteError }}</span>
                    </div>
                  </td>
                </tr>
                </template>
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

    <FleetOwnersBrowser v-show="tab === 'owned'" :active="tab === 'owned'" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { vehicleApi } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import PlayerVisibleToggle from '@/components/PlayerVisibleToggle.vue'
import FleetOwnersBrowser from '@/components/FleetOwnersBrowser.vue'
import { useAuthStore } from '@/stores/auth'

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
const playerVisible = ref('')
// 分頁：艦船資料庫／玩家擁有艦船（components/FleetOwnersBrowser.vue）
const tab = ref('master')

// ── 手寫說明（玩家頁的艦隊、持有船艦、批量登記會顯示）──
const NOTE_MAX = 1000
const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')
const editingId = ref('')
const noteDraft = ref('')
const savingNote = ref(false)
const noteError = ref('')

function startEdit(v) {
  editingId.value = v._id
  noteDraft.value = v.note || ''
  noteError.value = ''
}


async function saveNote(v) {
  savingNote.value = true
  noteError.value = ''
  const res = await vehicleApi.setNote(v._id, noteDraft.value)
  const body = res ? await res.json().catch(() => null) : null
  if (!(res?.ok && body?.success)) {
    noteError.value = body?.message || '儲存失敗'
    savingNote.value = false
    return
  }
  v.note = body.data.note
  editingId.value = ''
  savingNote.value = false
}

const hasActiveFilters = computed(() =>
  selectedCareers.value.length || selectedRoles.value.length ||
  selectedManufacturers.value.length || selectedSizeClasses.value.length || nameQuery.value
  || playerVisible.value)

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
  playerVisible.value = ''
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
    player_visible: playerVisible.value,
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
.note-cell { max-width: 16rem; }
.note-text { display: inline-block; max-width: 14rem; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; vertical-align: bottom; }
.edit-cell { background: var(--bs-tertiary-bg); }
</style>
