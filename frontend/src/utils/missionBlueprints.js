// 任務的獎勵藍圖「已登記幾張」——任務列表、任務細節、勢力聲望、藍圖的解鎖任務彈窗共用。
// 任務列表／勢力聲望的資料是 blueprint_pools[].items[]（blueprint_uuid），
// 解鎖任務彈窗的是 pool_blueprints[]（uuid），兩種都吃。
// 預設可用（is_available_by_default）的藍圖每個人本來就有，視同已登記。

/** 藍圖的 uuid（兩種資料形狀） */
export const bpUuid = it => it?.blueprint_uuid || it?.uuid || ''

/** 任務會給的所有藍圖：所有獎勵池合起來，同一張只算一次（保留順序） */
export function missionPool(m) {
  if (Array.isArray(m?.pool_blueprints)) return m.pool_blueprints
  const seen = new Map()
  for (const p of m?.blueprint_pools || []) {
    for (const it of p.items || []) {
      const id = bpUuid(it)
      if (id && !seen.has(id)) seen.set(id, it)
    }
  }
  return [...seen.values()]
}

/** 這張藍圖算不算已登記（registered：已登記 uuid 的 Set） */
export function isBpRegistered(it, registered) {
  return !!it?.is_available_by_default || !!registered?.has(bpUuid(it))
}

/** 已登記的狀態文字：預設可用／已登記／未登記 */
export function bpStateLabel(it, registered) {
  if (!isBpRegistered(it, registered)) return '未登記'
  return it.is_available_by_default && !registered?.has(bpUuid(it)) ? '預設可用' : '已登記'
}

/** 任務的藍圖已登記幾張 */
export function registeredInPool(m, registered) {
  return missionPool(m).filter(it => isBpRegistered(it, registered)).length
}
