// 藍圖配方的材料／拆解回收顯示名稱（中文）。
//
// 材料有兩種：礦物（kind === 'resource'，或拆解回收那種只有 resource_type_uuid 的）
// 用 mining_resource 查中文；其他（物品）用 item 查。中文一律從翻譯資料庫來
// （utils/translations.js），查不到就只顯示英文。
// 用在：玩家頁「我的藍圖」的配方、試算（BlueprintCalculator）、藍圖資料（BlueprintMasterBrowser）。
import { loadTranslations, translate } from '@/utils/translations'

export function isResource(m) {
  if (!m) return false
  return m.kind === 'resource' || (!m.kind && !!(m.resource_type_uuid || m.resourceUuid))
}

/** 材料的中文名稱，查不到回 ''。礦物先查礦物、再退回物品。 */
export function materialZh(m) {
  const name = m?.name || ''
  if (!name) return ''
  return (isResource(m) ? translate('mining_resource', name) : '') || translate('item', name) || ''
}

/** 「中文（English）」，沒有中文就只有英文。 */
export function materialLabel(m) {
  const name = m?.name || '—'
  const zh = materialZh(m)
  return zh ? `${zh}（${name}）` : name
}

/** 一次把配方（材料＋拆解回收）的中文載進快取，載完畫面會自動更新。 */
export function loadMaterialZh(recipe) {
  const mats = [...(recipe?.ingredients || []), ...(recipe?.dismantle_returns || [])]
  const names = mats.map(m => m.name).filter(Boolean)
  if (!names.length) return
  loadTranslations('mining_resource', mats.filter(isResource).map(m => m.name).filter(Boolean))
  loadTranslations('item', names)
}

// ── sc-datahub.com 對應頁面 ──────────────────────────────────────────
// 藍圖：https://sc-datahub.com/tools/crafting/<名稱 slug>（例如 10-series-greatsword-cannon）
// 礦物：https://sc-datahub.com/tools/mining/ores/<名稱 slug>（例如 iron）
// slug＝英文名稱轉小寫、非英數字換成 -。物品類材料 sc-datahub 沒有對應頁面，不給連結。
const SC_DATAHUB = 'https://sc-datahub.com/tools'

export function scDatahubSlug(name) {
  return String(name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
}

export function blueprintDatahubUrl(name) {
  const slug = scDatahubSlug(name)
  return slug ? `${SC_DATAHUB}/crafting/${slug}` : ''
}

export function materialDatahubUrl(m) {
  if (!isResource(m)) return ''
  // Iron (Ore)／Raw Ouratite 這種寫法對應到同一種礦：去掉 (Ore)／(Raw) 後綴與 Raw 前綴
  const base = String(m?.name || '').replace(/\s*\((ore|raw)\)\s*$/i, '').replace(/^raw\s+/i, '')
  const slug = scDatahubSlug(base)
  return slug ? `${SC_DATAHUB}/mining/ores/${slug}` : ''
}
