<!--
  配裝模擬的「電源與訊號」卡（components/LoadoutSimulator.vue）：每個耗電者一欄電格（pips，仿遊戲的電源畫面），
  點格子調整；最少格數合成一塊（護盾每個產生器各一塊），目前格數標在最上面那格；點下方圖示整欄關掉／再點恢復。
  飛控（FlightController）就是推進器（遊戲電源畫面上的 >>> 那欄）。
  上方是電力、冷卻用量，下方是 EM／IR／截面訊號。計算在 utils/loadoutPower.js，狀態由 LoadoutSimulator 管。
-->
<template>
  <div :class="[cardClass]">
    <div class="card-body">
      <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
        <h4 class="lp-h mb-0"><i class="bi bi-lightning-charge me-1"></i>電源與訊號</h4>
        <div class="btn-group btn-group-sm ms-auto" role="group" aria-label="模式">
          <button type="button" class="btn" :class="mode === 'scm' ? 'btn-primary' : 'btn-secondary'"
            :aria-pressed="mode === 'scm'" @click="$emit('mode', 'scm')"><i class="bi bi-shield-fill me-1"></i>戰鬥</button>
          <button type="button" class="btn" :class="mode === 'quantum' ? 'btn-primary' : 'btn-secondary'"
            :aria-pressed="mode === 'quantum'" @click="$emit('mode', 'quantum')"><i class="bi bi-stars me-1"></i>量子</button>
        </div>
        <button type="button" class="btn btn-sm btn-info" @click="$emit('auto')"><i class="bi bi-magic me-1"></i>自動分配</button>
        <button type="button" class="btn btn-sm btn-warning" @click="$emit('max')"><i class="bi bi-arrows-angle-expand me-1"></i>全部開滿</button>
      </div>

      <div class="row g-2 mb-2">
        <div class="col-12 col-md-6">
          <div class="d-flex justify-content-between lp-cap">
            <span>電力</span>
            <span class="fw-semibold" :class="{ 'sf-bad': summary.over }">{{ fmtNum(summary.used, 1) }} / {{ fmtNum(summary.gen) }}</span>
          </div>
          <div class="progress lp-bar" role="progressbar" :aria-valuenow="summary.used" aria-valuemin="0" :aria-valuemax="summary.gen">
            <div class="progress-bar" :class="{ 'lp-bar--over': summary.over }" :style="{ width: `${pct(summary.used, summary.gen)}%` }"></div>
          </div>
        </div>
        <div class="col-12 col-md-6">
          <div class="d-flex justify-content-between lp-cap">
            <span>冷卻</span>
            <span class="fw-semibold" :class="{ 'sf-bad': summary.coolShort }">{{ fmtNum(summary.coolUsed, 1) }} / {{ fmtNum(summary.coolGen, 1) }}
              （{{ fmtNum(summary.coolPct * 100) }}%）</span>
          </div>
          <div class="progress lp-bar" role="progressbar" :aria-valuenow="summary.coolUsed" aria-valuemin="0" :aria-valuemax="summary.coolGen">
            <div class="progress-bar lp-bar--cool" :class="{ 'lp-bar--over': summary.coolShort }"
              :style="{ width: `${pct(summary.coolUsed, summary.coolGen)}%` }"></div>
          </div>
        </div>
      </div>
      <div v-if="summary.over || summary.coolShort" class="d-flex flex-wrap gap-2 mb-2">
        <span v-if="summary.over" class="sf-chip sf-chip--warn">電力超出 {{ fmtNum(summary.used - summary.gen, 1) }} 格</span>
        <span v-if="summary.coolShort" class="sf-chip sf-chip--warn">冷卻不足</span>
      </div>

      <div class="lp-cols" role="group" aria-label="電源分配" :style="{ '--cell-h': `${cellH}px` }">
        <div v-for="c in list" :key="c.key" class="lp-col" :class="[`lp-col--${c.kind}`, { 'lp-col--off': c.off || c.fixed || !(pips[c.key] > 0) }]"
          :title="titleOf(c)">
          <div class="lp-cells">
            <template v-for="b in blocksOf(c)" :key="b.id">
              <!-- 固定／關閉（例如戰鬥模式的量子引擎）：一整塊灰色 -->
              <div v-if="b.fixed" class="lp-cell lp-cell--fixed" :style="{ height: blockH(b.n) }">{{ b.text }}</div>
              <button v-else type="button" class="lp-cell"
                :class="{ 'is-on': (pips[c.key] ?? 0) >= b.k, 'is-top': (pips[c.key] ?? 0) === b.k && !b.sub, 'is-min': b.n > 1 || b.min }"
                :style="b.n > 1 ? { height: blockH(b.n) } : null"
                :aria-label="`${labelOf(c)} ${b.k} 格`" @click="click(c, b.k)">
                <span v-if="(pips[c.key] ?? 0) === b.k && !b.sub" class="lp-cell__num">{{ b.k }}</span>
                <span v-else-if="b.n > 1" class="lp-cell__min">{{ b.n }}</span>
              </button>
            </template>
          </div>
          <button type="button" class="lp-icon" :disabled="c.off || c.fixed"
            :aria-label="(pips[c.key] ?? 0) > 0 ? `關掉${labelOf(c)}` : `打開${labelOf(c)}`" @click="toggle(c)">
            <i :class="iconOf(c)" aria-hidden="true"></i></button>
          <div class="lp-label">{{ labelOf(c) }}</div>
        </div>
      </div>

      <div class="lp-sig mt-3">
        <div class="lp-tile"><div class="lp-tile__v">{{ fmtNum(summary.em) }}</div><div class="lp-tile__l">EM 訊號</div></div>
        <div class="lp-tile"><div class="lp-tile__v">{{ fmtNum(summary.ir) }}</div><div class="lp-tile__l">IR 訊號</div></div>
        <div class="lp-tile"><div class="lp-tile__v">{{ fmtNum(summary.cs) }}</div><div class="lp-tile__l">截面（最大面）</div></div>
      </div>
      <div class="lp-em mt-2">
        <span v-for="e in emRows" :key="e.key" class="lp-kv"><span>{{ e.label }}</span>{{ fmtNum(e.value) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fmtNum } from '@/utils/navFormat'

const props = defineProps({
  list: { type: Array, required: true },
  pips: { type: Object, required: true },
  summary: { type: Object, required: true },
  mode: { type: String, default: 'scm' },
  itemLabel: { type: Function, required: true },
  cardClass: { type: String, default: 'card' },
})
const emit = defineEmits(['set', 'mode', 'auto', 'max'])

const KIND = {
  shield: ['bi bi-shield-fill', '護盾'], weapons: ['bi bi-crosshair', '武器'], cooler: ['bi bi-snow', '冷卻'],
  radar: ['bi bi-broadcast', '雷達'], quantum: ['bi bi-stars', '量子'], utility: ['bi bi-tools', '工具'],
}
const STATIC_ICON = { FlightController: 'bi bi-chevron-double-right', LifeSupportGenerator: 'bi bi-heart-pulse' }
const iconOf = c => (c.kind === 'static' ? STATIC_ICON[c.group] || 'bi bi-cpu' : KIND[c.kind]?.[0] || 'bi bi-cpu')
const labelOf = c => (c.kind === 'static' ? c.label : KIND[c.kind]?.[1] || c.kind)
const titleOf = c => [c.items?.length > 1 ? c.items.map(props.itemLabel).join('、') : c.item ? props.itemLabel(c.item) : labelOf(c), c.min ? `最少 ${c.min} 格` : '', `最多 ${c.max} 格`]
  .filter(Boolean).join(' · ')
/** 一欄由上到下的格子：最少格數以上一格一格；最少格數合成一塊（護盾每個產生器的最少格數各一塊）。
 *  k＝點這塊會設成的格數（也是「分到 k 格以上就亮」的門檻），n＝這塊佔幾格高 */
function blocksOf(c) {
  if (c.off || c.fixed) return [{ id: 'fixed', fixed: true, n: Math.max(1, Math.min(c.max || 1, 6)), text: c.off ? '關' : c.max || '—' }]
  const out = []
  const min = c.min || 0
  for (let k = c.max; k > Math.max(min, 1); k--) out.push({ id: k, k, n: 1 })
  if (min <= 1) {
    if (c.max >= 1) out.push({ id: 1, k: 1, n: 1, min: min === 1 })
    return out
  }
  // 最少格數：護盾依產生器分塊（點哪一塊都是開到最少格數；分到最少格數以上才全部亮）
  const parts = c.parts?.length > 1 ? c.parts.map(p => p.min || 0).filter(Boolean) : [min]
  parts.forEach((n, i) => out.push({ id: `min${i}`, k: min, n, min: true, sub: i > 0 }))
  return out
}
const maxCells = computed(() => Math.max(1, ...props.list.map(c => c.max || 0)))
const GAP = 3
const cellH = computed(() => Math.max(8, Math.min(16, Math.floor(190 / maxCells.value) - GAP)))
const blockH = n => `${n * cellH.value + (n - 1) * GAP}px`
const pct = (a, b) => (b ? Math.min(100, (a / b) * 100) : 0)

// 點圖示：整欄關掉；再點恢復成關掉前的格數（沒有就開到最少格數）
const lastPips = {}
function toggle(c) {
  const p = props.pips[c.key] ?? 0
  if (p > 0) {
    lastPips[c.key] = p
    emit('set', c.key, 0)
  } else {
    emit('set', c.key, lastPips[c.key] || Math.max(c.min || 1, 1))
  }
}
function click(c, k) {
  const p = props.pips[c.key] ?? 0
  let next = p === k ? k - 1 : k
  if (next > 0 && next < (c.min || 0)) next = next < p ? 0 : c.min
  emit('set', c.key, next)
}

const EM_LABEL = { power: '發電機', shield: '護盾', weapons: '武器', cooler: '冷卻', radar: '雷達', quantum: '量子', utility: '工具' }
const emRows = computed(() => Object.entries(props.summary.emBy || {})
  .filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1])
  .map(([k, v]) => ({ key: k, label: EM_LABEL[k] || k, value: v })))
