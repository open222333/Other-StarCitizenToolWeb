<!--
  「艦長室」上方的公告區：置頂在前、最新的補滿，最多 3 則，一行一則；點了 emit('open', id)，
  由 MyPlayerView 切到「新聞」分頁顯示全文（?tab=news&news=<id>，不用跳出視窗）；「全部新聞」切到「新聞」分頁。沒有新聞時整塊不顯示。資料同 NewsBoard.vue（GET /news/）。
-->
<template>
  <div v-if="items.length" :class="[cardClass, 'nbn', 'mb-3']">
    <div class="card-body py-2 px-3">
      <div class="d-flex align-items-center gap-2 mb-1">
        <span class="nbn-head"><i class="bi bi-megaphone-fill me-1"></i>公告</span>
        <button type="button" class="btn btn-sm btn-primary ms-auto" @click="emit('all')">全部新聞<i class="bi bi-chevron-right ms-1"></i></button>
      </div>
      <button v-for="n in items" :key="n._id" type="button" class="nbn-row" @click="emit('open', n._id)">
        <i v-if="n.pinned" class="bi bi-pin-angle-fill nbn-pin" aria-label="置頂"></i>
        <span class="nbn-title">{{ n.title }}</span>
        <span class="nbn-date">{{ fmtNewsDate(n.published_at) }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { fetchNewsFeatured, fmtNewsDate } from '@/utils/news'

const props = defineProps({
  fetcher: { type: Function, required: true },
  cardClass: { type: String, default: 'card' },
})
const emit = defineEmits(['all', 'open'])

const items = ref([])
// 跟新聞分頁的置頂區同一套：官方優先、再置頂、再最新（後端 GET /news/featured）
onMounted(async () => {
  const r = await fetchNewsFeatured(props.fetcher, 3)
  if (r.ok) items.value = r.data
})
</script>

<style scoped>
.nbn { border-left: 3px solid var(--sf-accent) !important; }
.nbn-head { font-weight: 700; color: var(--sf-accent-text, var(--sf-accent)); font-size: var(--sf-fs-sm); }
.nbn-row { display: flex; align-items: baseline; gap: .5rem; width: 100%; padding: .25rem 0; background: none; border: 0;
  color: inherit; text-align: left; border-top: 1px dashed var(--sf-border); }
.nbn-row:first-of-type { border-top: 0; }
.nbn-row:hover .nbn-title { color: var(--sf-accent-text, var(--sf-accent)); }
.nbn-pin { color: rgb(var(--bs-warning-rgb)); }
.nbn-title { flex: 1 1 auto; min-width: 0; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nbn-date { flex: 0 0 auto; color: var(--sf-text-muted); font-size: var(--sf-fs-sm); }
</style>
