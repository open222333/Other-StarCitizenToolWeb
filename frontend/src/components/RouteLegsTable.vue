<!--
  航線的航段表（RoutePlanner.vue、ContractPlanner.vue 共用）：出發點＋每一站的目的地、動作、經過的 OM／跳躍點、
  距離、時間、油量、剩油與補充燃料提示。plan 是後端 nav._build_plan 的結果。

  同一站連續的動作（後面幾段距離是 0）併成一列，動作逐項列出（同一份合約、同一種貨物、同一個動作的 SCU 加總）。
  補充燃料標在「出發前」那一站：plan.refuel_stops 的 k 是第 k 段的出發點；單段就超過油箱（fuel_short）也標在出發站。
  同名貨物分屬不同合約（同一站一起處理，或貨艙裡同時有）時提醒：取貨時分開放置、送貨時分開繳交。

  站號本身是「已去過」按鈕（大顆，點一下打勾、再點取消；v-model:visited 存列的代號；勾了的列變淡，
  第一個還沒去的列標成「下一站」）；reorderable 時最左邊一欄可以拖拉（或用上下按鈕）調整順序，
  發 reorder（新順序的 plan.legs），由上層重算。
  起點那一列、終點那一列不能移動。
  cargoOn 時（貨物規劃，可選）多一欄「貨艙」：每一站有「貨物」按鈕跳出視窗設定裝／卸哪些貨物、幾 SCU、最大貨櫃
  （components/StopCargoEditor.vue），列出每筆拆成哪些貨櫃、離開這站時貨艙用量（超過容量標紅）；v-model:stopCargo＝{列代號: [裝卸]}。
  seedCargo（航線規劃表單先填的裝卸）或 seedFromActions（合約分配：取貨＝裝、送貨＝卸）會先帶入，之後在視窗裡調整。
  replannable 時表格下面有「中途插入站點」按鈕，跳出視窗設定要插入的站＋「重新規劃未完成的行程」：最後一個勾了「已去過」的站之前都算跑完了，
  發 replan（目前位置、目前油量、跑完的／還沒跑的 plan.legs、要插入的地點 id 清單 inserts），由上層重算。可以插入好幾個站。
