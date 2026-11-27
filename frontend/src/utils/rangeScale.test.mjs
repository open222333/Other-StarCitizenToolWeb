import test from 'node:test'
import assert from 'node:assert/strict'
import { SLIDER_STEPS, fromPos, inRange, niceRound, rangeActive, toPos } from './rangeScale.js'

test('對數刻度：兩端對到 0 與最大值，中間取好看的整數', () => {
  assert.equal(toPos(0, 5000), 0)
  assert.equal(toPos(5000, 5000), SLIDER_STEPS)
  assert.equal(fromPos(SLIDER_STEPS, 5000), 5000)
  assert.equal(fromPos(0, 5000), 0)
  const mid = fromPos(SLIDER_STEPS / 2, 1e8)
  assert.ok(mid > 5000 && mid < 20000, `${mid}`)
  assert.equal(niceRound(87654), 88000)
  assert.equal(niceRound(7.4), 7)
})

test('範圍判斷：空的一邊不限、有設範圍時沒有值的不算', () => {
  assert.equal(rangeActive({ min: '', max: '' }), false)
  assert.equal(inRange(null, { min: '', max: '' }), true)
  assert.equal(inRange(null, { min: 10, max: '' }), false)
  assert.equal(inRange(50, { min: 10, max: 100 }), true)
  assert.equal(inRange(150, { min: '', max: 100 }), false)
})
