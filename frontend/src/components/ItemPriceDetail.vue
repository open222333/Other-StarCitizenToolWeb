<!--
  某個物品在哪裡買得到／哪裡收（UEX，aUEC）：購買由便宜到貴、收購由高到低。

  GET /item/<uuid>/uex-prices（src/models/uex_item_price.py 的 prices_for）。UEX 沒有這個物品時
  退回 Wiki 內嵌的購買價（source=wiki，只有購買、沒有地點路徑）。
  兩個地方用：後台「物品」列表展開（預設樣式）、玩家頁「倉庫 › 物品資料」展開（player：.sf-tree-leaf）。
  掛上去才查，查一次就好。
-->
<template>
  <div>
    <div v-if="loading" class="small" :class="player ? 'sf-tree-info' : 'text-muted'">載入價格中…</div>
    <div v-else-if="failed" class="small text-warning">
      <i class="bi bi-exclamation-triangle me-1"></i>讀取價格失敗。
      <button type="button" class="btn btn-sm ms-1" :class="player ? 'btn-primary' : 'btn-link p-0'" @click="load">重新整理</button>
    </div>
    <template v-else>
      <div v-for="sec in sections" :key="sec.key" class="ipd-section">
        <div :class="player ? 'sf-tree-info mb-1' : 'small fw-semibold mb-1'">
          {{ sec.label }}<template v-if="data[sec.key].length">（{{ data[sec.key].length }} 處）</template>
        </div>
        <div v-if="!data[sec.key].length" class="small" :class="player ? 'sf-tree-info' : 'text-muted'">
          {{ sec.empty }}
        </div>
        <template v-else-if="player">
          <div v-for="(r, i) in data[sec.key]" :key="i" class="sf-tree-leaf">
            <span class="sf-tree-title">{{ fmtAuec(r.price) }}</span>
            <span>{{ r.terminal.name }}</span>
            <span class="text-muted">{{ locationPathLabel(r.terminal.location) }}</span>
            <span v-if="r.date_modified" class="sf-tree-meta">更新 {{ fmtUexTime(r.date_modified) }}</span>
          </div>
        </template>
        <table v-else class="table table-sm mb-2 ipd-table">
          <tbody>
            <tr v-for="(r, i) in data[sec.key]" :key="i">
              <td class="text-end text-nowrap" style="width: 9rem">{{ fmtAuec(r.price) }}</td>
              <td>{{ r.terminal.name }}</td>
              <td class="text-muted">{{ r.terminal.location.join(' › ') }}</td>
              <td class="text-muted text-nowrap text-end">{{ r.date_modified ? fmtUexTime(r.date_modified) : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '@/api'
import { fmtAuec, fmtUexTime, loadLocationZh, locationPathLabel } from '@/utils/uexCommodity'

const props = defineProps({
  itemUuid: { type: String, required: true },
  /** 帶身分的 fetch（後台 apiFetch、玩家頁 playerFetch） */
  fetcher: { type: Function, default: apiFetch },
  /** 玩家頁樣式（蜂巢式下拉最內層） */
  player: { type: Boolean, default: false },
  /** 只顯示購買地點（玩家頁不需要收購） */
  buyOnly: { type: Boolean, default: false },
})

const SECTIONS = [
  { key: 'buy', label: '購買地點', empty: '沒有購買地點資料' },
  { key: 'sell', label: '收購地點', empty: '沒有收購地點資料' },
]

const sections = computed(() => (props.buyOnly ? SECTIONS.slice(0, 1) : SECTIONS))
const data = ref({ buy: [], sell: [] })
const loading = ref(false)
const failed = ref(false)

async function load() {
  loading.value = true
  failed.value = false
  const res = await props.fetcher(`/item/${encodeURIComponent(props.itemUuid)}/uex-prices`)
  const body = res?.ok ? await res.json().catch(() => null) : null
  loading.value = false
  if (!body?.success) {
    failed.value = true
    return
  }
  data.value = { buy: body.data?.buy || [], sell: body.data?.sell || [] }
  loadLocationZh([...data.value.buy, ...data.value.sell].flatMap(r => r.terminal.location))
}

onMounted(load)
</script>

<style scoped>
.ipd-section + .ipd-section { margin-top: .5rem; }
.ipd-table td { font-size: .875rem; }
</style>
