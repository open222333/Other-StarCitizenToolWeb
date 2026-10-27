<!--
  玩家頁「航線」：量子航行路線規劃（後端 POST /starmap/nav/route，演算法見 src/models/nav.py）。
  起點＋途經站點＋貨運（取貨→送貨、SCU；目前隱藏，見 SHOW_CARGO），可自動排序或照輸入順序，終點可不指定／回到起點／指定地點。
  結果一次給三種方案（最快／最省油／最順路），每一段列出經過的 OM 點、跳躍點。
  表單（地點、船、貨運）記在這台瀏覽器（localStorage）。
-->
<template>
  <div>
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body">
        <SfState :loading="loadingBase" :error="baseError" :empty="baseLoaded && !places.length"
          empty-text="尚無地點座標資料。" @retry="loadBase">
          <div class="row g-2 align-items-end">
            <div class="col-12 col-md-6">
              <label class="form-label small fw-semibold mb-1" for="rp-ship">船</label>
              <AutocompleteField id="rp-ship" v-model="shipText" :search="searchShips" :get-label="shipLabel"
                :get-meta="shipMeta" :min-chars="0" :debounce-ms="0" aria-label="船" @select="pickShip" />
            </div>
            <div class="col-12 col-md-6">
              <div v-if="ship" class="d-flex flex-wrap gap-1 rp-ship-facts">
                <span class="sf-chip">量子速度 {{ fmtSpeed(ship.qt_speed) }}</span>
                <span class="sf-chip">啟動 {{ fmtNum(ship.qt_spool, 1) }} 秒</span>
                <span v-if="ship.qt_fuel_capacity" class="sf-chip">量子油箱 {{ fmtNum(ship.qt_fuel_capacity) }}</span>
                <span v-if="SHOW_CARGO && ship.cargo_scu" class="sf-chip">貨艙 {{ fmtNum(ship.cargo_scu) }} SCU</span>
              </div>
            </div>
            <div class="col-12">
              <label class="form-label small fw-semibold mb-1" for="rp-start">起點</label>
              <PlacePicker id="rp-start" label="起點" :places="places" :model-value="start"
                @update:model-value="v => Object.assign(start, v)" />
            </div>
            <div class="col-12">
              <label class="form-label small fw-semibold mb-1" for="rp-end-mode">終點</label>
              <div class="row g-1">
                <div class="col-12 col-md-3">
                  <select id="rp-end-mode" v-model="endMode" class="form-select form-select-sm">
                    <option value="none">最後一站</option>
                    <option value="start">回到起點</option>
                    <option value="fixed">指定地點</option>
                  </select>
                </div>
                <div v-if="endMode === 'fixed'" class="col-12 col-md-9">
                  <PlacePicker id="rp-end" label="終點" :places="places" :model-value="endPlace"
                    @update:model-value="v => Object.assign(endPlace, v)" />
                </div>
              </div>
            </div>
          </div>

          <div class="mt-3">
            <div class="d-flex align-items-center gap-2 mb-1">
              <span class="small fw-semibold">途經站點</span>
              <button type="button" class="btn btn-sm btn-success ms-auto" :disabled="stops.length >= MAX_STOPS"
                @click="stops.push(newPlace())"><i class="bi bi-plus-lg me-1"></i>加站點</button>
            </div>
            <div v-for="(s, i) in stops" :key="s.key" class="d-flex gap-2 mb-2 align-items-center">
              <span class="rp-index">{{ i + 1 }}</span>
              <div class="flex-grow-1">
                <PlacePicker :id="`rp-stop-${s.key}`" :label="`站點 ${i + 1} `" :places="places" :model-value="s"
                  @update:model-value="v => Object.assign(s, v)" />
              </div>
              <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除站點 ${i + 1}`"
                @click="stops.splice(i, 1)"><i class="bi bi-trash"></i></button>
            </div>
          </div>

          <div v-if="SHOW_CARGO" class="mt-3">
            <div class="d-flex align-items-center gap-2 mb-1">
              <span class="small fw-semibold">貨運</span>
              <button type="button" class="btn btn-sm btn-success ms-auto" :disabled="cargo.length >= MAX_CARGO"
                @click="cargo.push(newCargo())"><i class="bi bi-plus-lg me-1"></i>加貨運</button>
            </div>
            <div v-for="(c, i) in cargo" :key="c.key" class="rp-cargo mb-2">
              <div class="d-flex align-items-center gap-2 mb-1">
                <span class="rp-index">#{{ i + 1 }}</span>
                <div class="input-group input-group-sm rp-scu">
                  <input v-model.number="c.scu" type="number" min="1" step="1" class="form-control"
                    :aria-label="`貨運 ${i + 1} SCU`">
                  <span class="input-group-text">SCU</span>
                </div>
                <button type="button" class="btn btn-sm btn-danger ms-auto" :aria-label="`移除貨運 ${i + 1}`"
                  @click="cargo.splice(i, 1)"><i class="bi bi-trash"></i></button>
              </div>
              <div class="d-flex gap-2 align-items-center mb-1">
                <span class="rp-cargo-tag">取貨</span>
                <div class="flex-grow-1">
                  <PlacePicker :id="`rp-pick-${c.key}`" :label="`貨運 ${i + 1} 取貨`" :places="places"
                    :model-value="c.pickup" @update:model-value="v => Object.assign(c.pickup, v)" />
                </div>
              </div>
              <div class="d-flex gap-2 align-items-center">
                <span class="rp-cargo-tag">送貨</span>
                <div class="flex-grow-1">
                  <PlacePicker :id="`rp-drop-${c.key}`" :label="`貨運 ${i + 1} 送貨`" :places="places"
                    :model-value="c.dropoff" @update:model-value="v => Object.assign(c.dropoff, v)" />
                </div>
              </div>
            </div>
          </div>

          <div class="d-flex flex-wrap align-items-center gap-3 mt-2">
            <div class="form-check mb-0">
              <input id="rp-auto" v-model="autoOrder" class="form-check-input" type="checkbox">
              <label class="form-check-label" for="rp-auto">自動排序</label>
            </div>
            <div v-if="SHOW_CARGO" class="form-check mb-0">
              <input id="rp-external" v-model="externalCargo" class="form-check-input" type="checkbox">
              <label class="form-check-label" for="rp-external">外掛貨櫃（只停太空站）</label>
            </div>
            <div class="ms-auto d-flex gap-2">
              <button type="button" class="btn btn-sm btn-warning" @click="clearForm">
                <i class="bi bi-eraser me-1"></i>清除
              </button>
              <button type="button" class="btn btn-sm btn-primary" :disabled="!canPlan || planning" @click="plan">
                <i class="bi bi-signpost-split me-1"></i>規劃航線
              </button>
            </div>
          </div>
        </SfState>
      </div>
    </div>

    <SfState v-if="planning || planError || result" :loading="planning" :error="planError" :empty="false"
      loading-text="規劃中…" @retry="plan">
      <div v-if="result" :class="cardClass">
        <div class="card-body">
          <div class="btn-group btn-group-sm flex-wrap mb-3" role="group" aria-label="方案">
            <button v-for="p in result.plans" :key="p.key" type="button" class="btn btn-subtab"
              :class="{ active: planKey === p.key }" :aria-pressed="planKey === p.key ? 'true' : 'false'"
              @click="planKey = p.key">{{ p.label }}</button>
          </div>
          <template v-if="current">
            <div class="d-flex flex-wrap gap-2 mb-3 rp-totals">
              <span class="sf-chip sf-chip--accent">距離 {{ fmtDist(current.totals.distance) }}</span>
              <span class="sf-chip sf-chip--accent">時間 {{ fmtTime(current.totals.time) }}</span>
              <span v-if="current.totals.fuel != null" class="sf-chip sf-chip--accent">油量 {{ fmtNum(current.totals.fuel) }}</span>
              <span class="sf-chip">量子跳躍 {{ current.totals.jumps }} 次</span>
              <span v-if="current.same_as" class="sf-chip">與「{{ planLabel(current.same_as) }}」相同</span>
              <span v-if="current.warnings.includes('fuel_over_capacity')" class="sf-chip sf-chip--warn">
                超過量子油箱 {{ fmtNum(result.ship.qt_fuel_capacity) }}，需中途加油</span>
              <span v-if="current.warnings.includes('step_over_range')" class="sf-chip sf-chip--warn">單段超過可達距離</span>
            </div>
            <div style="overflow-x:auto">
              <table class="table table-hover align-middle mb-0 sf-stack rp-legs">
                <thead class="table-light">
                  <tr>
                    <th class="ps-3">目的地</th>
                    <th>動作</th>
                    <th v-if="SHOW_CARGO" class="text-end">載貨</th>
                    <th class="text-end">距離</th>
                    <th class="text-end">時間</th>
                    <th class="text-end pe-3">油量</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td class="ps-3 sf-stack__title">
                      <div class="fw-semibold"><span class="rp-no">0</span>{{ placeLabel(current.start) }}</div>
                      <div class="rp-path ps-4">{{ placePath(current.start) }}</div>
                    </td>
                    <td data-label="動作">出發</td>
                    <td v-if="SHOW_CARGO" class="text-end" data-label="載貨">0</td>
                    <td class="text-end" data-label="距離">—</td>
                    <td class="text-end" data-label="時間">—</td>
                    <td class="text-end pe-3" data-label="油量">—</td>
                  </tr>
                  <tr v-for="(leg, i) in current.legs" :key="i">
                    <td class="ps-3 sf-stack__title">
                      <div class="fw-semibold"><span class="rp-no">{{ i + 1 }}</span>{{ placeLabel(leg.to) }}</div>
                      <div class="rp-path ps-4">{{ placePath(leg.to) }}</div>
                      <div v-if="viaOf(leg).length" class="d-flex flex-wrap gap-1 mt-1 ps-4">
                        <span v-for="(v, j) in viaOf(leg)" :key="j" class="sf-chip"
                          :class="{ 'sf-chip--accent': v.kind === 'jump' }">
                          {{ v.kind === 'jump' ? '跳躍' : '經' }} {{ placeLabel(v.place) }}
                        </span>
                      </div>
                    </td>
                    <td data-label="動作">
                      <span class="sf-chip text-nowrap" :class="actionClass(leg.action)">{{ actionLabel(leg) }}</span>
                    </td>
                    <td v-if="SHOW_CARGO" class="text-end text-nowrap" data-label="載貨">{{ fmtNum(leg.load_after) }}</td>
                    <td class="text-end text-nowrap" data-label="距離">{{ leg.steps.length ? fmtDist(leg.distance) : '—' }}</td>
                    <td class="text-end text-nowrap" data-label="時間">{{ leg.steps.length ? fmtTime(leg.time) : '—' }}</td>
                    <td class="text-end text-nowrap pe-3" data-label="油量">
                      {{ leg.fuel != null && leg.steps.length ? fmtNum(leg.fuel, leg.fuel < 10 ? 1 : 0) : '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </template>
        </div>
      </div>
    </SfState>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AutocompleteField from '@/components/AutocompleteField.vue'
import PlacePicker from '@/components/PlacePicker.vue'
import SfState from '@/components/SfState.vue'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card' },
  // 玩家機庫的船（vehicle UUID），排在船清單最前面
  fleetUuids: { type: Array, default: () => [] },
})

const MAX_STOPS = 12
// 貨運（取送順序、貨重、外掛貨櫃）先隱藏，後端仍支援；打開時改成 true
const SHOW_CARGO = false
const MAX_CARGO = 8
const STORAGE_KEY = 'sc_route_v1'
let keySeq = 0
const newPlace = (p = {}) => ({ key: ++keySeq, id: p.id || '', text: p.text || '' })
const newCargo = (c = {}) => ({ key: ++keySeq, pickup: newPlace(c.pickup), dropoff: newPlace(c.dropoff),
  scu: Number(c.scu) > 0 ? Number(c.scu) : null })

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') || {}
  } catch {
    return {}
  }
}
const saved = loadSaved()
const start = reactive(newPlace(saved.start))
const endPlace = reactive(newPlace(saved.end))
const endMode = ref(['none', 'start', 'fixed'].includes(saved.endMode) ? saved.endMode : 'none')
const stops = reactive((Array.isArray(saved.stops) ? saved.stops : []).slice(0, MAX_STOPS).map(newPlace))
const cargo = reactive((Array.isArray(saved.cargo) ? saved.cargo : []).slice(0, MAX_CARGO).map(newCargo))
const autoOrder = ref(saved.autoOrder !== false)
const shipId = ref(saved.shipId || '')
const shipText = ref(saved.shipText || '')
const externalCargo = ref(!!saved.externalCargo)

const plain = p => ({ id: p.id, text: p.text })
watch([start, endPlace, endMode, stops, cargo, autoOrder, shipId, shipText, externalCargo], () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      start: plain(start), end: plain(endPlace), endMode: endMode.value, stops: stops.map(plain),
      cargo: cargo.map(c => ({ pickup: plain(c.pickup), dropoff: plain(c.dropoff), scu: c.scu })),
      autoOrder: autoOrder.value, shipId: shipId.value, shipText: shipText.value,
      externalCargo: externalCargo.value,
    }))
  } catch { /* 存不了就算了 */ }
}, { deep: true })

// ── 地點、船 ─────────────────────────────────────────────
const places = ref([])
const ships = ref([])
const loadingBase = ref(false)
const baseError = ref('')
const baseLoaded = ref(false)

async function getJson(path, options) {
  const res = await props.fetcher(path, options)
  const body = res ? await res.json().catch(() => null) : null
  return { ok: !!res?.ok && !!body?.success, body }
}

async function loadBase() {
  loadingBase.value = true
  baseError.value = ''
  const [p, s] = await Promise.all([getJson('/starmap/nav/places'), getJson('/starmap/nav/ships')])
  loadingBase.value = false
  if (!p.ok || !s.ok) {
    baseError.value = '讀取失敗。'
    return
  }
  places.value = p.body.data || []
  ships.value = s.body.data || []
  baseLoaded.value = true
  pickDefaultShip()
}

watch(() => props.active, on => { if (on && !baseLoaded.value && !loadingBase.value) loadBase() }, { immediate: true })

const fleetSet = computed(() => new Set(props.fleetUuids))
const ship = computed(() => ships.value.find(s => s.id === shipId.value) || null)

function pickDefaultShip() {
  if (shipId.value && ship.value) return
  const mine = ships.value.find(s => fleetSet.value.has(s.id))
  if (mine) pickShip(mine)
}
watch(() => props.fleetUuids, () => { if (baseLoaded.value && !shipId.value) pickDefaultShip() })

function pickShip(s) {
  shipId.value = s?.id || ''
  if (s) {
    shipText.value = shipLabel(s)
    externalCargo.value = !!s.external_cargo
  }
}

const shipLabel = s => (s.name_zh && s.name_zh !== s.name ? `${s.name_zh}（${s.name}）` : s.name)
const shipMeta = s => (fleetSet.value.has(s.id) ? '我的機庫' : (s.cargo_scu ? `${fmtNum(s.cargo_scu)} SCU` : ''))

function norm(text) {
  return (text || '').toLowerCase()
}

async function searchShips(q) {
  const t = norm(q)
  const rows = ships.value.filter(s => !t || norm(s.name).includes(t) || norm(s.name_zh).includes(t))
  rows.sort((a, b) => (fleetSet.value.has(b.id) - fleetSet.value.has(a.id)))
  return rows.slice(0, 40)
}

const placeLabel = p => (p?.name_zh && p.name_zh !== p.name ? `${p.name_zh}（${p.name}）` : (p?.name || ''))
const placePath = p => [p?.system_zh || p?.system, ...(p?.path_zh || []).slice(1)].filter(Boolean).join(' › ')

// ── 規劃 ─────────────────────────────────────────────────
const planning = ref(false)
const planError = ref('')
const result = ref(null)
const planKey = ref('fastest')

const filledStops = computed(() => stops.filter(s => s.id))
const filledCargo = computed(() => !SHOW_CARGO ? [] : cargo.filter(c => c.pickup.id && c.dropoff.id && Number(c.scu) > 0))
const canPlan = computed(() => !!start.id && (filledStops.value.length || filledCargo.value.length
  || (endMode.value === 'fixed' && endPlace.id)))

async function plan() {
  if (!canPlan.value) return
  planning.value = true
  planError.value = ''
  const { ok, body } = await getJson('/starmap/nav/route', {
    method: 'POST',
    body: JSON.stringify({
      start: start.id,
      waypoints: filledStops.value.map(s => s.id),
      cargo: filledCargo.value.map(c => ({ pickup: c.pickup.id, dropoff: c.dropoff.id, scu: Number(c.scu) })),
      end_mode: endMode.value,
      end: endPlace.id,
      auto_order: autoOrder.value,
      ship: shipId.value,
      external_cargo: SHOW_CARGO ? externalCargo.value : false,
    }),
  })
  planning.value = false
  if (!ok) {
    result.value = null
    planError.value = body?.message || '規劃失敗。'
    return
  }
  result.value = body.data
  if (!result.value.plans.some(p => p.key === planKey.value)) planKey.value = result.value.plans[0]?.key
}

function clearForm() {
  Object.assign(start, newPlace())
  Object.assign(endPlace, newPlace())
  endMode.value = 'none'
  stops.splice(0)
  cargo.splice(0)
  result.value = null
  planError.value = ''
}

const current = computed(() => result.value?.plans.find(p => p.key === planKey.value) || null)
const planLabel = key => result.value?.plans.find(p => p.key === key)?.label || key

function viaOf(leg) {
  // 中途經過的點（最後一步的終點就是目的地，不列）
  return leg.steps.slice(0, -1).map((s, i) => ({ kind: leg.steps[i + 1].kind === 'jump' ? 'jump' : 'qt', place: s.to }))
}

const ACTIONS = { stop: '途經', pickup: '取貨', dropoff: '送貨', end: '終點' }
function actionLabel(leg) {
  const base = ACTIONS[leg.action] || leg.action
  return leg.cargo ? `${base} #${leg.cargo} · ${fmtNum(leg.scu)} SCU` : base
}
const actionClass = a => ({ pickup: 'sf-chip--accent', dropoff: 'sf-chip--ok', end: 'sf-chip--todo' }[a] || '')

