/**
 * craftCalc 的測試。用 node 內建的 assert 直接跑，不引入測試框架 ——
 * 前端目前沒有 test runner，而這個檔案是整個試算功能唯一「算錯就會誤導
 * 使用者」的地方，值得有測試守著。
 *
 *   cd frontend && npm run test:calc
 */
import assert from 'node:assert/strict'
import {
  normalizeIngredients, calcCraft, stockToHaveMap, craftTimeLabel, toAmount,
  UNIT_COUNT, UNIT_SCU,
} from './craftCalc.js'

let n = 0
const t = (name, fn) => { fn(); n++; }

// ── normalizeIngredients ──
t('個數與 SCU 兩種單位都能辨識', () => {
  const rows = normalizeIngredients({ ingredients: [
    { name: 'Laser Core', item_uuid: 'u1', quantity: 4 },
    { name: 'Quantainium', resource_type_uuid: 'r1', quantity_scu: 2.5 },
  ]})
  assert.equal(rows[0].unit, UNIT_COUNT); assert.equal(rows[0].need, 4)
  assert.equal(rows[0].canPrefill, true)
  assert.equal(rows[1].unit, UNIT_SCU);   assert.equal(rows[1].need, 2.5)
  assert.equal(rows[1].canPrefill, false)  // 沒有 item_uuid → 庫存對不起來
})

t('兩個數量欄位都 null → 需求未知，不能當成 0', () => {
  const [row] = normalizeIngredients({ ingredients: [{ name: '?', quantity: null, quantity_scu: null }] })
  assert.equal(row.need, null)
  assert.equal(row.unit, null)
})

t('quantity 是 0 或負數視為資料有問題', () => {
  const rows = normalizeIngredients({ ingredients: [
    { name: 'a', quantity: 0 }, { name: 'b', quantity: -3 },
  ]})
  assert.equal(rows[0].need, null); assert.equal(rows[1].need, null)
})

t('沒有 ingredients 不會爆', () => {
  assert.deepEqual(normalizeIngredients(null), [])
  assert.deepEqual(normalizeIngredients({}), [])
})

t('key 在沒有任何 uuid 時仍然唯一', () => {
  const rows = normalizeIngredients({ ingredients: [{ name: '鐵' }, { name: '鐵' }] })
  assert.notEqual(rows[0].key, rows[1].key)
})

// ── calcCraft 核心 ──
const recipe = normalizeIngredients({ ingredients: [
  { name: 'A', item_uuid: 'a', quantity: 2 },
  { name: 'B', item_uuid: 'b', quantity: 5 },
]})

t('取各材料可做數量的最小值', () => {
  const out = calcCraft(recipe, { a: 10, b: 12 })   // 5 個 vs 2 個
  assert.equal(out.maxCraftable, 2)
  assert.deepEqual(out.bottlenecks, ['b'])
  assert.equal(out.reliable, true)
})

t('材料不足時是 0，不是負數', () => {
  assert.equal(calcCraft(recipe, { a: 1, b: 0 }).maxCraftable, 0)
})

t('沒填數量當成 0', () => {
  assert.equal(calcCraft(recipe, {}).maxCraftable, 0)
})

t('剩料與消耗量', () => {
  const out = calcCraft(recipe, { a: 11, b: 12 })  // 可做 2
  const a = out.rows.find(r => r.key === 'a')
  assert.equal(out.maxCraftable, 2)
  assert.equal(a.used, 4)
  assert.equal(a.leftover, 11 - 4)
})

t('兩個材料同時是瓶頸', () => {
  const out = calcCraft(recipe, { a: 4, b: 10 })    // 兩邊都剛好 2
  assert.deepEqual(out.bottlenecks.sort(), ['a', 'b'])
})

t('需求未知的材料不參與瓶頸，但會標記結果不可靠', () => {
  const rows = normalizeIngredients({ ingredients: [
    { name: 'A', item_uuid: 'a', quantity: 2 },
    { name: '未知', item_uuid: 'x' },
  ]})
  const out = calcCraft(rows, { a: 10, x: 0 })
  assert.equal(out.maxCraftable, 5)      // 未知那列沒有把結果壓成 0
  assert.equal(out.unknownCount, 1)
  assert.equal(out.reliable, false)
})

