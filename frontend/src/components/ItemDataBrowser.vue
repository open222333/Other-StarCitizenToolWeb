<!--
  玩家頁「倉庫 › 物品資料」：瀏覽物品主檔（item_master），唯讀。

  篩選用「倉庫」分頁頂端的共用搜尋卡（MyPlayerView 傳進 filters：{ q, types, buyable, dismantlable, dismantle }），
  dismantlable（「只看可拆解」）＝ dismantlable=1、dismantle（拆解材料）＝ dismantle=…，兩者都會附 dismantle_hits；名稱＋類型跟
  物品庫存同一組條件；buyable（「只看買得到」勾選，物品資料展開時才出現在搜尋卡上）＝ acquire=buy。
  資料是 GET /item/?with_prices=1（後端分頁，玩家只看得到「玩家頁面顯示」的物品），每筆帶 uex_price
  （列表只顯示最低購買價）。點名稱展開詳細資料（components/ItemDetail.vue：基本欄位、遊戲內說明的數值、
  購買地點；玩家頁不顯示收購）。
  樣式用蜂巢式下拉（scifi-theme.css 的 .sf-tree-*），比照 VehicleDataBrowser。
-->
<template>
  <!-- 換頁載入中保留舊的列（只變淡），不讓頁面瞬間變短；變短會讓瀏覽器把畫面捲到下面去 -->
  <div ref="rootEl" class="sf-scroll-anchor" :class="{ 'sf-list-loading': loading }">
    <div v-if="loading && !rows.length" class="text-muted small">載入中…</div>
    <div v-else-if="loadFailed" class="small">
      <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取物品資料失敗。</span>
      <button type="button" class="btn btn-sm btn-primary ms-1" @click="reload(offset)">重新整理</button>
    </div>
    <div v-else-if="!rows.length" class="text-muted small">沒有符合條件的物品。</div>
    <template v-else>
      <!-- 欄位名稱＋排序（後端排序）；拆解回收欄只有用「拆解材料」或「只看可拆解」篩選時才出現，
           依所選材料的回收量（SCU 加總）排序 -->
      <div class="idb-list" :style="{ '--sf-tree-cols': gridCols }">
      <SfTreeHead :sort="sort" :columns="columns" />
      <div v-for="it in rows" :key="it._id" class="idb-item">
        <div class="idb-row">
          <button type="button" class="sf-tree-row sf-tree-row--ship sf-tree-row--cols idb-main"
            :aria-expanded="openId === it._id ? 'true' : 'false'" @click="openId = openId === it._id ? '' : it._id">
            <span class="sf-tree-cell idb-name">
              <i class="bi me-1" :class="openId === it._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
              <span class="sf-tree-title">{{ it.name_zh || it.name }}</span>
              <span v-if="it.name_zh" class="text-muted ms-1">{{ it.name }}</span>
              <!-- 拆解會回收的材料（有選材料時只列那幾種；後端 dismantle_hits） -->
              <span v-if="it.dismantle_hits?.length" class="d-block small text-muted">
                拆解回收：{{ dismantleHits(it.dismantle_hits, filters?.dismantle).join('、') }}
              </span>
            </span>
            <span class="sf-tree-cell sf-tree-cell--opt">{{ itemTypeLabel(it.type, it.sub_type) || '—' }}</span>
            <span class="sf-tree-cell sf-tree-cell--opt">{{ it.size !== null && it.size !== undefined ? `S${it.size}` : '—' }}</span>
            <span class="sf-tree-cell sf-tree-cell--opt">{{ it.grade ?? '—' }}</span>
            <span class="sf-tree-cell sf-tree-cell--opt">{{ it.manufacturer_name || it.manufacturer_code || '—' }}</span>
            <span v-if="showDismantle" class="sf-tree-cell sf-tree-cell--end">{{ fmtScu(dismantleScu(it)) }}</span>
            <span class="sf-tree-cell sf-tree-cell--end" :class="{ 'sf-tree-cell--opt': showDismantle }">
              <template v-if="it.uex_price?.buy_min">{{ fmtAuec(it.uex_price.buy_min) }} 起</template>
              <template v-else>—</template>
            </span>
          </button>
        </div>
        <div v-if="openId === it._id" class="sf-tree-level">
          <ItemDetail :item="it" :fetcher="fetcher" player buy-only />
        </div>
      </div>
      </div>
      <div class="d-flex align-items-center justify-content-between mt-2">
        <span class="small text-muted">共 {{ total }} 種 · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</span>
        <div class="btn-group">
          <button class="btn btn-sm btn-primary" :disabled="offset === 0 || loading"
            @click="goPage(Math.max(0, offset - limit))">上一頁</button>
          <button class="btn btn-sm btn-primary" :disabled="offset + limit >= total || loading"
            @click="goPage(offset + limit)">下一頁</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SfTreeHead from '@/components/SfTreeHead.vue'
