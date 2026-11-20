import assert from 'node:assert/strict'
import { applyCargo, cargoFlow } from './stopCargo.js'
const r = applyCargo({ Agricium: 106 }, [{ action: 'unload', item: '農業礦（Agricium）', scu: 50 }])
assert.deepEqual(r.onboard, { Agricium: 56 }); assert.deepEqual(r.shorts, [])
const f = cargoFlow(['s', 'a'], { s: [{ action: 'load', item: 'Waste', scu: 700 }], a: [{ action: 'unload', item: 'waste', scu: 800 }] }, 696)
assert.equal(f.get('s').over, true); assert.deepEqual(f.get('a').shorts, ['Waste']); assert.equal(f.get('a').total, 0)
console.log('stopCargo ok')
