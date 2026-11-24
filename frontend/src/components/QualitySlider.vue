<!--
  材料品質拉條（藍圖品質試算、配裝模擬的製作品質共用）：拉條＋−／數字輸入／＋，
  可選的刻度（ticks：[{ q, label }]，標在拉條下方對應位置）、MIN／MID／MAX 快速設定（presets），
  低於這個材料能用的最低品質（min-quality）時顯示警示。值一律夾在 Q0～Q1000（utils/craftQuality.js）。
-->
<template>
  <div class="qs" :class="{ 'qs--disabled': disabled }">
    <div class="qs-line">
      <label v-if="label" class="qs-label" :for="inputId">{{ label }}</label>
      <div class="qs-track">
        <input :value="modelValue" type="range" class="qs-range" :min="QUALITY_MIN" :max="QUALITY_MAX" :step="step"
          :disabled="disabled" :aria-label="`${ariaName}（拉條）`"
          :style="{ '--qs-fill': `${(modelValue / QUALITY_MAX) * 100}%` }" @input="set($event.target.value)">
        <div v-if="ticks.length" class="qs-ticks" aria-hidden="true">
          <span v-for="t in ticks" :key="t.q" class="qs-tick" :style="{ left: `${(t.q / QUALITY_MAX) * 100}%` }">{{ t.label }}</span>
        </div>
      </div>
      <div class="qs-num">
        <button type="button" class="btn btn-sm btn-secondary qs-step" :disabled="disabled || modelValue <= QUALITY_MIN"
          :aria-label="`${ariaName} 減 ${nudge}`" @click="set(modelValue - nudge)"><i class="bi bi-dash-lg"></i></button>
        <input :id="inputId" :value="display" type="number" class="form-control form-control-sm qs-input"
          :min="QUALITY_MIN" :max="QUALITY_MAX" step="1" :disabled="disabled" :aria-label="ariaName"
          @change="set($event.target.value); $event.target.value = display">
        <button type="button" class="btn btn-sm btn-secondary qs-step" :disabled="disabled || modelValue >= QUALITY_MAX"
          :aria-label="`${ariaName} 加 ${nudge}`" @click="set(modelValue + nudge)"><i class="bi bi-plus-lg"></i></button>
      </div>
    </div>
    <div v-if="presets && !disabled" class="btn-group btn-group-sm qs-presets" role="group" :aria-label="`${ariaName} 快速設定`">
      <button type="button" class="btn btn-info" @click="set(Math.max(QUALITY_MIN, minQuality))">MIN</button>
      <button type="button" class="btn btn-info" @click="set(QUALITY_MID)">MID</button>
      <button type="button" class="btn btn-info" @click="set(QUALITY_MAX)">MAX</button>
    </div>
    <div v-if="minQuality && modelValue < minQuality" class="qs-warn">低於最低品質 Q{{ minQuality }}，這個材料不能用</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { QUALITY_MAX, QUALITY_MID, QUALITY_MIN, clampQuality } from '@/utils/craftQuality'

const props = defineProps({
  modelValue: { type: Number, default: QUALITY_MID },
  label: { type: String, default: '' },
  /** 給螢幕閱讀器的名稱（例如「槍管 品質」） */
  name: { type: String, default: '品質' },
  minQuality: { type: Number, default: 0 },
  step: { type: Number, default: 1 },
  /** −／＋ 一次調多少 */
  nudge: { type: Number, default: 10 },
  ticks: { type: Array, default: () => [] },
  presets: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  /** 小數顯示（多批材料的加權平均品質） */
  decimals: { type: Number, default: 0 },
  id: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])
const uid = Math.random().toString(36).slice(2, 8)
const inputId = computed(() => props.id || `qs-${uid}`)
const ariaName = computed(() => props.name || props.label || '品質')
const display = computed(() => Number(Number(props.modelValue).toFixed(props.decimals)))
function set(v) {
  const q = clampQuality(v, props.modelValue)
  if (q !== props.modelValue) emit('update:modelValue', q)
}
</script>

<style scoped>
.qs-line { display: flex; align-items: center; gap: .6rem; }
.qs-label { flex: 0 0 auto; margin: 0; color: var(--sf-text-muted); white-space: nowrap; }
.qs-track { position: relative; flex: 1 1 auto; min-width: 6rem; }
.qs-ticks { position: relative; height: 1.1rem; margin-top: .15rem; }
.qs-tick { position: absolute; transform: translateX(-50%); font-size: var(--sf-fs-xs); color: var(--sf-text-muted);
  white-space: nowrap; font-variant-numeric: tabular-nums; }
.qs-tick:first-child { transform: none; }
.qs-tick:last-child { transform: translateX(-100%); }
.qs-range {
  /* 自己畫軌道：Bootstrap 的 form-range 在深色主題上軌道幾乎看不到 */
  -webkit-appearance: none; appearance: none; width: 100%; height: .45rem; border-radius: 999px; cursor: pointer; display: block;
  background: linear-gradient(to right, var(--sf-accent) var(--qs-fill, 50%), var(--sf-border) var(--qs-fill, 50%));
}
.qs-range::-webkit-slider-thumb { -webkit-appearance: none; width: 1.1rem; height: 1.1rem; border-radius: 50%;
  background: var(--sf-accent); border: 2px solid var(--sf-text-strong); }
.qs-range::-moz-range-thumb { width: 1.1rem; height: 1.1rem; border-radius: 50%;
  background: var(--sf-accent); border: 2px solid var(--sf-text-strong); }
.qs--disabled .qs-range { cursor: default; opacity: .6; }
.qs-num { flex: 0 0 auto; display: inline-flex; align-items: center; gap: .25rem; }
.qs-step { padding: .15rem .45rem; }
.qs-input { width: 4.8rem; text-align: center; font-variant-numeric: tabular-nums; }
.qs-presets { margin-top: .35rem; }
.qs-presets .btn { min-width: 3.2rem; font-weight: 700; letter-spacing: .03em; }
.qs-warn { color: var(--sf-accent-2); font-weight: 600; font-size: var(--sf-fs-sm); margin-top: .2rem; }
</style>
