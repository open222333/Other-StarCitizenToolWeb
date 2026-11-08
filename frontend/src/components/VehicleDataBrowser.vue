<!--
  玩家頁「艦隊 › 登記船艦資料」：瀏覽載具主檔＋登記到「我的艦隊」（原本的「批量登記」併進來）。

  篩選用「艦隊」分頁頂端的共用搜尋卡（MyPlayerView 傳進 filters：{ q, types, sizes, manufacturers, roles,
  acquire（取得方式：buy 可用遊戲幣購買／rent 可租船）}），
  跟「我的艦隊」同一組條件。資料是 GET /item/vehicles?with_prices=1（後端分頁），每筆帶 uex_price
  （遊戲內最低購買價／租船價與地點數）；官網現金價是 msrp（美金）。

  每一列：勾選框（批量登記）＋船名、類型、尺寸、廠商、角色、價格＋「登記」按鈕（登記 1 艘）。
  點船名展開：載員、貨艙、質量、價格＋購買／租船地點（components/VehiclePriceDetail.vue）。
  已經在我的艦隊裡的標「已登記」且不能再勾／再登記——要多登記幾艘請到我的艦隊改數量；
  後端也會再擋一次（Fleet.bulk_create_for_player）。已登記清單由父層傳進來（registeredUuids，
  就是我的艦隊的 vehicle_uuid），登記完 emit('registered') 讓父層重抓艦隊。
  列表外觀跟「我的艦隊」一致：卡片＋hover 表格＋表頭排序，「詳細」展開船艦資訊與價格（手機是底部面板）。
