<!--
  戰利品稀有度標籤（規格書第 6.3 節）。
  用法：<RarityTag :rarity="item.rarity" />
-->
<template>
  <span :class="`badge rounded-pill bg-${color}`">{{ label }}</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  rarity: { type: String, default: 'Unknown' },
})

const RARITY_COLORS = {
  Common:    'secondary',
  Uncommon:  'success',
  Rare:      'primary',
  'Very Rare': 'info',
  Epic:      'purple',
  Legendary: 'warning',
  Unknown:   'secondary',
}

const color = computed(() => RARITY_COLORS[props.rarity] || 'secondary')
const label = computed(() => props.rarity || 'Unknown')
</script>

<style scoped>
/* Bootstrap 沒有內建 purple，補一個給 Epic 用 */
.bg-purple { background-color: #8b5cf6 !important; color: #fff; }
</style>
