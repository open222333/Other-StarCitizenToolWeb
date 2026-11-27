// UEX 商品價格／交易終端的顯示格式（玩家頁「查詢 › 商品購買地點」、後台「商品資料庫」共用）。
// 中文一律走 utils/translations.js（資料庫 sc_translations）：商品名稱先查礦物、再查物品；
// 地點名稱查 location。查不到就顯示英文。
import { inRange, rangeActive } from '@/utils/rangeScale'
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

// ── 艦隊共用搜尋的價格／貨物量範圍（components/SfRangeFilter.vue）──
// 價格可以同時勾好幾種貨幣，每種一條範圍（條件之間 AND）；範圍 { min, max }，空字串＝那一邊不限。
// max＝拉條最右邊的值、presets＝預設級距（再大的用輸入框打）。
export const PRICE_CURRENCIES = [
  { key: 'usd', label: '美金', unit: 'USD', max: 5000, presets: [
    { label: '$50 以下', min: '', max: 50 }, { label: '$50–150', min: 50, max: 150 }, { label: '$150–350', min: 150, max: 350 },
    { label: '$350–750', min: 350, max: 750 }, { label: '$750 以上', min: 750, max: '' }] },
  { key: 'auec', label: '遊戲幣', unit: 'aUEC', max: 100_000_000, presets: [
    { label: '100 萬以下', min: '', max: 1_000_000 }, { label: '100–500 萬', min: 1_000_000, max: 5_000_000 },
    { label: '500–2000 萬', min: 5_000_000, max: 20_000_000 }, { label: '2000 萬以上', min: 20_000_000, max: '' }] },
  { key: 'rent', label: '租用', unit: 'aUEC', max: 1_000_000, presets: [
    { label: '1 萬以下', min: '', max: 10_000 }, { label: '1–5 萬', min: 10_000, max: 50_000 },
    { label: '5–20 萬', min: 50_000, max: 200_000 }, { label: '20 萬以上', min: 200_000, max: '' }] },
]
export const SCU_RANGE = { max: 10000, presets: [
  { label: '有貨艙', min: 1, max: '' }, { label: '50 以下', min: '', max: 50 }, { label: '50–200', min: 50, max: 200 },
  { label: '200–700', min: 200, max: 700 }, { label: '700 以上', min: 700, max: '' }] }
const emptyRange = () => ({ min: '', max: '' })
/** 空的範圍條件：priceOn＝勾了哪幾種貨幣，price.<貨幣>、scu 各一條範圍 */
export function emptyVehicleRange() {
  return { priceOn: [], price: Object.fromEntries(PRICE_CURRENCIES.map(c => [c.key, emptyRange()])), scu: emptyRange() }
}
/** 有設的範圍條數（勾了貨幣但範圍沒設不算） */
export function vehicleRangeCount(f) {
  return (f?.priceOn || []).filter(k => rangeActive(f.price?.[k])).length + (rangeActive(f?.scu) ? 1 : 0)
}

/** 範圍條件 → /item/vehicles 的查詢參數（usd_min／auec_max／rent_min／scu_max…） */
export function vehicleRangeParams(f) {
  const out = {}
  const put = (prefix, r) => {
    if (r?.min !== '' && r?.min != null) out[`${prefix}_min`] = r.min
    if (r?.max !== '' && r?.max != null) out[`${prefix}_max`] = r.max
  }
  for (const k of f?.priceOn || []) if (PRICE_CURRENCIES.some(c => c.key === k)) put(k, f.price?.[k])
  put('scu', f?.scu)
  return out
}

/** 同上的條件在前端篩一筆載具（我的艦隊） */
export function vehicleInRanges(v, f) {
  const priceOf = { usd: v?.msrp || null, auec: v?.uex_price?.buy_min || null, rent: v?.uex_price?.rent_min || null }
  for (const k of f?.priceOn || []) if (!inRange(priceOf[k], f.price?.[k])) return false
  return inRange(v?.cargo_capacity_scu ?? 0, f?.scu)
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
