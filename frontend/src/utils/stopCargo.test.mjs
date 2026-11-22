import assert from 'node:assert/strict'
import { applyCargo, cargoFlow } from './stopCargo.js'
const r = applyCargo({ Agricium: 106 }, [{ action: 'unload', item: '農業礦（Agricium）', scu: 50 }])
assert.deepEqual(r.onboard, { Agricium: 56 }); assert.deepEqual(r.shorts, [])
const f = cargoFlow(['s', 'a'], { s: [{ action: 'load', item: 'Waste', scu: 700 }], a: [{ action: 'unload', item: 'waste', scu: 800 }] }, 696)
assert.equal(f.get('s').over, true); assert.deepEqual(f.get('a').shorts, ['Waste']); assert.equal(f.get('a').total, 0)
// 邊界（待辦 A5）：卸超過船上有的 → 記在 shorts、船上清空；同品名大小寫不同算同一種；剛好裝滿不算超過
const over = applyCargo({ Waste: 10 }, [{ action: 'unload', item: 'waste', scu: 15 }])
assert.deepEqual(over.onboard, {}); assert.deepEqual(over.shorts, ['Waste'])
assert.deepEqual(applyCargo({}, [{ action: 'load', item: 'Gold', scu: 5 }, { action: 'load', item: 'gold', scu: 3 }]).onboard, { Gold: 8 })
const full = cargoFlow(['a', 'b'], { a: [{ action: 'load', item: 'X', scu: 696 }], b: [{ action: 'unload', item: 'x', scu: 696 }] }, 696)
assert.equal(full.get('a').over, false); assert.equal(full.get('a').total, 696); assert.equal(full.get('b').total, 0)
console.log('stopCargo ok')
