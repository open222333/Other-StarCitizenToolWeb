// 礦物的「自己的」單顆 RS（雷達截面訊號值）。
//
// 礦物本身沒有 RS——船艦掃描到的是岩石（礦床），RS 存在礦床上
// （mining_deposit_master.signature）。一種礦物的 RS 取「跟它同名的礦床」：
// 例如礦物 Hephaestanite (R) ↔ 礦床 Hephaestanite (R)。
//
// 但上游有些礦物跟它的礦床名稱寫法不一樣：
//   - 礦物 Stileron (Ore)  ↔ 礦床 Stileron
//   - 礦物 Raw Ouratite    ↔ 礦床 Ouratite
// 只比對完全同名的話這些會查不到 RS。所以先找完全同名的；找不到才把
// (Ore)／(Raw)／(Pure)／(R) 後綴、"Raw " 前綴拿掉再比一次。
// 不直接一律用去後綴的比法：Carinite 和 Carinite (Pure) 是兩種礦物、各有自己的
// 礦床，一律去後綴會把 Carinite 的 4000 也算到 Carinite (Pure) 頭上。
//
// 後台礦物資料庫（views/MiningView.vue）與玩家頁礦物分頁（components/MiningLookup.vue）
// 共用這一份，兩邊才不會一邊有值一邊沒有。

const SUFFIX = /\s*\((ore|raw|pure|r)\)\s*$/i
const RAW_PREFIX = /^raw\s+/i

const lower = (s) => (s || '').trim().toLowerCase()

export function mineralBaseName(name) {
  return lower(name).replace(SUFFIX, '').replace(RAW_PREFIX, '').trim()
}

/**
 * @param {string} mineralName  礦物英文名（parts[].resource_name）
 * @param {Array<{deposit_name: string, signature: number, tier?: string}>} deposits
 *        含這種礦物的礦床
 * @returns {Array<{signature: number, tier: string|null}>} 依 RS 由小到大、依值去重；
 *        RS 為 0／空的（FPS 徒手採礦用）排除
 */
export function ownSignatures(mineralName, deposits) {
  const withSig = (deposits || []).filter(d => d && d.signature)
  const exact = lower(mineralName)
  let own = withSig.filter(d => lower(d.deposit_name) === exact)
  if (!own.length) {
    const base = mineralBaseName(mineralName)
    own = base ? withSig.filter(d => mineralBaseName(d.deposit_name) === base) : []
  }
  const bySig = new Map()
  for (const d of own) {
    if (!bySig.has(d.signature)) bySig.set(d.signature, { signature: d.signature, tier: d.tier ?? null })
  }
  return [...bySig.values()].sort((a, b) => a.signature - b.signature)
}
