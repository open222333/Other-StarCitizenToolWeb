<!--
  欄位標題旁邊的「?」說明。滑鼠移過去顯示，點一下也會顯示。

  為什麼不直接用原生的 title 屬性：手機沒有 hover，原生 title 在觸控裝置上
  完全不會出現，那些說明就等於消失了。這頁的版面（sticky 工具列、橫向捲動的
  分頁列）明顯是為手機做的，所以做成 hover + click 兩種都行。

  也不用 Bootstrap 的 Tooltip：那需要逐個 element 手動 new Tooltip()，
  元件卸載時還要 dispose，v-if 進出時很容易漏。純 CSS + 一個 ref 更好維護。
-->
<template>
  <span class="field-hint">
    <button
      type="button"
      class="field-hint__btn"
      :aria-label="`說明：${text}`"
      :aria-expanded="shown ? 'true' : 'false'"
      @click.stop.prevent="pinned = !pinned"
      @mouseenter="hovered = true"
      @mouseleave="hovered = false"
      @blur="pinned = false"
      @keydown.esc="pinned = false"
    >?</button>

    <span v-if="shown" class="field-hint__bubble" role="tooltip">{{ text }}</span>
  </span>
</template>

<script setup>
import { computed, ref } from 'vue'

defineProps({ text: { type: String, required: true } })

const hovered = ref(false)
const pinned  = ref(false)
const shown   = computed(() => hovered.value || pinned.value)
</script>

<style scoped>
.field-hint {
  position: relative;
  display: inline-block;
  /* 標題是 small，這裡跟著縮但不要跟著變細 */
  font-weight: 400;
  vertical-align: middle;
}

.field-hint__btn {
  width: 1.15em;
  height: 1.15em;
  padding: 0;
  border: 1px solid var(--sf-border, rgba(255, 255, 255, .3));
  border-radius: 50%;
  background: transparent;
  color: var(--sf-text-muted, #b6c4d6);
  font-size: .82em;
  line-height: 1;
  cursor: help;
  /* 圓圈內的問號在不同字型下容易偏，用 flex 置中最穩 */
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.field-hint__btn:hover,
.field-hint__btn:focus-visible {
  border-color: var(--sf-accent, #3ea6ff);
  color: var(--sf-accent, #3ea6ff);
  outline: none;
}

.field-hint__bubble {
  position: absolute;
  z-index: 40;
  /* 從問號的左緣往右展開，不要置中 —— 置中在靠左的欄位會被切掉 */
  left: 0;
  top: calc(100% + 6px);
  /* width: max-content 是必要的，不是多餘：absolute 元素的 shrink-to-fit
     寬度是以「containing block 的可用寬度」為上限算的，而這裡的 containing
     block 是 .field-hint（就一個問號，約 16px），所以不給 width 的話它會
     一路縮到 min-width，max-width 永遠用不到，長句子被擠成很多行。 */
  width: max-content;
  min-width: 12rem;
  max-width: min(22rem, 70vw);
  padding: .4rem .55rem;
  border: 1px solid var(--sf-border, rgba(255, 255, 255, .25));
  border-radius: .35rem;
  background: var(--sf-surface-2, #16202e);
  color: var(--sf-text, #e6edf5);
  box-shadow: 0 .4rem 1rem rgba(0, 0, 0, .45);
  font-size: .8rem;
  font-weight: 400;
  line-height: 1.45;
  /* 說明是完整句子，要能折行；也不要讓它吃到滑鼠事件 */
  white-space: normal;
  text-align: left;
  pointer-events: none;
}

/* 手機上改成貼齊畫面下緣的一條說明，而不是跟著問號浮出來。
   原因：問號可能落在畫面中間，浮動氣泡不管往左或往右對齊都有機會超出畫面，
   要正確處理就得用 JS 量位置。position: fixed 不需要有定位祖先，直接以
   viewport 為基準，left/right 都給 1rem 就一定放得下、絕不被切掉。
   問號本身留在標題旁邊不動，所以還是看得出是在說明哪個欄位。 */
@media (max-width: 575.98px) {
  .field-hint__bubble {
    position: fixed;
    left: 1rem;
    right: 1rem;
    top: auto;
    bottom: 1rem;
    width: auto;
    min-width: 0;
    max-width: none;
    font-size: .875rem;
  }
}
</style>
