<!--
  玩家頁「航線 › 航線規劃」：量子航行路線規劃（後端 POST /starmap/nav/route，演算法見 src/models/nav.py）。
  起點＋途經站點＋貨運（取貨→送貨、SCU；目前隱藏，見 SHOW_CARGO），可自動排序或照輸入順序，終點可不指定／回到起點／指定地點。
  結果一次給三種方案（最快／最省油／最順路），每一段列出經過的 OM 點、跳躍點（components/RouteLegsTable.vue）；
  可切換成 3D 星圖（components/RouteMap3D.vue）。多份合約分給多個小隊見 components/ContractPlanner.vue。
  超寬螢幕（21:9）表單分左右兩欄（左：船／油量／起點／終點，右：途經站點）。
  結果預設在跳出視窗（SfModal）裡，可切回原版接在表單下面（popupResult）；結果最下面「完成」可選結束或終點設為起點。
  表單（地點、船、貨運）記在這台瀏覽器（localStorage）。
-->
<template>
  <div>
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body">
        <SfState :loading="base.loading.value" :error="base.error.value"
          :empty="base.loaded.value && !base.places.value.length" empty-text="尚無地點座標資料。" @retry="base.load">
          <!-- 超寬螢幕（21:9）：同一張卡片裡左邊放船／油量／起點／終點，右邊放途經站點，欄位不會被拉得太長 -->
          <div class="rp-split">
          <div class="rp-split__left">
          <ShipFilter id="rp-filter" class="mb-2" />
          <ShipPicker id="rp" v-model:ship-id="shipId" v-model:ship-text="shipText" v-model:qd-id="qdId"
            :ships="base.ships.value" :quantum-drives="base.quantumDrives.value" :fleet-uuids="fleetUuids"
            :show-cargo="SHOW_CARGO" auto-pick @pick="s => { if (s) externalCargo = !!s.external_cargo }" />
          <div class="row g-2 align-items-end mt-0">
            <div class="col-12">
              <label class="form-label small fw-semibold mb-1" for="rp-fuel">起始油量</label>
              <FuelStartInput id="rp-fuel" v-model="startFuel" />
            </div>
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
            <div class="col-12">
              <div class="form-check mb-1">
                <input id="rp-hub-on" v-model="hubOn" class="form-check-input" type="checkbox">
                <label class="form-check-label small fw-semibold" for="rp-hub-on">定期回指定站</label>
              </div>
              <div v-if="hubOn" class="row g-1">
                <div class="col-12 col-md-3">
                  <div class="input-group input-group-sm">
                    <span class="input-group-text">每</span>
                    <input id="rp-hub-every" v-model.number="hubEvery" type="number" min="1" :max="MAX_ON" step="1"
                      class="form-control" aria-label="幾站回指定站一次">
                    <span class="input-group-text">站</span>
                  </div>
                </div>
                <div class="col-12 col-md-9">
                  <PlacePicker id="rp-hub" label="指定站" :places="base.places.value" :model-value="hubPlace"
                    @update:model-value="v => Object.assign(hubPlace, v)" />
                </div>
              </div>
            </div>
          </div>

          </div>
          <div class="rp-split__right">
          <div class="mt-3 rp-stops">
            <div class="d-flex flex-wrap align-items-center gap-2 mb-1">
              <span class="small fw-semibold">途經站點</span>
              <span v-if="stops.length" class="sf-chip" :class="{ 'sf-chip--warn': onCount >= MAX_ON }">
                規劃 {{ onCount }} / {{ MAX_ON }}</span>
              <div class="ms-auto d-flex flex-wrap gap-2">
                <button v-if="stops.length > 1" type="button" class="btn btn-sm btn-warning" @click="stops.splice(0)">
                  <i class="bi bi-eraser me-1"></i>清空站點</button>
                <button type="button" class="btn btn-sm btn-success" :disabled="stops.length >= MAX_STOPS"
                  @click="stops.push(newStop({ on: onCount < MAX_ON }))"><i class="bi bi-plus-lg me-1"></i>加站點</button>
                <!-- 跟合約分配一樣：按了才展開依星系填入，填入後收起 -->
                <button type="button" class="btn btn-sm" :class="fillOpen ? 'btn-secondary' : 'btn-primary'"
                  :aria-expanded="fillOpen ? 'true' : 'false'" @click="fillOpen = !fillOpen">
                  <i class="bi bi-stars me-1"></i>依星系填入</button>
              </div>
            </div>
            <div v-if="fillOpen" class="rp-fill mb-2">
              <SystemStopsFill id="rp-fill" :places="base.places.value" @fill="fillStops" />
            </div>
            <div v-if="fillNote" class="sf-chip sf-chip--warn mb-2">{{ fillNote }}</div>
            <!-- 總開關：跟每列開關對齊放在列表最上方，全開時關閉全部，否則開到上限 -->
            <div v-if="stops.length > 1" class="d-flex gap-2 mb-2 align-items-center rp-all">
              <span class="rp-index"></span>
              <div class="form-check form-switch mb-0 rp-switch">
                <input id="rp-on-all" class="form-check-input" type="checkbox" role="switch"
                  :checked="allOnState === 'all'" :indeterminate.prop="allOnState === 'some'"
                  aria-label="全部站點加入規劃" @change="setAllOn(allOnState !== 'all')">
              </div>
              <label for="rp-on-all" class="small fw-semibold mb-0 rp-all-label">全部</label>
            </div>
            <div v-for="(s, i) in stops" :key="s.key" class="d-flex gap-2 mb-2 align-items-center"
              :class="{ 'rp-off': !s.on }">
              <span class="rp-index">{{ i + 1 }}</span>
              <div class="form-check form-switch mb-0 rp-switch">
                <input :id="`rp-on-${s.key}`" v-model="s.on" class="form-check-input" type="checkbox" role="switch"
                  :disabled="!s.on && onCount >= MAX_ON" :aria-label="`站點 ${i + 1} 加入規劃`">
              </div>
              <div v-if="s.auto && placeOf(s)" class="flex-grow-1 min-w-0 rp-auto">
                <span class="fw-semibold">{{ placeLabel(placeOf(s)) }}</span>
                <span class="rp-path">{{ placePath(placeOf(s)) }}</span>
              </div>
              <div v-else class="flex-grow-1">
                <PlacePicker :id="`rp-stop-${s.key}`" :label="`站點 ${i + 1} `" :places="base.places.value" :model-value="s"
                  @update:model-value="v => Object.assign(s, v)" />
              </div>
              <span v-if="directDist(s)" class="sf-chip text-nowrap" :title="`起點直達 ${directDist(s)}`">
                <i class="bi bi-rulers me-1"></i>{{ directDist(s) }}</span>
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

          </div>
          </div>

          <div class="d-flex flex-wrap align-items-center gap-3 mt-2 rp-actions">
            <div class="form-check mb-0">
              <input id="rp-auto" v-model="autoOrder" class="form-check-input" type="checkbox">
              <label class="form-check-label" for="rp-auto">自動排序</label>
            </div>
            <div v-if="SHOW_CARGO" class="form-check mb-0">
              <input id="rp-external" v-model="externalCargo" class="form-check-input" type="checkbox">
              <label class="form-check-label" for="rp-external">外掛貨櫃（只停外部貨運站）</label>
            </div>
            <div class="form-check form-switch mb-0">
              <input id="rp-popup" v-model="popupResult" class="form-check-input" type="checkbox" role="switch">
              <label class="form-check-label" for="rp-popup">結果用跳出視窗</label>
            </div>
            <div class="ms-auto d-flex gap-2">
              <button v-if="popupResult && result && !resultOpen" type="button" class="btn btn-sm btn-info"
                @click="resultOpen = true"><i class="bi bi-window-stack me-1"></i>查看航線</button>
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

    <!-- 規劃結果：預設在跳出視窗裡（popupResult），關掉開關就照原版接在表單下面；同一份內容用 Teleport 換位置 -->
    <SfModal id="rp-result" v-model:open="resultOpen" title="航線規劃" icon="bi bi-signpost-split" width="1440px">
      <div id="rp-result-modal"></div>
    </SfModal>
    <div id="rp-result-inline"></div>
    <Teleport defer :to="popupResult ? '#rp-result-modal' : '#rp-result-inline'">
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
              <span v-if="current.same_as && !manualOrder" class="sf-chip">與「{{ planLabel(current.same_as) }}」相同</span>
              <span v-if="manualOrder" class="sf-chip sf-chip--accent">已手動調整順序</span>
              <span v-if="replannedFrom" class="sf-chip sf-chip--accent">已從 {{ placeLabel(replannedFrom) }} 重新規劃</span>
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
            <div v-if="reorderError" class="alert alert-warning py-2 mb-2" role="alert">{{ reorderError }}</div>
            <RouteLegsTable v-show="view === 'table'" v-model:visited="visited" :plan="current"
              :fuel-capacity="result.ship.qt_fuel_capacity" :show-load="SHOW_CARGO" :reorderable="!SHOW_CARGO && !reordering"
              :replannable="!SHOW_CARGO" :replanning="reordering" :places="base.places.value"
              @reorder="reorder" @replan="replan" />

            <!-- 完成：兩個選項直接列出來——結束這趟（清掉結果），或把終點設成下一趟的起點、終點重設。
                 終點就是起點（回到起點）時「設為起點」沒有作用，按鈕停用 -->
            <div class="rp-finish mt-3">
              <span class="rp-finish__label"><i class="bi bi-flag-fill me-1"></i>完成</span>
              <button type="button" class="btn btn-sm btn-primary" @click="endTrip">
                <i class="bi bi-stop-circle me-1"></i>結束</button>
              <button type="button" class="btn btn-sm btn-success" :disabled="!finishTarget" @click="finishRoute">
                <i class="bi bi-arrow-repeat me-1"></i>{{ finishTarget ? `終點「${finishName}」設為起點` : '終點設為起點' }}</button>
            </div>
          </template>
        </div>
      </div>
    </SfState>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import PlacePicker from '@/components/PlacePicker.vue'
