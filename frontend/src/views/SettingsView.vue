<template>
  <div>
    <h4 class="fw-bold mb-4"><i class="bi bi-gear me-2"></i>系統設定</h4>

    <!-- 資料同步 -->
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
          </template>
          <div v-else class="text-danger">無法取得同步狀態</div>
        </div>

        <button
          v-if="canSync"
          class="btn btn-sm btn-primary"
          :disabled="syncState === 'running'"
          @click="triggerSync"
        >
          <span v-if="syncState === 'running'" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-arrow-repeat me-1"></i>
          立即同步
        </button>
        <div v-if="syncMessage" class="text-danger small mt-2">{{ syncMessage }}</div>

        <!-- 自動同步排程（可在此改 cron，不用改設定檔、不用重啟 worker/beat） -->
        <hr class="my-3">
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
        </template>
        <div v-else class="text-danger small">無法取得排程設定</div>
      </div>
    </div>

    <!-- 外觀模式 -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-body p-4">
        <h6 class="fw-semibold mb-1">外觀模式</h6>
        <p class="text-muted small mb-3">深色、淺色，或自動跟隨系統設定。</p>
        <div class="mode-row">
          <button
            v-for="m in theme.modes"
            :key="m.id"
            class="mode-btn"
            :class="{ active: theme.mode === m.id }"
            @click="theme.setMode(m.id)"
          >
            <i :class="['bi', m.icon, 'mode-icon']"></i>
            <span>{{ m.name }}</span>
          </button>
        </div>
      </div>
    </div>

    <!-- 頁面背景 -->
    <div class="card border-0 shadow-sm mb-3">
      <div class="card-body p-4">
        <h6 class="fw-semibold mb-1">頁面背景顏色</h6>
        <p class="text-muted small mb-3">調整內容區的背景色，可選擇預設色票或自訂。</p>

        <div class="bg-swatches">
          <!-- 跟隨主題（重設） -->
          <button
            class="bg-swatch reset-swatch"
            :class="{ active: !theme.isCustomBg }"
            @click="theme.resetContentBg()"
            title="跟隨主題預設"
          >
            <i class="bi bi-arrow-counterclockwise"></i>
            <span>預設</span>
          </button>

          <!-- 預設色票 -->
          <button
            v-for="s in BG_SWATCHES"
            :key="s.hex"
            class="bg-swatch"
            :class="{ active: theme.isCustomBg && theme.contentBg === s.hex }"
            :style="{ background: s.hex }"
            :title="s.name"
            @click="theme.setContentBg(s.hex)"
          >
            <i v-if="theme.isCustomBg && theme.contentBg === s.hex"
               class="bi bi-check2 check-icon"></i>
          </button>

          <!-- 自訂色票 -->
          <label
            class="bg-swatch custom-swatch"
            :class="{ active: theme.isCustomBg && !BG_SWATCHES.some(s => s.hex === theme.contentBg) }"
            title="自訂顏色"
            :style="theme.isCustomBg && !BG_SWATCHES.some(s => s.hex === theme.contentBg)
              ? { background: theme.contentBg } : {}"
          >
            <i class="bi bi-eyedropper"></i>
            <span>自訂</span>
            <input type="color"
              class="color-input"
              :value="theme.contentBg || '#f5f6fa'"
              @input="e => theme.setContentBg(e.target.value)"
            />
          </label>
        </div>

        <!-- 即時預覽條 -->
        <div class="bg-preview-bar mt-3"
          :style="{ background: theme.isCustomBg ? theme.contentBg : '' }">
          <span class="text-muted small">背景預覽</span>
        </div>
      </div>
    </div>

    <!-- 主題色彩 -->
    <div class="card border-0 shadow-sm">
      <div class="card-body p-4">
        <h6 class="fw-semibold mb-1">主題色彩</h6>
        <p class="text-muted small mb-3">選擇 sidebar 高亮主色，深色和淺色模式均適用。</p>
        <div class="accent-grid">
          <!-- 預設色票 -->
          <button
            v-for="a in theme.accents"
            :key="a.id"
            class="accent-card"
            :class="{ active: theme.accentId === a.id && !theme.isCustom }"
            @click="theme.setAccent(a.id)"
          >
            <div class="accent-preview">
              <div class="ap-half" :style="{ background: a.dark.sbBg }">
                <div class="ap-dot" :style="{ background: a.accent }"></div>
                <div class="ap-dot dim"></div>
              </div>
              <div class="ap-half ap-light">
                <div class="ap-dot" :style="{ background: a.accent }"></div>
                <div class="ap-dot dim light"></div>
              </div>
            </div>
            <div class="accent-label">
              {{ a.name }}
              <i v-if="theme.accentId === a.id && !theme.isCustom"
                 class="bi bi-check-circle-fill text-success ms-1"></i>
            </div>
          </button>

          <!-- 自訂色票 -->
          <label
            class="accent-card"
            :class="{ active: theme.isCustom }"
            title="自訂色彩"
          >
            <div class="accent-preview custom-preview">
              <div class="ap-half" :style="{ background: '#1e2130' }">
                <div class="ap-dot" :style="{ background: theme.customColor }"></div>
                <div class="ap-dot dim"></div>
              </div>
              <div class="ap-half ap-light">
                <div class="ap-dot" :style="{ background: theme.customColor }"></div>
                <div class="ap-dot dim light"></div>
              </div>
              <input
                type="color"
                class="color-input"
                :value="theme.customColor"
                @input="e => theme.setCustomColor(e.target.value)"
              />
            </div>
            <div class="accent-label">
              自訂
              <i v-if="theme.isCustom" class="bi bi-check-circle-fill text-success ms-1"></i>
            </div>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useAuthStore } from '@/stores/auth'
