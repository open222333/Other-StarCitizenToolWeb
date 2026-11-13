// 配裝模擬的電源分配（pips）與訊號（EM／IR／截面）計算，見 components/LoadoutPowerCard.vue。
//
// 模型（用 scunpacked-data 的預設配裝驗證：281 艘太空船全部格數都開滿時，耗電、EM、IR、冷卻產量都跟資料集一致）：
//   - 每個耗電配件分 p 格電（0，或 Usage.Power 的最小～最大）；效率 f(p) = p / 最大格數 × 倍率(p)，
//     倍率看 power_ranges（分到 Start 格以上用那一段的 Modifier）
//   - 配件的 EM、耗冷卻、護盾回充、冷卻器產量都乘上 f(p)
//   - 武器共用一個電源池（ship.power.weapon_pool 格），實際耗電＝min(分到的格數, 全部武器耗電加總)
//   - 發電機的 EM＝每格 EM（發電機 EM 上限 ÷ 發電格數）× 已用格數
//   - 冷卻需求＝各配件耗冷卻＋已用電量；IR＝冷卻器 IR 上限加總 × 冷卻需求 ÷ 冷卻產量
//   - 最後乘上裝甲的訊號倍率（ship.power.signal）
//   - 量子模式：護盾關閉、量子引擎開啟（量子引擎只算 EM 與冷卻，跟資料集一樣不佔電）
//   - 發電格數：資料集只有預設發電機的總格數，換發電機時依發電量比例換算（估算）
// 其他固定耗電者（飛控、維生…）用船的預設值，可以調格數，EM／冷卻依格數等比例。

import { sectionOf, walk } from './loadoutCalc'

/** 這裡自己算的類別；其餘照船的預設值當固定耗電者（MODELED 的類別在掛點樹裡找不到時也用預設值補） */
export const MODELED = new Set(['Shield', 'Cooler', 'Radar', 'WeaponGun', 'TractorBeam', 'WeaponMining', 'SalvageHead',
  'QuantumDrive'])

export const STATIC_LABEL = {
  Shield: '護盾', Cooler: '冷卻', Radar: '雷達', WeaponGun: '武器',
  FlightController: '飛控', LifeSupportGenerator: '維生', QuantumInterdictionGenerator: '量子干擾',
  EMP: 'EMP', TractorBeam: '牽引', TowingBeam: '拖曳', SalvageHead: '打撈', WeaponMining: '採礦',
}

/** 分到 p 格時的倍率 */
export function modifierAt(ranges, p) {
  let mod = 1
  for (const [start, m] of ranges || []) if (p >= start) mod = m
  return ranges?.length && p < ranges[0][0] ? ranges[0][1] : mod
}

/** 分到 p 格時的效率（0～1） */
export function efficiency(max, ranges, p) {
  if (!max) return 1
  if (p <= 0) return 0
  return (Math.min(p, max) / max) * modifierAt(ranges, p)
}

const usage = it => it?.stats?.power_use || [0, 0]

/**
 * 這艘船目前配裝的耗電者清單。
 * kind：shield／weapons／cooler／radar／utility／quantum／static；每個 { key, kind, label, min, max, step, items… }
 */
