<!--
  航段表「貨艙」欄（RouteLegsTable.vue 貨物規劃開啟時）：離開這站時貨艙用量（超過容量標紅）＋「貨物」按鈕（發 open，上層開視窗）。
-->
<template>
  <div class="rcc">
    <span class="text-nowrap" :class="{ 'sf-bad fw-semibold': flow?.over }">
      {{ fmt(flow?.total) }}<span v-if="capacity" class="text-muted"> / {{ fmt(capacity) }}</span></span>
    <div v-if="capacity" class="rcc-bar" aria-hidden="true">
      <div :class="{ 'is-over': flow?.over }" :style="{ width: `${Math.min(100, (flow?.total || 0) / capacity * 100)}%` }"></div>
    </div>
    <button type="button" class="btn btn-sm btn-info mt-1" aria-haspopup="dialog" :aria-label="label" @click="emit('open')">
      <i class="bi bi-box-seam me-1"></i>貨物<span v-if="count" class="ms-1">{{ count }}</span></button>
  </div>
</template>

<script setup>
defineProps({
  flow: { type: Object, default: null },
  capacity: { type: Number, default: 0 },
  count: { type: Number, default: 0 },
  label: { type: String, default: '貨物' },
})
const emit = defineEmits(['open'])
const fmt = v => Math.round(Number(v) || 0).toLocaleString('en-US')
</script>

<style scoped>
.rcc { display: inline-flex; flex-direction: column; align-items: flex-end; min-width: 6rem; }
.rcc-bar { width: 6rem; height: .3rem; margin-top: .2rem; border-radius: .2rem; background: var(--sf-chip-bg); overflow: hidden; }
.rcc-bar > div { height: 100%; background: var(--sf-accent); }
.rcc-bar > div.is-over { background: rgb(var(--bs-danger-rgb)); }
@media (max-width: 767.98px) { .rcc { align-items: flex-start; } }
</style>
