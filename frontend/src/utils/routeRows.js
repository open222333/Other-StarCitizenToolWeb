// 航段表的列（RouteLegsTable.vue 的表格、RouteFlowView.vue 的總覽共用）：plan（後端 nav._build_plan）→
// { start: 起點那一列（在起點就地做的事，沒有就是 null）, rows: [...] }；同一站連續的動作併成一列，
// 每列有 key（已去過、貨物規劃用的代號）、to、legs、via（經過的 OM／跳躍點）、距離／時間／油量、補燃料提示…
import { fmtNum } from '@/utils/navFormat'

export const ACTIONS = { start: '出發', stop: '途經', pickup: '取貨', dropoff: '送貨', end: '終點', hub: '回指定站' }
export const actionClass = a => ({ pickup: 'sf-chip--accent', dropoff: 'sf-chip--ok', end: 'sf-chip--todo', hub: 'sf-chip--todo' }[a] || '')
export function actionLabel(a) {
  const base = ACTIONS[a.action] || a.action
  // 收集任務的取貨點（合約分配：各點量不知道）
  if (a.unknown) return `${base}（數量未知）`
  if (a.contract_name) return `${base} ${fmtNum(a.scu)} SCU`
  return a.cargo ? `${base} #${a.cargo} · ${fmtNum(a.scu)} SCU` : base
}

// 站點特性：特大機庫、外部貨運（裝卸碼頭，外掛貨櫃船能裝卸）、對接口
export const TRAITS = [
  { key: 'xl', field: 'xl_hangar', label: '特大機庫', icon: 'bi bi-building' },
  { key: 'dock', field: 'loading_dock', label: '外部貨運', icon: 'bi bi-box-seam' },
  { key: 'docking', field: 'docking', label: '對接口', icon: 'bi bi-plug' },
]
export const traitsOf = p => TRAITS.filter(t => p?.[t.field])

// 第 k 段出發前要補燃料／第 k 段單段就超過油箱
export function viaOf(leg) {
  // 中途經過的點（最後一步的終點就是目的地，不列）
  return leg.steps.slice(0, -1).map((s, i) => ({ kind: leg.steps[i + 1].kind === 'jump' ? 'jump' : 'qt', place: s.to }))
}

export function buildRouteRows(plan) {
  const refuelBefore = k => !!plan.refuel_stops?.includes(k)
  const shortAt = k => !!plan.legs?.[k]?.fuel_short
  const legs = plan.legs || []
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
  const seenKeys = new Map()
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
      if (hit) {
        hit.scu += leg.scu || 0
        hit.unknown = hit.unknown && !!leg.scu_unknown
      } else merged.set(key, { action: leg.action, cargo: leg.cargo, scu: leg.scu || 0, contract: leg.contract,
        contract_name: leg.contract_name, item_name: leg.item_name, item_named: leg.item_named,
        unknown: !!leg.scu_unknown })
    }
    row.actions = [...merged.values()]
    // 列的代號（已去過用）：目的地＋做的事，調整順序後還認得
    // （同一個代號出現第二次時加上次數，例如同一站去兩次）
    const base = `${row.to.id}|${row.actions.map(a => (a.contract_name
      ? `${a.action}:${a.contract}:${norm(a.item_name)}` : a.action)).join(',')}`
    seenKeys.set(base, (seenKeys.get(base) || 0) + 1)
    row.key = seenKeys.get(base) > 1 ? `${base}#${seenKeys.get(base)}` : base
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
      // 數量未知的取貨也算「貨艙裡有這份合約的貨」
      const delta = a.action === 'pickup' ? (a.scu || (a.unknown ? 1 : 0)) : -a.scu
      byContract.set(a.contract_name, (byContract.get(a.contract_name) || 0) + delta)
    }
  }
  // 一開始就在起點做的事（沒有移動）併到起點那一列
  const start = out[0] && !out[0].moved && out[0].to.id === plan.start?.id ? out.shift() : null
  return { start, rows: out }
}

// 貨物名稱比對：「垃圾（Waste）」跟「Waste」算同一種（取括號裡的英文）
export function norm(text) {
  const t = (text || '').trim()
  const m = t.match(/[（(]([^（）()]+)[）)]$/)
  return (m ? m[1] : t).trim().toLowerCase()
}


// ── 航線結果的顯示方式（RouteViewBar.vue；兩個規劃器共用）──
export const ROUTE_VIEWS = [
  { key: 'table', label: '航段表', icon: 'bi bi-list-ol' },
  { key: 'flow', label: '總覽', icon: 'bi bi-grid-3x3-gap' },
  { key: 'map', label: '3D 星圖', icon: 'bi bi-globe2' },
]
export const FLOW_DIRS = [
  { key: 'horizontal', label: '橫向', icon: 'bi bi-arrow-left-right', title: '一行一行排，左右來回' },
  { key: 'vertical', label: '直向', icon: 'bi bi-arrow-down-up', title: '一欄一欄排，上下來回' },
]
/** 存起來的顯示方式／方向不認得就用預設（總覽、橫向） */
export const viewOr = v => (ROUTE_VIEWS.some(x => x.key === v) ? v : 'flow')
export const flowDirOr = d => (d === 'vertical' ? 'vertical' : 'horizontal')
