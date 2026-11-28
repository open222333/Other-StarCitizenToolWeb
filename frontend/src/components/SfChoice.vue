<!--
  單選的膠囊列（篩選用，選項少的「全部／A／B」這種）：點一下選、再點一次取消（回到全部＝空字串）。
  樣式同 .sf-pill（scifi-theme.css；後台淺色、玩家頁主題色），跟多選選項、開關（SfToggle）同一套。
    <SfChoice v-model="playerVisible" :options="[{ value: '1', label: '顯示' }, { value: '0', label: '不顯示' }]" label="玩家頁面" />
-->
<template>
  <div :id="id || undefined" class="sf-pills sf-pills--field" role="group" :aria-label="label">
    <button v-for="o in options" :key="o.value" type="button" class="sf-pill" :class="{ active: modelValue === o.value }"
      :aria-pressed="modelValue === o.value ? 'true' : 'false'" @click="$emit('update:modelValue', modelValue === o.value ? '' : o.value)">
      {{ o.label }}<span v-if="o.count !== undefined && o.count !== null" class="sf-pill__count">{{ o.count }}</span>
    </button>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: [String, Number, Boolean], default: '' },
  /** [{ value, label, count? }] */
  options: { type: Array, required: true },
  label: { type: String, default: '' },
  id: { type: String, default: '' },
})
defineEmits(['update:modelValue'])
</script>
