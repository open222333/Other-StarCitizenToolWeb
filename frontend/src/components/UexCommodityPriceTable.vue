<!--
  後台「商品資料庫 › 商品價格」（唯讀）：UEX 商品在各交易終端的買賣價（uex_commodities_prices）。

  一筆＝「某商品 × 某交易終端」，幾千筆，走後端分頁／篩選
  （GET /mining/uex-commodity-prices，src/models/uex_commodity_price.py 的 admin_list）。
  買價（price_buy）> 0 才代表這個終端買得到；玩家頁「查詢 › 商品購買地點」就是用這張表。
  價格是玩家回報到 UEX 的，新舊不一，看「更新時間」。
-->
<template>
  <div>
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm" style="max-width: 16rem"
            placeholder="搜尋商品縮寫、名稱或終端..." aria-label="搜尋商品價格">
          <select v-model="commodity" class="form-select form-select-sm w-auto" aria-label="商品">
            <option value="">商品：全部</option>
            <option v-for="c in commodityOptions" :key="c.id" :value="c.id">
              {{ c.code ? `${c.code} · ` : '' }}{{ c.name }}
            </option>
          </select>
          <select v-model="starSystem" class="form-select form-select-sm w-auto" aria-label="星系">
            <option value="">星系：全部</option>
            <option v-for="s in starSystems" :key="s" :value="s">{{ s }}</option>
          </select>
          <select v-model="side" class="form-select form-select-sm w-auto" aria-label="買賣">
            <option value="">買賣：全部</option>
            <option value="buy">只看買得到的</option>
            <option value="sell">只看能賣的</option>
          </select>
          <button v-if="hasActiveFilters" type="button" class="btn btn-sm btn-link" @click="resetFilters">
            清除全部篩選
          </button>
          <span class="ms-auto small text-muted">共 {{ total }} 筆</span>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">商品</th>
                <th>交易終端</th>
                <th>地點</th>
                <th class="text-end">買價</th>
                <th class="text-end">可買庫存</th>
                <th class="text-end">賣價</th>
                <th class="text-end">可收數量</th>
                <th>貨櫃（SCU）</th>
                <th class="pe-3">更新時間</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="9" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="9" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取商品價格失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="9" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合條件的價格' : '還沒有商品價格資料（到「資料同步排程」同步 UEX 價格）' }}
                </td>
              </tr>
              <tr v-for="r in rows" :key="r.id">
                <td class="ps-3">
                  <span v-if="r.commodity.code" class="badge bg-primary-subtle text-primary-emphasis font-monospace me-1">{{ r.commodity.code }}</span>
                  <span class="fw-semibold">{{ r.commodity.name }}</span>
                  <div v-if="commodityZh(r.commodity.name)" class="small text-muted">{{ commodityZh(r.commodity.name) }}</div>
                </td>
                <td>
                  {{ r.terminal.name || '—' }}
                  <span v-if="r.terminal.is_player_owned" class="badge bg-secondary-subtle text-secondary-emphasis ms-1">玩家</span>
                </td>
                <td class="small">{{ r.terminal.location.join(' › ') || '—' }}</td>
                <td class="small text-end text-nowrap">
                  {{ fmtAuec(r.price_buy) }}
                  <div v-if="r.price_buy_avg" class="text-muted">平均 {{ fmtAuec(r.price_buy_avg) }}</div>
                </td>
                <td class="small text-end text-nowrap">
                  {{ r.price_buy ? fmtScu(r.scu_buy) : '—' }}
                  <div v-if="r.price_buy && uexStatusLabel(r.status_buy)" class="text-muted">{{ uexStatusLabel(r.status_buy) }}</div>
                </td>
                <td class="small text-end text-nowrap">
                  {{ fmtAuec(r.price_sell) }}
                  <div v-if="r.price_sell_avg" class="text-muted">平均 {{ fmtAuec(r.price_sell_avg) }}</div>
                </td>
                <td class="small text-end text-nowrap">
                  {{ r.price_sell ? fmtScu(r.scu_sell_stock ?? r.scu_sell) : '—' }}
                  <div v-if="r.price_sell && uexStatusLabel(r.status_sell)" class="text-muted">{{ uexStatusLabel(r.status_sell) }}</div>
                </td>
                <td class="small">{{ r.container_sizes || '—' }}</td>
                <td class="small text-nowrap pe-3">{{ fmtUexTime(r.date_modified) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
      <div class="card-footer bg-transparent d-flex align-items-center justify-content-between">
        <span class="small text-muted">
          <template v-if="total">第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</template>
        </span>
        <div class="btn-group btn-group-sm">
          <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading"
            @click="reload(Math.max(0, offset - limit))">上一頁</button>
          <button class="btn btn-outline-secondary" :disabled="offset + limit >= total || loading"
            @click="reload(offset + limit)">下一頁</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { miningApi } from '@/api'
import {
  commodityZh, fmtAuec, fmtScu, fmtUexTime, loadCommodityZh, uexStatusLabel,
} from '@/utils/uexCommodity'

const limit = 50
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const starSystems = ref([])
const commodityOptions = ref([])

const query = ref('')
const commodity = ref('')
const starSystem = ref('')
const side = ref('')
const hasActiveFilters = computed(() => !!(query.value.trim() || commodity.value || starSystem.value || side.value))

let seq = 0
async function reload(nextOffset = 0) {
  offset.value = nextOffset
  loading.value = true
  loadFailed.value = false
  const mine = ++seq
  const res = await miningApi.uexCommodityPrices({
    q: query.value.trim(), commodity: commodity.value, star_system: starSystem.value, side: side.value,
    limit, offset: nextOffset,
  })
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (mine !== seq) return
  loading.value = false
  if (!body?.success) {
    rows.value = []
    total.value = 0
    loadFailed.value = true
    return
  }
  rows.value = body.data || []
  total.value = body.total || 0
  starSystems.value = body.star_systems || starSystems.value
  loadCommodityZh(rows.value.map(r => r.commodity.name))
}

function resetFilters() {
  query.value = ''
  commodity.value = ''
  starSystem.value = ''
  side.value = ''
}

async function loadCommodityOptions() {
  const res = await miningApi.uexCommodities()
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (body?.success) commodityOptions.value = body.data || []
}

let timer = null
watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(() => reload(0), 300)
})
watch([commodity, starSystem, side], () => reload(0))
onBeforeUnmount(() => clearTimeout(timer))

onMounted(() => {
  loadCommodityOptions()
  reload(0)
})
</script>