-->
<template>
  <!-- 換頁載入中保留舊的列（只變淡），不讓頁面瞬間變短；變短會讓瀏覽器把畫面捲到下面去 -->
  <div ref="rootEl" class="sf-scroll-anchor" :class="{ 'sf-list-loading': loading }">
    <div v-if="message" :class="['alert', 'py-2', messageType]">{{ message }}</div>

    <SfState :loading="loading && !rows.length" :error="loadFailed ? '讀取船艦資料失敗。' : ''" :empty="!rows.length"
      empty-text="沒有符合條件的船艦。" @retry="reload(offset)">
      <!-- 列表外觀跟「我的艦隊」一致：卡片＋hover 表格＋表頭排序（後端排序）；第一欄勾選（批量登記），最後一欄「詳細」「登記」 -->
      <SortSelect v-if="isPhone" class="mb-2" :sort="sort" :options="SORT_OPTIONS" />
      <div class="card scifi-card">
      <div class="card-body p-0">
      <div style="overflow-x: auto">
      <table class="table table-hover align-middle mb-0 sf-stack">
        <thead class="table-light">
          <tr>
            <th class="ps-3 vdb-check-col">
              <input class="form-check-input" type="checkbox" aria-label="全選本頁"
                :checked="allSelectableChecked" :indeterminate.prop="someSelectableChecked && !allSelectableChecked"
                :disabled="!selectableRows.length" @change="togglePage($event.target.checked)">
            </th>
            <SortTh :sort="sort" field="name">船艦</SortTh>
            <th class="d-none d-md-table-cell">類型</th>
            <SortTh :sort="sort" field="size_class" class="d-none d-lg-table-cell">尺寸</SortTh>
            <th class="d-none d-lg-table-cell">廠商</th>
            <th class="d-none d-xl-table-cell">角色</th>
            <SortTh :sort="sort" field="cargo_capacity_scu" class="text-end">載貨</SortTh>
            <SortTh :sort="sort" field="msrp" class="text-end">美金</SortTh>
            <SortTh :sort="sort" field="auec" class="text-end">遊戲幣</SortTh>
            <SortTh :sort="sort" field="rent" class="text-end d-none d-xl-table-cell">租用</SortTh>
            <SortTh :sort="sort" field="auec_per_usd" class="text-end d-none d-xxl-table-cell">aUEC／美金</SortTh>
            <th class="pe-3"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="v in rows" :key="v._id">
          <tr :class="{ 'is-registered': isRegistered(v) }">
            <td class="ps-3 sf-stack__check vdb-check-col">
              <input class="form-check-input" type="checkbox" :checked="selected.has(v._id)"
                :disabled="isRegistered(v)" :aria-label="`勾選 ${v.name_zh || v.name}`"
                @change="toggleOne(v._id, $event.target.checked)">
            </td>
            <td class="sf-stack__title">
              <span class="fw-semibold">{{ v.name_zh || v.name }}</span>
              <span v-if="v.name_zh" class="small text-muted ms-1">{{ v.name }}</span>
              <span v-if="v.system_note" class="sf-tree-chip ms-1" title="系統說明：同名變體的區別">{{ v.system_note }}</span>
              <span v-if="isRegistered(v)" class="sf-chip sf-chip--ok ms-1">已登記</span>
            </td>
            <!-- 手機／平板藏次要欄位（「詳細」裡都看得到；手機卡片照樣顯示） -->
            <td class="d-none d-md-table-cell text-nowrap" data-label="類型">{{ vehicleTypeLabel(v.vehicle_type) || '—' }}</td>
            <td class="d-none d-lg-table-cell" data-label="尺寸">{{ vehicleSizeLabel(v.size_class) || '—' }}</td>
            <td class="d-none d-lg-table-cell" data-label="廠商">{{ manufacturerLabel(v.manufacturer_name, v.manufacturer_code) || '—' }}</td>
            <td class="d-none d-xl-table-cell" data-label="角色">{{ vehicleRoleLabel(v.role, v.role_zh) || '—' }}</td>
            <td class="text-end text-nowrap" data-label="載貨">{{ v.cargo_capacity_scu ? `${fmtNum(v.cargo_capacity_scu)} SCU` : '—' }}</td>
            <td class="text-end text-nowrap" data-label="美金">{{ fmtUsd(v.msrp) }}</td>
            <td class="text-end text-nowrap" data-label="遊戲幣">{{ fmtAuec(v.uex_price?.buy_min) }}</td>
            <td class="text-end text-nowrap d-none d-xl-table-cell" data-label="租用">{{ fmtAuec(v.uex_price?.rent_min) }}</td>
            <td class="text-end text-nowrap d-none d-xxl-table-cell" data-label="aUEC／美金">{{ fmtAuecPerUsd(auecPerUsd(v)) }}</td>
            <td class="text-end text-nowrap pe-3 sf-stack__actions">
              <button type="button" class="btn btn-sm btn-info me-2" :aria-expanded="openId === v._id ? 'true' : 'false'"
                @click="openId = openId === v._id ? '' : v._id">
                <i class="bi me-1" :class="openId === v._id ? 'bi-chevron-up' : 'bi-chevron-down'"></i>詳細
              </button>
              <button v-if="!isRegistered(v)" type="button" class="btn btn-sm btn-success"
                :disabled="submitting" :aria-label="`登記 ${v.name_zh || v.name} 到我的艦隊`" @click="register([v._id], 1)">
                <i class="bi bi-plus-lg me-1"></i>登記
              </button>
            </td>
          </tr>
          <tr v-if="openId === v._id" class="sf-stack__detail">
            <!-- colspan 跟 thead 欄數一致（12）；手機上這一列變成底部面板 -->
            <td colspan="12" class="vdb-detail">
              <div class="sf-sheet__head sf-stack__sheet-head">
                <h3 class="sf-sheet__title">{{ v.name_zh || v.name }}</h3>
                <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="openId = ''"><i class="bi bi-x-lg"></i></button>
              </div>
              <div class="vdb-grid">
                <div v-for="f in infoFields(v)" :key="f.label" class="vdb-field">
                  <span class="vdb-field__label">{{ f.label }}</span>
                  <span class="vdb-field__value">{{ f.value }}</span>
                </div>
              </div>
              <div v-if="v.note" class="sf-tree-info vdb-note">{{ v.note }}</div>
              <VehiclePriceDetail :vehicle-uuid="v._id" :fetcher="fetcher" player />
            </td>
          </tr>
          </template>
        </tbody>
      </table>
      </div>
      </div>
      </div>
      <SfPager v-if="total !== null" class="mt-2" :total="total" :offset="offset" :limit="limit" :loading="loading" @page="goPage" />
      <!-- 總數未知（只打關鍵字時）SfPager 算不出下一頁，用自己的 -->
      <div v-else class="d-flex align-items-center justify-content-between mt-2">
        <span class="sf-pager__info vdb-pager-info">第 {{ offset + 1 }}–{{ offset + rows.length }} 筆</span>
        <div class="btn-group">
          <button class="btn btn-sm btn-primary" :disabled="offset === 0 || loading"
            @click="goPage(Math.max(0, offset - limit))">上一頁</button>
          <button class="btn btn-sm btn-primary" :disabled="!hasNext || loading"
            @click="goPage(offset + limit)">下一頁</button>
        </div>
      </div>
    </SfState>

    <!-- ── 批量登記列（有勾選才出現；勾選跨頁保留）──────────────── -->
    <!-- sf-sticky-bar：手機上固定在畫面底部 -->
    <div v-if="selected.size" class="card scifi-card sf-search mt-3 vdb-submit sf-sticky-bar">
      <div class="card-body">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <span class="fw-semibold">已選 {{ selected.size }} 款</span>
          <button type="button" class="btn btn-sm btn-warning" @click="selected.clear()">清除勾選</button>
          <span class="flex-grow-1"></span>
          <label class="small mb-0" :for="`${uid}-qty`">每款</label>
          <input :id="`${uid}-qty`" v-model.number="quantity" type="number" min="1" :max="maxQuantity"
            class="form-control form-control-sm" style="width: 5rem">
          <span class="small">艘</span>
          <button type="button" class="btn btn-sm btn-success" :disabled="submitting || selected.size > maxBulk"
            @click="register([...selected], quantity)">
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
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { scrollToListTop } from '@/utils/scrollAnchor'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import SfPager from '@/components/SfPager.vue'
import SfState from '@/components/SfState.vue'
import VehiclePriceDetail from '@/components/VehiclePriceDetail.vue'
import { useTableSort } from '@/composables/useTableSort'
import { fmtAuec, fmtUsd, auecPerUsd, fmtAuecPerUsd, vehicleRangeParams } from '@/utils/uexCommodity'
import { manufacturerLabel, vehicleRoleLabel, vehicleSizeLabel, vehicleTypeLabel } from '@/utils/vehicle'

