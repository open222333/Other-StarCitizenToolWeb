// 配裝模擬共用的中文標籤（LoadoutSimulator、LoadoutPicker、LoadoutItemModal、loadoutPicker.js）。
// 配件類型、子類型、組件類別一律查資料庫翻譯（utils/itemType.js → sc_translations；翻譯包沒有的
// 放 src/data/sc_translation_manual.json 人工條目），不另外做對照表（CLAUDE.md）。
// 傷害種類、追蹤方式不是遊戲物品資料的代碼，用這裡唯一的一份。
import { itemClassZh, itemSubTypeZh, itemTypeZh, loadItemClassZh, loadItemTypeZh } from './itemType.js'

export { DMG_LABEL, TRACK_LABEL } from './loadoutConst.js'

/** 掛點可裝的類型（「Turret.GunTurret」這種 類型.子類型）→「雲台／武器」：子類型有中文用子類型，否則用類型 */
export function typeLabel(types) {
  const out = []
  for (const t of types || []) {
    const [b, s] = String(t).split('.')
    const label = (s && s !== 'UNDEFINED' && itemSubTypeZh(s)) || itemTypeZh(b) || b
    if (label && !out.includes(label)) out.push(label)
  }
  return out.join('／')
}

/** 組件類別（Military…）→ 軍用 */
export const classLabel = c => (c ? itemClassZh(c) || c : '')

/** 載入一批配件／掛點會用到的中文（類型、子類型、類別）；查到之前先顯示英文 */
export function loadLoadoutZh(items = [], nodeTypes = []) {
  const types = new Set()
  const subs = new Set()
  const classes = new Set()
  for (const it of items) {
    if (it?.type) types.add(it.type)
    if (it?.sub_type) subs.add(it.sub_type)
    if (it?.item_class) classes.add(it.item_class)
  }
  for (const t of nodeTypes) {
    const [b, s] = String(t).split('.')
    if (b) types.add(b)
    if (s) subs.add(s)
  }
  loadItemTypeZh([...types], [...subs])
  if (classes.size) loadItemClassZh([...classes])
}
