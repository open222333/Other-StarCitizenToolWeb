<!--
  後台「API 文件」（只給 admin）：後端每個端點 docstring 的 Swagger YAML 組成的規格（GET /data/api-spec，
  跟 /apidocs、/apispec_1.json 同一份；那兩個也只給 admin token，瀏覽器直接開會 401）。
  依標籤分組列出端點，搜尋關鍵字（路徑、說明）、篩選標籤／方法；點一列展開參數、請求內容、回應。
  規格的 $ref 只展開 definitions 一層。可以下載整份 JSON（匯入 Postman、Swagger Editor 用）。
-->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold"><i class="bi bi-braces me-2 text-primary"></i>API 文件</h5>
      <div class="d-flex flex-wrap gap-2">
        <button class="btn btn-outline-secondary btn-sm" :disabled="!spec" @click="download">
          <i class="bi bi-download me-1"></i>下載 JSON</button>
        <button class="btn btn-outline-secondary btn-sm" :disabled="loading" @click="load">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-arrow-clockwise me-1"></i>重新整理</button>
      </div>
    </div>

    <AdminSearchCard :active="hasFilter" @clear="clearFilter">
      <AdminSearchField label="關鍵字" for-id="ad-q" col="col-12 col-md-5">
        <input id="ad-q" v-model.trim="query" type="search" class="form-control form-control-sm"
          placeholder="路徑或說明，例如 /player/me、航線">
      </AdminSearchField>
      <AdminSearchField label="分類" for-id="ad-tag" col="col-6 col-md-4">
        <MultiSelectFilter id="ad-tag" v-model="tagSel" :options="tagOptions" label="分類" placeholder="全部" block searchable />
      </AdminSearchField>
      <AdminSearchField label="方法" for-id="ad-method" col="col-6 col-md-3">
        <MultiSelectFilter id="ad-method" v-model="methodSel" :options="methodOptions" label="方法" placeholder="全部" block />
      </AdminSearchField>
      <template #options>
        <div class="form-check mb-0">
          <input id="ad-auth" v-model="authOnly" class="form-check-input" type="checkbox">
          <label class="form-check-label small" for="ad-auth">只看需要 token 的</label>
        </div>
      </template>
      <template #summary>
        <template v-if="spec">共 {{ ops.length }} 個端點，符合 {{ shown.length }} 個 · {{ spec.info?.title }} {{ spec.info?.version }}</template>
      </template>
    </AdminSearchCard>

    <div v-if="error" class="alert alert-danger py-2">{{ error }}</div>
    <div v-else-if="loading && !spec" class="text-center text-muted py-5"><span class="spinner-border spinner-border-sm me-2"></span>載入中…</div>
    <p v-if="spec?.info?.description" class="small text-muted mb-3">{{ spec.info.description }}</p>
    <div v-if="spec && !shown.length" class="text-center text-muted py-4">沒有符合的端點。</div>

    <div v-for="g in groups" :key="g.tag" class="card shadow-sm border-0 mb-3">
      <div class="card-header bg-transparent fw-semibold d-flex align-items-center gap-2">
        <span>{{ g.tag }}</span><span class="badge text-bg-secondary">{{ g.ops.length }}</span>
      </div>
      <ul class="list-group list-group-flush">
        <li v-for="op in g.ops" :key="op.id" class="list-group-item p-0">
          <button type="button" class="ad-row" :aria-expanded="open.has(op.id) ? 'true' : 'false'" @click="toggle(op.id)">
            <span class="ad-method" :class="`ad-method--${op.method}`">{{ op.method.toUpperCase() }}</span>
            <code class="ad-path">{{ op.path }}</code>
            <span class="ad-summary">{{ op.summary }}</span>
            <i v-if="op.auth" class="bi bi-lock-fill ad-lock" title="需要 token"></i>
            <i class="bi ms-1" :class="open.has(op.id) ? 'bi-chevron-up' : 'bi-chevron-down'" aria-hidden="true"></i>
          </button>
          <div v-if="open.has(op.id)" class="ad-detail">
            <p v-if="op.description" class="ad-desc">{{ op.description }}</p>
            <p v-if="op.auth" class="small mb-2"><i class="bi bi-lock-fill me-1"></i>需要 <code>Authorization: Bearer &lt;token&gt;</code></p>

            <template v-if="op.params.length">
              <div class="ad-h">參數</div>
              <div class="table-responsive">
                <table class="table table-sm align-middle mb-2">
                  <thead><tr><th>名稱</th><th>位置</th><th>型別</th><th>必填</th><th>說明</th></tr></thead>
                  <tbody>
                    <tr v-for="p in op.params" :key="`${p.in}-${p.name}`">
                      <td><code>{{ p.name }}</code></td><td>{{ IN_LABEL[p.in] || p.in }}</td>
                      <td>{{ typeOf(p) }}</td><td>{{ p.required ? '是' : '' }}</td>
                      <td class="ad-cell">{{ clean(p.description) }}<span v-if="p.enum" class="text-muted"> （{{ p.enum.join('／') }}）</span>
                        <span v-if="p.default !== undefined" class="text-muted"> 預設 {{ p.default }}</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>

            <template v-if="op.bodyFields.length">
              <div class="ad-h">請求內容（JSON）</div>
              <div class="table-responsive">
                <table class="table table-sm align-middle mb-2">
                  <thead><tr><th>欄位</th><th>型別</th><th>必填</th><th>說明</th></tr></thead>
                  <tbody>
                    <tr v-for="f in op.bodyFields" :key="f.name">
                      <td><code>{{ f.name }}</code></td><td>{{ f.type }}</td><td>{{ f.required ? '是' : '' }}</td>
                      <td class="ad-cell">{{ f.description }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </template>

            <template v-if="op.responses.length">
              <div class="ad-h">回應</div>
              <table class="table table-sm align-middle mb-0">
                <tbody>
                  <tr v-for="r in op.responses" :key="r.code">
                    <td class="ad-code"><span class="badge" :class="r.code < 300 ? 'text-bg-success' : r.code < 500 ? 'text-bg-warning' : 'text-bg-danger'">{{ r.code }}</span></td>
                    <td class="ad-cell">{{ r.description }}</td>
                  </tr>
                </tbody>
              </table>
            </template>
          </div>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { dataApi } from '@/api'
import AdminSearchCard from '@/components/AdminSearchCard.vue'
import AdminSearchField from '@/components/AdminSearchField.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import { downloadJson } from '@/utils/download'

const METHODS = ['get', 'post', 'put', 'patch', 'delete']
const IN_LABEL = { query: '網址參數', path: '路徑', body: '內容', formData: '表單', header: '標頭' }

const spec = ref(null)
const loading = ref(false)
const error = ref('')
async function load() {
  loading.value = true
  error.value = ''
  const res = await dataApi.apiSpec()
  const body = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!res?.ok || !body?.success) {
    error.value = body?.message || 'API 文件載入失敗。'
    return
  }
  spec.value = body.data
}
onMounted(load)