t('全部需求未知 → maxCraftable 為 null（不是 0 也不是 Infinity）', () => {
  const rows = normalizeIngredients({ ingredients: [{ name: '?' }] })
  const out = calcCraft(rows, {})
  assert.equal(out.maxCraftable, null)
  assert.deepEqual(out.bottlenecks, [])
  assert.equal(out.reliable, false)
})

t('小數 SCU 需求用 floor', () => {
  const rows = normalizeIngredients({ ingredients: [{ name: 'ore', resource_type_uuid: 'r', quantity_scu: 1.5 }] })
  assert.equal(calcCraft(rows, { r: 4 }).maxCraftable, 2)   // 4 / 1.5 = 2.67 → 2
})

// ── 目標數量與缺料 ──
t('目標數量算出每項還缺多少', () => {
  const out = calcCraft(recipe, { a: 4, b: 5 }, 3)
  assert.equal(out.target, 3)
  assert.equal(out.targetReachable, false)
  const missing = Object.fromEntries(out.missing.map(r => [r.key, r.shortfall]))
  assert.deepEqual(missing, { a: 2, b: 10 })   // 需要 6/15，有 4/5
})

t('目標達得到時缺料清單是空的', () => {
  const out = calcCraft(recipe, { a: 100, b: 100 }, 3)
  assert.equal(out.targetReachable, true)
  assert.deepEqual(out.missing, [])
})

t('沒填目標就不算缺料', () => {
  const out = calcCraft(recipe, { a: 0, b: 0 })
  assert.equal(out.targetReachable, null)
  assert.deepEqual(out.missing, [])
})

t('目標是小數或負數會被正規化', () => {
  assert.equal(calcCraft(recipe, {}, 2.9).target, 2)
  assert.equal(calcCraft(recipe, {}, -5).target, 0)
})

// ── 輸入清理 ──
t('toAmount 擋掉垃圾輸入', () => {
  assert.equal(toAmount(''), 0)
  assert.equal(toAmount(null), 0)
  assert.equal(toAmount('abc'), 0)
  assert.equal(toAmount(-3), 0)
  assert.equal(toAmount('7'), 7)
  assert.equal(toAmount(Infinity), 0)
})

// ── 從庫存帶入 ──
t('同一物品跨地點的庫存要加總', () => {
  const rows = normalizeIngredients({ ingredients: [{ name: 'A', item_uuid: 'a', quantity: 2 }] })
  const have = stockToHaveMap(rows, [
    { item_id: 'a', quantity: 3, total_scu: 0.3 },
    { item_id: 'a', quantity: 4, total_scu: 0.4 },
    { item_id: 'zzz', quantity: 99 },
  ])
  assert.equal(have.a, 7)
})

t('SCU 單位的材料用 total_scu 帶入', () => {
  const rows = normalizeIngredients({ ingredients: [{ name: 'ore', item_uuid: 'o', quantity_scu: 1 }] })
  const have = stockToHaveMap(rows, [{ item_id: 'o', quantity: 100, total_scu: 12.5 }])
  assert.equal(have.o, 12.5)
})

t('庫存沒有的材料不會被填成 0（保留使用者自己填的值）', () => {
  const rows = normalizeIngredients({ ingredients: [{ name: 'A', item_uuid: 'a', quantity: 2 }] })
  assert.deepEqual(stockToHaveMap(rows, []), {})
})

t('沒有 item_uuid 的原料不會亂對', () => {
  const rows = normalizeIngredients({ ingredients: [{ name: 'ore', resource_type_uuid: 'r', quantity_scu: 1 }] })
  assert.deepEqual(stockToHaveMap(rows, [{ item_id: 'r', quantity: 5 }]), {})
})

// ── 製造時間 ──
t('製造時間可讀化', () => {
  assert.equal(craftTimeLabel(3600, 2), '2 小時')
  assert.equal(craftTimeLabel(90, 1), '1 分 30 秒')
  assert.equal(craftTimeLabel(45, 1), '45 秒')
  assert.equal(craftTimeLabel(86400 + 3600, 1), '1 天 1 小時')
  assert.equal(craftTimeLabel(0, 5), '')
  assert.equal(craftTimeLabel(null, 5), '')
  assert.equal(craftTimeLabel(3600, 0), '')
})

console.log(`craftCalc: ${n} 項全部通過`)
