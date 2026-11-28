// 維克洛（Wikelo Emporium）交易的共用索引：物品／藍圖／艦船列決定要不要顯示「維克洛」按鈕（components/WikeloButton.vue）。
// GET /mission/wikelo/index（公開，整份很小）整站載一次：{uuids: {uuid: {reward, requirement}}, names: {小寫獎勵名稱: 筆數}}
import { reactive } from 'vue'
import { getJson } from '@/utils/getJson'

export const wikeloIndex = reactive({ uuids: {}, names: {}, loaded: false })
let pending = null

export function loadWikeloIndex(fetcher = fetch) {
  if (wikeloIndex.loaded) return Promise.resolve(wikeloIndex)
  if (!pending) {
    pending = getJson(fetcher, '/mission/wikelo/index', undefined, '').then(({ ok, data }) => {
      if (ok) Object.assign(wikeloIndex, { uuids: data.uuids || {}, names: data.names || {}, loaded: true })
      else pending = null   // 失敗下次再試
      return wikeloIndex
    }).catch(() => { pending = null; return wikeloIndex })
  }
  return pending
}

/** 這些 uuid／名稱有沒有出現在維克洛交易裡（獎勵或需求） */
export function wikeloHit(uuids = [], names = []) {
  return uuids.some(u => u && wikeloIndex.uuids[u])
    || names.some(n => n && wikeloIndex.names[String(n).trim().toLowerCase()])
}

/** 需求數量：個數，或 SCU（礦物、商品類） */
export function wikeloAmount(r) {
  if (r.amount !== null && r.amount !== undefined) {
    return r.max_amount ? `× ${r.amount}–${r.max_amount}` : `× ${r.amount}`
  }
  if (r.min_scu !== null && r.min_scu !== undefined) {
    return r.max_scu && r.max_scu !== r.min_scu ? `${r.min_scu}–${r.max_scu} SCU` : `${r.min_scu} SCU`
  }
  return ''
}

// 獎勵種類：載具主檔的＝艦船；物品看主檔 type（武器、護甲），其餘＝其他
export const WIKELO_KINDS = [
  { value: 'ship', label: '艦船' },
  { value: 'weapon', label: '武器' },
  { value: 'armor', label: '護甲' },
  { value: 'other', label: '其他' },
]
export const KIND_LABEL = Object.fromEntries(WIKELO_KINDS.map(k => [k.value, k.label]))
export function rewardKind(r) {
  if (r.source === 'vehicle') return 'ship'
  const t = r.type || ''
  if (/^Weapon/i.test(t)) return 'weapon'
  if (/^Char_Armor|^Suit/i.test(t)) return 'armor'
  if (!t && !r.source && !/favor|scrip/i.test(r.name || '')) return 'ship'   // 主檔還沒對到的船
  return 'other'
}
