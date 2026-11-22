<!--
  後台「新聞」：管理玩家頁「新聞」分頁與「艦長室」上方公告的內容（後端 app/news/view.py）。
  - 新增／編輯：標題、內文（Markdown，可預覽；轉換見 utils/markdown.js）、封面圖片網址、來源連結、標籤、置頂、發布時間
    （未來的時間＝排程，到時間才出現在玩家頁）。admin、operator 可以寫，viewer 只能看。
  - 外部程式寫入新聞（POST /news/ingest，標頭 X-API-Key）用的金鑰在後台「API 金鑰」頁（views/ApiKeysView.vue）。
-->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold"><i class="bi bi-newspaper me-2 text-primary"></i>新聞</h5>
      <div class="d-flex flex-wrap gap-2">
        <button v-if="canWrite" class="btn btn-primary btn-sm" @click="startNew"><i class="bi bi-plus-lg me-1"></i>新增新聞</button>
        <button class="btn btn-outline-secondary btn-sm" :disabled="loading" @click="load()">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-arrow-clockwise me-1"></i>重新整理</button>
      </div>
    </div>

    <!-- 新增／編輯 -->
    <div v-if="canWrite && editorOpen" class="card shadow-sm border-0 mb-3">
      <div class="card-body">
        <h6 class="fw-semibold mb-3">{{ editingId ? '編輯新聞' : '新增新聞' }}</h6>
        <form class="row g-2" @submit.prevent="submit">
          <div class="col-12">
            <label class="form-label small fw-semibold" for="nw-title">標題</label>
            <input id="nw-title" v-model="form.title" type="text" class="form-control form-control-sm" maxlength="200" required>
          </div>
          <div class="col-12">
            <div class="d-flex align-items-center gap-2 mb-1">
              <label class="form-label small fw-semibold mb-0" for="nw-body">內文（Markdown）</label>
              <div class="btn-group btn-group-sm ms-auto" role="group" aria-label="內文顯示">
                <button type="button" class="btn" :class="preview ? 'btn-outline-secondary' : 'btn-secondary'" @click="preview = false">編輯</button>
                <button type="button" class="btn" :class="preview ? 'btn-secondary' : 'btn-outline-secondary'" @click="preview = true">預覽</button>
              </div>
            </div>
            <textarea v-show="!preview" id="nw-body" v-model="form.body" rows="10" class="form-control form-control-sm font-monospace"
              maxlength="20000" placeholder="**粗體**、- 清單、[連結](https://…)、![圖片](https://…)"></textarea>
            <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown 先跳脫 HTML -->
            <div v-show="preview" class="nw-preview" v-html="previewHtml || '<span class=&quot;text-muted&quot;>（沒有內文）</span>'"></div>
          </div>
          <div class="col-12 col-md-6">
            <label class="form-label small fw-semibold" for="nw-cover">封面圖片網址</label>
            <input id="nw-cover" v-model.trim="form.cover_url" type="url" class="form-control form-control-sm" placeholder="https://">
          </div>
          <div class="col-12 col-md-6">
            <label class="form-label small fw-semibold" for="nw-source">來源連結</label>
            <input id="nw-source" v-model.trim="form.source_url" type="url" class="form-control form-control-sm" placeholder="https://">
          </div>
          <div class="col-12 col-md-6">
            <label class="form-label small fw-semibold" for="nw-tags">標籤（逗號分隔）</label>
            <input id="nw-tags" v-model="form.tags" type="text" class="form-control form-control-sm" placeholder="改版, 活動">
            <div v-if="allTags.length" class="d-flex flex-wrap gap-1 mt-1">
              <button v-for="t in allTags" :key="t.tag" type="button" class="btn btn-sm py-0"
                :class="formTagList.includes(t.tag) ? 'btn-primary' : 'btn-outline-secondary'" @click="toggleFormTag(t.tag)">{{ t.tag }}</button>
            </div>
          </div>
          <div class="col-8 col-md-4">
            <label class="form-label small fw-semibold" for="nw-pub">發布時間（空白＝現在）</label>
            <input id="nw-pub" v-model="form.published_local" type="datetime-local" class="form-control form-control-sm">
          </div>
          <div class="col-4 col-md-2 d-flex align-items-end">
            <div class="form-check mb-1">
              <input id="nw-pin" v-model="form.pinned" class="form-check-input" type="checkbox">
              <label class="form-check-label" for="nw-pin">置頂</label>
            </div>
          </div>
          <div class="col-12 d-flex gap-2 mt-2">
            <button type="submit" class="btn btn-primary btn-sm" :disabled="saving">
              <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>{{ editingId ? '儲存' : '新增' }}</button>
            <button type="button" class="btn btn-outline-secondary btn-sm" @click="closeEditor">取消</button>
          </div>
        </form>
      </div>
    </div>

    <AdminSearchCard :active="!!(query || tagSel.length)" @clear="query = ''; tagSel = []">
      <AdminSearchField label="關鍵字" for-id="nw-q" col="col-12 col-md-6">
        <input id="nw-q" v-model.trim="query" type="search" class="form-control form-control-sm" placeholder="標題、內文、標籤">
      </AdminSearchField>
      <AdminSearchField label="標籤" for-id="nw-tag" col="col-12 col-md-6">
        <MultiSelectFilter id="nw-tag" v-model="tagSel" :options="allTags.map(t => ({ value: t.tag, label: `${t.tag}（${t.count}）` }))"
          label="標籤" placeholder="全部" block />
      </AdminSearchField>
      <template #summary>{{ filtering ? '符合' : '共' }} {{ total }} 則</template>
    </AdminSearchCard>

    <div class="card shadow-sm border-0 mb-4">
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">標題</th>
                <th>標籤</th>
                <th class="text-nowrap">發布時間</th>
                <th class="text-nowrap">來源</th>
                <th v-if="canWrite" class="pe-3" style="width: 120px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading && !items.length"><td :colspan="canWrite ? 5 : 4" class="text-center py-4 text-muted">
                <span class="spinner-border spinner-border-sm me-2"></span>載入中…</td></tr>
              <tr v-else-if="!items.length"><td :colspan="canWrite ? 5 : 4" class="text-center py-4 text-muted">
                {{ filtering ? '沒有符合篩選條件的新聞' : '尚無新聞' }}</td></tr>
              <tr v-for="n in items" :key="n._id">
                <td class="ps-3">
                  <i v-if="n.pinned" class="bi bi-pin-angle-fill text-warning me-1" title="置頂"></i>
                  <span class="fw-semibold">{{ n.title }}</span>
                  <span v-if="n.scheduled" class="badge text-bg-info ms-1">排程中</span>
                  <a v-if="n.source_url" :href="n.source_url" target="_blank" rel="noopener noreferrer" class="ms-1 small">
                    <i class="bi bi-box-arrow-up-right"></i></a>
                </td>
                <td><span v-for="t in n.tags" :key="t" class="badge text-bg-secondary me-1">{{ t }}</span></td>
                <td class="text-nowrap small">{{ fmtNewsDate(n.published_at) }}</td>
                <td class="small text-muted text-nowrap">{{ n.created_by }}</td>
                <td v-if="canWrite" class="pe-3 text-nowrap">
                  <button class="btn btn-sm btn-outline-primary me-1" :aria-label="`編輯 ${n.title}`" @click="startEdit(n)"><i class="bi bi-pencil"></i></button>
                  <button class="btn btn-sm btn-outline-danger" :aria-label="`刪除 ${n.title}`" @click="remove(n)"><i class="bi bi-trash"></i></button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <SfPager class="mb-3" :total="total" :offset="offset" :limit="PAGE" :loading="loading" admin @page="load" />

    <ConfirmModal ref="confirmModalRef" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { newsApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { toast } from '@/utils/toast'
import { renderMarkdown } from '@/utils/markdown'
import { fmtNewsDate } from '@/utils/news'
import { scrollBehavior } from '@/utils/motion'
import { escapeHtml } from '@/utils/html'
import SfPager from '@/components/SfPager.vue'
import AdminSearchCard from '@/components/AdminSearchCard.vue'
import AdminSearchField from '@/components/AdminSearchField.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')
const confirmModalRef = ref(null)

