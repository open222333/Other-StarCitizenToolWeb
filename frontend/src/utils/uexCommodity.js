// UEX 商品價格／交易終端的顯示格式（玩家頁「查詢 › 商品購買地點」、後台「商品資料庫」共用）。
// 中文一律走 utils/translations.js（資料庫 sc_translations）：商品名稱先查礦物、再查物品；
// 地點名稱查 location。查不到就顯示英文。
import { loadTranslations, translate } from '@/utils/translations'

/** UEX 的庫存狀態 status_buy／status_sell（1～7） */
export const UEX_STATUS = {
  1: '缺貨', 2: '極少', 3: '少', 4: '中等', 5: '多', 6: '很多', 7: '滿倉',
}

export function uexStatusLabel(value) {
  if (value === null || value === undefined || value === '') return ''
  return UEX_STATUS[Number(value)] || String(value)
}

export function fmtAuec(value) {
  if (value === null || value === undefined || value === '' || Number(value) === 0) return '—'
  return `${Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })} aUEC`
}

export function fmtScu(value) {
  if (value === null || value === undefined || value === '') return '—'
  return `${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })} SCU`
}

/** 船艦「取得方式」篩選（UEX 遊戲內價格；多選取聯集），後端參數 acquire */
export const VEHICLE_ACQUIRE_OPTIONS = [
  { value: 'buy', label: '可用遊戲幣購買' },
  { value: 'rent', label: '可租船' },
]

/** 物品「取得方式」篩選（UEX 價格）：GET /item/?acquire=buy|sell */
export const ITEM_ACQUIRE_OPTIONS = [
  { value: 'buy', label: '買得到' },
  { value: 'sell', label: '能賣' },
]

/** 官網現金價（vehicle_master.msrp，美金） */
export function fmtUsd(value) {
  if (value === null || value === undefined || value === '' || Number(value) === 0) return '—'
  return `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 2 })}`
}

/** 每 1 美金換多少遊戲幣：遊戲內最低購買價（aUEC）÷ 官網售價（美金）；任一邊沒有回 null */
export function auecPerUsd(v) {
  const auec = Number(v?.uex_price?.buy_min)
  const usd = Number(v?.msrp)
  return auec > 0 && usd > 0 ? auec / usd : null
}

export function fmtAuecPerUsd(value) {
  return value ? `${Math.round(value).toLocaleString('en-US')} aUEC/$` : '—'
}

/** 艦隊共用搜尋的價格／貨艙範圍 → /item/vehicles 的查詢參數（空字串＝不限） */
export function vehicleRangeParams(f) {
  const out = {}
  const prefix = ['auec', 'rent'].includes(f?.priceCurrency) ? f.priceCurrency : 'usd'
  if (f?.priceMin !== '' && f?.priceMin != null) out[`${prefix}_min`] = f.priceMin
  if (f?.priceMax !== '' && f?.priceMax != null) out[`${prefix}_max`] = f.priceMax
  if (f?.scuMin !== '' && f?.scuMin != null) out.scu_min = f.scuMin
  if (f?.scuMax !== '' && f?.scuMax != null) out.scu_max = f.scuMax
  return out
}

/** 同上的條件在前端篩一筆載具（我的艦隊） */
export function vehicleInRanges(v, f) {
  const num = x => (x === '' || x == null ? null : Number(x))
  const within = (value, low, high) => (low === null || (value != null && value >= low))
    && (high === null || (value != null && value <= high))
  const pMin = num(f?.priceMin), pMax = num(f?.priceMax)
  if (pMin !== null || pMax !== null) {
    const price = f?.priceCurrency === 'auec' ? (v?.uex_price?.buy_min || null)
      : f?.priceCurrency === 'rent' ? (v?.uex_price?.rent_min || null) : (v?.msrp || null)
    if (!within(price, pMin, pMax)) return false
  }
  const sMin = num(f?.scuMin), sMax = num(f?.scuMax)
  if (sMin !== null || sMax !== null) {
    if (!within(v?.cargo_capacity_scu ?? 0, sMin, sMax)) return false
  }
  return true
}

/** UEX 的時間是 unix 秒數 */
export function fmtUexTime(value) {
  const n = Number(value)
  if (!n) return '—'
  return new Date(n * 1000).toLocaleString('zh-TW', { hour12: false })
}

export function commodityZh(name) {
  return name ? (translate('mining_resource', name) || translate('item', name) || '') : ''
}

/** 「中文（英文）」；沒有中文就只有英文 */
export function commodityLabel(c) {
  const zh = commodityZh(c?.name)
  return zh ? `${zh}（${c.name}）` : (c?.name || c?.code || '')
}

export function loadCommodityZh(names) {
  const list = (names || []).filter(Boolean)
  loadTranslations('mining_resource', list)
  loadTranslations('item', list)
}

export function locationZh(name) {
  return translate('location', name) || name || ''
}

export function loadLocationZh(names) {
  loadTranslations('location', (names || []).filter(Boolean))
}

/** 地點路徑（['Stanton', 'ArcCorp', 'Area18']）→「斯坦頓 › 弧光集團 › 18 區」 */
export function locationPathLabel(path) {
  return (path || []).map(locationZh).join(' › ')
}
