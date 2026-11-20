<!--
  航段表「動作」欄底下的貨物規劃摘要（RouteLegsTable.vue）：這一站裝／卸什麼、幾 SCU、拆成哪些貨櫃；卸得比艙內多的標警告。
-->
<template>
  <div v-if="rows.length || shorts?.length" class="d-flex gap-1" :class="inline ? 'flex-wrap align-items-center rcs-inline' : 'flex-column mt-1'">
    <div v-for="e in rows" :key="e.key" class="rcs">
      <span class="sf-chip mb-0 text-nowrap" :class="e.action === 'unload' ? 'sf-chip--ok' : 'sf-chip--accent'">
        {{ e.action === 'unload' ? '卸' : '裝' }} {{ e.item || '（未命名）' }} {{ fmt(e.scu) }} SCU</span>
      <span class="rcs-crates">{{ cratesText(splitCrates(e.scu, e.max)) }}</span>
    </div>
    <div v-if="shorts?.length" class="d-flex flex-wrap gap-1">
      <span v-for="n in shorts" :key="n" class="sf-chip sf-chip--warn mb-0">卸 {{ n }} 比艙內多</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { cratesText, splitCrates } from '@/utils/crateCombos'

const props = defineProps({
  entries: { type: Array, default: () => [] },
  shorts: { type: Array, default: () => [] },
  /** 排成一行（航線規劃表單的站點列中間） */
  inline: { type: Boolean, default: false },
})
const rows = computed(() => props.entries.filter(e => Number(e.scu) > 0))
const fmt = v => Math.round(Number(v) || 0).toLocaleString('en-US')
</script>

<style scoped>
.rcs { display: flex; flex-wrap: wrap; align-items: center; gap: .25rem .5rem; }
.rcs-crates { font-size: .85rem; color: var(--sf-text-muted); }
.rcs-inline { column-gap: .75rem; }
</style>
