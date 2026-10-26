<!--
  後台列表的搜尋卡（比照玩家頁的共用搜尋卡）：條件照列表的欄位名稱排成一列，每格上方有欄位名稱；
  不對應列表欄位的勾選類條件（例如「只看沒有中文」）放在下面一列（slot options），右邊是「清除篩選」。

  用法：
    <AdminSearchCard :active="hasActiveFilters" @clear="resetFilters">
      <AdminSearchField label="類型" for-id="mission-scope" col="col-6 col-md-3 col-xl-2">
        <MultiSelectFilter id="mission-scope" … block />
      </AdminSearchField>
      <template #options> 勾選框… </template>
    </AdminSearchCard>
-->
<template>
  <div class="card shadow-sm border-0 mb-3 admin-search">
    <div class="card-body py-3">
      <div class="row g-2 align-items-end">
        <slot />
      </div>
      <div v-if="$slots.options || active || $slots.summary" class="d-flex flex-wrap align-items-center gap-2 mt-2">
        <slot name="options" />
        <span v-if="$slots.summary" class="small text-muted"><slot name="summary" /></span>
        <button v-if="active" type="button" class="btn btn-sm btn-warning ms-auto" @click="$emit('clear')">
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
.admin-search :deep(.form-label) { font-size: .875rem; }
</style>
