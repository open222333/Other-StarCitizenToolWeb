import test from 'node:test'
import assert from 'node:assert/strict'
import { capSeconds } from './loadoutCalc.js'

test('capSeconds：乘上船的彈藥容量加成', () => {
  const s = { cap_load: 80, cap_regen: 10, rpm: 1600, cap_fire_s: 3, cap_recharge_s: 8 }
  assert.deepEqual(capSeconds(s, null), { fire: 3, recharge: 8 })
  assert.deepEqual(capSeconds(s, { ammo: 9, regen: 1 }), { fire: 27, recharge: 72 })
  assert.deepEqual(capSeconds(s, { ammo: 6, regen: 1.9 }), { fire: 18, recharge: 25.3 })
})

test('capSeconds：舊資料沒有原始容量，退回後端算好的秒數', () => {
  assert.deepEqual(capSeconds({ cap_fire_s: 3, cap_recharge_s: 8 }, { ammo: 9, regen: 1 }), { fire: 3, recharge: 8 })
  assert.deepEqual(capSeconds({}, null), { fire: null, recharge: null })
})
