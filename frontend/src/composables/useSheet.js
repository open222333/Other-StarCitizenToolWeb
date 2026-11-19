// 底部面板（.sf-sheet）的「對話框」行為：開啟時把焦點移進面板、Esc 關閉、
// 關閉後焦點回到開啟它的按鈕（開啟當下的 document.activeElement）。
// SfFilterSheet 跟 MyPlayerView 的「更多」面板共用。
//
//   const open = ref(false)
//   const sheetEl = ref(null)            // <div ref="sheetEl" class="sf-sheet" role="dialog" aria-modal="true" tabindex="-1">
//   const { close } = useSheet(open, sheetEl)
//
// 面板根元素要加 tabindex="-1"：裡面沒有可聚焦的元素時，焦點就落在面板本身。
import { nextTick, onBeforeUnmount, watch } from 'vue'

const FOCUSABLE = [
  'button:not([disabled])', '[href]', 'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',')

// 開著的面板／視窗（後開的在最後）：疊好幾層時（例如航線結果視窗裡再開貨櫃試算），Esc 只關最上面那層
const openStack = []

export function useSheet(openRef, sheetElRef, { initialFocus = null } = {}) {
  let trigger = null
  const token = {}
  const unstack = () => { const i = openStack.indexOf(token); if (i >= 0) openStack.splice(i, 1) }

  function close() { openRef.value = false }

  function onKeydown(event) {
    // 裡面的元件（例如 AutocompleteField 的候選清單）已經用 Esc 關掉自己時會 preventDefault，不要連面板一起關
    if (event.key === 'Escape' && openRef.value && !event.defaultPrevented && openStack[openStack.length - 1] === token) {
      event.preventDefault()
      event.stopPropagation()
      close()
    }
  }

  watch(openRef, async (isOpen) => {
    if (isOpen) {
      trigger = typeof document !== 'undefined' ? document.activeElement : null
      unstack(); openStack.push(token)
      document.addEventListener('keydown', onKeydown)
      await nextTick()
      const el = sheetElRef.value
      if (!el) return
      const target = (initialFocus && el.querySelector(initialFocus)) || el.querySelector(FOCUSABLE) || el
      target.focus?.({ preventScroll: true })
    } else {
      document.removeEventListener('keydown', onKeydown)
      unstack()
      const t = trigger
      trigger = null
      if (t && typeof t.focus === 'function' && document.contains(t)) t.focus({ preventScroll: true })
    }
  })

  onBeforeUnmount(() => { document.removeEventListener('keydown', onKeydown); unstack() })

  return { close }
}
