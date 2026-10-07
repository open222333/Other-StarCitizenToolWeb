<!--
  後台「商品資料庫」（唯讀）：UEX Corp API 的商品清單（uex_commodities）。

  資料由「資料同步排程」的 UEX 項目同步（需要 UEX token，見 src/models/app_setting.py），
  API 是 GET /mining/uex-commodities/detail（src/models/uex_commodity.py 的 list_detail）。
  約兩三百筆，一次載入、篩選排序都在前端做，比照礦物資料庫（MiningView.vue）。

  每筆附上「關聯礦物」：礦物資料庫依英文名稱自動對應到的（或在礦物資料庫手動指定的）
  礦物；精煉品與原礦兩筆都看得到關聯。要改關聯到 後台 › 礦物 › 礦物分頁。

  中文名稱：UEX 只有英文，用 utils/translations.js 查資料庫 sc_translations
  （先查礦物，再查物品），查不到顯示「—」。
-->
<template>
  <div>
    <h5 class="mb-3 fw-bold"><i class="bi bi-boxes me-2 text-primary"></i>商品資料庫</h5>

    <!-- ── 篩選 ────────────────────────────────────────────── -->
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm"
            style="max-width: 16rem" placeholder="搜尋縮寫、英文或中文名稱..." aria-label="搜尋商品">
          <MultiSelectFilter v-model="kinds" label="類別" :options="kindOptions" />
          <select v-model="flag" class="form-select form-select-sm w-auto" aria-label="屬性">
            <option value="">屬性：全部</option>
            <option v-for="f in FLAGS" :key="f.key" :value="f.key">{{ f.label }}</option>
          </select>
          <div class="form-check form-check-inline mb-0 ms-1">
            <input id="commodity-linked" v-model="linkedOnly" class="form-check-input" type="checkbox">
            <label class="form-check-label small" for="commodity-linked">只看有關聯礦物</label>
          </div>
          <button v-if="hasActiveFilters" type="button" class="btn btn-sm btn-link" @click="resetFilters">
            清除全部篩選
          </button>
          <span class="ms-auto small text-muted">
            <template v-if="hasActiveFilters">符合 {{ filtered.length }} 筆 · </template>共 {{ rows.length }} 筆
          </span>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-4 text-muted">
          <span class="spinner-border spinner-border-sm me-2"></span>載入中...
        </div>
        <div v-else-if="loadFailed" class="text-center py-4">
          <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取商品資料失敗。</span>
          <button class="btn btn-sm btn-link p-0 ms-1" @click="load">重試</button>
        </div>
        <div v-else style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3 sortable" @click="setSort('code')">縮寫<SortIcon k="code" /></th>
                <th class="sortable" @click="setSort('name')">商品（英文）<SortIcon k="name" /></th>
                <th>中文</th>
                <th class="sortable" @click="setSort('kind')">類別<SortIcon k="kind" /></th>
                <th class="text-end sortable" @click="setSort('price_buy')">參考買價<SortIcon k="price_buy" /></th>
                <th class="text-end sortable" @click="setSort('price_sell')">參考賣價<SortIcon k="price_sell" /></th>
                <th>屬性</th>
                <th class="pe-3">關聯礦物</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filtered.length">
                <td colspan="8" class="text-center py-4 text-muted">
                  {{ rows.length ? '沒有符合條件的商品' : '還沒有商品資料（到「資料同步排程」同步 UEX 價格）' }}
                </td>
              </tr>
              <tr v-for="r in filtered" :key="r.id">
                <td class="ps-3">
                  <span v-if="r.code" class="badge bg-primary-subtle text-primary-emphasis font-monospace code-badge">{{ r.code }}</span>
                  <span v-else class="text-muted">—</span>
                </td>
                <td class="fw-semibold">{{ r.name }}</td>
                <td><span v-if="r.zh">{{ r.zh }}</span><span v-else class="text-muted">—</span></td>
                <td class="small">{{ r.kind || '—' }}</td>
                <td class="small text-end text-nowrap">{{ fmtPrice(r.price_buy) }}</td>
                <td class="small text-end text-nowrap">{{ fmtPrice(r.price_sell) }}</td>
                <td class="small">
                  <span v-for="f in flagsOf(r)" :key="f.key" class="badge me-1" :class="f.cls">{{ f.label }}</span>
                  <span v-if="!flagsOf(r).length" class="text-muted">—</span>
                </td>
                <td class="small pe-3">
                  <span v-if="!r.minerals.length" class="text-muted">—</span>
                  <div v-for="m in r.minerals" :key="m.resource_key + (m.as_raw ? '/raw' : '')">
                    {{ m.zh ? `${m.zh}（${m.resource_name}）` : m.resource_name }}
                    <span v-if="m.as_raw" class="text-muted">· 原礦</span>
                    <span v-if="m.source === 'manual'" class="badge bg-secondary-subtle text-secondary-emphasis ms-1">手動</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { miningApi } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import { loadTranslations, translate } from '@/utils/translations'

