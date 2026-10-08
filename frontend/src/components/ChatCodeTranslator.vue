<!--
  玩家頁「中文轉碼」：遊戲聊天用的 中文 ↔ @xxx 代碼互轉。

  移植自 Other-Game/StarCitizen/tctp_translator（轉換邏輯在 utils/chatCode.js）。
  字典由後端 GET /player/chat-code/dictionary 提供（伺服器從社群 chsc-tw 下載並快取，
  見 src/models/chat_code.py），進到這個分頁才載入。
  輸入有中文 → 轉成「[zh] @代碼」；輸入 @代碼 → 轉回中文，邊打邊轉（方向也可以手動指定）。

  下半部「遊戲文字代碼」：遊戲的 localization key（例如 vehicle_NameAEGS_Avenger_Stalker）
  ⇄ 中文，查全站翻譯資料庫 sc_translations（GET /player/game-text）。
-->
<template>
  <div>
    <!-- 工具列：兩區的開關＋字典重新整理放最上面（比照倉庫／藍圖／艦隊） -->
    <div class="sf-toolbar">
      <button type="button" class="btn btn-sm" :class="chatOpen ? 'btn-secondary' : 'btn-info'"
        :aria-expanded="chatOpen ? 'true' : 'false'" @click="chatOpen = !chatOpen">
        <i class="bi me-1" :class="chatOpen ? 'bi-x-lg' : 'bi-chat-dots'"></i>{{ chatOpen ? '收起聊天代碼' : '聊天代碼' }}
      </button>
      <button type="button" class="btn btn-sm" :class="textOpen ? 'btn-secondary' : 'btn-info'"
        :aria-expanded="textOpen ? 'true' : 'false'" @click="textOpen = !textOpen">
        <i class="bi me-1" :class="textOpen ? 'bi-x-lg' : 'bi-code-square'"></i>{{ textOpen ? '收起遊戲文字代碼' : '遊戲文字代碼' }}
      </button>
      <button type="button" class="btn btn-sm btn-primary" :disabled="loading" @click="load">重新整理字典</button>
    </div>

    <div v-show="chatOpen" class="sf-drawer">
    <h3 class="sf-drawer__title"><i class="bi bi-chat-dots me-1"></i>聊天代碼</h3>
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body">
        <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
          <label class="form-label fw-semibold mb-0" for="chat-code-input">輸入</label>
          <div class="btn-group btn-group-sm ms-auto chat-code-modes" role="group" aria-label="轉換方向">
            <button v-for="m in MODES" :key="m.key" type="button" class="btn btn-subtab"
              :class="{ active: mode === m.key }" :aria-pressed="mode === m.key ? 'true' : 'false'"
              @click="mode = m.key">{{ m.label }}</button>
          </div>
        </div>
        <textarea id="chat-code-input" v-model="input" class="form-control" rows="3"
          :placeholder="mode === 'chinese' ? '中文' : mode === 'code' ? '[zh] @代碼' : '中文或 @代碼'" :disabled="!dict"></textarea>
        <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
          <button type="button" class="btn btn-sm btn-warning" :disabled="!input" @click="input = ''">清除</button>
          <span class="ms-auto chat-code-meta">
            <template v-if="dict">字典 {{ dict.entries.toLocaleString('en-US') }} 字<template v-if="fetchedAt"> · 更新於 {{ fetchedAt }}</template></template>
            <template v-else-if="loading">字典載入中…</template>
          </span>
        </div>
        <div v-if="stale" class="alert alert-warning py-2 mt-2 mb-0">字典暫時無法更新，目前用的是舊版。</div>
        <div v-if="error" class="alert alert-danger py-2 mt-2 mb-0">{{ error }}</div>
      </div>
    </div>

    <div v-if="result.type === 'chinese' || result.type === 'code'" :class="cardClass">
      <div class="card-body">
        <div class="d-flex align-items-center gap-2 mb-2">
          <span class="sf-tree-chip">{{ result.type === 'chinese' ? '中文 → 代碼' : '代碼 → 中文' }}</span>
          <button type="button" class="btn btn-sm btn-primary ms-auto" @click="copy">
            <i class="bi me-1" :class="copied ? 'bi-check-lg' : 'bi-clipboard'"></i>{{ copied ? '已複製' : '複製' }}
          </button>
        </div>
        <pre class="chat-code-output mb-0">{{ result.output }}</pre>
        <div v-if="result.unknown.length" class="mt-2">
          <span class="chat-code-meta me-1">字典裡沒有：</span>
          <span v-for="u in result.unknown" :key="u" class="sf-tree-chip me-1">{{ u }}</span>
        </div>
      </div>
    </div>
    <div v-else-if="result.type === 'unknown'" class="chat-code-meta">看不出是中文還是 @代碼。</div>

    <div class="chat-code-meta mt-2 mb-2">字典來源：社群專案 taksito/chsc-tw</div>
    </div>

    <!-- ── 遊戲文字代碼（localization key）⇄ 中文：查全站翻譯資料庫（GET /player/game-text）── -->
    <div v-show="textOpen" class="sf-drawer">
    <h3 class="sf-drawer__title"><i class="bi bi-code-square me-1"></i>遊戲文字代碼</h3>
    <div class="sf-search sf-search--inline d-flex flex-wrap align-items-center gap-2 mb-2">
      <input v-model="textQuery" type="search" class="form-control" style="max-width: 24rem"
        placeholder="代碼、中文或英文" aria-label="遊戲文字代碼、中文或英文">
      <select v-model="textMode" class="form-select w-auto" aria-label="查詢方式">
        <option v-for="m in TEXT_MODES" :key="m.key" :value="m.key">{{ m.label }}</option>
      </select>
      <span v-if="textUsedMode && textMode === 'auto'" class="sf-tree-chip">{{ TEXT_MODE_LABELS[textUsedMode] }}</span>
      <span v-if="textSearching" class="chat-code-meta">查詢中…</span>
    </div>
    <div v-if="textError" class="alert alert-danger py-2">{{ textError }}</div>
    <div v-else-if="textQuery.trim().length >= 2 && !textSearching && textRows" :class="cardClass">
      <div class="card-body p-0">
        <div style="overflow-x: auto">
          <table class="table table-hover align-middle mb-0 game-text-table">
            <thead class="table-light">
              <tr><th class="ps-3">代碼</th><th>中文</th><th>英文</th><th class="pe-3"></th></tr>
            </thead>
            <tbody>
              <tr v-if="!textRows.length"><td colspan="4" class="ps-3 text-muted">找不到符合的遊戲文字。</td></tr>
              <tr v-for="r in textRows" :key="r.key">
                <td class="ps-3 font-monospace game-text-key">{{ r.key }}</td>
                <td class="fw-semibold">{{ r.zh || '—' }}</td>
                <td>{{ r.en || '—' }}</td>
                <td class="pe-3 text-end text-nowrap">
                  <button type="button" class="btn btn-sm btn-primary" @click="copyText(r.key, 'k' + r.key)">
                    <i class="bi me-1" :class="copiedKey === 'k' + r.key ? 'bi-check-lg' : 'bi-clipboard'"></i>代碼
                  </button>
                  <button v-if="r.zh" type="button" class="btn btn-sm btn-primary ms-1" @click="copyText(r.zh, 'z' + r.key)">
                    <i class="bi me-1" :class="copiedKey === 'z' + r.key ? 'bi-check-lg' : 'bi-clipboard'"></i>中文
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <div v-if="textRows && textRows.length >= 50" class="chat-code-meta mt-1">只列前 50 筆，請再輸入完整一點。</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, shallowRef, watch } from 'vue'
import { autoTranslate, parseDictionary } from '@/utils/chatCode'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card' },
})