import FuelStartInput from '@/components/FuelStartInput.vue'
import RouteLegsTable from '@/components/RouteLegsTable.vue'
import RouteMap3D from '@/components/RouteMap3D.vue'
import SfState from '@/components/SfState.vue'
import SfModal from '@/components/SfModal.vue'
import SystemStopsFill from '@/components/SystemStopsFill.vue'
import ShipFilter from '@/components/ShipFilter.vue'
import ShipPicker from '@/components/ShipPicker.vue'
import { useNavBase } from '@/utils/navBase'
import { fmtDist, fmtNum, fmtTime, placeLabel, placePath } from '@/utils/navFormat'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card' },
  // 玩家機庫的船（vehicle UUID），排在船清單最前面
  fleetUuids: { type: Array, default: () => [] },
})

// 列在清單上的站點上限；實際送去規劃的（開關打開的）上限跟後端 nav.MAX_WAYPOINTS 一樣
const MAX_STOPS = 300
const MAX_ON = 40
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
// 途經站點：on＝加入規劃（開關）；auto＝依星系填入的（不用地點選擇器，直接顯示名稱）
const newStop = (p = {}) => ({ ...newPlace(p), on: p.on !== false, auto: !!p.auto })
const stops = reactive((Array.isArray(saved.stops) ? saved.stops : []).slice(0, MAX_STOPS).map(newStop))
// 舊存檔（12 個上限以前）沒有 on：超過上限的先關掉
stops.forEach((s, i) => { if (i >= MAX_ON) s.on = false })
const cargo = reactive((Array.isArray(saved.cargo) ? saved.cargo : []).slice(0, MAX_CARGO).map(newCargo))
const autoOrder = ref(saved.autoOrder !== false)
const shipId = ref(saved.shipId || '')
const shipText = ref(saved.shipText || '')
const qdId = ref(saved.qdId || '')
const externalCargo = ref(!!saved.externalCargo)
// 起始油量 { mode: pct／amount, value }，value 空的＝滿油（components/FuelStartInput.vue）
const startFuel = ref({ mode: saved.startFuel?.mode === 'amount' ? 'amount' : 'pct',
  value: Number(saved.startFuel?.value) >= 0 && saved.startFuel?.value !== null ? Number(saved.startFuel.value) : null })
