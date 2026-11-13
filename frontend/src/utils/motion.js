// 使用者在系統設定「減少動態效果」（prefers-reduced-motion）時，捲動改成直接跳過去，不做平滑捲動。
// CSS 的動畫與轉場在 scifi-theme.css 統一關掉；JS 呼叫 scrollIntoView／scrollTo 時用這個取 behavior。
export function prefersReducedMotion() {
  return typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

/** scrollIntoView／scrollTo 的 behavior：一般是 'smooth'，減少動態效果時是 'auto' */
export function scrollBehavior() {
  return prefersReducedMotion() ? 'auto' : 'smooth'
}
