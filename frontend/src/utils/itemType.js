// 物品類型／子類型的中文（item_master.type／sub_type，例如 WeaponPersonal、Char_Armor_Torso、Sniper）。
// 翻譯來自資料庫 sc_translations（遊戲 key item_Type<代碼>／item_SubType<代碼>，
// 後端 src/sc_zh.py 的 item_type_zh／item_sub_type_zh），透過 utils/translations.js 查。
import { reactive } from 'vue'
import { loadTranslations, translate } from '@/utils/translations'

export function loadItemTypeZh(types = [], subTypes = []) {
  if (types.length) loadItemTypeGroups()
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

// 物品類型群組（多選篩選 MultiSelectFilter 依群組分段、可整組勾選）：存在資料庫 app_settings（後台「系統設定」
// 可改，GET /item/type-groups 公開讀取）。群組 {label, types（完整代碼）, prefixes（代碼前綴）}；
// 沒對到的歸「其他」。讀到之前選項不分段，讀回來後自動重新渲染。
const typeGroups = reactive({ list: [] })
let groupsPromise = null
export function loadItemTypeGroups(force = false) {
  if (groupsPromise && !force) return groupsPromise
  groupsPromise = fetch('/item/type-groups')
    .then(res => (res.ok ? res.json() : null))
    .then((body) => {
      if (!body?.success) { groupsPromise = null; return typeGroups.list }
      typeGroups.list = Array.isArray(body.data?.groups) ? body.data.groups : []
      return typeGroups.list
    })
    .catch(() => { groupsPromise = null; return typeGroups.list })
  return groupsPromise
}
/** 後台存檔後直接換掉（不用再讀一次） */
export function setItemTypeGroups(groups) {
  typeGroups.list = Array.isArray(groups) ? groups : []
  groupsPromise = Promise.resolve(typeGroups.list)
}
export const OTHER_GROUP_LABEL = '其他'
export function matchesGroup(g, code) {
  const c = code || ''
  return (g.types || []).includes(c) || (g.prefixes || []).some(p => p && c.startsWith(p))
}
export function itemTypeGroup(code) {
  const list = typeGroups.list
  if (!list.length) return { label: '', index: 0 }
  const i = list.findIndex(g => matchesGroup(g, code))
  return i < 0 ? { label: OTHER_GROUP_LABEL, index: list.length } : { label: list[i].label, index: i }
}

/** 下拉選項：中文（代碼）；沒有中文就是代碼。group／groupIndex 給多選篩選分段用 */
export function itemTypeOption(code) {
  const zh = itemTypeZh(code)
  const g = itemTypeGroup(code)
  const opt = { value: code, label: zh && zh !== code ? `${zh}（${code}）` : code }
  return g.label ? { ...opt, group: g.label, groupIndex: g.index } : opt
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
