<!--
  玩家頁「查詢 › 商品購買地點」：勾選多種商品 → 列出「全部都買得到」的交易終端。

  資料：UEX 商品價格表（uex_commodities_prices，見 src/models/uex_commodity_price.py），
  由後台「資料同步排程」的 UEX 項目同步。API：
    - GET /player/commodities/buyable：買得到的商品（附可購買的終端數）、有終端的星系
    - GET /player/commodities/buy-locations?id=…&id=…&star_system=…：同時買得到的終端
  商品清單一次載入（兩三百筆），名稱／類別篩選在前端；勾選或星系改了才打後端查地點。

  結果用蜂巢式下拉（交易終端 → 每種商品的買價／庫存／回報時間），樣式見 scifi-theme.css 的 .sf-tree-*。
  中文：utils/uexCommodity.js（資料庫 sc_translations）。
-->
<template>
  <div>
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body py-3">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <label class="form-label small fw-semibold mb-0">搜尋條件</label>
          <button type="button" class="btn btn-sm btn-warning py-0" :disabled="!hasAnyFilter" @click="clearAll">
            清除全部
          </button>
        </div>
        <FieldHint :text="`勾選的商品要在同一個交易終端全部都買得到才會列出，一次最多 ${maxSelected} 種。價格與庫存是玩家回報到 UEX 的資料，請參考更新時間。`" />
        <div class="row g-2">
          <div class="col-12 col-md-6">
            <label class="form-label small mb-1" :for="`${uid}-q`">商品名稱</label>
            <input :id="`${uid}-q`" v-model="nameQuery" type="search" class="form-control form-control-sm"
              placeholder="輸入商品名稱或縮寫…" autocomplete="off">
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label small mb-1" :for="`${uid}-kind`">類別</label>
            <MultiSelectFilter :id="`${uid}-kind`" v-model="kinds" :options="kindOptions"
              label="類別" placeholder="全部" block searchable />
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label small mb-1" :for="`${uid}-system`">星系</label>
            <MultiSelectFilter :id="`${uid}-system`" v-model="systems" :options="systemOptions"
              label="星系" placeholder="全部" block />
          </div>
        </div>

        <div v-if="selected.length" class="cbf-picked mt-2">
          <span class="small text-muted me-1">已選 {{ selected.length }} / {{ maxSelected }}</span>
          <button v-for="c in selectedCommodities" :key="c.id" type="button" class="btn btn-sm btn-warning"
            :aria-label="`取消勾選 ${commodityLabel(c)}`" @click="toggle(c.id, false)">
            {{ commodityZh(c.name) || c.name }}<i class="bi bi-x-lg ms-1"></i>
          </button>
        </div>

        <div v-if="loading" class="text-muted small mt-2">載入中…</div>
        <div v-else-if="loadFailed" class="mt-2">
          <span class="text-warning small"><i class="bi bi-exclamation-triangle me-1"></i>讀取商品清單失敗。</span>
          <button type="button" class="btn btn-sm btn-primary ms-1" @click="loadCommodities">重新整理</button>
        </div>
        <div v-else-if="!commodities.length" class="text-muted small mt-2">目前沒有商品價格資料。</div>
        <div v-else class="cbf-list mt-2" role="group" aria-label="商品">
          <div v-if="!filteredCommodities.length" class="small text-muted px-2 py-2">沒有符合的商品</div>
          <label v-for="c in filteredCommodities" :key="c.id" class="cbf-item"
            :class="{ 'is-checked': selectedSet.has(c.id) }">
            <input type="checkbox" class="form-check-input me-2" :checked="selectedSet.has(c.id)"
              :disabled="!selectedSet.has(c.id) && selected.length >= maxSelected"
              @change="toggle(c.id, $event.target.checked)">
            <span class="cbf-item__name">{{ commodityLabel(c) }}</span>
            <span v-if="c.code" class="sf-tree-chip ms-2">{{ c.code }}</span>
            <span v-if="c.is_illegal" class="sf-tree-chip cbf-illegal ms-1">違禁</span>
            <span class="cbf-item__meta">{{ c.terminal_count }} 個地點</span>
          </label>
        </div>
      </div>
    </div>

    <!-- ── 結果 ───────────────────────────────────────────── -->
    <template v-if="selected.length">
      <div v-if="resultsLoading" class="text-muted small">查詢中…</div>
      <div v-else-if="resultsFailed" class="text-warning small">
        <i class="bi bi-exclamation-triangle me-1"></i>{{ resultsFailed }}
      </div>
      <div v-else-if="!locations.length" class="cbf-empty">
        <div class="mb-1">沒有交易終端同時買得到這 {{ selected.length }} 種商品<template v-if="systems.length">（限 {{ systems.map(locationZh).join('、') }}）</template>。</div>
        <div class="small text-muted">
          各自買得到的地點數：
          <template v-for="(c, i) in coverage" :key="c.id">
            <template v-if="i">、</template>{{ commodityZh(c.name) || c.name }} {{ c.terminal_count }}
          </template>
        </div>
      </div>
      <template v-else>
        <div class="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2">
          <span class="small text-muted">同時買得到 {{ selected.length }} 種商品的地點：{{ locations.length }} 個</span>
          <button type="button" class="btn btn-sm btn-info" @click="toggleAll">
            {{ allOpen ? '全部收起' : '全部展開' }}
          </button>
        </div>
        <div v-for="loc in locations" :key="loc.terminal.id" class="cbf-terminal">
          <button type="button" class="sf-tree-row sf-tree-row--ship"
            :aria-expanded="openIds.has(loc.terminal.id) ? 'true' : 'false'" @click="toggleOpen(loc.terminal.id)">
            <i class="bi" :class="openIds.has(loc.terminal.id) ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
            <span class="sf-tree-title">{{ loc.terminal.name }}</span>
            <span v-if="loc.terminal.star_system" class="sf-tree-chip">{{ locationZh(loc.terminal.star_system) }}</span>
            <span class="sf-tree-meta cbf-meta">{{ locationPathLabel(loc.terminal.location.slice(1)) }}</span>
          </button>
          <div v-if="openIds.has(loc.terminal.id)" class="sf-tree-level">
            <div class="sf-tree-info">
              {{ locationPathLabel(loc.terminal.location) }}
              <template v-if="loc.terminal.max_container_size"> · 最大貨櫃 {{ loc.terminal.max_container_size }} SCU</template>
            </div>
            <div v-for="item in loc.items" :key="item.id" class="sf-tree-leaf">
              <span class="sf-tree-title">{{ commodityLabel(item) }}</span>
              <span v-if="item.code" class="sf-tree-chip">{{ item.code }}</span>
              <span>{{ fmtAuec(item.price_buy) }} / SCU</span>
              <span class="text-muted">庫存 {{ fmtScu(item.scu_buy) }}<template v-if="uexStatusLabel(item.status_buy)">（{{ uexStatusLabel(item.status_buy) }}）</template></span>
              <span class="sf-tree-meta">更新 {{ fmtUexTime(item.date_modified) }}</span>
            </div>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import FieldHint from '@/components/FieldHint.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import {
  commodityLabel, commodityZh, fmtAuec, fmtScu, fmtUexTime, loadCommodityZh, loadLocationZh,
  locationPathLabel, locationZh, uexStatusLabel,
} from '@/utils/uexCommodity'

