// 貨艙網格（玩家頁「貨艙網格」分頁 components/CargoLoader.vue；航線選船時的 8／16／32 SCU 最大量）：把標準貨櫃擺進船的貨物網格。
//
// 網格資料來自 sc-cargo.space（後端 GET /starmap/nav/cargo-grids）：每格有位置 x／y／z 與
// 寬（x）、高（y）、長（z），單位都是 1 SCU 的邊長；max_size／min_size 是這格能放的貨櫃大小限制。
//
// 擺法（啟發式，不保證最佳）：大的先放；每個貨櫃依網格順序找第一個放得下的位置（由下往上、由前往後、
// 由左往右），可以水平轉 90 度；不是放在地板上就要整個底面都有東西撐著。

/** 貨櫃尺寸（SCU → 寬 x、高 y、長 z） */
export const CONTAINERS = {
  1: { w: 1, h: 1, l: 1 },
  2: { w: 1, h: 1, l: 2 },
  4: { w: 2, h: 1, l: 2 },
  8: { w: 2, h: 2, l: 2 },
  16: { w: 2, h: 2, l: 4 },
  24: { w: 2, h: 2, l: 6 },
  32: { w: 2, h: 2, l: 8 },
}
export const SIZES = [1, 2, 4, 8, 16, 24, 32]
const DESC = [...SIZES].reverse()

function makeSpace(g) {
  const W = Math.round(g.width), H = Math.round(g.height), L = Math.round(g.length)
  return { g, W, H, L, cells: new Uint8Array(Math.max(0, W * H * L)) }
}
const idx = (s, x, y, z) => (x * s.H + y) * s.L + z

function allowed(g, size) {
  if (g.max_size && size > g.max_size) return false
  if (g.min_size && size < g.min_size) return false
  return true
}

function fits(s, x, y, z, d) {
  if (x + d.w > s.W || y + d.h > s.H || z + d.l > s.L) return false
  for (let dx = 0; dx < d.w; dx++) {
    for (let dy = 0; dy < d.h; dy++) {
      for (let dz = 0; dz < d.l; dz++) if (s.cells[idx(s, x + dx, y + dy, z + dz)]) return false
    }
  }
  if (y > 0) {   // 要整個底面都有東西撐著
    for (let dx = 0; dx < d.w; dx++) {
      for (let dz = 0; dz < d.l; dz++) if (!s.cells[idx(s, x + dx, y - 1, z + dz)]) return false
    }
  }
  return true
}

function mark(s, x, y, z, d) {
  for (let dx = 0; dx < d.w; dx++) {
    for (let dy = 0; dy < d.h; dy++) {
      for (let dz = 0; dz < d.l; dz++) s.cells[idx(s, x + dx, y + dy, z + dz)] = 1
    }
  }
}

/** 找一個放得下這個大小貨櫃的位置並放進去 → 擺好的貨櫃，或 null */
function place(spaces, size) {
  const base = CONTAINERS[size]
  const dims = base.w === base.l ? [base] : [base, { w: base.l, h: base.h, l: base.w }]
  for (const s of spaces) {
    if (!allowed(s.g, size)) continue
    for (let y = 0; y < s.H; y++) {
      for (let z = 0; z < s.L; z++) {
        for (let x = 0; x < s.W; x++) {
          for (const d of dims) {
            if (fits(s, x, y, z, d)) {
              mark(s, x, y, z, d)
              return { size, x: s.g.x + x, y: s.g.y + y, z: s.g.z + z, w: d.w, h: d.h, l: d.l,
                unsecured: !!s.g.unsecured }
            }
          }
        }
      }
    }
  }
  return null
}

/**
 * 依數量擺貨櫃。counts：{ SCU 大小: 個數 } → { boxes: [擺好的貨櫃], left: { 大小: 放不下的個數 }, scu }
 */
export function packCounts(grids, counts) {
  const spaces = (grids || []).map(makeSpace)
  const boxes = [], left = {}
  for (const size of DESC) {
    const n = Math.max(0, Math.floor(Number(counts?.[size]) || 0))
    for (let i = 0; i < n; i++) {
      const b = place(spaces, size)
      if (b) boxes.push(b)
      else left[size] = (left[size] || 0) + 1
    }
  }
  return { boxes, left, scu: boxes.reduce((a, b) => a + b.size, 0) }
}

/**
 * 自動裝滿：大的貨櫃能放就放，放不下再換小的。maxSize 限制最大用到幾 SCU 的貨櫃。
 * → { counts: { 大小: 個數 }, ...packCounts 的結果 }
 */
export function autoFill(grids, maxSize = 32) {
  const spaces = (grids || []).map(makeSpace)
  const boxes = [], counts = {}
  for (const size of DESC) {
    if (size > maxSize) continue
    for (;;) {
      const b = place(spaces, size)
      if (!b) break
      boxes.push(b)
      counts[size] = (counts[size] || 0) + 1
    }
  }
  return { counts, boxes, left: {}, scu: boxes.reduce((a, b) => a + b.size, 0) }
}

/** 只放某一種大小的貨櫃，最多放得下幾個 */
export function maxOf(grids, size) {
  const spaces = (grids || []).map(makeSpace)
  let n = 0
  while (place(spaces, size)) n++
  return n
}

/** 網格的總容量（SCU） */
export const gridCapacity = grids => (grids || []).reduce((a, g) => a + g.width * g.height * g.length, 0)
