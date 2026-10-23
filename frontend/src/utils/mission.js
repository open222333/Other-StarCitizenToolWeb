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

/** 聲望異動數字：+1,500／-250 */
export function fmtRep(v) {
  const n = Number(v)
  return Number.isFinite(n) ? `${n > 0 ? '+' : ''}${fmtInt(n)}` : '—'
}

/** 冷卻秒數 → 「45 秒」「10 分」「2 時 30 分」「1 天 4 時」 */
export function fmtCooldown(sec) {
  const s = Number(sec)
  if (!Number.isFinite(s) || s <= 0) return '—'
  if (s < 60) return `${Math.round(s)} 秒`
  const m = Math.round(s / 60)
  if (m < 60) return `${m} 分`
  const h = Math.floor(m / 60), rm = m % 60
  if (h < 24) return rm ? `${h} 時 ${rm} 分` : `${h} 時`
  const d = Math.floor(h / 24), rh = h % 24
  return rh ? `${d} 天 ${rh} 時` : `${d} 天`
}

/** 任務條件一行（玩家頁）：可分享、可重複接、戰鬥、任務鏈… */
export function missionConditions(m) {
  const parts = []
  if (m.shareable) parts.push('可分享')
  parts.push(m.once_only ? '只能接一次' : '可重複接')
  if (m.has_combat) {
    const lo = m.enemy_count_min, hi = m.enemy_count_max
    parts.push(lo || hi ? `戰鬥（敵人 ${lo ?? '?'}–${hi ?? '?'}）` : '戰鬥')
  }
  if (m.has_chain) parts.push('任務鏈')
  if (m.has_prerequisites) parts.push('有前置條件')
  if (m.max_players_per_instance > 1) parts.push(`最多 ${m.max_players_per_instance} 人`)
  return parts.join(' · ')
}
