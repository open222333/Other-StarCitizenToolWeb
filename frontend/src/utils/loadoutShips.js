// 有配裝資料的船（GET /item/loadout/ships 的 id，跟載具主檔 uuid 同一套）：艦船列表的「預設配件」按鈕看這份決定要不要出現。
// 整頁共用一份，第一次用到才抓（同時好幾個按鈕只會抓一次）。
import { ref } from 'vue'
import { getJson } from '@/utils/getJson'

export const loadoutShipIds = ref(new Set())
let pending = null

export function loadLoadoutShipIds(fetcher) {
  if (pending) return pending
  pending = getJson(fetcher, '/item/loadout/ships').then(({ ok, data }) => {
    if (ok) loadoutShipIds.value = new Set((data || []).map(s => s.id || s._id).filter(Boolean))
    else pending = null          // 失敗：下次再試
  })
  return pending
}
