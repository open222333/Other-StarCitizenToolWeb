<!--
  配裝模擬的「電源與訊號」卡（components/LoadoutSimulator.vue）：每個耗電者一欄電格（pips），點格子調整；
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

      <div class="lp-cols" role="group" aria-label="電源分配">
        <div v-for="c in list" :key="c.key" class="lp-col" :class="{ 'lp-col--off': c.off || c.fixed }" :title="titleOf(c)">
          <div class="lp-num">{{ c.off ? '關' : c.fixed ? '—' : pips[c.key] ?? 0 }}</div>
          <div class="lp-cells" :style="{ '--cell-h': `${cellH(c)}px` }">
            <button v-for="k in cellsOf(c)" :key="k" type="button" class="lp-cell"
              :class="{ 'is-on': k <= (pips[c.key] ?? 0), 'is-min': k <= (c.min || 0) }"
              :disabled="c.off || c.fixed" :aria-label="`${labelOf(c)} ${k} 格`" @click="click(c, k)"></button>
          </div>
          <i :class="iconOf(c)" class="lp-icon" aria-hidden="true"></i>
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
const STATIC_ICON = { FlightController: 'bi bi-airplane', LifeSupportGenerator: 'bi bi-heart-pulse' }
const iconOf = c => (c.kind === 'static' ? STATIC_ICON[c.group] || 'bi bi-cpu' : KIND[c.kind]?.[0] || 'bi bi-cpu')
const labelOf = c => (c.kind === 'static' ? c.label : KIND[c.kind]?.[1] || c.kind)
const titleOf = c => [c.item ? props.itemLabel(c.item) : labelOf(c), c.min ? `最少 ${c.min} 格` : '', `最多 ${c.max} 格`]
  .filter(Boolean).join(' · ')
const cellsOf = c => Array.from({ length: Math.max(c.max, 0) }, (_, i) => c.max - i)
const maxCells = computed(() => Math.max(1, ...props.list.map(c => c.max || 0)))
const cellH = () => Math.max(6, Math.min(14, Math.floor(150 / maxCells.value)))
const pct = (a, b) => (b ? Math.min(100, (a / b) * 100) : 0)

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
.lp-cols { display: flex; align-items: flex-end; gap: .5rem; overflow-x: auto; padding-bottom: .25rem; }
.lp-col { flex: 0 0 auto; width: 3.1rem; display: flex; flex-direction: column; align-items: center; gap: .2rem; }
.lp-col--off { opacity: .45; }
.lp-num { font-weight: 700; color: var(--sf-text-strong); }
.lp-cells { display: flex; flex-direction: column; gap: 2px; width: 100%; }
.lp-cell { height: var(--cell-h); width: 100%; padding: 0; border: 1px solid var(--sf-border); border-radius: 2px;
  background: var(--sf-chip-bg); cursor: pointer; }
.lp-cell.is-min { border-style: dashed; }
.lp-cell.is-on { background: var(--sf-accent); border-color: var(--sf-accent); }
.lp-cell:disabled { cursor: default; }
.lp-cell:focus-visible { outline: 2px solid var(--sf-accent-2); outline-offset: 1px; }
.lp-icon { color: var(--sf-accent); font-size: 1.1rem; }
.lp-label { font-size: .75rem; color: var(--sf-text-muted); text-align: center; line-height: 1.1; min-height: 1.7em; }
.lp-sig { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; }
.lp-tile { padding: .5rem .6rem; border: 1px solid var(--sf-border); border-radius: .4rem; background: var(--sf-chip-bg); }
.lp-tile__v { font-size: 1.3rem; font-weight: 700; color: var(--sf-text-strong); line-height: 1.1; }
.lp-tile__l { font-size: .8rem; color: var(--sf-text-muted); }
.lp-em { display: flex; flex-wrap: wrap; gap: .2rem .9rem; font-size: .85rem; color: var(--sf-text); }
.lp-kv span { color: var(--sf-text-muted); margin-right: .3rem; }
</style>
