<!--
  列表／區塊的狀態切換：載入中 → 讀取失敗（含「重試」）→ 沒有資料 → 預設 slot（內容）。
  文字統一：載入中「載入中…」、重試「重試」。
    <SfState :loading="loading" :error="error" :empty="!rows.length" @retry="load">
      <table>…</table>
    </SfState>
-->
<template>
  <div v-if="loading" class="sf-state sf-state--loading" role="status" aria-live="polite">
    <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>{{ loadingText }}
  </div>
  <div v-else-if="error" class="sf-state sf-state--error" role="alert">
    <span class="sf-state__msg">{{ error }}</span>
    <button type="button" class="btn btn-sm btn-primary" @click="$emit('retry')">
      <i class="bi bi-arrow-clockwise me-1"></i>重試
    </button>
  </div>
  <div v-else-if="empty" class="sf-state sf-state--empty">{{ emptyText }}</div>
  <slot v-else />
</template>

<script setup>
defineProps({
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  empty: { type: Boolean, default: false },
  emptyText: { type: String, default: '沒有資料' },
  loadingText: { type: String, default: '載入中…' },
})
defineEmits(['retry'])
</script>

<style scoped>
.sf-state {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: .5rem;
  padding: 1.25rem 1rem; text-align: center; color: var(--bs-secondary-color);
}
.sf-state--error .sf-state__msg { color: rgb(var(--bs-danger-rgb)); }
</style>
