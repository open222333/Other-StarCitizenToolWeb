// 航線「貨物規劃」（航段表每一站的裝／卸貨；RouteLegsTable.vue、StopCargoEditor.vue）：
// 每一站一串 [{ key, action: 'load'|'unload', item, scu, max }]，依航線順序累加出每站抵達／離開時貨艙裡有什麼。
// 貨物名稱不分大小寫、前後空白，「中文（英文）」跟英文算同一種（顯示用第一次出現的寫法）。純前端，不送後端。

let seq = 0
/** 一筆裝卸貨；max＝最大貨櫃（拆貨櫃用，預設 32 SCU） */
export function newCargoEntry({ action = 'load', item = '', scu = null, max = 32 } = {}) {
  return { key: `c${Date.now().toString(36)}${(seq += 1)}`, action, item, scu, max: max || 32 }
}

// 比對用：「農業礦（Agricium）」跟「Agricium」算同一種（取最後括號裡的英文）
function keyOf(name) {
  const t = (name || '').trim()
  const m = t.match(/[（(]([^（）()]+)[）)]$/)
  return (m ? m[1] : t).trim().toLowerCase()
}

/**
 * 艙內 onboard（{ 貨物: SCU }）照順序做完 entries 之後：
 * { onboard, shorts: [卸貨比艙內多的貨物], nameOf(名稱) → onboard 裡用的寫法 }。
 * 沒填貨物名稱的算「（未命名）」。
 */
export function applyCargo(onboard, entries) {
  const out = { ...onboard }
  const names = new Map(Object.keys(out).map(n => [keyOf(n), n]))
  const nameOf = (item) => {
    const k = keyOf(item) || '（未命名）'
    if (!names.has(k)) names.set(k, (item || '').trim() || '（未命名）')
    return names.get(k)
  }
  const shorts = []
  for (const e of entries || []) {
    const scu = Number(e.scu) || 0
    if (scu <= 0) continue
    const name = nameOf(e.item)
    const have = out[name] || 0
    if (e.action === 'unload') {
      if (scu > have + 1e-9) shorts.push(name)
      out[name] = Math.max(0, have - scu)
    } else {
      out[name] = have + scu
    }
  }
  for (const k of Object.keys(out)) if (out[k] <= 1e-9) delete out[k]
  return { onboard: out, shorts, nameOf }
}

export const totalOf = onboard => Object.values(onboard || {}).reduce((n, v) => n + v, 0)

/**
 * 整條航線：keys 是站的代號（照順序，起點在最前面），byKey 是每站的裝卸。
 * 回傳 Map(代號 → { arriving, leaving, total, over, shorts })。capacity 是貨艙容量（0＝不檢查）。
 */
export function cargoFlow(keys, byKey, capacity = 0, initial = {}) {
  const map = new Map()
  let onboard = { ...initial }
  for (const key of keys) {
    const arriving = onboard
    const r = applyCargo(arriving, byKey?.[key] || [])
    onboard = r.onboard
    const total = totalOf(onboard)
    map.set(key, { arriving, leaving: onboard, total, over: capacity > 0 && total > capacity + 1e-9, shorts: r.shorts })
  }
  return map
}

/** 艙內 → 下一趟起點的「已在艙內」裝貨（中途重新規劃時帶過去） */
export const carryEntries = onboard => Object.entries(onboard || {})
  .filter(([, v]) => v > 1e-9).map(([item, scu]) => newCargoEntry({ action: 'load', item, scu }))
