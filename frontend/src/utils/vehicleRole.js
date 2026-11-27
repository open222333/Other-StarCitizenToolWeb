// ── 船艦角色分組（多選篩選 MultiSelectFilter 依群組分段、可整組勾選；同物品類型群組的做法）──
// 遊戲的角色是自由文字（Heavy Fighter、Light Freight / Medium Fighter、Starter / Pathfinder…），
// 用關鍵字歸到大類：有「/」的看第一段（Starter 跳過），第一個對到的群組為準；都沒對到歸「其他」。
export const ROLE_GROUPS = [
  { label: '戰機', words: ['fighter', 'interceptor', 'snub', 'combat'] },
  { label: '轟炸與砲艇', words: ['bomber', 'gunship', 'gun ship'] },
  { label: '主力艦', words: ['corvette', 'destroyer', 'frigate', 'carrier'] },
  { label: '陸戰與空降', words: ['dropship', 'tank', 'anti-vehicle', 'anti-air'] },
  { label: '運輸', words: ['freight', 'cargo', 'transport', 'passenger'] },
  { label: '工業', words: ['mining', 'salvage', 'refuel', 'recovery'] },
  { label: '探索與科研', words: ['expedition', 'pathfinder', 'exploration', 'science', 'data', 'reporting'] },
  { label: '支援', words: ['medical', 'interdiction', 'support'] },
  { label: '競速與觀光', words: ['racing', 'touring', 'luxury'] },
  { label: '多用途', words: ['generalist', 'modular', 'multi'] },
]
export const ROLE_OTHER_GROUP = '其他'

/** 角色 → { label, index }（index 給分段排序） */
export function vehicleRoleGroup(role) {
  const parts = String(role || '').toLowerCase().split('/').map(s => s.trim())
    .filter(s => s && s !== 'starter')
  for (const part of parts.length ? parts : [String(role || '').toLowerCase()]) {
    const i = ROLE_GROUPS.findIndex(g => g.words.some(w => part.includes(w)))
    if (i >= 0) return { label: ROLE_GROUPS[i].label, index: i }
  }
  return { label: ROLE_OTHER_GROUP, index: ROLE_GROUPS.length }
}

/** 角色選項（字串或 {value, label}）加上 group／groupIndex，同群組內照名稱排 */
export function groupRoleOptions(options) {
  return (options || []).map((o) => {
    const opt = o !== null && typeof o === 'object' ? o : { value: o, label: String(o) }
    const g = vehicleRoleGroup(opt.value)
    return { ...opt, group: g.label, groupIndex: g.index }
  }).sort((a, b) => a.groupIndex - b.groupIndex || String(a.label).localeCompare(String(b.label), 'zh-Hant'))
}
