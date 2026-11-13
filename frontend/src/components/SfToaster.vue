<!--
  全站共用的 Toast 顯示區（掛在 App.vue；發訊息用 utils/toast.js 的 toast()）。
  - 桌機在右下角，手機在底部置中（玩家頁有底部導覽列時浮在它上面）。
  - 成功／一般訊息用 role="status"（螢幕報讀器有空才念），錯誤用 role="alert"（馬上念）。
  - 每則都有圖示＋文字，不只靠顏色分辨；滑鼠移上去或鍵盤 focus 時暫停倒數。
  - 玩家頁（/player/*）用科幻主題的顏色，後台用後台主題的 Bootstrap 顏色。
-->
<template>
  <div class="sf-toaster" :class="{ 'sf-toaster--scifi': scifi }" aria-live="polite">
    <TransitionGroup name="sf-toast">
      <div v-for="t in toasts" :key="t.id" class="sf-toast" :class="`sf-toast--${t.type}`"
        :role="t.type === 'danger' ? 'alert' : 'status'"
        @mouseenter="holdToast(t.id)" @mouseleave="releaseToast(t.id)"
        @focusin="holdToast(t.id)" @focusout="releaseToast(t.id)">
        <i class="bi sf-toast__icon" :class="ICONS[t.type]" aria-hidden="true"></i>
        <span class="sf-toast__text">{{ t.text }}<span v-if="t.count > 1" class="sf-toast__count"> ×{{ t.count }}</span></span>
        <button type="button" class="sf-toast__close" aria-label="關閉提示" @click="dismissToast(t.id)">
          <i class="bi bi-x-lg" aria-hidden="true"></i></button>
      </div>
    </TransitionGroup>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { dismissToast, holdToast, releaseToast, toasts } from '@/utils/toast'

const ICONS = {
  success: 'bi-check-circle-fill',
  info: 'bi-info-circle-fill',
  warning: 'bi-exclamation-triangle-fill',
  danger: 'bi-x-octagon-fill',
}
const route = useRoute()
const scifi = computed(() => route.path.startsWith('/player'))
</script>

<style scoped>
.sf-toaster {
  /* 後台：沿用後台主題的 Bootstrap 變數 */
  --t-bg: var(--bs-body-bg, #fff);
  --t-text: var(--bs-body-color, #212529);
  --t-border: var(--bs-border-color, #dee2e6);
  --t-shadow: 0 .5rem 1.5rem rgba(0, 0, 0, .18);
  --t-success: var(--bs-success-rgb, 25, 135, 84);
  --t-info: var(--bs-info-rgb, 13, 202, 240);
  --t-warning: var(--bs-warning-rgb, 255, 193, 7);
  --t-danger: var(--bs-danger-rgb, 220, 53, 69);
  position: fixed; right: 1rem; bottom: 1rem; z-index: 1090;
  display: flex; flex-direction: column; align-items: flex-end; gap: .5rem;
  width: min(26rem, calc(100vw - 2rem)); pointer-events: none;
}
/* 玩家頁：科幻主題（顏色同 scifi-theme.css 的 .scifi-page） */
.sf-toaster--scifi {
  --t-bg: var(--sf-panel);
  --t-text: var(--sf-text);
  --t-border: var(--sf-border-hi);
  --t-shadow: 0 .5rem 1.5rem var(--sf-shadow, rgba(0, 0, 0, .45));
  --t-success: 52, 211, 153;
  --t-info: var(--sf-accent-rgb);
  --t-warning: var(--sf-accent-2-rgb);
  --t-danger: 248, 113, 113;
}
.sf-toast {
  --t-c: var(--t-info);
  pointer-events: auto; display: flex; align-items: flex-start; gap: .6rem; width: 100%;
  padding: .7rem .5rem .7rem .85rem; border-radius: .5rem;
  background: var(--t-bg); color: var(--t-text);
  border: 1px solid var(--t-border); border-left: 4px solid rgb(var(--t-c));
  box-shadow: var(--t-shadow); font-size: .95rem; line-height: 1.5;
}
.sf-toast--success { --t-c: var(--t-success); }
.sf-toast--warning { --t-c: var(--t-warning); }
.sf-toast--danger { --t-c: var(--t-danger); }
.sf-toast__icon { color: rgb(var(--t-c)); font-size: 1.1rem; line-height: 1.35; flex: 0 0 auto; }
.sf-toast__text { flex: 1 1 auto; min-width: 0; overflow-wrap: anywhere; padding-top: .05rem; }
.sf-toast__count { opacity: .7; }
.sf-toast__close {
  flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center;
  width: 2rem; height: 2rem; margin: -.3rem 0 -.3rem 0; border: 0; border-radius: .35rem;
  background: none; color: inherit; opacity: .7;
}
.sf-toast__close:hover { opacity: 1; background: rgba(var(--t-c), .12); }
.sf-toast__close:focus-visible { outline: 2px solid rgb(var(--t-c)); outline-offset: 1px; opacity: 1; }
@media (pointer: coarse) {
  .sf-toast__close { width: 44px; height: 44px; margin: -.65rem -.25rem -.65rem 0; }
}

/* 手機：底部置中；玩家頁有底部導覽列時浮在它上面 */
@media (max-width: 767.98px) {
  .sf-toaster { left: .75rem; right: .75rem; bottom: calc(.75rem + env(safe-area-inset-bottom)); width: auto; align-items: stretch; }
  /* 玩家頁有底部導覽列時浮在它上面（body:has 的規則在 scifi-theme.css，scoped 樣式寫不到 body） */
}

.sf-toast-enter-active, .sf-toast-leave-active { transition: opacity .2s ease, transform .2s ease; }
.sf-toast-enter-from, .sf-toast-leave-to { opacity: 0; transform: translateY(.5rem); }
@media (prefers-reduced-motion: reduce) {
  .sf-toast-enter-active, .sf-toast-leave-active { transition: none; }
}
</style>
