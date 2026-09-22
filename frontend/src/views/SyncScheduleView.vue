<template>
  <div>
    <h4 class="fw-bold mb-4"><i class="bi bi-arrow-repeat me-2"></i>資料同步與排程</h4>

    <!-- 目前狀態 -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-body p-4">
        <h6 class="fw-semibold mb-1">資料同步</h6>
        <p class="text-muted small mb-3">遊戲主檔（物品／載具／商品）由社群 API 同步而來，平常每週自動跑一次。</p>

        <div class="sync-status-box text-muted small mb-3">
          <div v-if="syncLoading && !syncStatus">載入中…</div>
          <template v-else-if="syncStatus">
            <div>
              目前狀態：
              <span class="badge" :class="stateBadgeClass">{{ stateLabel }}</span>
            </div>
            <div class="mt-1">
              物品 {{ syncStatus.counts?.items ?? '—' }}
              載具 {{ syncStatus.counts?.vehicles ?? '—' }}
              商品 {{ syncStatus.counts?.commodities ?? '—' }}
            </div>
            <div class="mt-1">
              最後同步：{{ formatTime(syncStatus.latest_run?.finished_at) }}
              <span v-if="syncStatus.latest_run && !syncStatus.latest_run.ok" class="text-danger ms-1">
                （上次有錯誤）
              </span>
            </div>
            <div class="mt-1">
              下次預定執行：{{ nextRunLabel }}
            </div>
          </template>
          <div v-else class="text-danger">無法取得同步狀態</div>
        </div>

        <button
          v-if="canSync"
          class="btn btn-sm btn-primary"
          :disabled="isRunning"
          @click="triggerSync"
        >
          <span v-if="isRunning" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-arrow-repeat me-1"></i>
          立即同步
        </button>
        <div v-if="syncMessage" class="text-danger small mt-2">{{ syncMessage }}</div>
        <p class="small hint mt-2 mb-0">
          按下後是丟進背景佇列非同步執行，這個畫面會自動輪詢狀態；
          如果「目前狀態」一直沒有變成「同步中」，通常是背景的 worker／beat 容器沒有啟動
          （本機測試環境要加 <code>--profile background</code> 才會一起帶起來）。
        </p>
      </div>
    </div>

    <!-- 自動同步排程 -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-body p-4">
        <h6 class="fw-semibold mb-1">自動同步排程</h6>
        <p class="text-muted small mb-2">
          分 時 日 月 星期，例如：<code>30 4 * * 1</code> = 每週一 04:30。
          時間以 <strong>{{ schedule?.timezone || 'Asia/Taipei' }}</strong> 解讀。
          支援 <code>*</code>、<code>5</code>、<code>1-5</code>、<code>*/15</code>、<code>1,3,5</code>；
          星期的 <code>0</code> 與 <code>7</code> 都是週日。
        </p>

        <div v-if="scheduleLoading && !schedule">載入中…</div>
        <template v-else-if="schedule">
          <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
            <input
              type="text"
              class="form-control form-control-sm"
              style="max-width: 220px"
              v-model="scheduleCron"
              :disabled="!canSync"
              placeholder="30 4 * * 1"
            >
            <div class="form-check form-switch mb-0">
              <input
                class="form-check-input"
                type="checkbox"
                role="switch"
                id="scheduleEnabled"
                v-model="scheduleEnabled"
                :disabled="!canSync"
              >
              <label class="form-check-label small" for="scheduleEnabled">啟用排程</label>
            </div>
            <button
              v-if="canSync"
              class="btn btn-sm btn-outline-primary"
              :disabled="scheduleSaving"
              @click="saveSchedule"
            >
              <span v-if="scheduleSaving" class="spinner-border spinner-border-sm me-1"></span>
              儲存排程
            </button>
          </div>
          <div v-if="scheduleError" class="text-danger small mb-2">{{ scheduleError }}</div>
          <div v-if="scheduleSaved" class="text-success small mb-2">已儲存排程設定</div>
          <div class="small hint">下次預定執行：{{ nextRunLabel }}</div>
        </template>
        <div v-else class="text-danger small">無法取得排程設定</div>
      </div>
    </div>

    <!-- 同步紀錄 -->
    <div class="card border-0 shadow-sm">
      <div class="card-body p-4">
        <div class="d-flex align-items-center justify-content-between mb-1">
          <h6 class="fw-semibold mb-0">同步紀錄</h6>
          <button class="btn btn-sm btn-link p-0" :disabled="runsLoading" @click="fetchSyncRuns">
            <span v-if="runsLoading" class="spinner-border spinner-border-sm me-1"></span>
            <i v-else class="bi bi-arrow-clockwise me-1"></i>重新整理
          </button>
        </div>
        <p class="text-muted small mb-3">最近 {{ syncRuns.length }} 筆（含手動觸發與自動排程）。</p>

        <div style="overflow-x:auto">
          <table class="table table-sm table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th>開始時間</th>
                <th>耗時</th>
                <th>涵蓋資源</th>
                <th>結果</th>
                <th>備註</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="runsLoading && !syncRuns.length">
                <td colspan="5" class="text-center py-4 hint">載入中…</td>
              </tr>
              <tr v-else-if="!syncRuns.length">
                <td colspan="5" class="text-center py-4 hint">還沒有任何同步紀錄</td>
              </tr>
              <tr v-else v-for="run in syncRuns" :key="run._id">
                <td>{{ formatTime(run.started_at) }}</td>
                <td>{{ formatDuration(run.duration_s) }}</td>
                <td>{{ resourcesLabel(run) }}</td>
                <td>
                  <span class="badge" :class="run.ok ? 'bg-success' : 'bg-danger'">
                    {{ run.ok ? '成功' : '失敗' }}
                  </span>
                </td>
                <td class="hint">{{ errorSummary(run) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { itemApi } from '@/api'

const auth = useAuthStore()

// 「立即同步」只給 admin / operator，其餘角色僅唯讀顯示狀態
const canSync = computed(() => auth.role === 'admin' || auth.role === 'operator')

const syncStatus  = ref(null)
const syncLoading = ref(false)
const syncMessage = ref('')
let pollTimer = null
let wasRunning = false

// 是否「正在跑」一律以後端的 Redis 鎖為準（is_running），不是前端自己猜的——
// worker 沒開的話任務只是卡在佇列裡，latest_run 不會變，只有這個欄位看得出來。
const isRunning = computed(() => !!syncStatus.value?.is_running)

const stateLabel = computed(() => {
  if (isRunning.value) return '同步中…'
  if (!syncStatus.value?.latest_run) return '尚未執行過'
  return syncStatus.value.latest_run.ok ? '閒置' : '上次執行有錯誤'
})
const stateBadgeClass = computed(() => {
  if (isRunning.value) return 'bg-primary'
  if (!syncStatus.value?.latest_run) return 'bg-secondary'
  return syncStatus.value.latest_run.ok ? 'bg-success' : 'bg-danger'
})

function formatTime(iso) {
  if (!iso) return '尚未同步'
  const d = new Date(iso)
  return isNaN(d) ? iso : d.toLocaleString()
}

function formatDuration(s) {
  if (s === null || s === undefined) return '—'
  if (s < 60) return `${s} 秒`
  const m = Math.floor(s / 60)
  const rest = Math.round(s % 60)
  return `${m} 分 ${rest} 秒`
}

function resourcesLabel(run) {
  const parts = [...(run.resources || [])]
  if (run.with_uex) parts.push('UEX 價格')
  if (run.with_scunpacked) parts.push('礦物')
  return parts.length ? parts.join('、') : '—'
}

function errorSummary(run) {
  if (!run.errors || !run.errors.length) return '—'
  const first = run.errors[0]
  return run.errors.length > 1 ? `${first}（共 ${run.errors.length} 筆錯誤）` : first
}

async function fetchSyncStatus() {
  syncLoading.value = true
  try {
    const res = await itemApi.syncStatus()
    if (res && res.ok) {
      const body = await res.json()
      if (body.success) {
        syncStatus.value = body.data
        const running = !!body.data.is_running
        if (running) {
          startPolling()
        } else {
          stopPolling()
          // 剛好在這次輪詢看到跑完了 → 補抓一次歷史紀錄和排程（下次執行時間會變）
          if (wasRunning) {
            fetchSyncRuns()
            fetchSyncSchedule()
          }
        }
        wasRunning = running
      }
    }
  } finally {
    syncLoading.value = false
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(fetchSyncStatus, 5000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

async function triggerSync() {
  if (isRunning.value) return
  syncMessage.value = ''
  const res = await itemApi.syncNow()
  if (!res || !res.ok) {
    const body = res ? await res.json().catch(() => null) : null
    syncMessage.value = (body && body.message) ||
      (res && res.status === 409 ? '已有同步進行中，請稍後再試' : '觸發同步失敗，請稍後再試')
    fetchSyncStatus()
    return
  }
  fetchSyncStatus()
  startPolling()
}

// ── 自動同步排程 ──────────────────────────────────────────────
const schedule        = ref(null)
const scheduleLoading = ref(false)
const scheduleSaving  = ref(false)
const scheduleError   = ref('')
const scheduleSaved   = ref(false)
const scheduleCron    = ref('')
const scheduleEnabled = ref(true)

const nextRunLabel = computed(() => {
  if (!schedule.value) return '—'
  if (!schedule.value.enabled) return '（排程已停用）'
  return formatTime(schedule.value.next_run)
})

async function fetchSyncSchedule() {
  scheduleLoading.value = true
  try {
    const res = await itemApi.getSyncSchedule()
    if (res && res.ok) {
      const body = await res.json()
      if (body.success) {
        schedule.value = body.data
        scheduleCron.value = body.data.cron
        scheduleEnabled.value = body.data.enabled
      }
    }
  } finally {
    scheduleLoading.value = false
  }
}

async function saveSchedule() {
  scheduleError.value = ''
  scheduleSaved.value = false
  scheduleSaving.value = true
  try {
    const res = await itemApi.updateSyncSchedule({
      cron: scheduleCron.value,
      enabled: scheduleEnabled.value,
    })
    if (!res) {
      scheduleError.value = '儲存失敗，請稍後再試'
      return
    }
    const body = await res.json().catch(() => null)
    if (res.status === 400) {
      scheduleError.value = (body && body.message) || 'cron 表達式無效'
      return
    }
    if (!res.ok || !body || !body.success) {
      scheduleError.value = (body && body.message) || '儲存失敗，請稍後再試'
      return
    }
    schedule.value = body.data
    scheduleCron.value = body.data.cron
    scheduleEnabled.value = body.data.enabled
    scheduleSaved.value = true
  } finally {
    scheduleSaving.value = false
  }
}

// ── 同步紀錄 ──────────────────────────────────────────────────
const syncRuns    = ref([])
const runsLoading = ref(false)

async function fetchSyncRuns() {
  runsLoading.value = true
  try {
    const res = await itemApi.syncRuns(20)
    if (res && res.ok) {
      const body = await res.json()
      if (body.success) syncRuns.value = body.data || []
    }
  } finally {
    runsLoading.value = false
  }
}

onMounted(() => {
  fetchSyncStatus()
  fetchSyncSchedule()
  fetchSyncRuns()
})
onUnmounted(stopPolling)
</script>

<style scoped>
.sync-status-box {
  background: rgba(0,0,0,.03);
  border-radius: .5rem;
  padding: .75rem 1rem;
  line-height: 1.6;
}
.hint { opacity: .72; }
</style>