// 兩區的開關（聊天代碼預設打開）
const chatOpen = ref(true)
const textOpen = ref(false)

const dict = shallowRef(null)
const loading = ref(false)
const error = ref('')
const stale = ref(false)
const fetchedAt = ref('')
const input = ref('')
const copied = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await props.fetcher('/player/chat-code/dictionary')
    const body = res ? await res.json().catch(() => null) : null
    if (!res?.ok || !body?.success) {
      error.value = body?.message || '字典載入失敗，請稍後再試'
      return
    }
    dict.value = parseDictionary(body.data.text)
    stale.value = !!body.data.stale
    fetchedAt.value = body.data.fetched_at
      ? new Date(body.data.fetched_at).toLocaleString('zh-TW', { hour12: false }) : ''
  } finally {
    loading.value = false
  }
}

// 進到這個分頁才載入字典（大約一百多 KB），載過就不重複載
watch(() => props.active, (v) => { if (v && !dict.value && !loading.value) load() }, { immediate: true })

// 轉換方向：自動判斷，或手動指定（例如想把含中文的句子裡的 @代碼 也當代碼處理）
const MODES = [
  { key: 'auto', label: '自動' },
  { key: 'chinese', label: '中文 → 代碼' },
  { key: 'code', label: '代碼 → 中文' },
]
const mode = ref('auto')

