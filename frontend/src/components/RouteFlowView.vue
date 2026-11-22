<!--
  航線的「總覽」顯示方式（RoutePlanner.vue、ContractPlanner.vue 跟航段表／3D 星圖並列）：
  整條航線排成一格一格（起點 → 第 1 站 → …），蛇形排列：橫向（direction=horizontal）一行左→右、下一行右→左；
  直向（vertical）一欄上→下、下一欄下→上。欄數依寬度自動算，40 個站也不用上下捲；
  每格只有站號、站名和幾個小圖示（補燃料、外部貨運、特大機庫、貨艙用量），滑鼠移上去（手機點一下）才跳出細節：
  動作、距離、時間、油量、剩油、經過的 OM／跳躍點、站點特性、這站的裝卸貨。
  站號一樣是「已去過」按鈕（v-model:visited，跟航段表共用同一份）。列的資料見 utils/routeRows.js。
-->
<template>
  <div ref="rootEl" class="rfv">
    <!-- 蛇形排列：第一行左→右，第二行右→左…換行的那一站就在上一站正下方（箭頭朝下），順著看不用跳回最左邊 -->
    <ol ref="gridEl" class="rfv-grid" aria-label="航線總覽" title="滑鼠移到站上（手機點一下）看細節；點站號標記已去過"
      :style="{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }">
      <li v-for="(n, i) in nodes" :key="n.key" class="rfv-node" :style="cellOf(i)"
        :class="[`dir-${dirOf(i)}`, { 'is-turn': isTurn(i), 'is-visited': isVisited(n.key), 'is-next': nextKey === n.key, 'is-warn': n.refuel || n.short,
                  'is-active': tipIndex === i, 'is-over': n.flow?.over }]"
        tabindex="0" :aria-label="`${i}. ${placeLabel(n.to)}`" @mouseenter="show(i, $event)" @mouseleave="hideSoon"
        @focus="show(i, $event)" @blur="hideSoon" @click="toggleTip(i, $event)">
        <i v-if="i > 0" class="bi rfv-arrow" :class="arrowIcon(i, n.jump)" aria-hidden="true"></i>
        <button type="button" class="rfv-mark" :class="{ 'is-done': isVisited(n.key) }"
          :aria-pressed="isVisited(n.key) ? 'true' : 'false'" :aria-label="`第 ${i} 站已去過`"
          @click.stop="setVisited(n.key, !isVisited(n.key))">
          <i v-if="isVisited(n.key)" class="bi bi-check-lg"></i><template v-else>{{ i }}</template>
        </button>
        <div class="rfv-body">
          <div class="rfv-name">{{ shortName(n.to) }}</div>
          <div class="rfv-icons">
            <span v-if="n.kind" class="rfv-kind">{{ n.kind }}</span>
            <i v-if="n.refuel || n.short" class="bi bi-fuel-pump-fill rfv-warn" title="出發前需補充燃料"></i>
            <i v-if="n.to.loading_dock" class="bi bi-box-seam rfv-dock" title="外部貨運"></i>
            <i v-if="n.to.xl_hangar" class="bi bi-building rfv-xl" title="特大機庫"></i>
            <span v-if="cargoOn && n.entries.length" class="rfv-cargo" :class="{ 'is-over': n.flow?.over }">
              <i class="bi bi-boxes me-1"></i>{{ fmtNum(n.flow?.total || 0) }}</span>
          </div>
        </div>
      </li>
    </ol>
    <!-- 操作提示放在格子區的 title（不另佔一行，矮螢幕才放得下 40 站） -->

    <!-- 細節：固定定位，貼著那一格（下面放不下就放上面） -->
    <!-- 純顯示，不攔滑鼠：移到下一格時不會被浮窗擋住 -->
    <div v-if="tip" ref="tipEl" class="rfv-tip scifi-card" role="tooltip" :style="tipStyle">
      <div class="fw-semibold">{{ tip.index }}. {{ placeLabel(tip.to) }}</div>
      <div class="rfv-path">{{ placePath(tip.to) }}</div>
      <div class="d-flex flex-wrap gap-1 mt-1">
        <span v-for="(a, j) in tip.actions" :key="j" class="sf-chip mb-0" :class="actionClass(a.action)">{{ actionLabel(a) }}</span>
        <span v-for="t in traitsOf(tip.to)" :key="t.key" class="sf-chip mb-0"><i :class="t.icon" class="me-1"></i>{{ t.label }}</span>
      </div>
      <dl v-if="tip.moved || tip.fuelText" class="rfv-facts">
        <template v-if="tip.moved">
          <dt>距離</dt><dd>{{ fmtDist(tip.distance) }}</dd>
          <dt>時間</dt><dd>{{ fmtTime(tip.time) }}</dd>
          <dt v-if="tip.fuel != null">油量</dt><dd v-if="tip.fuel != null">{{ fmtNum(tip.fuel, tip.fuel < 10 ? 1 : 0) }}</dd>
        </template>
        <dt v-if="tip.fuelText">剩油</dt><dd v-if="tip.fuelText">{{ tip.fuelText }}</dd>
      </dl>
      <div v-if="tip.via?.length" class="d-flex flex-wrap gap-1 mt-1">
        <span v-for="(v, j) in tip.via" :key="j" class="sf-chip mb-0" :class="{ 'sf-chip--accent': v.kind === 'jump' }">
          {{ v.kind === 'jump' ? '跳躍' : '經' }} {{ placeLabel(v.place) }}</span>
      </div>
      <div v-if="tip.refuel || tip.short" class="d-flex flex-wrap gap-1 mt-1">
        <span v-if="tip.refuel" class="sf-chip sf-chip--warn mb-0">出發前需補充燃料</span>
        <span v-if="tip.short" class="sf-chip sf-chip--warn mb-0">下一段超過油箱</span>
      </div>
      <template v-if="cargoOn">
        <RouteCargoSummary :entries="tip.entries" :shorts="tip.flow?.shorts" />
        <div class="small mt-1" :class="{ 'sf-bad': tip.flow?.over }">
          離開時貨艙 {{ fmtNum(tip.flow?.total || 0) }}{{ cargoCapacity ? ` / ${fmtNum(cargoCapacity)}` : '' }} SCU</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import RouteCargoSummary from '@/components/RouteCargoSummary.vue'