const fuelParam = () => (startFuel.value.value == null ? null : startFuel.value)
// 定期回指定站：每跑 hubEvery 站回 hubPlace 一次（後端 nav.plan_route 的 hub／hub_every）
const hubOn = ref(saved.hubOn === true)
const hubPlace = reactive(newPlace(saved.hub))
const hubEvery = ref(Number(saved.hubEvery) >= 1 ? Math.round(Number(saved.hubEvery)) : 3)
// 結果顯示方式：true＝跳出視窗（預設）、false＝原版（接在表單下面）
const popupResult = ref(saved.popupResult !== false)
const resultOpen = ref(false)
watch(popupResult, (on) => { resultOpen.value = on && !!(result.value || planning.value || planError.value) })
const hubReady = computed(() => !hubOn.value || (!!hubPlace.id && hubEvery.value >= 1 && hubEvery.value <= MAX_ON))

const plain = p => ({ id: p.id, text: p.text })
const plainStop = s => ({ ...plain(s), on: s.on, auto: s.auto })
watch([start, endPlace, endMode, stops, cargo, autoOrder, shipId, shipText, qdId, externalCargo, startFuel,
  hubOn, hubPlace, hubEvery, popupResult], () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      start: plain(start), end: plain(endPlace), endMode: endMode.value, stops: stops.map(plainStop),
      cargo: cargo.map(c => ({ pickup: plain(c.pickup), dropoff: plain(c.dropoff), scu: c.scu })),
      autoOrder: autoOrder.value, shipId: shipId.value, shipText: shipText.value, qdId: qdId.value,
      externalCargo: externalCargo.value, startFuel: startFuel.value,
      hubOn: hubOn.value, hub: plain(hubPlace), hubEvery: hubEvery.value, popupResult: popupResult.value,
    }))
  } catch { /* 存不了就算了 */ }
}, { deep: true })

