// 表單設定記在這台瀏覽器（localStorage）的共用寫法（待辦 3-3、B2）。
//
//   const saved = readStored('sc_route_v1')                // 讀不到／壞掉回 {}
//   const view = ref(saved.view ?? 'flow')
//   persistState('sc_route_v1', () => ({ view: view.value, ... }))
//
// persistState 用 getter 監看：getter 裡讀到的 ref 都會自動追蹤，不用再把十幾個 ref 列在 watch 的陣列裡
// （以前每加一個設定要改三個地方，漏列就不會存）。存不了（隱私模式、空間滿）就算了，不影響畫面。
import { watch } from 'vue'

export function readStored(key, fallback = {}) {
  try {
    const v = JSON.parse(localStorage.getItem(key) || 'null')
    return v && typeof v === 'object' ? v : fallback
  } catch {
    return fallback
  }
}

export function persistState(key, snapshot) {
  return watch(snapshot, (value) => {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch { /* 存不了就算了 */ }
  }, { deep: true })
}
