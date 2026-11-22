// 航線「總覽」的蛇形排列（純計算，RouteFlowView.vue 用；測試見 routeFlow.test.mjs，待辦 B4）。
//
// 橫向（horizontal）：一行放 cols 站，奇數行反過來（左右來回）；
// 直向（vertical）：一欄放 rows 站，奇數欄反過來（上下來回）。i 從 0 開始。

/** 第 i 站在第幾行／第幾欄（都從 0 開始） */
export function snakePos(i, { vertical = false, cols = 1, rows = 1 } = {}) {
  if (vertical) {
    const col = Math.floor(i / rows)
    const k = i % rows
    return { col, row: col % 2 === 0 ? k : rows - 1 - k }
  }
  const row = Math.floor(i / cols)
  const k = i % cols
  return { row, col: row % 2 === 0 ? k : cols - 1 - k }
}

/** 第 i 站跟上一站的方向：first＝第一站、r＝上一站在左（往右走）、l＝往左、d＝往下、u＝往上 */
export function snakeDir(i, opts) {
  if (i === 0) return 'first'
  const a = snakePos(i - 1, opts), b = snakePos(i, opts)
  if (a.row === b.row) return a.col < b.col ? 'r' : 'l'
  return a.row < b.row ? 'd' : 'u'
}

/** 換行（橫向）／換欄（直向）的那一站 */
export function isSnakeTurn(i, { vertical = false, cols = 1, rows = 1 } = {}) {
  return i > 0 && (vertical ? i % rows === 0 : i % cols === 0)
}
