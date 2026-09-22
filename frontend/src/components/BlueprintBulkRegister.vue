<!--
  藍圖主檔清單 ＋ 勾選批量登記。

  取代「只能用搜尋框一張一張登記」的流程：4.10 一次解鎖十幾張圖的時候，
  逐張搜尋、選取、送出要重複十幾次。這裡直接把主檔列出來（可依名稱／類型
  篩選、分頁），勾選後一次送出。

  已經登記過的會標成「已登記」且不能再勾 —— 後端也會再擋一次
  （見 Blueprint.bulk_create_for_player），因為畫面上的資料可能已經過時。
-->
<template>
  <div>
    <!-- ── 篩選 ────────────────────────────────────────────── -->
    <div :class="[cardClass, 'mb-3']">
      <div class="card-body">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-7">
            <label class="form-label small fw-semibold" :for="qId">名稱關鍵字</label>
            <input :id="qId" v-model="keyword" type="text" class="form-control form-control-sm"
              placeholder="中英文都可以，例如 Laser、醫療" @input="onKeywordInput">
          </div>
          <div class="col-12 col-md-5">
            <label class="form-label small fw-semibold" :for="typeId">類型</label>
            <select :id="typeId" v-model="outputType" class="form-select form-select-sm"
              @change="reload(0)">
              <option value="">全部</option>
              <option v-for="t in types" :key="t" :value="t">
                {{ blueprintTypeLabel(t) }}
              </option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <div v-if="message" :class="['alert', 'py-2', messageType]">{{ message }}</div>

    <!-- ── 清單 ────────────────────────────────────────────── -->
    <div :class="cardClass">
      <div class="card-body p-0">
        <div style="overflow-x: auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th style="width: 3rem" class="ps-3">
                  <input class="form-check-input" type="checkbox"
                    :checked="allSelectableChecked" :disabled="!selectableRows.length"
                    :indeterminate="someSelectableChecked && !allSelectableChecked"
                    aria-label="全選本頁" @change="togglePage($event.target.checked)">
                </th>
                <th>藍圖</th>
                <th>類型</th>
                <th class="text-end">材料數</th>
                <th class="text-end pe-3">製造時間</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="5" class="text-center py-4 hint">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中…
                </td>
              </tr>
              <!-- 讀取失敗要跟「真的沒有資料」分開講。同一句「沒有符合條件」
                   同時代表 500、連線斷掉、token 過期的話，使用者只會以為
                   自己篩錯條件，而不會想到重試。 -->
              <tr v-else-if="loadFailed">
                <td colspan="5" class="text-center py-4">
                  <span class="text-warning">
                    <i class="bi bi-exclamation-triangle me-1"></i>讀取藍圖清單失敗。
                  </span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="5" class="text-center py-4 hint">
                  {{ keyword || outputType
                     ? '沒有符合條件的藍圖，換個關鍵字或類型看看。'
                     : '藍圖主檔還是空的 —— 請先在後台「系統設定 → 遊戲資料同步」跑一次同步。' }}
                </td>
              </tr>
              <tr v-for="row in rows" :key="row._id"
                :class="{ 'row-registered': registered.has(row._id) }">
                <td class="ps-3">
                  <input class="form-check-input" type="checkbox"
                    :checked="selected.has(row._id)"
                    :disabled="registered.has(row._id)"
                    :aria-label="`勾選 ${row.name_zh || row.name}`"
                    @change="toggleOne(row._id, $event.target.checked)">
                </td>
                <td>
                  <span class="fw-semibold">{{ row.name_zh || row.name }}</span>
                  <span v-if="row.name_zh" class="small hint ms-1">{{ row.name }}</span>
                  <span v-if="registered.has(row._id)"
                    class="badge bg-secondary ms-1">已登記</span>
                </td>
                <td class="small">{{ row.output_type ? blueprintTypeLabel(row.output_type) : (row.output_type_label || '—') }}</td>
                <td class="text-end small">
                  {{ row.ingredient_count ?? '—' }}
                </td>
                <td class="text-end pe-3 small hint">{{ row.craft_time_label || '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── 分頁 ────────────────────────────────────────────── -->
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-2">
      <div class="small hint">
        共 {{ total }} 張<span v-if="total"> · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 張</span>
      </div>
      <div class="btn-group btn-group-sm">
        <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading"
          @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-outline-secondary"
          :disabled="offset + limit >= total || loading"
          @click="reload(offset + limit)">下一頁</button>
      </div>
    </div>

    <!-- ── 送出列（有勾選才出現）────────────────────────────── -->
    <div v-if="selected.size" :class="[cardClass, 'mt-3', 'sticky-submit']">
      <div class="card-body">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <span class="fw-semibold">已選 {{ selected.size }} 張</span>
          <button class="btn btn-sm btn-link p-0" @click="clearSelection">清除勾選</button>
          <span class="flex-grow-1"></span>
          <input v-model="acquisitionMethod" type="text" class="form-control form-control-sm"
            style="max-width: 10rem" placeholder="取得方式（可留空）"
            aria-label="取得方式（套用到這批全部）">
          <button class="btn btn-scifi btn-sm" :disabled="submitting" @click="submit">
            <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
            登記這 {{ selected.size }} 張
          </button>
        </div>
        <div v-if="selected.size > maxBulk" class="small text-danger mt-1">
          一次最多 {{ maxBulk }} 張，請先取消一些。
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'

const props = defineProps({
  /** 帶身分的 fetch（玩家頁傳 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  cardClass: { type: String, default: 'card shadow-sm border-0' },
})
const emit = defineEmits(['registered'])

// 跟後端的 MAX_BULK_BLUEPRINTS 一致
const maxBulk = 200

const uid = Math.random().toString(36).slice(2, 8)
const qId = `bpbulk-q-${uid}`
const typeId = `bpbulk-type-${uid}`

const rows = ref([])
const total = ref(0)
const limit = ref(50)
const offset = ref(0)
const loading = ref(false)
/** 上一次載入是不是失敗（跟「查詢結果為空」要分開顯示） */
const loadFailed = ref(false)
const types = ref([])

const keyword = ref('')
const outputType = ref('')

/** 已登記的主檔 uuid（畫面標記＋禁止再勾，後端也會再擋一次） */
const registered = reactive(new Set())
/** 勾選中的 uuid。跨頁保留 —— 翻頁去找其他類型再回來，勾過的不該消失 */
const selected = reactive(new Set())

const submitting = ref(false)
/** 這批共用的「取得方式」（例如「任務獎勵」），會套用到勾選的每一張 */
const acquisitionMethod = ref('')
const message = ref('')
const messageType = ref('alert-success')

/** 本頁可勾的（排除已登記） */
const selectableRows = computed(() => rows.value.filter(r => !registered.has(r._id)))
const allSelectableChecked = computed(() =>
  selectableRows.value.length > 0 && selectableRows.value.every(r => selected.has(r._id)))
const someSelectableChecked = computed(() =>
  selectableRows.value.some(r => selected.has(r._id)))

// ── 載入 ──────────────────────────────────────────────────────
//
// seq 是過期回應防護：翻頁／改篩選很容易連續送出，慢回應回來時如果已經
// 不是最新一次就整包丟掉（專案別處踩過「舊結果蓋掉新結果」的坑）。
let seq = 0
let keywordTimer = null

async function reload(nextOffset = 0) {
  offset.value = Math.max(0, nextOffset)
  loading.value = true
  const mine = ++seq

  const params = new URLSearchParams({
    limit: String(limit.value),
    offset: String(offset.value),
  })
  if (keyword.value.trim()) params.set('q', keyword.value.trim())
  if (outputType.value) params.set('output_type', outputType.value)

  const res = await props.fetcher(`/blueprint/master?${params.toString()}`)
  if (mine !== seq) return
  const data = res ? await res.json().catch(() => null) : null
  if (mine !== seq) return

  if (data?.success) {
    rows.value = data.data || []
    total.value = data.total ?? rows.value.length
    loadFailed.value = false
  } else {
    rows.value = []
    total.value = 0
    loadFailed.value = true
    flash(data?.message || '讀取藍圖清單失敗，請稍後再試', 'alert-warning')
  }
  loading.value = false
}

function onKeywordInput() {
  clearTimeout(keywordTimer)
  keywordTimer = setTimeout(() => reload(0), 300)
}

/** 我已經登記過哪些（用來標記清單） */
async function loadRegistered() {
  const res = await props.fetcher('/player/blueprints')
  const data = res ? await res.json().catch(() => null) : null
  if (!data?.success) {
    // 靜默失敗的後果是「已登記」標記全部消失 → 使用者會重複勾一次已經有的
    flash('讀不到你已登記的藍圖，「已登記」標記可能不完整，請重新整理。',
          'alert-warning')
    return
  }
  registered.clear()
  for (const row of data.data || []) {
    if (row.blueprint_uuid) registered.add(row.blueprint_uuid)
  }
}

async function loadTypes() {
  const res = await props.fetcher('/blueprint/master/types')
  const data = res ? await res.json().catch(() => null) : null
  if (data?.success) types.value = data.data || []
}

// ── 勾選 ──────────────────────────────────────────────────────

function toggleOne(uuid, checked) {
  if (checked) selected.add(uuid)
  else selected.delete(uuid)
}

function togglePage(checked) {
  for (const row of selectableRows.value) {
    if (checked) selected.add(row._id)
    else selected.delete(row._id)
  }
}

function clearSelection() {
  selected.clear()
}

function flash(text, type = 'alert-success') {
  message.value = text
  messageType.value = type
  setTimeout(() => { message.value = '' }, 6000)
}

// ── 送出 ──────────────────────────────────────────────────────

async function submit() {
  if (!selected.size || submitting.value) return
  if (selected.size > maxBulk) {
    flash(`一次最多 ${maxBulk} 張，目前勾了 ${selected.size} 張。`, 'alert-warning')
    return
  }
  submitting.value = true
  try {
    const res = await props.fetcher('/player/blueprints/bulk', {
      method: 'POST',
      body: JSON.stringify({
        blueprint_uuids: [...selected],
        acquisition_method: acquisitionMethod.value.trim(),
      }),
    })
    if (!res) { flash('網路錯誤，請稍後再試', 'alert-warning'); return }
    const data = await res.json().catch(() => null)
    if (!res.ok || !data?.success) {
      flash(data?.message || '登記失敗，請稍後再試', 'alert-warning')
      return
    }

    // 誠實回報：跳過與查不到的也要講，不然使用者會以為全部都登記進去了
    const parts = [`新增 ${data.added} 張`]
    if (data.skipped) parts.push(`跳過 ${data.skipped} 張（已登記過）`)
    if (data.not_found) parts.push(`${data.not_found} 張在主檔查不到`)
    flash(parts.join('，'), data.added ? 'alert-success' : 'alert-warning')

    clearSelection()
    await loadRegistered()
    emit('registered', data)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadTypes()
  loadRegistered()
  reload(0)
})
onBeforeUnmount(() => clearTimeout(keywordTimer))

// 讓外面（例如切回這個分頁時）可以要求重新整理已登記狀態
defineExpose({ refresh: async () => { await loadRegistered(); await reload(offset.value) } })
</script>

<style scoped>
/* 已登記的整列淡化，一眼看得出「這些不用再勾」 */
.row-registered > td {
  opacity: .55;
}

.hint {
  opacity: .72;
}

/* 送出列固定在視窗底部：清單可能很長，勾到一半不用滑回去按送出 */
.sticky-submit {
  position: sticky;
  bottom: .5rem;
  z-index: 10;
}
</style>
