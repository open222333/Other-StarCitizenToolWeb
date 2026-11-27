<!--
  航線選船的篩選（「航線規劃」「合約分配」共用同一份設定，記在這台瀏覽器；見 utils/navBase.js 的 shipFilter）：
  不顯示沒有貨艙的船（預設勾）、貨艙至少幾 SCU（拉條＋輸入框＋級距）、只看我的機庫。只影響船的候選清單，已選的船不會被清掉。
-->
<template>
  <div class="d-flex flex-wrap align-items-start gap-2 ship-filter">
    <SfToggle v-model="filter.hideNoCargo">不顯示沒有貨艙的船</SfToggle>
    <!-- 貨艙至少：拉條＋輸入框＋級距（只有下限，components/SfRangeFilter.vue） -->
    <div class="d-flex align-items-start gap-2 ship-filter__min">
      <label class="mb-0 text-nowrap ship-filter__label" :for="`${id}-min`">貨艙至少</label>
      <SfRangeFilter :id="`${id}-min`" single :model-value="{ min: filter.minScu || '', max: '' }" :max="SCU_RANGE.max"
        :presets="MIN_SCU_PRESETS" unit="SCU" label="貨艙至少" @update:model-value="r => { filter.minScu = r.min === '' ? null : r.min }" />
    </div>
    <SfToggle v-model="filter.fleetOnly">{{ fleetLabel }}</SfToggle>
  </div>
</template>

<script setup>
import SfToggle from '@/components/SfToggle.vue'
import SfRangeFilter from '@/components/SfRangeFilter.vue'
import { shipFilter as filter } from '@/utils/navBase'
import { SCU_RANGE } from '@/utils/uexCommodity'

// 貨艙至少的級距（只有下限）
const MIN_SCU_PRESETS = [32, 100, 500, 1000].map(n => ({ label: `${n.toLocaleString('en-US')} 以上`, min: n, max: '' }))

defineProps({
  id: { type: String, required: true },
  fleetLabel: { type: String, default: '只看我的機庫' },
})
</script>

<style scoped>
.ship-filter__min { flex: 1 1 20rem; max-width: 28rem; }
.ship-filter__label { padding-top: .1rem; }

.ship-filter__min > .srf { flex: 1 1 auto; min-width: 0; }
</style>
