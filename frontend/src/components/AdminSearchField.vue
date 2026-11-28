<!-- 後台搜尋卡的一格：上方欄位名稱（跟列表的欄位名稱一致）＋下方輸入元件（見 AdminSearchCard.vue）。
     寬度：一般 11rem 起、可以撐開；wide（名稱搜尋）18rem 起；裡面是膠囊（選項少、開關）就照內容寬。 -->
<template>
  <div class="admin-search__field" :class="{ 'admin-search__field--wide': isWide }">
    <label class="form-label small fw-semibold mb-1" :for="forId || undefined">{{ label }}</label>
    <slot />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: { type: String, required: true },
  /** 輸入元件的 id（點欄位名稱聚焦） */
  forId: { type: String, default: '' },
  /** 名稱搜尋這種要寬一點的 */
  wide: { type: Boolean, default: false },
  /** 舊參數（bootstrap col）：含 col-md-6 的當成 wide，其餘不再使用 */
  col: { type: String, default: '' },
})
const isWide = computed(() => props.wide || /col-md-6/.test(props.col))
</script>

<style scoped>
.admin-search__field { flex: 1 1 11rem; min-width: 10rem; max-width: 20rem; }
.admin-search__field--wide { flex: 2 1 18rem; max-width: 28rem; }
/* 膠囊（選項少的多選、單選、開關）照內容寬，不撐開 */
.admin-search__field:has(> .sf-pills) { flex: 0 0 auto; min-width: 0; max-width: none; }
.admin-search__field .form-label { display: block; font-size: .875rem; white-space: nowrap; }
@media (max-width: 575.98px) {
  .admin-search__field, .admin-search__field--wide { flex-basis: 100%; max-width: none; }
}
</style>
