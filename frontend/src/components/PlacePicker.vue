<!--
  航線規劃的地點選擇：星系 → 行星（或衛星、太空）→ 地點，三個下拉選單。
  v-model 是 { id, text }；places 是 GET /starmap/nav/places 的清單（每筆帶 system、group＝所屬星體）。
-->
<template>
  <div class="row g-1 place-picker">
    <div class="col-6 col-md-3">
      <select :id="`${id}-system`" v-model="system" class="form-select form-select-sm"
        :aria-label="`${label}星系`" @change="group = ''; choose('')">
        <option value="">星系</option>
        <option v-for="s in systems" :key="s.key" :value="s.key">{{ s.label }}</option>
      </select>
    </div>
    <div class="col-6 col-md-4">
      <select :id="`${id}-group`" v-model="group" class="form-select form-select-sm" :disabled="!system"
        :aria-label="`${label}行星`" @change="choose('')">
        <option value="">行星</option>
        <option v-for="g in groups" :key="g.key" :value="g.key">{{ g.label }}</option>
      </select>
    </div>
    <div class="col-12 col-md-5">
      <select :id="id" :value="modelValue.id" class="form-select form-select-sm" :disabled="!group"
        :aria-label="`${label}地點`" @change="choose($event.target.value)">
        <option value="">地點</option>
        <option v-for="p in options" :key="p.id" :value="p.id">{{ optionLabel(p) }}</option>
      </select>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: Object, required: true },   // { id, text }
  places: { type: Array, default: () => [] },
  id: { type: String, required: true },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const SPACE = '__space__'
const TYPE_RANK = { Planet: 0, Moon: 0, LandingZone: 1, Manmade: 2, Outpost: 3 }

const nameOf = (en, zh) => (zh && zh !== en ? `${zh}（${en}）` : (en || ''))
const groupKey = p => p.group || SPACE

const byId = computed(() => new Map(props.places.map(p => [p.id, p])))

const systems = computed(() => {
  const seen = new Map()
  for (const p of props.places) {
    const key = p.system || ''
    if (key && !seen.has(key)) seen.set(key, { key, label: nameOf(p.system, p.system_zh) })
  }
  return [...seen.values()].sort((a, b) => a.key.localeCompare(b.key))
})

const system = ref('')
const group = ref('')

const groups = computed(() => {
  if (!system.value) return []
  const seen = new Map()
  for (const p of props.places) {
    if (p.system !== system.value) continue
    const key = groupKey(p)
    if (seen.has(key)) continue
    if (key === SPACE) {
      seen.set(key, { key, label: '太空', sort: '￿' })
      continue
    }
    const body = byId.value.get(key)
    // 衛星接在所屬行星後面：用星體自己的上層路徑排序，顯示成「行星 › 衛星」
    const path = body ? (body.path_zh || []).slice(1) : []
    const label = nameOf(p.group_name, p.group_name_zh)
    seen.set(key, { key, label: path.length ? `${path.join(' › ')} › ${label}` : label,
      sort: [...(body?.path_zh || []), p.group_name].join('/').toLowerCase() })
  }
  return [...seen.values()].sort((a, b) => a.sort.localeCompare(b.sort))
})

const options = computed(() => {
  if (!group.value) return []
  const rows = props.places
    .filter(p => p.system === system.value && groupKey(p) === group.value)
    .sort((a, b) => (a.id === group.value ? -1 : b.id === group.value ? 1 : 0)
      || (TYPE_RANK[a.type] ?? 9) - (TYPE_RANK[b.type] ?? 9)
      || (a.name_zh || a.name).localeCompare(b.name_zh || b.name))
  // 同一組裡同名的地點（例如好幾個 QV Breaker Station）加上編號
  const total = {}, seen = {}
  rows.forEach(p => { total[p.name] = (total[p.name] || 0) + 1 })
  return rows.map(p => (total[p.name] > 1 ? { ...p, dup: (seen[p.name] = (seen[p.name] || 0) + 1) } : p))
})

function optionLabel(p) {
  const type = p.type_zh || p.type
  return `${nameOf(p.name, p.name_zh)}${p.dup ? ` #${p.dup}` : ''}${type ? ` · ${type}` : ''}${p.surface ? ' · 地表' : ''}`
}

function choose(placeId) {
  const p = placeId ? byId.value.get(placeId) : null
  emit('update:modelValue', { ...props.modelValue, id: p?.id || '', text: p ? nameOf(p.name, p.name_zh) : '' })
}

// 已選的地點（例如瀏覽器記住的）→ 帶出星系、行星
watch([() => props.modelValue.id, byId], () => {
  const p = byId.value.get(props.modelValue.id)
  if (p) {
    system.value = p.system || ''
    group.value = groupKey(p)
  }
}, { immediate: true })
</script>