-->
<template>
  <div style="overflow-x:auto">
    <table v-show="!hideTable" class="table table-hover align-middle mb-0 sf-stack rlt">
      <thead class="table-light">
        <tr>
          <th v-if="reorderable" class="ps-2 text-center text-nowrap">順序</th>
          <th :class="reorderable ? '' : 'ps-3'">目的地</th>
          <th>動作</th>
          <th v-if="showLoad && !cargoOn" class="text-end">載貨</th>
          <th v-if="cargoOn" class="text-end">貨艙</th>
          <th class="text-end">距離</th>
          <th class="text-end">時間</th>
          <th class="text-end">油量</th>
          <th class="text-end pe-3">剩油</th>
        </tr>
      </thead>
      <tbody>
        <tr :class="{ 'rlt-visited': isVisited(START_KEY) }">
          <td v-if="reorderable" class="ps-2 rlt-order"></td>
          <td class="sf-stack__title" :class="reorderable ? '' : 'ps-3'">
            <div class="rlt-dest">
              <button type="button" class="rlt-mark" :class="{ 'is-done': isVisited(START_KEY) }"
                :aria-pressed="isVisited(START_KEY) ? 'true' : 'false'" aria-label="起點已去過"
                @click="setVisited(START_KEY, !isVisited(START_KEY))">
                <i v-if="isVisited(START_KEY)" class="bi bi-check-lg"></i>
                <template v-else>
                  <span class="rlt-mark__num">0</span><i class="bi bi-check-lg rlt-mark__peek" aria-hidden="true"></i>
                  <span class="rlt-mark__badge" aria-hidden="true"><i class="bi bi-check"></i></span>
                </template>
              </button>
              <div class="flex-grow-1">
                <div class="fw-semibold">{{ placeLabel(plan.start) }}</div>
                <div class="rlt-path">{{ placePath(plan.start) }}</div>
                <div v-if="traitsOf(plan.start).length" class="d-flex flex-wrap gap-1 mt-1">
                  <span v-for="t in traitsOf(plan.start)" :key="t.key" class="sf-chip rlt-trait" :class="`rlt-trait--${t.key}`">
                    <i :class="t.icon" class="me-1" aria-hidden="true"></i>{{ t.label }}</span>
                </div>
              </div>
            </div>
          </td>
          <td data-label="動作">
            <div v-if="!table.start" class="rlt-action"><span class="sf-chip text-nowrap">出發</span></div>
            <div v-for="(a, j) in table.start?.actions || []" :key="j" class="rlt-action">
              <span class="sf-chip text-nowrap" :class="actionClass(a.action)">{{ actionLabel(a) }}</span>
              <span v-if="a.contract_name" class="rlt-cargo">{{ a.contract_name }} · {{ a.item_name }}</span>
            </div>
            <CargoSummary v-if="cargoOn" :entries="entriesOf(START_KEY)" :shorts="flow.get(START_KEY)?.shorts" />
            <div v-if="startFuel.mixed.length || startFuel.refuel || startFuel.short" class="d-flex flex-wrap gap-1 mt-1">
              <span v-for="m in startFuel.mixed" :key="m.name" class="sf-chip sf-chip--warn">
                {{ mixedLabel(m) }}</span>
              <span v-if="startFuel.refuel" class="sf-chip sf-chip--warn text-nowrap">需補充燃料</span>
              <span v-if="startFuel.short" class="sf-chip sf-chip--warn text-nowrap">下一段超過油箱</span>
            </div>
          </td>
          <td v-if="showLoad && !cargoOn" class="text-end" data-label="載貨">{{ fmtNum(table.start?.load_after || 0) }}</td>
          <td v-if="cargoOn" class="text-end" data-label="貨艙">
            <CargoCell :flow="flow.get(START_KEY)" :capacity="cargoCapacity" :count="entriesOf(START_KEY).length"
              :label="`起點 ${placeLabel(plan.start)} 的貨物`" @open="openCargo(START_KEY, plan.start)" />
          </td>
          <td class="text-end" data-label="距離">—</td>
          <td class="text-end" data-label="時間">—</td>
          <td class="text-end" data-label="油量">—</td>
          <td class="text-end pe-3" data-label="剩油">{{ startFuelText }}</td>
        </tr>
        <tr v-for="(row, i) in table.rows" :key="row.key"
          :class="{ 'rlt-visited': isVisited(row.key), 'rlt-next': nextKey === row.key,
                    'rlt-dragging': dragFrom === i, 'rlt-over': dragOver === i && dragFrom !== i }"
          :draggable="canMove(i)" @dragstart="onDragStart(i, $event)" @dragover.prevent="dragOver = i"
          @drop.prevent="onDrop(i)" @dragend="dragFrom = dragOver = -1">
          <td v-if="reorderable" class="ps-2 rlt-order">
            <div v-if="canMove(i)" class="rlt-order__box">
              <button type="button" class="btn btn-sm btn-info" :disabled="!canMove(i - 1)"
                :aria-label="`第 ${i + 1} 站往前`" @click="move(i, i - 1)"><i class="bi bi-chevron-up"></i></button>
              <i class="bi bi-grip-horizontal rlt-grip" aria-hidden="true"></i>
              <button type="button" class="btn btn-sm btn-info" :disabled="!canMove(i + 1)"
                :aria-label="`第 ${i + 1} 站往後`" @click="move(i, i + 1)"><i class="bi bi-chevron-down"></i></button>
            </div>
          </td>
          <td class="sf-stack__title" :class="reorderable ? '' : 'ps-3'">
            <div class="rlt-dest">
              <button type="button" class="rlt-mark"
                :class="{ 'is-done': isVisited(row.key), 'is-hint': showHint && nextKey === row.key }"
                :aria-pressed="isVisited(row.key) ? 'true' : 'false'" :aria-label="`第 ${i + 1} 站已去過`"
                @click="setVisited(row.key, !isVisited(row.key))">
                <i v-if="isVisited(row.key)" class="bi bi-check-lg"></i>
                <template v-else>
                  <span class="rlt-mark__num">{{ i + 1 }}</span><i class="bi bi-check-lg rlt-mark__peek" aria-hidden="true"></i>
                  <span class="rlt-mark__badge" aria-hidden="true"><i class="bi bi-check"></i></span>
                </template>
              </button>
              <div class="flex-grow-1">
                <div class="fw-semibold">
                  {{ placeLabel(row.to) }}
                  <span v-if="nextKey === row.key" class="sf-chip sf-chip--accent ms-1">下一站</span>
                </div>
                <div class="rlt-path">{{ placePath(row.to) }}</div>
                <div v-if="traitsOf(row.to).length" class="d-flex flex-wrap gap-1 mt-1">
                  <span v-for="t in traitsOf(row.to)" :key="t.key" class="sf-chip rlt-trait" :class="`rlt-trait--${t.key}`">
                    <i :class="t.icon" class="me-1" aria-hidden="true"></i>{{ t.label }}</span>
                </div>
                <div v-if="row.via.length" class="d-flex flex-wrap gap-1 mt-1">
                  <span v-for="(v, j) in row.via" :key="j" class="sf-chip"
                    :class="{ 'sf-chip--accent': v.kind === 'jump' }">
                    {{ v.kind === 'jump' ? '跳躍' : '經' }} {{ placeLabel(v.place) }}
                  </span>
                </div>
              </div>
            </div>
          </td>
          <td data-label="動作">
            <div v-for="(a, j) in row.actions" :key="j" class="rlt-action">
              <span class="sf-chip text-nowrap" :class="actionClass(a.action)">{{ actionLabel(a) }}</span>
              <span v-if="a.contract_name" class="rlt-cargo">{{ a.contract_name }} · {{ a.item_name }}</span>
            </div>
            <CargoSummary v-if="cargoOn" :entries="entriesOf(row.key)" :shorts="flow.get(row.key)?.shorts" />
            <div v-if="row.mixed.length || row.refuel || row.short" class="d-flex flex-wrap gap-1 mt-1">
              <span v-for="m in row.mixed" :key="m.name" class="sf-chip sf-chip--warn">
                {{ mixedLabel(m) }}</span>
              <span v-if="row.refuel" class="sf-chip sf-chip--warn text-nowrap">需補充燃料</span>
              <span v-if="row.short" class="sf-chip sf-chip--warn text-nowrap">下一段超過油箱</span>
            </div>
          </td>
          <td v-if="showLoad && !cargoOn" class="text-end text-nowrap" data-label="載貨">{{ fmtNum(row.load_after) }}</td>
          <td v-if="cargoOn" class="text-end" data-label="貨艙">
            <CargoCell :flow="flow.get(row.key)" :capacity="cargoCapacity" :count="entriesOf(row.key).length"
              :label="`第 ${i + 1} 站 ${placeLabel(row.to)} 的貨物`" @open="openCargo(row.key, row.to)" />
          </td>
          <td class="text-end text-nowrap" data-label="距離">{{ row.moved ? fmtDist(row.distance) : '—' }}</td>
          <td class="text-end text-nowrap" data-label="時間">{{ row.moved ? fmtTime(row.time) : '—' }}</td>
          <td class="text-end text-nowrap" data-label="油量">
            {{ row.fuel != null && row.moved ? fmtNum(row.fuel, row.fuel < 10 ? 1 : 0) : '—' }}</td>
          <td class="text-end text-nowrap pe-3" data-label="剩油" :class="{ 'sf-bad': row.fuel_short }">
            {{ fuelLeft(row) }}<template v-if="row.refuel"> → 補滿</template></td>
        </tr>
      </tbody>
    </table>
    <div v-if="replannable" class="d-flex flex-wrap align-items-center gap-2 mt-2">
      <button type="button" class="btn btn-sm btn-info" aria-haspopup="dialog" :disabled="replanning" @click="insertOpen = true">
        <i class="bi bi-signpost-2 me-1"></i>中途插入站點</button>
      <span class="sf-chip mb-0">目前位置 {{ placeLabel(progress.current) }}</span>
      <span v-if="progress.fuel != null && fuelCapacity" class="sf-chip mb-0">
        油量 {{ fmtNum(progress.fuel) }}（{{ Math.round(progress.fuel / fuelCapacity * 100) }}%）</span>
    </div>
    <!-- 視窗 Teleport 到 body（航段表可能已經在航線結果視窗裡），外面包 .scifi-page 才吃得到主題 -->
    <Teleport to="body">
      <div class="scifi-page rlt-host">
        <SfModal v-if="replannable" :id="`${uid}-insert`" v-model:open="insertOpen" title="中途插入站點" icon="bi bi-signpost-2" width="760px">
          <div class="rlt-insert">
          <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
            <span class="sf-chip mb-0">目前位置 {{ placeLabel(progress.current) }}</span>
            <span v-if="progress.fuel != null && fuelCapacity" class="sf-chip mb-0">
              油量 {{ fmtNum(progress.fuel) }}（{{ Math.round(progress.fuel / fuelCapacity * 100) }}%）</span>
            <span class="small text-muted">最後一個勾了「已去過」的站之前都算跑完了；插入的站跟還沒去的站一起重新排序。</span>
          </div>
          <!-- 可以插入好幾個站：每個一列，右邊移除；全部跟還沒去的站一起重新排序 -->
          <div v-for="(ins, i) in inserts" :key="ins.key" class="d-flex align-items-center gap-2 mb-1">
            <span class="rlt-replan__no">{{ i + 1 }}</span>
            <div class="flex-grow-1 rlt-replan__place">
              <PlacePicker :id="`${uid}-insert-${ins.key}`" :label="`插入站點 ${i + 1} `" :places="places" :model-value="ins"
                @update:model-value="v => Object.assign(ins, v)" />
            </div>
            <button v-if="inserts.length > 1 || ins.id || ins.text" type="button" class="btn btn-sm btn-danger"
              :aria-label="`移除插入站點 ${i + 1}`" @click="removeInsert(i)"><i class="bi bi-trash"></i></button>
          </div>
          <div class="d-flex flex-wrap align-items-center gap-2 mt-1">
            <button type="button" class="btn btn-sm btn-success" :disabled="inserts.length >= MAX_INSERTS"
              @click="inserts.push(newInsert())"><i class="bi bi-plus-lg me-1"></i>加插入站點</button>
            <button type="button" class="btn btn-sm btn-primary ms-auto" :disabled="replanning" @click="replan">
              <i class="bi bi-arrow-repeat me-1"></i>重新規劃未完成的行程
            </button>
          </div>
          </div>
        </SfModal>
        <SfModal v-if="cargoOn" :id="`${uid}-cargo`" v-model:open="cargoOpen" :title="cargoTitle" icon="bi bi-box-seam" width="900px">
          <StopCargoEditor v-if="cargoOpen && cargoKey" :id="`${uid}-cg`" :key="cargoKey" :entries="entriesOf(cargoKey)"
            :arriving="flow.get(cargoKey)?.arriving || {}" :capacity="cargoCapacity" :items="allItems" :commodities="commodities"
            @update:entries="v => setEntries(cargoKey, v)" />
        </SfModal>
      </div>
    </Teleport>
  </div>
