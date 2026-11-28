<!--
  玩家頁「航線 › 航線規劃」：量子航行路線規劃（後端 POST /starmap/nav/route，演算法見 src/models/nav.py）。
  起點＋途經站點＋貨運（取貨→送貨、SCU；目前隱藏，見 SHOW_CARGO），可自動排序或照輸入順序，終點可不指定／回到起點／指定地點。
  結果一次給三種方案（最快／最省油／最順路），每一段列出經過的 OM 點、跳躍點（components/RouteLegsTable.vue）；
  可切換成 3D 星圖（components/RouteMap3D.vue）。多份合約分給多個小隊見 components/ContractPlanner.vue。
  超寬螢幕（21:9）表單分左右兩欄（左：船／油量／起點／終點，右：途經站點）。
  結果上方的「貨物規劃」開關（可選）打開後，航段表每站有「貨物」按鈕設定裝卸（RouteLegsTable.vue、StopCargoEditor.vue）。
  結果上方有這艘船的「網格」（CargoGridButton.vue）與「貨櫃試算」（CrateCalcButton.vue）按鈕，各自跳出視窗。
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
              <div class="sf-pills mb-1">
                <SfToggle v-model="hubOn">定期回指定站</SfToggle>
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
              <span class="small fw-semibold">站點</span>
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
            <!-- 起點、途經站點、終點同一種列：序號（起／1…／終）、地點（選好後收成一行，點一下改）、貨物、刪除 -->
            <div class="d-flex gap-2 mb-2 align-items-center rp-row">
              <span class="rp-index rp-index--tag">起</span>
              <span class="rp-switch-gap" aria-hidden="true"></span>
              <div class="rp-place">
                <PlaceSlot id="rp-start" label="起點" :places="base.places.value" :model-value="start"
                  @update:model-value="v => Object.assign(start, v)" />
              </div>
              <!-- 中間：這站要裝卸的貨（沒有就是空白，把右邊的按鈕推到最右） -->
              <div class="rp-mid"><RouteCargoSummary inline :entries="startCargo" /></div>
              <span class="rp-dist-gap" aria-hidden="true"></span>
              <button type="button" class="btn btn-sm text-nowrap" :class="cargoCount(startCargo) ? 'btn-info' : 'btn-secondary'"
                aria-haspopup="dialog" :aria-label="'起點的貨物'" @click="openFormCargo('start')">
                <i class="bi bi-box-seam"></i><span class="d-none d-md-inline ms-1">貨物</span><span v-if="cargoCount(startCargo)" class="ms-1">{{ cargoCount(startCargo) }}</span></button>
              <span class="rp-del-gap" aria-hidden="true"></span>
            </div>
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
            <template v-for="(s, i) in stops" :key="s.key">
            <div class="d-flex gap-2 mb-2 align-items-center rp-row" :class="{ 'rp-off': !s.on }">
              <span class="rp-index">{{ i + 1 }}</span>
              <div class="form-check form-switch mb-0 rp-switch">
                <input :id="`rp-on-${s.key}`" v-model="s.on" class="form-check-input" type="checkbox" role="switch"
                  :disabled="!s.on && onCount >= MAX_ON" :aria-label="`站點 ${i + 1} 加入規劃`">
              </div>
              <div class="rp-place">
                <div v-if="s.auto && placeOf(s)" class="rp-auto">
                  <span class="fw-semibold">{{ placeLabel(placeOf(s)) }}</span>
                  <span class="rp-path">{{ placePath(placeOf(s)) }}</span>
                  <PlaceCargoTags :place="placeOf(s)" />
                </div>
                <PlaceSlot v-else :id="`rp-stop-${s.key}`" :label="`站點 ${i + 1} `" :places="base.places.value" :model-value="s"
                  @update:model-value="v => Object.assign(s, v)" />
              </div>
              <div class="rp-mid"><RouteCargoSummary inline :entries="s.cargo" /></div>
              <span v-if="directDist(s)" class="sf-chip text-nowrap rp-dist" :title="`起點直達 ${directDist(s)}`">
                <i class="bi bi-rulers me-1"></i>{{ directDist(s) }}</span>
              <button type="button" class="btn btn-sm text-nowrap" :class="cargoCount(s.cargo) ? 'btn-info' : 'btn-secondary'"
                aria-haspopup="dialog" :aria-label="`站點 ${i + 1} 的貨物`" @click="openFormCargo(`stop:${s.key}`)">
                <i class="bi bi-box-seam"></i><span class="d-none d-md-inline ms-1">貨物</span><span v-if="cargoCount(s.cargo)" class="ms-1">{{ cargoCount(s.cargo) }}</span></button>
              <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除站點 ${i + 1}`"
                @click="stops.splice(i, 1)"><i class="bi bi-trash"></i></button>
            </div>
            </template>
            <!-- 終點：最後一站／回到起點／指定地點 -->
            <div class="d-flex gap-2 mb-2 align-items-center rp-row">
              <span class="rp-index rp-index--tag">終</span>
              <SfChoice id="rp-end-mode" v-model="endMode" required label="終點" class="rp-end-mode"
                :options="[{ value: 'none', label: '最後一站' }, { value: 'start', label: '回到起點' }, { value: 'fixed', label: '指定地點' }]" />
              <div class="rp-place">
                <PlaceSlot v-if="endMode === 'fixed'" id="rp-end" label="終點" :places="base.places.value" :model-value="endPlace"
                  @update:model-value="v => Object.assign(endPlace, v)" />
                <div v-else-if="endMode === 'start'" class="rp-auto">
                  <span class="fw-semibold">{{ placeOf(start) ? placeLabel(placeOf(start)) : '（還沒選起點）' }}</span>
                  <span v-if="placeOf(start)" class="rp-path">{{ placePath(placeOf(start)) }}</span>
                  <PlaceCargoTags :place="placeOf(start)" />
                </div>
                <div v-else class="small text-muted">最後一個途經站點就是終點</div>
              </div>
              <div class="rp-mid"><RouteCargoSummary v-if="endMode !== 'none'" inline :entries="endCargo" /></div>
              <span class="rp-dist-gap" aria-hidden="true"></span>
              <template v-if="endMode !== 'none'">
              <button type="button" class="btn btn-sm text-nowrap" :class="cargoCount(endCargo) ? 'btn-info' : 'btn-secondary'"
                aria-haspopup="dialog" :aria-label="'終點的貨物'" @click="openFormCargo('end')">
                <i class="bi bi-box-seam"></i><span class="d-none d-md-inline ms-1">貨物</span><span v-if="cargoCount(endCargo)" class="ms-1">{{ cargoCount(endCargo) }}</span></button>
              </template>
              <span class="rp-del-gap" aria-hidden="true"></span>
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
            <div class="sf-pills">
              <SfToggle v-model="autoOrder">自動排序</SfToggle>
              <SfToggle v-if="SHOW_CARGO" v-model="externalCargo">外掛貨櫃（只停外部貨運站）</SfToggle>
              <SfToggle v-model="popupResult">結果用跳出視窗</SfToggle>
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
    <!-- 表單：某一站要裝／卸的貨（規劃後帶進航段表的貨物規劃） -->
    <SfModal id="rp-form-cargo" v-model:open="formCargoOpen" :title="formCargoTitle" icon="bi bi-box-seam" width="900px">
      <StopCargoEditor v-if="formCargoOpen && formCargoKey" id="rp-fc" :key="formCargoKey" simple
        :entries="formCargoOf(formCargoKey)" :items="formCargoItems" :commodities="base.commodities.value" @update:entries="v => setFormCargo(formCargoKey, v)" />
    </SfModal>
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
            <!-- 顯示方式／排列方向／貨物規劃（components/RouteViewBar.vue，跟合約分配共用） -->
            <RouteViewBar v-model:view="view" v-model:flow-dir="flowDir" v-model:cargo-on="cargoPlanOn" id-prefix="rp">
              <!-- 這趟的船：看貨艙網格、算貨櫃怎麼拆（總量預設帶船的貨艙容量） -->
              <div class="ms-auto d-flex flex-wrap gap-2">
                <CargoGridButton v-if="result.ship?.id" :vehicle-uuid="result.ship.id" :name="shipLabel(result.ship)" />
                <CrateCalcButton :total="Number(result.ship?.cargo_scu) || 0" />
              </div>
            </RouteViewBar>
            <RouteMap3D v-if="view === 'map'" :plan="current" :map="result.map || {}" />
            <RouteFlowView v-if="view === 'flow'" v-model:visited="visited" :plan="current" :direction="flowDir"
              :fuel-capacity="result.ship.qt_fuel_capacity" :cargo-on="cargoPlanOn && !SHOW_CARGO" :stop-cargo="stopCargo"
              :cargo-capacity="Number(result.ship?.cargo_scu) || 0" />
            <div v-if="reorderError" class="alert alert-warning py-2 mb-2" role="alert">{{ reorderError }}</div>
            <RouteLegsTable :hide-table="view !== 'table'" v-model:visited="visited" :plan="current"
              :fuel-capacity="result.ship.qt_fuel_capacity" :show-load="SHOW_CARGO" :reorderable="!SHOW_CARGO && !reordering"
              :replannable="!SHOW_CARGO" :replanning="reordering" :places="base.places.value"
              :cargo-on="cargoPlanOn && !SHOW_CARGO" v-model:stop-cargo="stopCargo" :seed-cargo="seedCargo"
              :cargo-capacity="Number(result.ship?.cargo_scu) || 0" :commodities="base.commodities.value"
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
import PlaceCargoTags from '@/components/PlaceCargoTags.vue'
import SfChoice from '@/components/SfChoice.vue'
import SfToggle from '@/components/SfToggle.vue'
import { computed, reactive, ref, watch } from 'vue'
import PlacePicker from '@/components/PlacePicker.vue'
import FuelStartInput from '@/components/FuelStartInput.vue'
import RouteLegsTable from '@/components/RouteLegsTable.vue'
import RouteMap3D from '@/components/RouteMap3D.vue'
import RouteFlowView from '@/components/RouteFlowView.vue'
import RouteViewBar from '@/components/RouteViewBar.vue'
import { persistState, readStored } from '@/composables/useStoredState'
import { flowDirOr, viewOr } from '@/utils/routeRows'
import SfState from '@/components/SfState.vue'
import SfModal from '@/components/SfModal.vue'
import PlaceSlot from '@/components/PlaceSlot.vue'
import StopCargoEditor from '@/components/StopCargoEditor.vue'
import RouteCargoSummary from '@/components/RouteCargoSummary.vue'
import CargoGridButton from '@/components/CargoGridButton.vue'
import CrateCalcButton from '@/components/CrateCalcButton.vue'
import SystemStopsFill from '@/components/SystemStopsFill.vue'
import ShipFilter from '@/components/ShipFilter.vue'
import ShipPicker from '@/components/ShipPicker.vue'
import { useNavBase } from '@/utils/navBase'
import { fmtDist, fmtNum, fmtTime, placeLabel, placePath, shipLabel } from '@/utils/navFormat'

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


const saved = readStored(STORAGE_KEY)
// 顯示方式：航段表、總覽（一頁看完整條航線，滑鼠移上去看細節；預設）、3D 星圖；選過的記在這台瀏覽器
const view = ref(viewOr(saved.view))
const flowDir = ref(flowDirOr(saved.flowDir))
const start = reactive(newPlace(saved.start))
const endPlace = reactive(newPlace(saved.end))
const endMode = ref(['none', 'start', 'fixed'].includes(saved.endMode) ? saved.endMode : 'none')
// 途經站點：on＝加入規劃（開關）；auto＝依星系填入的（不用地點選擇器，直接顯示名稱）
const newStop = (p = {}) => ({ ...newPlace(p), on: p.on !== false, auto: !!p.auto,
  cargo: Array.isArray(p.cargo) ? p.cargo.filter(e => e && typeof e === 'object') : [] })
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
// 貨物規劃（可選，記在這台瀏覽器）：每站裝卸 {航段表列代號: [...]}，見 utils/stopCargo.js；換一份航線就清掉
const cargoPlanOn = ref(saved.cargoPlanOn === true)
const stopCargo = ref({})
// 表單先填的裝卸（起點、終點、每個途經站點的 s.cargo）：規劃時當成 seedCargo 帶進航段表
const asList = v => (Array.isArray(v) ? v.filter(e => e && typeof e === 'object') : [])
const startCargo = ref(asList(saved.startCargo))
const endCargo = ref(asList(saved.endCargo))
const seedCargo = ref(null)
const formCargoOpen = ref(false)
const formCargoKey = ref('')
const formCargoTitle = ref('貨物')
// 有填 SCU 的才算一筆（按鈕上的數字、摘要都只看這些）
const cargoCount = list => (list || []).filter(e => Number(e.scu) > 0).length
function formCargoOf(key) {
  if (key === 'start') return startCargo.value
  if (key === 'end') return endCargo.value
  return stops.find(s => `stop:${s.key}` === key)?.cargo || []
}
function setFormCargo(key, list) {
  if (key === 'start') startCargo.value = list
  else if (key === 'end') endCargo.value = list
  else {
    const s = stops.find(x => `stop:${x.key}` === key)
    if (s) s.cargo = list
  }
}
function openFormCargo(key) {
  const name = p => (p?.id && placeOf(p) ? placeLabel(placeOf(p)) : '')
  if (key === 'start') formCargoTitle.value = `起點${name(start) ? ` ${name(start)}` : ''} 的貨物`
  else if (key === 'end') formCargoTitle.value = `終點${endMode.value === 'start' ? `（回到起點）` : name(endPlace) ? ` ${name(endPlace)}` : ''} 的貨物`
  else {
    const i = stops.findIndex(x => `stop:${x.key}` === key)
    formCargoTitle.value = `站點 ${i + 1}${name(stops[i]) ? ` ${name(stops[i])}` : ''} 的貨物`
  }
  formCargoKey.value = key
  formCargoOpen.value = true
}
const formCargoItems = computed(() => [...new Set([...startCargo.value, ...endCargo.value, ...stops.flatMap(s => s.cargo)]
  .map(e => (e.item || '').trim()).filter(Boolean))])
// 規劃時：表單的裝卸 → { start, end, places: {地點 id: [...]} }（同一個地點填在好幾列的合併）
function buildSeed() {
  const places = {}
  for (const s of filledStops.value) if (s.cargo.length) places[s.id] = [...(places[s.id] || []), ...s.cargo]
  const seed = { start: startCargo.value, end: endMode.value !== 'none' ? endCargo.value : [], places }
  const any = seed.start.length || seed.end.length || Object.keys(places).length
  return any ? JSON.parse(JSON.stringify(seed)) : null
}
const resultOpen = ref(false)
watch(popupResult, (on) => { resultOpen.value = on && !!(result.value || planning.value || planError.value) })
const hubReady = computed(() => !hubOn.value || (!!hubPlace.id && hubEvery.value >= 1 && hubEvery.value <= MAX_ON))

const plain = p => ({ id: p.id, text: p.text })
const plainStop = s => ({ ...plain(s), on: s.on, auto: s.auto, cargo: s.cargo })
// 記在這台瀏覽器（composables/useStoredState.js：getter 讀到的都會自動追蹤，加設定只要改這裡跟讀的地方）
persistState(STORAGE_KEY, () => ({
  start: plain(start), end: plain(endPlace), endMode: endMode.value, stops: stops.map(plainStop),
  cargo: cargo.map(c => ({ pickup: plain(c.pickup), dropoff: plain(c.dropoff), scu: c.scu })),
  autoOrder: autoOrder.value, shipId: shipId.value, shipText: shipText.value, qdId: qdId.value,
  externalCargo: externalCargo.value, startFuel: startFuel.value,
  hubOn: hubOn.value, hub: plain(hubPlace), hubEvery: hubEvery.value, popupResult: popupResult.value,
  cargoPlanOn: cargoPlanOn.value, startCargo: startCargo.value, endCargo: endCargo.value, view: view.value, flowDir: flowDir.value,
}))

// ── 地點、船、量子引擎（跟「合約分配」共用，見 utils/navBase.js）──
const base = useNavBase(props.fetcher)
watch(() => props.active, (on) => {
  if (!on) return
  if (!base.loaded.value) base.load()
  base.loadCargoGrids()
  base.loadCommodities()
}, { immediate: true })

// ── 規劃 ─────────────────────────────────────────────────
const planning = ref(false)
const planError = ref('')
const result = ref(null)
const planKey = ref('fastest')
// 結果的顯示方式：航段表／3D 星圖

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
  // 貨物規劃：現在艙內的貨（跑完的站做完的裝卸）當成新起點的「已在艙內」
  stopCargo.value = p.cargoCarry?.length ? { start: p.cargoCarry } : {}
  seedCargo.value = null
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
  stopCargo.value = {}
  seedCargo.value = buildSeed()
  // 表單有填貨物就自動打開貨物規劃
  if (seedCargo.value) cargoPlanOn.value = true
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
  stopCargo.value = {}
  seedCargo.value = null
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
  startCargo.value = []
  endCargo.value = []
  resetResult()
}

const current = computed(() => result.value?.plans.find(p => p.key === planKey.value) || null)
const planLabel = key => result.value?.plans.find(p => p.key === key)?.label || key
</script>

<style scoped>
.rp-index { min-width: 1.5rem; text-align: center; color: var(--sf-text-muted); }
/* 起點／終點的序號：「起」「終」字樣 */
.rp-index--tag { font-weight: 700; color: var(--sf-accent-text, var(--sf-accent)); }
/* 起點那一列沒有開關：留一樣寬的空位，地點欄跟途經站點對齊 */
.rp-switch-gap { flex: 0 0 auto; width: 2.5em; }
.rp-end-mode { flex: 0 0 auto; width: auto; }
/* 每站要裝卸的貨：摘要放在那一列下面，對齊地點欄 */
/* 一列：序號、開關、地點（只佔自己需要的寬度）、中間放這站的裝卸、右邊距離／貨物／刪除；滑過整列反白，橫向好對 */
.rp-row { padding: .2rem .3rem; margin-left: -.3rem; margin-right: -.3rem; border-radius: .4rem; }
.rp-row:hover { background: rgba(var(--sf-accent-rgb), .07); }
.rp-place { flex: 0 1 auto; min-width: 0; max-width: 60%; }
/* 還在選地點（地點選擇器）時佔滿 */
.rp-place:has(.place-picker) { flex: 1 1 auto; max-width: none; }
.rp-mid { flex: 1 1 0; min-width: 0; display: flex; align-items: center; }
/* 中間剩下的空白畫一條淡淡的虛線，眼睛從站名順著看到右邊的距離、按鈕 */
.rp-mid::after { content: ''; flex: 1 1 auto; min-width: 1rem; margin: 0 .5rem; border-bottom: 1px dashed var(--sf-border); opacity: .7; }
/* 右邊對齊：距離固定寬度靠右；起點／終點沒有刪除鈕，留一樣寬的空位 */
.rp-dist { min-width: 7.5rem; justify-content: flex-end; }
.rp-del-gap { flex: 0 0 auto; width: 2.35rem; }
.rp-dist-gap { flex: 0 0 auto; width: 7.5rem; }
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
/* 手機：站點一列放不下——地點欄佔滿第一行，距離、貨物、刪除換到下一行靠右 */
@media (max-width: 767.98px) {
  .rp-row { flex-wrap: wrap; row-gap: .35rem !important; }
  .rp-row > .rp-mid + * { margin-left: auto; }
  .rp-place { flex: 1 1 calc(100% - 6rem); max-width: none; }
  .rp-mid { flex: 1 1 100%; order: 10; padding-left: 4.5rem; }
  .rp-mid::after, .rp-del-gap, .rp-dist-gap { display: none; }
  .rp-dist { min-width: 0; }
  .rp-mid:not(:has(*)) { display: none; }
}
.rp-fill { padding: .5rem; border: 1px solid var(--sf-border); border-radius: .375rem; }
.rp-finish { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .5rem;
  align-items: center; padding: .6rem 0; border-top: 1px solid var(--sf-border);
  /* 貼在視窗（或畫面）底部，航段很多時不用捲到最下面才看得到 */
  position: sticky; bottom: -1rem; z-index: 2; background: var(--sf-panel); }
.rp-finish__label { font-weight: 600; color: var(--sf-text-strong); margin-right: auto; }
</style>
