// 藍圖「類型」（後端欄位是 output_type，例如 WeaponGun、PowerPlant）的顯示文字。
//
// 翻譯存在資料庫（sc_translations 的人工條目 manual.blueprint_type.*，來源
// src/data/sc_translation_manual.json——這些是遊戲內部分類代碼，社群翻譯包沒有），
// 這裡只負責取用，見 utils/translations.js。第一次用到時自動載入整份清單。
import { loadTranslationDomain, translate } from '@/utils/translations'

export function blueprintTypeZh(en) {
  // 已載入或載入中會直接返回；失敗的話下次呼叫會再試
  loadTranslationDomain('blueprint_type')
  return translate('blueprint_type', en)
}

export function blueprintTypeLabel(en) {
  if (!en) return ''
  const zh = blueprintTypeZh(en)
  return zh ? `${zh}（${en}）` : en
}
