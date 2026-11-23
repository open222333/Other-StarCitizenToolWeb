// 船的商店價（美金）摘要：整站共用一份，第一個「船價」按鈕掛上來時載入（GET /item/ship-prices）。
// 用載具主檔 uuid 查；RSI 商店或 Open Hangar 對得到載具的船才有。見 components/ShipPriceButton.vue。
import { ref } from 'vue'

/** 載具 uuid → 摘要列（key、msrp、on_sale、warbond_now、price_now、last_warbond、avail、period_count…） */
export const priceByVehicle = ref(new Map())
/** 摘要列的 key（Open Hangar 船名或 rsi:<id>）→ 摘要列：對不到載具的船（例如概念船）用這個查 */
export const priceByKey = ref(new Map())
export const priceAttribution = ref('')
let pending = null

export function loadShipPrices(fetcher) {
  if (pending) return pending
  pending = (async () => {
    const res = await fetcher('/item/ship-prices')
    const body = res ? await res.json().catch(() => null) : null
    if (!res?.ok || !body?.success) {
      pending = null   // 失敗：下一個按鈕掛上來時再試
      return
    }
    const map = new Map()
    for (const row of body.data || []) {
      // 同一艘載具對到好幾筆（例如一般版與「10 Year」版）：留上架紀錄多的那筆
      const old = row.vehicle_uuid && map.get(row.vehicle_uuid)
      if (row.vehicle_uuid && (!old || (row.period_count || 0) > (old.period_count || 0))) map.set(row.vehicle_uuid, row)
    }
    priceByVehicle.value = map
    priceByKey.value = new Map((body.data || []).map(r => [r.key, r]))
    priceAttribution.value = body.attribution || ''
  })()
  return pending
}
