<!--
  後台列表的搜尋卡（跟玩家頁的搜尋卡同一套做法）：條件照列表的欄位名稱排，每格上方有欄位名稱，
  欄位自動換行、寬度一致（名稱搜尋比較寬、膠囊選項照內容寬），標籤都對齊在同一條線上。
  選項少的條件用膠囊（MultiSelectFilter 選項 ≤ 4 會自動列出來、單選用 SfChoice、開關用 SfToggle），不用下拉或勾選框。
  不對應列表欄位的開關（例如「只看沒有中文」）放下面一列（slot options），右邊是筆數（slot summary）與「清除篩選」。

  用法：
    <AdminSearchCard :active="hasActiveFilters" @clear="resetFilters">
      <AdminSearchField label="名稱" for-id="x-q" wide> <input …> </AdminSearchField>
      <AdminSearchField label="類型" for-id="x-type"> <MultiSelectFilter … block /> </AdminSearchField>
      <template #options> <SfToggle v-model="missingZh">只看沒有中文</SfToggle> </template>
    </AdminSearchCard>
-->
<template>
  <div class="card shadow-sm border-0 mb-3 admin-search">
    <div class="card-body py-3">
      <div class="admin-search__fields">
        <slot />
      </div>
      <div v-if="$slots.options || active || $slots.summary" class="admin-search__foot">
        <div class="sf-pills"><slot name="options" /></div>
        <span v-if="$slots.summary" class="small text-muted ms-auto"><slot name="summary" /></span>
        <button v-if="active" type="button" class="btn btn-sm btn-warning" :class="{ 'ms-auto': !$slots.summary }" @click="$emit('clear')">
          <i class="bi bi-x-lg me-1"></i>清除篩選
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  /** 有任何條件在作用（顯示「清除篩選」） */
  active: { type: Boolean, default: false },
})
defineEmits(['clear'])
</script>

<style scoped>
.admin-search {
  /* 搜尋卡裡共用的玩家頁元件（範圍拉條 SfRangeFilter…）改用後台的主色與框線 */
  --sf-accent: var(--bs-primary); --sf-accent-rgb: var(--bs-primary-rgb); --sf-border: var(--bs-border-color);
}
.admin-search__fields { display: flex; flex-wrap: wrap; gap: .75rem 1rem; align-items: flex-start; }
.admin-search__foot {
  display: flex; flex-wrap: wrap; align-items: center; gap: .5rem;
  margin-top: .75rem; padding-top: .75rem; border-top: 1px solid var(--bs-border-color-translucent);
}
.admin-search__foot:has(> .sf-pills:empty):not(:has(> button, > span)) { display: none; }
</style>
