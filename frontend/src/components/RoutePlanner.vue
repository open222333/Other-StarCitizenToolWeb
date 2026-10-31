<!--
  玩家頁「航線 › 航線規劃」：量子航行路線規劃（後端 POST /starmap/nav/route，演算法見 src/models/nav.py）。
  起點＋途經站點＋貨運（取貨→送貨、SCU；目前隱藏，見 SHOW_CARGO），可自動排序或照輸入順序，終點可不指定／回到起點／指定地點。
  結果一次給三種方案（最快／最省油／最順路），每一段列出經過的 OM 點、跳躍點（components/RouteLegsTable.vue）；
  可切換成 3D 星圖（components/RouteMap3D.vue）。多份合約分給多個小隊見 components/ContractPlanner.vue。
  表單（地點、船、貨運）記在這台瀏覽器（localStorage）。
-->
<template>
  <div>
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body">
        <SfState :loading="base.loading.value" :error="base.error.value"
          :empty="base.loaded.value && !base.places.value.length" empty-text="尚無地點座標資料。" @retry="base.load">
          <ShipPicker id="rp" v-model:ship-id="shipId" v-model:ship-text="shipText" v-model:qd-id="qdId"
            :ships="base.ships.value" :quantum-drives="base.quantumDrives.value" :fleet-uuids="fleetUuids"
            :show-cargo="SHOW_CARGO" auto-pick @pick="s => { if (s) externalCargo = !!s.external_cargo }" />
          <div class="row g-2 align-items-end mt-0">
            <div class="col-12">
              <label class="form-label small fw-semibold mb-1" for="rp-start">起點</label>
              <PlacePicker id="rp-start" label="起點" :places="base.places.value" :model-value="start"
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
                  <PlacePicker id="rp-end" label="終點" :places="base.places.value" :model-value="endPlace"
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
                <PlacePicker :id="`rp-stop-${s.key}`" :label="`站點 ${i + 1} `" :places="base.places.value" :model-value="s"
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
                  <PlacePicker :id="`rp-pick-${c.key}`" :label="`貨運 ${i + 1} 取貨`" :places="base.places.value"
                    :model-value="c.pickup" @update:model-value="v => Object.assign(c.pickup, v)" />
                </div>
              </div>
              <div class="d-flex gap-2 align-items-center">
                <span class="rp-cargo-tag">送貨</span>
                <div class="flex-grow-1">
                  <PlacePicker :id="`rp-drop-${c.key}`" :label="`貨運 ${i + 1} 送貨`" :places="base.places.value"
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
            <div class="d-flex flex-wrap gap-2 mb-3">
              <span class="sf-chip sf-chip--accent">距離 {{ fmtDist(current.totals.distance) }}</span>
              <span class="sf-chip sf-chip--accent">時間 {{ fmtTime(current.totals.time) }}</span>
              <span v-if="current.totals.fuel != null" class="sf-chip sf-chip--accent">油量 {{ fmtNum(current.totals.fuel) }}</span>
              <span class="sf-chip">量子跳躍 {{ current.totals.jumps }} 次</span>
              <span v-if="current.same_as" class="sf-chip">與「{{ planLabel(current.same_as) }}」相同</span>
              <span v-if="current.refuel_stops?.length" class="sf-chip sf-chip--warn">
                需補充燃料 {{ current.refuel_stops.length }} 次</span>
              <span v-if="current.warnings.includes('fuel_short')" class="sf-chip sf-chip--warn">
                油量不足：有段落單趟就超過油箱</span>
              <span v-if="current.warnings.includes('step_over_range')" class="sf-chip sf-chip--warn">單段超過可達距離</span>
            </div>
            <div class="btn-group btn-group-sm mb-2" role="group" aria-label="顯示方式">
              <button v-for="v in VIEWS" :key="v.key" type="button" class="btn btn-subtab"
                :class="{ active: view === v.key }" :aria-pressed="view === v.key ? 'true' : 'false'"
                @click="view = v.key"><i :class="v.icon" class="me-1"></i>{{ v.label }}</button>
            </div>
            <RouteMap3D v-if="view === 'map'" :plan="current" :map="result.map || {}" />
            <RouteLegsTable v-show="view === 'table'" :plan="current" :fuel-capacity="result.ship.qt_fuel_capacity"
              :show-load="SHOW_CARGO" />
          </template>
        </div>
      </div>
    </SfState>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import PlacePicker from '@/components/PlacePicker.vue'
