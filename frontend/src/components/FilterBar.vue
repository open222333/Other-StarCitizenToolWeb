<!--
  Loot 篩選列（規格書第 12.2 節：類型／稀有度／取得地點／狀態）。
  用法：<FilterBar v-model="filters" :options="{ categories, rarities, locations, statuses }" />
-->
<template>
  <div class="d-flex flex-wrap gap-2 align-items-center mb-3 filter-bar">
    <select class="form-select form-select-sm w-auto" v-model="model.category">
      <option value="">全部類型</option>
      <option v-for="c in options.categories || []" :key="c" :value="c">{{ c }}</option>
    </select>

    <select class="form-select form-select-sm w-auto" v-model="model.rarity">
      <option value="">全部稀有度</option>
      <option v-for="r in options.rarities || []" :key="r" :value="r">{{ r }}</option>
    </select>

    <select class="form-select form-select-sm w-auto" v-model="model.location">
      <option value="">全部地點</option>
      <option v-for="l in options.locations || []" :key="l" :value="l">{{ l }}</option>
    </select>

    <select class="form-select form-select-sm w-auto" v-model="model.status">
      <option value="">全部狀態</option>
      <option v-for="s in options.statuses || []" :key="s.value" :value="s.value">{{ s.label }}</option>
    </select>

    <button v-if="hasActiveFilter" class="btn btn-sm btn-outline-secondary" @click="$emit('reset')">
      <i class="bi bi-x-circle me-1"></i>清除篩選
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },
  options:    { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue', 'reset'])

// 直接綁定父層傳入的 reactive 物件（filters store state），避免多一層拷貝
const model = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const hasActiveFilter = computed(() =>
  Object.values(props.modelValue).some(v => !!v)
)
</script>
