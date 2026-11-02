<!--
  玩家頁的跳出視窗（定居點、登記藍圖資料、勢力聲望、登記船艦資料…；新增／異動有自己的三步驟視窗 StockWizard.vue）。
  v-model:open 控制開關；右上角 ✕、Esc、點視窗外面都會關閉，開啟時焦點移進視窗、關閉後回到原本的按鈕（useSheet）。
  用 v-show 一直掛著：裡面的元件（例如用 Teleport 移進來的搜尋卡）不會每次開關都重建。手機上是全螢幕。
-->
<template>
  <div v-show="open" class="sfm-backdrop" @click.self="close">
    <div ref="dialogEl" class="sfm-dialog scifi-card" :style="{ maxWidth: width }" role="dialog" aria-modal="true"
      :aria-labelledby="`${id}-title`" tabindex="-1">
      <div class="sfm-head">
        <h3 :id="`${id}-title`" class="sfm-title"><i v-if="icon" :class="icon" class="me-1"></i>{{ title }}</h3>
        <slot name="head" />
        <button type="button" class="btn btn-sm btn-secondary ms-auto" aria-label="關閉" @click="close">
          <i class="bi bi-x-lg"></i></button>
      </div>
      <div class="sfm-body"><slot /></div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useSheet } from '@/composables/useSheet'

const props = defineProps({
  id: { type: String, required: true },
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  icon: { type: String, default: '' },
  /** 視窗最大寬度 */
  width: { type: String, default: '720px' },
})
const emit = defineEmits(['update:open'])

const openRef = computed({ get: () => props.open, set: v => emit('update:open', v) })
const dialogEl = ref(null)
const { close } = useSheet(openRef, dialogEl)
</script>

<style scoped>
.sfm-backdrop {
  position: fixed; inset: 0; z-index: 1080;
  display: flex; align-items: flex-start; justify-content: center;
  padding: 2rem 1rem 1rem; background: rgba(2, 6, 15, .72);
}
.sfm-dialog { width: 100%; max-height: calc(100dvh - 3rem); outline: none; display: flex; flex-direction: column; }
.sfm-head {
  display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .75rem;
  padding: .75rem 1rem; border-bottom: 1px solid var(--sf-border);
}
.sfm-title { font-size: 1.15rem; font-weight: 700; margin: 0; color: var(--sf-text-strong); }
.sfm-body { padding: 1rem; overflow-y: auto; flex: 1 1 auto; }
@media (max-width: 767.98px) {
  .sfm-backdrop { padding: 0; }
  .sfm-dialog { max-width: none !important; max-height: 100dvh; height: 100dvh; border-radius: 0; }
}
</style>
