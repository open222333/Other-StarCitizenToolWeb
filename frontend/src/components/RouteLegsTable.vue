<!--
  航線的航段表（RoutePlanner.vue、ContractPlanner.vue 共用）：出發點＋每一站的目的地、動作、經過的 OM／跳躍點、
  距離、時間、油量、剩油與補充燃料提示。plan 是後端 nav._build_plan 的結果。

  同一站連續的動作（後面幾段距離是 0）併成一列，動作逐項列出（同一份合約、同一種貨物、同一個動作的 SCU 加總）。
  補充燃料標在「出發前」那一站：plan.refuel_stops 的 k 是第 k 段的出發點；單段就超過油箱（fuel_short）也標在出發站。
  同名貨物分屬不同合約（同一站一起處理，或貨艙裡同時有）時提醒：取貨時分開放置、送貨時分開繳交。
-->
<template>
  <div style="overflow-x:auto">
    <table class="table table-hover align-middle mb-0 sf-stack rlt">
      <thead class="table-light">
        <tr>
          <th class="ps-3">目的地</th>
          <th>動作</th>
          <th v-if="showLoad" class="text-end">載貨</th>
          <th class="text-end">距離</th>
          <th class="text-end">時間</th>
          <th class="text-end">油量</th>
          <th class="text-end pe-3">剩油</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td class="ps-3 sf-stack__title">
            <div class="fw-semibold"><span class="rlt-no">0</span>{{ placeLabel(plan.start) }}</div>
            <div class="rlt-path ps-4">{{ placePath(plan.start) }}</div>
            <div v-if="traitsOf(plan.start).length" class="d-flex flex-wrap gap-1 mt-1 ps-4">
              <span v-for="t in traitsOf(plan.start)" :key="t" class="sf-chip">{{ t }}</span>
            </div>
          </td>
          <td data-label="動作">
            <div v-if="!table.start" class="rlt-action"><span class="sf-chip text-nowrap">出發</span></div>
            <div v-for="(a, j) in table.start?.actions || []" :key="j" class="rlt-action">
              <span class="sf-chip text-nowrap" :class="actionClass(a.action)">{{ actionLabel(a) }}</span>
              <span v-if="a.contract_name" class="rlt-cargo">{{ a.contract_name }} · {{ a.item_name }}</span>
            </div>
            <div v-if="startFuel.mixed.length || startFuel.refuel || startFuel.short" class="d-flex flex-wrap gap-1 mt-1">
              <span v-for="m in startFuel.mixed" :key="m.name" class="sf-chip sf-chip--warn">
                {{ mixedLabel(m) }}</span>
              <span v-if="startFuel.refuel" class="sf-chip sf-chip--warn text-nowrap">需補充燃料</span>
              <span v-if="startFuel.short" class="sf-chip sf-chip--warn text-nowrap">下一段超過油箱</span>
            </div>
          </td>
          <td v-if="showLoad" class="text-end" data-label="載貨">{{ fmtNum(table.start?.load_after || 0) }}</td>
          <td class="text-end" data-label="距離">—</td>
          <td class="text-end" data-label="時間">—</td>
          <td class="text-end" data-label="油量">—</td>
          <td class="text-end pe-3" data-label="剩油">{{ fuelCapacity ? '滿油' : '—' }}</td>
        </tr>
        <tr v-for="(row, i) in table.rows" :key="i">
          <td class="ps-3 sf-stack__title">
            <div class="fw-semibold"><span class="rlt-no">{{ i + 1 }}</span>{{ placeLabel(row.to) }}</div>
            <div class="rlt-path ps-4">{{ placePath(row.to) }}</div>
            <div v-if="traitsOf(row.to).length" class="d-flex flex-wrap gap-1 mt-1 ps-4">
              <span v-for="t in traitsOf(row.to)" :key="t" class="sf-chip">{{ t }}</span>
            </div>
            <div v-if="row.via.length" class="d-flex flex-wrap gap-1 mt-1 ps-4">
              <span v-for="(v, j) in row.via" :key="j" class="sf-chip"
                :class="{ 'sf-chip--accent': v.kind === 'jump' }">
                {{ v.kind === 'jump' ? '跳躍' : '經' }} {{ placeLabel(v.place) }}
              </span>
            </div>
          </td>
          <td data-label="動作">
            <div v-for="(a, j) in row.actions" :key="j" class="rlt-action">
              <span class="sf-chip text-nowrap" :class="actionClass(a.action)">{{ actionLabel(a) }}</span>
              <span v-if="a.contract_name" class="rlt-cargo">{{ a.contract_name }} · {{ a.item_name }}</span>
            </div>
            <div v-if="row.mixed.length || row.refuel || row.short" class="d-flex flex-wrap gap-1 mt-1">
              <span v-for="m in row.mixed" :key="m.name" class="sf-chip sf-chip--warn">
                {{ mixedLabel(m) }}</span>
              <span v-if="row.refuel" class="sf-chip sf-chip--warn text-nowrap">需補充燃料</span>
              <span v-if="row.short" class="sf-chip sf-chip--warn text-nowrap">下一段超過油箱</span>
            </div>
          </td>
          <td v-if="showLoad" class="text-end text-nowrap" data-label="載貨">{{ fmtNum(row.load_after) }}</td>
          <td class="text-end text-nowrap" data-label="距離">{{ row.moved ? fmtDist(row.distance) : '—' }}</td>
          <td class="text-end text-nowrap" data-label="時間">{{ row.moved ? fmtTime(row.time) : '—' }}</td>
          <td class="text-end text-nowrap" data-label="油量">
            {{ row.fuel != null && row.moved ? fmtNum(row.fuel, row.fuel < 10 ? 1 : 0) : '—' }}</td>
          <td class="text-end text-nowrap pe-3" data-label="剩油" :class="{ 'sf-bad': row.fuel_short }">
            {{ fuelLeft(row) }}<template v-if="row.refuel"> → 補滿</template></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fmtDist, fmtNum, fmtTime, placeLabel, placePath } from '@/utils/navFormat'

