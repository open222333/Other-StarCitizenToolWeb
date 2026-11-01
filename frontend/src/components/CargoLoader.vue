<!--
  玩家頁「貨艙網格」：選幾艘船，填各種大小的貨櫃數量（1／2／4／8／16／24／32 SCU），
  按「裝載」把貨櫃擺進船的貨物網格（utils/cargoPack.js），右邊 3D 檢視（components/CargoView3D.vue）。
  「自動裝滿」用最大的貨櫃把網格塞滿並回填數量。網格資料：GET /starmap/nav/cargo-grids（sc-cargo.space）。
  船與數量記在這台瀏覽器（localStorage）。
-->
<template>
  <div>
    <SfState :loading="loading" :error="error" :empty="loaded && !ships.length" empty-text="尚無貨物網格資料。"
      @retry="load">
      <div class="row g-3">
        <div class="col-12 col-lg-4">
          <div :class="[cardClass, 'sf-search', 'mb-3']">
            <div class="card-body">
              <label class="form-label small fw-semibold mb-1" for="cl-add">加入船</label>
              <AutocompleteField id="cl-add" v-model="addText" :search="searchShips" :get-label="shipLabel"
                :get-meta="shipMeta" :min-chars="0" :debounce-ms="0" aria-label="加入船" @select="addShip" />
              <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
                <button v-if="fleetShips.length" type="button" class="btn btn-sm btn-success"
                  :disabled="vehicles.length >= MAX_VEHICLES" @click="addFleet">
                  <i class="bi bi-plus-lg me-1"></i>加入機庫的船</button>
                <span v-if="vehicles.length" class="sf-chip sf-chip--accent ms-auto">
                  全部 {{ fmtNum(totalLoaded) }} / {{ fmtNum(totalCapacity) }} SCU</span>
              </div>
            </div>
          </div>

          <div v-for="(v, i) in vehicles" :key="v.key" :class="[cardClass, 'mb-3', 'cl-ship']">
            <div class="card-body">
              <div class="d-flex align-items-center gap-2 mb-2">
                <div class="flex-grow-1 min-w-0">
                  <div class="fw-semibold text-truncate">{{ shipLabel(shipOf(v)) }}</div>
                  <div class="cl-muted">{{ shipOf(v)?.manufacturer }}</div>
                </div>
                <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除 ${shipLabel(shipOf(v))}`"
                  @click="vehicles.splice(i, 1)"><i class="bi bi-trash"></i></button>
              </div>
              <select v-if="shipOf(v)?.unofficial" v-model="v.layout" class="form-select form-select-sm mb-2"
                :aria-label="`${shipLabel(shipOf(v))} 版面`" @change="v.applied = null">
                <option value="official">官方網格</option>
                <option value="unofficial">含非官方空間</option>
              </select>
              <div class="d-flex justify-content-between cl-cap">
                <span>容量</span>
                <span class="fw-semibold">{{ fmtNum(resultOf(v)?.scu || 0) }} / {{ fmtNum(capacityOf(v)) }} SCU</span>
              </div>
              <div class="progress cl-bar mb-2" role="progressbar" :aria-valuenow="resultOf(v)?.scu || 0"
                aria-valuemin="0" :aria-valuemax="capacityOf(v)">
                <div class="progress-bar" :style="{ width: `${pct(v)}%` }"></div>
              </div>
              <div class="row g-2">
                <div v-for="s in SIZES" :key="s" class="col-6 col-sm-3 col-lg-6">
                  <div class="input-group input-group-sm">
                    <span class="input-group-text cl-size"><i class="cl-dot" :style="{ background: COLORS[s] }"></i>{{ s }}</span>
                    <input v-model.number="v.counts[s]" type="number" min="0" step="1" class="form-control"
                      :aria-label="`${shipLabel(shipOf(v))} ${s} SCU 貨櫃數量`">
                  </div>
                </div>
              </div>
              <div v-if="leftText(v)" class="sf-chip sf-chip--warn mt-2">放不下：{{ leftText(v) }}</div>
              <div class="d-flex flex-wrap gap-2 mt-2">
                <button type="button" class="btn btn-sm btn-primary" @click="apply(v)">
                  <i class="bi bi-box-arrow-in-down me-1"></i>裝載</button>
                <button type="button" class="btn btn-sm btn-info" @click="fill(v)">
                  <i class="bi bi-magic me-1"></i>自動裝滿</button>
                <button type="button" class="btn btn-sm btn-warning ms-auto" @click="reset(v)">
                  <i class="bi bi-eraser me-1"></i>清除</button>
              </div>
            </div>
          </div>
        </div>

        <!-- 手機上 3D 檢視放最上面 -->
        <div class="col-12 col-lg-8 order-first order-lg-last">
          <div :class="[cardClass, 'cl-view']">
            <div class="card-body p-2">
              <CargoView3D v-if="viewShips.length" :ships="viewShips" />
              <div v-else class="cl-muted text-center py-5">加入船之後在這裡顯示貨艙</div>
            </div>
          </div>
        </div>
      </div>
    </SfState>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AutocompleteField from '@/components/AutocompleteField.vue'
import CargoView3D from '@/components/CargoView3D.vue'
import SfState from '@/components/SfState.vue'
import { SIZES, autoFill, gridCapacity, packCounts } from '@/utils/cargoPack'
import { fmtNum } from '@/utils/navFormat'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card' },
  fleetUuids: { type: Array, default: () => [] },
})

const COLORS = { 1: '#8fa3b8', 2: '#d88cb0', 4: '#7fc69a', 8: '#e3b65c', 16: '#6fa8e6', 24: '#ad94e0', 32: '#c3cbd6' }
const MAX_VEHICLES = 6
const STORAGE_KEY = 'sc_cargo_loader_v1'

// ── 網格資料 ──
const ships = ref([])
const loading = ref(false)
const error = ref('')
const loaded = ref(false)
async function load() {
  loading.value = true
  error.value = ''
  const res = await props.fetcher('/starmap/nav/cargo-grids')
  const body = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!res?.ok || !body?.success) {
    error.value = '讀取失敗。'
    return
  }
  ships.value = body.data || []
  loaded.value = true
}
watch(() => props.active, on => { if (on && !loaded.value && !loading.value) load() }, { immediate: true })

const byId = computed(() => new Map(ships.value.map(s => [s.id, s])))
const fleetSet = computed(() => new Set(props.fleetUuids))
const inFleet = s => (s.vehicle_uuids || []).some(u => fleetSet.value.has(u))
const fleetShips = computed(() => ships.value.filter(inFleet))

const shipLabel = s => (!s ? '' : s.name_zh && s.name_zh !== s.name ? `${s.name_zh}（${s.name}）` : s.name)
const shipMeta = s => [inFleet(s) ? '我的機庫' : '', `${fmtNum(s.capacity)} SCU`].filter(Boolean).join(' · ')
const addText = ref('')
async function searchShips(q) {
  const t = (q || '').trim().toLowerCase()
  const rows = ships.value.filter(s => !t || [s.name, s.name_zh, s.manufacturer, ...(s.aliases || [])]
    .some(x => (x || '').toLowerCase().includes(t)))
  rows.sort((a, b) => inFleet(b) - inFleet(a))
  return rows.slice(0, 40)
}

// ── 加入的船（記在這台瀏覽器）──
let keySeq = 0
const emptyCounts = () => Object.fromEntries(SIZES.map(s => [s, 0]))
const newVehicle = (v = {}) => ({ key: ++keySeq, id: v.id, layout: v.layout === 'unofficial' ? 'unofficial' : 'official',
  counts: { ...emptyCounts(), ...(v.counts || {}) }, applied: v.applied || null })
function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') || []
  } catch {
    return []
  }
}
const vehicles = reactive((Array.isArray(loadSaved()) ? loadSaved() : []).slice(0, MAX_VEHICLES).map(newVehicle))
watch(vehicles, () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(vehicles.map(v => ({ id: v.id, layout: v.layout,
      counts: v.counts, applied: v.applied }))))
  } catch { /* 存不了就算了 */ }
}, { deep: true })

function addShip(s) {
  if (!s || vehicles.length >= MAX_VEHICLES) return
  vehicles.push(newVehicle({ id: s.id }))
  addText.value = ''
}
function addFleet() {
  for (const s of fleetShips.value) {
    if (vehicles.length >= MAX_VEHICLES) break
    if (!vehicles.some(v => v.id === s.id)) vehicles.push(newVehicle({ id: s.id }))
  }
}

const shipOf = v => byId.value.get(v.id) || null
const gridsOf = v => shipOf(v)?.[v.layout]?.grids || shipOf(v)?.official?.grids || []
const capacityOf = v => gridCapacity(gridsOf(v))

// 裝載結果：按「裝載」時的數量（applied）擺出來；網格資料載入前沒有結果
const results = computed(() => new Map(vehicles.map(v => [v.key,
  v.applied && shipOf(v) ? packCounts(gridsOf(v), v.applied) : null])))
const resultOf = v => results.value.get(v.key)
const pct = v => Math.min(100, ((resultOf(v)?.scu || 0) / (capacityOf(v) || 1)) * 100)
function leftText(v) {
  const left = resultOf(v)?.left || {}
  return SIZES.filter(s => left[s]).reverse().map(s => `${s} SCU × ${left[s]}`).join('、')
}

function apply(v) {
  v.applied = { ...v.counts }
}
function fill(v) {
  const r = autoFill(gridsOf(v))
  v.counts = { ...emptyCounts(), ...r.counts }
  v.applied = { ...v.counts }
}
function reset(v) {
  v.counts = emptyCounts()
  v.applied = null
}

const totalLoaded = computed(() => vehicles.reduce((a, v) => a + (resultOf(v)?.scu || 0), 0))
const totalCapacity = computed(() => vehicles.reduce((a, v) => a + capacityOf(v), 0))

const viewShips = computed(() => vehicles.filter(shipOf).map(v => ({
  id: `${v.key}-${v.layout}`,
  label: `${shipOf(v).name_zh || shipOf(v).name}（${fmtNum(capacityOf(v))}）`,
  grids: gridsOf(v),
  boxes: resultOf(v)?.boxes || [],
})))
</script>

<style scoped>
.cl-muted { color: var(--sf-text-muted); }
.cl-cap { font-size: 1rem; color: var(--sf-text-muted); }
.cl-bar { height: .6rem; background: var(--sf-chip-bg); }
.cl-bar .progress-bar { background: var(--sf-accent); }
.cl-size { min-width: 3.4rem; gap: .3rem; }
.cl-dot { display: inline-block; width: .7rem; height: .7rem; border-radius: .15rem; }
.min-w-0 { min-width: 0; }
</style>