import RouteLegsTable from '@/components/RouteLegsTable.vue'
import RouteMap3D from '@/components/RouteMap3D.vue'
import SfState from '@/components/SfState.vue'
import ShipPicker from '@/components/ShipPicker.vue'
import { useNavBase } from '@/utils/navBase'
import { fmtDist, fmtNum, fmtTime } from '@/utils/navFormat'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card' },
  // 玩家機庫的船（vehicle UUID），排在船清單最前面
  fleetUuids: { type: Array, default: () => [] },
})

const MAX_STOPS = 12
// 貨運（取送順序、貨重、外掛貨櫃）先隱藏，後端仍支援；打開時改成 true（多份合約請用「合約分配」）
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
const qdId = ref(saved.qdId || '')
const externalCargo = ref(!!saved.externalCargo)

const plain = p => ({ id: p.id, text: p.text })
watch([start, endPlace, endMode, stops, cargo, autoOrder, shipId, shipText, qdId, externalCargo], () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      start: plain(start), end: plain(endPlace), endMode: endMode.value, stops: stops.map(plain),
      cargo: cargo.map(c => ({ pickup: plain(c.pickup), dropoff: plain(c.dropoff), scu: c.scu })),
      autoOrder: autoOrder.value, shipId: shipId.value, shipText: shipText.value, qdId: qdId.value,
      externalCargo: externalCargo.value,
    }))
  } catch { /* 存不了就算了 */ }
}, { deep: true })

// ── 地點、船、量子引擎（跟「合約分配」共用，見 utils/navBase.js）──
const base = useNavBase(props.fetcher)
watch(() => props.active, on => { if (on && !base.loaded.value) base.load() }, { immediate: true })

// ── 規劃 ─────────────────────────────────────────────────
const planning = ref(false)
const planError = ref('')
const result = ref(null)
const planKey = ref('fastest')
// 結果的顯示方式：航段表／3D 星圖
const VIEWS = [
  { key: 'table', label: '航段表', icon: 'bi bi-list-ol' },
  { key: 'map', label: '3D 星圖', icon: 'bi bi-globe2' },
]
const view = ref('table')

const filledStops = computed(() => stops.filter(s => s.id))
const filledCargo = computed(() => !SHOW_CARGO ? [] : cargo.filter(c => c.pickup.id && c.dropoff.id && Number(c.scu) > 0))
const canPlan = computed(() => !!start.id && (filledStops.value.length || filledCargo.value.length
  || (endMode.value === 'fixed' && endPlace.id)))

async function plan() {
  if (!canPlan.value) return
  planning.value = true
  planError.value = ''
  const res = await props.fetcher('/starmap/nav/route', {
    method: 'POST',
    body: JSON.stringify({
      start: start.id,
      waypoints: filledStops.value.map(s => s.id),
      cargo: filledCargo.value.map(c => ({ pickup: c.pickup.id, dropoff: c.dropoff.id, scu: Number(c.scu) })),
      end_mode: endMode.value,
      end: endPlace.id,
      auto_order: autoOrder.value,
      ship: shipId.value,
      quantum_drive: qdId.value,
      external_cargo: SHOW_CARGO ? externalCargo.value : false,
    }),
  })
  const body = res ? await res.json().catch(() => null) : null
  planning.value = false
  if (!res?.ok || !body?.success) {
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
</script>

<style scoped>
.rp-index { min-width: 1.5rem; text-align: center; color: var(--sf-text-muted); }
.rp-cargo { border: 1px solid var(--sf-border); border-radius: .5rem; padding: .5rem; }
.rp-cargo-tag { min-width: 2.5rem; font-size: 1rem; color: var(--sf-text-muted); }
.rp-scu { max-width: 9rem; }
</style>
