import test from 'node:test'
import assert from 'node:assert/strict'
import { componentColumns, visibleColumns } from './componentColumns.js'

const shield = { name: 'FR-66', size: 2, hp: 2000, stats: { hp: 9000, regen: 500, absorption: { physical: [0, 0.45] }, power_use: [1, 4], em: 2060 } }

test('護盾：專屬參數在前，護盾 HP 跟耐久分兩欄，沒有值的欄位不顯示', () => {
  const cols = componentColumns('Shield')
  const keys = cols.map(c => c.key)
  assert.ok(keys.indexOf('hp') < keys.indexOf('power_max'))
  assert.ok(keys.includes('durability'))
  const vis = visibleColumns(cols, [shield]).map(c => c.key)
  assert.deepEqual(vis, ['hp', 'regen', 'abs_physical', 'power_min', 'power_max', 'em', 'durability'])
  const abs = cols.find(c => c.key === 'abs_physical')
  assert.equal(abs.fmt(abs.get(shield), shield), '45%')
  assert.equal(cols.find(c => c.key === 'durability').get(shield), 2000)
})

test('發電機：發電放最前面、不重複；沒專屬參數的種類只有共用參數', () => {
  const keys = componentColumns('PowerPlant').map(c => c.key)
  assert.equal(keys[0], 'power_gen')
  assert.equal(keys.filter(k => k === 'power_gen').length, 1)
  assert.equal(componentColumns('TractorBeam')[0].key, 'power_gen')
})

test('武器：傷害類型照最大的排序、顯示各類型', () => {
  const gun = { stats: { damage: { physical: 12, energy: 30 } } }
  const c = componentColumns('WeaponGun').find(x => x.key === 'damage')
  assert.equal(c.get(gun), 'energy')
  assert.equal(c.fmt(c.get(gun), gun), '物理 12／能量 30')
})
