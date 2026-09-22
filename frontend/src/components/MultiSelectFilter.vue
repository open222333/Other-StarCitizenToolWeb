<!--
  多選篩選下拉（checkbox 多選，取代單選 <select>）。

  全站搜尋優化的第一條規則：「單一條件能多選 → 設計成可勾選多個」。這是
  第一個把它抽成共用元件的地方（操作紀錄頁），之後其他頁面的多選篩選
  （藍圖登記管理、使用者管理、庫存…）都直接用這個，不要各自重寫一份。

  不用 Bootstrap 的 dropdown（data-bs-toggle）：它一點擊 dropdown-menu 裡面
  的任何東西就會自動收起來，checkbox 要多勾幾個的話每勾一次就關一次，
  除非額外設 data-bs-auto-close="outside" 而且還要處理 focus 陷阱。
  自己用一個 ref + 點外面關閉更好控制，跟 FieldHint.vue 的理由一樣。
-->
<template>
  <div ref="rootEl" class="multi-select-filter">
    <button
      type="button" class="btn btn-sm btn-outline-secondary multi-select-filter__btn"
      :aria-expanded="open ? 'true' : 'false'" @click="open = !open"
    >
      {{ label }}
      <span v-if="modelValue.length" class="badge bg-primary ms-1">{{ modelValue.length }}</span>
      <i class="bi bi-chevron-down ms-1 small"></i>
    </button>

    <div v-if="open" class="multi-select-filter__panel" role="listbox" :aria-label="label">
      <div v-if="!normalizedOptions.length" class="small hint px-2 py-2">沒有選項</div>
      <label v-for="opt in normalizedOptions" :key="opt.value" class="multi-select-filter__item">
        <input
          type="checkbox" class="form-check-input me-1"
          :checked="modelValue.includes(opt.value)"
          @change="toggle(opt.value, $event.target.checked)"
        >
        <span class="small">{{ opt.label }}</span>
      </label>
      <div v-if="modelValue.length" class="multi-select-filter__footer">
        <button type="button" class="btn btn-sm btn-link p-0" @click="clear">清除已選</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  // 字串陣列，或 {value, label} 物件陣列都可以
  options:    { type: Array, default: () => [] },
  label:      { type: String, required: true },
})
const emit = defineEmits(['update:modelValue'])

const open   = ref(false)
const rootEl = ref(null)

const normalizedOptions = computed(() => props.options.map((o) =>
  (o !== null && typeof o === 'object') ? o : { value: o, label: String(o) }))

function toggle(value, checked) {
  const next = new Set(props.modelValue)
  if (checked) next.add(value); else next.delete(value)
  emit('update:modelValue', Array.from(next))
}
function clear() {
  emit('update:modelValue', [])
}

function onDocClick(event) {
  if (open.value && rootEl.value && !rootEl.value.contains(event.target)) open.value = false
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<style scoped>
.multi-select-filter { position: relative; display: inline-block; }

.multi-select-filter__panel {
  position: absolute;
  z-index: 30;
  top: calc(100% + 4px);
  left: 0;
  min-width: 12rem;
  max-width: min(18rem, 80vw);
  max-height: 16rem;
  overflow-y: auto;
  padding: .35rem;
  border: 1px solid var(--sf-border, rgba(255, 255, 255, .25));
  border-radius: .35rem;
  background: var(--sf-surface-2, #16202e);
  /* 一定要自己設文字顏色 —— 面板背景是深色，但這個元件會被用在淺色（玩家端）
     跟深色（後台）兩種主題，繼承來的預設文字顏色在深色主題下會變成深色文字
     疊在深色背景上（幾乎看不見，肉眼要盯著才看得出來，實測截圖才抓到）。
     跟 FieldHint.vue 的 __bubble 用同一組變數、同一個理由。 */
  color: var(--sf-text, #e6edf5);
  box-shadow: 0 .4rem 1rem rgba(0, 0, 0, .45);
}

.multi-select-filter__item {
  display: flex;
  align-items: center;
  padding: .25rem .35rem;
  border-radius: .25rem;
  cursor: pointer;
  white-space: nowrap;
  color: inherit;
}
.multi-select-filter__item:hover { background: rgba(255, 255, 255, .06); }

.multi-select-filter__footer {
  margin-top: .25rem;
  padding-top: .25rem;
  border-top: 1px solid var(--sf-border, rgba(255, 255, 255, .15));
  text-align: right;
}
</style>
