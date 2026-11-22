// 航線總覽蛇形排列：node src/utils/routeFlow.test.mjs
import assert from 'node:assert/strict'
import { isSnakeTurn, snakeDir, snakePos } from './routeFlow.js'

// 橫向 3 欄：0 1 2 / 5 4 3 / 6 …
const h = { cols: 3 }
assert.deepEqual([0, 1, 2, 3, 4, 5, 6].map(i => snakePos(i, h)), [
  { row: 0, col: 0 }, { row: 0, col: 1 }, { row: 0, col: 2 },
  { row: 1, col: 2 }, { row: 1, col: 1 }, { row: 1, col: 0 }, { row: 2, col: 0 }])
assert.deepEqual([0, 1, 2, 3, 4, 5, 6].map(i => snakeDir(i, h)), ['first', 'r', 'r', 'd', 'l', 'l', 'd'])
assert.deepEqual([0, 1, 2, 3, 4, 5, 6].map(i => isSnakeTurn(i, h)), [false, false, false, true, false, false, true])
// 直向 2 列：0 3 4 / 1 2 5
const v = { vertical: true, rows: 2 }
assert.deepEqual([0, 1, 2, 3, 4].map(i => snakePos(i, v)), [
  { col: 0, row: 0 }, { col: 0, row: 1 }, { col: 1, row: 1 }, { col: 1, row: 0 }, { col: 2, row: 0 }])
assert.deepEqual([0, 1, 2, 3, 4].map(i => snakeDir(i, v)), ['first', 'd', 'r', 'u', 'r'])
assert.deepEqual([1, 2, 4].map(i => isSnakeTurn(i, v)), [false, true, true])
// 一欄（窄螢幕）：一直往下
assert.deepEqual([1, 2].map(i => snakeDir(i, { cols: 1 })), ['d', 'd'])
console.log('routeFlow ok')
