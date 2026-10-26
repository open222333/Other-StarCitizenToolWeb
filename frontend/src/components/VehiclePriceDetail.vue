<!--
  某艘船的遊戲內購買地點／租船地點（UEX，aUEC），各自由便宜到貴。

  GET /item/vehicles/<uuid>/prices（src/models/uex_vehicle_price.py 的 prices_for）。
  兩個地方用：後台「艦船」列表展開（預設樣式）、玩家頁「艦隊 › 船艦資料」展開（player：
  蜂巢式下拉最內層 .sf-tree-leaf）。畫面與載入邏輯在 UexPriceList.vue（跟 ItemPriceDetail 共用）。
-->
<template>
  <UexPriceList :url="url" :sections="SECTIONS" :fetcher="fetcher" :player="player" />
</template>

<script setup>
import { computed } from 'vue'
import { apiFetch } from '@/api'
import UexPriceList from '@/components/UexPriceList.vue'

const props = defineProps({
  vehicleUuid: { type: String, required: true },
  /** 帶身分的 fetch（後台 apiFetch、玩家頁 playerFetch） */
  fetcher: { type: Function, default: apiFetch },
  /** 玩家頁樣式（蜂巢式下拉最內層） */
  player: { type: Boolean, default: false },
})

const SECTIONS = [
  { key: 'purchase', label: '遊戲內購買', empty: '沒有購買地點資料' },
  { key: 'rental', label: '租船', empty: '沒有租船地點資料' },
]

const url = computed(() => `/item/vehicles/${encodeURIComponent(props.vehicleUuid)}/prices`)
</script>
