<!--
  後台「商品資料庫 › 交易終端」（唯讀）：UEX 交易終端（uex_terminals）。

  約幾百筆，一次載入（GET /mining/uex-terminals），篩選排序在前端做。
  每筆附上這個終端在商品價格表裡有幾筆「買得到」「能賣」的商品，
  方便檢查價格表跟終端對不對得起來（0 筆的終端多半是只賣物品／載具的商店）。
-->
<template>
  <div>
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm" style="max-width: 16rem"
            placeholder="搜尋終端名稱、代碼或地點..." aria-label="搜尋交易終端">
          <MultiSelectFilter v-model="systems" label="星系" :options="systemOptions" />
          <MultiSelectFilter v-model="types" label="類型" :options="typeOptions" />
          <div class="form-check form-check-inline mb-0 ms-1">
            <input id="terminal-has-commodity" v-model="commodityOnly" class="form-check-input" type="checkbox">
            <label class="form-check-label small" for="terminal-has-commodity">只看有商品價格</label>
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
          <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取交易終端失敗。</span>
          <button class="btn btn-sm btn-link p-0 ms-1" @click="load">重試</button>
        </div>
        <div v-else style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">終端</th>
                <th>代碼</th>
                <th>類型</th>
                <th>地點</th>
                <th class="text-end">可買商品</th>
                <th class="text-end">可賣商品</th>
                <th class="text-end">最大貨櫃</th>
                <th>屬性</th>
                <th class="pe-3">更新時間</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filtered.length">
                <td colspan="9" class="text-center py-4 text-muted">
                  {{ rows.length ? '沒有符合條件的交易終端' : '還沒有交易終端資料（到「資料同步排程」同步 UEX 價格）' }}
                </td>
              </tr>
              <tr v-for="t in filtered" :key="t.id">
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
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
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
const commodityOnly = ref(false)
const hasActiveFilters = computed(() => !!(query.value.trim() || systems.value.length || types.value.length
  || commodityOnly.value))

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
  commodityOnly.value = false
}

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rows.value.filter(t =>
    (!q || [t.name, t.nickname, t.displayname, t.code, ...t.location].some(x => (x || '').toLowerCase().includes(q)))
    && (!systems.value.length || systems.value.includes(t.star_system_name))
    && (!types.value.length || types.value.includes(t.type))
    && (!commodityOnly.value || t.commodity_buy_count || t.commodity_sell_count))
})

onMounted(load)
</script>
