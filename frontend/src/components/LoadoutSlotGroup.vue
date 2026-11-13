<!--
  配裝模擬的一組槽位（components/LoadoutSimulator.vue）：同一層一模一樣的幾格合成一列顯示「N×」，
  換配件時整組一起換；子槽（砲塔上的武器、飛彈架上的飛彈）縮排列在下面，遞迴用自己。
  需要的函式由 LoadoutSimulator provide（'loadout'：itemOf、open、primary、secondary、itemLabel）。
-->
<template>
  <div class="lo-group" :class="{ 'lo-group--child': depth > 0 }">
    <div class="lo-row" :class="{ 'lo-row--empty': !first.item }">
      <span class="lo-size" :title="`尺寸 ${sizeText}`">S{{ sizeText }}</span>
      <span v-if="nodes.length > 1" class="lo-count">{{ nodes.length }}×</span>
      <div class="flex-grow-1 min-w-0">
        <div class="lo-name text-truncate" :title="title">{{ name }}</div>
        <div class="lo-meta text-truncate">{{ meta }}</div>
      </div>
      <div v-if="item && lo.primary(item)" class="lo-stat text-end">
        <div class="lo-stat__value">{{ lo.primary(item).text }}</div>
        <div class="lo-stat__label">{{ lo.primary(item).label }}</div>
      </div>
      <button v-if="first.editable" type="button" class="btn btn-sm btn-primary text-nowrap"
        :aria-label="`更換 ${name}`" @click="lo.open(nodes)"><i class="bi bi-arrow-left-right me-1"></i>更換</button>
      <span v-else class="lo-lock" title="這一格不能更換" aria-label="不能更換"><i class="bi bi-lock-fill"></i></span>
    </div>
    <div v-if="subStats.length" class="lo-sub">
      <span v-for="s in subStats" :key="s.label" class="lo-kv"><span>{{ s.label }}</span>{{ s.text }}</span>
    </div>
    <LoadoutSlotGroup v-for="(g, i) in groups" :key="`${g[0].id}-${i}`" :nodes="g" :depth="depth + 1" />
  </div>
</template>

<script setup>
import { computed, inject } from 'vue'
import { childGroups } from '@/utils/loadoutCalc'

const props = defineProps({
  nodes: { type: Array, required: true },
  depth: { type: Number, default: 0 },
})
const lo = inject('loadout')
const first = computed(() => props.nodes[0])
const item = computed(() => lo.itemOf(first.value.item))
const groups = computed(() => childGroups(props.nodes, lo.itemOf))
const sizeText = computed(() => {
  const n = first.value
  if (item.value?.size != null) return item.value.size
  return n.min === n.max || !n.max ? n.min : `${n.min}–${n.max}`
})
const name = computed(() => (item.value ? lo.itemLabel(item.value)
  : first.value.item ? first.value.name || lo.typeLabel(first.value.types) : '（空）'))
const title = computed(() => (item.value ? `${item.value.name}（${item.value.class_name}）`
  : [name.value, first.value.item_class_name].filter(Boolean).join('（') + (first.value.item_class_name ? '）' : '')))
// 列表只放前幾個數值（訊號、耗電這些在更換視窗看）
const subStats = computed(() => (item.value ? lo.secondary(item.value).filter(s => !['EM', 'IR 訊號', '耗電'].includes(s.label)).slice(0, 6) : []))
const meta = computed(() => {
  const it = item.value
  if (!it) return lo.typeLabel(first.value.types)
  return [lo.typeLabel([`${it.type}.${it.sub_type}`]), it.name_zh && it.name_zh !== it.name ? it.name : '',
    it.manufacturer, [it.grade, lo.classLabel(it.item_class)].filter(Boolean).join(' ')].filter(Boolean).join(' · ')
})
</script>

<style scoped>
.lo-group--child { margin-left: .9rem; padding-left: .7rem; border-left: 2px solid var(--sf-border); }
.lo-row { display: flex; align-items: center; gap: .5rem; padding: .45rem .55rem; margin-top: .4rem;
  border: 1px solid var(--sf-border); border-radius: .4rem; background: var(--sf-chip-bg); }
.lo-row--empty { opacity: .7; border-style: dashed; }
.lo-size { flex: none; min-width: 2.4rem; text-align: center; font-weight: 700; padding: .1rem .35rem; border-radius: .3rem;
  color: var(--sf-text-strong); background: rgba(var(--sf-accent-rgb), .25); border: 1px solid rgba(var(--sf-accent-rgb), .7); }
.lo-count { flex: none; font-weight: 700; color: var(--sf-accent-2); }
.lo-name { font-weight: 600; color: var(--sf-text-strong); }
.lo-meta { font-size: .85rem; color: var(--sf-text-muted); }
.lo-stat { flex: none; line-height: 1.1; }
.lo-stat__value { font-weight: 700; font-size: 1.1rem; color: var(--sf-accent); }
.lo-stat__label { font-size: .75rem; color: var(--sf-text-muted); }
.lo-lock { flex: none; width: 2rem; text-align: center; color: var(--sf-text-muted); }
.lo-sub { display: flex; flex-wrap: wrap; gap: .2rem .9rem; padding: .2rem .6rem 0 3.2rem; font-size: .85rem; color: var(--sf-text); }
.lo-kv span { color: var(--sf-text-muted); margin-right: .3rem; }
.min-w-0 { min-width: 0; }
@media (max-width: 575.98px) {
  .lo-stat__value { font-size: 1rem; }
  .lo-sub { padding-left: .6rem; }
}
</style>