import { actionClass, actionLabel, buildRouteRows, traitsOf } from '@/utils/routeRows'
import { cargoFlow } from '@/utils/stopCargo'
import { fmtDist, fmtNum, fmtTime, placeLabel, placePath } from '@/utils/navFormat'
import { isSnakeTurn, snakeDir, snakePos } from '@/utils/routeFlow'

const props = defineProps({
  plan: { type: Object, required: true },
  fuelCapacity: { type: Number, default: null },
  visited: { type: Array, default: () => [] },
  cargoOn: { type: Boolean, default: false },
  stopCargo: { type: Object, default: () => ({}) },
  cargoCapacity: { type: Number, default: 0 },
  // 排列方向：horizontal＝橫向（一行一行，左右來回）、vertical＝直向（一欄一欄，上下來回）
  direction: { type: String, default: 'horizontal' },
})
const emit = defineEmits(['update:visited'])

const START_KEY = 'start'
const KIND = { end: '終點', hub: '回指定站', pickup: '取貨', dropoff: '送貨' }

const table = computed(() => buildRouteRows(props.plan))
const flow = computed(() => (props.cargoOn
  ? cargoFlow([START_KEY, ...table.value.rows.map(r => r.key)], props.stopCargo, props.cargoCapacity) : new Map()))

function fuelText(f) {
  const cap = props.fuelCapacity
  if (f == null || !cap) return ''
  return `${fmtNum(f)}（${Math.max(0, Math.round(f / cap * 100))}%）`
}
const nodes = computed(() => {
  const t = table.value
  const s = t.start
  const startNode = {
    key: START_KEY, to: props.plan.start, actions: s?.actions?.length ? s.actions : [{ action: 'start' }], moved: false,
    refuel: s?.refuel || !!props.plan.refuel_stops?.includes(0), short: s?.short || !!props.plan.legs?.[0]?.fuel_short,
    fuelText: props.plan.start_fuel != null && props.fuelCapacity && props.plan.start_fuel < props.fuelCapacity - 1e-9
      ? fuelText(props.plan.start_fuel) : (props.fuelCapacity ? '滿油' : ''),
    kind: '起點', via: [],
  }
  const rows = t.rows.map(r => ({
    ...r, fuelText: fuelText(r.fuel_after),
    jump: r.via.some(v => v.kind === 'jump'),
    kind: [...new Set(r.actions.map(a => KIND[a.action]).filter(Boolean))].join('・'),
  }))
  return [startNode, ...rows].map(n => ({
    ...n, entries: props.stopCargo?.[n.key] || [], flow: flow.value.get(n.key) || null,
  }))
})

