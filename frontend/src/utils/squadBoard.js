// 戰術小隊分配表的純函式（components/SquadBoards.vue、SquadBoardView.vue 共用；資料格式見 src/models/squad.py）。
// 測試：node src/utils/squadBoard.test.mjs
// 表：{ title, event_at, note, fleets: [{ id, name, note, squads: [{ id, name, note, leader,
//        ships: [{ id, vehicle_id, vehicle_name, label, crew: [人員] }], members: [人員] }] }] }
// 人員：{ id, scid, name, roles: [職位] }（scid 是 null＝沒註冊網站的人；職位可兼職，最多 MAX_ROLES 個）

export const MAX_FLEETS = 10
export const MAX_SQUADS = 20         // 整張表（所有艦隊加起來）
export const MAX_ROLES = 3
export const MAX_SHIPS_PER_SQUAD = 30
export const MAX_PEOPLE = 300

/** 職位晶片的預設選項（後端也有一份 DEFAULT_ROLES） */
export const DEFAULT_ROLES = ['駕駛', '副駕駛', '砲手', '工程師', '醫療', '陸戰', '其他']

/** 表裡全部的小隊（依艦隊順序） */
export function allSquads(board) {
  return (board?.fleets || []).flatMap(f => f.squads || [])
}

/**
 * 後端舊格式（沒有艦隊、人員只有 role）轉新格式；後端讀取時已經轉過，這裡是保險（直接改 board，回傳同一個）。
 */
export function normalizeBoard(board) {
  if (!board) return board
  if (!Array.isArray(board.fleets)) board.fleets = [{ id: 'f0', name: '艦隊 1', note: '', squads: board.squads || [] }]
  delete board.squads
  for (const f of board.fleets) {
    f.name = f.name || ''
    f.note = f.note || ''
    f.squads = f.squads || []
  }
  for (const s of allSquads(board)) {
    for (const p of squadPeople(s)) {
      if (!Array.isArray(p.roles)) p.roles = p.role ? [p.role] : []
      delete p.role
    }
  }
  return board
}

