<!--
  單欄位自動完成——打字列出候選、用鍵盤或點擊選一個「精確值」代入，不是
  子字串即時篩選。跟 BlueprintCalculator.vue「選藍圖」欄位（搜尋→高亮→
  Enter/點擊選定→送出）同一套互動邏輯，抽成共用元件是因為「查詢」頁一次
  要用到 9 個（物品庫存 5 個＋持有藍圖 4 個），各自複製一份會很容易讓
  鍵盤操作或 aria 屬性在某幾個欄位漏掉、之後修一個 bug 要改 9 個地方。

  「精確值」的意思：只有使用者從候選清單裡選定，才會透過 @select 把選中
  的候選物件整個丟給外面；純打字不會觸發 @select，外面收到的篩選條件
  永遠是「使用者確實選過的東西」，不會被還沒選定的殘留文字污染。

  兩種候選來源都支援，呼叫端用同一個 `search(query)` 介面：
  - 伺服器搜尋（物品／藍圖／玩家名稱）：search 是打 API 的 async 函式，
    debounceMs 給預設 300ms 節流。
  - 本地清單過濾（物品類型／地點／藍圖類型，清單本來就是先整包載好的
    幾十筆）：search 包成同步邏輯包在 Promise 裡就好，debounceMs 可以
    傳 0，minChars 通常也傳 0（一 focus 就看到完整清單，不用先打字）。
-->
<template>
  <div ref="rootEl" class="autocomplete-field position-relative">
    <div class="d-flex gap-1">
      <input :id="id" :value="modelValue" type="text" class="form-control form-control-sm"
        role="combobox" aria-autocomplete="list" :aria-expanded="showResults"
        :aria-controls="listId" :aria-activedescendant="activeOptionId"
        :aria-label="ariaLabel" :placeholder="placeholder" autocomplete="off"
        @input="onInput($event.target.value)" @focus="onFocus" @keydown="onKeydown" @blur="onBlur">
      <button v-if="modelValue" type="button" class="btn btn-sm btn-outline-secondary"
        :aria-label="`清除${ariaLabel}`" @mousedown.prevent="clear">×</button>
    </div>
    <ul v-if="showResults" :id="listId" role="listbox" class="autocomplete-field__list">
      <li v-if="searching" class="autocomplete-field__hint">搜尋中…</li>
      <li v-else-if="!results.length" class="autocomplete-field__hint">沒有符合的候選</li>
      <li v-else v-for="(c, i) in results" :key="i" :id="`${listId}-${i}`"
        role="option" :aria-selected="i === highlighted"
        class="autocomplete-field__item" :class="{ 'is-active': i === highlighted }"
        @mousedown.prevent="pick(c)" @mousemove="highlighted = i">
        {{ getLabel(c) }}
      </li>
    </ul>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  // async (query) => candidate[]
  search:     { type: Function, required: true },
  // candidate => 顯示文字（下拉選項文字，選定後也是這個文字寫進 modelValue）
  getLabel:   { type: Function, required: true },
  placeholder: { type: String, default: '' },
  ariaLabel:  { type: String, default: '' },
  id:         { type: String, default: () => `ac-${Math.random().toString(36).slice(2, 9)}` },
  // 少於這個字數不查（伺服器搜尋欄位通常設 1，本地清單欄位可以設 0，
  // 這樣一 focus 就看得到完整清單）
  minChars:   { type: Number, default: 1 },
  debounceMs: { type: Number, default: 300 },
})
const emit = defineEmits(['update:modelValue', 'select'])

const results = ref([])
const searching = ref(false)
const showResults = ref(false)
const highlighted = ref(-1)
const listId = `${props.id}-list`
const activeOptionId = computed(() =>
  highlighted.value >= 0 ? `${listId}-${highlighted.value}` : undefined)

let timer = null
let seq = 0

function runSearch(q) {
  clearTimeout(timer)
  const mine = ++seq
  searching.value = true
  timer = setTimeout(async () => {
    const rows = await props.search(q)
    if (mine !== seq) return   // 過期回應：已經有更新的查詢在跑了
    results.value = rows || []
    searching.value = false
  }, props.debounceMs)
}

function onInput(value) {
  emit('update:modelValue', value)
  // 文字改了就代表使用者還沒選定新的候選——先撤銷上一次的選定，避免外面
  // 拿著「已經對不上目前輸入文字」的舊選定值繼續當篩選條件用。
  emit('select', null)
  showResults.value = true
  highlighted.value = -1
  const q = value.trim()
  if (q.length < props.minChars) {
    clearTimeout(timer)
    seq += 1
    results.value = []
    searching.value = false
    return
  }
  runSearch(q)
}

function onFocus() {
  showResults.value = true
  const q = props.modelValue.trim()
  if (q.length >= props.minChars) runSearch(q)
}

function onKeydown(event) {
  if (event.key === 'Escape') { showResults.value = false; return }
  if (!showResults.value || !results.value.length) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlighted.value = (highlighted.value + 1) % results.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlighted.value = highlighted.value <= 0 ? results.value.length - 1 : highlighted.value - 1
  } else if (event.key === 'Enter') {
    event.preventDefault()
    pick(results.value[highlighted.value >= 0 ? highlighted.value : 0])
  }
}

function onBlur() {
  // 延遲關閉，讓候選項的 mousedown 先觸發選定——不然 blur 比 click 先跑，
  // 選項還沒被點到清單就先收起來了（BlueprintCalculator.vue 同樣的理由）。
  setTimeout(() => { showResults.value = false }, 120)
}

function pick(candidate) {
  if (!candidate) return
  emit('update:modelValue', props.getLabel(candidate))
  emit('select', candidate)
  showResults.value = false
  results.value = []
}

function clear() {
  clearTimeout(timer)
  seq += 1
  emit('update:modelValue', '')
  emit('select', null)
  results.value = []
  showResults.value = false
}

const rootEl = ref(null)
function onDocClick(event) {
  if (showResults.value && rootEl.value && !rootEl.value.contains(event.target)) {
    showResults.value = false
  }
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => { document.removeEventListener('click', onDocClick); clearTimeout(timer) })
</script>

<style scoped>
.autocomplete-field__list {
  position: absolute;
  z-index: 30;
  top: calc(100% + 2px);
  left: 0;
  right: 0;
  max-height: 14rem;
  overflow-y: auto;
  margin: 0;
  padding: .3rem;
  list-style: none;
  /* 這個元件只會用在玩家頁（深色 scifi 主題），照 MultiSelectFilter.vue
     的理由給深色 fallback，不能讓面板背景跟繼承文字色一樣暗（幾乎看不見）。 */
  border: 1px solid var(--sf-border, rgba(255, 255, 255, .25));
  border-radius: .35rem;
  background: var(--sf-surface-2, #16202e);
  color: var(--sf-text, #e6edf5);
  box-shadow: 0 .4rem 1rem rgba(0, 0, 0, .45);
}
.autocomplete-field__item {
  padding: .3rem .5rem;
  border-radius: .25rem;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.autocomplete-field__item:hover,
.autocomplete-field__item.is-active { background: rgba(127, 127, 127, .18); }
.autocomplete-field__hint {
  padding: .3rem .5rem;
  opacity: .65;
  font-size: .85em;
}
</style>
