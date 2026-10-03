// 任務／勢力資料的顯示格式（後台任務、勢力資料庫與玩家頁「解鎖任務」共用）。
// 中文都是後端同步時從 sc_translations 查好的 *_zh 欄位，這裡只負責排版。

/** 中文（英文）；沒有中文就只有英文 */
export function zhPair(en, zh) {
  if (!en) return zh || ''
  return zh ? `${zh}（${en}）` : en
}

export function fmtInt(v) {
  if (v === null || v === undefined || v === '') return '—'
  return Math.round(Number(v)).toLocaleString('en-US')
}

/** 0~1 的機率 → 百分比字串 */
export function fmtChance(v) {
  if (v === null || v === undefined) return '—'
  const pct = Number(v) * 100
  if (!Number.isFinite(pct)) return '—'
  return `${pct >= 10 || pct === 0 ? Math.round(pct) : pct.toFixed(1)}%`
}

/** 報酬（含幣別）：上游 reward_max 常是 0（代表固定金額），大於 min 才顯示區間 */
export function rewardLabel(m) {
  const min = m?.reward_min
  const max = m?.reward_max
  if (!min && !max) return '—'
  const cur = ` ${m?.reward_currency || 'UEC'}`
  if (max && min && max > min) return `${fmtInt(min)}–${fmtInt(max)}${cur}`
  return `${fmtInt(min || max)}${cur}`
}

/** 聲望：+1,000（Wallace Klim）、… */
export function reputationLabel(m) {
  const reps = m?.reputation_gained || []
  if (!reps.length) return ''
  return reps.map(r => {
    const amount = Number(r.amount)
    const sign = amount > 0 ? '+' : ''
    return `${sign}${fmtInt(amount)}${r.faction ? `（${r.faction}）` : ''}`
  }).join('、')
}

export function factionLabel(m) {
  return zhPair(m?.faction_name, m?.faction_name_zh) || zhPair(m?.mission_giver, m?.mission_giver_zh) || '—'
}
