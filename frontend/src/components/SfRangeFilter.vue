<!--
  範圍篩選（搜尋卡共用）：雙頭拉條＋最低／最高兩個輸入框＋預設級距按鈕。
  v-model 是 { min, max }，空字串＝那一邊不限（拉條拉到最左＝最低不限、最右＝最高不限）。
  拉條預設用對數刻度（價格、貨艙從幾十到上億都有，見 utils/rangeScale.js），拉出來的值取好看的整數；
  輸入框照輸入的值。presets：[{ label, min, max }]（min／max 空字串＝不限），點了直接套用，再點一次取消。
  用在：艦長室 › 艦隊與資料庫 › 艦船的價格（每種貨幣一條）、貨物量；航線的「貨艙至少」（single：只有下限）。
-->
<template>
  <div class="srf" :class="{ 'srf--single': single }">
    <div class="srf-track" :style="{ '--lo': `${loPos / SLIDER_STEPS * 100}%`, '--hi': `${hiPos / SLIDER_STEPS * 100}%` }">
      <input type="range" class="srf-range srf-range--lo" :min="0" :max="SLIDER_STEPS" :value="loPos"
        :aria-label="`${label} 最低（拉條）`" @input="onLo(Number($event.target.value))">
      <input v-if="!single" type="range" class="srf-range srf-range--hi" :min="0" :max="SLIDER_STEPS" :value="hiPos"
        :aria-label="`${label} 最高（拉條）`" @input="onHi(Number($event.target.value))">
    </div>
    <div class="srf-inputs">
      <div class="input-group input-group-sm">
        <input :id="id" :value="modelValue.min" type="number" min="0" class="form-control" :placeholder="single ? '不限' : '最低'"
          :aria-label="`${label} 最低`" inputmode="numeric" @change="setMin($event.target.value)">
        <template v-if="!single">
          <span class="input-group-text">–</span>
          <input :value="modelValue.max" type="number" min="0" class="form-control" placeholder="不限"
            :aria-label="`${label} 最高`" inputmode="numeric" @change="setMax($event.target.value)">
        </template>
        <span v-if="unit" class="input-group-text">{{ unit }}</span>
      </div>
    </div>
    <div v-if="presets.length" class="srf-presets sf-pills" role="group" :aria-label="`${label} 級距`">
      <button v-for="p in presets" :key="p.label" type="button" class="srf-preset sf-pill" :class="{ active: isPreset(p) }"
        :aria-pressed="isPreset(p) ? 'true' : 'false'" @click="applyPreset(p)">{{ p.label }}</button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { SLIDER_STEPS, fromPos, toPos } from '@/utils/rangeScale'

const props = defineProps({
  modelValue: { type: Object, default: () => ({ min: '', max: '' }) },
  /** 拉條最右邊的值（再大的用輸入框打） */
  max: { type: Number, required: true },
  log: { type: Boolean, default: true },
  presets: { type: Array, default: () => [] },
  unit: { type: String, default: '' },
  /** 給螢幕閱讀器的名稱（例如「美金價格」） */
  label: { type: String, required: true },
  /** 只有下限（例如「貨艙至少」） */
  single: { type: Boolean, default: false },
  id: { type: String, default: undefined },
})
const emit = defineEmits(['update:modelValue'])

const blank = v => v === '' || v == null
const same = (a, b) => (blank(a) && blank(b)) || (!blank(a) && !blank(b) && Number(a) === Number(b))
// 拉條位置：值取整後再換回位置會跳（低的那一段好幾格才差 1），所以拉的時候記住拉到哪一格；
// 值是從外面改的（輸入框、級距、清除）才照值重算位置
const dragged = { lo: null, hi: null }   // { pos, value }
function posOf(which, value, fallback) {
  const d = dragged[which]
  if (d && same(d.value, value)) return d.pos
  return blank(value) ? fallback : toPos(value, props.max, props.log)
}
const loPos = computed(() => posOf('lo', props.modelValue.min, 0))
const hiPos = computed(() => (props.single ? SLIDER_STEPS : posOf('hi', props.modelValue.max, SLIDER_STEPS)))

