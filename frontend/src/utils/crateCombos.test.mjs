// node src/utils/crateCombos.test.mjs
import assert from 'node:assert/strict'
import { combos, minCounts, plan } from './crateCombos.js'

// 24 混進來時貪心法會錯：48 用 24×2 只要 2 個
assert.equal(minCounts(48, [32, 24, 8])[48], 2)
assert.equal(minCounts(7, [4, 2])[7], Infinity)

// 106 用全部尺寸：最少 32×3＋8＋2 = 5 個
let r = plan(106, [1, 2, 4, 8, 16, 24, 32])
assert.equal(r.exact, true)
assert.equal(r.targets[0].min, 5)
assert.deepEqual(r.targets[0].options[0].counts, { 32: 3, 24: 0, 16: 0, 8: 1, 4: 0, 2: 1, 1: 0 })

// 106 只用 16／8／4：湊不出來，給 104（少 2）與 108（多 2）
r = plan(106, [16, 8, 4])
assert.equal(r.exact, false)
assert.deepEqual(r.targets.map(t => [t.amount, t.diff, t.min]), [[104, -2, 7], [108, 2, 8]])
assert.deepEqual(r.targets[0].options[0].counts, { 16: 6, 8: 1, 4: 0 })

// 每組都剛好湊成目標、貨櫃數不超過上限、排序是少的在前
const list = combos(64, [32, 16, 8], 4)
assert.ok(list.every(c => Object.entries(c.counts).reduce((a, [s, n]) => a + s * n, 0) === 64 && c.total <= 4))
assert.deepEqual(list.map(c => c.total), [2, 3, 4, 4])

// 大數字不會卡住
const t0 = Date.now()
plan(9999, [1, 2, 4, 8, 16, 24, 32], { slack: 3 })
assert.ok(Date.now() - t0 < 2000)
assert.deepEqual(plan(0, [8]).targets, [])
console.log('crateCombos ok')
