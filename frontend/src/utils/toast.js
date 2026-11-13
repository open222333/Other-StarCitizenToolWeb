// 全站共用的輕量提示（Toast）：操作成功／失敗的回饋統一從這裡發，顯示在畫面角落（components/SfToaster.vue，掛在 App.vue）。
// 不會把頁面內容往下推，也不用每個元件各自管一條 alert 與計時器。
//
//   import { toast } from '@/utils/toast'
//   toast('已儲存')                    // 成功（預設）
//   toast('網路錯誤，請稍後再試', 'warning')
//   toast(data.message || '刪除失敗', 'danger')
//
// 表單欄位的驗證錯誤（某個欄位填錯）還是放在表單裡、欄位旁邊，不要用 toast——錯誤要出現在要修的地方。
import { reactive } from 'vue'

export const TOAST_TYPES = ['success', 'info', 'warning', 'danger']
/** 自動消失的時間（毫秒）：錯誤留久一點，讓人看得完 */
const DURATION = { success: 4000, info: 4000, warning: 6000, danger: 8000 }
const MAX_TOASTS = 4

export const toasts = reactive([])
let seq = 0
const timers = new Map()

/** 'alert-success'、'success'、'error' 都接受 */
function normType(type) {
  const t = String(type || 'success').replace(/^alert-/, '')
  if (t === 'error') return 'danger'
  return TOAST_TYPES.includes(t) ? t : 'info'
}

function schedule(item, ms) {
  clearTimeout(timers.get(item.id))
  timers.set(item.id, setTimeout(() => dismissToast(item.id), ms))
}

/** 顯示一則提示，回傳 id。同樣的訊息還在畫面上時不重複疊，只重新計時。 */
export function toast(text, type = 'success', { duration } = {}) {
  const msg = String(text ?? '').trim()
  if (!msg) return null
  const t = normType(type)
  const ms = duration ?? DURATION[t]
  const same = toasts.find(x => x.text === msg && x.type === t)
  if (same) {
    same.count += 1
    schedule(same, ms)
    return same.id
  }
  const item = { id: ++seq, text: msg, type: t, count: 1, ms }
  toasts.push(item)
  while (toasts.length > MAX_TOASTS) dismissToast(toasts[0].id)
  schedule(item, ms)
  return item.id
}

export function dismissToast(id) {
  clearTimeout(timers.get(id))
  timers.delete(id)
  const i = toasts.findIndex(x => x.id === id)
  if (i >= 0) toasts.splice(i, 1)
}

/** 滑鼠移上去或鍵盤 focus 時先不要消失（看不完的長訊息） */
export function holdToast(id) {
  clearTimeout(timers.get(id))
}

export function releaseToast(id) {
  const item = toasts.find(x => x.id === id)
  if (item) schedule(item, Math.min(item.ms, 3000))
}
