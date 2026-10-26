<!--
  某個物品在哪裡買得到／哪裡收（UEX，aUEC）：購買由便宜到貴、收購由高到低。

  GET /item/<uuid>/uex-prices（src/models/uex_item_price.py 的 prices_for）。UEX 沒有這個物品時
  退回 Wiki 內嵌的購買價（source=wiki，只有購買、沒有地點路徑）。
  兩個地方用：後台「物品」列表展開（預設樣式）、玩家頁「倉庫 › 物品資料」展開（player：.sf-tree-leaf）。
  畫面與載入邏輯在 UexPriceList.vue（跟 VehiclePriceDetail 共用）。
-->
<template>
  <UexPriceList :url="url" :sections="sections" :fetcher="fetcher" :player="player" />
</template>

<script setup>
import { computed } from 'vue'
import { apiFetch } from '@/api'
import UexPriceList from '@/components/UexPriceList.vue'

const props = defineProps({
  itemUuid: { type: String, required: true },
  /** 帶身分的 fetch（後台 apiFetch、玩家頁 playerFetch） */
  fetcher: { type: Function, default: apiFetch },
  /** 玩家頁樣式（蜂巢式下拉最內層） */
  player: { type: Boolean, default: false },
  /** 只顯示購買地點（玩家頁不需要收購） */
  buyOnly: { type: Boolean, default: false },
})

const SECTIONS = [
  { key: 'buy', label: '購買地點', empty: '沒有購買地點資料' },
  { key: 'sell', label: '收購地點', empty: '沒有收購地點資料' },
]

const url = computed(() => `/item/${encodeURIComponent(props.itemUuid)}/uex-prices`)
const sections = computed(() => (props.buyOnly ? SECTIONS.slice(0, 1) : SECTIONS))
</script>
