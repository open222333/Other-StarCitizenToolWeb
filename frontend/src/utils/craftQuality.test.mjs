// node src/utils/craftQuality.test.mjs
import assert from 'node:assert/strict'
import { combine, fmtModifier, fmtPercent, modifierAt } from './craftQuality.js'

const dmg = { key: 'weapon_damage', name: 'Impact Force', type: 'linear', q_min: 0, q_max: 1000, at_min: 0.95, at_max: 1.05 }
const recoil = { key: 'weapon_recoil_kick', name: 'Recoil Kick', type: 'linear', q_min: 0, q_max: 1000, at_min: 1.2, at_max: 0.8 }
const pips = { key: 'pips', name: 'Power Pips', type: 'linear_integer_additive', at_min: null, at_max: null,
  segments: [{ q_min: 0, q_max: 499, at_start: -1, at_end: -1 }, { q_min: 500, q_max: 1000, at_start: 1, at_end: 1 }] }

assert.equal(modifierAt(dmg, 0), 0.95)
assert.equal(modifierAt(dmg, 1000), 1.05)
assert.ok(Math.abs(modifierAt(dmg, 500) - 1) < 1e-9)
assert.equal(modifierAt(dmg, 5000), 1.05, '超出範圍取端點')
assert.equal(modifierAt(pips, 100), -1)
assert.equal(modifierAt(pips, 800), 1)
assert.equal(modifierAt({ type: 'linear', at_min: null }, 1), null)

const rows = combine([
  { key: 'BARREL', modifiers: [dmg] },
  { key: 'FRAME', modifiers: [recoil, pips] },
  { key: 'STOCK', modifiers: [recoil] },
], { BARREL: 1000, FRAME: 1000, STOCK: 500 })
const byKey = Object.fromEntries(rows.map(r => [r.key, r]))
assert.ok(Math.abs(byKey.weapon_damage.value - 1.05) < 1e-9 && byKey.weapon_damage.better === true)
assert.ok(Math.abs(byKey.weapon_recoil_kick.value - 0.8) < 1e-9, '同屬性多個部位相乘：0.8 × 1.0')
assert.equal(byKey.weapon_recoil_kick.better, true, '後座力變小算變好')
assert.equal(byKey.pips.value, 1)
assert.equal(combine([{ key: 'A', modifiers: [dmg] }], {})[0].value.toFixed(3), '1.000', '沒指定品質用 500')

assert.equal(fmtModifier(1.05, false), '×1.05')
assert.equal(fmtModifier(-1, true), '-1')
assert.equal(fmtPercent(1.05), '+5.0%')
assert.equal(fmtPercent(0.8), '-20.0%')
console.log('craftQuality: all passed')