const props = defineProps({
  plan: { type: Object, required: true },
  fuelCapacity: { type: Number, default: null },
  showLoad: { type: Boolean, default: false },
})

const ACTIONS = { stop: '途經', pickup: '取貨', dropoff: '送貨', end: '終點' }
const actionClass = a => ({ pickup: 'sf-chip--accent', dropoff: 'sf-chip--ok', end: 'sf-chip--todo' }[a] || '')
function actionLabel(a) {
  const base = ACTIONS[a.action] || a.action
  if (a.contract_name) return `${base} ${fmtNum(a.scu)} SCU`
  return a.cargo ? `${base} #${a.cargo} · ${fmtNum(a.scu)} SCU` : base
}

// 站點特性：特大機庫、外部貨運（裝卸碼頭，外掛貨櫃船能裝卸）、對接口
const traitsOf = p => [p?.xl_hangar ? '特大機庫' : '', p?.loading_dock ? '外部貨運' : '', p?.docking ? '對接口' : '']
  .filter(Boolean)

// 第 k 段出發前要補燃料／第 k 段單段就超過油箱
const refuelBefore = k => !!props.plan.refuel_stops?.includes(k)
const shortAt = k => !!props.plan.legs[k]?.fuel_short
// 起點那一列：在起點就地取貨的動作併進來
const startFuel = computed(() => {
  const s = table.value.start
  return s ? { refuel: s.refuel || refuelBefore(0), short: s.short, mixed: s.mixed }
    : { refuel: refuelBefore(0), short: shortAt(0), mixed: [] }
})

function viaOf(leg) {
  // 中途經過的點（最後一步的終點就是目的地，不列）
  return leg.steps.slice(0, -1).map((s, i) => ({ kind: leg.steps[i + 1].kind === 'jump' ? 'jump' : 'qt', place: s.to }))
}

