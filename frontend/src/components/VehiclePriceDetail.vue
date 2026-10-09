<!--
  某艘船的遊戲內購買地點／租船地點（UEX，aUEC），各自由便宜到貴。

  GET /item/vehicles/<uuid>/prices（src/models/uex_vehicle_price.py 的 prices_for）。
  兩個地方用：後台「艦船」列表展開（預設樣式）、玩家頁「艦隊 › 船艦資料」展開（player：
  蜂巢式下拉最內層 .sf-tree-leaf）。掛上去才查，查一次就好。
  中文地點：utils/uexCommodity.js（資料庫 sc_translations）。
-->
<template>
  <div>
    <div v-if="loading" class="small" :class="player ? 'sf-tree-info' : 'text-muted'">載入價格中…</div>
    <div v-else-if="failed" class="small text-warning">
      <i class="bi bi-exclamation-triangle me-1"></i>讀取價格失敗。
      <button type="button" class="btn btn-sm ms-1" :class="player ? 'btn-primary' : 'btn-link p-0'" @click="load">重新整理</button>
    </div>
    <template v-else>
      <div v-for="sec in SECTIONS" :key="sec.key" class="vpd-section">
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
            <span class="sf-tree-meta">更新 {{ fmtUexTime(r.date_modified) }}</span>
          </div>
        </template>
        <table v-else class="table table-sm mb-2 vpd-table">
          <tbody>
            <tr v-for="(r, i) in data[sec.key]" :key="i">
              <td class="text-end text-nowrap" style="width: 9rem">{{ fmtAuec(r.price) }}</td>
              <td>{{ r.terminal.name }}</td>
              <td class="text-muted">{{ r.terminal.location.join(' › ') }}</td>
              <td class="text-muted text-nowrap text-end">{{ fmtUexTime(r.date_modified) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { apiFetch } from '@/api'
import { fmtAuec, fmtUexTime, loadLocationZh, locationPathLabel } from '@/utils/uexCommodity'

const props = defineProps({
  vehicleUuid: { type: String, required: true },
  /** 帶身分的 fetch（後台 apiFetch、玩家頁 playerFetch） */
  fetcher: { type: Function, default: apiFetch },
  /** 玩家頁樣式（蜂巢式下拉最內層） */
  player: { type: Boolean, default: false },
})

const SECTIONS = [
  { key: 'purchase', label: '遊戲內購買', empty: '沒有購買地點資料' },
  { key: 'rental', label: '租船', empty: '沒有租船地點資料' },
]

const data = ref({ purchase: [], rental: [] })
const loading = ref(false)
const failed = ref(false)

async function load() {
  loading.value = true
  failed.value = false
  const res = await props.fetcher(`/item/vehicles/${encodeURIComponent(props.vehicleUuid)}/prices`)
  const body = res?.ok ? await res.json().catch(() => null) : null
  loading.value = false
  if (!body?.success) {
    failed.value = true
    return
  }
  data.value = { purchase: body.data?.purchase || [], rental: body.data?.rental || [] }
  loadLocationZh([...data.value.purchase, ...data.value.rental].flatMap(r => r.terminal.location))
}

onMounted(load)
</script>

<style scoped>
.vpd-section + .vpd-section { margin-top: .5rem; }
.vpd-table td { font-size: .875rem; }
</style>
