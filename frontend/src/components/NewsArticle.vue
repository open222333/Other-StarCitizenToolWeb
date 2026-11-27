<!--
  一則新聞的全文（NewsBoard.vue 的全文頁）：封面、標題、時間、標籤、
  Markdown 內文（utils/markdown.js：先跳脫 HTML 再轉，連結只接受 http/https；含表格）、來源連結、分享（複製 ?tab=news&news=<id> 連結）。
-->
<template>
  <article class="na">
    <img v-if="item.cover_url && !coverBroken" :src="item.cover_url" alt="" class="na-cover" loading="lazy" referrerpolicy="no-referrer"
      @error="coverBroken = true">
    <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
      <span v-if="item.pinned" class="sf-chip sf-chip--warn mb-0"><i class="bi bi-pin-angle-fill me-1"></i>置頂</span>
      <span class="na-date"><i class="bi bi-clock me-1"></i>{{ fmtNewsDate(item.published_at) }}</span>
      <span v-if="item.edited_at" class="na-date"><i class="bi bi-pencil me-1"></i>最後編輯 {{ fmtNewsDate(item.edited_at) }}</span>
      <span v-for="t in item.tags" :key="t" class="sf-chip sf-chip--accent mb-0">{{ t }}</span>
    </div>
    <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown 先跳脫整段 HTML，只產生白名單標籤 -->
    <div v-if="item.body" class="na-body" v-html="html"></div>
    <p v-else class="text-muted">（沒有內文）</p>
    <div class="d-flex flex-wrap gap-2 mt-2">
      <a v-if="item.source_url" :href="item.source_url" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-primary">
        <i class="bi bi-box-arrow-up-right me-1"></i>看原文</a>
      <!-- 分享：手機用系統分享選單，其他複製連結（玩家頁新聞分頁 ?news=<id>，不用登入也能開） -->
      <button v-if="item._id" type="button" class="btn btn-sm btn-info" @click="share">
        <i class="bi bi-share me-1"></i>分享</button>
    </div>
  </article>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { PLAYER_HOME } from '@/router'
import { copyText } from '@/utils/clipboard'
import { renderMarkdown } from '@/utils/markdown'
import { fmtNewsDate } from '@/utils/news'

const props = defineProps({ item: { type: Object, required: true } })
const html = computed(() => renderMarkdown(props.item.body))
const coverBroken = ref(false)
watch(() => props.item.cover_url, () => { coverBroken.value = false })

const router = useRouter()
const shareUrl = computed(() => new URL(router.resolve({ path: PLAYER_HOME, query: { tab: 'news', news: props.item._id } }).href,
  window.location.origin).toString())
async function share() {
  const url = shareUrl.value
  // 觸控裝置（手機、平板）有系統分享選單就用；使用者取消不算失敗
  if (navigator.share && window.matchMedia?.('(pointer: coarse)').matches) {
    try {
      await navigator.share({ title: props.item.title || '新聞', url })
      return
    } catch (err) {
      if (err?.name === 'AbortError') return
    }
  }
  copyText(url, { okText: '已複製分享連結' })
}
</script>

<style scoped>
.na-cover { width: 100%; max-height: 22rem; object-fit: cover; border-radius: .5rem; margin-bottom: .75rem; }
.na-date { color: var(--sf-text-muted); font-size: var(--sf-fs-sm); }
.na-body { line-height: 1.75; word-break: break-word; }
.na-body :deep(img) { max-width: 100%; border-radius: .4rem; margin: .4rem 0; }
.na-body :deep(pre) { background: var(--sf-chip-bg); padding: .6rem .8rem; border-radius: .4rem; overflow-x: auto; }
.na-body :deep(code) { background: var(--sf-chip-bg); padding: .05rem .3rem; border-radius: .25rem; }
.na-body :deep(pre code) { background: none; padding: 0; }
.na-body :deep(blockquote) { border-left: 3px solid var(--sf-accent); padding-left: .75rem; color: var(--sf-text-muted); margin: .5rem 0; }
.na-body :deep(h3), .na-body :deep(h4), .na-body :deep(h5), .na-body :deep(h6) { margin: 1rem 0 .4rem; font-weight: 700; }
.na-body :deep(table) { border-collapse: collapse; margin: .6rem 0; font-size: var(--sf-fs-sm); display: block; max-width: 100%; overflow-x: auto; }
.na-body :deep(th), .na-body :deep(td) { border: 1px solid var(--sf-border); padding: .35rem .65rem; vertical-align: top; min-width: 4rem; }
.na-body :deep(th) { background: var(--sf-chip-bg); color: var(--sf-text-strong); font-weight: 700; white-space: nowrap; }
.na-body :deep(tbody tr:nth-child(even)) { background: rgba(var(--sf-accent-rgb), .05); }
.na-body :deep(a) { color: var(--sf-accent-text, var(--sf-accent)); }
</style>