// 屬性篩選與標籤（UEX 的 is_* 欄位，1／0）
const FLAGS = [
  { key: 'is_mineral',     label: '礦物',   cls: 'bg-info-subtle text-info-emphasis' },
  { key: 'is_raw',         label: '原礦',   cls: 'bg-secondary-subtle text-secondary-emphasis' },
  { key: 'is_refined',     label: '精煉',   cls: 'bg-success-subtle text-success-emphasis' },
  { key: 'is_harvestable', label: '可採集', cls: 'bg-success-subtle text-success-emphasis' },
  { key: 'is_buyable',     label: '可買',   cls: 'bg-primary-subtle text-primary-emphasis' },
  { key: 'is_sellable',    label: '可賣',   cls: 'bg-primary-subtle text-primary-emphasis' },
  { key: 'is_illegal',     label: '違禁',   cls: 'bg-danger-subtle text-danger-emphasis' },
  { key: 'is_explosive',   label: '易爆',   cls: 'bg-warning-subtle text-warning-emphasis' },
  { key: 'is_volatile_qt', label: '量子不穩定', cls: 'bg-warning-subtle text-warning-emphasis' },
  { key: 'is_volatile_time', label: '會變質', cls: 'bg-warning-subtle text-warning-emphasis' },
]

const rawRows = ref([])
const loading = ref(false)
const loadFailed = ref(false)

const query = ref('')
const kinds = ref([])
const flag = ref('')
const linkedOnly = ref(false)
const sortKey = ref('code')
const sortAsc = ref(true)

async function load() {
  loading.value = true
  loadFailed.value = false
  try {
    const res = await miningApi.uexCommodityDetail()
    const body = res?.ok ? await res.json().catch(() => null) : null
    if (!body?.success) {
      loadFailed.value = true
      return
    }
    rawRows.value = body.data || []
    const names = rawRows.value.map(r => r.name).filter(Boolean)
    loadTranslations('mining_resource', names)
    loadTranslations('item', names)
  } finally {
    loading.value = false
  }
}

const zhOf = name => (name ? translate('mining_resource', name) || translate('item', name) || '' : '')

const rows = computed(() => rawRows.value.map(r => ({
  ...r,
  zh: zhOf(r.name),
  minerals: (r.minerals || []).map(m => ({
    ...m, zh: translate('mining_resource', m.resource_name) || m.resource_name_zh || '',
  })),
})))

const kindOptions = computed(() =>
  [...new Set(rawRows.value.map(r => r.kind).filter(Boolean))].sort().map(k => ({ value: k, label: k })))

const flagsOf = r => FLAGS.filter(f => r[f.key])

const hasActiveFilters = computed(() => !!(query.value.trim() || kinds.value.length || flag.value || linkedOnly.value))

function resetFilters() {
  query.value = ''
  kinds.value = []
  flag.value = ''
  linkedOnly.value = false
}

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  const out = rows.value.filter(r =>
    (!q || [r.code, r.name, r.zh, ...r.minerals.flatMap(m => [m.resource_name, m.zh])]
      .some(t => (t || '').toLowerCase().includes(q)))
    && (!kinds.value.length || kinds.value.includes(r.kind))
    && (!flag.value || r[flag.value])
    && (!linkedOnly.value || r.minerals.length))
  const key = sortKey.value
  const dir = sortAsc.value ? 1 : -1
  return out.sort((a, b) => {
    const x = a[key], y = b[key]
    // 空值一律排最後
    if (x === null || x === undefined || x === '') return 1
    if (y === null || y === undefined || y === '') return -1
    return (typeof x === 'number' ? x - y : String(x).localeCompare(String(y))) * dir
  })
})

function setSort(key) {
  if (sortKey.value === key) sortAsc.value = !sortAsc.value
  else { sortKey.value = key; sortAsc.value = !key.startsWith('price') }
}

const SortIcon = (props) => h('i', {
  class: ['bi', 'ms-1', sortKey.value !== props.k ? 'bi-arrow-down-up text-muted opacity-50'
    : (sortAsc.value ? 'bi-sort-up' : 'bi-sort-down')],
})
SortIcon.props = ['k']

function fmtPrice(v) {
  if (v === null || v === undefined || v === '' || Number(v) === 0) return '—'
  return `${Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 })} aUEC`
}

onMounted(load)
</script>

<style scoped>
.sortable { cursor: pointer; user-select: none; white-space: nowrap; }
.code-badge { font-size: .85rem; }
</style>
