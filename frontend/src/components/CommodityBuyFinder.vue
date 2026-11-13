<!--
  玩家頁「查詢 › 商品購買地點」：勾選多種商品 → 列出「全部都買得到」的交易終端。

  資料：UEX 商品價格表（uex_commodities_prices，見 src/models/uex_commodity_price.py），
  由後台「資料同步排程」的 UEX 項目同步。API：
    - GET /player/commodities/buyable：買得到的商品（附可購買的終端數）、有終端的星系、
      終端的「星系／行星／地點」分布（areas，給三段篩選的選項）
    - GET /player/commodities/buy-locations?id=…&id=…&star_system=…：同時買得到的終端
  商品清單一次載入（兩三百筆），名稱／類別篩選在前端；勾選或星系改了才打後端查地點，
  行星／地點在前端篩查回來的終端（terminal.planet／terminal.place）。

  商品清單是多欄、每項一行（中文名、英文全名、縮寫）；滑鼠移到（或點）哪一項，上方細節區塊就顯示它的完整名稱、類別、地點數。
  結果用蜂巢式下拉（交易終端 → 每種商品的買價／庫存／回報時間），樣式見 scifi-theme.css 的 .sf-tree-*。
  中文：utils/uexCommodity.js（資料庫 sc_translations）。
-->
<template>
  <!-- sf-split：超寬螢幕搜尋卡放左邊、列表放右邊（跟資料庫其他子分頁一致，見 scifi-theme.css） -->
  <div ref="rootEl" class="sf-split" :style="{ '--cbf-subtabs-h': `${subtabsH}px` }">
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body py-3">
        <div class="d-flex align-items-center justify-content-between mb-2">
          <span class="form-label small fw-semibold mb-0">搜尋條件</span>
          <button type="button" class="btn btn-sm btn-warning" :disabled="!hasAnyFilter" @click="clearAll">
            清除全部
          </button>
        </div>
        <div class="row g-2 align-items-end">
          <div class="col col-md-8">
            <label class="form-label small mb-1" :for="`${uid}-q`">商品名稱</label>
            <input :id="`${uid}-q`" v-model="nameQuery" type="search" class="form-control form-control-sm"
              placeholder="輸入商品名稱或縮寫…" autocomplete="off">
          </div>
          <!-- 手機：名稱以外的條件收進「篩選」底部面板（電腦／平板照原樣） -->
          <SfFilterSheet :count="sheetCount" @clear="clearSheet">
          <div class="col-12 col-md-4">
            <label class="form-label small mb-1" :for="`${uid}-kind`">類別</label>
            <MultiSelectFilter :id="`${uid}-kind`" v-model="kinds" :options="kindOptions"
              label="類別" placeholder="全部" block searchable />
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label small mb-1" :for="`${uid}-system`">星系</label>
            <MultiSelectFilter :id="`${uid}-system`" :model-value="systems" :options="systemOptions"
              label="星系" placeholder="全部" block @update:model-value="setSystems" />
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label small mb-1" :for="`${uid}-planet`">行星</label>
            <MultiSelectFilter :id="`${uid}-planet`" :model-value="planets" :options="planetOptions"
              label="行星" placeholder="全部" block searchable @update:model-value="setPlanets" />
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label small mb-1" :for="`${uid}-place`">地點</label>
            <MultiSelectFilter :id="`${uid}-place`" v-model="places" :options="placeOptions"
              label="地點" placeholder="全部" block searchable />
          </div>
          </SfFilterSheet>
        </div>

        <div v-if="selected.length" class="cbf-picked mt-2">
          <span class="small text-muted me-1">已選 {{ selected.length }} / {{ maxSelected }}</span>
          <button v-for="c in selectedCommodities" :key="c.id" type="button" class="btn btn-sm btn-warning"
            :aria-label="`取消勾選 ${commodityLabel(c)}`" @click="toggle(c.id, false)">
            {{ commodityZh(c.name) || c.name }}<i class="bi bi-x-lg ms-1"></i>
          </button>
        </div>

        <SfState :loading="loading" :error="loadFailed ? '讀取商品清單失敗。' : ''" :empty="!commodities.length"
          empty-text="目前沒有商品價格資料。" @retry="loadCommodities">
        <!-- 細節區塊：滑鼠移到（或點、鍵盤聚焦）哪一項就顯示哪一項；往下捲時黏在畫面頂端（在固定的工具列／分頁列下面） -->
        <div class="cbf-info mt-2" aria-live="polite">
          <template v-if="hovered">
            <span class="fw-semibold">{{ commodityLabel(hovered) }}</span>
            <span v-if="hovered.code" class="sf-tree-chip">{{ hovered.code }}</span>
            <span v-if="hovered.is_illegal" class="sf-tree-chip cbf-illegal">違禁</span>
            <span v-if="hovered.kind" class="cbf-info__muted">{{ hovered.kind }}</span>
            <span class="cbf-info__muted">{{ hovered.terminal_count }} 個地點</span>
          </template>
        </div>
        <div class="cbf-list mt-2" role="group" aria-label="商品" @mouseleave="hoverId = ''">
          <div v-if="!filteredCommodities.length" class="small text-muted px-2 py-2">沒有符合的商品</div>
          <label v-for="c in filteredCommodities" :key="c.id" class="cbf-item"
            :class="{ 'is-checked': selectedSet.has(c.id) }" @mouseenter="hoverId = c.id" @focusin="hoverId = c.id">
            <input type="checkbox" class="form-check-input me-2" :checked="selectedSet.has(c.id)"
              :disabled="!selectedSet.has(c.id) && selected.length >= maxSelected"
              @change="toggle(c.id, $event.target.checked)">
            <span class="cbf-item__name">{{ commodityZh(c.name) || c.name }}</span>
            <!-- 英文全名、縮寫直接顯示 -->
            <span class="cbf-item__sub">
              <span v-if="commodityZh(c.name)" class="cbf-item__en">{{ c.name }}</span>
              <span v-if="c.code" class="sf-tree-chip">{{ c.code }}</span>
              <span v-if="c.is_illegal" class="sf-tree-chip cbf-illegal">違禁</span>
            </span>
          </label>
        </div>
        </SfState>
      </div>
    </div>

    <!-- ── 結果 ───────────────────────────────────────────── -->
    <template v-if="selected.length">
      <SfState v-if="resultsLoading || resultsFailed" :loading="resultsLoading" :error="resultsFailed"
        loading-text="查詢中…" @retry="loadLocations" />
      <div v-else-if="!locations.length" class="cbf-empty">
        <div class="mb-1">沒有交易終端同時買得到這 {{ selected.length }} 種商品<template v-if="areaPicked.length">（限 {{ areaPicked.map(x => locationZh(x) || x).join('、') }}）</template>。</div>
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import SfFilterSheet from '@/components/SfFilterSheet.vue'
import SfState from '@/components/SfState.vue'
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
// 「星系／行星／地點」三段：星系送後端篩，行星／地點在前端篩查回來的終端
const systems = ref([])
const planets = ref([])
const places = ref([])
/** 交易終端分布（[{system, planet, place}]，/player/commodities/buyable 的 areas），給行星／地點的選項 */
const areas = ref([])
/** 勾選的商品 id（依勾選順序，結果裡每個終端的商品也照這個順序） */
const selected = ref([])
const selectedSet = computed(() => new Set(selected.value))
const hasAnyFilter = computed(() => !!(nameQuery.value.trim() || kinds.value.length || areaPicked.value.length
  || selected.value.length))
