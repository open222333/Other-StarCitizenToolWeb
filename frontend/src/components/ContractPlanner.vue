<!--
  玩家頁「航線 › 合約分配」：多份運貨合約（最多 10 份，每份幾項貨物；每項貨物的取貨點、送貨點各可以好幾個，
  送貨點填 SCU，取貨點不知道各拿多少可以不填：不猜數量，同一隊一趟去完這些取貨點再送）分給多個小隊，
  算出每隊載哪些貨、照什麼順序跑（後端 POST /starmap/nav/contracts，演算法見 src/models/haul.py）。
  貨物只能送到同一份合約的送貨地點；同一份合約可以拆給不同小隊，比最大貨艙還多的貨會拆成幾趟。
  結果四種方案（最快完成／總時間最少／總油量最少／站點平均：每個站點只給一隊、各隊航程平均）：
  分配表＋每隊的航段表／3D 星圖。
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
            <div class="col-12">
              <div class="form-check mb-1">
                <input id="cp-common-drop" v-model="commonDrop" class="form-check-input" type="checkbox">
                <label class="form-check-label fw-semibold" for="cp-common-drop">共同送貨點</label>
              </div>
              <template v-if="commonDrop">
                <div class="cp-side-head">
                  <span class="cp-side-label">送貨點</span>
                  <button type="button" class="btn btn-sm btn-success" :disabled="commonDrops.length >= MAX_POINTS"
                    @click="commonDrops.push(newCommonDrop())"><i class="bi bi-plus-lg me-1"></i>加送貨點</button>
                  <button type="button" class="btn btn-sm" :class="fillOpen.has('common') ? 'btn-secondary' : 'btn-primary'"
                    :aria-expanded="fillOpen.has('common')" @click="toggleFill('common')">
                    <i class="bi bi-stars me-1"></i>依星系填入</button>
                  <span v-if="fillNotes.common" class="sf-chip sf-chip--warn">{{ fillNotes.common }}</span>
                </div>
                <div v-if="fillOpen.has('common')" class="cp-fill mb-2">
                  <SystemStopsFill id="cp-fill-common" :places="base.places.value"
                    @fill="rows => fillList('common', commonDrops, rows, newCommonDrop)" />
                </div>
                <div v-for="(cd, di) in commonDrops" :key="cd.key" class="cp-point" :class="{ 'cp-point--off': !cd.on }">
                  <span class="cp-index">{{ di + 1 }}</span>
                  <div class="form-check form-switch mb-0 cp-switch">
                    <input v-model="cd.on" class="form-check-input" type="checkbox" role="switch"
                      :aria-label="`共同送貨點 ${di + 1} 加入規劃`">
                  </div>
                  <div class="cp-point__place" :class="{ 'cp-invalid': isBad(`cdrop-${cd.key}`) }">
                    <PlacePicker :id="`cp-cdrop-${cd.key}`" :label="`共同送貨點 ${di + 1}`" :places="base.places.value"
                      :model-value="cd.place" @update:model-value="v => Object.assign(cd.place, v)" />
                  </div>
                  <button v-if="commonDrops.length > 1" type="button" class="btn btn-sm btn-danger"
                    :aria-label="`移除共同送貨點 ${di + 1}`" @click="commonDrops.splice(di, 1)"><i class="bi bi-trash"></i></button>
                </div>
              </template>
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label small fw-semibold mb-1" for="cp-end">結束</label>
              <select id="cp-end" v-model="endMode" class="form-select form-select-sm">
                <option value="none">停在最後一站</option>
                <option value="start">回到起點</option>
              </select>
            </div>
            <div class="w-100 m-0"></div>
            <div class="col-12">
              <label class="form-label small fw-semibold mb-1" for="cp-fuel">起始油量</label>
              <FuelStartInput id="cp-fuel" v-model="startFuel" />
            </div>
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
              <!-- 標題列：編號徽章、隊名、我的小隊／另設起點、刪除 -->
              <div class="cp-squad-head">
                <span class="cp-squad-no">{{ i + 1 }}</span>
                <input v-model="sq.name" type="text" maxlength="30" class="form-control form-control-sm cp-squad-name"
                  :placeholder="`小隊 ${i + 1}`" :aria-label="`小隊 ${i + 1} 名稱`">
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
              <ShipPicker :id="`cp-sq-${sq.key}`" v-model:ship-id="sq.shipId" v-model:ship-text="sq.shipText"
                :class="{ 'cp-invalid': isBad(`ship-${sq.key}`) }"
                v-model:qd-id="sq.qdId" :ships="base.ships.value" :quantum-drives="base.quantumDrives.value"
                :fleet-uuids="fleetUuids" show-cargo :auto-pick="sq.mine" :fleet-filter="sq.mine" />
              <div v-if="usesOwnStart(sq)" class="mt-2">
                <label class="cp-field-label" :for="`cp-sq-start-${sq.key}`"><i class="bi bi-geo-alt me-1"></i>起點</label>
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
              <span v-if="contracts.some(c => !c.on)" class="sf-chip">規劃 {{ contracts.filter(c => c.on).length }} 份</span>
              <button type="button" class="btn btn-sm btn-success ms-auto" :disabled="contracts.length >= MAX_CONTRACTS"
                @click="contracts.push(newContract())"><i class="bi bi-plus-lg me-1"></i>加合約</button>
            </div>
            <div v-for="(c, ci) in contracts" :key="c.key" class="cp-box cp-box--contract mb-2" :class="{ 'cp-off': !c.on }">
              <div class="d-flex align-items-center gap-2 mb-2">
                <span class="cp-index">{{ ci + 1 }}</span>
                <!-- 開關：關掉＝這次不規劃（內容保留） -->
                <div class="form-check form-switch mb-0 cp-switch">
                  <input :id="`cp-on-${c.key}`" v-model="c.on" class="form-check-input" type="checkbox" role="switch"
                    :aria-label="`${contractName(c, ci)} 加入規劃`">
                </div>
                <input v-model="c.name" type="text" maxlength="40" class="form-control form-control-sm"
                  :placeholder="`合約 ${ci + 1}`" :aria-label="`合約 ${ci + 1} 名稱`">
                <button type="button" class="btn btn-sm btn-success text-nowrap" :disabled="c.items.length >= MAX_ITEMS"
                  @click="addItem(c)"><i class="bi bi-plus-lg me-1"></i>加貨物</button>
                <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除${contractName(c, ci)}`"
                  @click="contracts.splice(ci, 1)"><i class="bi bi-trash"></i></button>
              </div>
              <div v-for="(it, ii) in c.items" v-show="c.on" :key="it.key" class="cp-item mb-2">
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
                <div v-for="side in SIDES" :key="side.key" class="cp-side">
                  <!-- 標題列：取貨點／送貨點＋加點、依星系填入（在清單上方） -->
                  <div class="cp-side-head">
                    <span class="cp-side-label" :class="`cp-side-label--${side.key}`">{{ side.label }}點</span>
                    <template v-if="!locked(side)">
                      <button type="button" class="btn btn-sm btn-success" :disabled="it[side.key].length >= MAX_POINTS"
                        @click="it[side.key].push(newPoint())"><i class="bi bi-plus-lg me-1"></i>加{{ side.label }}點</button>
                      <button type="button" class="btn btn-sm" :class="fillOpen.has(fillKey(it, side)) ? 'btn-secondary' : 'btn-primary'"
                        :aria-expanded="fillOpen.has(fillKey(it, side))" @click="toggleFill(fillKey(it, side))">
                        <i class="bi bi-stars me-1"></i>依星系填入</button>
                      <span v-if="fillNotes[fillKey(it, side)]" class="sf-chip sf-chip--warn">{{ fillNotes[fillKey(it, side)] }}</span>
                    </template>
                    <span v-else class="sf-chip">共同送貨點</span>
                  </div>
                  <div v-if="!locked(side) && fillOpen.has(fillKey(it, side))" class="cp-fill mb-2">
                    <SystemStopsFill :id="`cp-fill-${fillKey(it, side)}`" :places="base.places.value"
                      @fill="rows => fillList(fillKey(it, side), it[side.key], rows, newPoint)" />
                  </div>
                  <!-- 每個點一列：序號、地點、SCU、刪除（跟航線規劃的站點同一種格式） -->
                  <div v-for="(pt, pi) in it[side.key]" :key="pt.key" class="cp-point" :class="{ 'cp-point--off': !isOn(pt) }">
                    <span class="cp-index">{{ pi + 1 }}</span>
                    <!-- 開關：關掉＝這次不去這個點（共同送貨點的開關在上方共同送貨點那裡） -->
                    <div class="form-check form-switch mb-0 cp-switch">
                      <input v-if="locked(side)" class="form-check-input" type="checkbox" role="switch" :checked="isOn(pt)" disabled
                        :aria-label="`${contractName(c, ci)} 貨物 ${ii + 1} ${side.label} ${pi + 1} 加入規劃`">
                      <input v-else v-model="pt.on" class="form-check-input" type="checkbox" role="switch"
                        :aria-label="`${contractName(c, ci)} 貨物 ${ii + 1} ${side.label} ${pi + 1} 加入規劃`">
                    </div>
                    <div v-if="locked(side)" class="cp-point__place cp-common-place">
                      {{ pt.place.text || `共同送貨點 ${pi + 1}` }}</div>
                    <div v-else class="cp-point__place" :class="{ 'cp-invalid': isBad(`place-${pt.key}`) }">
                      <PlacePicker :id="`cp-${side.key}-${pt.key}`"
                        :label="`${contractName(c, ci)} 貨物 ${ii + 1} ${side.label} ${pi + 1}`"
                        :places="base.places.value" :model-value="pt.place"
                        @update:model-value="v => Object.assign(pt.place, v)" />
                    </div>
                    <div class="input-group input-group-sm cp-point__scu" :class="{ 'cp-invalid': isBad(`scu-${pt.key}`) }">
                      <input v-model.number="pt.scu" type="number" min="1" step="1" class="form-control"
                        :placeholder="autoScu(it, side.key) ?? ''"
                        :aria-label="`${contractName(c, ci)} 貨物 ${ii + 1} ${side.label} ${pi + 1} SCU`">
                      <span class="input-group-text">SCU</span>
                    </div>
                    <button v-if="!locked(side)" type="button" class="btn btn-sm btn-danger" :disabled="it[side.key].length <= 1"
                      :aria-label="`移除${contractName(c, ci)} 貨物 ${ii + 1} ${side.label} ${pi + 1}`"
                      @click="it[side.key].splice(pi, 1)"><i class="bi bi-trash"></i></button>
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
          <!-- 站點平均：各隊站點數、航程；有貨物相連的站點組數比隊數少時，有些隊分不到 -->
          <div v-if="current.key === 'stations'" class="d-flex flex-wrap gap-2 mb-3">
            <span v-for="sq in current.squads" :key="sq.index" class="sf-chip">
              {{ sq.name }}：{{ sq.stations }} 站 · {{ fmtDist(sq.plan?.totals.distance || 0) }}</span>
            <span v-if="GROUP_MODE_NOTE[current.group_mode]" class="sf-chip sf-chip--warn">
              {{ GROUP_MODE_NOTE[current.group_mode] }}</span>
            <span v-if="current.groups < current.squads.length" class="sf-chip sf-chip--warn">
              有貨物相連的站點只分成 {{ current.groups }} 組，只能分給 {{ current.groups }} 隊</span>
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
                  <td data-label="取貨 → 送貨">
                    <template v-if="a.unknown">{{ (a.pickups || []).map(placeLabel).join('、') }}<span class="cp-muted">（數量未知，一趟取完）</span></template>
                    <template v-else>{{ placeLabel(a.pickup) }}</template> → {{ placeLabel(a.dropoff) }}</td>
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
              <span class="sf-chip">{{ squad.trips }} 趟 · {{ fmtNum(squad.scu) }} SCU · {{ squad.stations }} 站</span>
              <span v-if="squad.edited" class="sf-chip sf-chip--accent">已手動調整順序</span>
              <span v-if="squad.ctx?.replanned" class="sf-chip sf-chip--accent">
                已從 {{ placeLabel(squad.plan?.start) }} 重新規劃</span>
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
              <div v-if="reorderError" class="alert alert-warning py-2 mb-2" role="alert">{{ reorderError }}</div>
              <RouteLegsTable v-show="view === 'table'" :visited="visitedOf(squad)"
                :plan="squad.plan" :fuel-capacity="squad.ship.qt_fuel_capacity" show-load :reorderable="!reordering"
                replannable :replanning="reordering" :places="base.places.value"
                @update:visited="v => setVisitedOf(squad, v)" @reorder="legs => reorder(squad, legs)"
                @replan="p => replan(squad, p)" />
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
import SystemStopsFill from '@/components/SystemStopsFill.vue'
import FuelStartInput from '@/components/FuelStartInput.vue'
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
const MAX_POINTS = 30
// 站點平均：站點太集中時放寬的分組方式（後端 haul._pick_station_groups）
const GROUP_MODE_NOTE = {
  pickup: '站點太集中：取貨站由多隊共用',
  dropoff: '站點太集中：送貨站由多隊共用',
  task: '站點太集中：每趟貨各自分，同一站可能多隊都去',
}
const SIDES = [{ key: 'pickups', label: '取貨' }, { key: 'dropoffs', label: '送貨' }]
const STORAGE_KEY = 'sc_contracts_v1'

// 每項貨物的取／送貨「依星系填入」面板（key＝貨物 key-取送）；填入後收起，超過上限的在旁邊提示
const fillOpen = reactive(new Set())
const fillNotes = reactive({})
const fillKey = (it, side) => `${it.key}-${side.key}`
function toggleFill(k) {
  if (fillOpen.has(k)) fillOpen.delete(k)
  else fillOpen.add(k)
  delete fillNotes[k]
}
// list 的每一列都有 place；make({ place }) 建新的一列
function fillList(k, list, rows, make) {
  const have = new Set(list.map(pt => pt.place.id).filter(Boolean))
  let skipped = 0
  for (const p of rows) {
    if (have.has(p.id)) continue
    const place = { id: p.id, text: placeLabel(p) }
    const blank = list.find(pt => !pt.place.id && !pt.place.text)
    if (blank) Object.assign(blank.place, place)
    else if (list.length < MAX_POINTS) list.push(make({ place }))
    else {
      skipped++
      continue
    }
    have.add(p.id)
  }
  fillOpen.delete(k)
  if (skipped) fillNotes[k] = `已滿 ${MAX_POINTS} 個，${skipped} 個沒有填入`
  else delete fillNotes[k]
}

let keySeq = 0
const newPlace = (p = {}) => ({ id: p?.id || '', text: p?.text || '' })
// mine：「我的小隊」（用我機庫的船；選船篩選的「只看我的機庫」只套用在這種小隊）；舊存檔沒有這欄時第一隊算我的
const newSquad = (s = {}, i = -1) => ({ key: ++keySeq, name: s.name || '', shipId: s.shipId || '', shipText: s.shipText || '',
  qdId: s.qdId || '', ownStart: !!s.ownStart, start: reactive(newPlace(s.start)),
  mine: typeof s.mine === 'boolean' ? s.mine : i === 0 })
const numOrNull = v => (Number(v) > 0 ? Number(v) : null)
// on：加入規劃（開關；關掉的點保留內容、不送去分析）
const newPoint = (pt = {}) => ({ key: ++keySeq, place: reactive(newPlace(pt.place)), scu: numOrNull(pt.scu),
  on: pt.on !== false })
// 一項貨物：取貨點、送貨點各可以好幾個（舊格式 {pickup, dropoff, scu} 轉成各一個點）
function newItem(it = {}) {
  const pickups = Array.isArray(it.pickups) ? it.pickups : [{ place: it.pickup, scu: it.scu }]
  const dropoffs = Array.isArray(it.dropoffs) ? it.dropoffs : [{ place: it.dropoff, scu: it.scu }]
  return { key: ++keySeq, cargo: it.cargo || '',
    pickups: (pickups.length ? pickups : [{}]).slice(0, MAX_POINTS).map(newPoint),
    dropoffs: (dropoffs.length ? dropoffs : [{}]).slice(0, MAX_POINTS).map(newPoint) }
}
// on：加入規劃（開關；關掉的合約保留內容、不送去分析、不檢查）
const newContract = (c = {}) => ({ key: ++keySeq, name: c.name || '', on: c.on !== false,
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
// 各隊的起始油量 { mode: pct／amount, value }，value 空的＝滿油（百分比照各自油箱算）
const startFuel = ref({ mode: saved.startFuel?.mode === 'amount' ? 'amount' : 'pct',
  value: Number(saved.startFuel?.value) >= 0 && saved.startFuel?.value !== null ? Number(saved.startFuel.value) : null })
const fuelParam = () => (startFuel.value.value == null ? null : { ...startFuel.value })
// 共同起點預設關閉：每個小隊各自選起點；打開後沒勾「另設起點」的小隊用共同起點
const commonStart = ref(saved.commonStart === true)
const usesOwnStart = sq => !commonStart.value || sq.ownStart
const squads = reactive((Array.isArray(saved.squads) && saved.squads.length ? saved.squads : [{}])
  .slice(0, MAX_SQUADS).map(newSquad))
const contracts = reactive((Array.isArray(saved.contracts) && saved.contracts.length ? saved.contracts : [{}])
  .slice(0, MAX_CONTRACTS).map(newContract))

const plain = p => ({ id: p.id, text: p.text })

// 共同送貨點：打開後所有合約的每項貨物都送到這組地點（地點共用同一個物件），各項貨物只各填各點的 SCU；
// 各項貨物的送貨點用 ck 對到共同送貨點，關掉時各自留一份地點副本
const newCommonDrop = (d = {}) => ({ key: ++keySeq, place: reactive(newPlace(d.place)), on: d.on !== false })
// 點有沒有加入規劃：共同送貨點帶出來的點（common）跟著共同送貨點的開關
const isOn = pt => (pt.common ? pt.common.on : pt.on) !== false
const onPickups = it => it.pickups.filter(isOn)
const onDropoffs = it => it.dropoffs.filter(isOn)
const commonDrop = ref(saved.commonDrop === true)
const commonDrops = reactive((Array.isArray(saved.commonDrops) && saved.commonDrops.length ? saved.commonDrops : [{}])
  .slice(0, MAX_POINTS).map(newCommonDrop))
const locked = side => commonDrop.value && side.key === 'dropoffs'
function syncDrops() {
  for (const c of contracts) {
    for (const it of c.items) {
      const used = new Set()
      const pick = test => {
        const d = it.dropoffs.find(x => !used.has(x) && test(x))
        if (d) used.add(d)
        return d
      }
      const rows = commonDrops.map(cd => {
        const old = pick(x => x.ck === cd.key) || (cd.place.id ? pick(x => !x.ck && x.place.id === cd.place.id) : null)
        return { key: old?.key ?? ++keySeq, ck: cd.key, place: cd.place, scu: old?.scu ?? null, on: true, common: cd }
      })
      it.dropoffs.splice(0, it.dropoffs.length, ...rows)
    }
  }
}
function unsyncDrops() {
  for (const c of contracts) {
    for (const it of c.items) {
      it.dropoffs.forEach(d => {
        d.place = reactive(newPlace(plain(d.place)))
        d.on = isOn(d)
        delete d.ck
        delete d.common
      })
    }
  }
}
const dropSig = () => (commonDrop.value
  ? `${commonDrops.map(cd => cd.key).join(',')}|${contracts.map(c => c.items.map(it => it.key).join(',')).join(';')}` : '')
watch(dropSig, (sig, old) => {
  if (sig) syncDrops()
  else if (old) unsyncDrops()
}, { immediate: true })

const savePoint = pt => ({ place: plain(pt.place), scu: pt.scu, on: isOn(pt) })
watch([start, endMode, commonStart, startFuel, squads, contracts, commonDrop, commonDrops], () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      start: plain(start), endMode: endMode.value, commonStart: commonStart.value, startFuel: startFuel.value,
      commonDrop: commonDrop.value, commonDrops: commonDrops.map(cd => ({ place: plain(cd.place), on: cd.on })),
      squads: squads.map(s => ({ name: s.name, shipId: s.shipId, shipText: s.shipText, qdId: s.qdId,
        ownStart: s.ownStart, start: plain(s.start), mine: s.mine })),
      contracts: contracts.map(c => ({ name: c.name, on: c.on, items: c.items.map(it => ({ cargo: it.cargo,
        pickups: it.pickups.map(savePoint), dropoffs: it.dropoffs.map(savePoint) })) })),
    }))
  } catch { /* 存不了就算了 */ }
}, { deep: true })

const base = useNavBase(props.fetcher)
watch(() => props.active, (on) => {
  if (!on) return
  if (!base.loaded.value) base.load()
  base.loadCommodities()
  base.loadCargoGrids()
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
// 共同送貨點時，SCU 留空的送貨點＝這項貨物不送那裡（至少要填一個；只有一個送貨點時照原規則）
// 下面都只算開關打開的點（onPickups／onDropoffs）
const dropsOf = (it) => {
  const drops = onDropoffs(it)
  return commonDrop.value && drops.some(filled) ? drops.filter(filled) : drops
}
function demandOf(it) {
  const drops = dropsOf(it), picks = onPickups(it)
  if (!drops.length || !picks.length) return null
  if (drops.every(filled)) return sumScu(drops)
  if (onDropoffs(it).length === 1 && picks.every(filled)) return sumScu(picks)
  return null
}
function autoScu(it, sideKey) {
  const picks = onPickups(it)
  if (sideKey === 'dropoffs') {
    return onDropoffs(it).length === 1 && picks.length && picks.every(filled) ? sumScu(picks) : null
  }
  if (picks.length > 1) return '未知'
  return demandOf(it)
}
function mismatch(it) {
  const demand = demandOf(it)
  if (demand == null) return false
  const picks = onPickups(it)
  const known = sumScu(picks.filter(filled))
  // 有沒填的取貨點時，有填的合計要比送貨少（沒填的點也要拿得到貨）
  return picks.every(filled) ? Math.abs(known - demand) > 1e-6 : known >= demand - 1e-6
}
function itemSummary(it) {
  const demand = demandOf(it)
  if (demand == null) return '— SCU'
  if (mismatch(it)) {
    const known = fmtNum(sumScu(onPickups(it).filter(filled)))
    return onPickups(it).every(filled) ? `取 ${known} ≠ 送 ${fmtNum(demand)} SCU` : `已填取貨 ${known} ≥ 送 ${fmtNum(demand)} SCU`
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
  contracts.forEach((c, ci) => c.on && c.items.forEach((it) => {
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
  .map((c, ci) => ({ on: c.on, name: contractName(c, ci),
    items: c.items.filter(it => !blankItem(it))
      .map(it => ({ cargo: it.cargo.trim(),
        pickups: filledPoints(onPickups(it)).map(pt => ({ place: pt.place.id, scu: numOrNull(pt.scu) })),
        dropoffs: filledPoints(dropsOf(it)).map(pt => ({ place: pt.place.id, scu: numOrNull(pt.scu) })) })) }))
  .filter(c => c.on && c.items.length)
  .map(({ on, ...c }) => c))
const totalScu = computed(() => contracts.filter(c => c.on)
  .reduce((n, c) => n + c.items.reduce((m, it) => m + (demandOf(it) || 0), 0), 0))

// ── 沒填完的欄位：按「分析分配」時列出來並標紅框（bad 是欄位代號）──
// 整項空白的貨物（沒選地點、沒填 SCU、沒貨物名稱）直接略過，不算沒填
const blankItem = it => !it.cargo.trim() && it.pickups.every(pt => !pt.place.id && !filled(pt))
  && it.dropoffs.every(pt => (commonDrop.value || !pt.place.id) && !filled(pt))
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
    if (!c.on || blankItem(it)) return
    items++
    const where = `${contractName(c, ci)} › ${it.cargo.trim() || `貨物 ${ii + 1}`}`
    for (const side of SIDES) {
      if (!it[side.key].some(isOn)) {
        add(`${where}：${side.label}點都關掉了，至少開一個`)
        continue
      }
      if (locked(side)) continue
      it[side.key].forEach((pt, pi) => {
        if (isOn(pt) && !pt.place.id) add(`${where}：${side.label} ${pi + 1} 未選地點`, `place-${pt.key}`)
      })
    }
    if (!onPickups(it).length || !onDropoffs(it).length) return
    if (demandOf(it) == null && commonDrop.value && onDropoffs(it).length > 1) {
      add(`${where}：送貨 SCU 至少填一個`, ...onDropoffs(it).map(pt => `scu-${pt.key}`))
    } else if (demandOf(it) == null) {
      it.dropoffs.forEach((pt, pi) => {
        if (isOn(pt) && !filled(pt)) add(`${where}：送貨 ${pi + 1} 未填 SCU`, `scu-${pt.key}`)
      })
    } else if (mismatch(it)) {
      add(`${where}：${itemSummary(it)}`, `item-${it.key}`, ...onPickups(it).filter(filled).map(pt => `scu-${pt.key}`))
    }
  }))
  if (!items) add(contracts.some(c => c.on) ? '合約：至少要填一項貨物' : '合約：全部都關掉了，至少開一份')
  else if (commonDrop.value) {
    commonDrops.forEach((cd, di) => {
      if (cd.on && !cd.place.id) add(`共同送貨點 ${di + 1}：未選地點`, `cdrop-${cd.key}`)
    })
  }
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

// ── 航段表：已去過（每個方案、每隊各自記）、拖拉調整順序後重算那一隊 ──
const visitedMap = reactive({})
const visitedOf = sq => visitedMap[`${planKey.value}-${sq.index}`] || []
const setVisitedOf = (sq, v) => { visitedMap[`${planKey.value}-${sq.index}`] = v }
const reordering = ref(false)
const reorderError = ref('')
let resultEndMode = 'none'
let resultStartFuel = null

// 一隊目前航線的出發條件：起點、最後回去的地點、起始油量、出發時貨艙裡已有的貨（中途重新規劃後會變）
function ctxOf(sq) {
  return sq.ctx || { start: sq.start.id, end: resultEndMode === 'start' ? sq.start.id : '',
    fuel: resultStartFuel, onboard: [] }
}
// 航段 → 後端的站（取貨／送貨／途經）
const stepOf = l => (l.action === 'stop' ? { place: l.to.id, kind: 'stop' } : {
  place: l.to.id, kind: l.action, scu: l.scu, cargo: l.cargo, contract: l.contract, contract_name: l.contract_name,
  item: l.item, item_name: l.item_name, item_named: l.item_named, ...(l.scu_unknown ? { scu_unknown: true } : {}) })
const isStep = l => ['pickup', 'dropoff', 'stop'].includes(l.action)

async function reorder(sq, legs) {
  reordering.value = true
  reorderError.value = ''
  const ctx = ctxOf(sq)
  const res = await props.fetcher('/starmap/nav/sequence', {
    method: 'POST',
    body: JSON.stringify({ start: ctx.start, end: ctx.end, ship: sq.ship.id, quantum_drive: sq.ship.qd_uuid,
      name: sq.name, steps: legs.filter(isStep).map(stepOf), start_fuel: ctx.fuel, onboard: ctx.onboard }),
  })
  const body = res ? await res.json().catch(() => null) : null
  reordering.value = false
  if (!res?.ok || !body?.success) {
    reorderError.value = body?.message || '重新計算失敗。'
    return
  }
  sq.plan = body.data.plan
  sq.edited = true
  recomputeTotals(current.value)
}

// 中途重新規劃：從目前位置出發，還沒做的取貨／送貨＋還沒去的插入站＋新插入的站重新排
async function replan(sq, p) {
  const ctx = ctxOf(sq)
  // 貨艙裡現在有的：原本就在的＋已經取過的趟（用 cargo 號碼配對），量＝這趟還沒送的合計
  // （收集任務的取貨量不知道、送貨可能好幾個點，所以看還剩多少要送，不看取了多少）
  const left = new Map()
  for (const l of p.remaining) {
    if (l.action === 'dropoff') left.set(String(l.cargo), (left.get(String(l.cargo)) || 0) + (l.scu || 0))
  }
  const byCargo = new Map()
  for (const o of [...ctx.onboard, ...p.done.filter(l => l.action === 'pickup')]) {
    byCargo.set(String(o.cargo), { cargo: o.cargo, contract: o.contract, item: o.item, item_name: o.item_name })
  }
  const onboard = [...byCargo.entries()].filter(([c]) => left.get(c) > 0)
    .map(([c, o]) => ({ ...o, scu: left.get(c) }))
  const steps = p.remaining.filter(l => l.action === 'pickup' || l.action === 'dropoff').map(stepOf)
  const stops = [...new Set([...p.remaining.filter(l => l.action === 'stop').map(l => l.to.id), ...(p.inserts || [])])]
  const fuel = p.fuel != null ? { mode: 'amount', value: p.fuel } : ctx.fuel
  reordering.value = true
  reorderError.value = ''
  const res = await props.fetcher('/starmap/nav/replan', {
    method: 'POST',
    body: JSON.stringify({ start: p.current.id, end: ctx.end, ship: sq.ship.id, quantum_drive: sq.ship.qd_uuid,
      name: sq.name, steps, onboard: onboard.map(o => String(o.cargo)), stops, start_fuel: fuel }),
  })
  const body = res ? await res.json().catch(() => null) : null
  reordering.value = false
  if (!res?.ok || !body?.success) {
    reorderError.value = body?.message || '重新規劃失敗。'
    return
  }
  sq.plan = body.data.plan
  sq.ctx = { start: p.current.id, end: ctx.end, fuel, onboard, replanned: true }
  sq.edited = false
  setVisitedOf(sq, [])
  recomputeTotals(current.value)
}

// 某一隊的航線改了：重算這個方案的合計
function recomputeTotals(p) {
  const plans = p.squads.map(s => s.plan).filter(Boolean)
  const times = plans.map(x => x.totals.time)
  const fuels = plans.map(x => x.totals.fuel)
  p.totals = { makespan: times.length ? Math.max(...times) : 0, time: times.reduce((a, b) => a + b, 0),
    fuel: fuels.some(f => f == null) ? null : fuels.reduce((a, b) => a + b, 0),
    distance: plans.reduce((a, x) => a + x.totals.distance, 0),
    refuels: plans.reduce((a, x) => a + (x.refuel_stops?.length || 0), 0) }
  p.warnings = [...new Set(plans.flatMap(x => x.warnings))].sort()
  p.same_as = null
}

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
  reorderError.value = ''
  Object.keys(visitedMap).forEach(k => delete visitedMap[k])
  resultEndMode = endMode.value
  resultStartFuel = fuelParam()
  const res = await props.fetcher('/starmap/nav/contracts', {
    method: 'POST',
    body: JSON.stringify({
      start: commonStart.value ? start.id : '',
      end_mode: endMode.value,
      start_fuel: resultStartFuel,
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
  commonDrops.splice(0, commonDrops.length, newCommonDrop())
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
.cp-switch { padding-left: 2.5em; }
.cp-switch .form-check-input { width: 2.2em; height: 1.2em; cursor: pointer; }
/* 關掉的點：變淡（開關本身保持清楚） */
.cp-point--off > :not(.cp-switch) { opacity: .45; }
/* 關掉的合約：只留標題列、變淡 */
.cp-off { opacity: .6; }
/* 小隊：標題列（編號徽章＋隊名）與欄位標題 */
.cp-squad-head { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .75rem; margin-bottom: .6rem;
  padding-bottom: .5rem; border-bottom: 1px solid rgba(var(--sf-accent-2-rgb), .3); }
.cp-squad-no { display: inline-flex; align-items: center; justify-content: center; width: 1.9rem; height: 1.9rem;
  border-radius: 50%; background: var(--sf-accent-2); color: #0b1020; font-weight: 700; flex: 0 0 auto; }
.cp-squad-name { flex: 1 1 10rem; max-width: 16rem; font-weight: 600; }
.cp-field-label { display: block; margin: .25rem 0 .3rem; font-weight: 600; color: var(--sf-accent-2-text, var(--sf-accent-2)); }
/* 取貨點／送貨點：標題列在上（加點、依星系填入），每個點一列 */
.cp-side { margin-top: .5rem; }
.cp-side-head { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem .5rem; margin-bottom: .35rem; }
.cp-side-label { min-width: 4rem; font-weight: 600; }
.cp-side-label--pickups { color: var(--sf-accent-text, var(--sf-accent)); }
.cp-side-label--dropoffs { color: var(--bs-success); }
.cp-point { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem .5rem; margin-bottom: .35rem; }
.cp-point__place { flex: 1 1 18rem; min-width: 0; }
.cp-point__scu { flex: 0 0 9rem; width: 9rem; }
.cp-muted { color: var(--sf-text-muted); }
.cp-common-place { padding: .25rem .5rem; border: 1px solid var(--sf-border); border-radius: .375rem; }
.cp-fill { padding: .5rem; border: 1px solid var(--sf-border); border-radius: .375rem; }
/* 沒填完的欄位：紅框 */
.cp-invalid :deep(.form-control) {
  border-color: var(--bs-danger) !important;
  box-shadow: 0 0 0 .15rem rgba(var(--bs-danger-rgb), .25);
}
.cp-cargo { flex: 1 1 14rem; max-width: 22rem; }
.cp-scu { max-width: 9rem; }
</style>