// ── 已去過（跟航段表同一份） ──
const visitedSet = computed(() => new Set(props.visited))
const isVisited = key => visitedSet.value.has(key)
function setVisited(key, on) {
  const next = new Set(props.visited)
  if (on) next.add(key)
  else next.delete(key)
  emit('update:visited', [...next])
}
const nextKey = computed(() => table.value.rows.find(r => !isVisited(r.key))?.key || '')

// ── 蛇形排列：依寬度算一行幾格；偶數行（0 起算）左→右、奇數行右→左 ──
const gridEl = ref(null)
const cols = ref(6)
// 欄距（箭頭放在格子之間的空隙裡）；要跟 CSS 的 column-gap 一樣
const GAP_PX = 20
function measure() {
  const el = gridEl.value
  if (!el) return
  const w = el.clientWidth
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16
  const colW = Math.min(9.5 * rem, w / 2 - GAP_PX)
  cols.value = Math.max(1, Math.floor((w + GAP_PX) / (colW + GAP_PX)))
}
// 直向：欄數一樣（寬度決定），行數＝站數÷欄數；第一欄上→下、第二欄下→上…
const rowsN = computed(() => Math.max(1, Math.ceil(nodes.value.length / cols.value)))
const vertical = computed(() => props.direction === 'vertical')
// 蛇形排列的計算在 utils/routeFlow.js（純函式、有測試）
const layout = computed(() => ({ vertical: vertical.value, cols: cols.value, rows: rowsN.value }))
const posOf = i => snakePos(i, layout.value)
const cellOf = (i) => {
  const p = posOf(i)
  return { gridRow: p.row + 1, gridColumn: p.col + 1 }
}
// 這一格跟上一站的關係：r＝上一站在左邊、l＝在右邊、d＝在正上方、u＝在正下方
const dirOf = i => snakeDir(i, layout.value)
// 換行（橫向）／換欄（直向）的那一格
const isTurn = i => isSnakeTurn(i, layout.value)
function arrowIcon(i, jump) {
  const d = dirOf(i)
  if (d === 'd') return jump ? 'bi-chevron-double-down' : 'bi-arrow-down'
  if (d === 'u') return jump ? 'bi-chevron-double-up' : 'bi-arrow-up'
  if (d === 'l') return jump ? 'bi-chevron-double-left' : 'bi-arrow-left'
  return jump ? 'bi-chevron-double-right' : 'bi-arrow-right'
}
let ro = null

// 站名：只要名稱（中文優先），完整的在細節裡
const shortName = p => p?.name_zh || p?.name || ''

// ── 細節浮窗 ──
const rootEl = ref(null)
const tipEl = ref(null)
const tipIndex = ref(-1)
const pinned = ref(false)
const anchor = ref(null)
const tipPos = ref({ left: 0, top: 0, ready: false })
const tip = computed(() => (tipIndex.value >= 0 && nodes.value[tipIndex.value]
  ? { ...nodes.value[tipIndex.value], index: tipIndex.value } : null))
const tipStyle = computed(() => ({ left: `${tipPos.value.left}px`, top: `${tipPos.value.top}px`,
  visibility: tipPos.value.ready ? 'visible' : 'hidden' }))
let hideTimer = null

async function place() {
  const el = anchor.value
  if (!el) return
  tipPos.value = { ...tipPos.value, ready: false }
  await nextTick()
  const t = tipEl.value
  if (!t) return
  const r = el.getBoundingClientRect()
  const w = t.offsetWidth, h = t.offsetHeight
  const vw = window.innerWidth, vh = window.innerHeight
  const left = Math.min(Math.max(8, r.left), vw - w - 8)
  const below = r.bottom + 6
  const top = below + h <= vh - 8 ? below : Math.max(8, r.top - h - 6)
  tipPos.value = { left, top, ready: true }
}
function show(i, event) {
  cancelHide()
  if (pinned.value && tipIndex.value !== i && event?.type === 'mouseenter') pinned.value = false
  tipIndex.value = i
  anchor.value = event?.currentTarget || null
  place()
}
function hideSoon() {
  if (pinned.value) return
  cancelHide()
  hideTimer = setTimeout(() => { tipIndex.value = -1 }, 120)
}
function cancelHide() {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = null
}
// 點一下：釘住（手機沒有滑鼠移上去），再點一次或點外面關掉
function toggleTip(i, event) {
  if (pinned.value && tipIndex.value === i) {
    pinned.value = false
    tipIndex.value = -1
    return
  }
  pinned.value = true
  show(i, event)
}
function onDocClick(e) {
  if (!pinned.value) return
  if (rootEl.value?.contains(e.target)) return
  pinned.value = false
  tipIndex.value = -1
}
const onScroll = () => { if (tipIndex.value >= 0) place() }
onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined' && gridEl.value) {
    ro = new ResizeObserver(measure)
    ro.observe(gridEl.value)
  }
  document.addEventListener('click', onDocClick)
  window.addEventListener('scroll', onScroll, true)
  window.addEventListener('resize', onScroll)
})
onBeforeUnmount(() => {
  ro?.disconnect()
  cancelHide()
  document.removeEventListener('click', onDocClick)
  window.removeEventListener('scroll', onScroll, true)
  window.removeEventListener('resize', onScroll)
})
</script>