const props = defineProps({
  /** 帶身分的 fetch（玩家頁傳 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  cardClass: { type: String, default: 'card scifi-card' },
  /** 點開才載入（玩家頁用 v-show 一直掛著） */
  active: { type: Boolean, default: true },
})

// 跟後端 src/models/uex_commodity_price.py 的 MAX_SELECTED 一致
const maxSelected = 20
const uid = `cbf-${Math.random().toString(36).slice(2, 8)}`

const commodities = ref([])
const starSystems = ref([])
const loading = ref(false)
const loadFailed = ref(false)

const nameQuery = ref('')
const kinds = ref([])
const systems = ref([])
/** 勾選的商品 id（依勾選順序，結果裡每個終端的商品也照這個順序） */
const selected = ref([])
const selectedSet = computed(() => new Set(selected.value))
const hasAnyFilter = computed(() => !!(nameQuery.value.trim() || kinds.value.length || systems.value.length
  || selected.value.length))

const byId = computed(() => new Map(commodities.value.map(c => [c.id, c])))
const selectedCommodities = computed(() => selected.value.map(id => byId.value.get(id)).filter(Boolean))

const kindOptions = computed(() =>
  [...new Set(commodities.value.map(c => c.kind).filter(Boolean))].sort().map(k => ({ value: k, label: k })))
const systemOptions = computed(() => starSystems.value.map(s => ({ value: s, label: locationZh(s) })))

