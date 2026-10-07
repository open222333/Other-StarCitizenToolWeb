<!--
  玩家頁「艦隊 › JSON 匯入」：匯入 HangarXPLOR（RSI 機庫頁的瀏覽器擴充功能）
  匯出的 shiplist.json。

  流程：選檔／拖放 → 瀏覽器讀成 JSON → POST /player/fleet/import 拿預覽
  （每款船匯入幾艘、現有、匯入後、自訂名稱、對不到的）→ 按「確認匯入」再送一次 apply=true。
  對應規則與重複匯入的處理見 src/models/fleet_import.py。
-->
<template>
  <div :class="[cardClass, { 'fleet-import-drop': dragging }]"
    @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
    <div class="card-body">
      <div class="d-flex flex-wrap align-items-center gap-2">
        <button type="button" class="btn btn-primary" :disabled="busy" @click="fileInput?.click()">
          <i class="bi bi-filetype-json me-1"></i>選擇 JSON 檔
        </button>
        <FieldHint text="在 RSI 網站的機庫頁用 HangarXPLOR 擴充功能「Download JSON」下載 shiplist.json；也可以把檔案直接拖進這個區塊。" />
        <span v-if="fileName" class="fleet-import-meta"><i class="bi bi-file-earmark me-1"></i>{{ fileName }}</span>
        <!-- 匯出 JSON 用的擴充功能（Chrome 線上應用程式商店）；玩家頁開外部網址一律用 btn-primary 按鈕 -->
        <a class="btn btn-primary ms-auto" :href="HANGAR_XPLOR_URL" target="_blank" rel="noopener noreferrer">
          <i class="bi bi-browser-chrome me-1"></i>安裝 HangarXPLOR<i class="bi bi-box-arrow-up-right ms-1"></i>
        </a>
        <input ref="fileInput" type="file" accept=".json,application/json" class="d-none" @change="onInputFile">
      </div>

      <div v-if="error" class="alert alert-danger py-2 mt-2 mb-0">{{ error }}</div>
      <div v-if="doneText" class="alert alert-success py-2 mt-2 mb-0">{{ doneText }}</div>
      <div v-if="busy" class="fleet-import-meta mt-2">處理中…</div>

      <template v-if="preview">
        <div class="mt-3 mb-2">
          船單共 {{ preview.total }} 艘，對應到 {{ preview.rows.length }} 款<template v-if="preview.unmatched.length">，{{ unmatchedCount }} 艘對不到</template>
        </div>
        <div v-if="preview.rows.length" class="card scifi-card mb-2">
          <div class="card-body p-0">
            <div style="overflow-x: auto">
              <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
                  <tr>
                    <th class="ps-3">載具</th>
                    <th class="text-end">船單</th><th class="text-end">現有</th><th class="text-end">匯入後</th>
                    <th class="pe-3">自訂名稱</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="r in preview.rows" :key="r.vehicle_uuid">
                    <td class="ps-3">
                      <span class="fw-semibold">{{ r.name_zh || r.name }}</span>
                      <span v-if="r.name_zh" class="small text-muted ms-1">{{ r.name }}</span>
                    </td>
                    <td class="text-end">{{ r.count }}</td>
                    <td class="text-end">{{ r.existing_quantity || '—' }}</td>
                    <td class="text-end">
                      <span :class="{ 'fleet-import-changed': r.new_quantity !== r.existing_quantity }">{{ r.new_quantity }}</span>
                    </td>
                    <td class="pe-3">
                      <span v-for="n in r.nicknames" :key="n" class="sf-tree-chip me-1">{{ n }}</span>
                      <span v-if="!r.nicknames.length" class="text-muted">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
        <div v-if="preview.unmatched.length" class="mb-2">
          <span class="fleet-import-meta me-1">對不到遊戲資料的（不會匯入）：</span>
          <span v-for="u in preview.unmatched" :key="u.ship_code || u.name" class="sf-tree-chip me-1">
            {{ u.name }}<template v-if="u.count > 1"> ×{{ u.count }}</template>
          </span>
        </div>
        <div class="d-flex flex-wrap gap-2">
          <button type="button" class="btn btn-success" :disabled="busy || !preview.rows.length" @click="confirm">
            <i class="bi bi-check-lg me-1"></i>確認匯入
          </button>
          <button type="button" class="btn btn-secondary" :disabled="busy" @click="reset">取消</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, shallowRef } from 'vue'
import FieldHint from '@/components/FieldHint.vue'

// Star Citizen Hangar XPLORer（Chrome 擴充功能），在 RSI 機庫頁「Download JSON」匯出 shiplist.json
const HANGAR_XPLOR_URL = 'https://chromewebstore.google.com/detail/star-citizen-hangar-xplor/bhkgemjdepodofcnmekdobmmbifemhkc?hl=zh-TW'

const props = defineProps({
  fetcher: { type: Function, required: true },
  cardClass: { type: String, default: 'card' },
})
const emit = defineEmits(['imported'])

const fileInput = ref(null)
const fileName = ref('')
const ships = shallowRef(null)
const preview = ref(null)
const busy = ref(false)
const error = ref('')
const doneText = ref('')
const dragging = ref(false)

const unmatchedCount = computed(() => (preview.value?.unmatched || []).reduce((n, u) => n + u.count, 0))

async function post(apply) {
  const res = await props.fetcher('/player/fleet/import', {
    method: 'POST', body: JSON.stringify({ ships: ships.value, apply }),
  })
  const body = res ? await res.json().catch(() => null) : null
  if (!res?.ok || !body?.success) throw new Error(body?.message || '匯入失敗，請稍後再試')
  return body.data
}

async function load(file) {
  reset()
  fileName.value = file.name
  busy.value = true
  try {
    let data
    try {
      data = JSON.parse(await file.text())
    } catch {
      throw new Error('這個檔案不是 JSON')
    }
    ships.value = data
    preview.value = await post(false)
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function onInputFile(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (file) load(file)
}

function onDrop(e) {
  dragging.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) load(file)
}

async function confirm() {
  busy.value = true
  error.value = ''
  try {
    const r = await post(true)
    const parts = [`新增 ${r.added} 款`, `更新 ${r.updated} 款`]
    if (r.unchanged) parts.push(`${r.unchanged} 款沒有變動`)
    if (r.unmatched) parts.push(`${r.unmatched} 款對不到`)
    const text = `匯入完成：${parts.join('、')}。`
    reset()
    doneText.value = text
    emit('imported')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

function reset() {
  fileName.value = ''
  ships.value = null
  preview.value = null
  error.value = ''
  doneText.value = ''
}
</script>

<style scoped>
.fleet-import-meta { color: var(--sf-text-muted); font-size: .95rem; }
.fleet-import-changed { color: rgb(var(--bs-success-rgb)); font-weight: 700; }
.fleet-import-unmatched { font-size: .95rem; }
.fleet-import-drop { outline: 2px dashed var(--sf-accent); outline-offset: -6px; }
</style>