import { useTableSort } from '@/composables/useTableSort'
import { scrollToListTop } from '@/utils/scrollAnchor'
import ItemDetail from '@/components/ItemDetail.vue'
import { itemTypeLabel, loadItemTypeZh } from '@/utils/itemType'
import { fmtAuec } from '@/utils/uexCommodity'
import { dismantleHits } from '@/utils/blueprintMaterial'

const props = defineProps({
  /** 帶身分的 fetch（玩家頁傳 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /** 「倉庫」分頁頂端共用搜尋卡的條件：{ q, types, buyable } */
  filters: { type: Object, default: () => ({}) },
  /** 點開才載入（玩家頁用 v-show 一直掛著） */
  active: { type: Boolean, default: true },
})

const limit = 30
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const openId = ref('')

let seq = 0
async function reload(nextOffset = 0) {
  offset.value = Math.max(0, nextOffset)
  loading.value = true
  loadFailed.value = false
  const mine = ++seq
  const f = props.filters || {}
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset.value), with_prices: '1' })
  if (f.q) params.set('q', f.q)
  ;(f.types || []).forEach(v => params.append('type', v))
  if (f.buyable) params.append('acquire', 'buy')
  ;(f.dismantle || []).forEach(v => params.append('dismantle', v))
  if (f.dismantlable) params.append('dismantlable', '1')
  for (const [k, v] of Object.entries(sort.params.value)) params.set(k, v)
  const res = await props.fetcher(`/item/?${params.toString()}`)
  const data = res ? await res.json().catch(() => null) : null
  if (mine !== seq) return
  loading.value = false
  if (!data?.success) {
    rows.value = []
    total.value = 0
    loadFailed.value = true
    return
  }
  rows.value = data.data || []
  total.value = data.total || 0
  loadItemTypeZh(rows.value.map(r => r.type), rows.value.map(r => r.sub_type))
  openId.value = ''
}

// ── 欄位名稱＋排序（後端排序：name／type／size／grade／manufacturer_name／dismantle_scu）──
const showDismantle = computed(() => !!(props.filters?.dismantle?.length || props.filters?.dismantlable))
const columns = computed(() => [
  { label: '物品', field: 'name' },
  { label: '類型', field: 'type', opt: true },
  { label: '尺寸', field: 'size', opt: true },
  { label: '等級', field: 'grade', opt: true },
  { label: '廠商', field: 'manufacturer_name', opt: true },
  ...(showDismantle.value ? [{ label: '拆解回收', field: 'dismantle_scu', end: true }] : []),
  { label: '最低價', end: true, opt: showDismantle.value },
])
const gridCols = computed(() => ['minmax(0, 1fr)', '9rem', '3.5rem', '3.5rem', '9rem',
  ...(showDismantle.value ? ['6.5rem'] : []), '9.5rem'].join(' '))
const sort = useTableSort(null, { onChange: () => reload(0) })

/** 這個物品拆解回收的 SCU（有選材料時只算那幾種，跟後端 dismantle_scu 排序一致） */
function dismantleScu(it) {
  const names = props.filters?.dismantle || []
  return (it.dismantle_hits || []).filter(h => !names.length || names.includes(h.name))
    .reduce((n, h) => n + (h.quantity_scu || 0), 0)
}
function fmtScu(v) {
  return v ? `${Number(v.toFixed(3))} SCU` : '—'
}

let loaded = false
let timer = null
watch(() => props.active, (v) => {
  if (!v || loaded) return
  loaded = true
  reload(0)
}, { immediate: true })
// 共用搜尋卡每打一個字就會換一次 filters，等停手 300ms 再查；還沒展開過就先不查
watch(() => props.filters, (f, old) => {
  // 剛開始用拆解材料篩選、還沒自己選排序時，預設依回收量由多到少；拆解欄消失時取消這個排序
  const nowDismantle = !!(f?.dismantle?.length || f?.dismantlable)
  if (nowDismantle && !sort.sortKey.value) { sort.sortKey.value = 'dismantle_scu'; sort.sortDir.value = 'desc' }
  if (!nowDismantle && sort.sortKey.value === 'dismantle_scu') sort.sortKey.value = ''
  if (!loaded) return
  clearTimeout(timer)
  timer = setTimeout(() => reload(0), 300)
}, { deep: true })
onBeforeUnmount(() => clearTimeout(timer))

defineExpose({ refresh: () => { if (loaded) reload(offset.value) } })

// 上一頁／下一頁：載入後把列表頂端捲回畫面（不然會停在最下方的分頁按鈕，見 utils/scrollAnchor.js）
const rootEl = ref(null)
async function goPage(newOffset) {
  await reload(newOffset)
  scrollToListTop(rootEl.value)
}
</script>

<style scoped>
.idb-item { margin-bottom: .4rem; }
.idb-row { display: flex; align-items: center; gap: .5rem; }
.idb-main { flex: 1 1 auto; min-width: 0; }
.idb-name { min-width: 0; }
.idb-attrs { display: flex; flex-wrap: wrap; gap: .25rem .9rem; color: var(--sf-text); font-size: .95rem; }
</style>