const filteredCommodities = computed(() => {
  const q = nameQuery.value.trim().toLowerCase()
  return commodities.value.filter(c =>
    (!kinds.value.length || kinds.value.includes(c.kind))
    && (!q || [c.name, c.code, commodityZh(c.name)].some(t => (t || '').toLowerCase().includes(q))))
})

function toggle(id, checked) {
  if (checked) {
    if (!selectedSet.value.has(id) && selected.value.length < maxSelected) selected.value = [...selected.value, id]
  } else {
    selected.value = selected.value.filter(x => x !== id)
  }
}

function clearAll() {
  nameQuery.value = ''
  kinds.value = []
  systems.value = []
  selected.value = []
}

async function getJson(path) {
  const res = await props.fetcher(path)
  const data = res ? await res.json().catch(() => null) : null
  return { ok: !!res?.ok, data }
}

async function loadCommodities() {
  loading.value = true
  loadFailed.value = false
  const { ok, data } = await getJson('/player/commodities/buyable')
  loading.value = false
  if (!ok || !data?.success) {
    loadFailed.value = true
    return
  }
  commodities.value = data.data || []
  starSystems.value = data.star_systems || []
  loadCommodityZh(commodities.value.map(c => c.name))
  loadLocationZh(starSystems.value)
}

// ── 查同時買得到的地點 ───────────────────────────────────────
const locations = ref([])
const coverage = ref([])
const resultsLoading = ref(false)
const resultsFailed = ref('')
const openIds = ref(new Set())
const allOpen = computed(() => locations.value.length > 0 && openIds.value.size === locations.value.length)
let seq = 0
let timer = null

async function loadLocations() {
  const mine = ++seq
  if (!selected.value.length) {
    locations.value = []
    coverage.value = []
    resultsLoading.value = false
    return
  }
  resultsLoading.value = true
  resultsFailed.value = ''
  const params = new URLSearchParams()
  selected.value.forEach(id => params.append('id', id))
  systems.value.forEach(s => params.append('star_system', s))
  const { ok, data } = await getJson(`/player/commodities/buy-locations?${params.toString()}`)
  if (mine !== seq) return
  resultsLoading.value = false
  if (!ok || !data?.success) {
    resultsFailed.value = data?.message || '查詢失敗，請稍後再試'
    return
  }
  locations.value = data.data?.locations || []
  coverage.value = data.data?.commodities || []
  // 結果少的時候直接展開，不用一個一個點
  openIds.value = new Set(locations.value.length <= 3 ? locations.value.map(l => l.terminal.id) : [])
  loadLocationZh(locations.value.flatMap(l => l.terminal.location))
}

watch([selected, systems], () => {
  clearTimeout(timer)
  timer = setTimeout(loadLocations, 250)
})
onBeforeUnmount(() => clearTimeout(timer))

function toggleOpen(id) {
  const next = new Set(openIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  openIds.value = next
}

function toggleAll() {
  openIds.value = new Set(allOpen.value ? [] : locations.value.map(l => l.terminal.id))
}

let loaded = false
watch(() => props.active, (v) => {
  if (!v || loaded) return
  loaded = true
  loadCommodities()
}, { immediate: true })

defineExpose({ refresh: () => { loadCommodities(); loadLocations() } })
</script>

<style scoped>
.cbf-picked { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; }
.cbf-list {
  max-height: 18rem;
  overflow-y: auto;
  padding: .25rem;
  background: var(--sf-panel-2);
  border: 1px solid var(--sf-border);
  border-radius: 6px;
}
.cbf-item {
  display: flex;
  align-items: center;
  padding: .35rem .5rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  color: var(--sf-text);
}
.cbf-item:hover,
.cbf-item.is-checked { background: rgba(var(--sf-accent-rgb), .12); }
.cbf-item__name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cbf-item__meta { margin-left: auto; padding-left: .75rem; white-space: nowrap; color: var(--sf-text-muted); }
.cbf-illegal { color: var(--sf-accent-2); border-color: rgba(var(--sf-accent-2-rgb), .45); }
.cbf-terminal { margin-bottom: .4rem; }
.cbf-meta { overflow: hidden; text-overflow: ellipsis; }
.cbf-empty {
  padding: .75rem 1rem;
  background: var(--sf-panel);
  border: 1px solid var(--sf-border);
  border-radius: 6px;
}
</style>