export function consumers(ship, slots, itemOf, mode = 'scm') {
  const out = []
  const shields = []
  const weapons = []
  walk(slots, (n, root) => {
    const it = itemOf(n.item)
    if (!it) return
    if (it.type === 'Missile' || it.type === 'Bomb') return false
    if (it.type === 'WeaponGun') {
      weapons.push(it)
      return
    }
    const [min, max] = usage(it)
    const base = { key: n.id, item: it, min: Math.ceil(min || 0), max: Math.round(max || 0) }
    if (it.type === 'Shield') shields.push(base)
    else if (it.type === 'Cooler') out.push({ ...base, kind: 'cooler' })
    else if (it.type === 'Radar') out.push({ ...base, kind: 'radar' })
    else if (it.type === 'QuantumDrive') out.push({ ...base, kind: 'quantum', min: 0, max: 0, fixed: true })
    else if (['TractorBeam', 'WeaponMining', 'SalvageHead'].includes(it.type) && max) {
      out.push({ ...base, kind: 'utility', section: sectionOf(root, itemOf) })
    }
  })
  // 同時運作的護盾有上限，取最強的幾個（跟 loadoutCalc.summarize 一樣）
  shields.sort((a, b) => (b.item.stats?.hp || 0) - (a.item.stats?.hp || 0))
  const active = ship?.shield_slots > 0 ? shields.slice(0, ship.shield_slots) : shields
  const list = active.map(s => ({ ...s, kind: 'shield' }))
  const wSum = weapons.reduce((a, it) => a + (usage(it)[1] || 0), 0)
  const pool = ship?.power?.weapon_pool > 0 ? ship.power.weapon_pool : Math.ceil(wSum)
  if (weapons.length) {
    list.push({ key: 'weapons', kind: 'weapons', min: 0, max: Math.min(pool, Math.max(1, Math.ceil(wSum))), items: weapons,
      draw: wSum, em: weapons.reduce((a, it) => a + (it.stats?.em || 0), 0),
      coolant: 0 })
  }
  list.push(...out)
  // 掛點樹裡算得到的類別
  const found = new Set(list.map(c => c.kind === 'weapons' ? 'WeaponGun' : c.item?.type).filter(Boolean))
  for (const [group, v] of Object.entries(ship?.power?.groups || {})) {
    if (!v.power && !v.em && !v.coolant) continue
    if (MODELED.has(group) && (found.has(group) || group === 'QuantumDrive')) continue
    list.push({ key: `static:${group}`, kind: 'static', group, label: STATIC_LABEL[group] || group,
      min: 0, max: Math.round(v.power), em: v.em, coolant: v.coolant })
  }
  // 戰鬥模式量子引擎關閉；量子模式護盾關閉
  const offKind = mode === 'quantum' ? 'shield' : 'quantum'
  for (const c of list) {
    if (c.kind === offKind) c.off = true
  }
  return list
}

/** 一個耗電者分 p 格時的耗電、EM、耗冷卻、效率 */
export function consumerLoad(c, p) {
  if (c.off) return { power: 0, em: 0, coolant: 0, eff: 0 }
  if (c.kind === 'quantum') {
    // 量子引擎：只算 EM 與冷卻（不佔電，跟資料集一致）
    return { power: 0, em: c.item.stats?.em || 0, coolant: c.item.stats?.coolant_use?.[1] || 0, eff: 1 }
  }
  if (c.kind === 'weapons') {
    const draw = Math.min(p, c.draw)
    const ratio = c.draw ? draw / c.draw : 0
    return { power: draw, em: c.em * ratio, coolant: 0, eff: ratio }
  }
  if (c.kind === 'static') {
    const ratio = c.max ? Math.min(p, c.max) / c.max : 1
    return { power: Math.min(p, c.max), em: c.em * ratio, coolant: c.coolant * ratio, eff: ratio }
  }
  const s = c.item.stats || {}
  const eff = efficiency(c.max, s.power_ranges, p)
  const coolant = c.kind === 'cooler' ? 0 : (s.coolant_use?.[1] || 0) * eff
  return { power: Math.min(p, c.max), em: (s.em || 0) * eff, coolant, eff }
}

/** 合法的格數：0，或最小～最大之間 */
export function clampPips(c, p) {
  if (c.fixed || c.off) return 0
  if (p <= 0) return 0
  return Math.max(c.min || 1, Math.min(c.max, Math.round(p)))
}

/** 發電格數：預設發電機的總格數 × 目前發電量 ÷ 預設發電量 */
export function generation(ship, slots, defaults, itemOf) {
  const sumGen = ids => ids.reduce((a, id) => a + (itemOf(id)?.type === 'PowerPlant' ? itemOf(id).stats?.power_gen || 0 : 0), 0)
  const now = []
  walk(slots, n => { if (n.item) now.push(n.item) })
  const base = sumGen(Object.values(defaults || {}).filter(Boolean))
  const cur = sumGen(now)
  const gen = ship?.power?.gen || 0
  return base ? Math.round(gen * cur / base) : cur
}

