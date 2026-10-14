<!--
  搜尋卡的「其他篩選條件」。電腦／平板照原樣直接顯示（預設 slot 是一般的 col-* 欄位，
  放在搜尋卡的 .row 裡）；手機只顯示一顆「篩選（已套用數）」按鈕，條件收進底部滑出面板。
  slot more：只有手機的面板裡才顯示的額外內容（例如勾選框，電腦版由父層自己放在原位）。
-->
<template>
  <slot v-if="!isPhone" />
  <template v-else>
    <div :class="buttonCol">
      <button type="button" class="btn btn-info w-100 text-nowrap" :aria-expanded="open ? 'true' : 'false'"
        @click="open = true">
        <i class="bi bi-funnel me-1"></i>篩選<span v-if="count" class="sf-count-badge">{{ count }}</span>
      </button>
    </div>
    <div v-show="open" class="sf-sheet-backdrop" @click="open = false"></div>
    <div v-show="open" class="sf-sheet" role="dialog" aria-modal="true" :aria-label="title">
      <div class="sf-sheet__grip"></div>
      <div class="sf-sheet__head">
        <h3 class="sf-sheet__title">{{ title }}</h3>
        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="open = false">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="row g-2"><slot /></div>
      <slot name="more" />
      <div class="d-flex gap-2 mt-3">
        <button type="button" class="btn btn-warning flex-grow-1" :disabled="!count" @click="$emit('clear')">清除篩選</button>
        <button type="button" class="btn btn-primary flex-grow-1" @click="open = false">完成</button>
      </div>
    </div>
  </template>
</template>

<script setup>
import { ref } from 'vue'
import { useBreakpoint } from '@/composables/useBreakpoint'

defineProps({
  // 已套用的條件數（按鈕上的數字；0 時「清除篩選」停用）
  count: { type: Number, default: 0 },
  title: { type: String, default: '篩選' },
  // 手機上按鈕那一欄的 class（跟名稱欄同一列）
  buttonCol: { type: String, default: 'col-auto' },
})
defineEmits(['clear'])

const { isPhone } = useBreakpoint()
const open = ref(false)
</script>