const areaPicked = computed(() => [...systems.value, ...planets.value, ...places.value])

const byId = computed(() => new Map(commodities.value.map(c => [c.id, c])))
const selectedCommodities = computed(() => selected.value.map(id => byId.value.get(id)).filter(Boolean))

const kindOptions = computed(() =>
  [...new Set(commodities.value.map(c => c.kind).filter(Boolean))].sort().map(k => ({ value: k, label: k })))
const areaLabel = v => (locationZh(v) && locationZh(v) !== v ? `${v}（${locationZh(v)}）` : v)
const uniqOpts = vals => [...new Set(vals.filter(Boolean))].sort((a, b) => a.localeCompare(b))
  .map(v => ({ value: v, label: areaLabel(v) }))
const systemOptions = computed(() => starSystems.value.map(s => ({ value: s, label: areaLabel(s) })))
const areasIn = (sys, pl) => areas.value.filter(a =>
  (!sys.length || sys.includes(a.system)) && (!pl.length || pl.includes(a.planet)))
const planetOptions = computed(() => uniqOpts(areasIn(systems.value, []).map(a => a.planet)))
const placeOptions = computed(() => uniqOpts(areasIn(systems.value, planets.value).map(a => a.place)))

// 改了上一段，下一段已選但不在新選項裡的拿掉
function setSystems(v) {
  systems.value = v
  const ok = new Set(areasIn(v, []).map(a => a.planet))
  planets.value = planets.value.filter(p => ok.has(p))
  setPlanets(planets.value)
}
function setPlanets(v) {
  planets.value = v
  const ok = new Set(areasIn(systems.value, v).map(a => a.place))
  places.value = places.value.filter(p => ok.has(p))
}

