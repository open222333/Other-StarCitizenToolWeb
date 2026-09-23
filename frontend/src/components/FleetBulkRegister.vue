<!--
  載具主檔清單 ＋ 勾選批量登記到「我的艦隊」。

  比照 BlueprintBulkRegister.vue：把主檔列出來（可依名稱／類型／尺寸／
  廠商／角色篩選、分頁），勾選後一次送出。已經登記過的款式標成「已登記」
  且不能再勾——要多登記幾艘請到「我的艦隊」改數量。後端也會再擋一次
  （見 Fleet.bulk_create_for_player），因為畫面上的資料可能已經過時。
-->
<template>
  <div>
    <!-- ── 篩選 ────────────────────────────────────────────── -->
    <div :class="[cardClass, 'mb-3']">
      <div class="card-body">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-4">
            <label class="form-label small fw-semibold" :for="`${uid}-q`">名稱關鍵字</label>
            <input :id="`${uid}-q`" v-model="keyword" type="text" class="form-control form-control-sm"
              placeholder="例如 Cutlass、Cyclone" @input="onKeywordInput">
          </div>
          <div class="col-6 col-md-2">
            <label class="form-label small fw-semibold" :for="`${uid}-type`">類型</label>
            <select :id="`${uid}-type`" v-model="vehicleType" class="form-select form-select-sm"
              @change="reload(0)">
              <option value="">全部</option>
              <option v-for="t in facets.types" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
          </div>
          <div class="col-6 col-md-2">
            <label class="form-label small fw-semibold" :for="`${uid}-size`">尺寸</label>
            <select :id="`${uid}-size`" v-model="size" class="form-select form-select-sm"
              @change="reload(0)">
              <option value="">全部</option>
              <option v-for="s in facets.size_classes" :key="s" :value="String(s)">{{ vehicleSizeLabel(s) }}</option>
            </select>
          </div>
          <div class="col-6 col-md-2">
            <label class="form-label small fw-semibold" :for="`${uid}-mfr`">廠商</label>
            <select :id="`${uid}-mfr`" v-model="manufacturer" class="form-select form-select-sm"
              @change="reload(0)">
              <option value="">全部</option>
              <option v-for="m in facets.manufacturers" :key="m.value" :value="m.value">
                {{ manufacturerLabel(m.label, m.value) }}
              </option>
            </select>
          </div>
          <div class="col-6 col-md-2">
            <label class="form-label small fw-semibold" :for="`${uid}-role`">角色</label>
            <select :id="`${uid}-role`" v-model="role" class="form-select form-select-sm"
              @change="reload(0)">
              <option value="">全部</option>
              <option v-for="r in facets.roles" :key="r" :value="r">{{ r }}</option>
            </select>
          </div>
        </div>
        <div v-if="hasFilter" class="text-end mt-2">
          <button type="button" class="btn btn-sm btn-link p-0" @click="clearFilters">清除篩選</button>
        </div>
      </div>
    </div>

    <div v-if="message" :class="['alert', 'py-2', messageType]">{{ message }}</div>

    <!-- ── 清單 ────────────────────────────────────────────── -->
    <div :class="cardClass">
      <div class="card-body p-0">
        <div style="overflow-x: auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th style="width: 3rem" class="ps-3">
                  <input class="form-check-input" type="checkbox"
                    :checked="allSelectableChecked" :disabled="!selectableRows.length"
                    :indeterminate="someSelectableChecked && !allSelectableChecked"
                    aria-label="全選本頁" @change="togglePage($event.target.checked)">
                </th>
                <th>載具</th>
                <th>類型</th>
                <th>尺寸</th>
                <th>廠商</th>
                <th class="pe-3">角色</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="6" class="text-center py-4 hint">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中…
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="6" class="text-center py-4">
                  <span class="text-warning">
                    <i class="bi bi-exclamation-triangle me-1"></i>讀取載具清單失敗。
                  </span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="6" class="text-center py-4 hint">
                  {{ hasFilter
                     ? '沒有符合條件的載具，換個條件看看。'
                     : '載具主檔還是空的 —— 請先在後台「資料同步排程」跑一次遊戲資料同步。' }}
                </td>
              </tr>
              <tr v-for="row in rows" :key="row._id"
                :class="{ 'row-registered': registered.has(row._id) }">
                <td class="ps-3">
                  <input class="form-check-input" type="checkbox"
                    :checked="selected.has(row._id)"
                    :disabled="registered.has(row._id)"
                    :aria-label="`勾選 ${row.name}`"
                    @change="toggleOne(row._id, $event.target.checked)">
                </td>
                <td>
                  <span class="fw-semibold">{{ row.name }}</span>
                  <span v-if="registered.has(row._id)" class="badge bg-secondary ms-1">已登記</span>
                </td>
                <td class="small">{{ vehicleTypeLabel(row.vehicle_type) }}</td>
                <td class="small">{{ vehicleSizeLabel(row.size_class) }}</td>
                <td class="small">{{ manufacturerLabel(row.manufacturer_name, row.manufacturer_code) }}</td>
                <td class="small pe-3">{{ row.role || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── 分頁 ────────────────────────────────────────────── -->
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-2">
      <div class="small hint">
        <template v-if="total !== null">
          共 {{ total }} 款<span v-if="total"> · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 款</span>
        </template>
        <template v-else-if="rows.length">第 {{ offset + 1 }}–{{ offset + rows.length }} 款</template>
      </div>
      <div class="btn-group btn-group-sm">
        <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading"
          @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-outline-secondary"
          :disabled="!hasNext || loading"
          @click="reload(offset + limit)">下一頁</button>
      </div>
    </div>

    <!-- ── 送出列（有勾選才出現）────────────────────────────── -->
    <div v-if="selected.size" :class="[cardClass, 'mt-3', 'sticky-submit']">
      <div class="card-body">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <span class="fw-semibold">已選 {{ selected.size }} 款</span>
          <button class="btn btn-sm btn-link p-0" @click="clearSelection">清除勾選</button>
          <span class="flex-grow-1"></span>
          <label class="small mb-0" :for="`${uid}-qty`">每款</label>
          <input :id="`${uid}-qty`" v-model.number="quantity" type="number" min="1" :max="maxQuantity"
            class="form-control form-control-sm" style="width: 5rem">
          <span class="small">艘</span>
          <button class="btn btn-scifi btn-sm" :disabled="submitting" @click="submit">
            <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
            登記這 {{ selected.size }} 款
          </button>
        </div>
        <div v-if="selected.size > maxBulk" class="small text-danger mt-1">
          一次最多 {{ maxBulk }} 款，請先取消一些。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { manufacturerLabel, vehicleSizeLabel, vehicleTypeLabel } from '@/utils/vehicle'

const props = defineProps({
  /** 帶身分的 fetch（玩家頁傳 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  cardClass: { type: String, default: 'card shadow-sm border-0' },
})
const emit = defineEmits(['registered'])

// 跟後端的 MAX_BULK_VEHICLES／MAX_QUANTITY 一致
const maxBulk = 200
const maxQuantity = 99

const uid = `fleetbulk-${Math.random().toString(36).slice(2, 8)}`

const rows = ref([])
const total = ref(0)   // null＝總數未知（只打關鍵字時）
const limit = ref(50)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const facets = ref({ size_classes: [], types: [], manufacturers: [], roles: [] })

const keyword = ref('')
const vehicleType = ref('')
const size = ref('')
const manufacturer = ref('')
const role = ref('')
const hasFilter = computed(() => !!(keyword.value.trim() || vehicleType.value || size.value
  || manufacturer.value || role.value))

/** 已登記的載具 uuid */
const registered = reactive(new Set())
/** 勾選中的 uuid，跨頁保留 */
const selected = reactive(new Set())

const submitting = ref(false)
const quantity = ref(1)
const message = ref('')
const messageType = ref('alert-success')

const hasNext = computed(() => (total.value === null
  ? rows.value.length >= limit.value
  : offset.value + limit.value < total.value))

const selectableRows = computed(() => rows.value.filter(r => !registered.has(r._id)))
const allSelectableChecked = computed(() =>
  selectableRows.value.length > 0 && selectableRows.value.every(r => selected.has(r._id)))
const someSelectableChecked = computed(() =>
  selectableRows.value.some(r => selected.has(r._id)))

// ── 載入 ──────────────────────────────────────────────────────
// seq：過期回應防護，理由同 BlueprintBulkRegister.vue
let seq = 0
let keywordTimer = null

async function reload(nextOffset = 0) {
  offset.value = Math.max(0, nextOffset)
  loading.value = true
  const mine = ++seq

  const params = new URLSearchParams({ limit: String(limit.value), offset: String(offset.value) })
  if (keyword.value.trim()) params.set('q', keyword.value.trim())
  if (vehicleType.value) params.set('type', vehicleType.value)
  if (size.value) params.set('size_class', size.value)
  if (manufacturer.value) params.set('manufacturer_code', manufacturer.value)
  if (role.value) params.set('role', role.value)

  const res = await props.fetcher(`/item/vehicles?${params.toString()}`)
  if (mine !== seq) return
  const data = res ? await res.json().catch(() => null) : null
  if (mine !== seq) return

  if (data?.success) {
    rows.value = data.data || []
    // 只打關鍵字（沒有其他篩選）時後端走前綴搜尋，total 回 null 代表「總數
    // 未知」—— 見 app/item/view.py 的 list_vehicles。這時改用「本頁滿了就
    // 還有下一頁」判斷分頁。
    total.value = data.total ?? null
    loadFailed.value = false
  } else {
    rows.value = []
    total.value = 0
    loadFailed.value = true
    flash(data?.message || '讀取載具清單失敗，請稍後再試', 'alert-warning')
  }
  loading.value = false
}

function onKeywordInput() {
  clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => reload(0), 300)
}

function clearFilters() {
  keyword.value = ''
  vehicleType.value = ''
  size.value = ''
  manufacturer.value = ''
  role.value = ''
  reload(0)
}

async function loadRegistered() {
  const res = await props.fetcher('/player/fleet')
  const data = res ? await res.json().catch(() => null) : null
  if (!data?.success) {
    flash('讀不到你已登記的艦隊，「已登記」標記可能不完整，請重新整理。', 'alert-warning')
    return
  }
  registered.clear()
  for (const row of data.data || []) {
    if (row.vehicle_uuid) registered.add(row.vehicle_uuid)
  }
}

async function loadFacets() {
  const res = await props.fetcher('/item/vehicles/facets')
  const data = res ? await res.json().catch(() => null) : null
  if (data?.success) facets.value = { ...facets.value, ...(data.data || {}) }
}

// ── 勾選 ──────────────────────────────────────────────────────

function toggleOne(uuid, checked) {
  if (checked) selected.add(uuid)
  else selected.delete(uuid)
}

function togglePage(checked) {
  for (const row of selectableRows.value) {
    if (checked) selected.add(row._id)
    else selected.delete(row._id)
  }
}

function clearSelection() {
  selected.clear()
}

let flashTimer = null
function flash(text, type = 'alert-success') {
  message.value = text
  messageType.value = type
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => { message.value = '' }, 6000)
}

// ── 送出 ──────────────────────────────────────────────────────

async function submit() {
  if (!selected.size || submitting.value) return
  if (selected.size > maxBulk) {
    flash(`一次最多 ${maxBulk} 款，目前勾了 ${selected.size} 款。`, 'alert-warning')
    return
  }
  const qty = Math.max(1, Math.min(maxQuantity, Math.trunc(Number(quantity.value) || 1)))
  submitting.value = true
  try {
    const res = await props.fetcher('/player/fleet/bulk', {
      method: 'POST',
      body: JSON.stringify({ vehicle_uuids: [...selected], quantity: qty }),
    })
    if (!res) { flash('網路錯誤，請稍後再試', 'alert-warning'); return }
    const data = await res.json().catch(() => null)
    if (!res.ok || !data?.success) {
      flash(data?.message || '登記失敗，請稍後再試', 'alert-warning')
      return
    }

    // 誠實回報：跳過與查不到的也要講
    const parts = [`新增 ${data.added} 款`]
    if (data.skipped) parts.push(`跳過 ${data.skipped} 款（已登記過，要加艘數請到「我的艦隊」改數量）`)
    if (data.not_found) parts.push(`${data.not_found} 款在主檔查不到`)
    flash(parts.join('，'), data.added ? 'alert-success' : 'alert-warning')

    clearSelection()
    quantity.value = 1
    await loadRegistered()
    emit('registered', data)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadFacets()
  loadRegistered()
  reload(0)
})
onBeforeUnmount(() => { clearTimeout(keywordTimer); clearTimeout(flashTimer) })

defineExpose({ refresh: async () => { await loadRegistered(); await reload(offset.value) } })
</script>

<style scoped>
.row-registered > td {
  opacity: .55;
}

.hint {
  opacity: .72;
}

.sticky-submit {
  position: sticky;
  bottom: .5rem;
  z-index: 10;
}
</style>