</template>

<script>
import { ref as moduleRef } from 'vue'

// 「已去過」引導有沒有看過（記在這台瀏覽器，所有航段表共用）
const HINT_KEY = 'sc_route_mark_hint_v1'
function readHint() {
  try {
    return localStorage.getItem(HINT_KEY) === '1'
  } catch {
    return false
  }
}
const hintSeen = moduleRef(readHint())
function markHintSeen() {
  if (hintSeen.value) return
  hintSeen.value = true
  try {
    localStorage.setItem(HINT_KEY, '1')
  } catch { /* 存不了就算了 */ }
}
</script>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import PlacePicker from '@/components/PlacePicker.vue'
import SfModal from '@/components/SfModal.vue'
import StopCargoEditor from '@/components/StopCargoEditor.vue'
import CargoCell from '@/components/RouteCargoCell.vue'
import CargoSummary from '@/components/RouteCargoSummary.vue'
import { cargoFlow, carryEntries, newCargoEntry } from '@/utils/stopCargo'
import { actionClass, actionLabel, buildRouteRows, norm, traitsOf } from '@/utils/routeRows'
import { fmtDist, fmtNum, fmtTime, placeLabel, placePath } from '@/utils/navFormat'

const props = defineProps({
  plan: { type: Object, required: true },
  fuelCapacity: { type: Number, default: null },
  showLoad: { type: Boolean, default: false },
  // 已去過的列（列的代號，見 rowKey）
  visited: { type: Array, default: () => [] },
  // 可以拖拉調整順序（發 reorder，由上層重算）
  reorderable: { type: Boolean, default: false },
  // 可以中途插入站點、重新規劃未完成的行程（發 replan，由上層重算）；places 是插入站點的選單
  replannable: { type: Boolean, default: false },
  replanning: { type: Boolean, default: false },
  places: { type: Array, default: () => [] },
  // 只藏表格（切到總覽／3D 星圖時）：下面的「中途插入站點」、貨物視窗照樣能用
  hideTable: { type: Boolean, default: false },
  // 貨物規劃（可選）：每站裝卸 {列代號: [{ key, action, item, scu, max }]}、貨艙容量（0＝不檢查超載）
  cargoOn: { type: Boolean, default: false },
  stopCargo: { type: Object, default: () => ({}) },
  cargoCapacity: { type: Number, default: 0 },
  // 商品資料庫（貨物名稱自動完成）
  commodities: { type: Array, default: () => [] },
  // 預先帶入的裝卸（航線規劃表單填的）：{ start: [...], end: [...], places: {地點 id: [...]} }；換一個物件才再帶一次
  seedCargo: { type: Object, default: null },
  // 合約分配：直接把每站的取貨／送貨（合約動作）帶成裝／卸；maxCrateOf(動作) 給最大貨櫃
  seedFromActions: { type: Boolean, default: false },
  maxCrateOf: { type: Function, default: null },
})
const emit = defineEmits(['update:visited', 'reorder', 'replan', 'update:stopCargo'])
const uid = `rlt-${Math.random().toString(36).slice(2, 8)}`