// 列表：後端篩選＋分頁（關鍵字、標籤多選取聯集），每頁 PAGE 則
const PAGE = 50
const items = ref([])
const allTags = ref([])
const loading = ref(false)
const total = ref(0)
const offset = ref(0)
const query = ref('')
const tagSel = ref([])
async function load(newOffset = offset.value) {
  loading.value = true
  const res = await newsApi.listAdmin({ q: query.value, tag: tagSel.value, limit: PAGE, offset: newOffset })
  const body = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!res?.ok || !body?.success) { toast(body?.message || '讀取新聞失敗', 'error'); return }
  items.value = body.data || []
  total.value = body.total || 0
  offset.value = newOffset
  allTags.value = body.tags || []
}
onMounted(() => load(0))
let qTimer = null
watch([query, tagSel], () => { clearTimeout(qTimer); qTimer = setTimeout(() => load(0), 250) })
const filtering = computed(() => !!(query.value || tagSel.value.length))

// ── 新增／編輯 ──
const editorOpen = ref(false)
const editingId = ref('')
const saving = ref(false)
const preview = ref(false)
const blank = () => ({ title: '', body: '', cover_url: '', source_url: '', tags: '', pinned: false, published_local: '' })
const form = reactive(blank())
const previewHtml = computed(() => renderMarkdown(form.body))
const splitTags = text => [...new Set((text || '').replace(/，/g, ',').split(',').map(t => t.trim()).filter(Boolean))]
const formTagList = computed(() => splitTags(form.tags))
function toggleFormTag(tag) {
  const list = formTagList.value
  form.tags = (list.includes(tag) ? list.filter(t => t !== tag) : [...list, tag]).join(', ')
}
// datetime-local（瀏覽器時區）↔ ISO（UTC）
const toLocalInput = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`
}
function startNew() {
  Object.assign(form, blank())
  editingId.value = ''
  preview.value = false
  editorOpen.value = true
}
function startEdit(n) {
  Object.assign(form, { title: n.title, body: n.body || '', cover_url: n.cover_url || '', source_url: n.source_url || '',
    tags: (n.tags || []).join(', '), pinned: !!n.pinned, published_local: toLocalInput(n.published_at) })
  editingId.value = n._id
  preview.value = false
  editorOpen.value = true
  window.scrollTo({ top: 0, behavior: scrollBehavior() })
}
function closeEditor() {
  editorOpen.value = false
  editingId.value = ''
}
async function submit() {
  saving.value = true
  const payload = { title: form.title, body: form.body, cover_url: form.cover_url, source_url: form.source_url,
    tags: formTagList.value, pinned: form.pinned,
    published_at: form.published_local ? new Date(form.published_local).toISOString() : '' }
  const res = editingId.value ? await newsApi.update(editingId.value, payload) : await newsApi.create(payload)
  const body = res ? await res.json().catch(() => null) : null
  saving.value = false
  if (!res?.ok || !body?.success) { toast(body?.message || '儲存失敗', 'error'); return }
  toast(editingId.value ? '已儲存' : '已新增')
  closeEditor()
  load()
}
async function remove(n) {
  if (!(await confirmModalRef.value?.confirm(`確定要刪除 <strong>${escapeHtml(n.title)}</strong>？`))) return
  const res = await newsApi.remove(n._id)
  const body = res ? await res.json().catch(() => null) : null
  if (!res?.ok || !body?.success) { toast(body?.message || '刪除失敗', 'error'); return }
  toast('已刪除')
  load()
}

</script>

<style scoped>
.nw-preview { border: 1px solid var(--bs-border-color); border-radius: .375rem; padding: .5rem .75rem; min-height: 10rem; line-height: 1.7; }
.nw-preview :deep(img) { max-width: 100%; }
</style>