import { itemApi } from '@/api'

const theme = useThemeStore()
const auth = useAuthStore()

// 「立即同步」只給 admin / operator，其餘角色僅唯讀顯示狀態
const canSync = computed(() => auth.role === 'admin' || auth.role === 'operator')

const syncStatus  = ref(null)
const syncLoading = ref(false)
const syncState   = ref('idle') // idle | running | done | error
let pollTimer = null
let clickedAt = 0

const stateLabel = computed(() => ({
  idle: '閒置', running: '同步中…', done: '已完成', error: '發生錯誤',
}[syncState.value] || '閒置'))

const stateBadgeClass = computed(() => ({
  idle: 'bg-secondary', running: 'bg-primary', done: 'bg-success', error: 'bg-danger',
}[syncState.value] || 'bg-secondary'))

function formatTime(iso) {
  if (!iso) return '尚未同步'
  const d = new Date(iso)
  return isNaN(d) ? iso : d.toLocaleString()
}

async function fetchSyncStatus() {
  syncLoading.value = true
  try {
    const res = await itemApi.syncStatus()
    if (res && res.ok) {
      const body = await res.json()
      if (body.success) {
        syncStatus.value = body.data

        // 若正在等待這次觸發的同步完成，用 finished_at 是否晚於點擊時間來判斷有沒有跑完
        if (syncState.value === 'running') {
          const finishedAt = body.data.latest_run?.finished_at
          if (finishedAt && new Date(finishedAt).getTime() >= clickedAt) {
            syncState.value = body.data.latest_run.ok ? 'done' : 'error'
            stopPolling()
          }
        }
      }
    }
  } finally {
    syncLoading.value = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(fetchSyncStatus, 5000)
}
function stopPolling() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
}

const syncMessage = ref('')

async function triggerSync() {
  if (syncState.value === 'running') return
  clickedAt = Date.now()
  syncState.value = 'running'
  syncMessage.value = ''
  const res = await itemApi.syncNow()
  if (!res || !res.ok) {
    syncState.value = 'error'
    // 後端對「已有一輪同步進行中」正確回 409，這裡要分辨出來，
    // 不能一律顯示成籠統的「發生錯誤」，否則使用者會誤以為同步失敗了。
    if (res && res.status === 409) {
      const body = await res.json().catch(() => null)
      syncMessage.value = (body && body.message) || '已有同步進行中，請稍後再試'
    } else {
      syncMessage.value = '觸發同步失敗，請稍後再試'
    }
    return
  }
  startPolling()
  fetchSyncStatus()
}

// ── 自動同步排程 ──────────────────────────────────────────────
const schedule        = ref(null)
const scheduleLoading = ref(false)
const scheduleSaving  = ref(false)
const scheduleError   = ref('')
const scheduleSaved   = ref(false)
const scheduleCron    = ref('')
const scheduleEnabled = ref(true)

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

onMounted(() => {
  fetchSyncStatus()
  fetchSyncSchedule()
})
onUnmounted(stopPolling)