// ── 中途重新規劃：最後一個勾了「已去過」的站（含）之前都算跑完 ──
const MAX_INSERTS = 10
let insertSeq = 0
const newInsert = () => ({ key: ++insertSeq, id: '', text: '' })
const inserts = reactive([newInsert()])
function removeInsert(i) {
  inserts.splice(i, 1)
  if (!inserts.length) inserts.push(newInsert())
}
const progress = computed(() => {
  const rows = table.value.rows
  let last = -1
  rows.forEach((r, i) => { if (isVisited(r.key)) last = i })
  const startDone = last >= 0 || isVisited(START_KEY)
  const startLegs = table.value.start?.legs || []
  const done = [...(startDone ? startLegs : []), ...rows.slice(0, last + 1).flatMap(r => r.legs)]
  const remaining = [...(startDone ? [] : startLegs), ...rows.slice(last + 1).flatMap(r => r.legs)]
    .filter(l => l.action !== 'end')
  const row = last >= 0 ? rows[last] : null
  const fuel = row ? (row.refuel ? props.fuelCapacity : row.fuel_after) : props.plan.start_fuel
  return { current: row ? row.to : props.plan.start, fuel: fuel ?? null, done, remaining,
    startDone, lastKey: row ? row.key : (startDone ? START_KEY : '') }
})
const insertOpen = ref(false)
function replan() {
  const ids = [...new Set(inserts.map(x => x.id).filter(Boolean))]
  // 貨物規劃：跑完的站做完的裝卸，現在艙內有什麼一起帶過去（新航線起點的「已在艙內」）
  const p = progress.value
  const carry = props.cargoOn ? carryEntries(flow.value.get(p.lastKey)?.leaving || {}) : []
  const startEntries = props.cargoOn && !p.startDone ? entriesOf(START_KEY) : []
  emit('replan', { ...p, inserts: ids, cargoCarry: [...carry, ...startEntries] })
  insertOpen.value = false
}

