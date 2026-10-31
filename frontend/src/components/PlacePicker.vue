<!--
  航線規劃的地點選擇：地點欄直接打字自動完成（中英文、上層名稱都能搜），選定後自動帶出星系、行星；
  也可以先選星系／行星縮小候選（只選了行星時，點進地點欄就列出那顆星體上的全部地點）。
  v-model 是 { id, text }；places 是 GET /starmap/nav/places 的清單（每筆帶 system、group＝所屬星體）。
-->
<template>
  <div class="row g-1 place-picker">
    <div class="col-12 col-md-6">
      <AutocompleteField :id="id" v-model="text" :search="search" :get-label="optionName" :get-meta="optionMeta"
        :min-chars="0" :debounce-ms="0" :aria-label="`${label}地點`" placeholder="地點" @select="choose" />
    </div>
    <div class="col-6 col-md-3">
      <select :id="`${id}-system`" v-model="system" class="form-select form-select-sm"
        :aria-label="`${label}星系`" @change="onSystemChange">
        <option value="">星系</option>
        <option v-for="s in systems" :key="s.key" :value="s.key">{{ s.label }}</option>
      </select>
    </div>
    <div class="col-6 col-md-3">
      <select :id="`${id}-group`" v-model="group" class="form-select form-select-sm" :disabled="!system"
        :aria-label="`${label}行星`" @change="onGroupChange">
        <option value="">行星</option>
        <option v-for="g in groups" :key="g.key" :value="g.key">{{ g.label }}</option>
      </select>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import AutocompleteField from '@/components/AutocompleteField.vue'

const props = defineProps({
  modelValue: { type: Object, required: true },   // { id, text }
  places: { type: Array, default: () => [] },
  id: { type: String, required: true },
  label: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue'])

const SPACE = '__space__'
const TYPE_RANK = { Planet: 0, Moon: 0, LandingZone: 1, Manmade: 2, Outpost: 3 }
const MAX_RESULTS = 100

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
const text = ref(props.modelValue.text || '')

const groupLabel = (p) => {
  if (groupKey(p) === SPACE) return '太空'
  const body = byId.value.get(p.group)
  // 衛星接在所屬行星後面：顯示成「行星 › 衛星」
  const path = body ? (body.path_zh || []).slice(1) : []
  const label = nameOf(p.group_name, p.group_name_zh)
  return path.length ? `${path.join(' › ')} › ${label}` : label
}

const groups = computed(() => {
  if (!system.value) return []
  const seen = new Map()
  for (const p of props.places) {
    if (p.system !== system.value) continue
    const key = groupKey(p)
    if (seen.has(key)) continue
    const body = key === SPACE ? null : byId.value.get(key)
    seen.set(key, { key, label: groupLabel(p),
      sort: key === SPACE ? '￿' : [...(body?.path_zh || []), p.group_name].join('/').toLowerCase() })
  }
  return [...seen.values()].sort((a, b) => a.sort.localeCompare(b.sort))
})

// 同一組裡同名的地點（例如好幾個 QV Breaker Station）加上編號
const dupIndex = computed(() => {
  const total = {}, seen = {}, out = new Map()
  for (const p of props.places) total[`${groupKey(p)}|${p.name}`] = (total[`${groupKey(p)}|${p.name}`] || 0) + 1
  for (const p of props.places) {
    const k = `${groupKey(p)}|${p.name}`
    if (total[k] > 1) out.set(p.id, (seen[k] = (seen[k] || 0) + 1))
  }
  return out
})

function optionName(p) {
  const dup = dupIndex.value.get(p.id)
  return `${nameOf(p.name, p.name_zh)}${dup ? ` #${dup}` : ''}`
}

function optionMeta(p) {
  const type = p.type_zh || p.type
  return [p.system_zh || p.system, groupLabel(p), type, p.surface ? '地表' : '', p.services ? '可補給' : '', p.xl_hangar ? '特大機庫' : '', p.loading_dock ? '外部貨運' : '',
    p.docking ? '對接口' : '']
    .filter(Boolean).join(' · ')
}

const norm = s => (s || '').toLowerCase()
// 星體分組的排序鍵（太空排最後）
function groupSort(p) {
  if (groupKey(p) === SPACE) return '\uffff'
  const body = byId.value.get(p.group)
  return [...(body?.path_zh || []), p.group_name].join('/').toLowerCase()
}

async function search(q) {
  const t = norm(q).trim()
  const head = [], rest = []
  for (const p of props.places) {
    if (system.value && p.system !== system.value) continue
    if (group.value && groupKey(p) !== group.value) continue
    if (!t) { rest.push(p); continue }
    const name = norm(p.name), zh = norm(p.name_zh)
    if (name.startsWith(t) || zh.startsWith(t)) head.push(p)
    else if (name.includes(t) || zh.includes(t) || norm(p.group_name).includes(t) || norm(p.group_name_zh).includes(t)
      || norm((p.path_zh || []).join(' ')).includes(t)) rest.push(p)
  }
  const sortRows = rows => rows.sort((a, b) => (a.id === group.value ? -1 : b.id === group.value ? 1 : 0)
    || (TYPE_RANK[a.type] ?? 9) - (TYPE_RANK[b.type] ?? 9)
    || (a.name_zh || a.name).localeCompare(b.name_zh || b.name))
  // 還沒打字：列出範圍內全部地點，照星系 › 星體（行星後面接它的衛星）› 類型排
  if (!t) {
    return rest.sort((a, b) => (a.system || '').localeCompare(b.system || '')
      || groupSort(a).localeCompare(groupSort(b))
      || (a.id === a.group ? -1 : b.id === b.group ? 1 : 0)
      || (TYPE_RANK[a.type] ?? 9) - (TYPE_RANK[b.type] ?? 9)
      || (a.name_zh || a.name).localeCompare(b.name_zh || b.name))
  }
  return [...sortRows(head), ...sortRows(rest)].slice(0, MAX_RESULTS)
}

function choose(p) {
  // 打字（還沒選定）時 AutocompleteField 會先送 null：清掉 id，文字保留
  emit('update:modelValue', { ...props.modelValue, id: p?.id || '', text: p ? optionName(p) : text.value })
}

function onSystemChange() {
  group.value = ''
  const cur = byId.value.get(props.modelValue.id)
  if (cur && cur.system !== system.value) clearPlace()
}

function onGroupChange() {
  const cur = byId.value.get(props.modelValue.id)
  if (cur && group.value && groupKey(cur) !== group.value) clearPlace()
}

// 改星系／行星造成地點被清掉時，不要連帶把剛選的星系／行星也清掉
let keepScope = false
function clearPlace() {
  keepScope = text.value !== ''   // 文字本來就是空的就不會觸發下面的 watch
  text.value = ''
  emit('update:modelValue', { ...props.modelValue, id: '', text: '' })
}

// 地點欄清空（按 × 或刪光文字、或整張表單清除）→ 星系、行星也一起清掉
watch(text, v => {
  if (v) return
  if (keepScope) {
    keepScope = false
    return
  }
  system.value = ''
  group.value = ''
})

// 選定的地點（或瀏覽器記住的）→ 帶出星系、行星與欄位文字
watch([() => props.modelValue.id, byId], () => {
  const p = byId.value.get(props.modelValue.id)
  if (p) {
    system.value = p.system || ''
    group.value = groupKey(p)
    text.value = optionName(p)
  }
}, { immediate: true })
watch(() => props.modelValue.text, v => { if (!props.modelValue.id && v !== text.value) text.value = v || '' })
</script>
