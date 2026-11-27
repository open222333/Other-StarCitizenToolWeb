<!--
  單一條件的開關（篩選用，例如「只看買得到」「只看有藍圖」）：膠囊按鈕，按一下打開（實心強調色）、再按一下關掉。
  玩家頁的篩選一律用這個，不用勾選框（樣式見 scifi-theme.css 的 .sf-pill，跟多選選項、範圍級距同一套）。
    <SfToggle v-model="buyableOnly" icon="bi bi-cart3">只看買得到</SfToggle>
-->
<template>
  <button type="button" class="sf-pill" :class="{ active: modelValue }" :aria-pressed="modelValue ? 'true' : 'false'"
    @click="$emit('update:modelValue', !modelValue)">
    <i v-if="icon" :class="icon" aria-hidden="true"></i><slot />
  </button>
</template>

<script setup>
defineProps({
  modelValue: { type: Boolean, default: false },
  icon: { type: String, default: '' },
})
defineEmits(['update:modelValue'])
</script>