// ── 貨物規劃（可選）：每一站的裝卸，依航線順序累加 ──
const entriesOf = key => props.stopCargo?.[key] || []
function setEntries(key, list) {
  const next = { ...(props.stopCargo || {}) }
  if (list.length) next[key] = list
  else delete next[key]
  emit('update:stopCargo', next)
}
const flow = computed(() => cargoFlow([START_KEY, ...table.value.rows.map(r => r.key)], props.stopCargo, props.cargoCapacity))
const allItems = computed(() => [...new Set(Object.values(props.stopCargo || {}).flat().map(e => (e.item || '').trim()).filter(Boolean))])

const cargoOpen = ref(false)
const cargoKey = ref('')
const cargoTitle = ref('貨物')
function openCargo(key, place) {
  cargoKey.value = key
  cargoTitle.value = `${placeLabel(place)} 的貨物`
  cargoOpen.value = true
}
// 換了一份航線（重新規劃成功）就清掉插入的站點
watch(() => props.plan, () => inserts.splice(0, inserts.length, newInsert()))

// ── 已去過 ──
const START_KEY = 'start'
const visitedSet = computed(() => new Set(props.visited))
const isVisited = key => visitedSet.value.has(key)
function setVisited(key, on) {
  const next = new Set(props.visited)
  if (on) markHintSeen()
  if (on) next.add(key)
  else next.delete(key)
  emit('update:visited', [...next])
}
// 第一次使用的引導：還沒在這台瀏覽器標記過任何一站時，「下一站」的站號外圈會閃（點過一次就不再閃）
const showHint = computed(() => !hintSeen.value && !props.visited.length)
// 第一個還沒去的列＝下一站
const nextKey = computed(() => table.value.rows.find(r => !isVisited(r.key))?.key || '')

