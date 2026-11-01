<!--
  航線的起始油量（「航線規劃」「合約分配」）：v-model 是 { mode: 'pct'（百分比）／'amount'（油量）, value }；
  value 空的＝滿油。後端換算見 src/models/nav.py 的 start_fuel_amount（超過油箱就是滿油）。
-->
<template>
  <div class="input-group input-group-sm fuel-start">
    <input :id="id" :value="modelValue.value ?? ''" type="number" min="0" :max="modelValue.mode === 'pct' ? 100 : null"
      step="any" class="form-control" placeholder="滿油" aria-label="起始油量"
      @input="update({ value: $event.target.value === '' ? null : Number($event.target.value) })">
    <select :value="modelValue.mode" class="form-select fuel-start__mode" aria-label="起始油量單位"
      @change="update({ mode: $event.target.value })">
      <option value="pct">%</option>
      <option value="amount">油量</option>
    </select>
  </div>
</template>

<script setup>
const props = defineProps({
  id: { type: String, required: true },
  modelValue: { type: Object, required: true },
})
const emit = defineEmits(['update:modelValue'])
const update = patch => emit('update:modelValue', { ...props.modelValue, ...patch })
</script>

<style scoped>
.fuel-start { max-width: 14rem; }
.fuel-start__mode { max-width: 5.5rem; }
</style>