const filteredCommodities = computed(() => {
  const q = nameQuery.value.trim().toLowerCase()
  return commodities.value.filter(c =>
    (!kinds.value.length || kinds.value.includes(c.kind))
    && (!q || [c.name, c.code, commodityZh(c.name)].some(t => (t || '').toLowerCase().includes(q))))
})

// 細節區塊黏在頂端時要讓出下層分頁列（.scifi-subtabs，也是 sticky）的高度；
// 工具列、主分頁列的高度由 MyPlayerView 量好放在 --sf-topbar-h／--sf-tabs-h
const rootEl = ref(null)
const subtabsH = ref(0)
let subtabsObserver = null
onMounted(() => {
  const el = document.querySelector('.scifi-subtabs')
  if (!el || typeof ResizeObserver === 'undefined') return
  const sync = () => { subtabsH.value = Math.round(el.getBoundingClientRect().height) }
  sync()
  subtabsObserver = new ResizeObserver(sync)
  subtabsObserver.observe(el)
})
onBeforeUnmount(() => subtabsObserver?.disconnect())

// 上方細節區塊顯示的商品（滑鼠移到／聚焦的那一項）
const hoverId = ref('')
const hovered = computed(() => (hoverId.value ? byId.value.get(hoverId.value) || null : null))

function toggle(id, checked) {
  if (checked) {
    if (!selectedSet.value.has(id) && selected.value.length < maxSelected) selected.value = [...selected.value, id]
  } else {
    selected.value = selected.value.filter(x => x !== id)
  }
}

/** 手機「篩選」面板裡的條件數（名稱以外） */
const sheetCount = computed(() => kinds.value.length + areaPicked.value.length)
function clearSheet() {
  kinds.value = []
  systems.value = []
  planets.value = []
  places.value = []
}

function clearAll() {
  nameQuery.value = ''
  kinds.value = []
  systems.value = []
  planets.value = []
  places.value = []
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
  areas.value = data.areas || []
  loadCommodityZh(commodities.value.map(c => c.name))
  loadLocationZh([...starSystems.value, ...areas.value.flatMap(a => [a.planet, a.place])].filter(Boolean))
}

// ── 查同時買得到的地點 ───────────────────────────────────────
/** 後端回來的（已依星系篩過）；locations 再依行星／地點篩 */
const allLocations = ref([])
const locations = computed(() => allLocations.value.filter(l =>
  (!planets.value.length || planets.value.includes(l.terminal.planet))
  && (!places.value.length || places.value.includes(l.terminal.place))))
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
    allLocations.value = []
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
  allLocations.value = data.data?.locations || []
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
/* 商品格狀清單：寬度自動排欄（手機 2 欄） */
/* 商品清單：多欄、每項一行（不加外框） */
.cbf-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: .1rem .75rem;
  padding: .35rem;
  background: var(--sf-panel-2);
  border: 1px solid var(--sf-border);
  border-radius: 6px;
}
@media (min-width: 768px) {
  .cbf-list { grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr)); }
}
.cbf-list > .small { grid-column: 1 / -1; }
.cbf-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: .4rem;
  min-width: 0;
  padding: .3rem .45rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  color: var(--sf-text);
  white-space: nowrap;
}
.cbf-item .form-check-input { margin-right: 0 !important; flex: 0 0 auto; }
.cbf-item:hover,
.cbf-item:focus-within { background: rgba(var(--sf-accent-rgb), .08); }
.cbf-item.is-checked { background: rgba(var(--sf-accent-rgb), .16); }
.cbf-item__name { flex: 0 0 auto; }
.cbf-item__sub { display: flex; align-items: center; gap: .4rem; min-width: 0; }
/* 英文全名：一行放不下才省略（上方細節區塊有完整名稱） */
.cbf-item__en { min-width: 0; color: var(--sf-text-muted); overflow: hidden; text-overflow: ellipsis; }
.cbf-item__sub .sf-tree-chip { flex: 0 0 auto; }
/* 上方細節區塊：固定高度，換項目時版面不跳；往下捲時黏在固定的工具列＋分頁列＋下層分頁列下面 */
.cbf-info {
  position: sticky;
  top: calc(var(--sf-topbar-h, 52px) + var(--sf-tabs-h, 42px) + var(--cbf-subtabs-h, 0px) + .35rem);
  z-index: 5;
  box-shadow: 0 .3rem .6rem rgba(0, 0, 0, .3);
  display: flex; flex-wrap: wrap; align-items: center; gap: .25rem .6rem;
  min-height: 2.4rem; padding: .35rem .6rem;
  border: 1px solid var(--sf-border); border-radius: 6px; background: var(--sf-panel);
}
.cbf-info__muted { color: var(--sf-text-muted); }
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