// ── 調整順序：起點那一列不在 rows 裡；終點（action end）固定在最後、回指定站（action hub）由後端每 N 站插入 ──
const dragFrom = ref(-1)
const dragOver = ref(-1)
const canMove = i => props.reorderable && i >= 0 && i < table.value.rows.length
  && !table.value.rows[i].legs.some(l => l.action === 'end' || l.action === 'hub')
function move(from, to) {
  if (!canMove(from) || !canMove(to) || from === to) return
  const rows = [...table.value.rows]
  const [row] = rows.splice(from, 1)
  rows.splice(to, 0, row)
  emit('reorder', [...(table.value.start?.legs || []), ...rows.flatMap(r => r.legs)])
}
function onDragStart(i, event) {
  dragFrom.value = i
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', String(i))
}
function onDrop(i) {
  if (dragFrom.value >= 0) move(dragFrom.value, i)
  dragFrom.value = dragOver.value = -1
}

const refuelBefore = k => !!props.plan.refuel_stops?.includes(k)
const shortAt = k => !!props.plan.legs[k]?.fuel_short
// 起點那一列：在起點就地取貨的動作併進來
const startFuel = computed(() => {
  const s = table.value.start
  return s ? { refuel: s.refuel || refuelBefore(0), short: s.short, mixed: s.mixed }
    : { refuel: refuelBefore(0), short: shortAt(0), mixed: [] }
})

const table = computed(() => buildRouteRows(props.plan))

const mixedLabel = m => (m.kind === 'dropoff'
  ? `送貨：${m.name} 分屬 ${m.contracts.join('、')}，請分開繳交`
  : `取貨：${m.name} 分屬 ${m.contracts.join('、')}，請分開放置`)

// 起點的油量：後端 plan.start_fuel（起始油量設定），沒有或滿油就寫「滿油」
const startFuelText = computed(() => {
  const cap = props.fuelCapacity, f = props.plan.start_fuel
  if (!cap) return '—'
  if (f == null || f >= cap - 1e-9) return '滿油'
  return `${fmtNum(f)}（${Math.round(f / cap * 100)}%）`
})

function fuelLeft(row) {
  const cap = props.fuelCapacity
  if (row.fuel_after == null || !cap) return '—'
  return `${fmtNum(row.fuel_after)}（${Math.max(0, Math.round(row.fuel_after / cap * 100))}%）`
}

