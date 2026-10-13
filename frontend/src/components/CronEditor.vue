<!--
  易讀的排程設定（v-model 仍是 cron 字串，後端不變）：頻率（每 N 小時／每天／每週／每月／自訂）
  ＋時間＋星期或日期；「自訂」才顯示原始 cron 輸入框。認不得的 cron 一律當自訂，不會被改寫。
  轉換規則見 utils/cronHuman.js。
-->
<template>
  <div class="cron-editor">
    <div class="d-flex flex-wrap align-items-center gap-1">
      <select class="form-select form-select-sm w-auto" :value="state.mode" :disabled="disabled"
        :aria-label="`${label} 頻率`" @change="setMode($event.target.value)">
        <option v-for="m in MODES" :key="m.value" :value="m.value">{{ m.label }}</option>
      </select>

      <template v-if="state.mode === 'hourly'">
        <select class="form-select form-select-sm w-auto" :value="state.every" :disabled="disabled"
          :aria-label="`${label} 間隔`" @change="update({ every: +$event.target.value })">
          <option v-for="n in HOUR_STEPS" :key="n" :value="n">{{ n === 1 ? '每小時' : `每 ${n} 小時` }}</option>
        </select>
        <span class="small">第</span>
        <select class="form-select form-select-sm w-auto" :value="state.minute" :disabled="disabled"
          :aria-label="`${label} 分鐘`" @change="update({ minute: +$event.target.value })">
          <option v-for="n in MINUTES" :key="n" :value="n">{{ n }}</option>
        </select>
        <span class="small">分</span>
      </template>

      <template v-else-if="state.mode === 'monthly'">
        <select class="form-select form-select-sm w-auto" :value="state.dom" :disabled="disabled"
          :aria-label="`${label} 日期`" @change="update({ dom: +$event.target.value })">
          <option v-for="n in 31" :key="n" :value="n">{{ n }} 號</option>
        </select>
      </template>

      <!-- 時間用兩個下拉（24 小時制），不用 <input type="time">：它會依瀏覽器語系顯示上午／下午 -->
      <template v-if="state.mode !== 'hourly' && state.mode !== 'custom'">
        <select class="form-select form-select-sm w-auto" :value="state.hour" :disabled="disabled"
          :aria-label="`${label} 時`" @change="update({ hour: +$event.target.value })">
          <option v-for="h in 24" :key="h - 1" :value="h - 1">{{ pad(h - 1) }}</option>
        </select>
        <span>:</span>
        <select class="form-select form-select-sm w-auto" :value="state.minute" :disabled="disabled"
          :aria-label="`${label} 分`" @change="update({ minute: +$event.target.value })">
          <option v-for="n in MINUTES" :key="n" :value="n">{{ pad(n) }}</option>
        </select>
      </template>

      <input v-if="state.mode === 'custom'" type="text" class="form-control form-control-sm cron-editor__raw"
        :class="{ 'is-invalid': invalid }" :value="modelValue" :disabled="disabled" placeholder="30 4 * * 1"
        :aria-label="`${label} cron`" @input="$emit('update:modelValue', $event.target.value)">
    </div>

    <div v-if="state.mode === 'weekly'" class="btn-group btn-group-sm mt-1" role="group" :aria-label="`${label} 星期`">
      <button v-for="d in WEEKDAYS" :key="d.value" type="button" class="btn"
        :class="state.days.includes(d.value) ? 'btn-primary' : 'btn-outline-secondary'" :disabled="disabled"
        :aria-pressed="state.days.includes(d.value) ? 'true' : 'false'" @click="toggleDay(d.value)">{{ d.label }}</button>
    </div>
    <div v-if="state.mode === 'monthly' && state.dom > 28" class="small text-warning mt-1">
      沒有 {{ state.dom }} 號的月份不會執行
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import { HOUR_STEPS, WEEKDAYS, buildCron, parseCron } from '@/utils/cronHuman'

const props = defineProps({
  modelValue: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
  invalid: { type: Boolean, default: false },
  /** 給螢幕閱讀器的名稱前綴（例如項目名稱） */
  label: { type: String, default: '排程' },
})
const emit = defineEmits(['update:modelValue'])

const MODES = [
  { value: 'hourly', label: '每隔幾小時' },
  { value: 'daily', label: '每天' },
  { value: 'weekly', label: '每週' },
  { value: 'monthly', label: '每月' },
  { value: 'custom', label: '自訂（cron）' },
]
const STEP_MINUTES = Array.from({ length: 12 }, (_, i) => i * 5)
// 每 5 分一格；原本的 cron 是別的分鐘（例如 17）也要列出來，不然選單會是空白
const MINUTES = computed(() => [...new Set([...STEP_MINUTES, state.minute])].sort((a, b) => a - b))

const state = reactive(parseCron(props.modelValue))
// 外部改了（例如儲存後伺服器回傳、重新載入）就重新解析；自己 emit 的值解析回來會一樣，不會打架
watch(() => props.modelValue, (v) => {
  if (state.mode === 'custom' && parseCron(v).mode === 'custom') return
  Object.assign(state, parseCron(v))
})

const pad = n => String(n).padStart(2, '0')

function emitCron() {
  const cron = buildCron(state)
  if (cron !== null && cron !== props.modelValue) emit('update:modelValue', cron)
}
function update(patch) {
  Object.assign(state, patch)
  emitCron()
}
function setMode(mode) {
  state.mode = mode
  emitCron()
}
function toggleDay(day) {
  const days = state.days.includes(day) ? state.days.filter(d => d !== day) : [...state.days, day]
  if (!days.length) return   // 至少留一天
  update({ days })
}
</script>

<style scoped>
.cron-editor { min-width: 16rem; }
.cron-editor__raw { min-width: 9rem; max-width: 11rem; font-family: var(--bs-font-monospace); }
</style>
