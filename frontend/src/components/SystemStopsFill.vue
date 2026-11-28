<!--
  航線「途經站點」的依星系填入（components/RoutePlanner.vue）：選星系、勾要哪幾類站點，按「填入」把符合的站點
  交給上層（@fill，參數是地點清單）。站點只算有服務（可補給）的地點，分這幾類（kindOf）：
    主城＝LandingZone；地面站＝在地表的其他地點（前哨站等）；
    不在地表的太空站再分：星門（名稱有 Gateway，或本身連著跳躍點）、行星軌道站（繞著某顆行星／衛星）、
    拉格朗日站（名稱像 ARC-L1，不屬於任何星體）、其他太空站（其餘不屬於任何星體的，例如派羅的深空站）。
  另外兩個條件：只要有貨物裝卸區（可放外掛貨櫃）、只要有 XL 機庫。
  地面站一個星系動輒上百個，一定要先選行星（或衛星）才能填；選了行星時三類都只填那顆星體底下的。
-->
<template>
  <div class="ssf">
    <div class="row g-2 align-items-end">
      <div class="col-12 col-md-6">
        <span class="form-label small fw-semibold mb-1 d-block">星系</span>
        <!-- 星系只有幾個：膠囊單選（再點一次取消） -->
        <SfChoice :id="`${id}-system`" v-model="system" label="星系" :options="systems.map(x => ({ value: x.key, label: x.label }))" />
      </div>
      <div class="col-12 col-md-6">
        <label class="form-label small fw-semibold mb-1" :for="`${id}-group`">行星</label>
        <select :id="`${id}-group`" v-model="group" class="form-select form-select-sm" :disabled="!system"
          :class="{ 'is-invalid': needGroup }">
          <option value="">全部行星</option>
          <option v-for="g in groups" :key="g.key" :value="g.key">{{ g.label }}</option>
        </select>
      </div>
    </div>
    <!-- 站點類別：按鈕上是目前星系／行星底下有幾個 -->
    <div class="sf-pills mt-2" role="group" aria-label="站點類別">
      <SfToggle v-for="k in KINDS" :key="k.key" :model-value="kinds.includes(k.key)"
        @update:model-value="on => { kinds = on ? [...kinds, k.key] : kinds.filter(x => x !== k.key) }">{{ k.label }}<span v-if="system" class="ssf-count">{{ kindCounts[k.key] || 0 }}</span></SfToggle>
    </div>
    <div class="sf-pills mt-2" role="group" aria-label="其他條件">
      <SfToggle v-model="needDock">只要有貨物裝卸區</SfToggle>
      <SfToggle v-model="needXl">只要有 XL 機庫</SfToggle>
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
import SfChoice from '@/components/SfChoice.vue'
import SfToggle from '@/components/SfToggle.vue'
import { computed, ref, watch } from 'vue'

const props = defineProps({
  id: { type: String, required: true },
  places: { type: Array, default: () => [] },
})
const emit = defineEmits(['fill'])

const KINDS = [
  { key: 'gateway', label: '星門' },
  { key: 'orbital', label: '行星軌道站' },
  { key: 'lpoint', label: '拉格朗日站' },
  { key: 'deep', label: '其他太空站' },
  { key: 'city', label: '主城' },
  { key: 'ground', label: '地面站' },
]
/** 太空站的四類 */
const SPACE_KINDS = ['gateway', 'orbital', 'lpoint', 'deep']
const nameOf = (en, zh) => (zh && zh !== en ? `${zh}（${en}）` : (en || ''))
const byId = computed(() => new Map(props.places.map(p => [p.id, p])))

/** 站點類別（見檔頭）；不是站點（星體、沒有服務的地點）回 '' */
function kindOf(p) {
  if (!p.services || p.synthetic) return ''
  if (p.type === 'LandingZone') return 'city'
  if (p.surface) return 'ground'
  if (p.jump || /gateway/i.test(p.name || '')) return 'gateway'
  if (p.group) return 'orbital'
  if (/-L\d\b/i.test(p.name || '')) return 'lpoint'
  return 'deep'
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
const kinds = ref([...SPACE_KINDS, 'city'])
const needDock = ref(false)
const needXl = ref(false)
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
/** 星系、行星、裝卸區、XL 機庫都符合的站點（還沒看類別） */
const candidates = computed(() => (!system.value ? [] : props.places.filter(p => p.system === system.value && kindOf(p)
  && (!group.value || p.group === group.value) && (!needDock.value || p.loading_dock) && (!needXl.value || p.xl_hangar))))
const kindCounts = computed(() => {
  const out = {}
  for (const p of candidates.value) { const k = kindOf(p); out[k] = (out[k] || 0) + 1 }
  return out
})
const matches = computed(() => (needGroup.value ? [] : candidates.value.filter(p => kinds.value.includes(kindOf(p)))))
const canFill = computed(() => !!system.value && kinds.value.length > 0 && !needGroup.value && matches.value.length > 0)

function fill() {
  if (canFill.value) emit('fill', matches.value)
}
</script>

<style scoped>
.ssf-count { opacity: .7; font-size: .85em; }
.ssf { border: 1px solid var(--sf-border); border-radius: .5rem; padding: .5rem; margin-bottom: .5rem; }
</style>
