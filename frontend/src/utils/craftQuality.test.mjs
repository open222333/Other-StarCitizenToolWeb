// node src/utils/craftQuality.test.mjs
import assert from 'node:assert/strict'
import { applyToBase, combine, requiredQuality, fmtModifier, fmtPercent, fmtStat, modifierAt, statKey } from './craftQuality.js'

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
assert.equal(statKey('Min Temp'), 'mintemp')
assert.equal(fmtStat(applyToBase(40, 1.15, false), '%'), '46%')
assert.equal(fmtStat(applyToBase(-70, 1.2, false), '°C'), '-84°C')
assert.equal(applyToBase(2, -1, true), 1)
assert.equal(applyToBase(null, 1.1, false), null)
assert.equal(fmtStat(26800, 'REM'), '26,800 REM')
{
  const slots = [{ key: 'frame', modifiers: [{ key: 'dm', name: 'Damage Mitigation', type: 'linear', q_min: 0, q_max: 1000, at_min: 0.85, at_max: 1.15 }] },
    { key: 'core', modifiers: [{ key: 'other', name: 'X', type: 'linear', q_min: 0, q_max: 1000, at_min: 1, at_max: 1 }] }]
  const r = requiredQuality(slots, { frame: 500, core: 500 }, 'dm', 1.1)
  assert.equal(r.quality, 834)   // 0.85 + 0.3 * q/1000 >= 1.1 → q >= 833.3
  assert.deepEqual(r.slotKeys, ['frame'])
  assert.equal(requiredQuality(slots, {}, 'dm', 0.8).quality, 0)
  const no = requiredQuality(slots, {}, 'dm', 1.2)
  assert.equal(no.reachable, false)
  assert.ok(Math.abs(no.best - 1.15) < 1e-9)
  // 越低越好的屬性（後座力 at_max < at_min）
  const rec = [{ key: 'b', modifiers: [{ key: 'r', name: 'Recoil', type: 'linear', q_min: 0, q_max: 1000, at_min: 1.2, at_max: 0.8 }] }]
  assert.equal(requiredQuality(rec, {}, 'r', 1.0).quality, 500)
  assert.equal(requiredQuality(rec, {}, 'nope', 1), null)
}
console.log('craftQuality: all passed')