<style scoped>
.rfv-grid {
  list-style: none; margin: 0; padding: 0;
  display: grid; gap: .95rem 20px;
}
.rfv-node {
  position: relative; display: flex; align-items: center; gap: .45rem; min-width: 0;
  padding: .15rem .45rem; border: 1px solid var(--sf-border); border-radius: .5rem;
  background: var(--sf-chip-bg); cursor: default; outline: none;
}
/* 箭頭放在格子外面、兩格之間的空隙（不佔格子內的位置） */
.rfv-node:hover, .rfv-node:focus-visible, .rfv-node.is-active { border-color: var(--sf-accent); }
.rfv-node.is-next { box-shadow: inset 3px 0 0 var(--sf-accent); }
.rfv-node.is-warn { border-color: rgba(var(--bs-warning-rgb), .6); }
.rfv-node.is-visited .rfv-body { opacity: .5; }
.rfv-node.is-visited .rfv-name { text-decoration: line-through; }
/* 格子之間的箭頭：放在每一格左邊 */
.rfv-arrow { position: absolute; font-size: 1rem; color: var(--sf-text-muted); line-height: 1; pointer-events: none; }
.dir-r > .rfv-arrow { left: -10px; top: 50%; transform: translate(-50%, -50%); }
.dir-l > .rfv-arrow { right: -10px; top: 50%; transform: translate(50%, -50%); }
/* 換行：箭頭在上下兩格之間，指著從上面那一站下來 */
.dir-d > .rfv-arrow { left: 50%; top: calc(-.95rem / 2); transform: translate(-50%, -50%); }
.dir-u > .rfv-arrow { left: 50%; bottom: calc(-.95rem / 2); transform: translate(-50%, 50%); }
/* 換行／換欄的那一個箭頭用強調色 */
.rfv-node.is-turn > .rfv-arrow { color: var(--sf-accent-text, var(--sf-accent)); }
.rfv-mark {
  flex: 0 0 auto; width: 1.75rem; height: 1.75rem; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;
  font-size: .9rem; font-weight: 600; color: var(--sf-text); background: var(--sf-bg-2, rgba(0, 0, 0, .25));
  border: 2px solid var(--sf-border-hi); cursor: pointer; padding: 0;
}
.rfv-mark:hover { border-color: var(--sf-accent); }
.rfv-mark.is-done { color: rgb(var(--bs-success-rgb)); background: rgba(var(--bs-success-rgb), .16); border-color: rgb(var(--bs-success-rgb)); }
.rfv-node.is-next .rfv-mark { border-color: var(--sf-accent); }
.rfv-body { min-width: 0; flex: 1 1 auto; }
.rfv-name { font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; line-height: 1.25; }
.rfv-icons { display: flex; align-items: center; gap: .35rem; font-size: .78rem; color: var(--sf-text-muted); min-height: 1rem; white-space: nowrap; }
.rfv-kind { color: var(--sf-accent-text, var(--sf-accent)); }
.rfv-warn { color: rgb(var(--bs-warning-rgb)); }
.rfv-dock { color: rgb(255, 163, 26); }
.rfv-xl { color: rgb(168, 107, 255); }
.rfv-cargo.is-over { color: rgb(var(--bs-danger-rgb)); font-weight: 600; }
.rfv-hint { margin-top: .3rem; font-size: .8rem; color: var(--sf-text-muted); }
.rfv-tip {
  position: fixed; z-index: 1200; pointer-events: none; width: min(24rem, calc(100vw - 16px)); padding: .65rem .8rem;
  border: 1px solid var(--sf-border-hi); border-radius: .5rem; box-shadow: 0 8px 24px rgba(0, 0, 0, .45);
}
.rfv-path { font-size: .85rem; color: var(--sf-text-muted); }
.rfv-facts { display: grid; grid-template-columns: auto 1fr auto 1fr; gap: .1rem .6rem; margin: .45rem 0 0; font-size: .9rem; }
.rfv-facts dt { color: var(--sf-text-muted); font-weight: 400; }
.rfv-facts dd { margin: 0; }
</style>
