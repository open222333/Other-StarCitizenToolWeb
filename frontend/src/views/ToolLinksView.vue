<!--
  工具網站連結管理（後台）。這裡維護的連結會顯示在玩家頁的「工具網站」分頁：
  依標籤分組（一個網址可以有好幾個標籤，會出現在每個標籤底下），標題是連結、說明收在
  標題旁的「?」裡。標籤存在 mongo 的 tool_link_tags（順序），見 src/models/tool_link.py。
  列表上方可以用關鍵字（標題／網址／說明／標籤）與標籤篩選，篩選在前端做（量很少）。

  JSON 批量匯入／匯出（app/links/view.py 的 /links/export、/links/import）：
  匯出檔可以直接拿來匯入；匯入以網址比對，同網址更新、新網址新增，勾「取代現有清單」
  時檔案裡沒有的會被刪除（軟刪除）。任何一筆不合法整批不寫入。格式範例在「格式範例」裡，
  也可以下載範例檔改。JSON 可以選檔案，也可以直接貼上（兩者擇一，以最後動過的那個為準）。
-->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold"><i class="bi bi-link-45deg me-2 text-primary"></i>工具網站</h5>
      <div class="d-flex flex-wrap gap-2">
        <button class="btn btn-outline-secondary btn-sm" :disabled="exporting || !links.length" @click="exportJson">
          <span v-if="exporting" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-download me-1"></i>匯出 JSON
        </button>
        <button v-if="canWrite" class="btn btn-outline-secondary btn-sm" :aria-expanded="showImport ? 'true' : 'false'"
          @click="showImport = !showImport">
          <i class="bi bi-upload me-1"></i>匯入 JSON
        </button>
        <button class="btn btn-outline-secondary btn-sm" :disabled="loading" @click="load">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-arrow-clockwise me-1"></i>重新整理
        </button>
      </div>
    </div>

    <Transition name="alert-slide">
      <div v-if="msg" :class="`alert alert-${msgType} py-2 mb-3`">{{ msg }}</div>
    </Transition>

    <!-- JSON 批量匯入 -->
    <div v-if="canWrite && showImport" class="card shadow-sm border-0 mb-3">
      <div class="card-body">
        <h6 class="fw-semibold mb-3">匯入 JSON</h6>
        <div class="d-flex flex-wrap align-items-center gap-3">
          <input ref="fileEl" type="file" accept=".json,application/json" class="form-control form-control-sm"
            style="max-width: 22rem" aria-label="選擇 JSON 檔" @change="onFile">
          <div class="form-check mb-0">
            <input id="tl-import-replace" v-model="importReplace" class="form-check-input" type="checkbox">
            <label class="form-check-label small" for="tl-import-replace">取代現有清單（檔案裡沒有的會刪除）</label>
          </div>
          <button class="btn btn-primary btn-sm" :disabled="!importData || importing" @click="doImport">
            <span v-if="importing" class="spinner-border spinner-border-sm me-1"></span>匯入
          </button>
        </div>
        <label class="form-label small fw-semibold mt-3 mb-1" for="tl-import-text">或直接貼上 JSON</label>
        <textarea id="tl-import-text" v-model="importText" rows="6" class="form-control form-control-sm font-monospace"
          spellcheck="false" :placeholder="pastePlaceholder" @input="onPaste"></textarea>
        <div v-if="importSource" class="small mt-2" :class="importError ? 'text-danger' : 'text-muted'">
          {{ importSource }}：{{ importError || `${importCount} 筆` }}
        </div>
        <div class="mt-3">
          <button type="button" class="btn btn-sm btn-link p-0 me-3" :aria-expanded="showExample ? 'true' : 'false'"
            @click="showExample = !showExample">
            <i class="bi me-1" :class="showExample ? 'bi-chevron-down' : 'bi-chevron-right'"></i>格式範例
          </button>
          <button type="button" class="btn btn-sm btn-link p-0" @click="downloadExample">
            <i class="bi bi-file-earmark-arrow-down me-1"></i>下載範例檔
          </button>
          <div v-if="showExample" class="row g-3 mt-1">
            <div class="col-lg-7">
              <pre class="json-example mb-0">{{ exampleText }}</pre>
            </div>
            <div class="col-lg-5 small">
              <table class="table table-sm mb-0">
                <thead><tr><th>欄位</th><th class="text-nowrap">必填</th><th>說明</th></tr></thead>
                <tbody>
                  <tr><td class="font-monospace">tags（最外層）</td><td>否</td><td>標籤的順序（玩家頁分組順序）</td></tr>
                  <tr><td class="font-monospace">title</td><td>是</td><td>標題，最多 100 字</td></tr>
                  <tr><td class="font-monospace">url</td><td>是</td><td>http:// 或 https://，沒寫的會補 https://；同網址視為同一筆</td></tr>
                  <tr><td class="font-monospace">description</td><td>否</td><td>說明（玩家頁收在「?」裡），最多 2000 字</td></tr>
                  <tr><td class="font-monospace">sort_order</td><td>否</td><td>排序，整數，越小越前面，預設 0</td></tr>
                  <tr><td class="font-monospace">tags</td><td>否</td><td>這個網址的標籤，陣列，最多 10 個、每個最多 50 字</td></tr>
                </tbody>
              </table>
              <div class="text-muted mt-2">
                同一個網址出現好幾次會合併成一筆、標籤取聯集。分類版
                <code>{"categories": [{"name", "links"}]}</code>（分類名稱當成標籤）、
                直接一個陣列也可以。一次最多 500 筆。
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 新增／編輯 -->
    <div v-if="canWrite" class="card shadow-sm border-0 mb-3">
      <div class="card-body">
        <h6 class="fw-semibold mb-3">{{ editingId ? '編輯工具網站' : '新增工具網站' }}</h6>
        <form class="row g-2" @submit.prevent="submit">
          <div class="col-12 col-md-4">
            <label class="form-label small fw-semibold" for="tl-title">標題</label>
            <input id="tl-title" v-model="form.title" type="text" class="form-control form-control-sm"
              maxlength="100" required>
          </div>
          <div class="col-12 col-md-6">
            <label class="form-label small fw-semibold" for="tl-url">網址</label>
            <input id="tl-url" v-model="form.url" type="text" class="form-control form-control-sm"
              maxlength="2000" placeholder="https://" required>
          </div>
          <div class="col-6 col-md-2">
            <label class="form-label small fw-semibold" for="tl-order">排序</label>
            <input id="tl-order" v-model.number="form.sort_order" type="number" step="1"
              class="form-control form-control-sm">
          </div>
          <div class="col-12">
            <label class="form-label small fw-semibold" for="tl-tags">標籤</label>
            <input id="tl-tags" v-model="form.tags" type="text" class="form-control form-control-sm"
              placeholder="配裝, 交易">
            <div v-if="allTags.length" class="d-flex flex-wrap gap-1 mt-1">
              <button v-for="t in allTags" :key="t" type="button" class="btn btn-sm py-0"
                :class="formTagList.includes(t) ? 'btn-primary' : 'btn-outline-secondary'"
                @click="toggleFormTag(t)">{{ t }}</button>
            </div>
          </div>
          <div class="col-12">
            <label class="form-label small fw-semibold" for="tl-desc">說明</label>
            <textarea id="tl-desc" v-model="form.description" rows="2" maxlength="2000"
              class="form-control form-control-sm"></textarea>
          </div>
          <div class="col-12 d-flex gap-2 justify-content-end">
            <button v-if="editingId" type="button" class="btn btn-outline-secondary btn-sm"
              @click="resetForm">取消</button>
            <button type="submit" class="btn btn-primary btn-sm" :disabled="saving">
              <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
              {{ editingId ? '儲存' : '新增' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <!-- 搜尋 -->
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm" style="max-width: 18rem"
            placeholder="搜尋標題、網址、說明、標籤..." aria-label="搜尋工具網站">
          <MultiSelectFilter v-model="selectedTags" label="標籤" :options="tagOptions" searchable />
          <button v-if="query || selectedTags.length" type="button" class="btn btn-sm btn-outline-secondary"
            @click="query = ''; selectedTags = []">清除篩選</button>
          <span class="small text-muted ms-auto">{{ filteredLinks.length }} / {{ links.length }}</span>
        </div>
      </div>
    </div>

    <!-- 列表 -->
    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3" style="width:5rem">排序</th>
                <th>標題</th>
                <th>網址</th>
                <th>標籤</th>
                <th>說明</th>
                <th v-if="canWrite" style="width:120px" class="pe-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading && !links.length">
                <td :colspan="canWrite ? 6 : 5" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!links.length">
                <td :colspan="canWrite ? 6 : 5" class="text-center py-4 text-muted">尚無工具網站</td>
              </tr>
              <tr v-else-if="!filteredLinks.length">
                <td :colspan="canWrite ? 6 : 5" class="text-center py-4 text-muted">沒有符合篩選條件的工具網站</td>
              </tr>
              <tr v-for="l in filteredLinks" :key="l._id" :class="{ 'table-active': l._id === editingId }">
                <td class="ps-3 small text-muted">{{ l.sort_order ?? 0 }}</td>
                <td class="fw-semibold">{{ l.title }}</td>
                <td class="small text-break">
                  <a :href="l.url" target="_blank" rel="noopener noreferrer">{{ l.url }}</a>
                </td>
                <td>
                  <span v-for="t in l.tags" :key="t" class="badge text-bg-secondary me-1">{{ t }}</span>
                  <span v-if="!l.tags?.length" class="text-muted small">—</span>
                </td>
                <td class="small text-muted text-break" style="white-space: pre-line">{{ l.description || '—' }}</td>
                <td v-if="canWrite" class="pe-3 text-nowrap">
                  <button class="btn btn-sm btn-outline-primary me-1" @click="edit(l)">編輯</button>
                  <button class="btn btn-sm btn-outline-danger" @click="remove(l)">刪除</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { toolLinkApi } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')

const links   = ref([])
const loading = ref(false)
const saving  = ref(false)
const msg     = ref('')
const msgType = ref('success')
const editingId = ref('')
const form = reactive({ title: '', url: '', description: '', sort_order: 0, tags: '' })
// 標籤順序（後端 /links/ 一起回傳，存在 mongo 的 tool_link_tags）
const allTags = ref([])

// 表單的標籤欄位是逗號分隔的文字；下面的標籤按鈕可以直接加／移除
const splitTags = text => [...new Set((text || '').replace(/，/g, ',').split(',').map(t => t.trim()).filter(Boolean))]
const formTagList = computed(() => splitTags(form.tags))
function toggleFormTag(tag) {
  const list = formTagList.value
  form.tags = (list.includes(tag) ? list.filter(t => t !== tag) : [...list, tag]).join(', ')
}

// ── 搜尋／篩選（前端做，量很少）──
const query = ref('')
const selectedTags = ref([])
const tagOptions = computed(() => allTags.value.map(t => ({ value: t, label: t })))
const filteredLinks = computed(() => {
  const q = query.value.trim().toLowerCase()
  return links.value.filter((l) => {
    if (selectedTags.value.length && !selectedTags.value.some(t => (l.tags || []).includes(t))) return false
    if (!q) return true
    return [l.title, l.url, l.description, ...(l.tags || [])].some(v => (v || '').toLowerCase().includes(q))
  })
})

// ── JSON 匯入／匯出 ──────────────────────────────────────────
const EXAMPLE = {
  version: 3,
  tags: ['配裝', '交易', '資料'],
  links: [
    { title: 'Erkul', url: 'https://www.erkul.games', description: '船艦配裝與 DPS 計算', sort_order: 1, tags: ['配裝'] },
    { title: 'UEX Corp', url: 'https://uexcorp.space', description: '商品價格、交易路線', sort_order: 2, tags: ['交易', '資料'] },
    { title: 'Star Citizen Wiki', url: 'https://starcitizen.tools', description: '', sort_order: 3, tags: ['資料'] },
  ],
}
const exampleText = JSON.stringify(EXAMPLE, null, 2)

const showImport = ref(false)
const showExample = ref(false)
const importReplace = ref(false)
const importData = ref(null)
const importSource = ref('')     // 「檔名」或「貼上的內容」
const importText = ref('')
const pastePlaceholder = '{"links": [{"title": "Erkul", "url": "https://www.erkul.games", "tags": ["配裝"]}]}'
const importCount = ref(0)
const importError = ref('')
const importing = ref(false)
const exporting = ref(false)
const fileEl = ref(null)

function downloadFile(filename, obj) {
  const blob = new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

function downloadExample() {
  downloadFile('tool-links-example.json', EXAMPLE)
}

async function exportJson() {
  exporting.value = true
  try {
    const res = await toolLinkApi.exportAll()
    const data = await readJson(res)
    if (!res?.ok || !data?.success) {
      flash(data?.message || '匯出失敗', 'danger')
      return
    }
    const stamp = new Date().toISOString().slice(0, 10)
    downloadFile(`tool-links-${stamp}.json`, data.data)
  } finally {
    exporting.value = false
  }
}

// 檔案、貼上共用：解析並檢查最外層格式（欄位內容交給後端驗證）
function parseImport(text, source) {
  importData.value = null
  importError.value = ''
  importCount.value = 0
  importSource.value = source
  if (!text.trim()) {
    importSource.value = ''
    return
  }
  try {
    const parsed = JSON.parse(text)
    // 格式 2：{"categories": [{"name", "links": [...]}]}；舊格式：{"links": [...]} 或陣列
    let count = null
    if (Array.isArray(parsed?.categories)) {
      count = parsed.categories.reduce((n, c) => n + (Array.isArray(c?.links) ? c.links.length : 0), 0)
    } else {
      const items = Array.isArray(parsed) ? parsed : parsed?.links
      if (Array.isArray(items)) count = items.length
    }
    if (count === null) {
      importError.value = '格式不對：要是 {"links": [...]}、{"categories": [...]} 或一個陣列'
      return
    }
    importData.value = parsed
    importCount.value = count
  } catch (err) {
    importError.value = `不是有效的 JSON（${err.message}）`
  }
}

async function onFile(event) {
  const file = event.target.files?.[0]
  if (!file) {
    parseImport('', '')
    return
  }
  importText.value = ''   // 以檔案為準
  parseImport(await file.text(), file.name)
}

let pasteTimer = null
function onPaste() {
  if (fileEl.value) fileEl.value.value = ''   // 以貼上的內容為準
  clearTimeout(pasteTimer)
  pasteTimer = setTimeout(() => parseImport(importText.value, '貼上的內容'), 300)
}

async function doImport() {
  if (!importData.value || importing.value) return
  if (importReplace.value && !window.confirm('取代現有清單：檔案裡沒有的工具網站會被刪除，確定要匯入？')) return
  importing.value = true
  try {
    const res = await toolLinkApi.importAll({ data: importData.value, replace: importReplace.value })
    const data = await readJson(res)
    if (!res?.ok || !data?.success) {
      flash(data?.message || '匯入失敗', 'danger')
      return
    }
    const r = data.data
    flash(`匯入完成：新增 ${r.created}、更新 ${r.updated}${r.deleted ? `、刪除 ${r.deleted}` : ''}`)
    importData.value = null
    importSource.value = ''
    importText.value = ''
    importReplace.value = false
    if (fileEl.value) fileEl.value.value = ''
    await load()
  } finally {
    importing.value = false
  }
}

let msgTimer = null
function flash(text, type = 'success') {
  msg.value = text
  msgType.value = type
  clearTimeout(msgTimer)
  msgTimer = setTimeout(() => { msg.value = '' }, 5000)
}

async function readJson(res) {
  return res ? await res.json().catch(() => null) : null
}

async function load() {
  loading.value = true
  const res = await toolLinkApi.list()
  const data = await readJson(res)
  loading.value = false
  if (res?.ok && data?.success) {
    links.value = data.data || []
    allTags.value = data.tags || []
  }
  else flash(data?.message || '讀取工具網站失敗', 'danger')
}

function resetForm() {
  editingId.value = ''
  Object.assign(form, { title: '', url: '', description: '', sort_order: 0, tags: '' })
}

function edit(link) {
  editingId.value = link._id
  Object.assign(form, {
    tags: (link.tags || []).join(', '), title: link.title, url: link.url,
    description: link.description || '', sort_order: link.sort_order ?? 0,
  })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

async function submit() {
  if (saving.value) return
  saving.value = true
  const payload = {
    tags: formTagList.value, title: form.title.trim(), url: form.url.trim(),
    description: form.description.trim(), sort_order: Number(form.sort_order) || 0,
  }
  const res = editingId.value
    ? await toolLinkApi.update(editingId.value, payload)
    : await toolLinkApi.create(payload)
  const data = await readJson(res)
  saving.value = false
  if (!res?.ok || !data?.success) {
    flash(data?.message || '儲存失敗', 'danger')
    return
  }
  flash(editingId.value ? '已儲存' : '已新增')
  resetForm()
  await load()
}

async function remove(link) {
  if (!window.confirm(`確定要刪除「${link.title}」？`)) return
  const res = await toolLinkApi.remove(link._id)
  const data = await readJson(res)
  if (!res?.ok || !data?.success) {
    flash(data?.message || '刪除失敗', 'danger')
    return
  }
  if (editingId.value === link._id) resetForm()
  flash('已刪除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.json-example {
  background: var(--bs-tertiary-bg); border-radius: .375rem; padding: .75rem 1rem;
  font-size: .8rem; max-height: 22rem; overflow: auto;
}
</style>
