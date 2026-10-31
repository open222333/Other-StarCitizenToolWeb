<!--
  航線規劃的「船＋量子引擎」選擇（RoutePlanner.vue、ContractPlanner.vue 每個小隊共用）。
  船是自動完成（自己機庫的船排前面），量子引擎只列跟船的引擎槽同尺寸的，下面列出實際數值。
  v-model:ship-id／v-model:ship-text／v-model:qd-id；選了船另外發 pick(船)。
-->
<template>
  <div class="row g-2 align-items-end">
    <div class="col-12 col-md-6">
      <label class="form-label small fw-semibold mb-1" :for="`${id}-ship`">{{ label }}</label>
      <AutocompleteField :id="`${id}-ship`" :model-value="shipText" :search="searchShips" :get-label="shipLabel"
        :get-meta="shipMeta" :min-chars="0" :debounce-ms="0" :aria-label="label"
        @update:model-value="v => emit('update:shipText', v)" @select="pickShip" />
    </div>
    <div class="col-12 col-md-6">
      <label class="form-label small fw-semibold mb-1" :for="`${id}-qd`">量子引擎</label>
      <select :id="`${id}-qd`" :value="qdId" class="form-select form-select-sm" :disabled="!ship || !qdOptions.length"
        @change="emit('update:qdId', $event.target.value)">
        <option v-if="!qdOptions.length" value="">預設</option>
        <option v-for="q in qdOptions" :key="q.id" :value="q.id">{{ qdLabel(q) }}</option>
      </select>
    </div>
    <div v-if="ship" class="col-12">
      <div class="d-flex flex-wrap gap-1 sp-facts">
        <span v-if="showCargo" class="sf-chip" :class="{ 'sf-chip--warn': !ship.cargo_scu }">
          貨艙 {{ fmtNum(ship.cargo_scu || 0) }} SCU</span>
        <span class="sf-chip">量子速度 {{ fmtSpeed(effective.speed) }}</span>
        <span class="sf-chip">啟動 {{ fmtNum(effective.spool, 1) }} 秒</span>
        <span v-if="effective.fuelPerGm" class="sf-chip">每 Gm 耗油 {{ fmtNum(effective.fuelPerGm, 2) }}</span>
        <span v-if="ship.qt_fuel_capacity" class="sf-chip">量子油箱 {{ fmtNum(ship.qt_fuel_capacity) }}</span>
        <span v-if="effective.rangeGm" class="sf-chip">滿油約 {{ fmtNum(effective.rangeGm, 1) }} Gm</span>
        <span v-if="showCargo && ship.external_cargo" class="sf-chip">外掛貨櫃（只停外部貨運站）</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, watch } from 'vue'
import AutocompleteField from '@/components/AutocompleteField.vue'
import { fmtNum, fmtSpeed, shipLabel } from '@/utils/navFormat'

const props = defineProps({
  id: { type: String, required: true },
  label: { type: String, default: '船' },
  ships: { type: Array, default: () => [] },
  quantumDrives: { type: Array, default: () => [] },
  // 玩家機庫的船（vehicle UUID），排在船清單最前面
  fleetUuids: { type: Array, default: () => [] },
  shipId: { type: String, default: '' },
  shipText: { type: String, default: '' },
  qdId: { type: String, default: '' },
  showCargo: { type: Boolean, default: false },
  // 還沒選船時，自動選機庫裡的第一艘
  autoPick: { type: Boolean, default: false },
})
const emit = defineEmits(['update:shipId', 'update:shipText', 'update:qdId', 'pick'])

const fleetSet = computed(() => new Set(props.fleetUuids))
const ship = computed(() => props.ships.find(s => s.id === props.shipId) || null)

function pickShip(s) {
  const changed = (s?.id || '') !== props.shipId
  emit('update:shipId', s?.id || '')
  if (changed || !props.qdId) emit('update:qdId', s?.qd_uuid || '')   // 換船就換回它的預設量子引擎
  if (s) emit('update:shipText', shipLabel(s))
  emit('pick', s || null)
}

watch([() => props.ships, fleetSet], () => {
  if (!props.autoPick || ship.value || !props.ships.length) return
  const mine = props.ships.find(s => fleetSet.value.has(s.id))
  if (mine) pickShip(mine)
}, { immediate: true })

const qdOptions = computed(() => {
  const size = ship.value?.qd_size
  if (!size) return []
  return props.quantumDrives.filter(q => q.size === size)
    .sort((a, b) => (a.id === ship.value.qd_uuid ? -1 : b.id === ship.value.qd_uuid ? 1 : 0)
      || (a.name || '').localeCompare(b.name || ''))
})
const qd = computed(() => qdOptions.value.find(q => q.id === props.qdId) || null)
// 畫面上顯示的實際數值（換了引擎就用引擎的；油箱一律是船的）
const effective = computed(() => {
  const s = ship.value || {}
  const fuelPerGm = qd.value?.fuel_per_gm || (s.qt_fuel_per_m ? s.qt_fuel_per_m * 1e9 : null)
  return {
    speed: qd.value?.speed || s.qt_speed,
    spool: qd.value?.spool ?? s.qt_spool,
    fuelPerGm,
    rangeGm: fuelPerGm && s.qt_fuel_capacity ? s.qt_fuel_capacity / fuelPerGm : null,
  }
})

function qdLabel(q) {
  const grade = q.grade ? `${q.grade} 級` : ''
  const cls = q.item_class_zh || q.item_class || ''
  const parts = [`S${q.size}`, [cls, grade].filter(Boolean).join(' '), q.manufacturer || '',
    `${fmtSpeed(q.speed)}`, `每 Gm ${fmtNum(q.fuel_per_gm, 2)}`].filter(Boolean)
  return `${q.name}${q.id === ship.value?.qd_uuid ? '（預設）' : ''} · ${parts.join(' · ')}`
}

const shipMeta = s => (fleetSet.value.has(s.id) ? '我的機庫' : (s.cargo_scu ? `${fmtNum(s.cargo_scu)} SCU` : ''))
const norm = text => (text || '').toLowerCase()

async function searchShips(q) {
  const t = norm(q)
  const rows = props.ships.filter(s => !t || norm(s.name).includes(t) || norm(s.name_zh).includes(t))
  rows.sort((a, b) => (fleetSet.value.has(b.id) - fleetSet.value.has(a.id)))
  return rows.slice(0, 40)
}
</script>

<style scoped>
.sp-facts { min-height: 1.75rem; }
</style>
