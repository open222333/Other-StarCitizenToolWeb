<!--
  後台「系統設定」：AI 問答（Discord /ask，只有 admin 看得到）。見 src/ai/、GET／PUT /data/ai/config。
  - 啟用開關（關掉時 Discord /ask 不能用；下面的「測試」照樣可以用）
  - 供應商：照順序輪換（上下按鈕調整），各自的啟用、模型、API key（只顯示末 4 碼；留空＝不改，按「清除」才清掉）、
    目前狀態（冷卻中、今天次數、最後錯誤）
  - 每人限流（Discord）：每分鐘／每天幾次
  - 測試問答、最近紀錄
-->
<template>
  <div class="card border-0 shadow-sm mb-3">
    <div class="card-body p-4">
      <h6 class="fw-semibold mb-3"><i class="bi bi-robot me-1"></i>AI 問答（Discord /ask）</h6>
      <div v-if="message" class="alert py-2" :class="messageType === 'danger' ? 'alert-danger' : 'alert-success'">{{ message }}</div>
      <div v-if="loading" class="text-muted small">載入中…</div>
      <template v-else-if="cfg">
        <div class="form-check form-switch mb-3">
          <input id="ai-enabled" v-model="form.enabled" class="form-check-input" type="checkbox" role="switch">
          <label class="form-check-label" for="ai-enabled">開放 Discord /ask</label>
        </div>

        <div class="fw-semibold mb-2">供應商（照順序輪換：額度用完或出錯就換下一家）</div>
        <div v-for="(p, i) in form.providers" :key="p.key" class="ai-provider mb-2">
          <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
            <span class="badge text-bg-secondary">{{ i + 1 }}</span>
            <span class="fw-semibold">{{ p.label }}</span>
            <div class="form-check form-switch mb-0 ms-2">
              <input :id="`ai-p-${p.key}`" v-model="p.enabled" class="form-check-input" type="checkbox" role="switch">
              <label class="form-check-label" :for="`ai-p-${p.key}`">啟用</label>
            </div>
            <span v-if="runtime(p.key).cooldown" class="badge text-bg-warning">冷卻中 {{ runtime(p.key).cooldown }} 秒</span>
            <span class="badge text-bg-light border">今天 {{ runtime(p.key).today }} 次</span>
            <div class="ms-auto d-flex gap-1">
              <button type="button" class="btn btn-sm btn-outline-secondary" :disabled="i === 0" :aria-label="`${p.label} 往前`"
                @click="move(i, i - 1)"><i class="bi bi-arrow-up"></i></button>
              <button type="button" class="btn btn-sm btn-outline-secondary" :disabled="i === form.providers.length - 1"
                :aria-label="`${p.label} 往後`" @click="move(i, i + 1)"><i class="bi bi-arrow-down"></i></button>
            </div>
          </div>
          <div class="row g-2">
            <div class="col-12 col-md-5">
              <label class="form-label small fw-semibold mb-1" :for="`ai-model-${p.key}`">模型</label>
              <input :id="`ai-model-${p.key}`" v-model="p.model" type="text" class="form-control form-control-sm"
                :placeholder="p.default_model">
            </div>
            <div class="col-12 col-md-7">
              <label class="form-label small fw-semibold mb-1" :for="`ai-key-${p.key}`">
                API key <span v-if="p.has_key" class="text-muted fw-normal">目前：{{ p.masked_key }}</span>
                <span v-else class="text-danger fw-normal">未設定</span>
                <a :href="p.key_url" target="_blank" rel="noopener noreferrer" class="ms-2 small">取得 key</a>
              </label>
              <div class="d-flex gap-2">
                <input :id="`ai-key-${p.key}`" v-model="p.newKey" type="password" class="form-control form-control-sm"
                  autocomplete="off" :placeholder="p.has_key ? '留空＝不改' : '貼上 API key'">
                <button v-if="p.has_key" type="button" class="btn btn-sm btn-outline-danger text-nowrap"
                  @click="p.clearKey = !p.clearKey">{{ p.clearKey ? '取消清除' : '清除' }}</button>
              </div>
              <div v-if="p.clearKey" class="small text-danger mt-1">儲存後會清掉這把 key</div>
            </div>
          </div>
          <div v-if="runtime(p.key).last_error" class="small text-muted mt-1">最後錯誤：{{ runtime(p.key).last_error }}</div>
        </div>

        <div class="row g-2 mt-1 mb-3">
          <div class="col-6 col-md-3">
            <label class="form-label small fw-semibold mb-1" for="ai-pm">每人每分鐘</label>
            <input id="ai-pm" v-model.number="form.user_per_minute" type="number" min="1" max="60" class="form-control form-control-sm">
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label small fw-semibold mb-1" for="ai-pd">每人每天</label>
            <input id="ai-pd" v-model.number="form.user_per_day" type="number" min="1" max="5000" class="form-control form-control-sm">
          </div>
        </div>
        <button type="button" class="btn btn-sm btn-primary" :disabled="saving" @click="save">
          <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>儲存</button>
        <span v-if="cfg.updated_at" class="small text-muted ms-2">上次更新：{{ fmtTime(cfg.updated_at) }}（{{ cfg.updated_by || '—' }}）</span>

        <hr>
        <div class="fw-semibold mb-2">測試</div>
        <div class="d-flex gap-2">
          <input v-model="question" type="text" class="form-control form-control-sm" maxlength="500"
            placeholder="例如：誰有大力神 C2？" aria-label="測試問題" @keydown.enter="test">
          <button type="button" class="btn btn-sm btn-success text-nowrap" :disabled="testing || !question.trim()" @click="test">
            <span v-if="testing" class="spinner-border spinner-border-sm me-1"></span>送出</button>
        </div>
        <div v-if="testResult" class="ai-answer mt-2">
          <div class="small text-muted mb-1">
            {{ testResult.providers.map(providerLabel).join(' → ') }} · {{ testResult.ms }} ms
            <template v-if="testResult.tools.length"> · 工具：{{ testResult.tools.map(t => t.name).join('、') }}</template>
          </div>
          <div class="ai-answer__text">{{ testResult.answer }}</div>
        </div>

        <hr>
        <button type="button" class="btn btn-sm btn-outline-secondary" @click="toggleLogs">
          <i class="bi me-1" :class="logsOpen ? 'bi-chevron-up' : 'bi-chevron-down'"></i>最近紀錄</button>
        <div v-if="logsOpen" class="table-responsive mt-2">
          <table class="table table-sm align-middle mb-0">
            <thead><tr><th>時間</th><th>提問者</th><th>問題</th><th>AI</th><th>工具</th><th class="text-end">耗時</th></tr></thead>
            <tbody>
              <tr v-if="!logs.length"><td colspan="6" class="text-muted">還沒有紀錄</td></tr>
              <tr v-for="(l, i) in logs" :key="i" :class="{ 'table-danger': !l.ok }">
                <td class="text-nowrap">{{ fmtTime(l.created_at) }}</td>
                <td class="small">{{ l.asker }}</td>
                <td>{{ l.question }}<div v-if="!l.ok" class="small text-danger">{{ l.error }}</div></td>
                <td class="small text-nowrap">{{ (l.providers || []).map(providerLabel).join(' → ') }}</td>
                <td class="small">{{ (l.tools || []).map(t => t.name).join('、') }}</td>
                <td class="text-end text-nowrap">{{ l.ms }} ms</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '@/api'

