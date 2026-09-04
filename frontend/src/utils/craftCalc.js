/**
 * 藍圖材料試算的純計算邏輯。
 *
 * 刻意跟畫面分開：這裡是整個功能唯一「會算錯就直接誤導使用者」的部分，
 * 抽成純函式才能單獨驗證，也才不會被 Vue 的 reactive 細節干擾。
 *
 * ## 主檔資料的兩種單位
 *
 * `blueprint_master.ingredients` 的每一項（見 src/scdata.py 的 map_blueprint）
 * 可能是：
 *   - `quantity`：**個數**（成品零件之類，對得上 item_master 的 item_uuid）
 *   - `quantity_scu`：**體積 SCU**（礦石／氣體這種原料，通常只有
 *     resource_type_uuid，item_master 裡沒有對應文件）
 * 兩種單位不能混在一起加減，所以每一列都自己帶 unit。
 *
 * ## 為什麼要有「未知需求」這個狀態
 *
 * `ingredients` 只在同步時帶了 include 參數才會有內容，而且個別項目也可能
 * 兩個數量欄位都是 null。這種情況**不能當成 0**（那會算出「可以做無限個」）
 * 也不能當成 1，只能誠實標成未知、從瓶頸計算裡排除，並讓畫面提示
 * 「這張藍圖的資料不完整，結果僅供參考」。
 */

export const UNIT_COUNT = 'count'
export const UNIT_SCU = 'scu'

const UNIT_LABEL = { [UNIT_COUNT]: '個', [UNIT_SCU]: 'SCU' }

export function unitLabel(unit) {
  return UNIT_LABEL[unit] || ''
}

/** 把使用者輸入（字串／空值／負數）轉成可計算的非負數量。 */
export function toAmount(value) {
  if (value === '' || value === null || value === undefined) return 0
  const n = Number(value)
  if (!Number.isFinite(n) || n < 0) return 0
  return n
}

/**
 * 把主檔的 ingredients 正規化成試算用的列。
 *
 * 回傳的 `key` 是這一列的穩定識別（給 v-for 與「現有數量」的 map 用）：
 * item_uuid 優先，其次 resource_type_uuid，都沒有就退回名稱＋索引 ——
 * 有些原料只有名稱，沒有 uuid。
 */
export function normalizeIngredients(recipe) {
  const list = (recipe && recipe.ingredients) || []
  return list.map((ing, index) => {
    const hasCount = ing.quantity !== null && ing.quantity !== undefined
    const hasScu = ing.quantity_scu !== null && ing.quantity_scu !== undefined
    const unit = hasCount ? UNIT_COUNT : (hasScu ? UNIT_SCU : null)
    const need = hasCount ? Number(ing.quantity) : (hasScu ? Number(ing.quantity_scu) : null)

    return {
      key: ing.item_uuid || ing.resource_type_uuid || `${ing.name || 'ingredient'}#${index}`,
      name: ing.name || '（未命名材料）',
      kind: ing.kind || '',
      itemUuid: ing.item_uuid || '',
      resourceUuid: ing.resource_type_uuid || '',
      unit,
      // need > 0 才算「已知需求」：0 或負數在配方裡沒有意義，當成資料有問題
      need: Number.isFinite(need) && need > 0 ? need : null,
      // 只有對得上 item_master 的材料才可能從庫存自動帶入
      canPrefill: Boolean(ing.item_uuid),
    }
  })
}

/**
 * 試算主體。
 *
 * @param {Array}  rows    normalizeIngredients() 的結果
 * @param {Object} haveMap `{ [row.key]: 使用者填的現有數量 }`
 * @param {number} target  想做幾個（0／空 = 不算目標缺料）
 */
