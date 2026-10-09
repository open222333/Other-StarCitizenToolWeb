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