function emitRange(min, max) {
  emit('update:modelValue', { min, max: props.single ? '' : max })
}
function onLo(pos) {
  const p = Math.min(pos, hiPos.value)
  const value = p <= 0 ? '' : fromPos(p, props.max, props.log)
  dragged.lo = { pos: p, value }
  emitRange(value, props.modelValue.max)
}
function onHi(pos) {
  const p = Math.max(pos, loPos.value)
  const value = p >= SLIDER_STEPS ? '' : fromPos(p, props.max, props.log)
  dragged.hi = { pos: p, value }
  emitRange(props.modelValue.min, value)
}
const parse = v => (blank(v) || Number.isNaN(Number(v)) || Number(v) < 0 ? '' : Number(v))
function setMin(v) {
  let min = parse(v)
  const max = props.modelValue.max
  if (min !== '' && !blank(max) && min > Number(max)) min = Number(max)
  emitRange(min, max)
}
function setMax(v) {
  let max = parse(v)
  const min = props.modelValue.min
  if (max !== '' && !blank(min) && max < Number(min)) max = Number(min)
  emitRange(min, max)
}
const isPreset = p => same(p.min, props.modelValue.min) && (props.single || same(p.max, props.modelValue.max))
function applyPreset(p) {
  if (isPreset(p)) emitRange('', '')
  else emitRange(p.min ?? '', p.max ?? '')
}
</script>

<style scoped>
.srf { display: flex; flex-direction: column; gap: .45rem; }
/* 雙頭拉條：兩條 range 疊在一起，只有圓點接收滑鼠；中間選到的區段用強調色 */
.srf-track { position: relative; height: 1.5rem; }
.srf-track::before, .srf-track::after { content: ''; position: absolute; top: 50%; height: .4rem; transform: translateY(-50%); border-radius: 999px; }
.srf-track::before { left: 0; right: 0; background: var(--sf-border); }
.srf-track::after { left: var(--lo); right: calc(100% - var(--hi)); background: var(--sf-accent); box-shadow: 0 0 .4rem rgba(var(--sf-accent-rgb), .5); }
.srf-range {
  position: absolute; inset: 0; width: 100%; margin: 0; background: none; pointer-events: none; z-index: 1;
  -webkit-appearance: none; appearance: none;
}
.srf-range::-webkit-slider-runnable-track { background: none; height: 1.5rem; }
.srf-range::-moz-range-track { background: none; }
.srf-range::-webkit-slider-thumb {
  -webkit-appearance: none; pointer-events: auto; cursor: grab; margin-top: .2rem;
  width: 1.1rem; height: 1.1rem; border-radius: 50%; background: var(--sf-accent); border: 2px solid var(--sf-text-strong);
}
.srf-range::-moz-range-thumb {
  pointer-events: auto; cursor: grab; width: 1.1rem; height: 1.1rem; border-radius: 50%;
  background: var(--sf-accent); border: 2px solid var(--sf-text-strong);
}
.srf-range:focus-visible::-webkit-slider-thumb { box-shadow: 0 0 0 3px rgba(var(--sf-accent-rgb), .5); }
.srf-range:focus-visible::-moz-range-thumb { box-shadow: 0 0 0 3px rgba(var(--sf-accent-rgb), .5); }
.srf-inputs .form-control { min-width: 0; font-variant-numeric: tabular-nums; }
/* 級距按鈕的樣式在 scifi-theme.css 的 .sf-pill */
/* 觸控：圓點、級距按鈕放大到好按 */
@media (pointer: coarse) {
  .srf-track { height: 2.75rem; }
  .srf-range::-webkit-slider-runnable-track { height: 2.75rem; }
  .srf-range::-webkit-slider-thumb { width: 1.6rem; height: 1.6rem; margin-top: .575rem; }
  .srf-range::-moz-range-thumb { width: 1.6rem; height: 1.6rem; }
}
</style>
