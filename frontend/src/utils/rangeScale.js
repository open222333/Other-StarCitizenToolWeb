// 範圍篩選（components/SfRangeFilter.vue）的拉條刻度換算：價格、貨艙這種從幾十到上億都有的值用對數刻度，
// 拉條上每一段差不多一樣好拉；拉出來的值取「好看的整數」（兩位有效數字），輸入框照輸入的值不修。
// 純函式，node 測試能直接載入。

export const SLIDER_STEPS = 1000

/** 值 → 拉條位置（0～SLIDER_STEPS）。log＝對數刻度（0 也可以：用 log(1+x)） */
export function toPos(value, max, log = true) {
  const v = Math.min(Math.max(Number(value) || 0, 0), max)
  if (!max) return 0
  const r = log ? Math.log1p(v) / Math.log1p(max) : v / max
  return Math.round(r * SLIDER_STEPS)
}

/** 拉條位置 → 值（取兩位有效數字，例如 1234 → 1200、87654 → 88000） */
export function fromPos(pos, max, log = true) {
  const r = Math.min(Math.max(Number(pos) || 0, 0), SLIDER_STEPS) / SLIDER_STEPS
  const raw = log ? Math.expm1(r * Math.log1p(max)) : r * max
  return niceRound(raw)
}

export function niceRound(v) {
  if (!(v > 0)) return 0
  if (v < 10) return Math.round(v)
  const mag = 10 ** (Math.floor(Math.log10(v)) - 1)
  return Math.round(v / mag) * mag
}

/** 範圍是不是有設（min／max 任一邊不是空的） */
export const rangeActive = r => !!r && ((r.min !== '' && r.min != null) || (r.max !== '' && r.max != null))

/** value 在不在範圍內（空的那一邊不限；有設範圍時沒有值的不算在內） */
export function inRange(value, r) {
  if (!rangeActive(r)) return true
  if (value == null || value === '') return false
  const n = Number(value)
  const lo = r.min === '' || r.min == null ? null : Number(r.min)
  const hi = r.max === '' || r.max == null ? null : Number(r.max)
  return (lo === null || n >= lo) && (hi === null || n <= hi)
}