// flasgger 把 docstring 的換行轉成 <br/>：換回真的換行（畫面用 pre-line 顯示）
const clean = t => (t || '').replace(/<br\s*\/?>/gi, '\n').replace(/\n{3,}/g, '\n\n').trim()

// $ref → definitions（只展開一層）
function deref(schema) {
  const ref = schema?.$ref
  if (!ref) return schema || {}
  const name = ref.split('/').pop()
  return spec.value?.definitions?.[name] || {}
}
function typeOf(p) {
  const s = p.schema ? deref(p.schema) : p
  if (s.type === 'array') return `${(s.items && (deref(s.items).type || 'object')) || ''}[]`
  return s.type || (p.schema ? 'object' : '')
}
function fieldsOf(schema) {
  const s = deref(schema)
  const req = new Set(s.required || [])
  return Object.entries(s.properties || {}).map(([name, f]) => {
    const d = deref(f)
    const type = d.type === 'array' ? `${(d.items && (deref(d.items).type || 'object')) || ''}[]` : (d.type || 'object')
    return { name, type, required: req.has(name), description: [clean(d.description), d.enum ? `（${d.enum.join('／')}）` : '', d.example !== undefined ? ` 例：${JSON.stringify(d.example)}` : ''].join('').trim() }
  })
}

