<!--
  Loot／Blueprint 狀態徽章，涵蓋規格書第 6.4 節（Loot 狀態）與第 11.1 節（未確認資料標記）。
  用法：<StatusBadge :status="item.status" />
-->
<template>
  <span :class="`badge bg-${color}`">
    <i v-if="icon" :class="`bi ${icon} me-1`"></i>{{ label }}
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: '' },
})

// key: [顯示文字, badge 顏色, bootstrap-icon class]
const STATUS_MAP = {
  in_stock:     ['庫存中', 'secondary', 'bi-box-seam'],
  held:         ['玩家持有', 'primary', 'bi-person-fill'],
  equipped:     ['已裝備', 'success', 'bi-shield-fill-check'],
  transferred:  ['已轉交', 'info', 'bi-arrow-left-right'],
  sold:         ['已出售', 'warning', 'bi-currency-exchange'],
  lost:         ['已遺失', 'dark', 'bi-skull'],
  consumed:     ['已消耗', 'secondary', 'bi-trash'],
  unconfirmed:  ['未確認', 'warning', 'bi-question-circle'],
  outdated:     ['已過時', 'danger', 'bi-exclamation-triangle'],
  confirmed:    ['已確認', 'success', 'bi-check-circle'],
}

const entry = computed(() => STATUS_MAP[props.status] || [props.status || '—', 'secondary', ''])
const label = computed(() => entry.value[0])
const color = computed(() => entry.value[1])
const icon  = computed(() => entry.value[2])
</script>