// 預先帶入：每個來源（表單的 seedCargo，或合約分配的這份 plan）只帶一次，而且只補還沒有設定的站
const seededTokens = new WeakSet()
// 合約分配：數量未知的取貨（只知道送多少）→ 用這份航線同一份合約、同一種貨物「送貨合計－已知取貨」估，給第一個未知的取貨點
let unknownLeft = new Map()
const actionKey = a => `${a.contract}|${norm(a.item_name)}`
function estimateUnknown(rows) {
  const left = new Map()
  for (const a of rows.flatMap(r => r?.actions || [])) {
    if (!a.contract_name) continue
    const k = actionKey(a)
    if (a.action === 'dropoff') left.set(k, (left.get(k) || 0) + (Number(a.scu) || 0))
    else if (a.action === 'pickup' && !a.unknown) left.set(k, (left.get(k) || 0) - (Number(a.scu) || 0))
  }
  unknownLeft = left
}
function scuOf(a) {
  if (a.action !== 'pickup' || !a.unknown || Number(a.scu) > 0) return Number(a.scu) || 0
  const k = actionKey(a)
  const v = Math.max(0, unknownLeft.get(k) || 0)
  unknownLeft.set(k, 0)
  return v
}
function seedEntries(row, isStart) {
  if (props.seedFromActions) {
    return (row?.actions || []).filter(a => a.contract_name && (a.action === 'pickup' || a.action === 'dropoff'))
      .map(a => ({ a, scu: scuOf(a) })).filter(x => x.scu > 0)
      .map(({ a, scu }) => newCargoEntry({ action: a.action === 'pickup' ? 'load' : 'unload', item: a.item_name, scu,
        max: props.maxCrateOf?.(a) || 32 }))
  }
  const seed = props.seedCargo
  if (isStart) return seed.start || []
  if (row.legs.some(l => l.action === 'end')) return seed.end || []
  if (row.legs.every(l => l.action === 'stop')) return seed.places?.[row.to.id] || []
  return []
}
watch(() => [props.cargoOn, props.seedCargo, props.plan, table.value], () => {
  const token = props.seedFromActions ? props.plan : props.seedCargo
  if (!props.cargoOn || !token || seededTokens.has(token)) return
  seededTokens.add(token)
  const next = { ...(props.stopCargo || {}) }
  const usedPlaces = new Set()
  if (props.seedFromActions) estimateUnknown([table.value.start, ...table.value.rows])
  let changed = false
  const put = (key, list) => {
    if (!list?.length || next[key]?.length) return
    next[key] = list.map(e => newCargoEntry(e))
    changed = true
  }
  put(START_KEY, seedEntries(table.value.start, true))
  for (const row of table.value.rows) {
    // 表單同一個地點只帶到第一次經過的那一站
    if (!props.seedFromActions && row.legs.every(l => l.action === 'stop')) {
      if (usedPlaces.has(row.to.id)) continue
      usedPlaces.add(row.to.id)
    }
    put(row.key, seedEntries(row, false))
  }
  if (changed) emit('update:stopCargo', next)
}, { immediate: true })
</script>

