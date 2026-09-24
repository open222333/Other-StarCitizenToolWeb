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
  <div ref="rootEl" class="multi-select-filter" :class="{ 'multi-select-filter--block': block }">
    <button
      :id="id" type="button" class="btn btn-sm btn-outline-secondary multi-select-filter__btn"
      :aria-expanded="open ? 'true' : 'false'" :aria-label="label" @click="toggleOpen"
    >
      <!-- block 模式（表單欄位）：按鈕上直接顯示已選的項目；一般模式（篩選列）顯示欄位名稱 -->
      <span class="multi-select-filter__text">{{ block ? (selectedSummary || placeholder || label) : label }}</span>
      <span v-if="modelValue.length" class="badge bg-primary ms-1">{{ modelValue.length }}</span>
      <i class="bi bi-chevron-down ms-1 small"></i>
    </button>

    <div v-if="open" class="multi-select-filter__panel" role="listbox" :aria-label="label">
      <input v-if="searchable" ref="searchEl" v-model="query" type="search"
        class="form-control form-control-sm mb-1" :aria-label="`篩選${label}選項`">
      <div v-if="!visibleOptions.length" class="small hint px-2 py-2">沒有選項</div>
      <label v-for="opt in visibleOptions" :key="opt.value" class="multi-select-filter__item">
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
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  // 字串陣列，或 {value, label} 物件陣列都可以
  options:    { type: Array, default: () => [] },
  label:      { type: String, required: true },
  // 選項很多時（地點、物品類型）在面板頂端加一個文字框篩選選項
  searchable: { type: Boolean, default: false },
  // 當成表單欄位用：按鈕撐滿寬度、上面顯示已選的項目（沒選時顯示 placeholder）
  block:       { type: Boolean, default: false },
  placeholder: { type: String, default: '' },
  id:          { type: String, default: undefined },
})
const emit = defineEmits(['update:modelValue'])

const open     = ref(false)
const rootEl   = ref(null)
const searchEl = ref(null)
const query    = ref('')

const normalizedOptions = computed(() => props.options.map((o) =>
  (o !== null && typeof o === 'object') ? o : { value: o, label: String(o) }))

const visibleOptions = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return normalizedOptions.value
  return normalizedOptions.value.filter(o =>
    `${o.label} ${o.value}`.toLowerCase().includes(q))
})

const selectedSummary = computed(() => {
  const byValue = new Map(normalizedOptions.value.map(o => [o.value, o.label]))
  return props.modelValue.map(v => byValue.get(v) ?? String(v)).join('、')
})

async function toggleOpen() {
  open.value = !open.value
  if (!open.value) { query.value = ''; return }
  if (props.searchable) {
    await nextTick()
    searchEl.value?.focus()
  }
}

function toggle(value, checked) {
  const next = new Set(props.modelValue)
  if (checked) next.add(value); else next.delete(value)
  emit('update:modelValue', Array.from(next))
}
function clear() {
  emit('update:modelValue', [])
}

function onDocClick(event) {
  if (open.value && rootEl.value && !rootEl.value.contains(event.target)) {
    open.value = false
    query.value = ''
  }
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<style scoped>
.multi-select-filter { position: relative; display: inline-block; }

.multi-select-filter--block { display: block; }
.multi-select-filter--block .multi-select-filter__btn {
  display: flex;
  align-items: center;
  width: 100%;
  text-align: left;
}
.multi-select-filter--block .multi-select-filter__text {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.multi-select-filter--block .multi-select-filter__panel {
  right: 0;
  max-width: none;
}

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
