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
