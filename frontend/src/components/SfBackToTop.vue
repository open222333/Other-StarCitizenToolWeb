<!--
  回到頂部（玩家頁右下角）：往下捲超過一個畫面高度才出現，按了平滑捲回最上面（搜尋卡就在那裡）。
  手機上避開底部導覽列；有「已選 N 張 · 登記」這種底部操作列（.sf-sticky-bar）時再往上讓一點。
  減少動態效果的設定下直接跳回去，不做捲動動畫。
-->
<template>
  <Transition name="sbt">
    <button v-show="visible" type="button" class="btn btn-primary sbt" aria-label="回到頂部" title="回到頂部" @click="toTop">
      <i class="bi bi-arrow-up" aria-hidden="true"></i>
    </button>
  </Transition>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const visible = ref(false)
let ticking = false
function onScroll() {
  if (ticking) return
  ticking = true
  requestAnimationFrame(() => {
    visible.value = window.scrollY > Math.max(400, window.innerHeight * .8)
    ticking = false
  })
}
function toTop() {
  const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' })
}
onMounted(() => { window.addEventListener('scroll', onScroll, { passive: true }); onScroll() })
onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))
</script>

<style scoped>
.sbt {
  position: fixed; right: max(1rem, env(safe-area-inset-right)); bottom: calc(1.25rem + env(safe-area-inset-bottom));
  z-index: 1040; width: 2.9rem; height: 2.9rem; padding: 0; border-radius: 50%;
  display: grid; place-items: center; font-size: 1.15rem;
  box-shadow: 0 .35rem 1rem rgba(0, 0, 0, .45), 0 0 .6rem rgba(var(--sf-accent-rgb), .45);
}
/* 手機：底部導覽列上面 */
@media (max-width: 767.98px) {
  .scifi-page.has-bottom-nav .sbt { bottom: calc(72px + 1rem + env(safe-area-inset-bottom)); }
  .scifi-page:has(.sf-sticky-bar) .sbt { bottom: calc(160px + 1rem + env(safe-area-inset-bottom)); }
}
.sbt-enter-active, .sbt-leave-active { transition: opacity .2s, transform .2s; }
.sbt-enter-from, .sbt-leave-to { opacity: 0; transform: translateY(.5rem); }
@media (prefers-reduced-motion: reduce) { .sbt-enter-active, .sbt-leave-active { transition: none; } }
</style>
