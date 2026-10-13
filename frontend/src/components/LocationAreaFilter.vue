<!--
  「星系／行星／地點」三段多選篩選（全站地點搜尋共用）。

  names 是候選地點名稱（英文）；星系／行星由 utils/locationArea.js 查地點資料庫，
  或由呼叫端用 areaFor 自己給（例如 UEX 終端）。行星的選項跟著已選的星系縮小、
  地點跟著星系＋行星縮小；改了上一段時，下一段已選、但不在新選項裡的會自動拿掉。

  block（預設）：表單欄位樣式，三欄各有標題，欄寬用 colClass；
  inline：篩選列樣式（後台），三個按鈕排在一起。
-->
<template>
  <template v-if="inline">
    <MultiSelectFilter v-for="f in fields" :key="f.key" :model-value="f.value" :options="f.options"
      :label="f.label" :searchable="f.searchable" @update:model-value="f.update" />
  </template>
  <template v-else>
    <div v-for="f in fields" :key="f.key" :class="colClass">
      <label class="form-label small fw-semibold mb-1" :for="`${uid}-${f.key}`">{{ f.label }}</label>
      <MultiSelectFilter :id="`${uid}-${f.key}`" :model-value="f.value" :options="f.options"
        :label="f.label" placeholder="全部" block :searchable="f.searchable" @update:model-value="f.update" />
    </div>
  </template>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import { areaOf, areaOptions, loadLocationAreas, placeLabel } from '@/utils/locationArea'

const props = defineProps({
  names:     { type: Array, default: () => [] },
  systems:   { type: Array, default: () => [] },
  planets:   { type: Array, default: () => [] },
  locations: { type: Array, default: () => [] },
  /** 地點的顯示文字 */
  locLabel:  { type: Function, default: placeLabel },
  /** 自訂某地點的 { system, planet }（預設查地點資料庫） */
  areaFor:   { type: Function, default: null },
  /** 第三段的標題 */
  locationTitle: { type: String, default: '地點' },
  inline:    { type: Boolean, default: false },
  colClass:  { type: String, default: 'col-12 col-md-4' },
})
const emit = defineEmits(['update:systems', 'update:planets', 'update:locations'])

const uid = `laf-${Math.random().toString(36).slice(2, 8)}`
const areaFor = computed(() => props.areaFor || areaOf)

const opts = computed(() => areaOptions(props.names,
  { systems: props.systems, planets: props.planets },
  { locLabel: props.locLabel, areaFor: areaFor.value }))

function setSystems(v) {
  emit('update:systems', v)
  const next = areaOptions(props.names, { systems: v }, { areaFor: areaFor.value })
  const planets = props.planets.filter(p => next.planets.some(o => o.value === p))
  if (planets.length !== props.planets.length) emit('update:planets', planets)
  pruneLocations(v, planets)
}
function setPlanets(v) {
  emit('update:planets', v)
  pruneLocations(props.systems, v)
}
function pruneLocations(systems, planets) {
  const next = areaOptions(props.names, { systems, planets }, { areaFor: areaFor.value })
  const locations = props.locations.filter(l => next.locations.some(o => o.value === l))
  if (locations.length !== props.locations.length) emit('update:locations', locations)
}

const fields = computed(() => [
  { key: 'system', label: '星系', value: props.systems, options: opts.value.systems, update: setSystems },
  { key: 'planet', label: '行星', value: props.planets, options: opts.value.planets, update: setPlanets, searchable: true },
  { key: 'location', label: props.locationTitle, value: props.locations, options: opts.value.locations,
    update: v => emit('update:locations', v), searchable: true },
])

onMounted(() => { if (!props.areaFor) loadLocationAreas() })
</script>
