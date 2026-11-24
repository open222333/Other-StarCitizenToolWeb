// 電源分配不超出發電量：node src/utils/loadoutPower.test.mjs
import assert from 'node:assert/strict'
import { autoAllocate, consumerLoad, consumers, maxAllocate, setWithinGen, usedPower } from './loadoutPower.js'

const item = max => ({ stats: { power_use: [1, max], power_ranges: [] } })
const list = [
  { key: 'sh', kind: 'shield', min: 1, max: 3, item: item(3) },
  { key: 'w', kind: 'weapons', min: 0, max: 4, draw: 4, em: 0, coolant: 0 },
  { key: 'r', kind: 'radar', min: 1, max: 3, item: item(3) },
  { key: 'fc', kind: 'static', min: 0, max: 4, em: 0, coolant: 0 },
]
const gen = 10
// 全部開滿：依優先度開，總和不超過發電量（固定 4 → 護盾 3 → 武器 3，雷達放不下）
const m = maxAllocate(list, gen)
assert.ok(usedPower(list, m) <= gen)
assert.deepEqual(m, { sh: 3, w: 3, r: 0, fc: 4 })
// 手動點到超過：降到放得下的最大格數；連最小值都放不下就不動
assert.deepEqual(setWithinGen(list, m, 'r', 3, gen), m)
const lower = setWithinGen(list, m, 'w', 1, gen)
assert.equal(lower.w, 1)
assert.equal(setWithinGen(list, lower, 'r', 3, gen).r, 2)
// 自動分配：保留的格數加起來超過時從優先度低的扣
const a = autoAllocate(list, 6, { r: 3, sh: 3 })
assert.ok(usedPower(list, a) <= 6, JSON.stringify(a))
// 兩個護盾產生器合成一欄：格數相加，分到的格數依上限比例分給每一個
const sh = id => ({ id, type: 'Shield', stats: { power_use: [1, 3], power_ranges: [], em: 100, hp: 1000 } })
const items = { a: sh('a'), b: sh('b') }
const slots = [{ id: 'p1', item: 'a' }, { id: 'p2', item: 'b' }]
const cs = consumers({ shield_slots: 2, power: { groups: { Shield: { power: 6, em: 1, coolant: 1 } } } }, slots, id => items[id])
const shields = cs.filter(c => c.kind === 'shield')
assert.equal(shields.length, 1, '護盾只有一欄')
assert.ok(!cs.some(c => c.kind === 'static' && c.group === 'Shield'), '不會再用船的預設值多補一欄護盾')
assert.deepEqual([shields[0].min, shields[0].max], [2, 6])
assert.equal(consumerLoad(shields[0], 6).em, 200)
assert.equal(consumerLoad(shields[0], 3).power, 3)
// 雷達：不耗電的假雷達不列；遊戲順序 武器 → 推進器 → 護盾 → 量子 → 雷達 → 維生 → 冷卻
const it2 = { r: { id: 'r', type: 'Radar', stats: { power_use: [1, 5] } }, f: { id: 'f', type: 'Radar', stats: { power_use: [0, null] } },
  c: { id: 'c', type: 'Cooler', stats: { power_use: [1, 3] } }, s: sh('s'), g: { id: 'g', type: 'WeaponGun', stats: { power_use: [0, 1] } } }
const cs2 = consumers({ power: { groups: { FlightController: { power: 8 }, LifeSupportGenerator: { power: 2 } } } },
  ['c', 'r', 'f', 'f', 's', 'g'].map((id, i) => ({ id: `n${i}`, item: id })), id => it2[id])
assert.equal(cs2.filter(c => c.kind === 'radar').length, 1, '雷達只有一欄')
assert.deepEqual(cs2.map(c => c.kind === 'static' ? c.group : c.kind),
  ['weapons', 'FlightController', 'shield', 'radar', 'LifeSupportGenerator', 'cooler'])
console.log('loadoutPower ok')

// 單格武器關電：不算進武器電源池
{
  const gun = id => ({ id, type: 'WeaponGun', stats: { power_use: [0, 2], em: 10 } })
  const its = { g1: gun('g1'), g2: gun('g2') }
  const sl = [{ id: 'w1', item: 'g1' }, { id: 'w2', item: 'g2' }]
  const all = consumers({}, sl, id => its[id]).find(c => c.kind === 'weapons')
  assert.equal(all.draw, 4)
  const one = consumers({}, sl, id => its[id], 'scm', new Set(['w1'])).find(c => c.kind === 'weapons')
  assert.equal(one.draw, 2)
  assert.equal(consumers({}, sl, id => its[id], 'scm', new Set(['w1', 'w2'])).find(c => c.kind === 'weapons'), undefined)
}
