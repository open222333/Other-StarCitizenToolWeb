<!--
  列表分頁列：「共 N 筆 · 第 a–b 筆」＋ 上一頁／下一頁。
  玩家頁用有底色的 btn-primary（CLAUDE.md 按鈕規則）；後台頁傳 admin 改成 btn-outline-secondary。
  @page(newOffset)：父層拿新的 offset 重新查詢。
-->
<template>
  <div class="sf-pager d-flex flex-wrap align-items-center justify-content-between gap-2">
    <span class="sf-pager__info">
      共 {{ total }} 筆<template v-if="total"> · 第 {{ from }}–{{ to }} 筆</template>
    </span>
    <div class="d-flex flex-wrap gap-2">
      <button type="button" :class="btnClass" :disabled="loading || !hasPrev" aria-label="上一頁"
        @click="$emit('page', Math.max(0, offset - limit))">
        <i class="bi bi-chevron-left me-1"></i>上一頁
      </button>
      <button type="button" :class="btnClass" :disabled="loading || !hasNext" aria-label="下一頁"
        @click="$emit('page', offset + limit)">
        下一頁<i class="bi bi-chevron-right ms-1"></i>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  total: { type: Number, default: 0 },
  offset: { type: Number, default: 0 },
  limit: { type: Number, default: 50 },
  loading: { type: Boolean, default: false },
  // 後台頁的樣式（outline 按鈕）
  admin: { type: Boolean, default: false },
})
defineEmits(['page'])

const from = computed(() => (props.total ? Math.min(props.offset + 1, props.total) : 0))
const to = computed(() => Math.min(props.offset + props.limit, props.total))
const hasPrev = computed(() => props.offset > 0)
const hasNext = computed(() => props.offset + props.limit < props.total)
const btnClass = computed(() => ['btn', 'btn-sm', props.admin ? 'btn-outline-secondary' : 'btn-primary'])
</script>

<style scoped>
.sf-pager__info { font-size: .95rem; color: var(--bs-secondary-color); }
</style>