const result = computed(() => (dict.value
  ? autoTranslate(input.value, dict.value, mode.value)
  : { type: 'empty', output: '', unknown: [] }))

// ── 遊戲文字代碼 ⇄ 中文（後端查 sc_translations，見 src/models/translation.py 的 search）──
const TEXT_MODES = [
  { key: 'auto', label: '自動判斷' },
  { key: 'key', label: '代碼 → 中文' },
  { key: 'zh', label: '中文 → 代碼' },
  { key: 'en', label: '英文' },
]
const TEXT_MODE_LABELS = { key: '代碼 → 中文', zh: '中文 → 代碼', en: '英文' }
const textQuery = ref('')
const textMode = ref('auto')
const textRows = ref(null)
const textUsedMode = ref('')
const textSearching = ref(false)
const textError = ref('')
const copiedKey = ref('')
let textTimer = null
let textSeq = 0

async function searchText() {
  const q = textQuery.value.trim()
  if (q.length < 2) {
    textRows.value = null
    textUsedMode.value = ''
    return
  }
  const seq = ++textSeq
  textSearching.value = true
  textError.value = ''
  try {
    const params = new URLSearchParams({ q, mode: textMode.value })
    const res = await props.fetcher(`/player/game-text?${params.toString()}`)
    if (seq !== textSeq) return   // 已經有更新的查詢
    const body = res ? await res.json().catch(() => null) : null
    if (!res?.ok || !body?.success) {
      textError.value = body?.message || '查詢失敗，請稍後再試'
      textRows.value = null
      return
    }
    textRows.value = body.data || []
    textUsedMode.value = body.mode || ''
  } finally {
    if (seq === textSeq) textSearching.value = false
  }
}

// 邊打邊查（停 350ms 才送出）
watch([textQuery, textMode], () => {
  clearTimeout(textTimer)
  textTimer = setTimeout(searchText, 350)
})

async function copyText(text, id) {
  try {
    await navigator.clipboard.writeText(text)
    copiedKey.value = id
    setTimeout(() => { if (copiedKey.value === id) copiedKey.value = '' }, 1500)
  } catch {
    textError.value = '無法複製，請手動選取文字'
  }
}

async function copy() {
  try {
    await navigator.clipboard.writeText(result.value.output)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch {
    error.value = '無法複製，請手動選取文字'
  }
}
</script>

<style scoped>
.chat-code-meta { color: var(--sf-text-muted); font-size: .95rem; }
.chat-code-output {
  white-space: pre-wrap; word-break: break-all;
  font-size: 1.05rem; color: var(--sf-text-strong);
  background: var(--sf-panel-2); border: 1px solid var(--sf-border); border-radius: 6px;
  padding: .6rem .8rem;
}
.chat-code-unknown { font-size: .95rem; }
.game-text-key { font-size: .95rem; color: var(--sf-text-muted); min-width: 14rem; max-width: 22rem; word-break: break-all; }
/* 手機上表格維持一般欄寬、改成左右滑，不要把每格擠成一個字一行 */
.game-text-table { min-width: 40rem; }
.chat-code-modes .btn { white-space: nowrap; padding: .35rem .75rem; }
</style>
