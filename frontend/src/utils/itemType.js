// 物品類型／子類型的中文（item_master.type／sub_type，例如 WeaponPersonal、Char_Armor_Torso、Sniper）。
// 翻譯來自資料庫 sc_translations（遊戲 key item_Type<代碼>／item_SubType<代碼>，
// 後端 src/sc_zh.py 的 item_type_zh／item_sub_type_zh），透過 utils/translations.js 查。
import { loadTranslations, translate } from '@/utils/translations'

export function loadItemTypeZh(types = [], subTypes = []) {
  loadTranslations('item_type', types)
  loadTranslations('item_sub_type', subTypes.filter(s => s && s !== 'UNDEFINED'))
}

export const itemClassZh = code => translate('item_class', code)
export function itemClassOption(code) {
  const zh = itemClassZh(code)
  return { value: code, label: zh && zh !== code ? `${zh}（${code}）` : code }
}
export const loadItemClassZh = (classes = []) => loadTranslations('item_class', classes)

export const itemTypeZh = code => translate('item_type', code)
export const itemSubTypeZh = code => (code === 'UNDEFINED' ? '' : translate('item_sub_type', code))

/** 下拉選項：中文（代碼）；沒有中文就是代碼 */
export function itemTypeOption(code) {
  const zh = itemTypeZh(code)
  return { value: code, label: zh && zh !== code ? `${zh}（${code}）` : code }
}
export function itemSubTypeOption(code) {
  const zh = itemSubTypeZh(code)
  return { value: code, label: zh && zh !== code ? `${zh}（${code}）` : code }
}

/** 列表顯示：類型 › 子類型（有中文用中文） */
export function itemTypeLabel(type, subType) {
  const sub = subType && subType !== 'UNDEFINED' ? (itemSubTypeZh(subType) || subType) : ''
  return [type ? (itemTypeZh(type) || type) : '', sub].filter(Boolean).join(' › ')
}
