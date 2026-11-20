// 貨櫃組合試算（玩家頁「工具箱 › 貨櫃試算」 components/CrateCalculator.vue）：
// 一個總量（SCU）要用哪幾種標準貨櫃湊、各幾個。只算數量，不管船的網格擺不擺得下（那是「貨艙網格」）。
//
//  - minCounts：每個量最少要幾個貨櫃（動態規劃，sizes 任意組合都對；24 SCU 混進來時貪心法會錯）
//  - combos：剛好湊成某個量、而且貨櫃數不超過「最少＋slack」的所有組合（大貨櫃多的排前面）
//  - plan：剛好湊得出來就給組合；湊不出來（例如 106 只用 16／8／4）就給最接近的下限、上限各自的組合

/** v＝0..max 各自最少要幾個貨櫃；湊不出來是 Infinity */
export function minCounts(max, sizes) {
  const dp = new Array(max + 1).fill(Infinity)
  dp[0] = 0
  for (let v = 1; v <= max; v += 1) {
    for (const s of sizes) {
      if (s <= v && dp[v - s] + 1 < dp[v]) dp[v] = dp[v - s] + 1
    }
  }
  return dp
}

/**
 * 剛好湊成 target 的組合：[{counts: {size: n}, total}]，貨櫃數 ≤ limit。
 * 大的尺寸先決定，剩下的量至少還要 ceil(剩下 / 目前最大尺寸) 個，超過 limit 就不往下找。
 * maxResults：最多回幾組；maxSteps：搜尋步數上限（極端輸入時不讓瀏覽器卡住）。
 */
export function combos(target, sizes, limit, { maxResults = 50, maxSteps = 200000 } = {}) {
  const desc = [...new Set(sizes)].filter(s => s > 0).sort((a, b) => b - a)
  const out = []
  const counts = new Array(desc.length).fill(0)
  let steps = 0
  function walk(i, rest, used) {
    if (out.length >= maxResults || steps > maxSteps) return
    steps += 1
    if (rest === 0) {
      out.push({ counts: Object.fromEntries(desc.map((s, k) => [s, counts[k]])), total: used })
      return
    }
    if (i >= desc.length) return
    const s = desc[i]
    if (used + Math.ceil(rest / s) > limit) return
    if (i === desc.length - 1) {
      if (rest % s === 0) {
        counts[i] = rest / s
        walk(i + 1, 0, used + counts[i])
        counts[i] = 0
      }
      return
    }
    for (let n = Math.min(Math.floor(rest / s), limit - used); n >= 0; n -= 1) {
      counts[i] = n
      walk(i + 1, rest - n * s, used + n)
    }
    counts[i] = 0
  }
  walk(0, target, 0)
  // 貨櫃少的在前；一樣多時大貨櫃多的在前
  out.sort((a, b) => a.total - b.total
    || desc.reduce((r, s) => r || (b.counts[s] - a.counts[s]), 0))
  return out
}

/**
 * 試算：total（SCU）、sizes（可用的貨櫃尺寸）、slack（比最少多幾個以內的組合也列出來）。
 * 回傳 {exact: boolean, targets: [{amount, diff, min, options}]}：
 *   剛好湊得出來 → targets 只有一筆（diff 0）；湊不出來 → 往下最接近的（diff < 0）與往上最接近的（diff > 0）。
 */
export function plan(total, sizes, { slack = 2, maxShown = 10 } = {}) {
  const list = [...new Set(sizes)].filter(s => Number.isInteger(s) && s > 0)
  if (!(total > 0) || !list.length) return { exact: false, targets: [] }
  const big = Math.max(...list)
  const dp = minCounts(total + big, list)
  const make = amount => ({
    amount, diff: amount - total, min: dp[amount],
    options: combos(amount, list, dp[amount] + slack).slice(0, maxShown),
  })
  if (Number.isFinite(dp[total])) return { exact: true, targets: [make(total)] }
  const targets = []
  for (let v = total - 1; v > 0; v -= 1) if (Number.isFinite(dp[v])) { targets.push(make(v)); break }
  for (let v = total + 1; v <= total + big; v += 1) if (Number.isFinite(dp[v])) { targets.push(make(v)); break }
  return { exact: false, targets }
}

/**
 * 一個量用「最大到 maxSize」的標準貨櫃拆，最少個數的拆法：{size: n}（大到小）。
 * 標準貨櫃 1／2／4／8／16／32 都是 2 的次方，大的先放（貪心）就是最少；
 * sizes 給的不是這種組合時改用動態規劃（plan）。
 */
export function splitCrates(total, maxSize = 32, sizes = [1, 2, 4, 8, 16, 32]) {
  const n = Math.max(0, Math.round(Number(total) || 0))
  const use = sizes.filter(s => s <= maxSize).sort((a, b) => b - a)
  if (!n || !use.length) return {}
  const pow2 = use.every(s => (s & (s - 1)) === 0) && use.includes(1)
  if (!pow2) {
    const best = plan(n, use).targets[0]?.options[0]?.counts || {}
    return Object.fromEntries(Object.entries(best).filter(([, c]) => c))
  }
  const out = {}
  let rest = n
  for (const s of use) {
    const c = Math.floor(rest / s)
    if (c) { out[s] = c; rest -= c * s }
  }
  return out
}

/** splitCrates 的結果 → 「32×3、8×1」 */
export const cratesText = counts => Object.entries(counts || {})
  .sort((a, b) => b[0] - a[0]).map(([s, c]) => `${s}×${c}`).join('、')
