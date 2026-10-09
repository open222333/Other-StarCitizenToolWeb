<!--
  後台「艦船 › 購買價格／租船價格」（唯讀）：UEX 載具價格表原始內容，方便檢查同步下來的資料。

  GET /item/uex-vehicle-prices?kind=purchase|rental（src/models/uex_vehicle_price.py 的 admin_list），
  後端分頁。每筆列出 UEX 的載具名稱與對應到的載具主檔；「對應主檔」是空的代表 uuid、名稱都對不上，
  這艘船的價格不會出現在艦船列表跟玩家頁。
-->
<template>
  <div>
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm" style="max-width: 16rem"
            placeholder="搜尋載具或終端名稱..." :aria-label="`搜尋${title}`">
          <select v-model="starSystem" class="form-select form-select-sm w-auto" aria-label="星系">
            <option value="">星系：全部</option>
            <option v-for="s in starSystems" :key="s" :value="s">{{ s }}</option>
          </select>
          <button v-if="query || starSystem" type="button" class="btn btn-sm btn-link"
            @click="query = ''; starSystem = ''">清除全部篩選</button>
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
                <th class="ps-3">UEX 載具</th>
                <th>對應主檔</th>
                <th class="text-end">{{ kind === 'rental' ? '租船價' : '購買價' }}</th>
                <th>交易終端</th>
                <th>地點</th>
                <th class="pe-3">更新時間</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="6" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="6" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取{{ title }}失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="6" class="text-center py-4 text-muted">
                  {{ query || starSystem ? '沒有符合條件的價格' : `還沒有${title}資料（到「資料同步排程」同步 UEX 價格）` }}
                </td>
              </tr>
              <tr v-for="r in rows" :key="r.id">
                <td class="ps-3 fw-semibold">{{ r.uex_vehicle.name || '—' }}</td>
                <td>
                  <span v-if="r.vehicle">{{ r.vehicle.name || r.vehicle.uuid }}</span>
                  <span v-else class="badge bg-warning-subtle text-warning-emphasis">對不到</span>
                </td>
                <td class="small text-end text-nowrap">{{ fmtAuec(r.price) }}</td>
                <td>{{ r.terminal.name || '—' }}</td>
                <td class="small">{{ r.terminal.location.join(' › ') || '—' }}</td>
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
import { vehicleApi } from '@/api'
import { fmtAuec, fmtUexTime } from '@/utils/uexCommodity'

const props = defineProps({
  /** purchase（購買價格）／rental（租船價格） */
  kind: { type: String, required: true },
})
const title = computed(() => (props.kind === 'rental' ? '租船價格' : '購買價格'))

const limit = 50
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const starSystems = ref([])
const query = ref('')
const starSystem = ref('')

let seq = 0
async function reload(nextOffset = 0) {
  offset.value = nextOffset
  loading.value = true
  loadFailed.value = false
  const mine = ++seq
  const res = await vehicleApi.uexPrices({
    kind: props.kind, q: query.value.trim(), star_system: starSystem.value, limit, offset: nextOffset,
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
}

let timer = null
watch(query, () => {
  clearTimeout(timer)
  timer = setTimeout(() => reload(0), 300)
})
watch(starSystem, () => reload(0))
watch(() => props.kind, () => reload(0))
onBeforeUnmount(() => clearTimeout(timer))
onMounted(() => reload(0))
</script>
