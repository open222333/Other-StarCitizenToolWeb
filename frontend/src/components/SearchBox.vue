<!--
  全域搜尋輸入框（規格書第 12.1 節）。用法：<SearchBox v-model="keyword" placeholder="搜尋 Loot..." />
-->
<template>
  <div class="input-group input-group-sm search-box">
    <span class="input-group-text bg-transparent border-end-0">
      <i class="bi bi-search"></i>
    </span>
    <input
      class="form-control border-start-0"
      type="search"
      :placeholder="placeholder"
      :value="modelValue"
      @input="$emit('update:modelValue', $event.target.value)"
    >
  </div>
</template>

<script setup>
defineProps({
  modelValue:  { type: String, default: '' },
  placeholder: { type: String, default: '搜尋...' },
})
defineEmits(['update:modelValue'])
</script>

<style scoped>
.search-box { max-width: 320px; }
</style>
