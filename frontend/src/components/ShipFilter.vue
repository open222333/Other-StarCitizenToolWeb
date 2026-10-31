<!--
  航線選船的篩選（「航線規劃」「合約分配」共用同一份設定，記在這台瀏覽器；見 utils/navBase.js 的 shipFilter）：
  不顯示沒有貨艙的船（預設勾）、貨艙至少幾 SCU、只看我的機庫。只影響船的候選清單，已選的船不會被清掉。
-->
<template>
  <div class="d-flex flex-wrap align-items-center gap-3 ship-filter">
    <div class="form-check mb-0">
      <input :id="`${id}-cargo`" v-model="filter.hideNoCargo" class="form-check-input" type="checkbox">
      <label class="form-check-label" :for="`${id}-cargo`">不顯示沒有貨艙的船</label>
    </div>
    <div class="d-flex align-items-center gap-2">
      <label class="mb-0 text-nowrap" :for="`${id}-min`">貨艙至少</label>
      <div class="input-group input-group-sm ship-filter__min">
        <input :id="`${id}-min`" v-model.number="filter.minScu" type="number" min="0" step="1" class="form-control">
        <span class="input-group-text">SCU</span>
      </div>
    </div>
    <div class="form-check mb-0">
      <input :id="`${id}-fleet`" v-model="filter.fleetOnly" class="form-check-input" type="checkbox">
      <label class="form-check-label" :for="`${id}-fleet`">只看我的機庫</label>
    </div>
  </div>
</template>

<script setup>
import { shipFilter as filter } from '@/utils/navBase'

defineProps({ id: { type: String, required: true } })
</script>

<style scoped>
.ship-filter__min { width: 8.5rem; }
</style>
