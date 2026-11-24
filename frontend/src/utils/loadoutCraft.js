// 配裝模擬的「製作品質」（純函式，測試：node src/utils/loadoutCraft.test.mjs）。
//
// 可製作的配件（後端 /item/loadout/items 帶 blueprint）可以調每個部位的材料品質（0–1000），
// 品質資料（GET /blueprint/master/<uuid>/quality）的加成依 utils/craftQuality.js 的 combine 合起來，
// 再套到配件數值上。配件主檔（scunpacked）的數值就是 Q500（倍率 1、加減值 0），
// 所以不可製作的配件一律當 Q500（鎖定）。
import { QUALITY_MID, clampQuality, combine } from './craftQuality.js'

export const LOCKED_QUALITY = QUALITY_MID

const mul = (obj, key, v) => { if (obj && typeof obj[key] === 'number') obj[key] *= v }

/** 品質屬性 key → 套到配件（item 是複本，可以直接改） */
const APPLY = {
  health_maxhealth: (it, v) => mul(it, 'hp', v),
  weapon_damage: (it, v) => {
    const s = it.stats || {}
    if (it.type === 'WeaponMining') return mul(s, 'mining_power', v)
    for (const k of ['alpha', 'dps', 'sustained']) mul(s, k, v)
    for (const k of Object.keys(s.damage || {})) mul(s.damage, k, v)
  },
  shield_maxhealth: (it, v) => mul(it.stats, 'hp', v),
  itemresource_coolantgeneration: (it, v) => mul(it.stats, 'coolant_gen', v),
  itemresource_powergeneration: (it, v) => { if (it.stats && typeof it.stats.power_gen === 'number') it.stats.power_gen += v },
  quantum_speed: (it, v) => mul(it.stats, 'speed', v),
  quantum_fuelrequirement: (it, v) => mul(it.stats, 'fuel_req', v),
}

/** 這個屬性在配裝模擬有沒有反映（雷達輔助瞄準距離、牽引光束這些沒有建模） */
export const applied = key => key in APPLY

/** 每個部位的品質：沒設定的是 Q500 */
export function qualitiesOf(slots, set) {
  return Object.fromEntries((slots || []).map(s => [s.key, set?.[s.key] ?? LOCKED_QUALITY]))
}

/** 配件套上品質後的複本（回傳 { item, rows }；rows＝combine 的綜合加成，畫面列出用） */
export function applyQuality(item, slots, qualities) {
  const rows = combine(slots, qualitiesOf(slots, qualities))
  const out = JSON.parse(JSON.stringify(item))
  for (const r of rows) APPLY[r.key]?.(out, r.value, r.additive)
  return { item: out, rows }
}

/** 全部部位都是 Q500＝沒調 */
export const isDefault = (q) => !q || Object.values(q).every(v => v === LOCKED_QUALITY)

/** 平均品質（列表上顯示「Q680」） */
export function avgQuality(slots, q) {
  const vals = Object.values(qualitiesOf(slots, q))
  return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : LOCKED_QUALITY
}

// 網址：配件 id:部位=品質,部位=品質;配件 id:…（只記調過的）
export function encodeQualities(map) {
  return Object.entries(map || {}).filter(([, q]) => !isDefault(q))
    .map(([id, q]) => `${id}:${Object.entries(q).map(([k, v]) => `${k}=${v}`).join(',')}`).join(';')
}
export function decodeQualities(text) {
  const out = {}
  for (const part of String(text || '').split(';')) {
    const i = part.indexOf(':')
    if (i <= 0) continue
    const q = {}
    for (const kv of part.slice(i + 1).split(',')) {
      const [k, v] = kv.split('=')
      const n = clampQuality(v, null)
      if (k && n !== null && v !== '' && v !== undefined) q[k] = n
    }
    if (Object.keys(q).length) out[part.slice(0, i)] = q
  }
  return out
}

/** 「實際數值」要列的欄位：品質屬性 key → [[取值, 名稱, 單位]] */
const STAT_VIEW = {
  health_maxhealth: [[it => it.hp, '耐久', '']],
  weapon_damage: [[it => it.stats?.alpha, '單發傷害', ''], [it => it.stats?.dps, 'DPS', ''],
    [it => it.stats?.sustained, '持續 DPS', ''], [it => it.stats?.mining_power, '採礦功率', '']],
  shield_maxhealth: [[it => it.stats?.hp, '護盾值', '']],
  itemresource_coolantgeneration: [[it => it.stats?.coolant_gen, '冷卻產量', '']],
  itemresource_powergeneration: [[it => it.stats?.power_gen, '電力產量', '格']],
  quantum_speed: [[it => it.stats?.speed, '量子速度', 'm/s']],
  quantum_fuelrequirement: [[it => it.stats?.fuel_req, '燃料需求', '']],
}

/** 配件套上品質前後的實際數值（配裝模擬有反映的屬性；配件沒有這個數值的略過）：[{ label, unit, before, after, better }] */
export function appliedStats(item, slots, qualities) {
  if (!item) return []
  const { item: out, rows } = applyQuality(item, slots, qualities)
  const res = []
  for (const r of rows) {
    for (const [get, label, unit] of STAT_VIEW[r.key] || []) {
      const before = get(item)
      if (typeof before !== 'number') continue
      res.push({ key: `${r.key}:${label}`, label, unit, before, after: get(out), better: r.better })
    }
  }
  return res
}