/** 表裡全部用過的 id */
function usedIds(board) {
  const ids = new Set()
  for (const f of board.fleets || []) ids.add(f.id)
  for (const s of allSquads(board)) {
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
  return { id: newId(board, 's'), name: `小隊 ${allSquads(board).length + 1}`, note: '', leader: null, ships: [], members: [] }
}

export function emptyFleet(board) {
  return { id: newId(board, 'f'), name: `艦隊 ${(board.fleets || []).length + 1}`, note: '', squads: [] }
}

/** 一個小隊的全部人員（船上＋不在船上） */
export function squadPeople(squad) {
  return [...(squad.ships || []).flatMap(v => v.crew || []), ...(squad.members || [])]
}

export function countPeople(board) {
  return allSquads(board).reduce((n, s) => n + squadPeople(s).length, 0)
}

export function countShips(board) {
  return allSquads(board).reduce((n, s) => n + (s.ships || []).length, 0)
}

/** 人員清單裡各職位的人數（兼職的每個職位都算一次）：{ 駕駛: 1, 砲手: 2 }，照 DEFAULT_ROLES 的順序，自填的排後面 */
export function roleCounts(people) {
  const m = new Map(DEFAULT_ROLES.map(r => [r, 0]))
  for (const p of people || []) for (const r of p.roles || []) m.set(r, (m.get(r) || 0) + 1)
  return Object.fromEntries([...m].filter(([, n]) => n > 0))
}

/** 「駕駛 1／砲手 2」 */
export function roleSummary(people) {
  return Object.entries(roleCounts(people)).map(([r, n]) => `${r} ${n}`).join('／')
}

/**
 * 艦隊統計（卡片標題列）：{ ships, people, roles, emptySeats, noPilot }
 * emptySeats：船的建議乘員（crew_max）減掉船上人數，加總（超員不抵）；noPilot：沒有人兼「駕駛」的船數
 */
export function fleetStats(fleet) {
  const squads = fleet?.squads || []
  const ships = squads.flatMap(s => s.ships || [])
  const people = squads.flatMap(squadPeople)
  return {
    squads: squads.length,
    ships: ships.length,
    people: people.length,
    roles: roleCounts(people),
    emptySeats: ships.reduce((n, v) => n + (v.crew_max ? Math.max(0, v.crew_max - (v.crew || []).length) : 0), 0),
    noPilot: ships.filter(v => !(v.crew || []).some(p => (p.roles || []).includes('駕駛'))).length,
  }
}

/** 切換人員的某個職位（兼職最多 MAX_ROLES 個，滿了就不加，回傳 false）。直接改 person。 */
export function toggleRole(person, role) {
  const roles = person.roles || (person.roles = [])
  const i = roles.indexOf(role)
  if (i >= 0) { roles.splice(i, 1); return true }
  if (roles.length >= MAX_ROLES) return false
  roles.push(role)
  return true
}

/** 同一個玩家在表裡出現兩次以上的 scid（兩處都標「重複」，不擋） */
export function duplicateScids(board) {
  const seen = new Map()
  for (const s of allSquads(board)) {
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
  allSquads(board).forEach((s, si) => {
    ;(s.ships || []).forEach(v => out.push({ key: `v:${v.id}`, label: `${s.name || `小隊 ${si + 1}`} › ${v.label || v.vehicle_name}` }))
    out.push({ key: `s:${s.id}`, label: `${s.name || `小隊 ${si + 1}`} › 不在船上` })
  })
  return out
}

/** 人員現在在哪（personTargets 的 key） */
export function personLocation(board, personId) {
  for (const s of allSquads(board)) {
    for (const v of s.ships || []) if ((v.crew || []).some(p => p.id === personId)) return `v:${v.id}`
    if ((s.members || []).some(p => p.id === personId)) return `s:${s.id}`
  }
  return ''
}

/** 把人員移到 target（personTargets 的 key），加在最後。直接改 board。 */
export function movePerson(board, personId, target) {
  let person = null
  let fromSquad = null
  const squads = allSquads(board)
  // 先確定目標在，再拿出來（目標不存在時不要把人弄丟）
  const [kind, id] = String(target || '').split(':')
  const exists = squads.some(s => (kind === 's' ? s.id === id : (s.ships || []).some(v => v.id === id)))
  if (!exists) return false
  for (const s of squads) {
    for (const v of s.ships || []) {
      const i = (v.crew || []).findIndex(p => p.id === personId)
      if (i >= 0) { person = v.crew.splice(i, 1)[0]; fromSquad = s }
    }
    const i = (s.members || []).findIndex(p => p.id === personId)
    if (i >= 0) { person = s.members.splice(i, 1)[0]; fromSquad = s }
  }
  if (!person) return false
  for (const s of squads) {
    const list = kind === 's' ? (s.id === id ? s.members : null) : (s.ships || []).find(v => v.id === id)?.crew
    if (!list) continue
    list.push(person)
    // 換到別的小隊就不再是原本小隊的隊長
    if (fromSquad && fromSquad !== s && fromSquad.leader === personId) fromSquad.leader = null
    return true
  }
  return false
}

/** 艦船可以移去的小隊：[{ key: 小隊 id, label: 艦隊 › 小隊 }] */
export function squadTargets(board) {
  return (board.fleets || []).flatMap(f => (f.squads || []).map(s => ({ key: s.id, label: `${f.name} › ${s.name}` })))
}

/** 艦船現在在哪個小隊（id） */
export function shipLocation(board, shipId) {
  return allSquads(board).find(s => (s.ships || []).some(v => v.id === shipId))?.id || ''
}

/** 把艦船（連同船上的人）移到另一個小隊，加在最後；船上的隊長跟著換小隊就不再是原小隊隊長。直接改 board。 */
export function moveShip(board, shipId, squadId) {
  const squads = allSquads(board)
  const to = squads.find(s => s.id === squadId)
  const from = squads.find(s => (s.ships || []).some(v => v.id === shipId))
  if (!to || !from || to === from) return false
  const i = from.ships.findIndex(v => v.id === shipId)
  const [ship] = from.ships.splice(i, 1)
  to.ships.push(ship)
  if (from.leader && (ship.crew || []).some(p => p.id === from.leader)) from.leader = null
  return true
}

/** 小隊現在在哪個艦隊（id） */
export function squadFleet(board, squadId) {
  return (board.fleets || []).find(f => (f.squads || []).some(s => s.id === squadId))?.id || ''
}

/** 把小隊移到另一個艦隊，加在最後。直接改 board。 */
export function moveSquad(board, squadId, fleetId) {
  const to = (board.fleets || []).find(f => f.id === fleetId)
  const from = (board.fleets || []).find(f => (f.squads || []).some(s => s.id === squadId))
  if (!to || !from || to === from) return false
  const i = from.squads.findIndex(s => s.id === squadId)
  to.squads.push(...from.squads.splice(i, 1))
  return true
}

/** 船的顯示名稱：識別名稱（船名） */
export function shipTitle(v) {
  return v.label ? `${v.label}（${v.vehicle_name}）` : v.vehicle_name || '未選船'
}

/** 存檔用：只留後端要的欄位 */
export function boardPayload(board) {
  const person = p => ({ id: p.id, scid: p.scid || null, name: p.name || '', roles: [...(p.roles || [])] })
  const squad = s => ({
    id: s.id, name: s.name || '', note: s.note || '', leader: s.leader || null,
    ships: (s.ships || []).map(v => ({ id: v.id, vehicle_id: v.vehicle_id, label: v.label || '', crew: (v.crew || []).map(person) })),
    members: (s.members || []).map(person),
  })
  return {
    title: board.title || '', event_at: board.event_at || '', note: board.note || '', rev: board.rev,
    fleets: (board.fleets || []).map(f => ({ id: f.id, name: f.name || '', note: f.note || '', squads: (f.squads || []).map(squad) })),
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
