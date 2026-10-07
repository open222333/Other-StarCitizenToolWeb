<!--
  玩家頁「LOG 解析」：讀玩家自己的 Game.log，整理成中文事件時間軸＋本次遊玩回顧。

  移植自 Other-Game/StarCitizen/gamelog_reader（解析規則在 utils/gameLogRules.json，
  程式在 utils/gameLog.js）。**解析完全在瀏覽器裡做，Game.log 不會上傳到伺服器**。

  讀檔兩種方式：
    - Chrome／Edge：File System Access API（showOpenFilePicker）選檔，拿到檔案控制代碼，
      可以「重新讀取」，也可以「持續監看」——每 2 秒看檔案有沒有變長，只讀新增的部分
      （遊戲重開會重寫 Game.log，檔案變短就整份重讀）
    - 其他瀏覽器：一般的檔案選擇／拖放，只能讀當下那一份
-->
<template>
  <div>
    <div :class="[cardClass, 'mb-3', { 'gamelog-drop': dragging }]"
      @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
      <div class="card-body">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <button type="button" class="btn btn-primary" :disabled="loading" @click="pickFile">
            <i class="bi bi-file-earmark-text me-1"></i>選擇 Game.log
          </button>
          <FieldHint :text="`Game.log 在遊戲安裝資料夾裡，例如 ${DEFAULT_PATH}；也可以把檔案直接拖進這個區塊。`" />
          <template v-if="handle">
            <button type="button" class="btn btn-primary" :disabled="loading" @click="reload">
              <i class="bi bi-arrow-clockwise me-1"></i>重新讀取
            </button>
            <button type="button" class="btn" :class="watching ? 'btn-secondary' : 'btn-success'"
              :disabled="loading" :aria-pressed="watching ? 'true' : 'false'" @click="toggleWatch">
              <i class="bi me-1" :class="watching ? 'bi-pause-fill' : 'bi-broadcast'"></i>{{ watching ? '停止監看' : '持續監看' }}
            </button>
          </template>
          <button v-if="fileName" type="button" class="btn btn-warning" :disabled="loading" @click="clearAll">清除</button>
          <input ref="fileInput" type="file" accept=".log,.txt,text/plain" class="d-none" @change="onInputFile">
        </div>

        <div v-if="fileName" class="mt-2 gamelog-meta">
          <i class="bi bi-file-earmark me-1"></i>{{ fileName }} · {{ fmtSize(fileSize) }}
          <span v-if="readAt"> · 讀取於 {{ fmtClock(readAt) }}</span>
          <span v-if="watching" class="ms-2 gamelog-live"><i class="bi bi-circle-fill me-1"></i>監看中</span>
        </div>
        <div v-if="loading" class="progress mt-2" role="progressbar" :aria-valuenow="Math.round(progress * 100)"
          aria-valuemin="0" aria-valuemax="100" style="height: 6px">
          <div class="progress-bar" :style="{ width: `${Math.round(progress * 100)}%` }"></div>
        </div>
        <div v-if="error" class="alert alert-danger py-2 mt-2 mb-0">{{ error }}</div>
      </div>
    </div>

    <template v-if="fileName && !loading">
      <!-- 本次遊玩回顧 -->
      <div :class="[cardClass, 'mb-3']">
        <div class="card-body">
          <h3 class="h6 fw-bold mb-2"><i class="bi bi-journal-text me-1"></i>本次遊玩回顧</h3>
          <ul v-if="summary.length" class="mb-0 gamelog-summary">
            <li v-for="(s, i) in summary" :key="i">{{ s }}</li>
          </ul>
          <div v-else>這份 Game.log 裡沒有認得的事件。</div>
        </div>
      </div>

      <template v-if="events.length">
        <div class="sf-search sf-search--inline d-flex flex-wrap align-items-center gap-2 mb-2">
          <input v-model="query" type="search" class="form-control" style="max-width: 18rem"
            placeholder="搜尋事件" aria-label="搜尋事件">
          <select v-model="category" class="form-select w-auto" aria-label="分類">
            <option value="">全部分類</option>
            <option v-for="c in categoryOptions" :key="c.value" :value="c.value">{{ c.label }}</option>
          </select>
          <button v-if="query || category" type="button" class="btn btn-sm btn-warning" @click="query = ''; category = ''">清除篩選</button>
          <span class="ms-auto gamelog-meta">{{ rows.length }} 件</span>
        </div>

        <div :class="cardClass">
          <div class="card-body p-0">
            <div style="overflow-x: auto">
              <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
                  <tr><th class="ps-3" style="width: 9rem">時間</th><th class="pe-3">事件</th></tr>
                </thead>
                <tbody>
                  <tr v-if="!rows.length"><td colspan="2" class="ps-3 text-muted">沒有符合條件的事件。</td></tr>
                  <tr v-for="(r, i) in shownRows" :key="i">
                    <td class="ps-3 text-nowrap">
                      <div>{{ casualTime(r.ev.when) }}</div>
                      <div class="gamelog-meta">{{ casualDate(r.ev.when) }}</div>
                    </td>
                    <td class="pe-3">
                      <span class="me-1">{{ r.ev.icon }}</span>{{ r.ev.text }}
                      <span v-if="r.count > 1" class="sf-tree-chip ms-1">連續 {{ r.count }} 次</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div v-if="rows.length > shownCount" class="text-center mt-2">
          <button type="button" class="btn btn-sm btn-primary" @click="shownCount += PAGE">顯示更多</button>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, shallowRef } from 'vue'
import FieldHint from '@/components/FieldHint.vue'
import { CATEGORY_LABELS, GameLogParser, casualDate, casualTime, summaryLines, timeline } from '@/utils/gameLog'

defineProps({ cardClass: { type: String, default: 'card' } })

