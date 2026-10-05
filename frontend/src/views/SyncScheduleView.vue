<!--
  後台「資料同步排程」頁。

  每個資料庫（翻譯、物品、載具、商品、藍圖、勢力、任務、礦物、地點、UEX 價格）是一個
  同步項目，各自有 cron、啟用狀態與上次結果（後端 src/models/sync_schedule.py 的
  SyncJobs，API 在 app/item/view.py 的 /item/sync-jobs）。這頁可以個別改時間、
  個別手動同步，也可以全部一起同步。UEX 那一列另外可以直接設定 API token（只有 admin，
  /item/sync-uex-token，後端只回末 4 碼）。

  不同項目可以同時同步（每一項各自一個 Celery 任務、各自一把鎖；同時跑幾個看
  worker 的 concurrency，超過的會排隊）。上方「進行中」區塊即時顯示正在跑與排隊中
  的項目、目前階段與進度，每 3 秒更新一次；「正在跑」以該項的鎖為準（後端 running
  欄位），worker 被砍掉也不會一直顯示。
-->
<template>
  <div>
    <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-3">
      <h5 class="mb-0 fw-bold"><i class="bi bi-arrow-repeat me-2 text-primary"></i>資料同步排程</h5>
      <button v-if="canSync" class="btn btn-sm btn-primary" :disabled="!idleJobs.length || triggering"
        @click="trigger(null)">
        <i class="bi bi-arrow-repeat me-1"></i>全部立即同步
      </button>
    </div>

    <Transition name="alert-slide">
      <div v-if="message" :class="`alert alert-${messageType} py-2 mb-3`">{{ message }}</div>
    </Transition>

    <!-- 進行中（即時） -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-body p-3">
        <div class="d-flex align-items-center gap-2 mb-2">
          <h6 class="fw-semibold mb-0">進行中</h6>
          <span v-if="activeJobs.length" class="badge bg-primary">{{ runningJobs.length }} 個執行中</span>
          <span v-if="queuedJobs.length" class="badge bg-warning text-dark">{{ queuedJobs.length }} 個排隊中</span>
          <span class="ms-auto small text-muted live-dot" :class="{ 'live-dot--on': !loadFailed }">
            {{ lastUpdatedLabel }}
          </span>
        </div>
        <div v-if="!activeJobs.length" class="small text-muted">目前沒有進行中的同步</div>
        <div v-else class="row g-2">
          <div v-for="job in activeJobs" :key="job.key" class="col-12 col-md-6 col-xl-4">
            <div class="live-job" :class="job.running ? 'live-job--running' : 'live-job--queued'">
              <div class="d-flex align-items-center gap-2">
                <span v-if="job.running" class="spinner-border spinner-border-sm text-primary"></span>
                <i v-else class="bi bi-hourglass-split text-warning"></i>
                <span class="fw-semibold">{{ job.label }}</span>
                <span class="small text-muted ms-auto text-nowrap">
                  {{ job.running ? `已執行 ${elapsed(job.running_since)}` : `排隊 ${elapsed(job.queued_at)}` }}
                </span>
              </div>
              <template v-if="job.running">
                <div class="small mt-1">{{ job.progress?.phase || '準備中' }}</div>
                <div v-if="progressPct(job) !== null" class="progress mt-1" role="progressbar"
                  :aria-valuenow="progressPct(job)" aria-valuemin="0" aria-valuemax="100" style="height: 6px">
                  <div class="progress-bar" :style="{ width: `${progressPct(job)}%` }"></div>
                </div>
                <div v-if="job.progress?.seen !== undefined" class="small text-muted mt-1">
                  已處理 {{ fmtInt(job.progress.seen) }}<span v-if="job.progress.total"> / 約 {{ fmtInt(job.progress.total) }}</span>
                </div>
              </template>
              <div v-else class="small text-muted mt-1">等待 worker 接手</div>
              <div class="small text-muted mt-1">{{ triggeredByLabel(job) }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="card border-0 shadow-sm mb-3">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0 small">
            <thead class="table-light">
              <tr>
                <th class="ps-3">項目</th>
                <th class="text-end">筆數</th>
                <th>排程（{{ timezone }}）</th>
                <th>啟用</th>
                <th>下次執行</th>
                <th>上次執行</th>
                <th class="pe-3 text-end">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading && !jobs.length">
                <td colspan="7" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed && !jobs.length">
                <td colspan="7" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取同步排程失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="fetchJobs">重試</button>
                </td>
              </tr>
              <tr v-for="job in jobs" v-else :key="job.key" :class="{ 'table-primary': job.running }">
                <td class="ps-3 fw-semibold text-nowrap">
                  {{ job.label }}
                  <span v-if="job.running" class="badge bg-primary ms-1">同步中</span>
                  <span v-else-if="job.queued" class="badge bg-warning text-dark ms-1">排隊中</span>
                  <div class="text-muted font-monospace fw-normal job-key">{{ job.key }}</div>
                  <!-- UEX 需要 token：admin 才看得到設定狀態（只顯示末 4 碼） -->
                  <div v-if="job.key === 'uex' && isAdmin && uexStatus" class="fw-normal mt-1">
                    <span v-if="uexStatus.configured" class="badge bg-success-subtle text-success-emphasis">
                      token {{ uexStatus.masked }}{{ uexStatus.source === 'env' ? '（環境變數）' : '' }}
                    </span>
                    <span v-else class="badge bg-warning-subtle text-warning-emphasis">未設定 token</span>
                  </div>
                </td>
                <td class="text-end">{{ fmtInt(job.count) }}</td>
                <td>
                  <input v-model="drafts[job.key].cron" type="text" class="form-control form-control-sm cron-input"
                    :class="{ 'is-invalid': errors[job.key] }" :disabled="!canSync" placeholder="30 4 * * 1"
                    :aria-label="`${job.label} 排程`" @keydown.enter="save(job)">
                  <div v-if="errors[job.key]" class="invalid-feedback d-block">{{ errors[job.key] }}</div>
                </td>
                <td>
                  <div class="form-check form-switch mb-0">
                    <input :id="`job-enabled-${job.key}`" v-model="drafts[job.key].enabled" class="form-check-input"
                      type="checkbox" role="switch" :disabled="!canSync" :aria-label="`${job.label} 啟用排程`">
                  </div>
                </td>
                <td class="text-nowrap">
                  <span v-if="!job.enabled" class="text-muted">已停用</span>
                  <span v-else>{{ fmtTime(job.next_run) }}</span>
                </td>
                <td>
                  <template v-if="job.last_finished_at">
                    <span class="badge me-1" :class="resultClass(job)">{{ resultLabel(job) }}</span>
                    <span class="text-nowrap">{{ fmtTime(job.last_finished_at) }}</span>
                    <span class="text-muted"> · {{ fmtDuration(job.last_duration_s) }}</span>
                    <span v-if="statsLabel(job)" class="text-muted"> · {{ statsLabel(job) }}</span>
                    <div v-if="job.last_error" class="text-danger last-error" :title="job.last_error">{{ job.last_error }}</div>
                  </template>
                  <span v-else class="text-muted">尚未執行</span>
                </td>
                <td class="pe-3 text-end text-nowrap">
                  <template v-if="canSync">
                    <button v-if="isDirty(job)" class="btn btn-sm btn-outline-primary me-1"
                      :disabled="saving[job.key]" @click="save(job)">
                      <span v-if="saving[job.key]" class="spinner-border spinner-border-sm me-1"></span>儲存
                    </button>
                    <button v-if="job.key === 'uex' && isAdmin" class="btn btn-sm btn-outline-primary me-1"
                      :aria-expanded="uexEditing ? 'true' : 'false'" @click="toggleUexEdit">
                      <i class="bi bi-key me-1"></i>設定 token
                    </button>
                    <button class="btn btn-sm btn-outline-secondary" :disabled="job.running || job.queued || triggering"
                      @click="trigger([job.key])">
                      <i class="bi bi-arrow-repeat me-1"></i>立即同步
                    </button>
                  </template>
                </td>
              </tr>
              <tr v-for="job in uexEditRows" :key="`${job.key}-token`">
                <td colspan="7" class="ps-3 pe-3">
                  <form class="d-flex flex-wrap align-items-center gap-2" @submit.prevent="saveUexToken(uexDraft)">
                    <label class="fw-semibold mb-0" for="uex-token-input">UEX API token</label>
                    <input id="uex-token-input" v-model="uexDraft" type="password" class="form-control form-control-sm uex-token-input"
                      autocomplete="off" maxlength="500" :placeholder="uexStatus?.configured ? `目前 ${uexStatus.masked}，填新的會取代` : 'abcd1234'">
                    <button type="submit" class="btn btn-sm btn-primary" :disabled="uexSaving || !uexDraft.trim()">
                      <span v-if="uexSaving" class="spinner-border spinner-border-sm me-1"></span>儲存
                    </button>
                    <button v-if="uexStatus?.source === 'admin'" type="button" class="btn btn-sm btn-outline-danger"
                      :disabled="uexSaving" @click="saveUexToken('')">清除</button>
                    <button type="button" class="btn btn-sm btn-outline-secondary" @click="uexEditing = false">取消</button>
                    <a class="small ms-auto" href="https://uexcorp.space/api/apps" target="_blank" rel="noopener">取得 token</a>
                  </form>
                  <div v-if="uexError" class="text-danger mt-1">{{ uexError }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 同步紀錄 -->
    <div class="card border-0 shadow-sm">
      <div class="card-body p-4">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <h6 class="fw-semibold mb-0">同步紀錄</h6>
          <button class="btn btn-sm btn-link p-0" :disabled="runsLoading" @click="fetchSyncRuns">
            <span v-if="runsLoading" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="bi bi-arrow-clockwise me-1"></i>重新整理
          </button>
        </div>
        <div style="overflow-x:auto">
          <table class="table table-sm table-hover align-middle mb-0 small">
            <thead class="table-light">
              <tr>
                <th>開始時間</th>
                <th>耗時</th>
                <th>項目</th>
                <th>結果</th>
                <th>備註</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="runsLoading && !syncRuns.length">
                <td colspan="5" class="text-center py-4 text-muted">載入中…</td>
              </tr>
              <tr v-else-if="!syncRuns.length">
                <td colspan="5" class="text-center py-4 text-muted">還沒有任何同步紀錄</td>
              </tr>
              <tr v-for="run in syncRuns" v-else :key="run._id">
                <td class="text-nowrap">{{ fmtTime(run.started_at) }}</td>
                <td class="text-nowrap">{{ fmtDuration(run.duration_s) }}</td>
                <td>{{ runJobsLabel(run) }}</td>
                <td>
                  <span class="badge" :class="run.ok ? 'bg-success' : 'bg-danger'">{{ run.ok ? '成功' : '失敗' }}</span>
                </td>
                <td class="text-muted">{{ errorSummary(run) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { itemApi } from '@/api'

const auth = useAuthStore()
// 改排程、立即同步只給 admin / operator，其餘角色唯讀
const canSync = computed(() => auth.role === 'admin' || auth.role === 'operator')

// 舊版同步紀錄沒有 jobs 欄位，用這張表把 resources／with_* 翻成項目名稱
const LEGACY_LABELS = {
  translations: '翻譯', items: '物品', vehicles: '載具', commodities: '商品', blueprints: '藍圖',
  factions: '勢力', missions: '任務', mining: '礦物', locations: '地點', uex: 'UEX 價格',
}

const jobs = ref([])
const timezone = ref('Asia/Taipei')
const loading = ref(false)
const loadFailed = ref(false)
const drafts = reactive({})
const errors = reactive({})
const saving = reactive({})
const triggering = ref(false)
const message = ref('')
const messageType = ref('success')
let pollTimer = null
let tickTimer = null
let wasActive = false
let messageTimer = null
// 伺服器時間 − 本機時間（毫秒），「已執行多久」用伺服器時間算
let clockOffset = 0
const now = ref(Date.now())
const lastFetchedAt = ref(0)

// 有東西在跑時 3 秒更新一次；閒置時 15 秒（排程到期會自己開始，也要看得到）
const POLL_ACTIVE_MS = 3000
const POLL_IDLE_MS = 15000

const labelOf = key => jobs.value.find(j => j.key === key)?.label || LEGACY_LABELS[key] || key

const runningJobs = computed(() => jobs.value.filter(j => j.running))
const queuedJobs = computed(() => jobs.value.filter(j => !j.running && j.queued))
const activeJobs = computed(() => [...runningJobs.value, ...queuedJobs.value])
const idleJobs = computed(() => jobs.value.filter(j => !j.running && !j.queued))

const lastUpdatedLabel = computed(() => {
  if (!lastFetchedAt.value) return ''
  const s = Math.max(0, Math.round((now.value - lastFetchedAt.value) / 1000))
  return s < 2 ? '即時' : `${s} 秒前更新`
})

function elapsed(iso) {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (isNaN(t)) return '—'
  const s = Math.max(0, Math.round((now.value + clockOffset - t) / 1000))
  if (s < 60) return `${s} 秒`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} 分 ${s % 60} 秒`
  return `${Math.floor(m / 60)} 小時 ${m % 60} 分`
}

function progressPct(job) {
  const p = job.progress || {}
  if (!p.total || p.seen === undefined) return null
  return Math.min(100, Math.round((p.seen / p.total) * 100))
}

function triggeredByLabel(job) {
  const by = job.queued_by
  if (!by) return ''
  return by === 'schedule' ? '排程觸發' : `${by} 手動觸發`
}

function flash(text, type = 'success') {
  message.value = text
  messageType.value = type
  clearTimeout(messageTimer)
  messageTimer = setTimeout(() => { message.value = '' }, 4000)
}

function syncDraft(job, force = false) {
  if (!drafts[job.key] || force) drafts[job.key] = { cron: job.cron || '', enabled: !!job.enabled }
}

function isDirty(job) {
  const d = drafts[job.key]
  return !!d && (d.cron.trim() !== (job.cron || '') || d.enabled !== !!job.enabled)
}

async function fetchJobs() {
  loading.value = true
  try {
    const res = await itemApi.syncJobs()
    const body = res?.ok ? await res.json().catch(() => null) : null
    if (!body?.success) {
      loadFailed.value = true
      return
    }
    loadFailed.value = false
    lastFetchedAt.value = Date.now()
    const serverTime = new Date(body.data.server_time).getTime()
    if (!isNaN(serverTime)) clockOffset = serverTime - Date.now()
    timezone.value = body.data.timezone || timezone.value
    jobs.value = body.data.jobs || []
    // 沒改過的列跟著伺服器更新；正在編輯的不要蓋掉
    for (const job of jobs.value) {
      if (!drafts[job.key] || !isDirtyAgainst(job, drafts[job.key])) syncDraft(job, true)
    }
    const active = jobs.value.some(j => j.running || j.queued)
    // 有項目剛結束 → 補抓同步紀錄（上次結果、下次時間在 jobs 裡已經更新了）
    if (wasActive && !active) fetchSyncRuns()
    wasActive = active
    schedulePoll(active ? POLL_ACTIVE_MS : POLL_IDLE_MS)
  } finally {
    loading.value = false
  }
}

// 用「上一次伺服器值」判斷使用者有沒有改過——伺服器值更新後，未改過的草稿要跟著變
const lastServer = {}
function isDirtyAgainst(job, draft) {
  const prev = lastServer[job.key]
  lastServer[job.key] = { cron: job.cron || '', enabled: !!job.enabled }
  if (!prev) return false
  return draft.cron.trim() !== prev.cron || draft.enabled !== prev.enabled
}

function schedulePoll(ms) {
  clearTimeout(pollTimer)
  if (document.hidden) return
  pollTimer = setTimeout(fetchJobs, ms)
}
function stopPolling() {
  clearTimeout(pollTimer)
  pollTimer = null
}

async function save(job) {
  const draft = drafts[job.key]
  errors[job.key] = ''
  saving[job.key] = true
  try {
    const res = await itemApi.updateSyncJob(job.key, { cron: draft.cron.trim(), enabled: draft.enabled })
    const body = res ? await res.json().catch(() => null) : null
    if (!res?.ok || !body?.success) {
      errors[job.key] = body?.message || '儲存失敗'
      return
    }
    const i = jobs.value.findIndex(j => j.key === job.key)
    if (i >= 0) jobs.value[i] = body.data
    lastServer[job.key] = { cron: body.data.cron || '', enabled: !!body.data.enabled }
    syncDraft(body.data, true)
    flash(`已儲存「${body.data.label}」的排程`)
  } finally {
    saving[job.key] = false
  }
}

// ── UEX API token（只有 admin；後端只回末 4 碼，見 src/models/app_setting.py）──
const isAdmin = computed(() => auth.role === 'admin')
const uexStatus = ref(null)
const uexEditing = ref(false)
const uexDraft = ref('')
const uexSaving = ref(false)
const uexError = ref('')
// 編輯列接在項目列表後面（UEX 固定排最後一項，所以就在它正下方）
const uexEditRows = computed(() => (uexEditing.value ? jobs.value.filter(j => j.key === 'uex') : []))

async function fetchUexToken() {
  if (!isAdmin.value) return
  const res = await itemApi.uexToken()
  const body = res ? await res.json().catch(() => null) : null
  if (res?.ok && body?.success) uexStatus.value = body.data
}

function toggleUexEdit() {
  uexEditing.value = !uexEditing.value
  uexDraft.value = ''
  uexError.value = ''
}

async function saveUexToken(token) {
  uexSaving.value = true
  uexError.value = ''
  try {
    const res = await itemApi.setUexToken(token.trim())
    const body = res ? await res.json().catch(() => null) : null
    if (!res?.ok || !body?.success) {
      uexError.value = body?.message || '儲存失敗'
      return
    }
    uexStatus.value = body.data
    uexEditing.value = false
    uexDraft.value = ''
    flash(token ? '已儲存 UEX token' : '已清除後台設定的 UEX token')
  } finally {
    uexSaving.value = false
  }
}

async function trigger(keys) {
  if (triggering.value) return
  triggering.value = true
  try {
    const res = await itemApi.syncNow(keys ? { jobs: keys } : {})
    const body = res ? await res.json().catch(() => null) : null
    if (!res?.ok || !body?.success) {
      flash(body?.message || (res?.status === 409 ? '這些項目都已經在同步或排隊中' : '觸發同步失敗'), 'danger')
      return
    }
    const sent = (body.dispatched || []).map(labelOf).join('、')
    const skipped = (body.skipped || []).map(labelOf).join('、')
    flash(`已排入同步：${sent}${skipped ? `（${skipped} 已在進行中，略過）` : ''}`)
    fetchJobs()
  } finally {
    triggering.value = false
  }
}

function resultLabel(job) {
  if (job.last_ok === true) return '成功'
  if (job.last_ok === false) return job.consecutive_failures > 1 ? `失敗 ×${job.consecutive_failures}` : '失敗'
  return '略過'
}
function resultClass(job) {
  if (job.last_ok === true) return 'bg-success'
  if (job.last_ok === false) return 'bg-danger'
  return 'bg-secondary'
}
function statsLabel(job) {
  const s = job.last_stats || {}
  const parts = []
  if (s.seen !== undefined) parts.push(`讀取 ${fmtInt(s.seen)}`)
  if (s.written !== undefined) parts.push(`寫入 ${fmtInt(s.written)}`)
  if (s.retired) parts.push(`下架 ${fmtInt(s.retired)}`)
  return parts.join(' · ')
}

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d) ? iso : d.toLocaleString()
}
function fmtDuration(s) {
  if (s === null || s === undefined) return '—'
  if (s < 60) return `${s} 秒`
  return `${Math.floor(s / 60)} 分 ${Math.round(s % 60)} 秒`
}
function fmtInt(v) {
  if (v === null || v === undefined) return '—'
  return Number(v).toLocaleString('en-US')
}

// ── 同步紀錄 ──────────────────────────────────────────────────
const syncRuns = ref([])
const runsLoading = ref(false)

async function fetchSyncRuns() {
  runsLoading.value = true
  try {
    const res = await itemApi.syncRuns(20)
    const body = res?.ok ? await res.json().catch(() => null) : null
    if (body?.success) syncRuns.value = body.data || []
  } finally {
    runsLoading.value = false
  }
}

function runJobsLabel(run) {
  let keys = run.jobs
  if (!keys) {
    keys = [...(run.translations_only || run.with_translations ? ['translations'] : []),
      ...(run.resources || []),
      ...(run.with_scunpacked ? ['mining'] : []),
      ...(run.with_uex ? ['uex'] : [])]
  }
  const skipped = new Set(run.skipped_jobs || [])
  return keys.length ? keys.map(k => labelOf(k) + (skipped.has(k) ? '（略過）' : '')).join('、') : '—'
}

function errorSummary(run) {
  if (!run.errors || !run.errors.length) return '—'
  const first = run.errors[0]
  return run.errors.length > 1 ? `${first}（共 ${run.errors.length} 筆錯誤）` : first
}

// 頁面切到背景時不輪詢，切回來立刻更新一次
function onVisibility() {
  if (document.hidden) stopPolling()
  else fetchJobs()
}

onMounted(() => {
  fetchJobs()
  fetchSyncRuns()
  fetchUexToken()
  tickTimer = setInterval(() => { now.value = Date.now() }, 1000)
  document.addEventListener('visibilitychange', onVisibility)
})
onUnmounted(() => {
  stopPolling()
  clearInterval(tickTimer)
  clearTimeout(messageTimer)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>

<style scoped>
.cron-input { min-width: 9rem; max-width: 11rem; font-family: var(--bs-font-monospace); }
.job-key { font-size: .72rem; }
.uex-token-input { max-width: 22rem; font-family: var(--bs-font-monospace); }
.live-job {
  border: 1px solid var(--bs-border-color); border-radius: .5rem;
  padding: .6rem .75rem; height: 100%;
}
.live-job--running { border-left: 3px solid var(--bs-primary); }
.live-job--queued  { border-left: 3px solid var(--bs-warning); }
.live-dot::before {
  content: ''; display: inline-block; width: .45rem; height: .45rem; border-radius: 50%;
  margin-right: .35rem; vertical-align: middle; background: var(--bs-secondary-color);
}
.live-dot--on::before { background: var(--bs-success); }
.last-error { max-width: 22rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>