// ── 地點、船、量子引擎（跟「合約分配」共用，見 utils/navBase.js）──
const base = useNavBase(props.fetcher)
watch(() => props.active, (on) => {
  if (!on) return
  if (!base.loaded.value) base.load()
  base.loadCargoGrids()
}, { immediate: true })

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

const filledStops = computed(() => stops.filter(s => s.id && s.on))
const onCount = computed(() => stops.filter(s => s.on).length)
const placeById = computed(() => new Map(base.places.value.map(p => [p.id, p])))
const placeOf = s => placeById.value.get(s.id) || null
// 起點到站點的直線距離（同星系才算；地點座標是各星系自己的座標系）
function directDist(s) {
  const a = placeById.value.get(start.id), b = placeOf(s)
  if (!a?.p || !b?.p) return ''
  if (a.system_key !== b.system_key) return '跨星系'
  return fmtDist(Math.hypot(a.p[0] - b.p[0], a.p[1] - b.p[1], a.p[2] - b.p[2]))
}

// 總開關狀態：all＝能開的都開了（全開或已到上限）、some＝部分、none＝全關
const allOnState = computed(() => {
  const n = onCount.value
  if (!n) return 'none'
  return n === stops.length || n >= MAX_ON ? 'all' : 'some'
})

function setAllOn(on) {
  let n = 0
  for (const s of stops) {
    s.on = on && n < MAX_ON
    if (s.on) n++
  }
}

// 依星系填入：已經在清單上的跳過；開關打開到上限為止，其餘先關著
const fillNote = ref('')
const fillOpen = ref(false)
function fillStops(rows) {
  fillOpen.value = false
  const have = new Set(stops.map(s => s.id).filter(Boolean))
  let on = onCount.value, added = 0, skipped = 0
  for (const p of rows) {
    if (have.has(p.id)) continue
    if (stops.length >= MAX_STOPS) {
      skipped++
      continue
    }
    stops.push(newStop({ id: p.id, text: placeLabel(p), auto: true, on: on < MAX_ON }))
    if (on < MAX_ON) on++
    have.add(p.id)
    added++
  }
  const off = stops.filter(s => !s.on).length
  fillNote.value = [skipped ? `清單已滿 ${MAX_STOPS} 個，${skipped} 個沒有填入` : '',
    added && off ? `超過 ${MAX_ON} 個，${off} 個站點先關閉` : ''].filter(Boolean).join('；')
}
watch(() => stops.length, n => { if (!n) fillNote.value = '' })
const filledCargo = computed(() => !SHOW_CARGO ? [] : cargo.filter(c => c.pickup.id && c.dropoff.id && Number(c.scu) > 0))
const canPlan = computed(() => !!start.id && hubReady.value && (filledStops.value.length || filledCargo.value.length
  || (endMode.value === 'fixed' && endPlace.id)))

