<!--
  一則新聞的全文（NewsBoard.vue、NewsBanner.vue 的跳出視窗共用）：封面、標題、時間、標籤、
  Markdown 內文（utils/markdown.js：先跳脫 HTML 再轉，連結只接受 http/https）、來源連結。
-->
<template>
  <article class="na">
    <img v-if="item.cover_url && !coverBroken" :src="item.cover_url" alt="" class="na-cover" loading="lazy" referrerpolicy="no-referrer"
      @error="coverBroken = true">
    <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
      <span v-if="item.pinned" class="sf-chip sf-chip--warn mb-0"><i class="bi bi-pin-angle-fill me-1"></i>置頂</span>
      <span class="na-date"><i class="bi bi-clock me-1"></i>{{ fmtNewsDate(item.published_at) }}</span>
      <span v-for="t in item.tags" :key="t" class="sf-chip sf-chip--accent mb-0">{{ t }}</span>
    </div>
    <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown 先跳脫整段 HTML，只產生白名單標籤 -->
    <div v-if="item.body" class="na-body" v-html="html"></div>
    <p v-else class="text-muted">（沒有內文）</p>
    <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-primary mt-2">
      <i class="bi bi-box-arrow-up-right me-1"></i>看原文</a>
  </article>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { fmtNewsDate } from '@/utils/news'

const props = defineProps({ item: { type: Object, required: true } })
const html = computed(() => renderMarkdown(props.item.body))
const coverBroken = ref(false)
watch(() => props.item.cover_url, () => { coverBroken.value = false })
</script>

<style scoped>
.na-cover { width: 100%; max-height: 22rem; object-fit: cover; border-radius: .5rem; margin-bottom: .75rem; }
.na-date { color: var(--sf-text-muted); font-size: .9rem; }
.na-body { line-height: 1.75; word-break: break-word; }
.na-body :deep(img) { max-width: 100%; border-radius: .4rem; margin: .4rem 0; }
.na-body :deep(pre) { background: var(--sf-chip-bg); padding: .6rem .8rem; border-radius: .4rem; overflow-x: auto; }
.na-body :deep(code) { background: var(--sf-chip-bg); padding: .05rem .3rem; border-radius: .25rem; }
.na-body :deep(pre code) { background: none; padding: 0; }
.na-body :deep(blockquote) { border-left: 3px solid var(--sf-accent); padding-left: .75rem; color: var(--sf-text-muted); margin: .5rem 0; }
.na-body :deep(h3), .na-body :deep(h4), .na-body :deep(h5), .na-body :deep(h6) { margin: 1rem 0 .4rem; font-weight: 700; }
.na-body :deep(a) { color: var(--sf-accent-text, var(--sf-accent)); }
</style>