const ops = computed(() => {
  const out = []
  for (const [path, item] of Object.entries(spec.value?.paths || {})) {
    for (const method of METHODS) {
      const op = item[method]
      if (!op) continue
      const params = [...(item.parameters || []), ...(op.parameters || [])]
      const body = params.find(p => p.in === 'body')
      out.push({
        id: `${method} ${path}`, method, path,
        tag: op.tags?.[0] || '其他',
        summary: clean(op.summary),
        description: clean(op.description),
        auth: !!(op.security || spec.value?.security)?.length,
        params: params.filter(p => p.in !== 'body'),
        bodyFields: body ? fieldsOf(body.schema) : [],
        responses: Object.entries(op.responses || {}).map(([code, r]) => ({ code: Number(code) || code, description: clean(r.description) })),
      })
    }
  }
  return out.sort((a, b) => a.path.localeCompare(b.path) || METHODS.indexOf(a.method) - METHODS.indexOf(b.method))
})

const query = ref('')
const tagSel = ref([])
const methodSel = ref([])
const authOnly = ref(false)
const tagOptions = computed(() => [...new Set(ops.value.map(o => o.tag))].sort().map(t => ({ value: t, label: t })))
const methodOptions = METHODS.map(m => ({ value: m, label: m.toUpperCase() }))
const hasFilter = computed(() => !!(query.value || tagSel.value.length || methodSel.value.length || authOnly.value))
function clearFilter() {
  query.value = ''
  tagSel.value = []
  methodSel.value = []
  authOnly.value = false
}
const shown = computed(() => {
  const q = query.value.toLowerCase()
  return ops.value.filter(o => (!q || `${o.path} ${o.summary} ${o.description}`.toLowerCase().includes(q))
    && (!tagSel.value.length || tagSel.value.includes(o.tag))
    && (!methodSel.value.length || methodSel.value.includes(o.method))
    && (!authOnly.value || o.auth))
})
const groups = computed(() => {
  const map = new Map()
  for (const o of shown.value) {
    if (!map.has(o.tag)) map.set(o.tag, [])
    map.get(o.tag).push(o)
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([tag, list]) => ({ tag, ops: list }))
})

const open = reactive(new Set())
function toggle(id) {
  if (open.has(id)) open.delete(id)
  else open.add(id)
}

function download() {
  downloadJson(spec.value, 'api-spec.json')
}
</script>

<style scoped>
.ad-row {
  display: flex; align-items: center; gap: .6rem; width: 100%; padding: .5rem .9rem;
  background: none; border: 0; text-align: left; color: inherit;
}
.ad-row:hover { background: rgba(127, 127, 127, .08); }
.ad-method {
  flex: 0 0 4.2rem; text-align: center; font-size: .75rem; font-weight: 700; border-radius: .3rem; padding: .15rem 0;
  color: #fff; background: #6c757d;
}
.ad-method--get { background: #0d6efd; }
.ad-method--post { background: #198754; }
.ad-method--put, .ad-method--patch { background: #fd7e14; }
.ad-method--delete { background: #dc3545; }
.ad-path { flex: 0 1 auto; font-size: .9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 45%; }
.ad-summary { flex: 1 1 auto; min-width: 0; color: var(--bs-secondary-color); font-size: .9rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ad-lock { color: var(--bs-secondary-color); font-size: .8rem; }
.ad-detail { padding: .25rem 1rem 1rem 5.6rem; }
.ad-desc { white-space: pre-line; font-size: .9rem; }
.ad-h { font-weight: 600; font-size: .85rem; margin: .5rem 0 .25rem; }
.ad-cell { white-space: pre-line; font-size: .85rem; }
.ad-code { width: 4rem; }
@media (max-width: 767.98px) {
  .ad-row { flex-wrap: wrap; }
  .ad-path { max-width: none; flex: 1 1 calc(100% - 5rem); }
  .ad-summary { flex-basis: 100%; white-space: normal; }
  .ad-detail { padding-left: 1rem; }
}
</style>
