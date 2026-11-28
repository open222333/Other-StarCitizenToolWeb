<!--
  航線規劃的站點欄（起點、途經站點、終點同一種顯示）：選好地點後收成一行「名稱＋所屬星系／行星」，
  後面標貨運設施（外部貨運、貨梯，PlaceCargoTags）；點一下（或鉛筆）回到地點選擇器（PlacePicker.vue）改；還沒選地點時直接是選擇器。v-model＝{ id, text }。
-->
<template>
  <div v-if="place && !editing" class="ps-show" role="button" tabindex="0" :aria-label="`${label}：${placeLabel(place)}，按一下更改`"
    @click="edit" @keydown.enter.prevent="edit" @keydown.space.prevent="edit">
    <span class="fw-semibold">{{ placeLabel(place) }}</span>
    <span class="ps-path">{{ placePath(place) }}</span>
    <PlaceCargoTags :place="place" />
    <i class="bi bi-pencil ps-edit ms-auto" aria-hidden="true"></i>
  </div>
  <PlacePicker v-else :id="id" :label="label" :places="places" :model-value="modelValue"
    @update:model-value="pick" />
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import PlaceCargoTags from '@/components/PlaceCargoTags.vue'
import PlacePicker from '@/components/PlacePicker.vue'
import { placeLabel, placePath } from '@/utils/navFormat'

const props = defineProps({
  id: { type: String, required: true },
  label: { type: String, default: '' },
  places: { type: Array, default: () => [] },
  modelValue: { type: Object, required: true },
})
const emit = defineEmits(['update:modelValue'])

const place = computed(() => (props.modelValue.id ? props.places.find(p => p.id === props.modelValue.id) || null : null))
const editing = ref(false)
async function edit() {
  editing.value = true
  await nextTick()
  document.getElementById(props.id)?.focus()
}
function pick(v) {
  emit('update:modelValue', v)
  if (v.id) editing.value = false
}
</script>

<style scoped>
.ps-show {
  display: flex; flex-wrap: wrap; align-items: baseline; gap: .1rem .6rem; padding: .25rem .5rem; cursor: pointer;
  border: 1px solid var(--sf-border); border-radius: .375rem; background: var(--sf-chip-bg); min-height: calc(1.5em + .5rem + 2px);
}
.ps-show:hover, .ps-show:focus-visible { border-color: var(--sf-accent); outline: none; }
.ps-path { color: var(--sf-text-muted); }
.ps-edit { color: var(--sf-text-muted); align-self: center; }
</style>
