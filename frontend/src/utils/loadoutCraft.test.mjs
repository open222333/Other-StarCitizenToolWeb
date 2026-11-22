// 配裝模擬的製作品質：node src/utils/loadoutCraft.test.mjs
import assert from 'node:assert/strict'
import { applyQuality, avgQuality, decodeQualities, encodeQualities, isDefault } from './loadoutCraft.js'

const lin = (key, lo, hi) => ({ key, type: 'linear', q_min: 0, q_max: 1000, at_min: lo, at_max: hi })
const slots = [
  { key: 'FRAME', modifiers: [lin('health_maxhealth', 0.9, 1.1)] },
  { key: 'EMITTER', modifiers: [lin('weapon_damage', 0.95, 1.05)] },
  { key: 'CORE', modifiers: [lin('weapon_damage', 0.95, 1.05)] },
]
const gun = { id: 'g', type: 'WeaponGun', hp: 1000, stats: { alpha: 100, dps: 200, sustained: 150, damage: { energy: 100 } } }

// 全部 Q500＝原本的數值
assert.deepEqual(applyQuality(gun, slots, {}).item, gun)
// Q1000：耐久 ×1.1、兩個部位的傷害倍率相乘 ×1.05²
const best = applyQuality(gun, slots, { FRAME: 1000, EMITTER: 1000, CORE: 1000 }).item
assert.equal(Math.round(best.hp), 1100)
assert.equal(Math.round(best.stats.alpha * 100) / 100, 110.25)
assert.equal(Math.round(best.stats.damage.energy * 100) / 100, 110.25)
assert.equal(gun.stats.alpha, 100, '原本的配件不會被改到')
// 發電機的 Power Pips 是加減值
const pp = { id: 'p', type: 'PowerPlant', stats: { power_gen: 16 } }
const pips = [{ key: 'A', modifiers: [{ key: 'itemresource_powergeneration', type: 'linear_integer_additive',
  segments: [{ q_min: 0, q_max: 399, at_start: -1, at_end: -1 }, { q_min: 400, q_max: 899, at_start: 0, at_end: 0 },
    { q_min: 900, q_max: 1000, at_start: 1, at_end: 1 }] }] }]
assert.equal(applyQuality(pp, pips, { A: 950 }).item.stats.power_gen, 17)
assert.equal(applyQuality(pp, pips, { A: 100 }).item.stats.power_gen, 15)
// 平均、網址
assert.equal(avgQuality(slots, { FRAME: 800 }), 600)
assert.equal(avgQuality(slots, null), 500, '沒設定＝全部 Q500')
assert.ok(isDefault({ A: 500 }) && !isDefault({ A: 501 }))
const enc = encodeQualities({ g: { FRAME: 800, EMITTER: 500 }, p: { A: 500 } })
assert.equal(enc, 'g:FRAME=800,EMITTER=500')
assert.deepEqual(decodeQualities(enc), { g: { FRAME: 800, EMITTER: 500 } })
assert.deepEqual(decodeQualities('x:A=5000;bad;y:'), { x: { A: 1000 } })
console.log('loadoutCraft ok')
