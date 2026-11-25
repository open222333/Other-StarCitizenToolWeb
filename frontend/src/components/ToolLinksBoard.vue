<!--
  玩家頁「工具網站」：後台維護的外部連結（GET /player/tool-links），從 MyPlayerView 拆出來（待辦 3-6）。
  搜尋（名稱、網址、說明、標籤）＋標籤快速篩選（可多選）；依標籤分組（後台設定的順序，沒有標籤的排最後），
  一個網址有好幾個標籤就出現在每一組，分組標題按了可以收起來。每次切到這個分頁都重抓（清單很小）。
-->
<template>
  <SfState :loading="loadingToolLinks && !toolLinks.length" :error="toolLinksError" :empty="!toolLinks.length"
    empty-text="目前沒有工具網站。" @retry="loadToolLinks">
  <div class="sf-split">
    <!-- 搜尋卡：關鍵字（名稱、網址、說明、標籤）＋標籤快速篩選（按鈕，可多選，上面有數量） -->
    <div class="card scifi-card sf-search mb-3">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-6 col-xl-4">
            <label class="form-label small mb-1" for="tool-q">搜尋</label>
            <input id="tool-q" v-model="toolQuery" type="search" class="form-control form-control-sm"
              placeholder="名稱、網址、說明、標籤…" aria-label="搜尋工具網站">
          </div>
          <div class="col-12">
            <span class="form-label small mb-1 d-block">標籤</span>
            <div class="d-flex flex-wrap gap-2">
              <button type="button" class="btn btn-sm btn-subtab" :class="{ active: !toolSelectedTags.length }"
                :aria-pressed="!toolSelectedTags.length ? 'true' : 'false'" @click="toolSelectedTags = []">
                全部<span class="tool-count">{{ toolLinks.length }}</span></button>
              <button v-for="t in toolTagCounts" :key="t.tag" type="button" class="btn btn-sm btn-subtab"
                :class="{ active: toolSelectedTags.includes(t.tag) }"
                :aria-pressed="toolSelectedTags.includes(t.tag) ? 'true' : 'false'" @click="toggleToolTag(t.tag)">
                {{ t.tag }}<span class="tool-count">{{ t.count }}</span></button>
            </div>
          </div>
        </div>
        <div v-if="toolQuery || toolSelectedTags.length" class="d-flex justify-content-end mt-2">
          <button type="button" class="btn btn-sm btn-warning" @click="toolQuery = ''; toolSelectedTags = []">清除全部</button>
        </div>
      </div>
    </div>

    <div>
      <div v-if="!toolLinkGroups.length" class="text-muted">沒有符合的工具網站。</div>
      <!-- 依標籤分組（後台設定的順序，沒有標籤的排最後）；一個網址有好幾個標籤就出現在每一組，分組標題按了可以收起來 -->
      <section v-for="group in toolLinkGroups" :key="group.name" class="tool-group">
        <button type="button" class="tool-group__head" :aria-expanded="collapsedToolGroups.has(group.name) ? 'false' : 'true'"
          @click="toggleToolGroup(group.name)">
          <i class="bi" :class="collapsedToolGroups.has(group.name) ? 'bi-chevron-right' : 'bi-chevron-down'"></i>
          <span>{{ group.name || '未分類' }}</span>
          <span class="sf-chip">{{ group.links.length }}</span>
        </button>
        <div v-if="!collapsedToolGroups.has(group.name)" class="row g-3">
          <div v-for="link in group.links" :key="link._id" class="col-12 col-md-6 col-xl-4 col-xxl-3">
            <div class="card scifi-card h-100 tool-card">
              <div class="card-body d-flex flex-column gap-2">
                <div class="d-flex align-items-start gap-2">
                  <span class="tool-card__icon" aria-hidden="true">{{ toolInitial(link) }}</span>
                  <div class="flex-grow-1 min-w-0">
                    <div class="tool-card__title">{{ link.title }}</div>
                    <div class="tool-card__host">{{ toolHost(link.url) }}</div>
                  </div>
                  <a :href="link.url" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-primary text-nowrap"
                    :aria-label="`開啟 ${link.title}`"><i class="bi bi-box-arrow-up-right me-1"></i>開啟</a>
                </div>
                <p v-if="link.description" class="tool-card__desc mb-0">{{ link.description }}</p>
                <div v-if="link.tags?.length" class="d-flex flex-wrap gap-1 mt-auto">
                  <button v-for="t in link.tags" :key="t" type="button" class="sf-chip tool-card__tag"
                    :class="{ 'sf-chip--accent': toolSelectedTags.includes(t) }" @click="toggleToolTag(t)">{{ t }}</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
  </SfState>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import SfState from '@/components/SfState.vue'
