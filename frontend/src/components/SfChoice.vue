<!--
  單選的膠囊列（選項少的「全部／A／B」這種）：點一下選、再點一次取消（回到全部＝空字串）；
  加 required 就是一定要選一個的設定（例如航線終點、油量單位），再點一次不會取消。
  樣式同 .sf-pill（scifi-theme.css；後台淺色、玩家頁主題色），跟多選選項、開關（SfToggle）同一套。
    <SfChoice v-model="playerVisible" :options="[{ value: '1', label: '顯示' }, { value: '0', label: '不顯示' }]" label="玩家頁面" />
-->
<template>
  <div :id="id || undefined" class="sf-pills sf-pills--field" role="group" :aria-label="label">
    <button v-for="o in options" :key="o.value" type="button" class="sf-pill" :class="{ active: modelValue === o.value }"
      :aria-pressed="modelValue === o.value ? 'true' : 'false'" @click="$emit('update:modelValue', modelValue === o.value && !required ? '' : o.value)">
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
  /** 一定要選一個（例如終點、單位）：再點一次不會取消 */
  required: { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
</script>
