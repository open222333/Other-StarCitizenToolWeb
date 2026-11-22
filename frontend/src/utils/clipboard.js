// 複製文字到剪貼簿，成功／失敗都用 toast 告知（待辦 C8，取代各頁自己寫的 navigator.clipboard＋toast）。
import { toast } from '@/utils/toast'

/** 回傳 true／false；okText／failText 可以換成那一頁的說法 */
export async function copyText(text, { okText = '已複製', failText = '複製失敗，請手動選取' } = {}) {
  try {
    await navigator.clipboard.writeText(String(text ?? ''))
    toast(okText)
    return true
  } catch {
    toast(failText, 'danger')
    return false
  }
}