export function calcCraft(rows, haveMap = {}, target = 0) {
  const wanted = Math.max(0, Math.floor(toAmount(target)))

  const detail = rows.map(row => {
    const have = toAmount(haveMap[row.key])
    if (!row.need) {
      // 需求未知 → 這一列不參與瓶頸計算，也算不出缺多少
      return { ...row, have, canMake: null, shortfall: null }
    }
    return {
      ...row,
      have,
      // 「只看這一項材料的話夠做幾個」——瓶頸就是這個值最小的那些列
      canMake: Math.floor(have / row.need),
      // 要做到 target 還缺多少（已經夠就是 0）
      shortfall: wanted > 0 ? Math.max(0, row.need * wanted - have) : 0,
    }
  })

  const known = detail.filter(row => row.need)
  const unknownCount = detail.length - known.length

  // 沒有任何一列有明確需求 → 算不出來，回 null 而不是 0 或 Infinity
  const maxCraftable = known.length
    ? known.reduce((min, row) => Math.min(min, row.canMake), Infinity)
    : null

  // 瓶頸：可做數量等於最終結果的那些列（可能同時有好幾個）
  const bottlenecks = maxCraftable === null
    ? []
    : known.filter(row => row.canMake === maxCraftable).map(row => row.key)

  // 依「最多可做幾個」算出實際會消耗與剩下的量。
  //
  // ⚠️ leftover 一定要用最終的 maxCraftable 算，不能用該列自己的 canMake ——
  // 用後者的話，非瓶頸的材料會顯示「只剩 1 個」（假設它被用到極限），
  // 但實際上做完 2 個之後還剩 7 個。這個 bug 是靠測試抓到的。
  const usable = maxCraftable === null ? 0 : maxCraftable
  const detailWithUse = detail.map(row => {
    if (!row.need) return { ...row, used: null, leftover: null, isBottleneck: false }
    const used = row.need * usable
    return {
      ...row,
      used,
      leftover: row.have - used,
      isBottleneck: bottlenecks.includes(row.key),
    }
  })

  const missing = wanted > 0
    ? detailWithUse.filter(row => row.shortfall > 0)
    : []

  return {
    rows: detailWithUse,
    maxCraftable,
    bottlenecks,
    unknownCount,
    // 資料不完整（有未知需求的材料）時，結果只能當參考值
    reliable: unknownCount === 0 && known.length > 0,
    target: wanted,
    missing,
    // 目標做得到嗎（沒填目標時為 null）
    targetReachable: wanted > 0 && maxCraftable !== null ? maxCraftable >= wanted : null,
  }
}

/**
 * 從庫存列表算出每個材料的現有數量。
 *
 * 庫存是按「地點／容器」分開存的，同一個物品會有多列，所以要按 item_id 加總。
 * 個數用 `quantity`，SCU 用 `total_scu`（後端已經算好體積），不要自己乘 ——
 * 體積係數在 item_master 上，前端沒有。
 */
export function stockToHaveMap(rows, stockRows) {
  const byItem = new Map()
  for (const stock of stockRows || []) {
    const id = stock.item_id
    if (!id) continue
    const prev = byItem.get(id) || { count: 0, scu: 0 }
    byItem.set(id, {
      count: prev.count + toAmount(stock.quantity),
      scu: prev.scu + toAmount(stock.total_scu),
    })
  }

  const haveMap = {}
  for (const row of rows) {
    if (!row.itemUuid) continue
    const found = byItem.get(row.itemUuid)
    if (!found) continue
    haveMap[row.key] = row.unit === UNIT_SCU ? found.scu : found.count
  }
  return haveMap
}

/** 製造時間：單個秒數 × 數量 → 「2 小時 15 分」這種可讀字串。 */
export function craftTimeLabel(secondsPerCraft, count) {
  const per = toAmount(secondsPerCraft)
  const n = Math.max(0, Math.floor(toAmount(count)))
  if (!per || !n) return ''

  let total = Math.round(per * n)
  const days = Math.floor(total / 86400); total -= days * 86400
  const hours = Math.floor(total / 3600); total -= hours * 3600
  const minutes = Math.floor(total / 60)
  const seconds = total - minutes * 60

  const parts = []
  if (days) parts.push(`${days} 天`)
  if (hours) parts.push(`${hours} 小時`)
  if (minutes) parts.push(`${minutes} 分`)
  if (!days && !hours && seconds) parts.push(`${seconds} 秒`)
  return parts.join(' ')
}