const table = computed(() => {
  const legs = props.plan.legs || []
  const out = []
  for (let i = 0; i < legs.length; i++) {
    const leg = legs[i]
    const prev = out[out.length - 1]
    // 同一站：這段沒有移動，而且目的地跟上一列一樣
    if (prev && !leg.steps.length && leg.to.id === prev.to.id) {
      prev.legs.push(leg)
      prev.last = i
      continue
    }
    out.push({ to: leg.to, legs: [leg], first: i, last: i, via: viaOf(leg), moved: leg.steps.length > 0,
      distance: leg.distance, time: leg.time, fuel: leg.fuel, fuel_short: !!leg.fuel_short })
  }
  // 貨艙裡目前有哪些（貨物名稱 → 合約 → SCU），用來檢查同名不同合約
  const onboard = new Map()
  for (const row of out) {
    const lastLeg = row.legs[row.legs.length - 1]
    row.load_after = lastLeg.load_after
    row.fuel_after = lastLeg.fuel_after
    // 出發往下一段前：補燃料、下一段超過油箱
    row.refuel = refuelBefore(row.last + 1)
    row.short = shortAt(row.last + 1)
    // 動作：同一個動作、同一份合約、同一種貨物合併
    const merged = new Map()
    for (const leg of row.legs) {
      // 同一份合約裡同名的貨物（例如兩項都是 Waste）也合併
      const key = leg.contract_name ? `${leg.action}|${leg.contract}|${norm(leg.item_name)}` : `${leg.action}|${leg.cargo}|${merged.size}`
      const hit = merged.get(key)
      if (hit) hit.scu += leg.scu || 0
      else merged.set(key, { action: leg.action, cargo: leg.cargo, scu: leg.scu || 0, contract: leg.contract,
        contract_name: leg.contract_name, item_name: leg.item_name, item_named: leg.item_named })
    }
    row.actions = [...merged.values()]
    // 同名貨物分屬不同合約：這一站處理到的貨物名稱，在這站的動作或貨艙裡出現兩份以上合約
    // 沒填貨物名稱的（item_named 是 false，名稱是後端補的「貨物 N」）不比對
    const named = a => a.contract_name && a.item_named !== false
    const names = new Set(row.actions.filter(named).map(a => norm(a.item_name)))
    const contractsOf = new Map()
    const note = (name, contractName) => {
      if (!names.has(name)) return
      if (!contractsOf.has(name)) contractsOf.set(name, { label: '', set: new Set(), dropoff: false })
      contractsOf.get(name).set.add(contractName)
    }
    for (const [name, byContract] of onboard) {
      for (const [contractName, scu] of byContract) if (scu > 1e-9) note(name, contractName)
    }
    for (const a of row.actions) {
      if (!named(a)) continue
      note(norm(a.item_name), a.contract_name)
      const entry = contractsOf.get(norm(a.item_name))
      if (!entry.label) entry.label = a.item_name
      if (a.action === 'dropoff') entry.dropoff = true
    }
    // 取貨時：貨艙裡要分開放；送貨時：要分開繳交
    row.mixed = [...contractsOf.values()].filter(v => v.set.size > 1)
      .map(v => ({ name: v.label, contracts: [...v.set], kind: v.dropoff ? 'dropoff' : 'pickup' }))
    // 更新貨艙
    for (const a of row.actions) {
      if (!named(a)) continue
      const name = norm(a.item_name)
      if (!onboard.has(name)) onboard.set(name, new Map())
      const byContract = onboard.get(name)
      byContract.set(a.contract_name, (byContract.get(a.contract_name) || 0) + (a.action === 'pickup' ? a.scu : -a.scu))
    }
  }
  // 一開始就在起點做的事（沒有移動）併到起點那一列
  const start = out[0] && !out[0].moved && out[0].to.id === props.plan.start?.id ? out.shift() : null
  return { start, rows: out }
})

// 貨物名稱比對：「垃圾（Waste）」跟「Waste」算同一種（取括號裡的英文）
function norm(text) {
  const t = (text || '').trim()
  const m = t.match(/[（(]([^（）()]+)[）)]$/)
  return (m ? m[1] : t).trim().toLowerCase()
}

const mixedLabel = m => (m.kind === 'dropoff'
  ? `送貨：${m.name} 分屬 ${m.contracts.join('、')}，請分開繳交`
  : `取貨：${m.name} 分屬 ${m.contracts.join('、')}，請分開放置`)

function fuelLeft(row) {
  const cap = props.fuelCapacity
  if (row.fuel_after == null || !cap) return '—'
  return `${fmtNum(row.fuel_after)}（${Math.max(0, Math.round(row.fuel_after / cap * 100))}%）`
}
</script>

<style scoped>
.rlt-no { display: inline-block; min-width: 1.5rem; color: var(--sf-text-muted); font-weight: 400; }
.rlt-path { font-size: 1rem; color: var(--sf-text-muted); }
.rlt-action { display: flex; flex-wrap: wrap; align-items: center; gap: .25rem .5rem; }
.rlt-action + .rlt-action { margin-top: .35rem; }
.rlt-cargo { color: var(--sf-text-muted); }
</style>