const cfg = ref(null)
const form = ref(null)
const loading = ref(true)
const saving = ref(false)
const message = ref('')
const messageType = ref('success')
const question = ref('')
const testing = ref(false)
const testResult = ref(null)
const logsOpen = ref(false)
const logs = ref([])

function say(text, type = 'success') {
  message.value = text
  messageType.value = type
}

function applyCfg(data) {
  cfg.value = data
  form.value = {
    enabled: data.enabled,
    user_per_minute: data.user_per_minute,
    user_per_day: data.user_per_day,
    providers: data.providers.map(p => ({ ...p, newKey: '', clearKey: false })),
  }
}
const runtime = key => cfg.value?.runtime?.[key] || { cooldown: 0, today: 0, last_error: '' }
const providerLabel = key => cfg.value?.providers.find(p => p.key === key)?.label || key

async function load() {
  loading.value = true
  const res = await apiFetch('/data/ai/config')
  const data = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!data?.success) return say(data?.message || '讀取失敗。', 'danger')
  applyCfg(data.data)
}

function move(from, to) {
  const list = form.value.providers
  list.splice(to, 0, list.splice(from, 1)[0])
}

async function save() {
  saving.value = true
  message.value = ''
  const f = form.value
  const providers = {}
  for (const p of f.providers) {
    providers[p.key] = { enabled: p.enabled, model: (p.model || '').trim() }
    if (p.clearKey) providers[p.key].api_key = ''
    else if (p.newKey.trim()) providers[p.key].api_key = p.newKey.trim()
  }
  const res = await apiFetch('/data/ai/config', {
    method: 'PUT',
    body: JSON.stringify({ enabled: f.enabled, order: f.providers.map(p => p.key), user_per_minute: f.user_per_minute,
      user_per_day: f.user_per_day, providers }),
  })
  const data = res ? await res.json().catch(() => null) : null
  saving.value = false
  if (!data?.success) return say(data?.message || '儲存失敗。', 'danger')
  applyCfg(data.data)
  say('已儲存。')
}

async function test() {
  if (!question.value.trim() || testing.value) return
  testing.value = true
  testResult.value = null
  message.value = ''
  const res = await apiFetch('/data/ai/test', { method: 'POST', body: JSON.stringify({ question: question.value }) })
  const data = res ? await res.json().catch(() => null) : null
  testing.value = false
  if (!data?.success) return say(data?.message || '測試失敗。', 'danger')
  testResult.value = data.data
  load()
  if (logsOpen.value) loadLogs()
}

async function loadLogs() {
  const res = await apiFetch('/data/ai/logs?limit=30')
  const data = res ? await res.json().catch(() => null) : null
  logs.value = data?.success ? data.data : []
}
function toggleLogs() {
  logsOpen.value = !logsOpen.value
  if (logsOpen.value) loadLogs()
}

function fmtTime(v) {
  if (!v) return '—'
  // 後端的時間是 UTC；ISO 格式沒帶時區時補 Z，其他格式（例如 HTTP 日期）直接交給 Date 解析
  const iso = typeof v === 'string' && /^\d{4}-\d{2}-\d{2}T[\d:.]+$/.test(v)
  const d = new Date(iso ? `${v}Z` : v)
  return Number.isNaN(d.getTime()) ? String(v) : d.toLocaleString('zh-TW', { hour12: false })
}

onMounted(load)
</script>

<style scoped>
.ai-provider { border: 1px solid var(--bs-border-color); border-radius: .5rem; padding: .75rem; }
.ai-answer { border: 1px solid var(--bs-border-color); border-radius: .5rem; padding: .75rem; }
.ai-answer__text { white-space: pre-wrap; }
</style>
