<!--
  後台「商品資料庫 › 交易終端」（唯讀）：UEX 交易終端（uex_terminals）。

  約幾百筆，一次載入（GET /mining/uex-terminals），篩選排序在前端做。
  每筆附上這個終端在商品價格表裡有幾筆「買得到」「能賣」的商品，
  方便檢查價格表跟終端對不對得起來（0 筆的終端多半是只賣物品／載具的商店）。
-->
<template>
  <div>
    <!-- 搜尋卡：條件照列表欄位排（見 components/AdminSearchCard.vue）；篩選在前端做，打字即篩 -->
    <AdminSearchCard :active="hasActiveFilters" @clear="resetFilters">
      <AdminSearchField label="終端／代碼" for-id="uex-terminal-q" col="col-12 col-md-6 col-xl-3">
        <input id="uex-terminal-q" v-model="query" type="search" class="form-control form-control-sm" placeholder="輸入終端名稱、代碼或地點">
      </AdminSearchField>
      <AdminSearchField label="類型" for-id="uex-terminal-type">
        <MultiSelectFilter id="uex-terminal-type" v-model="types" label="類型" :options="typeOptions" block placeholder="全部" />
      </AdminSearchField>
      <AdminSearchField label="地點" for-id="uex-terminal-system">
        <MultiSelectFilter id="uex-terminal-system" v-model="systems" label="星系" :options="systemOptions" block placeholder="全部" />
      </AdminSearchField>
      <AdminSearchField label="可買／可賣商品" for-id="uex-terminal-has-commodity" col="col-6 col-md-3 col-xl">
        <select id="uex-terminal-has-commodity" v-model="hasCommodity" class="form-select form-select-sm">
          <option value="">全部</option>
          <option value="1">有</option>
          <option value="0">無</option>
        </select>
      </AdminSearchField>
      <template #summary>
        <template v-if="hasActiveFilters">符合 {{ filtered.length }} 筆 · </template>共 {{ rows.length }} 筆
      </template>
    </AdminSearchCard>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div v-if="loading" class="text-center py-4 text-muted">
          <span class="spinner-border spinner-border-sm me-2"></span>載入中...
        </div>
        <div v-else-if="loadFailed" class="text-center py-4">
          <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取交易終端失敗。</span>
          <button class="btn btn-sm btn-link p-0 ms-1" @click="load">重試</button>
        </div>
        <div v-else style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <SortTh :sort="tSort" field="name" class="ps-3">終端</SortTh>
                <SortTh :sort="tSort" field="code">代碼</SortTh>
                <SortTh :sort="tSort" field="type">類型</SortTh>
                <SortTh :sort="tSort" field="location">地點</SortTh>
                <SortTh :sort="tSort" field="commodity_buy_count" class="text-end">可買商品</SortTh>
                <SortTh :sort="tSort" field="commodity_sell_count" class="text-end">可賣商品</SortTh>
                <SortTh :sort="tSort" field="max_container_size" class="text-end">最大貨櫃</SortTh>
                <SortTh :sort="tSort" field="flags">屬性</SortTh>
                <SortTh :sort="tSort" field="date_modified" class="pe-3">更新時間</SortTh>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filtered.length">
                <td colspan="9" class="text-center py-4 text-muted">
                  {{ rows.length ? '沒有符合條件的交易終端' : '還沒有交易終端資料（到「資料同步排程」同步 UEX 價格）' }}
                </td>
              </tr>
              <tr v-for="t in tSort.sorted.value" :key="t.id">
                <td class="ps-3">
                  <span class="fw-semibold">{{ t.displayname || t.name || '—' }}</span>
                  <div v-if="t.name && t.displayname && t.name !== t.displayname" class="small text-muted">{{ t.name }}</div>
                </td>
                <td class="small font-monospace">{{ t.code || '—' }}</td>
                <td class="small">{{ t.type || '—' }}</td>
                <td class="small">{{ t.location.join(' › ') || '—' }}</td>
                <td class="small text-end">{{ t.commodity_buy_count || '—' }}</td>
                <td class="small text-end">{{ t.commodity_sell_count || '—' }}</td>
                <td class="small text-end text-nowrap">{{ t.max_container_size ? `${t.max_container_size} SCU` : '—' }}</td>
                <td class="small">
                  <span v-for="f in flagsOf(t)" :key="f.key" class="badge me-1" :class="f.cls">{{ f.label }}</span>
                  <span v-if="!flagsOf(t).length" class="text-muted">—</span>
                </td>
                <td class="small text-nowrap pe-3">{{ fmtUexTime(t.date_modified) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { miningApi } from '@/api'
import AdminSearchCard from '@/components/AdminSearchCard.vue'
import AdminSearchField from '@/components/AdminSearchField.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import SortTh from '@/components/SortTh.vue'
import { useTableSort } from '@/composables/useTableSort'
import { fmtUexTime } from '@/utils/uexCommodity'

// UEX 終端的 is_*／has_* 欄位（1／0）；is_available 為 0 的另外標「停用」
const FLAGS = [
  { key: 'is_player_owned',      label: '玩家經營', cls: 'bg-secondary-subtle text-secondary-emphasis' },
  { key: 'is_refinery',          label: '精煉廠',   cls: 'bg-info-subtle text-info-emphasis' },
  { key: 'is_cargo_center',      label: '貨運中心', cls: 'bg-info-subtle text-info-emphasis' },
  { key: 'has_loading_dock',     label: '裝卸碼頭', cls: 'bg-primary-subtle text-primary-emphasis' },
  { key: 'has_docking_port',     label: '停靠埠',   cls: 'bg-primary-subtle text-primary-emphasis' },
  { key: 'has_freight_elevator', label: '貨梯',     cls: 'bg-primary-subtle text-primary-emphasis' },
  { key: 'is_auto_load',         label: '自動裝貨', cls: 'bg-success-subtle text-success-emphasis' },
]

const rows = ref([])
const loading = ref(false)
const loadFailed = ref(false)

const query = ref('')
const systems = ref([])
const types = ref([])
const hasCommodity = ref('')   // '' 全部／'1' 有可買或可賣商品／'0' 都沒有
const hasActiveFilters = computed(() => !!(query.value.trim() || systems.value.length || types.value.length
  || hasCommodity.value))

async function load() {
  loading.value = true
  loadFailed.value = false
  try {
    const res = await miningApi.uexTerminals()
    const body = res?.ok ? await res.json().catch(() => null) : null
    if (!body?.success) {
      loadFailed.value = true
      return
    }
    rows.value = body.data || []
  } finally {
    loading.value = false
  }
}

const systemOptions = computed(() =>
  [...new Set(rows.value.map(t => t.star_system_name).filter(Boolean))].sort().map(s => ({ value: s, label: s })))
const typeOptions = computed(() =>
  [...new Set(rows.value.map(t => t.type).filter(Boolean))].sort().map(s => ({ value: s, label: s })))

function flagsOf(t) {
  const out = FLAGS.filter(f => Number(t[f.key]))
  if (t.is_available === 0 || t.is_available === '0') {
    out.unshift({ key: 'unavailable', label: '停用', cls: 'bg-danger-subtle text-danger-emphasis' })
  }
  return out
}

function resetFilters() {
  query.value = ''
  systems.value = []
  types.value = []
  hasCommodity.value = ''
}

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rows.value.filter(t =>
    (!q || [t.name, t.nickname, t.displayname, t.code, ...t.location].some(x => (x || '').toLowerCase().includes(q)))
    && (!systems.value.length || systems.value.includes(t.star_system_name))
    && (!types.value.length || types.value.includes(t.type))
    && (!hasCommodity.value || !!(t.commodity_buy_count || t.commodity_sell_count) === (hasCommodity.value === '1')))
})
const tSort = useTableSort(filtered, { accessors: {
  name: t => t.displayname || t.name, location: t => (t.location || []).join(' › '),
  max_container_size: t => Number(t.max_container_size) || null, flags: t => flagsOf(t).map(f => f.label).join('、'),
  date_modified: t => Number(t.date_modified) || null,
} })

onMounted(load)
</script>