const DEFAULT_PATH = 'C:\\Program Files\\Roberts Space Industries\\StarCitizen\\LIVE\\Game.log'
const WATCH_MS = 2000
const PAGE = 200

let parser = null
const supportsPicker = typeof window !== 'undefined' && 'showOpenFilePicker' in window

const fileInput = ref(null)
const handle = shallowRef(null)      // FileSystemFileHandle（Chrome／Edge 才有）
const fileName = ref('')
const fileSize = ref(0)
const readAt = ref(null)
const events = shallowRef([])
const loading = ref(false)
const progress = ref(0)
const error = ref('')
const dragging = ref(false)
const watching = ref(false)
const query = ref('')
const category = ref('')
const shownCount = ref(PAGE)

let offset = 0                       // 已經讀到第幾個 byte（只會停在換行之後）
let watchTimer = null
let polling = false

function newParser() {
  try {
    parser = new GameLogParser()
    return true
  } catch (e) {
    error.value = `解析規則有問題：${e.message}`
    return false
  }
}

async function readWhole(file) {
  error.value = ''
  if (!newParser()) return
  loading.value = true
  progress.value = 0
  try {
    const text = await file.text()
    await parser.parseText(text, p => { progress.value = p })
    offset = file.size
    fileName.value = file.name
    fileSize.value = file.size
    readAt.value = new Date()
    events.value = [...parser.events]
    shownCount.value = PAGE
  } catch (e) {
    error.value = `讀取失敗：${e.message || e}`
  } finally {
    loading.value = false
  }
}

async function pickFile() {
  if (!supportsPicker) {
    fileInput.value?.click()
    return
  }
  try {
    const [h] = await window.showOpenFilePicker({
      types: [{ description: 'Game.log', accept: { 'text/plain': ['.log', '.txt'] } }],
    })
    stopWatch()
    handle.value = h
    await readWhole(await h.getFile())
  } catch (e) {
    if (e?.name !== 'AbortError') error.value = `無法開啟檔案：${e.message || e}`
  }
}

async function onInputFile(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  stopWatch()
  handle.value = null
  await readWhole(file)
}

async function onDrop(e) {
  dragging.value = false
  const item = e.dataTransfer?.items?.[0]
  stopWatch()
  // Chrome／Edge 拖放也拿得到檔案控制代碼，之後一樣可以重新讀取、持續監看
  if (item?.getAsFileSystemHandle) {
    try {
      const h = await item.getAsFileSystemHandle()
      if (h?.kind === 'file') {
        handle.value = h
        await readWhole(await h.getFile())
        return
      }
    } catch { /* 退回一般檔案 */ }
  }
  const file = e.dataTransfer?.files?.[0]
  if (file) {
    handle.value = null
    await readWhole(file)
  }
}

async function reload() {
  if (!handle.value) return
  try {
    await readWhole(await handle.value.getFile())
  } catch (e) {
    error.value = `重新讀取失敗：${e.message || e}`
  }
}

/** 只讀新增的部分：讀到最後一個換行為止，沒寫完的那一行留到下一次 */
async function pollOnce() {
  if (polling || !handle.value) return
  polling = true
  try {
    const file = await handle.value.getFile()
    if (file.size < offset) {         // 遊戲重開，Game.log 被重寫
      await readWhole(file)
      return
    }
    if (file.size === offset) return
    const bytes = new Uint8Array(await file.slice(offset).arrayBuffer())
    const lastNl = bytes.lastIndexOf(10)
    if (lastNl < 0) return
    const text = new TextDecoder('utf-8').decode(bytes.subarray(0, lastNl + 1))
    offset += lastNl + 1
    let added = false
    for (const line of text.split(/\r?\n/)) if (parser.parseLine(line)) added = true
    fileSize.value = file.size
    readAt.value = new Date()
    if (added) events.value = [...parser.events]
  } catch (e) {
    error.value = `監看中斷：${e.message || e}`
    stopWatch()
  } finally {
    polling = false
  }
}

function toggleWatch() {
  if (watching.value) {
    stopWatch()
    return
  }
  watching.value = true
  pollOnce()
  watchTimer = setInterval(pollOnce, WATCH_MS)
}

function stopWatch() {
  watching.value = false
  clearInterval(watchTimer)
  watchTimer = null
}

function clearAll() {
  stopWatch()
  handle.value = null
  parser = null
  offset = 0
  fileName.value = ''
  fileSize.value = 0
  readAt.value = null
  events.value = []
  error.value = ''
  query.value = ''
  category.value = ''
}

onBeforeUnmount(stopWatch)

const summary = computed(() => summaryLines(events.value))

const categoryOptions = computed(() => [...new Set(events.value.map(e => e.category))]
  .map(c => ({ value: c, label: CATEGORY_LABELS[c] || c })))

// 新的在上面；連續重複的同一句合併成「連續 N 次」
const rows = computed(() => {
  const q = query.value.trim().toLowerCase()
  const list = events.value.filter(e => (!category.value || e.category === category.value)
    && (!q || e.text.toLowerCase().includes(q)))
  return timeline(list).reverse()
})
const shownRows = computed(() => rows.value.slice(0, shownCount.value))

function fmtSize(n) {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`
  return `${Math.max(1, Math.round(n / 1024))} KB`
}

const fmtClock = d => d.toLocaleTimeString('zh-TW', { hour12: false })
</script>

<style scoped>
.gamelog-meta { color: var(--sf-text-muted); font-size: .95rem; }
.gamelog-live { color: rgb(var(--bs-success-rgb)); }
.gamelog-live .bi { font-size: .6rem; vertical-align: middle; }
.gamelog-summary li { margin-bottom: .25rem; }
.gamelog-drop { outline: 2px dashed var(--sf-accent); outline-offset: -6px; }
</style>
