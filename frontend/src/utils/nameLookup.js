/**
 * 名稱候選（AutocompleteField 的 search）：物品、藍圖、船艦主檔，中英文都比對。
 * 查詢持有資訊（components/PlayerHoldersSearch.vue）與我的藍圖的名稱欄共用。
 * fetcher 是 playerAuth.playerFetch 這類「回 Response 或 null」的函式；失敗一律回空陣列。
 */
async function list(fetcher, url) {
  const res = await fetcher(url)
  if (!res) return []
  const data = await res.json().catch(() => null)
  return (res.ok && data?.success) ? (data.data || []) : []
}

export const searchItemNames = (fetcher, q) => list(fetcher, `/item/search?q=${encodeURIComponent(q)}&limit=20`)
export const searchBlueprintNames = (fetcher, q) =>
  list(fetcher, `/blueprint/master/search?q=${encodeURIComponent(q)}&limit=20`)
export const searchVehicleNames = (fetcher, q) => list(fetcher, `/item/vehicles?q=${encodeURIComponent(q)}&limit=20`)
/** 候選顯示的名稱：中文為主，沒有就英文 */
export const nameLabel = c => c.name_zh || c.name
