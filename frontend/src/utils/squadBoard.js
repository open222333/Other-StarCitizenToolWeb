// 戰術小隊分配表的純函式（components/SquadBoards.vue、SquadBoardView.vue 共用；資料格式見 src/models/squad.py）。
// 表：{ title, event_at, note, squads: [{ id, name, note, leader, ships: [{ id, vehicle_id, vehicle_name, label, crew: [人員] }], members: [人員] }] }
// 人員：{ id, scid, name, role }（scid 是 null＝沒註冊網站的人）

export const MAX_SQUADS = 20
export const MAX_SHIPS_PER_SQUAD = 30
export const MAX_PEOPLE = 300

/** 職位下拉的預設選項（後端也有一份 DEFAULT_ROLES；可以自填） */
export const DEFAULT_ROLES = ['駕駛', '副駕駛', '砲手', '工程師', '醫療', '陸戰', '其他']

/** 表裡全部用過的 id */
function usedIds(board) {
  const ids = new Set()
  for (const s of board.squads || []) {
    ids.add(s.id)
    for (const v of s.ships || []) {
      ids.add(v.id)
      for (const p of v.crew || []) ids.add(p.id)
    }
    for (const p of s.members || []) ids.add(p.id)
  }
  return ids
}

/** 產生表內不重複的 id（prefix：s 小隊、v 艦船、m 人員） */
export function newId(board, prefix) {
  const used = usedIds(board)
  let n = used.size + 1
  while (used.has(`${prefix}${n}`)) n += 1
  return `${prefix}${n}`
}

export function emptySquad(board) {
  return { id: newId(board, 's'), name: `小隊 ${(board.squads || []).length + 1}`, note: '', leader: null, ships: [], members: [] }
}

/** 一個小隊的全部人員（船上＋不在船上） */
export function squadPeople(squad) {
  return [...(squad.ships || []).flatMap(v => v.crew || []), ...(squad.members || [])]
}

export function countPeople(board) {
  return (board.squads || []).reduce((n, s) => n + squadPeople(s).length, 0)
}

export function countShips(board) {
  return (board.squads || []).reduce((n, s) => n + (s.ships || []).length, 0)
}

/** 同一個玩家在表裡出現兩次以上的 scid（兩處都標「重複」，不擋） */
export function duplicateScids(board) {
  const seen = new Map()
  for (const s of board.squads || []) {
    for (const p of squadPeople(s)) if (p.scid) seen.set(p.scid, (seen.get(p.scid) || 0) + 1)
  }
  return new Set([...seen].filter(([, n]) => n > 1).map(([k]) => k))
}

/** 陣列裡第 i 個往上（d = -1）或往下（d = 1）移一格；超出範圍就不動。直接改 list。 */
export function moveItem(list, i, d) {
  const j = i + d
  if (j < 0 || j >= list.length) return false
  const [x] = list.splice(i, 1)
  list.splice(j, 0, x)
  return true
}

/** 人員可以移去的位置：每個小隊的每艘船、每個小隊的「不在船上」 */
export function personTargets(board) {
  const out = []
  ;(board.squads || []).forEach((s, si) => {
    ;(s.ships || []).forEach(v => out.push({ key: `v:${v.id}`, label: `${s.name || `小隊 ${si + 1}`} › ${v.label || v.vehicle_name}` }))
    out.push({ key: `s:${s.id}`, label: `${s.name || `小隊 ${si + 1}`} › 不在船上` })
  })
  return out
}

/** 人員現在在哪（personTargets 的 key） */
export function personLocation(board, personId) {
  for (const s of board.squads || []) {
    for (const v of s.ships || []) if ((v.crew || []).some(p => p.id === personId)) return `v:${v.id}`
    if ((s.members || []).some(p => p.id === personId)) return `s:${s.id}`
  }
  return ''
}

/** 把人員移到 target（personTargets 的 key），加在最後。直接改 board。 */
export function movePerson(board, personId, target) {
  let person = null
  let fromSquad = null
  for (const s of board.squads || []) {
    for (const v of s.ships || []) {
      const i = (v.crew || []).findIndex(p => p.id === personId)
      if (i >= 0) { person = v.crew.splice(i, 1)[0]; fromSquad = s }
    }
    const i = (s.members || []).findIndex(p => p.id === personId)
    if (i >= 0) { person = s.members.splice(i, 1)[0]; fromSquad = s }
  }
  if (!person) return false
  const [kind, id] = target.split(':')
  for (const s of board.squads || []) {
    const list = kind === 's' ? (s.id === id ? s.members : null) : (s.ships || []).find(v => v.id === id)?.crew
    if (!list) continue
    list.push(person)
    // 換到別的小隊就不再是原本小隊的隊長
    if (fromSquad && fromSquad !== s && fromSquad.leader === personId) fromSquad.leader = null
    return true
  }
  return false
}

/** 船的顯示名稱：識別名稱（船名） */
export function shipTitle(v) {
  return v.label ? `${v.label}（${v.vehicle_name}）` : v.vehicle_name || '未選船'
}

/** 存檔用：只留後端要的欄位 */
export function boardPayload(board) {
  const person = p => ({ id: p.id, scid: p.scid || null, name: p.name || '', role: p.role || '' })
  return {
    title: board.title || '', event_at: board.event_at || '', note: board.note || '', rev: board.rev,
    squads: (board.squads || []).map(s => ({
      id: s.id, name: s.name || '', note: s.note || '', leader: s.leader || null,
      ships: (s.ships || []).map(v => ({ id: v.id, vehicle_id: v.vehicle_id, label: v.label || '', crew: (v.crew || []).map(person) })),
      members: (s.members || []).map(person),
    })),
  }
}

/** 行動時間 'YYYY-MM-DDTHH:MM' → 顯示文字（含星期） */
export function fmtEventAt(value) {
  if (!value) return ''
  const d = new Date(value.length === 10 ? `${value}T00:00` : value)
  if (Number.isNaN(d.getTime())) return value
  const week = '日一二三四五六'[d.getDay()]
  const date = `${d.getFullYear()}/${String(d.getMonth() + 1).padStart(2, '0')}/${String(d.getDate()).padStart(2, '0')}（${week}）`
  return value.length === 10 ? date : `${date} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