const props = defineProps({
  /** 帶身分的 fetch（玩家頁傳 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /** 「艦隊」分頁頂端共用搜尋卡的條件 */
  filters: { type: Object, default: () => ({}) },
  /** 已經在我的艦隊裡的載具 uuid（標「已登記」、不能再勾） */
  registeredUuids: { type: Array, default: () => [] },
  /** 點開才載入（玩家頁用 v-show 一直掛著） */
  active: { type: Boolean, default: true },
})
const emit = defineEmits(['registered'])

// 跟後端的 MAX_BULK_VEHICLES／MAX_QUANTITY 一致
const maxBulk = 200
const maxQuantity = 99
const uid = `vdb-${Math.random().toString(36).slice(2, 8)}`

const limit = 30
const rows = ref([])
const total = ref(0)   // null＝總數未知（只打關鍵字時，見 app/item/view.py 的 list_vehicles）
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const openId = ref('')

const hasNext = computed(() => (total.value === null
  ? rows.value.length >= limit
  : offset.value + limit < total.value))

// ── 登記 ──────────────────────────────────────────────────────
const registeredSet = computed(() => new Set(props.registeredUuids))
const isRegistered = v => registeredSet.value.has(v._id)
/** 勾選中的 uuid，跨頁保留 */
const selected = reactive(new Set())
const quantity = ref(1)
const submitting = ref(false)
const message = ref('')
const messageType = ref('alert-success')

const selectableRows = computed(() => rows.value.filter(v => !isRegistered(v)))
const allSelectableChecked = computed(() =>
  selectableRows.value.length > 0 && selectableRows.value.every(v => selected.has(v._id)))
const someSelectableChecked = computed(() => selectableRows.value.some(v => selected.has(v._id)))

function toggleOne(id, checked) {
  if (checked) selected.add(id)
  else selected.delete(id)
}

function togglePage(checked) {
  for (const v of selectableRows.value) {
    if (checked) selected.add(v._id)
    else selected.delete(v._id)
  }
}

// 別處（JSON 匯入、我的艦隊刪除）改了艦隊，已登記的就不該還勾著
watch(registeredSet, (set) => { for (const id of [...selected]) if (set.has(id)) selected.delete(id) })

let flashTimer = null
function flash(text, type = 'alert-success') {
  message.value = text
  messageType.value = type
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => { message.value = '' }, 6000)
}

async function register(uuids, qtyInput) {
  if (!uuids.length || submitting.value) return
  const qty = Math.max(1, Math.min(maxQuantity, Math.trunc(Number(qtyInput) || 1)))
  submitting.value = true
  try {
    const res = await props.fetcher('/player/fleet/bulk', {
      method: 'POST',
      body: JSON.stringify({ vehicle_uuids: uuids, quantity: qty }),
    })
    if (!res) { flash('網路錯誤，請稍後再試', 'alert-warning'); return }
    const data = await res.json().catch(() => null)
    if (!res.ok || !data?.success) {
      flash(data?.message || '登記失敗，請稍後再試', 'alert-warning')
      return
    }
    // 誠實回報：跳過與查不到的也要講
    const parts = [`新增 ${data.added} 款`]
    if (data.skipped) parts.push(`跳過 ${data.skipped} 款（已登記過）`)
    if (data.not_found) parts.push(`${data.not_found} 款在主檔查不到`)
    flash(parts.join('，'), data.added ? 'alert-success' : 'alert-warning')
    uuids.forEach(id => selected.delete(id))
    quantity.value = 1
    emit('registered', data)
  } finally {
    submitting.value = false
  }
}

// ── 列表 ──────────────────────────────────────────────────────
function fmtNum(v) {
  return v === null || v === undefined ? '—' : Math.round(v).toLocaleString('en-US')
}

