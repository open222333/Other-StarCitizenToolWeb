import test from 'node:test'
import assert from 'node:assert/strict'
import { groupRoleOptions, vehicleRoleGroup } from './vehicleRole.js'

test('角色分組：關鍵字、有「/」看第一段、Starter 跳過、對不到歸其他', () => {
  const g = r => vehicleRoleGroup(r).label
  assert.equal(g('Heavy Fighter'), '戰機')
  assert.equal(g('Heavy Fighter / Bomber'), '戰機')
  assert.equal(g('Light Freight / Medium Fighter'), '運輸')
  assert.equal(g('Starter / Light Mining'), '工業')
  assert.equal(g('Starter / Pathfinder'), '探索與科研')
  assert.equal(g('Stealth Bomber'), '轟炸與砲艇')
  assert.equal(g('Frigate'), '主力艦')
  assert.equal(g('Medical'), '支援')
  assert.equal(g('Racing'), '競速與觀光')
  assert.equal(g('Something New'), '其他')
})

test('groupRoleOptions：字串或物件都可以，依群組排序', () => {
  const out = groupRoleOptions(['Racing', { value: 'Light Fighter', label: '輕型戰機（Light Fighter）' }])
  assert.deepEqual(out.map(o => [o.value, o.group]), [['Light Fighter', '戰機'], ['Racing', '競速與觀光']])
})
