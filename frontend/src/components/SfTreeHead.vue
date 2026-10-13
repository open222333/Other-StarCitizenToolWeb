<!--
  蜂巢式下拉（.sf-tree-*）的欄位名稱列：每欄一個名稱，有 field 的可以點擊排序
  （sort 是 composables/useTableSort.js 的回傳值）。欄寬用外層的 --sf-tree-cols，
  跟 .sf-tree-row--cols 的上層列同一組，所以會對齊（樣式見 scifi-theme.css）。

    <SfTreeHead :sort="sort" :columns="[{ label: '船艦', field: 'name' }, { label: '數量', field: 'qty', end: true }]" />

  column：label、field（沒有就不能排序）、end（靠右）、opt（手機上隱藏）。
-->
<template>
  <div class="sf-tree-head" role="row">
    <div v-for="c in columns" :key="c.label" role="columnheader" class="sf-tree-cell"
      :class="{ 'sf-tree-cell--end': c.end, 'sf-tree-cell--opt': c.opt }"
      :aria-sort="c.field && sort && isActive(c) ? (dir === 'desc' ? 'descending' : 'ascending') : undefined">
      <button v-if="c.field && sort" type="button" class="sf-tree-head__btn" :class="{ 'is-active': isActive(c) }"
        @click="sort.toggle(c.field)">
        {{ c.label }}<i class="bi sf-tree-head__icon" :class="iconOf(c)" aria-hidden="true"></i>
      </button>
      <span v-else>{{ c.label }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, unref } from 'vue'

const props = defineProps({
  columns: { type: Array, required: true },
  sort: { type: Object, default: null },
})
const dir = computed(() => unref(props.sort?.sortDir))
const isActive = c => unref(props.sort?.sortKey) === c.field
const iconOf = c => (isActive(c)
  ? (dir.value === 'desc' ? 'bi-sort-down' : 'bi-sort-up')
  : 'bi-arrow-down-up sf-tree-head__icon--idle')
</script>
