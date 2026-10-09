<!--
  玩家頁「艦隊 › 船艦資料」：瀏覽載具主檔＋登記到「我的艦隊」（原本的「批量登記」併進來）。

  篩選用「艦隊」分頁頂端的共用搜尋卡（MyPlayerView 傳進 filters：{ q, types, sizes, manufacturers, roles,
  acquire（取得方式：buy 可用遊戲幣購買／rent 可租船）}），
  跟「我的艦隊」同一組條件。資料是 GET /item/vehicles?with_prices=1（後端分頁），每筆帶 uex_price
  （遊戲內最低購買價／租船價與地點數）；官網現金價是 msrp（美金）。

  每一列：勾選框（批量登記）＋船名、類型、尺寸、廠商、角色、價格＋「登記」按鈕（登記 1 艘）。
  點船名展開：載員、貨艙、質量、價格＋購買／租船地點（components/VehiclePriceDetail.vue）。
  已經在我的艦隊裡的標「已登記」且不能再勾／再登記——要多登記幾艘請到我的艦隊改數量；
  後端也會再擋一次（Fleet.bulk_create_for_player）。已登記清單由父層傳進來（registeredUuids，
  就是我的艦隊的 vehicle_uuid），登記完 emit('registered') 讓父層重抓艦隊。
  樣式用蜂巢式下拉（scifi-theme.css 的 .sf-tree-*）。
-->
<template>
  <div>
    <div v-if="message" :class="['alert', 'py-2', messageType]">{{ message }}</div>

    <div v-if="loading" class="text-muted small">載入中…</div>
    <div v-else-if="loadFailed" class="small">
      <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取船艦資料失敗。</span>
      <button type="button" class="btn btn-sm btn-primary ms-1" @click="reload(offset)">重新整理</button>
    </div>
    <div v-else-if="!rows.length" class="text-muted small">沒有符合條件的船艦。</div>
    <template v-else>
      <div class="vdb-head">
        <input class="form-check-input" type="checkbox" aria-label="全選本頁"
          :checked="allSelectableChecked" :indeterminate.prop="someSelectableChecked && !allSelectableChecked"
          :disabled="!selectableRows.length" @change="togglePage($event.target.checked)">
        <span class="small text-muted">全選本頁</span>
      </div>
      <div v-for="v in rows" :key="v._id" class="vdb-ship" :class="{ 'is-registered': isRegistered(v) }">
        <div class="vdb-row">
          <input class="form-check-input vdb-check" type="checkbox" :checked="selected.has(v._id)"
            :disabled="isRegistered(v)" :aria-label="`勾選 ${v.name_zh || v.name}`"
            @change="toggleOne(v._id, $event.target.checked)">
          <button type="button" class="sf-tree-row sf-tree-row--ship vdb-main"
            :aria-expanded="openId === v._id ? 'true' : 'false'" @click="openId = openId === v._id ? '' : v._id">
            <i class="bi" :class="openId === v._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
            <span class="vdb-name">
              <span class="sf-tree-title">{{ v.name_zh || v.name }}</span>
              <span v-if="v.name_zh" class="text-muted ms-1">{{ v.name }}</span>
              <span v-if="v.system_note" class="sf-tree-chip ms-1" title="系統說明：同名變體的區別">{{ v.system_note }}</span>
            </span>
            <span class="vdb-attrs">
              <span>{{ vehicleTypeLabel(v.vehicle_type) || '—' }}</span>
              <span>{{ vehicleSizeLabel(v.size_class) || '—' }}</span>
              <span>{{ manufacturerLabel(v.manufacturer_name, v.manufacturer_code) || '—' }}</span>
              <span>{{ vehicleRoleLabel(v.role, v.role_zh) || '—' }}</span>
            </span>
            <span class="sf-tree-meta">
              <template v-if="v.msrp">{{ fmtUsd(v.msrp) }}</template>
              <template v-if="v.msrp && v.uex_price?.buy_min"> · </template>
              <template v-if="v.uex_price?.buy_min">{{ fmtAuec(v.uex_price.buy_min) }} 起</template>
            </span>
          </button>
          <span v-if="isRegistered(v)" class="sf-tree-chip vdb-action">已登記</span>
          <button v-else type="button" class="btn btn-sm btn-success vdb-action"
            :disabled="submitting" :aria-label="`登記 ${v.name_zh || v.name} 到我的艦隊`" @click="register([v._id], 1)">
            <i class="bi bi-plus-lg me-1"></i>登記
          </button>
        </div>
        <div v-if="openId === v._id" class="sf-tree-level">
          <div class="vdb-grid">
            <div v-for="f in infoFields(v)" :key="f.label" class="vdb-field">
              <span class="vdb-field__label">{{ f.label }}</span>
              <span class="vdb-field__value">{{ f.value }}</span>
            </div>
          </div>
          <div v-if="v.note" class="sf-tree-info vdb-note">{{ v.note }}</div>
          <VehiclePriceDetail :vehicle-uuid="v._id" :fetcher="fetcher" player />
        </div>
      </div>
      <div class="d-flex align-items-center justify-content-between mt-2">
        <span class="small text-muted">
          <template v-if="total === null">第 {{ offset + 1 }}–{{ offset + rows.length }} 筆</template>
          <template v-else>共 {{ total }} 款 · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</template>
        </span>
        <div class="btn-group">
          <button class="btn btn-sm btn-primary" :disabled="offset === 0 || loading"
            @click="reload(Math.max(0, offset - limit))">上一頁</button>
          <button class="btn btn-sm btn-primary" :disabled="!hasNext || loading"
            @click="reload(offset + limit)">下一頁</button>
        </div>
      </div>
    </template>

    <!-- ── 批量登記列（有勾選才出現；勾選跨頁保留）──────────────── -->
    <div v-if="selected.size" class="card scifi-card sf-search mt-3 vdb-submit">
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
import VehiclePriceDetail from '@/components/VehiclePriceDetail.vue'
import { fmtAuec, fmtUsd } from '@/utils/uexCommodity'
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
    { label: '貨艙', value: v.cargo_capacity_scu ? `${fmtNum(v.cargo_capacity_scu)} SCU` : '—' },
    { label: '質量', value: v.mass_hull ? `${fmtNum(v.mass_hull)} kg` : '—' },
    { label: '官網售價', value: fmtUsd(v.msrp) },
    { label: '遊戲內購買', value: p.buy_min ? `${fmtAuec(p.buy_min)} 起（${p.buy_count} 處）` : '—' },
    { label: '租船', value: p.rent_min ? `${fmtAuec(p.rent_min)} 起（${p.rent_count} 處）` : '—' },
  ]
}

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
</script>

<style scoped>
.vdb-head { display: flex; align-items: center; gap: .5rem; padding: 0 0 .4rem .2rem; }
.vdb-ship { margin-bottom: .4rem; }
.vdb-row { display: flex; align-items: center; gap: .5rem; }
.vdb-check { flex: 0 0 auto; margin: 0 0 0 .2rem; }
.vdb-main { flex: 1 1 auto; min-width: 0; flex-wrap: wrap; }
.vdb-name { min-width: 12rem; }
.vdb-attrs { display: flex; flex-wrap: wrap; gap: .25rem .9rem; color: var(--sf-text); font-size: .95rem; }
.vdb-action { flex: 0 0 auto; white-space: nowrap; }
.is-registered .vdb-main { opacity: .7; }
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
.vdb-submit { position: sticky; bottom: .5rem; z-index: 10; }
</style>
