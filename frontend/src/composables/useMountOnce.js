// 「第一次切到才建立，之後一直留著」的分頁（待辦 C6）：
//   const mountedOnce = useMountOnce(activePane)
//   <div v-if="mountedOnce('squads')" v-show="activePane === 'squads'">…
// source 變成那個值一次之後就永遠回 true（v-if 掛上去、之後靠 v-show 切換，不會因為切走就被拆掉重建）。
import { reactive, watch } from 'vue'

export function useMountOnce(source) {
  const seen = reactive(new Set())
  watch(source, v => { if (v) seen.add(v) }, { immediate: true })
  return key => seen.has(key)
}
