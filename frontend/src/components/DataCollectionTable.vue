<!--
  後台「資料庫檢視」的單一資料表列表（唯讀，GET /data/collections/<name>）。
  欄位是後端取樣出來的全部欄位（物件展開成 a.b）；陣列只顯示縮短的 JSON，點一列看完整內容（含 raw）。
  搜尋卡：「欄位」選要比對的欄位（空＝全部欄位）＋「關鍵字」（部分比對，數字也比對相等）；
  「條件」可以加好幾個（任何欄位，含 raw.xxx；包含／等於／大小／有沒有值），全部都要符合。
  後台「資料庫檢視」頁、礦物資料庫的「精煉站」分頁共用。
-->
<template>
  <div class="sf-scroll-anchor">
    <AdminSearchCard :active="!!(field || query.trim() || activeConditions.length)" @clear="clearFilters">
      <AdminSearchField label="欄位" :for-id="`${uid}-field`" col="col-6 col-md-4 col-xl-3">
        <select :id="`${uid}-field`" v-model="field" class="form-select form-select-sm" @change="reload(0)">
          <option value="">全部欄位</option>
          <option v-for="c in searchFields" :key="c" :value="c">{{ c }}</option>
        </select>
      </AdminSearchField>
      <AdminSearchField label="關鍵字" :for-id="`${uid}-q`" col="col-6 col-md-8 col-xl-5">
        <input :id="`${uid}-q`" v-model="query" type="search" class="form-control form-control-sm" placeholder="輸入關鍵字">
      </AdminSearchField>
      <div class="col-12">
        <div class="d-flex align-items-center gap-2 mb-1">
          <span class="small fw-semibold">條件</span>
          <button type="button" class="btn btn-sm btn-success" :disabled="conditions.length >= MAX_CONDITIONS"
            @click="conditions.push(newCondition())"><i class="bi bi-plus-lg me-1"></i>加條件</button>
        </div>
        <datalist :id="`${uid}-fields`">
          <option v-for="c in searchFields" :key="c" :value="c" />
        </datalist>
        <div v-for="(cond, i) in conditions" :key="cond.key" class="row g-1 align-items-center mb-1">
          <div class="col-12 col-md-4">
            <input v-model.trim="cond.field" type="text" class="form-control form-control-sm font-monospace"
              :list="`${uid}-fields`" placeholder="欄位" :aria-label="`條件 ${i + 1} 欄位`">
          </div>
          <div class="col-5 col-md-3">
            <select v-model="cond.op" class="form-select form-select-sm" :aria-label="`條件 ${i + 1} 比對`">
              <option v-for="o in OPS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
          <div class="col col-md-4">
            <input v-if="!NO_VALUE.has(cond.op)" v-model="cond.value" type="text" class="form-control form-control-sm"
              placeholder="值" :aria-label="`條件 ${i + 1} 值`">
          </div>
          <div class="col-auto">
            <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除條件 ${i + 1}`"
              @click="conditions.splice(i, 1)"><i class="bi bi-trash"></i></button>
          </div>
        </div>
      </div>
      <template #summary>共 {{ total }} 筆<span v-if="total"> · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</span> · {{ columns.length }} 欄</template>
    </AdminSearchCard>

    <div v-if="error && !loading" class="alert alert-danger py-2 d-flex flex-wrap align-items-center gap-2" role="alert">
      <span>{{ error }}</span>
      <button type="button" class="btn btn-sm btn-primary" @click="reload(offset)"><i class="bi bi-arrow-clockwise me-1"></i>重試</button>
    </div>

    <div v-else class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover table-sm align-middle mb-0 small dct">
            <thead class="table-light">
              <tr>
                <SortTh v-for="(c, i) in columns" :key="c" :sort="sort" :field="c" :class="{ 'ps-3': i === 0 }">{{ c }}</SortTh>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading && !rows.length">
                <td :colspan="columns.length || 1" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td :colspan="columns.length || 1" class="text-center py-4 text-muted">沒有資料</td>
              </tr>
              <template v-for="r in rows" v-else :key="String(r._id)">
                <tr class="dct-row" role="button" tabindex="0" :aria-expanded="openId === String(r._id) ? 'true' : 'false'"
                  @click="toggle(r)" @keydown.enter="toggle(r)">
                  <td v-for="(c, i) in columns" :key="c" :class="{ 'ps-3 font-monospace': i === 0 }">
                    <span v-if="r[c] === undefined || r[c] === null || r[c] === ''" class="text-muted">—</span>
                    <span v-else-if="typeof r[c] === 'boolean'" class="badge" :class="r[c] ? 'text-bg-success' : 'text-bg-secondary'">{{ r[c] }}</span>
                    <span v-else class="dct-cell">{{ r[c] }}</span>
                  </td>
                </tr>
                <tr v-if="openId === String(r._id)">
                  <td :colspan="columns.length" class="dct-detail">
                    <div v-if="detailLoading" class="text-muted">載入中...</div>
                    <pre v-else class="mb-0">{{ detailText }}</pre>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="d-flex justify-content-end mt-2">
      <div class="btn-group btn-group-sm">
        <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading" @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-outline-secondary" :disabled="offset + limit >= total || loading" @click="reload(offset + limit)">下一頁</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { dataApi } from '@/api'
import AdminSearchCard from '@/components/AdminSearchCard.vue'
import AdminSearchField from '@/components/AdminSearchField.vue'
import SortTh from '@/components/SortTh.vue'
import { useTableSort } from '@/composables/useTableSort'

const props = defineProps({
  /** 資料表名稱（要在後端 src/models/data_browser.py 的 CATALOG 裡） */
  collection: { type: String, required: true },
})


const uid = `dct-${Math.random().toString(36).slice(2, 8)}`
const limit = 50
const columns = ref([])
// 搜尋卡「欄位」的選項：列表欄位＋後端另外開放的巢狀欄位（例如翻譯的 text.en、text.zh-TW）
const searchFields = ref([])
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const error = ref('')
const field = ref('')
const query = ref('')
const openId = ref('')
const detailText = ref('')
const detailLoading = ref(false)

const sort = useTableSort(null, { onChange: () => reload(0) })

// ── 條件（後端 src/models/data_browser.py 的 _filters_query）──
const MAX_CONDITIONS = 10
const OPS = [
  { value: 'contains', label: '包含' }, { value: 'not_contains', label: '不包含' },
  { value: 'eq', label: '等於' }, { value: 'ne', label: '不等於' },
  { value: 'gt', label: '大於' }, { value: 'gte', label: '大於等於' },
  { value: 'lt', label: '小於' }, { value: 'lte', label: '小於等於' },
  { value: 'not_empty', label: '有值' }, { value: 'empty', label: '沒有值' },
]
const NO_VALUE = new Set(['empty', 'not_empty'])
let condSeq = 0
const newCondition = () => ({ key: ++condSeq, field: '', op: 'contains', value: '' })
const conditions = reactive([])
const activeConditions = computed(() => conditions
  .filter(c => c.field && (NO_VALUE.has(c.op) || String(c.value).trim() !== ''))
  .map(c => ({ field: c.field, op: c.op, value: NO_VALUE.has(c.op) ? '' : String(c.value).trim() })))
const filtersParam = computed(() => (activeConditions.value.length ? JSON.stringify(activeConditions.value) : ''))

let seq = 0
let lastQuery = ''
async function reload(newOffset = 0) {
  const my = ++seq
  offset.value = newOffset
  loading.value = true
  error.value = ''
  openId.value = ''
  lastQuery = query.value.trim()
  const res = await dataApi.list(props.collection, {
    field: field.value, q: lastQuery, filters: filtersParam.value, ...sort.params.value, limit, offset: newOffset,
  })
  const body = res ? await res.json().catch(() => null) : null
  if (my !== seq) return
  if (res?.ok && body?.success) {
    columns.value = body.data.columns || []
    searchFields.value = body.data.search_fields || columns.value
    rows.value = body.data.rows || []
    total.value = body.data.total || 0
  } else {
    rows.value = []
    total.value = 0
    error.value = body?.message || '讀取資料失敗。'
  }
  loading.value = false
}

function clearFilters() {
  field.value = ''
  query.value = ''
  conditions.splice(0)
  reload(0)
}

async function toggle(r) {
  const id = String(r._id)
  if (openId.value === id) { openId.value = ''; return }
  openId.value = id
  detailLoading.value = true
  const res = await dataApi.doc(props.collection, id)
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (openId.value !== id) return
  detailText.value = body?.success ? JSON.stringify(body.data, null, 2) : '讀取失敗。'
  detailLoading.value = false
}

// 關鍵字打字停 300ms 就查
let timer = null
watch(query, () => {
  clearTimeout(timer)
  if (query.value.trim() === lastQuery) return
  timer = setTimeout(() => reload(0), 300)
})
onBeforeUnmount(() => { clearTimeout(timer); clearTimeout(condTimer) })

// 條件改了（停 400ms）就查；只有真的影響查詢的變動才重查
let condTimer = null
let lastFilters = ''
watch(filtersParam, (v) => {
  clearTimeout(condTimer)
  if (v === lastFilters) return
  condTimer = setTimeout(() => { lastFilters = v; reload(0) }, 400)
})

watch(() => props.collection, () => {
  field.value = ''
  query.value = ''
  conditions.splice(0)
  lastFilters = ''
  lastQuery = ''
  sort.sortKey.value = ''
  reload(0)
}, { immediate: true })
</script>

<style scoped>
.dct-row { cursor: pointer; }
.dct-cell { display: inline-block; max-width: 22rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; vertical-align: bottom; }
.dct-detail { background: var(--bs-tertiary-bg); }
.dct-detail pre { max-height: 32rem; overflow: auto; font-size: .75rem; white-space: pre-wrap; word-break: break-all; }
</style>
