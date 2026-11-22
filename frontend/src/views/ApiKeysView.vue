<!--
  後台「API 金鑰」（只有 admin）：給外部程式呼叫寫入端點用的金鑰（後端 app/api_key/view.py，GET／POST／DELETE /data/api-keys）。
  原本在「新聞」頁裡，獨立出來是因為之後其他功能也可能要開放外部寫入：每把金鑰有自己的權限（scope，
  後端 src/models/api_key.py 的 SCOPES），新功能加一個 scope，這頁的權限勾選就會自動多一項。
  金鑰只在建立時顯示一次，資料庫只存雜湊；停用後立刻失效。下面附各權限的呼叫範例。
-->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold"><i class="bi bi-key me-2 text-primary"></i>API 金鑰</h5>
      <button class="btn btn-outline-secondary btn-sm" :disabled="loading" @click="load">
        <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
        <i v-else class="bi bi-arrow-clockwise me-1"></i>重新整理</button>
    </div>

    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body">
        <h6 class="fw-semibold mb-2">建立金鑰</h6>
        <form class="row g-2 align-items-end" @submit.prevent="createKey">
          <div class="col-12 col-md-4">
            <label class="form-label small fw-semibold mb-1" for="ak-name">名稱</label>
            <input id="ak-name" v-model.trim="keyName" type="text" maxlength="50" class="form-control form-control-sm"
              placeholder="例如：RSI 新聞爬蟲" required>
          </div>
          <div class="col-12 col-md">
            <span class="form-label small fw-semibold mb-1 d-block">權限</span>
            <div class="d-flex flex-wrap gap-3">
              <div v-for="(label, scope) in scopes" :key="scope" class="form-check mb-0">
                <input :id="`ak-scope-${scope}`" v-model="keyScopes" class="form-check-input" type="checkbox" :value="scope">
                <label class="form-check-label small" :for="`ak-scope-${scope}`"><code>{{ scope }}</code> {{ label }}</label>
              </div>
            </div>
          </div>
          <div class="col-auto">
            <button type="submit" class="btn btn-sm btn-success" :disabled="creating || !keyName || !keyScopes.length">
              <i class="bi bi-plus-lg me-1"></i>建立金鑰</button>
          </div>
        </form>
        <div v-if="newKey" class="alert alert-warning py-2 mt-3 mb-0">
          <div class="small fw-semibold mb-1">新金鑰「{{ newKey.name }}」（只會顯示這一次）</div>
          <div class="d-flex flex-wrap align-items-center gap-2">
            <code class="ak-key">{{ newKey.key }}</code>
            <button type="button" class="btn btn-sm btn-outline-dark" @click="copyText(newKey.key)"><i class="bi bi-clipboard me-1"></i>複製</button>
            <button type="button" class="btn btn-sm btn-outline-secondary" @click="newKey = null">我已保存</button>
          </div>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body p-0">
        <div class="table-responsive">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light"><tr>
              <th class="ps-3">名稱</th><th>金鑰</th><th>權限</th><th>建立</th><th>最後使用</th><th class="text-end">次數</th><th class="pe-3"></th>
            </tr></thead>
            <tbody>
              <tr v-if="loading && !keys.length"><td colspan="7" class="text-center text-muted py-3">
                <span class="spinner-border spinner-border-sm me-2"></span>載入中…</td></tr>
              <tr v-else-if="!keys.length"><td colspan="7" class="text-center text-muted py-3">還沒有金鑰</td></tr>
              <tr v-for="k in keys" :key="k._id" :class="{ 'text-muted': k.revoked }">
                <td class="ps-3">{{ k.name }}<span v-if="k.revoked" class="badge text-bg-secondary ms-1">已停用</span></td>
                <td><code>{{ k.prefix }}…</code></td>
                <td class="small"><code v-for="s in k.scopes" :key="s" class="me-1">{{ s }}</code></td>
                <td class="small text-nowrap">{{ fmtNewsDate(k.created_at) }}<span class="text-muted"> · {{ k.created_by }}</span></td>
                <td class="small text-nowrap">{{ fmtNewsDate(k.last_used_at) || '—' }}</td>
                <td class="text-end small">{{ k.use_count }}</td>
                <td class="text-end pe-3"><button v-if="!k.revoked" class="btn btn-sm btn-outline-danger" @click="revokeKey(k)">停用</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body">
        <h6 class="fw-semibold mb-2">呼叫範例</h6>
        <details v-for="(label, scope) in scopes" :key="scope" class="mb-2">
          <summary class="small fw-semibold"><code>{{ scope }}</code> {{ label }}</summary>
          <pre class="ak-example mt-2 mb-0">{{ examples[scope] || '（沒有範例）' }}</pre>
        </details>
      </div>
    </div>

    <ConfirmModal ref="confirmModalRef" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiKeyApi } from '@/api'
import ConfirmModal from '@/components/ConfirmModal.vue'
import { getJson } from '@/utils/getJson'
import { toast } from '@/utils/toast'
import { copyText } from '@/utils/clipboard'
import { escapeHtml } from '@/utils/html'
import { fmtNewsDate } from '@/utils/news'

const confirmModalRef = ref(null)
const keys = ref([])
const scopes = ref({})
const loading = ref(false)
async function load() {
  loading.value = true
  const r = await getJson(apiKeyApi.list, '', undefined, '讀取金鑰失敗')
  loading.value = false
  if (!r.ok) { toast(r.message, 'danger'); return }
  keys.value = r.data || []
  scopes.value = r.body.scopes || {}
}
onMounted(load)

const keyName = ref('')
const keyScopes = ref([])
const creating = ref(false)
const newKey = ref(null)
async function createKey() {
  creating.value = true
  const r = await getJson(() => apiKeyApi.create({ name: keyName.value, scopes: keyScopes.value }), '', undefined, '建立失敗')
  creating.value = false
  if (!r.ok) { toast(r.message, 'danger'); return }
  newKey.value = r.data
  keyName.value = ''
  keyScopes.value = []
  load()
}
async function revokeKey(k) {
  if (!(await confirmModalRef.value?.confirm(`停用金鑰 <strong>${escapeHtml(k.name)}</strong>（${escapeHtml(k.prefix)}…）？用這把金鑰的程式會立刻不能寫入。`,
    { title: '停用金鑰', okText: '停用' }))) return
  const r = await getJson(() => apiKeyApi.revoke(k._id), '', undefined, '停用失敗')
  if (!r.ok) { toast(r.message, 'danger'); return }
  toast('已停用')
  load()
}

// 各權限的呼叫範例（新增 scope 時在這裡補一段）
const examples = computed(() => ({
  'news:write': `curl -X POST ${window.location.origin}/news/ingest \\
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
# 回應：{"success": true, "data": {"created": ["…id"], "updated": []}}`,
}))
</script>

<style scoped>
.ak-key { word-break: break-all; }
.ak-example { background: var(--bs-tertiary-bg); padding: .75rem; border-radius: .375rem; font-size: .8rem; white-space: pre-wrap; }
</style>