// 航段表：已去過（列代號）、拖拉調整順序後的重算（照新順序、不自動排序）
const visited = ref([])
const manualOrder = ref(false)
const reordering = ref(false)
const reorderError = ref('')

// 上一次成功的規劃參數（調整順序時沿用：中途重新規劃過的話起點、終點、油量是新的）
let lastReq = null

// 中途重新規劃：從目前位置出發，還沒去的站＋插入的站自動排序；原本要回起點／指定終點的照舊
const replannedFrom = ref(null)
async function replan(p) {
  const waypoints = p.remaining.filter(l => l.action === 'stop').map(l => l.to.id)
  for (const id of p.inserts || []) if (!waypoints.includes(id)) waypoints.push(id)
  // 原本的終點（回到起點＝原起點）
  const endId = lastReq?.end_mode === 'start' ? lastReq.start : lastReq?.end_mode === 'fixed' ? lastReq.end : ''
  if (!waypoints.length && !endId) {
    reorderError.value = '沒有還沒去的站點，請插入一個站點'
    return
  }
  reordering.value = true
  reorderError.value = ''
  const req = {
    ...lastReq, start: p.current.id, waypoints, cargo: [], end_mode: endId ? 'fixed' : 'none', end: endId,
    auto_order: true, start_fuel: p.fuel != null ? { mode: 'amount', value: p.fuel } : lastReq?.start_fuel,
  }
  const res = await props.fetcher('/starmap/nav/route', { method: 'POST', body: JSON.stringify(req) })
  const body = res ? await res.json().catch(() => null) : null
  reordering.value = false
  if (!res?.ok || !body?.success) {
    reorderError.value = body?.message || '重新規劃失敗。'
    return
  }
  result.value = body.data
  lastReq = req
  visited.value = []
  manualOrder.value = false
  replannedFrom.value = p.current
}

async function reorder(legs) {
  reordering.value = true
  reorderError.value = ''
  const res = await props.fetcher('/starmap/nav/route', {
    method: 'POST',
    body: JSON.stringify({ ...lastReq, waypoints: legs.filter(l => l.action === 'stop').map(l => l.to.id), auto_order: false }),
  })
  const body = res ? await res.json().catch(() => null) : null
  reordering.value = false
  if (!res?.ok || !body?.success) {
    reorderError.value = body?.message || '重新計算失敗。'
    return
  }
  result.value = body.data
  manualOrder.value = true
}

async function plan() {
  if (!canPlan.value) return
  planning.value = true
  if (popupResult.value) resultOpen.value = true
  planError.value = ''
  visited.value = []
  manualOrder.value = false
  replannedFrom.value = null
  reorderError.value = ''
  const req = {
    start: start.id,
    waypoints: filledStops.value.map(s => s.id),
    cargo: filledCargo.value.map(c => ({ pickup: c.pickup.id, dropoff: c.dropoff.id, scu: Number(c.scu) })),
    end_mode: endMode.value,
    end: endPlace.id,
    auto_order: autoOrder.value,
    ship: shipId.value,
    quantum_drive: qdId.value,
    external_cargo: SHOW_CARGO ? externalCargo.value : false,
    start_fuel: fuelParam(),
    hub: hubOn.value ? hubPlace.id : '',
    hub_every: hubOn.value ? hubEvery.value : null,
  }
  const res = await props.fetcher('/starmap/nav/route', { method: 'POST', body: JSON.stringify(req) })
  const body = res ? await res.json().catch(() => null) : null
  planning.value = false
  if (!res?.ok || !body?.success) {
    result.value = null
    planError.value = body?.message || '規劃失敗。'
    return
  }
  result.value = body.data
  lastReq = req
  if (!result.value.plans.some(p => p.key === planKey.value)) planKey.value = result.value.plans[0]?.key
}

