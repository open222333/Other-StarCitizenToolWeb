// 新聞日期篩選：node src/utils/newsDate.test.mjs
import assert from 'node:assert/strict'
import { dateRange } from './newsDate.js'

const now = new Date(2026, 10, 24, 15, 30)   // 本地時間 11/24 15:30
const mid = (d) => new Date(2026, 10, d).toISOString()
assert.deepEqual(dateRange('today', now), { since: mid(24) })
assert.deepEqual(dateRange('yesterday', now), { since: mid(23), until: mid(24) })
assert.deepEqual(dateRange('week', now), { since: mid(18) })
assert.deepEqual(dateRange('', now), {})
// 跨月
assert.deepEqual(dateRange('yesterday', new Date(2026, 11, 1, 1)), { since: new Date(2026, 10, 30).toISOString(), until: new Date(2026, 11, 1).toISOString() })
console.log('news ok')
