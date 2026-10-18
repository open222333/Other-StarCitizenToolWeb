<!-- 後台搜尋卡的一格：上方欄位名稱（跟列表的欄位名稱一致）＋下方輸入元件（見 AdminSearchCard.vue） -->
<template>
  <div :class="col">
    <label class="form-label small fw-semibold mb-1" :for="forId || undefined">{{ label }}</label>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  /** 輸入元件的 id（點欄位名稱聚焦） */
  forId: { type: String, default: '' },
  /** 這一格的寬度（bootstrap col 類別） */
  col: { type: String, default: 'col-6 col-md-3 col-xl-2' },
})
</script>