<style scoped>
/* 站號＝「已去過」按鈕：大顆好按，勾了變成打勾 */
.rlt-dest { display: flex; align-items: flex-start; gap: .65rem; }
.rlt-mark {
  position: relative; flex: 0 0 auto; width: 2.6rem; height: 2.6rem; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center;
  font-size: 1.05rem; font-weight: 600; line-height: 1;
  color: var(--sf-text);
  /* 長得像按鈕：有底色、上亮下暗、帶一點陰影 */
  background: linear-gradient(180deg, rgba(255, 255, 255, .10), rgba(0, 0, 0, .12)), var(--sf-chip-bg);
  box-shadow: 0 2px 4px rgba(0, 0, 0, .35), inset 0 1px 0 rgba(255, 255, 255, .12);
  border: 2px solid var(--sf-border-hi); cursor: pointer;
  transition: background-color .15s, border-color .15s, color .15s, transform .1s, box-shadow .15s;
}
.rlt-mark:active { transform: scale(.92); box-shadow: 0 1px 2px rgba(0, 0, 0, .35); }
/* 右下角的小勾徽章：像還沒打勾的勾選框 */
.rlt-mark__badge {
  position: absolute; right: -.3rem; bottom: -.3rem; width: 1.15rem; height: 1.15rem; border-radius: 50%;
  display: inline-flex; align-items: center; justify-content: center; font-size: .85rem;
  color: var(--sf-text-muted); background: var(--sf-bg-2); border: 1.5px solid var(--sf-border-hi);
}
.rlt-mark__peek { display: none; font-size: 1.35rem; }
/* 滑鼠移過去：預告按下去的樣子（數字換成打勾） */
@media (hover: hover) {
  .rlt-mark:not(.is-done):hover { border-color: var(--sf-accent); color: var(--sf-accent-text, var(--sf-accent)); }
  .rlt-mark:not(.is-done):hover .rlt-mark__num { display: none; }
  .rlt-mark:not(.is-done):hover .rlt-mark__peek { display: inline-block; }
  .rlt-mark:not(.is-done):hover .rlt-mark__badge { color: var(--sf-accent-text, var(--sf-accent)); border-color: var(--sf-accent); }
}
/* 第一次使用：下一站外圈閃動 */
.rlt-mark.is-hint::after {
  content: ''; position: absolute; inset: -2px; border-radius: 50%; pointer-events: none;
  border: 2px solid var(--sf-accent); animation: rlt-pulse 1.6s ease-out infinite;
}
@keyframes rlt-pulse {
  0% { transform: scale(1); opacity: .9; }
  100% { transform: scale(1.75); opacity: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .rlt-mark.is-hint::after { animation: none; transform: scale(1.3); opacity: .6; }
}
.rlt-mark.is-done { color: rgb(var(--bs-success-rgb)); background: rgba(var(--bs-success-rgb), .16); border-color: rgb(var(--bs-success-rgb)); font-size: 1.35rem; }
.rlt-next .rlt-mark { border-color: var(--sf-accent); box-shadow: 0 0 0 3px rgba(var(--sf-accent-rgb), .25); }
/* 順序欄（最左）：往前、拖拉握把、往後 */
.rlt-order { width: 3.25rem; }
.rlt-order__box { display: inline-flex; flex-direction: column; align-items: center; gap: .15rem; }
.rlt-order__box .btn { padding: .05rem .45rem; line-height: 1.2; }
/* 手機（表格變卡片）：順序按鈕放到卡片右上角、橫排、按鈕加大；站名讓出位置 */
@media (max-width: 767.98px) {
  .rlt tbody tr { position: relative; }
  .rlt td.rlt-order { position: absolute; top: .75rem; right: .75rem; width: auto; }
  .rlt td.rlt-order:empty { display: none !important; }
  .rlt-order__box { flex-direction: row; gap: .4rem; }
  .rlt-order__box .btn { padding: .35rem .7rem; font-size: 1rem; }
  .rlt-grip { display: none; }
  .rlt td.rlt-order:not(:empty) + td.sf-stack__title { padding-right: 6.5rem !important; }
}
.rlt-path { font-size: 1rem; color: var(--sf-text-muted); }
.rlt-action { display: flex; flex-wrap: wrap; align-items: center; gap: .25rem .5rem; }
.rlt-action + .rlt-action { margin-top: .35rem; }
.rlt-cargo { color: var(--sf-text-muted); }
/* 站點特性：每種一個鮮明的顏色；文字跟主題文字色混合，亮底、暗底都看得清楚 */
.sf-chip.rlt-trait {
  --trait: 255, 255, 255;
  color: color-mix(in srgb, rgb(var(--trait)) 62%, var(--sf-text));
  background: rgba(var(--trait), .16);
  border-color: rgba(var(--trait), .65);
  font-weight: 600;
}
.sf-chip.rlt-trait--xl { --trait: 168, 107, 255; }
.sf-chip.rlt-trait--dock { --trait: 255, 163, 26; }
.sf-chip.rlt-trait--docking { --trait: 24, 201, 230; }
.rlt-host { display: contents; }
/* 插入站點視窗：留高度給地點的候選清單 */
.rlt-insert { min-height: 16rem; }
.rlt-replan__no { min-width: 1.25rem; text-align: center; color: var(--sf-text-muted); }
.rlt-replan__place { min-width: min(100%, 20rem); }
.rlt-grip { color: var(--sf-text-muted); cursor: grab; }
tr[draggable="true"] { cursor: grab; }
/* 已去過：變淡；下一站：左邊色條 */
.rlt-visited > td { opacity: .5; }
.rlt-visited > td:has(.rlt-mark) { opacity: 1; }
.rlt-visited .rlt-dest > div { opacity: .5; }
.rlt-visited .fw-semibold { text-decoration: line-through; }
.rlt-next > td:first-child { box-shadow: inset 4px 0 0 var(--sf-accent); }
.rlt-dragging > td { opacity: .4; }
.rlt-over > td { box-shadow: inset 0 2px 0 var(--sf-accent); }
</style>
