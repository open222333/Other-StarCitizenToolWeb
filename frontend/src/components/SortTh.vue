<!--
  可點擊排序的表頭（搭配 composables/useTableSort.js）。
    <SortTh :sort="sort" field="name" class="ps-3">名稱</SortTh>
  sort 是 useTableSort() 的回傳值；field 是排序欄位（前端排序對應 accessors 的 key，後端排序就是 sort_by）。
  沒有 field 的表頭照一般 <th> 用就好。
-->
<template>
  <th class="sort-th" role="button" tabindex="0" :aria-sort="ariaSort"
    @click="sort.toggle(field)" @keydown.enter.prevent="sort.toggle(field)" @keydown.space.prevent="sort.toggle(field)">
    <slot />
    <i class="bi ms-1 sort-th__icon" :class="iconClass" aria-hidden="true"></i>
  </th>
</template>

<script setup>
import { computed, unref } from 'vue'

const props = defineProps({
  sort: { type: Object, required: true },
  field: { type: String, required: true },
})

const active = computed(() => unref(props.sort.sortKey) === props.field)
const dir = computed(() => unref(props.sort.sortDir))
const iconClass = computed(() => (active.value
  ? (dir.value === 'desc' ? 'bi-sort-down' : 'bi-sort-up')
  : 'bi-arrow-down-up sort-th__icon--idle'))
const ariaSort = computed(() => (active.value ? (dir.value === 'desc' ? 'descending' : 'ascending') : 'none'))
</script>

<style scoped>
.sort-th { cursor: pointer; user-select: none; white-space: nowrap; }
.sort-th:hover { color: var(--sf-accent, var(--bs-primary)); }
.sort-th__icon { font-size: .85em; }
.sort-th__icon--idle { opacity: .35; }
.sort-th:hover .sort-th__icon--idle { opacity: .7; }
</style>
