// 藍圖品質試算（純函式，測試：node src/utils/craftQuality.test.mjs）。
//
// 資料來自 GET /blueprint/master/<uuid>/quality（scunpacked-data blueprints.json，見 src/scdata.py
// 的 map_blueprint_quality）：每個部位（Frame／Barrel…）列出會受材料品質影響的屬性：
//   - type 'linear'：倍率。品質 q_min → at_min、q_max → at_max，中間線性內插（超出範圍取端點）
//   - type 'linear_integer_additive'：依品質分段（segments），每段加減一個整數（例如 Power Pips）
// 同一個屬性出現在好幾個部位時：倍率相乘、加減值相加（綜合加成）。

export const QUALITY_MIN = 0
export const QUALITY_MAX = 1000

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))

export function isAdditive(m) {
  return m?.type === 'linear_integer_additive'
}

/** 某個加成在品質 q 的值：倍率（linear）或整數加減值（additive）；資料不完整回 null */
export function modifierAt(m, q) {
  if (!m) return null
  const quality = clamp(Number(q) || 0, QUALITY_MIN, QUALITY_MAX)
  if (isAdditive(m)) {
    const segs = m.segments || []
    const seg = segs.find(s => quality >= s.q_min && quality <= s.q_max)
      || (quality < (segs[0]?.q_min ?? 0) ? segs[0] : segs[segs.length - 1])
    if (!seg) return null
    const span = seg.q_max - seg.q_min
    const t = span > 0 ? clamp((quality - seg.q_min) / span, 0, 1) : 0
    return Math.round(seg.at_start + (seg.at_end - seg.at_start) * t)
  }
  if (m.at_min === null || m.at_min === undefined || m.at_max === null || m.at_max === undefined) return null
  const span = (m.q_max ?? QUALITY_MAX) - (m.q_min ?? QUALITY_MIN)
  const t = span > 0 ? clamp((quality - (m.q_min ?? 0)) / span, 0, 1) : 0
  return m.at_min + (m.at_max - m.at_min) * t
}

/** 品質越高越好的方向：倍率往 at_max 那邊走才算變好（例如後座力 at_max < at_min） */
export function improves(m, value) {
  if (value === null || value === undefined) return null
  if (isAdditive(m)) return value === 0 ? null : value > 0
  if (m.at_max === m.at_min || value === 1) return null
  return m.at_max > m.at_min ? value > 1 : value < 1
}

/**
 * 綜合加成：slots 是品質資料的部位陣列，qualities 是 {部位 key: 品質}。
 * 回傳 [{ key, name, name_zh, additive, value, better }]，依第一次出現的順序。
 */
export function combine(slots, qualities) {
  const out = new Map()
  for (const slot of slots || []) {
    const q = qualities?.[slot.key] ?? 500
    for (const m of slot.modifiers || []) {
      const v = modifierAt(m, q)
      if (v === null) continue
      const key = m.key || m.name
      if (!out.has(key)) {
        out.set(key, { key, name: m.name, name_zh: m.name_zh, additive: isAdditive(m), value: isAdditive(m) ? 0 : 1, ref: m })
      }
      const row = out.get(key)
      row.value = row.additive ? row.value + v : row.value * v
    }
  }
  return [...out.values()].map(({ ref, ...row }) => ({ ...row, better: improves(ref, row.value) }))
}

/** ×1.05；additive 顯示 +1／-2 */
export function fmtModifier(value, additive) {
  if (value === null || value === undefined) return '—'
  if (additive) return value > 0 ? `+${value}` : String(value)
  return `×${value.toFixed(3).replace(/0$/, '')}`
}

/** 倍率換成百分比變化：1.05 → +5.0%、0.9 → -10.0% */
export function fmtPercent(value) {
  if (value === null || value === undefined) return ''
  const pct = (value - 1) * 100
  if (Math.abs(pct) < 0.05) return '±0%'
  return `${pct > 0 ? '+' : ''}${pct.toFixed(1)}%`
}
