<!--
  玩家詳細頁（規格書第 4.2 節）。

  這一頁原本接的是 `/loot/*` —— 那個後端從來沒有實作過（app/ 下沒有 loot
  藍圖），所以「玩家取得紀錄」永遠是空表格、上面四個統計方塊有三個永遠是 0，
  而且因為錯誤被當成空狀態渲染，看起來像「這個玩家還沒有東西」而不是壞掉。

  現在改接實際存在的兩支 API：
    - GET /inventory/?owner_type=player&player=<遊戲ID>  → 他的個人庫存
    - GET /blueprint/?player_id=<玩家_id>                 → 他登記的藍圖
  個人庫存是用 star_citizen_id（RSI handle）對應的，不是玩家文件的 _id。
-->
<template>
  <div v-if="player">
    <RouterLink to="/players" class="btn btn-sm btn-outline-secondary mb-3">
      <i class="bi bi-arrow-left me-1"></i>返回玩家列表
    </RouterLink>

    <div class="card shadow-sm border-0 mb-4">
      <div class="card-body">
        <h5 class="fw-bold mb-3">
          <i class="bi bi-person-badge me-2 text-primary"></i>{{ player.player_name }}
          <span v-if="player.deleted_at" class="badge bg-secondary ms-1">已移除</span>
        </h5>
        <div class="row small">
          <div class="col-sm-4 mb-2"><span class="text-muted">Star Citizen ID</span><div class="fw-semibold">{{ player.star_citizen_id }}</div></div>
          <div class="col-sm-4 mb-2"><span class="text-muted">Discord</span><div class="fw-semibold">{{ player.discord_name || '—' }}</div></div>
          <div class="col-sm-4 mb-2"><span class="text-muted">加入日期</span><div class="fw-semibold">{{ fmtDate(player.created_at) }}</div></div>
        </div>
        <div v-if="player.notes" class="mt-2 small text-muted">備註：{{ player.notes }}</div>
      </div>
    </div>

    <div class="row mb-4 g-3">
      <div class="col-6 col-md-4" v-for="stat in stats" :key="stat.label">
        <div class="card shadow-sm border-0 text-center py-3">
          <div class="fs-4">{{ stat.icon }}</div>
          <div class="fw-bold fs-5">{{ stat.count }}</div>
          <div class="small text-muted">{{ stat.label }}</div>
        </div>
      </div>
    </div>

    <h6 class="fw-bold mb-3">
      <i class="bi bi-box-seam me-2 text-secondary"></i>個人庫存
      <span v-if="stockTotal > stock.length" class="small text-muted fw-normal">
        （顯示前 {{ stock.length }} 筆，共 {{ stockTotal }} 筆）
      </span>
    </h6>

    <!-- 錯誤要跟空狀態分開顯示：後端壞掉被渲染成「尚無資料」是最容易
         誤判的失敗模式，這一頁先前就是這樣（見檔頭說明）。 -->
    <div v-if="stockError" class="alert alert-warning py-2">{{ stockError }}</div>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">物品</th>
                <th>位置</th>
                <th class="text-end">數量</th>
                <th class="text-end pe-3">體積 (SCU)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loadingStock">
                <td colspan="4" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中…
                </td>
              </tr>
              <tr v-else-if="!stock.length && !stockError">
                <td colspan="4" class="text-center py-4 text-muted">這位玩家目前沒有登記任何庫存</td>
              </tr>
              <tr v-else v-for="row in stock" :key="`${row.item_id}-${row.location}-${row.container}`">
                <td class="ps-3 fw-semibold">
                  {{ row.item_name_zh || row.item_name }}
                  <span v-if="row.item_name_zh" class="small text-muted">{{ row.item_name }}</span>
                  <i v-if="row.item_retired" class="bi bi-exclamation-triangle text-warning ms-1"
                    title="這個物品已從遊戲主檔移除（舊 patch）"></i>
                </td>
                <td class="small">
                  {{ row.location || '—' }}
                  <span v-if="row.container" class="text-muted">／{{ row.container }}</span>
                </td>
                <td class="text-end">{{ row.quantity }}</td>
                <td class="text-end pe-3 text-muted small">{{ row.total_scu ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <div v-else-if="notFound" class="text-center text-muted py-5">
    <p class="mb-2">找不到這位玩家（可能已被移除）。</p>
    <RouterLink to="/players" class="btn btn-sm btn-outline-secondary">返回玩家列表</RouterLink>
  </div>

  <div v-else class="text-center text-muted py-5">
    <span class="spinner-border spinner-border-sm me-2"></span>載入玩家資料中...
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { usePlayerStore } from '@/stores/player'
import { inventoryApi, blueprintApi } from '@/api'

const route = useRoute()
const store = usePlayerStore()

const stock          = ref([])
const stockTotal     = ref(0)
const stockScu       = ref(0)
const loadingStock   = ref(false)
const stockError     = ref('')
const blueprintCount = ref(0)
const notFound       = ref(false)

const player = computed(() => store.byId(route.params.id))

const stats = computed(() => [
  { icon: '📘', label: '藍圖',     count: blueprintCount.value },
  { icon: '📦', label: '庫存品項', count: stockTotal.value },
  { icon: '⚖️', label: '總體積 (SCU)', count: stockScu.value },
])

function fmtDate(d) { return d ? new Date(d).toLocaleDateString('zh-TW') : '—' }

async function loadStock(scid) {
  loadingStock.value = true
  stockError.value = ''
  // limit 100：這一頁是「概觀」，要細查有專門的庫存頁可以篩選
  const res = await inventoryApi.list({ owner_type: 'player', player: scid, limit: 100 })
  const data = res ? await res.json().catch(() => null) : null
  if (data?.success) {
    stock.value      = data.data || []
    stockTotal.value = data.total ?? stock.value.length
    stockScu.value   = data.summary?.total_scu ?? 0
  } else {
    stockError.value = data?.message || '讀取庫存失敗，請稍後再試'
  }
  loadingStock.value = false
}

async function loadBlueprintCount() {
  const res = await blueprintApi.list({ player_id: route.params.id })
  const data = res ? await res.json().catch(() => null) : null
  if (data?.success) blueprintCount.value = (data.data || []).length
}

onMounted(async () => {
  if (!store.players.length) await store.load()
  // 已移除的玩家也要看得到（後台可能正在確認要不要還原）
  if (!store.byId(route.params.id) && !store.includeDeleted) await store.load(true)

  const current = store.byId(route.params.id)
  if (!current) { notFound.value = true; return }

  await Promise.all([loadStock(current.star_citizen_id), loadBlueprintCount()])
})
</script>