</script>

<style scoped>
.lp-h { font-size: 1.05rem; font-weight: 700; color: var(--sf-text-strong); }
.lp-cap { font-size: .9rem; color: var(--sf-text-muted); }
.lp-bar { height: .55rem; background: var(--sf-chip-bg); }
.lp-bar .progress-bar { background: var(--sf-accent); }
.lp-bar .lp-bar--cool { background: var(--sf-accent-2); }
.lp-bar .lp-bar--over { background: var(--bs-danger); }
.lp-cols { display: flex; align-items: flex-end; gap: .5rem; overflow-x: auto; padding: .5rem 0 .25rem; }
.lp-col { flex: 0 0 auto; width: 2.9rem; display: flex; flex-direction: column; align-items: center; gap: .35rem; }
.lp-cells { display: flex; flex-direction: column; gap: 3px; width: 100%; }
.lp-cell { position: relative; height: var(--cell-h); width: 100%; padding: 0; border: 0; border-radius: 3px;
  background: rgba(var(--sf-accent-rgb), .1); cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: background-color .12s; }
.lp-cell:hover { background: rgba(var(--sf-accent-rgb), .25); }
.lp-cell.is-on { background: rgba(var(--sf-accent-rgb), .55); }
.lp-cell.is-min.is-on { background: rgba(var(--sf-accent-rgb), .35); }
.lp-cell.is-top { background: var(--sf-accent); box-shadow: 0 0 10px rgba(var(--sf-accent-rgb), .45); }
.lp-cell:focus-visible { outline: 2px solid var(--sf-accent-2); outline-offset: 1px; }
/* 武器的電源池：沒分到的格子只畫外框（跟遊戲一樣） */
.lp-col--weapons .lp-cell:not(.is-on) { background: transparent; box-shadow: inset 0 0 0 1px var(--sf-border); }
.lp-cell__num { position: absolute; left: 0; right: 0; top: 50%; transform: translateY(-50%); font-weight: 800;
  font-size: var(--sf-fs-md); line-height: 1; color: var(--sf-text-strong); text-shadow: 0 1px 2px rgba(0, 0, 0, .6); pointer-events: none; }
