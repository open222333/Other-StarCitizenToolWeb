// 玩家頁新聞的日期篩選（純函式，測試：node src/utils/newsDate.test.mjs；後端 GET /news/?since=&until=）
/** 日期篩選選項（玩家頁新聞）：今日、昨日、上週（今天往回 7 天，含今天） */
export const DATE_FILTERS = [
  { key: '', label: '不限' },
  { key: 'today', label: '今日' },
  { key: 'yesterday', label: '昨日' },
  { key: 'week', label: '上週' },
]

/** 日期篩選 → { since, until }（ISO，用瀏覽器時區的午夜切；until 不含）；key 是空的回 {} */
export function dateRange(key, now = new Date()) {
  const day = n => { const d = new Date(now); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + n); return d.toISOString() }
  if (key === 'today') return { since: day(0) }
  if (key === 'yesterday') return { since: day(-1), until: day(0) }
  if (key === 'week') return { since: day(-6) }
  return {}
}
