// 依「畫面寬度」與「觸控」判斷手機／平板（不看 User-Agent：iPad 會自稱 Mac，
// 手機橫放、平板分割畫面時寬度也跟機型不符）。斷點對齊 Bootstrap，CSS 也用同一組數字：
//   手機 < 768px、平板 768–1199px、電腦 ≥ 1200px；觸控＝(pointer: coarse)。
// 方案說明見專案文件「星際公民工具-玩家頁手機平板UI方案」。
import { onBeforeUnmount, ref } from 'vue'

export const PHONE_QUERY = '(max-width: 767.98px)'
export const TABLET_QUERY = '(min-width: 768px) and (max-width: 1199.98px)'
export const TOUCH_QUERY = '(pointer: coarse)'

export function useBreakpoint() {
  const cleanups = []
  function watchQuery(query) {
    const m = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query) : null
    const state = ref(!!m?.matches)
    if (m?.addEventListener) {
      const onChange = (e) => { state.value = e.matches }
      m.addEventListener('change', onChange)
      cleanups.push(() => m.removeEventListener('change', onChange))
    }
    return state
  }
  const isPhone = watchQuery(PHONE_QUERY)
  const isTablet = watchQuery(TABLET_QUERY)
  const isTouch = watchQuery(TOUCH_QUERY)
  onBeforeUnmount(() => cleanups.forEach(fn => fn()))
  return { isPhone, isTablet, isTouch }
}
