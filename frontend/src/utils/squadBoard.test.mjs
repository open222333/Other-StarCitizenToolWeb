// 戰術小隊分配表：node src/utils/squadBoard.test.mjs
import assert from 'node:assert/strict'
import {
  allSquads, boardPayload, emptyFleet, emptySquad, fleetStats, movePerson, moveShip, moveSquad, newId, normalizeBoard,
  roleSummary, shipLocation, squadFleet, toggleRole,
} from './squadBoard.js'

const mk = () => normalizeBoard({
  title: 't', rev: 3,
  squads: [{ id: 's1', name: 'A', leader: 'm1', ships: [{ id: 'v1', vehicle_id: 'x', vehicle_name: 'Cutlass', crew_max: 3,
    crew: [{ id: 'm1', name: '甲', role: '駕駛' }, { id: 'm2', name: '乙', role: '' }] }], members: [{ id: 'm3', name: '丙', role: '陸戰' }] }],
})

// 舊格式 → 預設艦隊、role → roles
{
  const b = mk()
  assert.equal(b.squads, undefined)
  assert.equal(b.fleets.length, 1)
  assert.deepEqual(allSquads(b)[0].ships[0].crew.map(p => p.roles), [['駕駛'], []])
  assert.equal(allSquads(b)[0].members[0].role, undefined)
}
// id 不跟艦隊重複
{
  const b = mk()
  assert.notEqual(newId(b, 'f'), 'f0')
  const f = emptyFleet(b)
  b.fleets.push(f)
  f.squads.push(emptySquad(b))
  assert.equal(allSquads(b).length, 2)
  assert.equal(f.squads[0].name, '小隊 2')
}
// 兼職：最多 3 個
{
  const p = { roles: [] }
  for (const r of ['駕駛', '砲手', '陸戰']) assert.ok(toggleRole(p, r))
  assert.equal(toggleRole(p, '醫療'), false)
  assert.ok(toggleRole(p, '砲手'))
  assert.deepEqual(p.roles, ['駕駛', '陸戰'])
}
// 統計
{
  const b = mk()
  allSquads(b)[0].ships[0].crew[1].roles = ['砲手', '駕駛']
  const st = fleetStats(b.fleets[0])
  assert.deepEqual([st.squads, st.ships, st.people, st.emptySeats, st.noPilot], [1, 1, 3, 1, 0])
  assert.equal(roleSummary(allSquads(b)[0].ships[0].crew), '駕駛 2／砲手 1')
  allSquads(b)[0].ships[0].crew = []
  assert.equal(fleetStats(b.fleets[0]).noPilot, 1)
}
// 移動：船（連同隊長換小隊）、小隊、人員（目標不存在時不弄丟）
{
  const b = mk()
  const f2 = emptyFleet(b); b.fleets.push(f2)
  const s2 = emptySquad(b); f2.squads.push(s2)
  assert.ok(moveShip(b, 'v1', s2.id))
  assert.equal(shipLocation(b, 'v1'), s2.id)
  assert.equal(allSquads(b)[0].leader, null)
  assert.ok(moveSquad(b, 's1', f2.id))
  assert.equal(squadFleet(b, 's1'), f2.id)
  assert.equal(b.fleets[0].squads.length, 0)
  assert.equal(movePerson(b, 'm3', 'v:nope'), false)
  assert.equal(allSquads(b).find(s => s.id === 's1').members.length, 1)
  assert.ok(movePerson(b, 'm3', 'v:v1'))
  assert.equal(s2.ships[0].crew.length, 3)
}
// 存檔格式
{
  const p = boardPayload(mk())
  assert.deepEqual(Object.keys(p), ['title', 'event_at', 'note', 'rev', 'fleets'])
  assert.deepEqual(p.fleets[0].squads[0].ships[0].crew[0], { id: 'm1', scid: null, name: '甲', roles: ['駕駛'] })
}
console.log('squadBoard ok')
