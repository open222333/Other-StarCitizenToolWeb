// cron（5 欄：分 時 日 月 星期）↔ 易讀的排程設定（後台「資料同步排程」的 CronEditor 用）。
//
// 只認得下面幾種常見寫法，其他的一律當「自訂」顯示原始 cron（不會亂改）：
//   每 N 小時  M */N * * *   （N=1 時也接受 M * * * *）
//   每天       M H * * *
//   每週       M H * * 1,3,5  （星期 0／7＝週日）
//   每月       M H D * *
export const WEEKDAYS = [
  { value: 1, label: '一' }, { value: 2, label: '二' }, { value: 3, label: '三' }, { value: 4, label: '四' },
  { value: 5, label: '五' }, { value: 6, label: '六' }, { value: 0, label: '日' },
]
export const HOUR_STEPS = [1, 2, 3, 4, 6, 8, 12]

const INT = /^\d+$/
const pad = n => String(n).padStart(2, '0')
const inRange = (v, lo, hi) => INT.test(v) && +v >= lo && +v <= hi

/** cron → { mode: 'hourly'|'daily'|'weekly'|'monthly'|'custom', minute, hour, every, days, dom } */
export function parseCron(cron) {
  const parts = (cron || '').trim().split(/\s+/)
  const base = { mode: 'custom', minute: 0, hour: 4, every: 6, days: [1], dom: 1 }
  if (parts.length !== 5) return base
  const [mi, h, d, mo, w] = parts
  if (!inRange(mi, 0, 59) || mo !== '*') return base
  const minute = +mi
  if (d === '*' && w === '*') {
    if (h === '*') return { ...base, mode: 'hourly', minute, every: 1 }
    const step = /^\*\/(\d+)$/.exec(h)
    if (step && HOUR_STEPS.includes(+step[1])) return { ...base, mode: 'hourly', minute, every: +step[1] }
    if (inRange(h, 0, 23)) return { ...base, mode: 'daily', minute, hour: +h }
    return base
  }
  if (!inRange(h, 0, 23)) return base
  const hour = +h
  if (d === '*' && w !== '*') {
    const list = w.split(',')
    if (!list.every(x => inRange(x, 0, 7))) return base
    const days = [...new Set(list.map(x => +x % 7))]
    return { ...base, mode: 'weekly', minute, hour, days }
  }
  if (w === '*' && inRange(d, 1, 31)) return { ...base, mode: 'monthly', minute, hour, dom: +d }
  return base
}

/** 易讀設定 → cron（custom 回 null，呼叫端自己留原字串） */
export function buildCron(s) {
  const m = Math.min(59, Math.max(0, +s.minute || 0))
  const h = Math.min(23, Math.max(0, +s.hour || 0))
  if (s.mode === 'hourly') return s.every === 1 ? `${m} * * * *` : `${m} */${s.every} * * *`
  if (s.mode === 'daily') return `${m} ${h} * * *`
  if (s.mode === 'weekly') {
    const order = WEEKDAYS.map(d => d.value)
    const days = [...new Set(s.days)].sort((a, b) => order.indexOf(a) - order.indexOf(b))
    return `${m} ${h} * * ${(days.length ? days : [1]).join(',')}`
  }
  if (s.mode === 'monthly') return `${m} ${h} ${Math.min(31, Math.max(1, +s.dom || 1))} * *`
  return null
}

/** cron → 中文說明，例如「每週一、四 04:30」；認不得的回 null */
export function describeCron(cron) {
  const s = parseCron(cron)
  const time = `${pad(s.hour)}:${pad(s.minute)}`
  if (s.mode === 'hourly') return s.every === 1 ? `每小時第 ${s.minute} 分` : `每 ${s.every} 小時（第 ${s.minute} 分）`
  if (s.mode === 'daily') return `每天 ${time}`
  if (s.mode === 'weekly') {
    if (s.days.length === 7) return `每天 ${time}`
    const labels = WEEKDAYS.filter(d => s.days.includes(d.value)).map(d => d.label)
    return `每週${labels.join('、')} ${time}`
  }
  if (s.mode === 'monthly') return `每月 ${s.dom} 號 ${time}`
  return null
}
