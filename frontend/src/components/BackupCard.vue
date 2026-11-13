<!--
  後台「系統設定」：資料備份（只有 admin 看得到）。匯出／匯入還原「不是同步排程抓來的」資料
  （後台帳號、會員、會員的倉庫／藍圖／艦隊、系統設定、工具網站，可選紀錄），見 src/backup.py、/data/backup/*。
  匯出：勾要哪幾類，下載 .json.gz。匯入：選檔先讀摘要（dry_run），勾要還原哪幾類，按「還原」再按一次「確定還原」才寫入；
  還原＝整個資料表換成檔案內容（不是合併）。
-->
<template>
  <div class="card border-0 shadow-sm mb-3">
    <div class="card-body p-4">
      <h6 class="fw-semibold mb-1"><i class="bi bi-database-down me-1"></i>資料備份</h6>
      <p class="text-body-secondary small mb-3">匯出／還原不是同步排程抓來的資料（帳號、會員與會員資料、系統設定、工具網站，可選紀錄）。還原會把勾選的資料表整個換成檔案內容，不是合併。</p>
      <div v-if="message && messageType === 'danger'" class="alert alert-danger py-2">{{ message }}</div>
      <div v-if="loading" class="text-muted small">載入中…</div>
      <div v-else class="row g-4">
        <!-- 匯出 -->
        <div class="col-12 col-lg-6">
          <div class="fw-semibold mb-2">匯出</div>
          <div v-for="s in sets" :key="s.key" class="form-check mb-1">
            <input :id="`bk-ex-${s.key}`" v-model="exportKeys" class="form-check-input" type="checkbox" :value="s.key">
            <label class="form-check-label" :for="`bk-ex-${s.key}`">
              {{ s.label }}
              <span class="text-muted small ms-1">{{ s.collections.map(c => `${c.name} ${c.count}`).join('、') }}</span>
            </label>
          </div>
          <button type="button" class="btn btn-sm btn-primary mt-2" :disabled="!exportKeys.length || exporting" @click="doExport">
            <span v-if="exporting" class="spinner-border spinner-border-sm me-1"></span><i v-else class="bi bi-download me-1"></i>匯出
          </button>
        </div>

        <!-- 匯入還原 -->
        <div class="col-12 col-lg-6">
          <div class="fw-semibold mb-2">匯入還原</div>
          <input ref="fileEl" type="file" class="form-control form-control-sm" accept=".gz,.json,application/gzip,application/json"
            aria-label="選擇備份檔" @change="onFile">
          <div v-if="reading" class="text-muted small mt-2">讀取中…</div>
          <template v-if="fileSummary">
            <div class="small text-muted mt-2">匯出時間：{{ fmtTime(fileSummary.exported_at) }}</div>
            <div v-for="s in fileSummary.sets" :key="s.key" class="form-check mt-1">
              <input :id="`bk-im-${s.key}`" v-model="importKeys" class="form-check-input" type="checkbox" :value="s.key"
                @change="confirming = false">
              <label class="form-check-label" :for="`bk-im-${s.key}`">
                {{ s.label }}
                <span class="text-muted small ms-1">{{ s.collections.map(c => `${c.name} ${c.count}`).join('、') }}</span>
              </label>
            </div>
            <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
              <button v-if="!confirming" type="button" class="btn btn-sm btn-danger" :disabled="!importKeys.length"
                @click="confirming = true"><i class="bi bi-arrow-counterclockwise me-1"></i>還原</button>
              <template v-else>
                <span class="text-danger small">勾選的資料會整個換成檔案裡的內容</span>
                <button type="button" class="btn btn-sm btn-danger" :disabled="restoring" @click="doRestore">
                  <span v-if="restoring" class="spinner-border spinner-border-sm me-1"></span>確定還原</button>
                <button type="button" class="btn btn-sm btn-secondary" :disabled="restoring" @click="confirming = false">取消</button>
              </template>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { toast } from '@/utils/toast'
import { onMounted, ref, watch } from 'vue'
import { apiFetch } from '@/api'

const sets = ref([])
const loading = ref(true)
const message = ref('')
const messageType = ref('success')
// 錯誤留在卡片裡（要修的地方）；成功改用全站的 toast（utils/toast.js），不把卡片內容往下推
watch([message, messageType], ([m, t]) => {
  if (m && t !== 'danger') {
    toast(m, t)
    message.value = ''
  }
})
const exportKeys = ref([])
const exporting = ref(false)

const fileEl = ref(null)
let file = null
const reading = ref(false)
const fileSummary = ref(null)
const importKeys = ref([])
const confirming = ref(false)
const restoring = ref(false)

function say(text, type = 'success') {
  message.value = text
  messageType.value = type
}

async function loadSets() {
  loading.value = true
  const res = await apiFetch('/data/backup/sets')
  const data = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!data?.success) return say(data?.message || '讀取失敗。', 'danger')
  sets.value = data.data
  exportKeys.value = data.data.filter(s => s.default).map(s => s.key)
}

async function doExport() {
  exporting.value = true
  message.value = ''
  const qs = exportKeys.value.map(k => `set=${encodeURIComponent(k)}`).join('&')
  const res = await apiFetch(`/data/backup/export?${qs}`)
  exporting.value = false
  if (!res?.ok) {
    const data = res ? await res.json().catch(() => null) : null
    return say(data?.message || '匯出失敗。', 'danger')
  }
  const blob = await res.blob()
  const name = (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] || 'sc-tool-backup.json.gz'
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
  say('已匯出。')
}

function upload(extra) {
  const fd = new FormData()
  fd.append('file', file)
  for (const [k, v] of extra) fd.append(k, v)
  return apiFetch('/data/backup/import', { method: 'POST', body: fd })
}

async function onFile(event) {
  file = event.target.files?.[0] || null
  fileSummary.value = null
  importKeys.value = []
  confirming.value = false
  message.value = ''
  if (!file) return
  reading.value = true
  const res = await upload([['dry_run', '1']])
  const data = res ? await res.json().catch(() => null) : null
  reading.value = false
  if (!data?.success) return say(data?.message || '讀取備份檔失敗。', 'danger')
  fileSummary.value = data.data
  importKeys.value = data.data.sets.map(s => s.key)
}

async function doRestore() {
  restoring.value = true
  const res = await upload(importKeys.value.map(k => ['set', k]))
  const data = res ? await res.json().catch(() => null) : null
  restoring.value = false
  confirming.value = false
  if (!data?.success) return say(data?.message || '還原失敗。', 'danger')
  const total = Object.values(data.data.restored).reduce((a, b) => a + b, 0)
  say(`已還原 ${Object.keys(data.data.restored).length} 個資料表、共 ${total} 筆。`)
  fileSummary.value = null
  importKeys.value = []
  file = null
  if (fileEl.value) fileEl.value.value = ''
  loadSets()
}

function fmtTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString('zh-TW', { hour12: false })
}

onMounted(loadSets)
</script>
