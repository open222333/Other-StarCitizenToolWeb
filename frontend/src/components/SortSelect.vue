<!--
  手機用的排序下拉（表格在手機改成卡片，表頭看不到，點表頭排序改用這個）。
  背後跟 SortTh 共用同一個 useTableSort 的狀態，所以兩邊會同步。
    <SortSelect :sort="sort" :options="[{ field: 'name', label: '名稱' }, …]" />
-->
<template>
  <select class="form-select form-select-sm sf-sort-select" :value="current" aria-label="排序" @change="pick">
    <option value="">預設排序</option>
    <template v-for="o in options" :key="o.field">
      <option :value="`${o.field}:asc`">{{ o.label }} ↑</option>
      <option :value="`${o.field}:desc`">{{ o.label }} ↓</option>
    </template>
  </select>
</template>

<script setup>
import { computed, unref } from 'vue'

const props = defineProps({
  sort: { type: Object, required: true },
  options: { type: Array, required: true },
})

const current = computed(() => {
  const key = unref(props.sort.sortKey)
  return key ? `${key}:${unref(props.sort.sortDir)}` : ''
})

function pick(e) {
  const [field, dir] = (e.target.value || '').split(':')
  props.sort.set(field || '', dir || 'asc')
}
</script>
