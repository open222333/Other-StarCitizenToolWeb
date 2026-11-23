// 分頁開放狀態：node src/utils/playerTabs.test.mjs
import assert from 'node:assert/strict'
import { isTabClosed, openSubTabs } from './playerTabs.js'

const access = { news: 'closed', 'items.missions': 'closed', search: 'hidden' }
assert.equal(isTabClosed(access, 'news'), true)
assert.equal(isTabClosed(access, 'search'), false, '「預設不顯示」不算不開放')
assert.equal(isTabClosed(access, 'items'), false)
assert.equal(isTabClosed(access, 'items', 'missions'), true)
assert.equal(isTabClosed(access, 'items', 'data'), false)
assert.ok(!openSubTabs(access, 'items', []).some(s => s.key === 'missions'))
// 下層分頁全部不開放＝整個主分頁不開放
const routeOff = { 'route.plan': 'closed', 'route.contracts': 'closed' }
assert.equal(isTabClosed(routeOff, 'route'), true)
assert.deepEqual(openSubTabs(routeOff, 'route', []), [])
console.log('playerTabs ok')
