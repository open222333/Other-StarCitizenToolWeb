<!--
  後台「新聞」：管理玩家頁「新聞」分頁與「艦長室」上方公告的內容（後端 app/news/view.py）。
  - 新增／編輯：標題、內文（Markdown，可預覽；轉換見 utils/markdown.js）、封面圖片網址、來源連結、標籤、置頂、發布時間
    （未來的時間＝排程，到時間才出現在玩家頁）。admin、operator 可以寫，viewer 只能看。
  - API 金鑰（只有 admin）：給外部程式寫入新聞用（POST /news/ingest，標頭 X-API-Key）。金鑰只在建立時顯示一次，
    資料庫只存雜湊；停用後立刻失效。下面附呼叫範例。
-->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold"><i class="bi bi-newspaper me-2 text-primary"></i>新聞</h5>
      <div class="d-flex flex-wrap gap-2">
        <button v-if="canWrite" class="btn btn-primary btn-sm" @click="startNew"><i class="bi bi-plus-lg me-1"></i>新增新聞</button>
        <button class="btn btn-outline-secondary btn-sm" :disabled="loading" @click="load">
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
      <template #summary>共 {{ items.length }} 則，符合 {{ shown.length }} 則</template>
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
              <tr v-else-if="!shown.length"><td :colspan="canWrite ? 5 : 4" class="text-center py-4 text-muted">
                {{ items.length ? '沒有符合篩選條件的新聞' : '尚無新聞' }}</td></tr>
              <tr v-for="n in shown" :key="n._id">
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

    <!-- API 金鑰（只有 admin）：外部程式寫入新聞 -->
    <div v-if="auth.isAdmin" class="card shadow-sm border-0 mb-3">
      <div class="card-body">
        <h6 class="fw-semibold mb-1"><i class="bi bi-key me-1"></i>API 金鑰（外部程式寫入新聞）</h6>
        <p class="small text-muted mb-3">外部程式用金鑰呼叫 <code>POST /news/ingest</code>；同一個來源連結再送一次是更新，不會重複。
          金鑰只在建立時顯示一次，請馬上複製保存；不用了就停用（立刻失效）。</p>
        <form class="d-flex flex-wrap gap-2 align-items-end mb-3" @submit.prevent="createKey">
          <div>
            <label class="form-label small fw-semibold mb-1" for="nw-key-name">名稱</label>
            <input id="nw-key-name" v-model.trim="keyName" type="text" maxlength="50" class="form-control form-control-sm" placeholder="例如：RSI 新聞爬蟲" required>
          </div>
          <button type="submit" class="btn btn-sm btn-success" :disabled="creatingKey || !keyName">
            <i class="bi bi-plus-lg me-1"></i>建立金鑰</button>
        </form>
        <div v-if="newKey" class="alert alert-warning py-2">
          <div class="small fw-semibold mb-1">新金鑰「{{ newKey.name }}」（只會顯示這一次）</div>
          <div class="d-flex flex-wrap align-items-center gap-2">
            <code class="nw-key">{{ newKey.key }}</code>
            <button type="button" class="btn btn-sm btn-outline-dark" @click="copy(newKey.key)"><i class="bi bi-clipboard me-1"></i>複製</button>
            <button type="button" class="btn btn-sm btn-link" @click="newKey = null">我已保存</button>
          </div>
        </div>
        <div class="table-responsive">
          <table class="table table-sm align-middle mb-3">
            <thead><tr><th>名稱</th><th>金鑰</th><th>權限</th><th>建立</th><th>最後使用</th><th class="text-end">次數</th><th></th></tr></thead>
            <tbody>
              <tr v-if="!keys.length"><td colspan="7" class="text-center text-muted py-3">還沒有金鑰</td></tr>
              <tr v-for="k in keys" :key="k._id" :class="{ 'text-muted': k.revoked }">
                <td>{{ k.name }}<span v-if="k.revoked" class="badge text-bg-secondary ms-1">已停用</span></td>
                <td><code>{{ k.prefix }}…</code></td>
                <td class="small">{{ k.scopes.join('、') }}</td>
                <td class="small text-nowrap">{{ fmtNewsDate(k.created_at) }}<span class="text-muted"> · {{ k.created_by }}</span></td>
                <td class="small text-nowrap">{{ fmtNewsDate(k.last_used_at) || '—' }}</td>
                <td class="text-end small">{{ k.use_count }}</td>
                <td class="text-end"><button v-if="!k.revoked" class="btn btn-sm btn-outline-danger" @click="revokeKey(k)">停用</button></td>
              </tr>
            </tbody>
          </table>
        </div>
        <details>
          <summary class="small fw-semibold">呼叫範例</summary>
          <pre class="nw-example mt-2 mb-0">{{ example }}</pre>
        </details>
      </div>
    </div>

    <ConfirmModal ref="confirmModalRef" />
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { newsApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { toast } from '@/utils/toast'
import { renderMarkdown } from '@/utils/markdown'
import { fmtNewsDate } from '@/utils/news'
import AdminSearchCard from '@/components/AdminSearchCard.vue'
import AdminSearchField from '@/components/AdminSearchField.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import ConfirmModal from '@/components/ConfirmModal.vue'

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')
const confirmModalRef = ref(null)

const items = ref([])
const allTags = ref([])
const loading = ref(false)
async function load() {
  loading.value = true
  const res = await newsApi.listAdmin()
  const body = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!res?.ok || !body?.success) { toast(body?.message || '讀取新聞失敗', 'error'); return }
  items.value = body.data || []
  allTags.value = body.tags || []
  if (auth.isAdmin) loadKeys()
}
onMounted(load)