import { getJson } from '@/utils/getJson'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
})

// ── 工具網站 ────────────────────────────────────────────────
// 每次進分頁都重抓（清單很小），後台剛改完玩家這邊切回來就看得到
const toolLinks        = ref([])
const toolTags         = ref([])   // 標籤順序（後端一起回傳）
const toolQuery        = ref('')
const toolSelectedTags = ref([])
// 先篩選再依標籤分組，預設全部展開
const toolLinkGroups = computed(() => {
  const q = toolQuery.value.trim().toLowerCase()
  const picked = toolSelectedTags.value
  const matches = link => !q || [link.title, link.url, link.description, ...(link.tags || [])]
    .some(v => (v || '').toLowerCase().includes(q))
  const groups = new Map(toolTags.value.map(t => [t, { name: t, links: [] }]))
  const untagged = { name: '', links: [] }
  for (const link of toolLinks.value) {
    if (!matches(link)) continue
    const tags = link.tags || []
    if (!tags.length) {
      if (!picked.length) untagged.links.push(link)
      continue
    }
    for (const tag of tags) {
      if (picked.length && !picked.includes(tag)) continue
      if (!groups.has(tag)) groups.set(tag, { name: tag, links: [] })
      groups.get(tag).links.push(link)
    }
  }
  return [...groups.values(), untagged].filter(g => g.links.length)
})
// 標籤快速篩選按鈕上的數量（後台設定的順序）
const toolTagCounts = computed(() => toolTags.value
  .map(tag => ({ tag, count: toolLinks.value.filter(l => (l.tags || []).includes(tag)).length }))
  .filter(t => t.count))
function toggleToolTag(tag) {
  const i = toolSelectedTags.value.indexOf(tag)
  toolSelectedTags.value = i >= 0 ? toolSelectedTags.value.filter(t => t !== tag) : [...toolSelectedTags.value, tag]
}
function toolHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
}
// 卡片左上角的字母圖示（不去抓外站的 favicon）
const toolInitial = link => ((link.title || toolHost(link.url) || '?').trim()[0] || '?').toUpperCase()
const collapsedToolGroups = reactive(new Set())
function toggleToolGroup(name) {
  if (collapsedToolGroups.has(name)) collapsedToolGroups.delete(name)
  else collapsedToolGroups.add(name)
}
const loadingToolLinks = ref(false)
const toolLinksError   = ref('')

async function loadToolLinks() {
  loadingToolLinks.value = true
  const r = await getJson(props.fetcher, '/player/tool-links', undefined, '讀取工具網站失敗')
  loadingToolLinks.value = false
  if (r.ok) {
    toolLinks.value = r.data || []
    toolTags.value = r.body.tags || []
    toolLinksError.value = ''
  } else if (!toolLinks.value.length) {
    toolLinksError.value = r.message
  }
}

watch(() => props.active, (v) => { if (v) loadToolLinks() }, { immediate: true })
</script>

<style scoped>
/* 工具網站：分組標題、卡片 */
.tool-count { margin-left: .4rem; opacity: .7; }
.tool-group { margin-bottom: 1.5rem; }
.tool-group__head {
  display: flex; align-items: center; gap: .5rem; width: 100%; margin-bottom: .6rem; padding: .35rem 0;
  background: none; border: 0; border-bottom: 1px solid var(--sf-border);
  color: var(--sf-text-strong); font-size: 1.1rem; font-weight: 700; text-align: left;
}
.tool-card { transition: border-color .15s, transform .15s; }
.tool-card:hover { border-color: var(--sf-accent); transform: translateY(-1px); }
.tool-card__icon {
  flex: 0 0 2.4rem; height: 2.4rem; display: inline-flex; align-items: center; justify-content: center;
  border-radius: .5rem; font-weight: 700; font-size: 1.1rem;
  color: var(--sf-accent); background: rgba(var(--sf-accent-rgb), .14); border: 1px solid rgba(var(--sf-accent-rgb), .35);
}
.tool-card__title { font-weight: 700; font-size: 1.05rem; color: var(--sf-text-strong); overflow-wrap: anywhere; }
.tool-card__host { font-size: .9rem; color: var(--sf-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-card__desc { font-size: .95rem; color: var(--sf-text); }
.tool-card__tag { cursor: pointer; font: inherit; font-size: .9rem; }
.min-w-0 { min-width: 0; }
</style>
