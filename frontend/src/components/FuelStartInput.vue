<!--
  航線的起始油量（「航線規劃」「合約分配」）：v-model 是 { mode: 'pct'（百分比）／'amount'（油量）, value }；
  value 空的＝滿油。後端換算見 src/models/nav.py 的 start_fuel_amount（超過油箱就是滿油）。
-->
<template>
  <div class="fuel-start">
    <input :id="id" :value="modelValue.value ?? ''" type="number" min="0" :max="modelValue.mode === 'pct' ? 100 : null"
      step="any" class="form-control form-control-sm fuel-start__value" placeholder="滿油" aria-label="起始油量"
      @input="update({ value: $event.target.value === '' ? null : Number($event.target.value) })">
    <!-- 單位：膠囊單選（一定要選一個） -->
    <SfChoice :model-value="modelValue.mode" required label="起始油量單位"
      :options="[{ value: 'pct', label: '%' }, { value: 'amount', label: '油量' }]" @update:model-value="v => update({ mode: v })" />
  </div>
</template>

<script setup>
import SfChoice from '@/components/SfChoice.vue'

const props = defineProps({
  id: { type: String, required: true },
  modelValue: { type: Object, required: true },
})
const emit = defineEmits(['update:modelValue'])
const update = patch => emit('update:modelValue', { ...props.modelValue, ...patch })
</script>

<style scoped>
.fuel-start { display: flex; flex-wrap: wrap; align-items: center; gap: .5rem; }
.fuel-start__value { flex: 0 1 9rem; min-width: 6rem; }
</style>