.lp-cell__min { font-size: var(--sf-fs-sm); font-weight: 700; color: var(--sf-text); opacity: .8; pointer-events: none; }
.lp-cell--fixed { cursor: default; background: var(--sf-chip-bg); color: var(--sf-text-muted); font-weight: 700;
  font-size: var(--sf-fs-sm); }
.lp-icon { width: 2.4rem; height: 2.4rem; border-radius: 50%; border: 0; padding: 0; background: none; font-size: 1.35rem;
  color: var(--sf-accent); transition: background-color .12s, color .12s, opacity .12s; }
.lp-icon:hover:not(:disabled) { background: var(--sf-hover-bg); }
.lp-icon:focus-visible { outline: 2px solid var(--sf-accent); }
.lp-icon:disabled { cursor: default; }
.lp-col--off .lp-icon { color: var(--sf-text-muted); opacity: .6; }
.lp-label { font-size: var(--sf-fs-xs); color: var(--sf-text-muted); text-align: center; line-height: 1.1; min-height: 1.2em; margin-top: -.2rem; }
.lp-sig { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; }
.lp-tile { padding: .5rem .6rem; border: 1px solid var(--sf-border); border-radius: .4rem; background: var(--sf-chip-bg); }
.lp-tile__v { font-size: 1.3rem; font-weight: 700; color: var(--sf-text-strong); line-height: 1.1; }
.lp-tile__l { font-size: .8rem; color: var(--sf-text-muted); }
.lp-em { display: flex; flex-wrap: wrap; gap: .2rem .9rem; font-size: .85rem; color: var(--sf-text); }
.lp-kv span { color: var(--sf-text-muted); margin-right: .3rem; }
</style>
