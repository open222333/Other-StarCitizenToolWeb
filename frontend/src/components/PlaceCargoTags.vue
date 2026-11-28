<!--
  地點的貨運設施標籤（航線規劃、合約分配的站點欄）：外部貨運（裝卸碼頭，外掛貨櫃的 Hull 系列只能在這種站點裝卸）、
  貨梯（貨物從貨運電梯進出）。資料是 GET /starmap/nav/places 的 loading_dock／freight_elevator（src/models/nav.py）。
-->
<template>
  <span v-if="place && (place.loading_dock || place.freight_elevator)" class="pct">
    <span v-if="place.loading_dock" class="sf-chip sf-chip--ok pct-chip">外部貨運</span>
    <span v-if="place.freight_elevator" class="sf-chip pct-chip">貨梯</span>
  </span>
</template>

<script setup>
defineProps({
  place: { type: Object, default: null },
})
</script>

<style scoped>
.pct { display: inline-flex; flex-wrap: wrap; gap: .25rem; align-self: center; }
.pct-chip { margin: 0; font-size: var(--sf-fs-xs); }
</style>
