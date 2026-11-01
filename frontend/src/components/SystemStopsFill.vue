<!--
  航線「途經站點」的依星系填入（components/RoutePlanner.vue）：選星系、勾要哪幾類站點，按「填入」把符合的站點
  交給上層（@fill，參數是地點清單）。站點只算有服務（可補給）的地點：
    太空站＝不在地表的、主城＝LandingZone、地面站＝在地表的其他地點（前哨站等）。
  地面站一個星系動輒上百個，一定要先選行星（或衛星）才能填；選了行星時三類都只填那顆星體底下的。
-->
<template>
  <div class="ssf">
    <div class="row g-2 align-items-end">
      <div class="col-12 col-md-4">
        <label class="form-label small fw-semibold mb-1" :for="`${id}-system`">星系</label>
        <select :id="`${id}-system`" v-model="system" class="form-select form-select-sm">
          <option value="">選擇星系</option>
          <option v-for="s in systems" :key="s.key" :value="s.key">{{ s.label }}</option>
        </select>
      </div>
      <div class="col-12 col-md-4">
        <label class="form-label small fw-semibold mb-1" :for="`${id}-group`">行星</label>
        <select :id="`${id}-group`" v-model="group" class="form-select form-select-sm" :disabled="!system"
          :class="{ 'is-invalid': needGroup }">
          <option value="">全部行星</option>
          <option v-for="g in groups" :key="g.key" :value="g.key">{{ g.label }}</option>
        </select>
      </div>
      <div class="col-12 col-md-4 d-flex flex-wrap align-items-center gap-3">
        <div v-for="k in KINDS" :key="k.key" class="form-check mb-0">
          <input :id="`${id}-kind-${k.key}`" v-model="kinds" class="form-check-input" type="checkbox" :value="k.key">
          <label class="form-check-label" :for="`${id}-kind-${k.key}`">{{ k.label }}</label>
        </div>
      </div>
    </div>
    <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
      <span v-if="needGroup" class="sf-chip sf-chip--warn">地面站需選擇行星</span>
      <span v-else-if="system && kinds.length" class="sf-chip">符合 {{ matches.length }} 個</span>
      <button type="button" class="btn btn-sm btn-success ms-auto" :disabled="!canFill" @click="fill">
        <i class="bi bi-plus-lg me-1"></i>填入站點</button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  id: { type: String, required: true },
  places: { type: Array, default: () => [] },
})
const emit = defineEmits(['fill'])

const KINDS = [
  { key: 'station', label: '太空站' },
  { key: 'city', label: '主城' },
  { key: 'ground', label: '地面站' },
]
const nameOf = (en, zh) => (zh && zh !== en ? `${zh}（${en}）` : (en || ''))
const byId = computed(() => new Map(props.places.map(p => [p.id, p])))

/** 站點類別：station／city／ground；不是站點（星體、沒有服務的地點）回 '' */
function kindOf(p) {
  if (!p.services || p.synthetic) return ''
  if (p.type === 'LandingZone') return 'city'
  return p.surface ? 'ground' : 'station'
}

const systems = computed(() => {
  const seen = new Map()
  for (const p of props.places) {
    if (p.system && kindOf(p) && !seen.has(p.system)) seen.set(p.system, { key: p.system, label: nameOf(p.system, p.system_zh) })
  }
  return [...seen.values()].sort((a, b) => a.key.localeCompare(b.key))
})

const system = ref('')
const group = ref('')
const kinds = ref(['station', 'city'])
watch(system, () => { group.value = '' })

// 行星／衛星：這個星系裡有站點的星體，衛星接在行星後面
const groups = computed(() => {
  if (!system.value) return []
  const seen = new Map()
  for (const p of props.places) {
    if (p.system !== system.value || !p.group || !kindOf(p) || seen.has(p.group)) continue
    const body = byId.value.get(p.group)
    const path = body ? (body.path_zh || []).slice(1) : []
    const label = nameOf(p.group_name, p.group_name_zh)
    seen.set(p.group, { key: p.group, label: path.length ? `${path.join(' › ')} › ${label}` : label,
      sort: [...(body?.path_zh || []), p.group_name].join('/').toLowerCase() })
  }
  return [...seen.values()].sort((a, b) => a.sort.localeCompare(b.sort))
})

const needGroup = computed(() => !!system.value && kinds.value.includes('ground') && !group.value)
const matches = computed(() => {
  if (!system.value || needGroup.value) return []
  return props.places.filter(p => p.system === system.value && kinds.value.includes(kindOf(p))
    && (!group.value || p.group === group.value))
})
const canFill = computed(() => !!system.value && kinds.value.length > 0 && !needGroup.value && matches.value.length > 0)

function fill() {
  if (canFill.value) emit('fill', matches.value)
}
</script>

<style scoped>
.ssf { border: 1px solid var(--sf-border); border-radius: .5rem; padding: .5rem; margin-bottom: .5rem; }
</style>