const BG_SWATCHES = [
  { hex: '#f5f6fa', name: '藍白（深色預設）' },
  { hex: '#eef0f5', name: '淺藍白（淺色預設）' },
  { hex: '#ffffff', name: '純白' },
  { hex: '#fafafa', name: '暖白' },
  { hex: '#f0f4f8', name: '冷藍灰' },
  { hex: '#f5f0eb', name: '暖米' },
  { hex: '#1e1e2e', name: '深藍黑' },
  { hex: '#1e1e1e', name: '深灰' },
]
</script>

<style scoped>
/* ── Sync status ── */
.sync-status-box {
  background: rgba(0,0,0,.03);
  border-radius: .5rem;
  padding: .75rem 1rem;
  line-height: 1.6;
}

/* ── Mode ── */
.mode-row { display: flex; gap: .75rem; flex-wrap: wrap; }

.mode-btn {
  display: flex; flex-direction: column; align-items: center;
  gap: .35rem; padding: .85rem 1.5rem;
  border: 2px solid #dee2e6; border-radius: .75rem;
  background: none; cursor: pointer; min-width: 90px;
  transition: border-color .15s, box-shadow .15s;
}
.mode-btn:hover  { border-color: #adb5bd; }
.mode-btn.active { border-color: #6384ff; box-shadow: 0 0 0 3px rgba(99,132,255,.2); }
.mode-icon       { font-size: 1.5rem; color: #6c757d; }
.mode-btn.active .mode-icon { color: #6384ff; }
.mode-btn span   { font-size: .85rem; color: #495057; }

/* ── Accent ── */
.accent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(90px, 1fr));
  gap: 1rem;
}
.accent-card {
  background: none;
  border: 2px solid #dee2e6; border-radius: .75rem;
  padding: .5rem; cursor: pointer;
  transition: border-color .15s, transform .12s, box-shadow .15s;
  text-align: center;
}
.accent-card:hover  { transform: translateY(-2px); border-color: #adb5bd; }
.accent-card.active { border-color: #6384ff; box-shadow: 0 0 0 3px rgba(99,132,255,.2); }

.accent-preview {
  width: 100%; aspect-ratio: 3 / 2;
  border-radius: .4rem; overflow: hidden;
  display: flex; border: 1px solid rgba(0,0,0,.08);
  position: relative;
}
.ap-half {
  flex: 1; display: flex; flex-direction: column;
  gap: 3px; padding: 5px 4px;
}
.ap-light { background: #f8f9fa; }
.ap-dot   { height: 4px; border-radius: 2px; }
.ap-dot.dim       { background: rgba(255,255,255,.25); }
.ap-dot.dim.light { background: rgba(0,0,0,.15); }

.custom-preview { cursor: pointer; }
.color-input {
  position: absolute; inset: 0;
  opacity: 0; width: 100%; height: 100%;
  cursor: pointer;
}

.accent-label {
  margin-top: .4rem; font-size: .8rem; color: #495057;
}

/* ── Background swatches ── */
.bg-swatches {
  display: flex; flex-wrap: wrap; gap: .6rem; align-items: center;
}

.bg-swatch {
  width: 48px; height: 48px;
  border-radius: .5rem;
  border: 2px solid #dee2e6;
  cursor: pointer;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  transition: border-color .15s, transform .1s, box-shadow .15s;
  font-size: .65rem; color: #6c757d; gap: 2px;
  position: relative; overflow: hidden;
}
.bg-swatch:hover  { transform: translateY(-2px); border-color: #adb5bd; }
.bg-swatch.active { border-color: #6384ff; box-shadow: 0 0 0 3px rgba(99,132,255,.2); }

.reset-swatch  { background: linear-gradient(135deg, #f5f6fa 50%, #eef0f5 50%); }
.custom-swatch { background: conic-gradient(red, yellow, lime, cyan, blue, magenta, red); }
.custom-swatch.active { background: v-bind("theme.contentBg"); }
.custom-swatch .bi-eyedropper, .custom-swatch span { text-shadow: 0 0 3px rgba(255,255,255,.8); }

.check-icon {
  position: absolute; font-size: 1.1rem;
  color: #fff; text-shadow: 0 0 4px rgba(0,0,0,.5);
}
.color-input {
  position: absolute; inset: 0; opacity: 0;
  width: 100%; height: 100%; cursor: pointer;
}

.bg-preview-bar {
  background: var(--content-bg, #f5f6fa);
  border-radius: .5rem; border: 1px solid rgba(0,0,0,.08);
  padding: .75rem 1rem; transition: background .2s;
}
</style>
