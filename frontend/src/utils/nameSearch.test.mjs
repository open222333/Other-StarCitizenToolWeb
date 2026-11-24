// 名稱搜尋規則：node src/utils/nameSearch.test.mjs
import assert from 'node:assert/strict'
import { filterByName, matchStrict, nameTokens } from './nameSearch.js'

const list = [
  { name: 'Gamma LL', zh: '伽瑪 LL' },
  { name: 'Telescopic Collector', zh: '伸縮收集器' },
  { name: 'Delta LL', zh: '德爾塔 LL' },
  { name: 'CarinitePure', zh: '純卡利石' },
]
const f = r => [r.name, r.zh]
const names = (q) => filterByName(list, q, f).rows.map(r => r.name)

assert.deepEqual(nameTokens('  "Gamma  ll gamma '), ['gamma', 'll'])
assert.deepEqual(names('gamma ll'), ['Gamma LL'])
assert.deepEqual(names('ll gamma'), ['Gamma LL'])
// 字首：ll 不會對到 Collector 中間的 ll
assert.deepEqual(names('ll'), ['Gamma LL', 'Delta LL'])
// 中文任意位置
assert.deepEqual(names('卡利'), ['CarinitePure'])
// 嚴格找不到才放寬：ollect 不是字首
const r = filterByName(list, 'ollect', f)
assert.equal(r.match, 'loose')
assert.deepEqual(r.rows.map(x => x.name), ['Telescopic Collector'])
// 底線分段的代碼也比字首
assert.ok(matchStrict(['COOL_AEGS_S01_Bracer'], ['bracer']))
assert.equal(filterByName(list, '', f).rows, list)
console.log('nameSearch ok')
