<!--
  UEX 價格地點列表（aUEC）：物品的購買／收購、船艦的遊戲內購買／租船共用這一個元件。
  ItemPriceDetail／VehiclePriceDetail 只是薄包裝（帶各自的 API 網址與區段），掛上去才查，查一次就好。
  後台用預設樣式（表格），玩家頁傳 player（蜂巢式下拉最內層 .sf-tree-leaf）。
  API 回應 data 是 { <section key>: [{ terminal, price, date_modified }] }。
-->
<template>
  <div>
    <div v-if="loading" class="small" :class="player ? 'sf-tree-info' : 'text-muted'">載入價格中…</div>
    <div v-else-if="failed" class="small text-warning">
      <i class="bi bi-exclamation-triangle me-1"></i>讀取價格失敗。
      <button type="button" class="btn btn-sm ms-1" :class="player ? 'btn-primary' : 'btn-link p-0'" @click="load">重試</button>
    </div>
    <template v-else>
      <div v-for="sec in sections" :key="sec.key" class="upl-section">
        <div :class="player ? 'sf-tree-info mb-1' : 'small fw-semibold mb-1'">
          {{ sec.label }}<template v-if="rowsOf(sec.key).length">（{{ rowsOf(sec.key).length }} 處）</template>
        </div>
        <div v-if="!rowsOf(sec.key).length" class="small" :class="player ? 'sf-tree-info' : 'text-muted'">
          {{ sec.empty }}
        </div>
        <template v-else-if="player">
          <div v-for="(r, i) in rowsOf(sec.key)" :key="i" class="sf-tree-leaf">
            <span class="sf-tree-title">{{ fmtAuec(r.price) }}</span>
            <span>{{ r.terminal.name }}</span>
            <span class="text-muted">{{ locationPathLabel(r.terminal.location) }}</span>
            <span v-if="r.date_modified" class="sf-tree-meta">更新 {{ fmtUexTime(r.date_modified) }}</span>
          </div>
        </template>
        <table v-else class="table table-sm mb-2 upl-table">
          <tbody>
            <tr v-for="(r, i) in rowsOf(sec.key)" :key="i">
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
import { onMounted, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { fmtAuec, fmtUexTime, loadLocationZh, locationPathLabel } from '@/utils/uexCommodity'

const props = defineProps({
  /** 價格 API 路徑（例如 /item/<uuid>/uex-prices） */
  url: { type: String, required: true },
  /** 要顯示的區段 [{ key, label, empty }]，key 對到回應 data 的欄位 */
  sections: { type: Array, required: true },
  /** 帶身分的 fetch（後台 apiFetch、玩家頁 playerFetch） */
  fetcher: { type: Function, default: apiFetch },
  /** 玩家頁樣式（蜂巢式下拉最內層） */
  player: { type: Boolean, default: false },
})

const data = ref({})
const loading = ref(false)
const failed = ref(false)

function rowsOf(key) {
  return data.value[key] || []
}

async function load() {
  loading.value = true
  failed.value = false
  const res = await props.fetcher(props.url)
  const body = res?.ok ? await res.json().catch(() => null) : null
  loading.value = false
  if (!body?.success) {
    failed.value = true
    return
  }
  const out = {}
  for (const sec of props.sections) out[sec.key] = body.data?.[sec.key] || []
  data.value = out
  loadLocationZh(Object.values(out).flat().flatMap(r => r.terminal?.location || []))
}

onMounted(load)
watch(() => props.url, load)
</script>

<style scoped>
.upl-section + .upl-section { margin-top: .5rem; }
.upl-table td { font-size: .875rem; }
</style>
