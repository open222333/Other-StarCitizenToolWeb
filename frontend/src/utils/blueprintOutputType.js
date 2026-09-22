// 藍圖「類型」（後端欄位是 output_type，例如 WeaponGun、PowerPlant）的中文對照。
//
// 跟 MyPlayerView.vue 的 locationNamesZh 同一個做法：純靜態查表，不會隨遊戲
// 改版自動更新（收錄的 27 種是從 scunpacked-data 的 blueprints.json 撈出
// 1,607 張藍圖實際出現過的 output_type 統計出來的完整清單，2026-09）。
// 這些是遊戲/Wiki API 內部的分類代碼，不是玩家會在遊戲介面看到的專有名詞，
// 官方繁中化包（cosmo-chang-1701/sc-translation-pack）沒有對應詞條可以照抄，
// 這份是照一般星際公民玩家熟悉的分類講法手動翻的，不是社群翻譯包來源
// ——跟 sc_zh.py 其他幾份「查不到就顯示英文，不強行猜」的表不同，這裡
// 選擇直接給合理翻譯，因為都是常見裝備/艦體分類詞彙，不是需要對照遊戲內
// 文本才能確認的專有名詞。WeaponGun 對照「Vehicle Weapon」有 Wiki API 的
// type_label 佐證（見 tests/test_blueprint_master.py 的 fixture）。
// 唯一排除的是 output_type 為 null 的極少數藍圖（沒有分類可翻）。
//
// 只用在「查詢」頁的類型篩選欄位跟藍圖清單顯示——跟真正的物品/地點名稱
// 一樣走「英文（中文）」的 label 格式，見 locLabel() 的慣例。
import typeNamesZh from '@/assets/sc-blueprint-types-zh.json'

export function blueprintTypeZh(en) {
  return typeNamesZh[en] || ''
}

export function blueprintTypeLabel(en) {
  if (!en) return ''
  const zh = blueprintTypeZh(en)
  return zh ? `${zh}（${en}）` : en
}