// ── 格式 ─────────────────────────────────────────────────
function fmtNum(v, digits = 0) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: digits })
}
function fmtDist(m) {
  if (!m) return '0 km'
  if (m >= 1e9) return `${fmtNum(m / 1e9, 2)} Gm`
  return `${fmtNum(m / 1000)} km`
}
function fmtTime(s) {
  const t = Math.round(s || 0)
  const h = Math.floor(t / 3600), mm = Math.floor((t % 3600) / 60), ss = t % 60
  if (h) return `${h} 時 ${mm} 分`
  return mm ? `${mm} 分 ${ss} 秒` : `${ss} 秒`
}
const fmtSpeed = v => (v ? `${fmtNum(v / 1000)} km/s` : '—')
</script>

<style scoped>
.rp-index { min-width: 1.5rem; text-align: center; color: var(--sf-text-muted); }
.rp-no { display: inline-block; min-width: 1.5rem; color: var(--sf-text-muted); font-weight: 400; }
.rp-path { font-size: .9rem; color: var(--sf-text-muted); }
.rp-cargo { border: 1px solid var(--sf-border); border-radius: .5rem; padding: .5rem; }
.rp-cargo-tag { min-width: 2.5rem; font-size: .9rem; color: var(--sf-text-muted); }
.rp-scu { max-width: 9rem; }
.rp-ship-facts { min-height: 1.75rem; }
</style>
