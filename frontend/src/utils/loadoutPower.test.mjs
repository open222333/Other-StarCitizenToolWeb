// 電源分配不超出發電量：node src/utils/loadoutPower.test.mjs
import assert from 'node:assert/strict'
import { autoAllocate, maxAllocate, setWithinGen, usedPower } from './loadoutPower.js'

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
console.log('loadoutPower ok')