// 完成：跑完這趟後「結束」（清掉結果）或「終點設為起點」（目前方案最後一站變成下一趟起點，終點重設）。
// 終點看目前方案實際的最後一站（最後一站／指定地點／中途重新規劃過都對）；回到起點時跟起點一樣就不給這個選項
const finishTarget = computed(() => {
  const legs = current.value?.legs || []
  const id = legs[legs.length - 1]?.to?.id
  if (!id || id === start.id) return null
  return placeById.value.get(id) || legs[legs.length - 1].to
})
const finishName = computed(() => finishTarget.value ? (finishTarget.value.name_zh || finishTarget.value.name) : '')
function resetResult() {
  result.value = null
  planError.value = ''
  visited.value = []
  manualOrder.value = false
  replannedFrom.value = null
  reorderError.value = ''
  resultOpen.value = false
}
function endTrip() {
  resetResult()
}
function finishRoute() {
  const p = finishTarget.value
  if (!p) return
  Object.assign(start, { id: p.id, text: placeLabel(p) })
  Object.assign(endPlace, { id: '', text: '' })
  resetResult()
}

function clearForm() {
  Object.assign(start, newPlace())
  Object.assign(endPlace, newPlace())
  endMode.value = 'none'
  hubOn.value = false
  Object.assign(hubPlace, newPlace())
  stops.splice(0)
  cargo.splice(0)
  resetResult()
}

const current = computed(() => result.value?.plans.find(p => p.key === planKey.value) || null)
const planLabel = key => result.value?.plans.find(p => p.key === key)?.label || key
</script>

<style scoped>
.rp-index { min-width: 1.5rem; text-align: center; color: var(--sf-text-muted); }
.rp-switch { padding-left: 2.5em; }
.rp-switch .form-check-input { width: 2.2em; height: 1.2em; cursor: pointer; }
.rp-auto { display: flex; flex-wrap: wrap; align-items: baseline; gap: .1rem .6rem; padding: .25rem .5rem;
  border: 1px solid var(--sf-border); border-radius: .375rem; background: var(--sf-chip-bg); }
.rp-path { font-size: 1rem; color: var(--sf-text-muted); }
.rp-off .rp-auto, .rp-off .rp-index { opacity: .5; }
.rp-all { padding-bottom: .4rem; border-bottom: 1px dashed var(--sf-border); }
.rp-all-label { cursor: pointer; }
.min-w-0 { min-width: 0; }
.rp-cargo { border: 1px solid var(--sf-border); border-radius: .5rem; padding: .5rem; }
.rp-cargo-tag { min-width: 2.5rem; font-size: 1rem; color: var(--sf-text-muted); }
.rp-scu { max-width: 9rem; }
/* 超寬螢幕（跟 scifi-theme.css 的 .sf-split 同一組條件）：表單分左右兩欄，中間一條分隔線 */
@media (min-aspect-ratio: 11/5) and (min-width: 1800px) {
  .rp-split { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); column-gap: 2rem; align-items: start; }
  .rp-split__right { border-left: 1px solid var(--sf-border); padding-left: 2rem; min-height: 100%; }
  .rp-split__right > .rp-stops { margin-top: 0 !important; }
  .rp-actions { border-top: 1px solid var(--sf-border); padding-top: .75rem; margin-top: 1rem !important; }
}
.rp-fill { padding: .5rem; border: 1px solid var(--sf-border); border-radius: .375rem; }
.rp-finish { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .5rem;
  align-items: center; padding: .6rem 0; border-top: 1px solid var(--sf-border);
  /* 貼在視窗（或畫面）底部，航段很多時不用捲到最下面才看得到 */
  position: sticky; bottom: -1rem; z-index: 2; background: var(--sf-panel); }
.rp-finish__label { font-weight: 600; color: var(--sf-text-strong); margin-right: auto; }
</style>
