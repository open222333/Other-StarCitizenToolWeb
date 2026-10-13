<!--
  玩家頁「倉庫 › 物品資料」：瀏覽物品主檔（item_master），唯讀。

  篩選用「倉庫」分頁頂端的共用搜尋卡（MyPlayerView 傳進 filters：{ q, types, buyable }），名稱＋類型跟
  物品庫存同一組條件；buyable（「只看買得到」勾選，物品資料展開時才出現在搜尋卡上）＝ acquire=buy。
  資料是 GET /item/?with_prices=1（後端分頁，玩家只看得到「玩家頁面顯示」的物品），每筆帶 uex_price
  （列表只顯示最低購買價）。點名稱展開詳細資料（components/ItemDetail.vue：基本欄位、遊戲內說明的數值、
  購買地點；玩家頁不顯示收購）。
  樣式用蜂巢式下拉（scifi-theme.css 的 .sf-tree-*），比照 VehicleDataBrowser。
-->
<template>
  <div>
    <div v-if="loading" class="text-muted small">載入中…</div>
    <div v-else-if="loadFailed" class="small">
      <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取物品資料失敗。</span>
      <button type="button" class="btn btn-sm btn-primary ms-1" @click="reload(offset)">重新整理</button>
    </div>
    <div v-else-if="!rows.length" class="text-muted small">沒有符合條件的物品。</div>
    <template v-else>
      <div v-for="it in rows" :key="it._id" class="idb-item">
        <div class="idb-row">
          <button type="button" class="sf-tree-row sf-tree-row--ship idb-main"
            :aria-expanded="openId === it._id ? 'true' : 'false'" @click="openId = openId === it._id ? '' : it._id">
            <i class="bi" :class="openId === it._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
            <span class="idb-name">
              <span class="sf-tree-title">{{ it.name_zh || it.name }}</span>
              <span v-if="it.name_zh" class="text-muted ms-1">{{ it.name }}</span>
            </span>
            <span class="idb-attrs">
              <span>{{ [it.type, it.sub_type].filter(Boolean).join(' › ') || '—' }}</span>
              <span v-if="it.size !== null && it.size !== undefined">S{{ it.size }}</span>
              <span v-if="it.grade !== null && it.grade !== undefined">等級 {{ it.grade }}</span>
              <span v-if="it.manufacturer_name || it.manufacturer_code">{{ it.manufacturer_name || it.manufacturer_code }}</span>
            </span>
            <span class="sf-tree-meta">
              <template v-if="it.uex_price?.buy_min">{{ fmtAuec(it.uex_price.buy_min) }} 起</template>
            </span>
          </button>
        </div>
        <div v-if="openId === it._id" class="sf-tree-level">
          <ItemDetail :item="it" :fetcher="fetcher" player buy-only />
        </div>
      </div>
      <div class="d-flex align-items-center justify-content-between mt-2">
        <span class="small text-muted">共 {{ total }} 種 · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</span>
        <div class="btn-group">
          <button class="btn btn-sm btn-primary" :disabled="offset === 0 || loading"
            @click="reload(Math.max(0, offset - limit))">上一頁</button>
          <button class="btn btn-sm btn-primary" :disabled="offset + limit >= total || loading"
            @click="reload(offset + limit)">下一頁</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import ItemDetail from '@/components/ItemDetail.vue'
import { fmtAuec } from '@/utils/uexCommodity'

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
  openId.value = ''
}

let loaded = false
let timer = null
watch(() => props.active, (v) => {
  if (!v || loaded) return
  loaded = true
  reload(0)
}, { immediate: true })
// 共用搜尋卡每打一個字就會換一次 filters，等停手 300ms 再查；還沒展開過就先不查
watch(() => props.filters, () => {
  if (!loaded) return
  clearTimeout(timer)
  timer = setTimeout(() => reload(0), 300)
}, { deep: true })
onBeforeUnmount(() => clearTimeout(timer))

defineExpose({ refresh: () => { if (loaded) reload(offset.value) } })
</script>

<style scoped>
.idb-item { margin-bottom: .4rem; }
.idb-row { display: flex; align-items: center; gap: .5rem; }
.idb-main { flex: 1 1 auto; min-width: 0; flex-wrap: wrap; }
.idb-name { min-width: 12rem; }
.idb-attrs { display: flex; flex-wrap: wrap; gap: .25rem .9rem; color: var(--sf-text); font-size: .95rem; }
</style>