/** 自動分配：固定耗電者開滿，其餘先給最小值，剩下的格數輪流加（護盾 → 武器 → 冷卻 → 雷達 → 其他） */
export function autoAllocate(list, gen, keep = {}) {
  // keep：要保留的格數（例如換配件時沒動到的那幾個），其餘重新分
  const pips = {}
  const ORDER = ['shield', 'weapons', 'cooler', 'radar', 'utility']
  let used = 0
  for (const c of list) {
    if (c.off || c.fixed) { pips[c.key] = 0; continue }
    if (c.key in keep) pips[c.key] = clampPips(c, keep[c.key])
    else if (c.kind === 'static') pips[c.key] = c.max
    // 武器先給到全部武器的耗電量（再多也用不到），其餘先給最小值
    else if (c.kind === 'weapons') pips[c.key] = Math.min(c.max, Math.ceil(c.draw))
    else pips[c.key] = c.min || 0
    used += consumerLoad(c, pips[c.key]).power
  }
  const growable = list.filter(c => !c.off && !c.fixed && c.kind !== 'static' && !(c.key in keep))
    .sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind))
  let changed = true
  while (changed) {
    changed = false
    for (const c of growable) {
      const p = pips[c.key]
      if (p >= c.max) continue
      const next = clampPips(c, p + 1)
      const extra = consumerLoad(c, next).power - consumerLoad(c, p).power
      if (used + extra > gen + 1e-9) continue
      pips[c.key] = next
      used += extra
      changed = true
    }
  }
  return pips
}

/** 全部開滿 */
export function maxAllocate(list) {
  return Object.fromEntries(list.map(c => [c.key, c.off || c.fixed ? 0 : c.max]))
}

/** 依目前的格數算出電力、冷卻、訊號 */
export function powerSummary(ship, list, pips, gen, ppEmMax) {
  let used = 0
  let em = 0
  let coolUsed = 0
  let coolGen = 0
  let irMax = 0
  const loads = {}
  const emBy = {}
  for (const c of list) {
    const p = pips[c.key] ?? 0
    const l = consumerLoad(c, p)
    loads[c.key] = { ...l, pips: p }
    used += l.power
    em += l.em
    coolUsed += l.coolant
    const g = c.kind === 'static' ? c.label : c.kind
    emBy[g] = (emBy[g] || 0) + l.em
    if (c.kind === 'cooler' && !c.off) {
      coolGen += (c.item.stats?.coolant_gen || 0) * l.eff
      irMax += c.item.stats?.ir || 0
    }
  }
  // 發電機：每格 EM（發電機 EM 上限 ÷ 發電格數）× 已用格數
  const ppEm = gen ? (ppEmMax || 0) / gen * used : 0
  em += ppEm
  emBy.power = ppEm
  coolUsed += used                          // 發電機本身的冷卻需求＝已用電量
  const sig = ship?.power?.signal || { em: 1, ir: 1, cs: 1 }
  const ir = coolGen ? irMax * coolUsed / coolGen : 0
  const cs = Math.max(...(ship?.cross_section || [0]).map(v => v || 0)) * (sig.cs ?? 1)
  return {
    gen, used, free: gen - used, over: used > gen + 1e-9, loads,
    coolUsed, coolGen, coolPct: coolGen ? coolUsed / coolGen : 0, coolShort: coolUsed > coolGen + 1e-9,
    em: em * (sig.em ?? 1), ir: ir * (sig.ir ?? 1), cs, emBy,
  }
}

/** 發電機 EM 上限加總（目前配裝） */
export function powerPlantEm(slots, itemOf) {
  let sum = 0
  walk(slots, n => { const it = itemOf(n.item); if (it?.type === 'PowerPlant') sum += it.stats?.em || 0 })
  return sum
}
