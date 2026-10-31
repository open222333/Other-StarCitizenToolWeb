<!--
  玩家頁「航線 › 合約分配」：多份運貨合約（最多 10 份，每份幾項貨物；每項貨物的取貨點、送貨點各可以好幾個，
  送貨點填 SCU，取貨點不知道各拿多少可以不填）分給多個小隊，
  算出每隊載哪些貨、照什麼順序跑（後端 POST /starmap/nav/contracts，演算法見 src/models/haul.py）。
  貨物只能送到同一份合約的送貨地點；同一份合約可以拆給不同小隊，比最大貨艙還多的貨會拆成幾趟。
  結果三種方案（最快完成／總時間最少／總油量最少）：分配表＋每隊的航段表／3D 星圖。
  表單記在這台瀏覽器（localStorage）。
-->
<template>
  <div>
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body">
        <SfState :loading="base.loading.value" :error="base.error.value"
          :empty="base.loaded.value && !base.places.value.length" empty-text="尚無地點座標資料。" @retry="base.load">
          <div class="row g-2">
            <div class="col-12">
              <div class="form-check mb-1">
                <input id="cp-common-start" v-model="commonStart" class="form-check-input" type="checkbox">
                <label class="form-check-label fw-semibold" for="cp-common-start">共同起點</label>
              </div>
              <PlacePicker v-if="commonStart" id="cp-start" label="共同起點" :places="base.places.value" :model-value="start"
                :class="{ 'cp-invalid': isBad('start') }" @update:model-value="v => Object.assign(start, v)" />
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label small fw-semibold mb-1" for="cp-end">結束</label>
              <select id="cp-end" v-model="endMode" class="form-select form-select-sm">
                <option value="none">停在最後一站</option>
                <option value="start">回到起點</option>
              </select>
            </div>
            <div class="w-100 m-0"></div>
            <div class="col-12 col-md-4">
              <label class="form-label small fw-semibold mb-1" for="cp-squads">小隊數</label>
              <input id="cp-squads" :value="squads.length" type="number" min="1" :max="MAX_SQUADS" step="1"
                class="form-control form-control-sm" @change="setSquadCount($event.target.value)">
            </div>
          </div>

          <!-- 小隊 -->
          <div class="mt-3">
            <div class="cp-section-title cp-section-title--squad mb-2"><i class="bi bi-people me-1"></i>小隊 {{ squads.length }} / {{ MAX_SQUADS }}</div>
            <ShipFilter id="cp-filter" class="mb-2" fleet-label="我的小隊只看我的機庫" />
            <div v-for="(sq, i) in squads" :key="sq.key" class="cp-box cp-box--squad mb-2">
              <div class="row g-2 align-items-center mb-1">
                <div class="col-12 col-md-4">
                  <input v-model="sq.name" type="text" maxlength="30" class="form-control form-control-sm"
                    :placeholder="`小隊 ${i + 1}`" :aria-label="`小隊 ${i + 1} 名稱`">
                </div>
                <div class="col d-flex flex-wrap align-items-center gap-2">
                  <div class="form-check mb-0">
                    <input :id="`cp-mine-${sq.key}`" v-model="sq.mine" class="form-check-input" type="checkbox">
                    <label class="form-check-label" :for="`cp-mine-${sq.key}`">我的小隊</label>
                  </div>
                  <div v-if="commonStart" class="form-check mb-0">
                    <input :id="`cp-own-start-${sq.key}`" v-model="sq.ownStart" class="form-check-input" type="checkbox">
                    <label class="form-check-label" :for="`cp-own-start-${sq.key}`">另設起點</label>
                  </div>
                  <button v-if="squads.length > 1" type="button" class="btn btn-sm btn-danger ms-auto"
                    :aria-label="`移除${squadName(sq, i)}`" @click="squads.splice(i, 1)"><i class="bi bi-trash"></i></button>
                </div>
              </div>
              <ShipPicker :id="`cp-sq-${sq.key}`" v-model:ship-id="sq.shipId" v-model:ship-text="sq.shipText"
                :class="{ 'cp-invalid': isBad(`ship-${sq.key}`) }"
                v-model:qd-id="sq.qdId" :ships="base.ships.value" :quantum-drives="base.quantumDrives.value"
                :fleet-uuids="fleetUuids" show-cargo :auto-pick="sq.mine" :fleet-filter="sq.mine" />
              <div v-if="usesOwnStart(sq)" class="mt-2">
                <label class="form-label small fw-semibold mb-1" :for="`cp-sq-start-${sq.key}`">起點</label>
                <PlacePicker :id="`cp-sq-start-${sq.key}`" :label="`${squadName(sq, i)}起點`" :places="base.places.value"
                  :class="{ 'cp-invalid': isBad(`start-${sq.key}`) }"
                  :model-value="sq.start" @update:model-value="v => Object.assign(sq.start, v)" />
              </div>
            </div>
          </div>

          <!-- 合約 -->
          <div class="mt-3">
            <div class="d-flex align-items-center gap-2 mb-1">
              <span class="cp-section-title cp-section-title--contract"><i class="bi bi-file-earmark-text me-1"></i>合約 {{ contracts.length }} / {{ MAX_CONTRACTS }}</span>
              <button type="button" class="btn btn-sm btn-success ms-auto" :disabled="contracts.length >= MAX_CONTRACTS"
                @click="contracts.push(newContract())"><i class="bi bi-plus-lg me-1"></i>加合約</button>
            </div>
            <div v-for="(c, ci) in contracts" :key="c.key" class="cp-box cp-box--contract mb-2">
              <div class="d-flex align-items-center gap-2 mb-2">
                <span class="cp-index">{{ ci + 1 }}</span>
                <input v-model="c.name" type="text" maxlength="40" class="form-control form-control-sm"
                  :placeholder="`合約 ${ci + 1}`" :aria-label="`合約 ${ci + 1} 名稱`">
                <button type="button" class="btn btn-sm btn-success text-nowrap" :disabled="c.items.length >= MAX_ITEMS"
                  @click="addItem(c)"><i class="bi bi-plus-lg me-1"></i>加貨物</button>
                <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除${contractName(c, ci)}`"
                  @click="contracts.splice(ci, 1)"><i class="bi bi-trash"></i></button>
              </div>
              <div v-for="(it, ii) in c.items" :key="it.key" class="cp-item mb-2">
                <div class="d-flex align-items-center gap-2 mb-1">
                  <AutocompleteField :id="`cp-cargo-${it.key}`" v-model="it.cargo" class="cp-cargo"
                    :search="searchCommodities" :get-label="commodityLabel" :get-meta="c => c.code || ''"
                    :min-chars="0" :debounce-ms="0"
                    :placeholder="`貨物 ${ii + 1}`" :aria-label="`${contractName(c, ci)} 貨物 ${ii + 1} 名稱`" />
                  <span class="sf-chip text-nowrap" :class="{ 'sf-chip--warn': mismatch(it) || isBad(`item-${it.key}`) }">{{ itemSummary(it) }}</span>
                  <span v-if="sameNameIn(it, ci).length" class="sf-chip sf-chip--warn">
                    {{ sameNameIn(it, ci).join('、') }} 也有同名商品</span>
                  <button type="button" class="btn btn-sm btn-danger ms-auto"
                    :aria-label="`移除${contractName(c, ci)} 貨物 ${ii + 1}`" @click="c.items.splice(ii, 1)">
                    <i class="bi bi-trash"></i></button>
                </div>
                <div v-for="side in SIDES" :key="side.key" class="mb-1">
                  <div v-for="(pt, pi) in it[side.key]" :key="pt.key" class="row g-1 align-items-center mb-1">
                    <div class="col-12 col-md-9 d-flex gap-2 align-items-center">
                      <span class="cp-tag">{{ pi === 0 ? side.label : '' }}</span>
                      <div class="flex-grow-1" :class="{ 'cp-invalid': isBad(`place-${pt.key}`) }">
                        <PlacePicker :id="`cp-${side.key}-${pt.key}`"
                          :label="`${contractName(c, ci)} 貨物 ${ii + 1} ${side.label} ${pi + 1}`"
                          :places="base.places.value" :model-value="pt.place"
                          @update:model-value="v => Object.assign(pt.place, v)" />
                      </div>
                    </div>
                    <div class="col-12 col-md-3 d-flex gap-2 align-items-center">
                      <span class="cp-tag d-md-none"></span>
                      <div class="input-group input-group-sm" :class="{ 'cp-invalid': isBad(`scu-${pt.key}`) }">
                        <input v-model.number="pt.scu" type="number" min="1" step="1" class="form-control"
                          :placeholder="autoScu(it, side.key) ?? ''"
                          :aria-label="`${contractName(c, ci)} 貨物 ${ii + 1} ${side.label} ${pi + 1} SCU`">
                        <span class="input-group-text">SCU</span>
                      </div>
                      <button v-if="it[side.key].length > 1" type="button" class="btn btn-sm btn-danger"
                        :aria-label="`移除${contractName(c, ci)} 貨物 ${ii + 1} ${side.label} ${pi + 1}`"
                        @click="it[side.key].splice(pi, 1)"><i class="bi bi-trash"></i></button>
                    </div>
                  </div>
                  <div class="d-flex">
                    <span class="cp-tag"></span>
                    <button type="button" class="btn btn-sm btn-success ms-2" :disabled="it[side.key].length >= MAX_POINTS"
                      @click="it[side.key].push(newPoint())"><i class="bi bi-plus-lg me-1"></i>加{{ side.label }}點</button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="showProblems && problems.list.length" class="alert alert-warning py-2 mt-2 mb-0" role="alert">
            <div class="fw-semibold mb-1"><i class="bi bi-exclamation-triangle me-1"></i>還沒填完：</div>
            <ul class="mb-0 ps-3">
              <li v-for="(m, i) in problems.list" :key="i">{{ m }}</li>
            </ul>
          </div>
          <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
            <span v-if="totalScu" class="sf-chip">貨物共 {{ fmtNum(totalScu) }} SCU</span>
            <div class="ms-auto d-flex gap-2">
              <button type="button" class="btn btn-sm btn-warning" @click="clearForm">
                <i class="bi bi-eraser me-1"></i>清除
              </button>
              <button type="button" class="btn btn-sm btn-primary" :disabled="planning" @click="plan">
                <i class="bi bi-diagram-3 me-1"></i>分析分配
              </button>
            </div>
          </div>
        </SfState>
      </div>
    </div>

    <SfState v-if="planning || planError || result" :loading="planning" :error="planError" :empty="false"
      loading-text="分析中…" @retry="plan">
      <div v-if="result && current" :class="cardClass">
        <div class="card-body">
          <div class="btn-group btn-group-sm flex-wrap mb-3" role="group" aria-label="方案">
            <button v-for="p in result.plans" :key="p.key" type="button" class="btn btn-subtab"
              :class="{ active: planKey === p.key }" :aria-pressed="planKey === p.key ? 'true' : 'false'"
              @click="planKey = p.key">{{ p.label }}</button>
          </div>
          <div class="d-flex flex-wrap gap-2 mb-3">
            <span class="sf-chip sf-chip--accent">全部完成 {{ fmtTime(current.totals.makespan) }}</span>
            <span class="sf-chip sf-chip--accent">各隊合計 {{ fmtTime(current.totals.time) }}</span>
            <span v-if="current.totals.fuel != null" class="sf-chip sf-chip--accent">總油量 {{ fmtNum(current.totals.fuel) }}</span>
            <span class="sf-chip">總距離 {{ fmtDist(current.totals.distance) }}</span>
            <span class="sf-chip">共 {{ result.trips }} 趟 · {{ fmtNum(result.total_scu) }} SCU</span>
            <span v-if="current.same_as" class="sf-chip">與「{{ planLabel(current.same_as) }}」相同</span>
            <span v-if="current.totals.refuels" class="sf-chip sf-chip--warn">需補充燃料 {{ current.totals.refuels }} 次</span>
            <span v-if="current.warnings.includes('fuel_short')" class="sf-chip sf-chip--warn">
              油量不足：有段落單趟就超過油箱</span>
          </div>

          <!-- 分配表 -->
          <div style="overflow-x:auto" class="mb-3">
            <table class="table table-hover align-middle mb-0 sf-stack">
              <thead class="table-light">
                <tr>
                  <th class="ps-3">合約</th>
                  <th>貨物</th>
                  <th>取貨 → 送貨</th>
                  <th class="text-end">SCU</th>
                  <th class="pe-3">小隊</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(a, i) in current.allocation" :key="i">
                  <td class="ps-3 sf-stack__title">{{ a.contract_name }}</td>
                  <td data-label="貨物">{{ a.item_name }}<span v-if="a.parts > 1" class="cp-muted"> · 第 {{ a.part }}/{{ a.parts }} 趟</span></td>
                  <td data-label="取貨 → 送貨">{{ placeLabel(a.pickup) }} → {{ placeLabel(a.dropoff) }}</td>
                  <td class="text-end" data-label="SCU">{{ fmtNum(a.scu, 1) }}</td>
                  <td class="pe-3" data-label="小隊">
                    <button type="button" class="btn btn-sm btn-info" @click="squadIndex = a.squad">
                      {{ current.squads[a.squad].name }}</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 各隊航線 -->
          <div class="btn-group btn-group-sm flex-wrap mb-2" role="group" aria-label="小隊">
            <button v-for="sq in current.squads" :key="sq.index" type="button" class="btn btn-subtab"
              :class="{ active: squadIndex === sq.index }" :aria-pressed="squadIndex === sq.index ? 'true' : 'false'"
              @click="squadIndex = sq.index">{{ sq.name }}</button>
          </div>
          <template v-if="squad">
            <div class="d-flex flex-wrap gap-2 mb-2">
              <span class="sf-chip">{{ shipLabel(squad.ship) }}</span>
              <span class="sf-chip">{{ squad.trips }} 趟 · {{ fmtNum(squad.scu) }} SCU</span>
              <template v-if="squad.plan">
                <span class="sf-chip sf-chip--accent">時間 {{ fmtTime(squad.plan.totals.time) }}</span>
                <span v-if="squad.plan.totals.fuel != null" class="sf-chip sf-chip--accent">油量 {{ fmtNum(squad.plan.totals.fuel) }}</span>
                <span class="sf-chip">距離 {{ fmtDist(squad.plan.totals.distance) }}</span>
              </template>
            </div>
            <div v-if="!squad.plan" class="cp-muted py-2">沒有分到貨物</div>
            <template v-else>
              <div class="btn-group btn-group-sm mb-2" role="group" aria-label="顯示方式">
                <button v-for="v in VIEWS" :key="v.key" type="button" class="btn btn-subtab"
                  :class="{ active: view === v.key }" :aria-pressed="view === v.key ? 'true' : 'false'"
                  @click="view = v.key"><i :class="v.icon" class="me-1"></i>{{ v.label }}</button>
              </div>
              <RouteMap3D v-if="view === 'map'" :key="`${planKey}-${squad.index}`" :plan="squad.plan" :map="result.map || {}" />
              <RouteLegsTable v-show="view === 'table'" :plan="squad.plan" :fuel-capacity="squad.ship.qt_fuel_capacity"
                show-load />
            </template>
          </template>
        </div>
      </div>
    </SfState>
  </div>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import AutocompleteField from '@/components/AutocompleteField.vue'
import PlacePicker from '@/components/PlacePicker.vue'
import RouteLegsTable from '@/components/RouteLegsTable.vue'
import RouteMap3D from '@/components/RouteMap3D.vue'
import SfState from '@/components/SfState.vue'
import ShipFilter from '@/components/ShipFilter.vue'
import ShipPicker from '@/components/ShipPicker.vue'
import { useNavBase } from '@/utils/navBase'
import { fmtDist, fmtNum, fmtTime, placeLabel, shipLabel } from '@/utils/navFormat'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card' },
  fleetUuids: { type: Array, default: () => [] },
})

// 跟後端 src/models/haul.py 一致
const MAX_CONTRACTS = 10
const MAX_ITEMS = 10
const MAX_SQUADS = 6
const MAX_POINTS = 10
const SIDES = [{ key: 'pickups', label: '取貨' }, { key: 'dropoffs', label: '送貨' }]
const STORAGE_KEY = 'sc_contracts_v1'

let keySeq = 0
const newPlace = (p = {}) => ({ id: p?.id || '', text: p?.text || '' })
// mine：「我的小隊」（用我機庫的船；選船篩選的「只看我的機庫」只套用在這種小隊）；舊存檔沒有這欄時第一隊算我的
const newSquad = (s = {}, i = -1) => ({ key: ++keySeq, name: s.name || '', shipId: s.shipId || '', shipText: s.shipText || '',
  qdId: s.qdId || '', ownStart: !!s.ownStart, start: reactive(newPlace(s.start)),
  mine: typeof s.mine === 'boolean' ? s.mine : i === 0 })
const numOrNull = v => (Number(v) > 0 ? Number(v) : null)
const newPoint = (pt = {}) => ({ key: ++keySeq, place: reactive(newPlace(pt.place)), scu: numOrNull(pt.scu) })
// 一項貨物：取貨點、送貨點各可以好幾個（舊格式 {pickup, dropoff, scu} 轉成各一個點）
function newItem(it = {}) {
  const pickups = Array.isArray(it.pickups) ? it.pickups : [{ place: it.pickup, scu: it.scu }]
  const dropoffs = Array.isArray(it.dropoffs) ? it.dropoffs : [{ place: it.dropoff, scu: it.scu }]
  return { key: ++keySeq, cargo: it.cargo || '',
    pickups: (pickups.length ? pickups : [{}]).slice(0, MAX_POINTS).map(newPoint),
    dropoffs: (dropoffs.length ? dropoffs : [{}]).slice(0, MAX_POINTS).map(newPoint) }
}
const newContract = (c = {}) => ({ key: ++keySeq, name: c.name || '',
  items: (Array.isArray(c.items) && c.items.length ? c.items : [{}]).slice(0, MAX_ITEMS).map(newItem) })

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') || {}
  } catch {
    return {}
  }
}
const saved = loadSaved()
const start = reactive(newPlace(saved.start))
const endMode = ref(saved.endMode === 'start' ? 'start' : 'none')
// 共同起點預設關閉：每個小隊各自選起點；打開後沒勾「另設起點」的小隊用共同起點
const commonStart = ref(saved.commonStart === true)
const usesOwnStart = sq => !commonStart.value || sq.ownStart
const squads = reactive((Array.isArray(saved.squads) && saved.squads.length ? saved.squads : [{}])
  .slice(0, MAX_SQUADS).map(newSquad))
const contracts = reactive((Array.isArray(saved.contracts) && saved.contracts.length ? saved.contracts : [{}])
  .slice(0, MAX_CONTRACTS).map(newContract))

const plain = p => ({ id: p.id, text: p.text })
const savePoint = pt => ({ place: plain(pt.place), scu: pt.scu })
watch([start, endMode, commonStart, squads, contracts], () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      start: plain(start), endMode: endMode.value, commonStart: commonStart.value,
      squads: squads.map(s => ({ name: s.name, shipId: s.shipId, shipText: s.shipText, qdId: s.qdId,
        ownStart: s.ownStart, start: plain(s.start), mine: s.mine })),
      contracts: contracts.map(c => ({ name: c.name, items: c.items.map(it => ({ cargo: it.cargo,
        pickups: it.pickups.map(savePoint), dropoffs: it.dropoffs.map(savePoint) })) })),
    }))
  } catch { /* 存不了就算了 */ }
}, { deep: true })

const base = useNavBase(props.fetcher)
watch(() => props.active, (on) => {
  if (!on) return
  if (!base.loaded.value) base.load()
  base.loadCommodities()
}, { immediate: true })

// 貨物：從商品資料庫選（中文、英文、縮寫都能搜），也可以直接打字
const commodityLabel = c => (c.name_zh && c.name_zh !== c.name ? `${c.name_zh}（${c.name}）` : c.name)
async function searchCommodities(q) {
  const t = (q || '').trim().toLowerCase()
  const rows = base.commodities.value.filter(c => !t || c.name.toLowerCase().includes(t)
    || (c.name_zh || '').toLowerCase().includes(t) || (c.code || '').toLowerCase() === t)
  return rows.slice(0, 50)
}

const squadName = (sq, i) => sq.name.trim() || `小隊 ${i + 1}`
const contractName = (c, i) => c.name.trim() || `合約 ${i + 1}`

function setSquadCount(value) {
  const n = Math.min(MAX_SQUADS, Math.max(1, Math.round(Number(value) || 1)))
  while (squads.length < n) squads.push(newSquad())
  squads.splice(n)
}

// 新的一項貨物：帶入上一項的取貨點（同一份合約常常是同一處取貨、送到好幾個地方）
function addItem(c) {
  const last = c.items[c.items.length - 1]
  c.items.push(newItem(last ? { pickups: last.pickups.map(pt => ({ place: plain(pt.place) })) } : {}))
}

// 有選地點的點；SCU 合計
const filledPoints = list => list.filter(pt => pt.place.id)
const sumScu = list => list.reduce((n, pt) => n + (Number(pt.scu) || 0), 0)
// SCU 規則跟後端一樣（src/models/haul.py 的 _item_points）：送貨點要填（只有一個送貨點、取貨點都有填時可省略）；
// 取貨點可以不填（每個取貨點都一定要去，沒填的平均分掉剩下的量），有填的一定拿完
const filled = pt => Number(pt.scu) > 0
function demandOf(it) {
  if (it.dropoffs.every(filled)) return sumScu(it.dropoffs)
  if (it.dropoffs.length === 1 && it.pickups.every(filled)) return sumScu(it.pickups)
  return null
}
function autoScu(it, sideKey) {
  if (sideKey === 'dropoffs') {
    return it.dropoffs.length === 1 && it.pickups.every(filled) ? sumScu(it.pickups) : null
  }
  if (it.pickups.length > 1) return '自動'
  return demandOf(it)
}
function mismatch(it) {
  const demand = demandOf(it)
  if (demand == null) return false
  const known = sumScu(it.pickups.filter(filled))
  // 有沒填的取貨點時，有填的合計要比送貨少（沒填的點也要拿得到貨）
  return it.pickups.every(filled) ? Math.abs(known - demand) > 1e-6 : known >= demand - 1e-6
}
function itemSummary(it) {
  const demand = demandOf(it)
  if (demand == null) return '— SCU'
  if (mismatch(it)) {
    const known = fmtNum(sumScu(it.pickups.filter(filled)))
    return it.pickups.every(filled) ? `取 ${known} ≠ 送 ${fmtNum(demand)} SCU` : `已填取貨 ${known} ≥ 送 ${fmtNum(demand)} SCU`
  }
  return `${fmtNum(demand)} SCU`
}

// 同名商品出現在別的合約（取貨、送貨都要分開）→ 那幾份合約的名稱
const cargoKey = text => {
  const t = (text || '').trim()
  const m = t.match(/[（(]([^（）()]+)[）)]$/)
  return (m ? m[1] : t).trim().toLowerCase()
}
const cargoContracts = computed(() => {
  const map = new Map()
  contracts.forEach((c, ci) => c.items.forEach((it) => {
    const key = cargoKey(it.cargo)
    if (!key) return
    if (!map.has(key)) map.set(key, new Set())
    map.get(key).add(ci)
  }))
  return map
})
function sameNameIn(it, ci) {
  const set = cargoContracts.value.get(cargoKey(it.cargo))
  return set ? [...set].filter(x => x !== ci).map(x => contractName(contracts[x], x)) : []
}

const filledContracts = computed(() => contracts
  .map((c, ci) => ({ name: contractName(c, ci),
    items: c.items.filter(it => !blankItem(it))
      .map(it => ({ cargo: it.cargo.trim(),
        pickups: filledPoints(it.pickups).map(pt => ({ place: pt.place.id, scu: numOrNull(pt.scu) })),
        dropoffs: filledPoints(it.dropoffs).map(pt => ({ place: pt.place.id, scu: numOrNull(pt.scu) })) })) }))
  .filter(c => c.items.length))
const totalScu = computed(() => contracts.reduce((n, c) => n + c.items.reduce((m, it) => m + (demandOf(it) || 0), 0), 0))

// ── 沒填完的欄位：按「分析分配」時列出來並標紅框（bad 是欄位代號）──
// 整項空白的貨物（沒選地點、沒填 SCU、沒貨物名稱）直接略過，不算沒填
const blankItem = it => !it.cargo.trim() && [...it.pickups, ...it.dropoffs].every(pt => !pt.place.id && !filled(pt))
const problems = computed(() => {
  const list = [], bad = new Set()
  const add = (msg, ...keys) => { list.push(msg); keys.forEach(k => bad.add(k)) }
  if (squads.some(s => !usesOwnStart(s)) && !start.id) add('共同起點：未選地點', 'start')
  squads.forEach((sq, i) => {
    if (!sq.shipId) add(`${squadName(sq, i)}：未選船`, `ship-${sq.key}`)
    if (usesOwnStart(sq) && !sq.start.id) add(`${squadName(sq, i)}：未選起點`, `start-${sq.key}`)
  })
  let items = 0
  contracts.forEach((c, ci) => c.items.forEach((it, ii) => {
    if (blankItem(it)) return
    items++
    const where = `${contractName(c, ci)} › ${it.cargo.trim() || `貨物 ${ii + 1}`}`
    for (const side of SIDES) {
      it[side.key].forEach((pt, pi) => {
        if (!pt.place.id) add(`${where}：${side.label} ${pi + 1} 未選地點`, `place-${pt.key}`)
      })
    }
    if (demandOf(it) == null) {
      it.dropoffs.forEach((pt, pi) => {
        if (!filled(pt)) add(`${where}：送貨 ${pi + 1} 未填 SCU`, `scu-${pt.key}`)
      })
    } else if (mismatch(it)) {
      add(`${where}：${itemSummary(it)}`, `item-${it.key}`, ...it.pickups.filter(filled).map(pt => `scu-${pt.key}`))
    }
  }))
  if (!items) add('合約：至少要填一項貨物')
  return { list, bad }
})
const showProblems = ref(false)
const isBad = key => showProblems.value && problems.value.bad.has(key)

// ── 分析 ─────────────────────────────────────────────────
const planning = ref(false)
const planError = ref('')
const result = ref(null)
const planKey = ref('time')
const squadIndex = ref(0)
const VIEWS = [
  { key: 'table', label: '航段表', icon: 'bi bi-list-ol' },
  { key: 'map', label: '3D 星圖', icon: 'bi bi-globe2' },
]
const view = ref('table')

async function plan() {
  if (problems.value.list.length) {
    showProblems.value = true
    // 捲到第一個沒填的欄位
    nextTick(() => document.querySelector('.cp-invalid')?.scrollIntoView({ block: 'center', behavior: 'smooth' }))
    return
  }
  showProblems.value = false
  planning.value = true
  planError.value = ''
  const res = await props.fetcher('/starmap/nav/contracts', {
    method: 'POST',
    body: JSON.stringify({
      start: commonStart.value ? start.id : '',
      end_mode: endMode.value,
      squads: squads.map((s, i) => ({ name: squadName(s, i), ship: s.shipId, quantum_drive: s.qdId,
        start: usesOwnStart(s) ? s.start.id : '' })),
      contracts: filledContracts.value,
    }),
  })
  const body = res ? await res.json().catch(() => null) : null
  planning.value = false
  if (!res?.ok || !body?.success) {
    result.value = null
    planError.value = body?.message || '分析失敗。'
    return
  }
  result.value = body.data
  if (!result.value.plans.some(p => p.key === planKey.value)) planKey.value = result.value.plans[0]?.key
  const busy = current.value?.squads.find(s => s.plan)
  squadIndex.value = busy ? busy.index : 0
}

function clearForm() {
  Object.assign(start, newPlace())
  endMode.value = 'none'
  contracts.splice(0, contracts.length, newContract())
  result.value = null
  planError.value = ''
}

const current = computed(() => result.value?.plans.find(p => p.key === planKey.value) || null)
const squad = computed(() => current.value?.squads[squadIndex.value] || null)
const planLabel = key => result.value?.plans.find(p => p.key === key)?.label || key
</script>

<style scoped>
.cp-box { border: 1px solid var(--sf-border); border-radius: .5rem; padding: .75rem; }
/* 小隊、合約用不同底色和左邊色條區分 */
.cp-box--squad {
  background: rgba(var(--sf-accent-2-rgb), .08);
  border-color: rgba(var(--sf-accent-2-rgb), .35);
  border-left: 4px solid var(--sf-accent-2);
}
.cp-box--contract {
  background: rgba(var(--sf-accent-rgb), .07);
  border-color: rgba(var(--sf-accent-rgb), .35);
  border-left: 4px solid var(--sf-accent);
}
.cp-section-title { font-weight: 600; }
.cp-section-title--squad { color: var(--sf-accent-2-text, var(--sf-accent-2)); }
.cp-section-title--contract { color: var(--sf-accent-text, var(--sf-accent)); }
.cp-item { background: var(--sf-panel); border: 1px solid var(--sf-border); border-radius: .5rem; padding: .5rem; }
.cp-index { min-width: 1.5rem; text-align: center; color: var(--sf-text-muted); }
.cp-tag { min-width: 2.5rem; color: var(--sf-text-muted); }
.cp-muted { color: var(--sf-text-muted); }
/* 沒填完的欄位：紅框 */
.cp-invalid :deep(.form-control) {
  border-color: var(--bs-danger) !important;
  box-shadow: 0 0 0 .15rem rgba(var(--bs-danger-rgb), .25);
}
.cp-cargo { flex: 1 1 14rem; max-width: 22rem; }
.cp-scu { max-width: 9rem; }
</style>