const query = ref('')
const tagSel = ref([])
const shown = computed(() => {
  const q = query.value.toLowerCase()
  return items.value.filter(n => (!tagSel.value.length || tagSel.value.some(t => n.tags.includes(t)))
    && (!q || [n.title, n.body, ...n.tags].some(v => (v || '').toLowerCase().includes(q))))
})

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
  window.scrollTo({ top: 0, behavior: 'smooth' })
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
const escHtml = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
async function remove(n) {
  if (!(await confirmModalRef.value?.confirm(`確定要刪除 <strong>${escHtml(n.title)}</strong>？`))) return
  const res = await newsApi.remove(n._id)
  const body = res ? await res.json().catch(() => null) : null
  if (!res?.ok || !body?.success) { toast(body?.message || '刪除失敗', 'error'); return }
  toast('已刪除')
  load()
}

// ── API 金鑰 ──
const keys = ref([])
const keyName = ref('')
const creatingKey = ref(false)
const newKey = ref(null)
async function loadKeys() {
  const res = await newsApi.keys()
  const body = res ? await res.json().catch(() => null) : null
  if (res?.ok && body?.success) keys.value = body.data || []
}
async function createKey() {
  creatingKey.value = true
  const res = await newsApi.createKey({ name: keyName.value, scopes: ['news:write'] })
  const body = res ? await res.json().catch(() => null) : null
  creatingKey.value = false
  if (!res?.ok || !body?.success) { toast(body?.message || '建立失敗', 'error'); return }
  newKey.value = body.data
  keyName.value = ''
  loadKeys()
}
async function revokeKey(k) {
  if (!(await confirmModalRef.value?.confirm(`停用金鑰 <strong>${escHtml(k.name)}</strong>（${escHtml(k.prefix)}…）？用這把金鑰的程式會立刻不能寫入。`,
    { title: '停用金鑰', okText: '停用' }))) return
  const res = await newsApi.revokeKey(k._id)
  const body = res ? await res.json().catch(() => null) : null
  if (!res?.ok || !body?.success) { toast(body?.message || '停用失敗', 'error'); return }
  toast('已停用')
  loadKeys()
}
async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    toast('已複製')
  } catch {
    toast('複製失敗，請手動選取', 'error')
  }
}
const example = computed(() => `curl -X POST ${window.location.origin}/news/ingest \\
  -H "X-API-Key: ${newKey.value?.key || 'sct_你的金鑰'}" \\
  -H "Content-Type: application/json" \\
  -d '{
    "title": "Alpha 4.5 改版說明",
    "body": "**重點**\\n- 新增星系\\n- [完整說明](https://robertsspaceindustries.com/comm-link)",
    "cover_url": "https://example.com/cover.jpg",
    "source_url": "https://robertsspaceindustries.com/comm-link/transmission/12345",
    "tags": ["改版", "RSI"],
    "pinned": false,
    "published_at": "2026-11-20T08:00:00Z"
  }'

# 一次多則：送陣列（最多 50 則）。同一個 source_url 再送一次＝更新。
# 回應：{"success": true, "data": {"created": ["…id"], "updated": []}}`)
</script>

<style scoped>
.nw-preview { border: 1px solid var(--bs-border-color); border-radius: .375rem; padding: .5rem .75rem; min-height: 10rem; line-height: 1.7; }
.nw-preview :deep(img) { max-width: 100%; }
.nw-key { font-size: .95rem; word-break: break-all; }
.nw-example { background: var(--bs-tertiary-bg); padding: .75rem; border-radius: .375rem; font-size: .8rem; white-space: pre-wrap; }
</style>