function crewLabel(v) {
  if (!v.crew_max) return '—'
  return v.crew_min && v.crew_min !== v.crew_max ? `${v.crew_min}–${v.crew_max} 人` : `${v.crew_max} 人`
}

function infoFields(v) {
  const p = v.uex_price || {}
  return [
    { label: '載員', value: crewLabel(v) },
    { label: '載貨', value: v.cargo_capacity_scu ? `${fmtNum(v.cargo_capacity_scu)} SCU` : '—' },
    { label: '質量', value: v.mass_hull ? `${fmtNum(v.mass_hull)} kg` : '—' },
    { label: '官網售價', value: fmtUsd(v.msrp) },
    { label: '遊戲內購買', value: p.buy_min ? `${fmtAuec(p.buy_min)} 起（${p.buy_count} 處）` : '—' },
    { label: 'aUEC／美金', value: fmtAuecPerUsd(auecPerUsd(v)) },
    { label: '租船', value: p.rent_min ? `${fmtAuec(p.rent_min)} 起（${p.rent_count} 處）` : '—' },
  ]
}

// 欄位名稱＋排序（後端 /item/vehicles 的 sort_by：船名、尺寸、貨艙、美金、遊戲幣、租用、aUEC／美金）
// 手機沒有表頭，另外給排序下拉（後端排序欄位）
const SORT_OPTIONS = [
  { field: 'name', label: '船艦' }, { field: 'size_class', label: '尺寸' }, { field: 'cargo_capacity_scu', label: '載貨' },
  { field: 'msrp', label: '美金' }, { field: 'auec', label: '遊戲幣' }, { field: 'rent', label: '租用' },
  { field: 'auec_per_usd', label: 'aUEC／美金' },
]
const { isPhone } = useBreakpoint()
const sort = useTableSort(null, { onChange: () => reload(0) })

let seq = 0
async function reload(nextOffset = 0) {
  offset.value = Math.max(0, nextOffset)
  loading.value = true
  loadFailed.value = false
  const mine = ++seq
  const f = props.filters || {}
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset.value), with_prices: '1' })
  if (f.q) params.set('q', f.q)
  ;(f.types || []).forEach(v => params.append('type', v))
  ;(f.sizes || []).forEach(v => params.append('size_class', v))
  ;(f.manufacturers || []).forEach(v => params.append('manufacturer_code', v))
  ;(f.roles || []).forEach(v => params.append('role', v))
  ;(f.acquire || []).forEach(v => params.append('acquire', v))
  for (const [k, v] of Object.entries(vehicleRangeParams(f))) params.set(k, v)
  for (const [k, v] of Object.entries(sort.params.value)) params.set(k, v)
  const res = await props.fetcher(`/item/vehicles?${params.toString()}`)
  const data = res ? await res.json().catch(() => null) : null
  if (mine !== seq) return
  loading.value = false
  if (!data?.success) {
    rows.value = []
    total.value = 0
    loadFailed.value = true
    return
  }
  rows.value = data.data || []
  total.value = data.total ?? null
  openId.value = ''
}

let loaded = false
let timer = null
watch(() => props.active, (v) => {
  if (!v || loaded) return
  loaded = true
  reload(0)
}, { immediate: true })
// 共用搜尋卡每打一個字就會換一次 filters，等停手 300ms 再查；還沒展開過就先不查
watch(() => props.filters, () => {
  if (!loaded) return
  clearTimeout(timer)
  timer = setTimeout(() => reload(0), 300)
}, { deep: true })
onBeforeUnmount(() => { clearTimeout(timer); clearTimeout(flashTimer) })

defineExpose({ refresh: () => { if (loaded) reload(offset.value) } })

// 上一頁／下一頁：載入後把列表頂端捲回畫面（不然會停在最下方的分頁按鈕，見 utils/scrollAnchor.js）
const rootEl = ref(null)
async function goPage(newOffset) {
  await reload(newOffset)
  scrollToListTop(rootEl.value)
}
</script>

<style scoped>
.vdb-check-col { width: 2.5rem; }
.is-registered > td:not(.sf-stack__actions) { opacity: .7; }
.vdb-detail { background: var(--sf-panel-2); }
.vdb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: .35rem .75rem;
  margin-bottom: .6rem;
}
.vdb-field { display: flex; gap: .5rem; font-size: 1rem; }
.vdb-field__label { color: var(--sf-text-muted); white-space: nowrap; }
.vdb-field__value { color: var(--sf-text-strong); font-weight: 600; }
.vdb-note { white-space: pre-line; }
/* 手機上 .sf-sticky-bar 由 scifi-theme.css 固定在底部，這裡只管桌機／平板 */
@media (min-width: 768px) {
  .vdb-submit { position: sticky; bottom: .5rem; z-index: 10; }
}
.vdb-pager-info { font-size: .95rem; color: var(--bs-secondary-color); }
</style>
