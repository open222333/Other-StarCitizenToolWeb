<!--
  後台「艦船 › 玩家擁有艦船」：玩家在玩家頁登記的船／載具（fleet），每筆登記一列，唯讀。
  後端 GET /item/fleet（src/models/fleet.py 的 Fleet.admin_list）分頁／篩選／排序；
  已刪除的登記與已刪除的玩家不列，不顯示玩家自己寫的備註。
  第一次切到這個分頁才載入（active prop）。
-->
<template>
  <div>
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm" style="max-width: 14rem"
            placeholder="搜尋船名（中英文）..." aria-label="搜尋船名" @change="reload(0)">
          <input v-model="player" type="search" class="form-control form-control-sm" style="max-width: 14rem"
            placeholder="搜尋玩家（遊戲ID／暱稱）..." aria-label="搜尋玩家" @change="reload(0)">
          <select v-model="sort" class="form-select form-select-sm w-auto" aria-label="排序" @change="reload(0)">
            <option value="name">依船名</option>
            <option value="player">依玩家</option>
            <option value="quantity">依數量</option>
            <option value="updated">最近更新</option>
          </select>
          <button v-if="query || player" type="button" class="btn btn-sm btn-link" @click="resetFilters">
            清除全部篩選
          </button>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0 small">
            <thead class="table-light">
              <tr>
                <th class="ps-3">船艦</th>
                <th>玩家</th>
                <th class="text-end">數量</th>
                <th>製造商</th>
                <th>角色</th>
                <th class="text-end">尺寸</th>
                <th>配件網址</th>
                <th class="pe-3 text-nowrap">更新時間</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="8" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="8" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取玩家艦船失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="8" class="text-center py-4 text-muted">
                  {{ query || player ? '沒有符合篩選條件的登記。' : '還沒有玩家登記船艦' }}
                </td>
              </tr>
              <template v-else>
              <tr v-for="r in rows" :key="r._id">
                <td class="ps-3">
                  <span class="fw-semibold">{{ r.name }}</span>
                  <span v-if="r.vehicle?.name_zh" class="ms-1">（{{ r.vehicle.name_zh }}）</span>
                  <span v-if="r.vehicle?.system_note" class="badge bg-info text-dark ms-1" title="系統說明：同名變體的區別">{{ r.vehicle.system_note }}</span>
                  <span v-if="r.vehicle && r.vehicle.is_current === false" class="badge text-bg-secondary ms-1">已下架</span>
                  <span v-if="!r.vehicle" class="badge text-bg-warning ms-1">主檔查不到</span>
                </td>
                <td>
                  <RouterLink v-if="r.player?._id" :to="`/players/${r.player._id}`">{{ playerLabel(r.player) }}</RouterLink>
                  <span v-else class="text-muted">—</span>
                </td>
                <td class="text-end">{{ r.quantity ?? '—' }}</td>
                <td>{{ r.vehicle?.manufacturer_name || r.vehicle?.manufacturer_code || '—' }}</td>
                <td>{{ r.vehicle?.role_zh ? `${r.vehicle.role_zh}（${r.vehicle.role}）` : (r.vehicle?.role || '—') }}</td>
                <td class="text-end">{{ r.vehicle?.size_class ?? '—' }}</td>
                <td>
                  <VehicleLoadoutLinks v-if="r.loadout_links?.length" :links="r.loadout_links" />
                  <span v-else class="text-muted">—</span>
                </td>
                <td class="pe-3 text-nowrap text-muted">{{ fmtTime(r.updated_at || r.created_at) }}</td>
              </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-2">
      <div class="small text-muted">
        共 {{ total }} 筆<span v-if="total"> · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</span>
      </div>
      <div class="btn-group btn-group-sm">
        <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading"
          @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-outline-secondary" :disabled="offset + limit >= total || loading"
          @click="reload(offset + limit)">下一頁</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { vehicleApi } from '@/api'
import VehicleLoadoutLinks from '@/components/VehicleLoadoutLinks.vue'

const props = defineProps({ active: { type: Boolean, default: false } })

const limit = 50
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const loaded = ref(false)

const query = ref('')
const player = ref('')
const sort = ref('name')

async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  const res = await vehicleApi.playerFleet({
    q: query.value.trim(), player: player.value.trim(), sort: sort.value, limit, offset: newOffset,
  })
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (body?.success) {
    rows.value = body.data || []
    total.value = body.total || 0
  } else {
    rows.value = []
    total.value = 0
    loadFailed.value = true
  }
  loaded.value = true
  loading.value = false
}

function resetFilters() {
  query.value = ''
  player.value = ''
  reload(0)
}

function playerLabel(p) {
  const name = p.nickname || p.player_name
  return name && name !== p.star_citizen_id ? `${name}（${p.star_citizen_id}）` : (p.star_citizen_id || '—')
}

function fmtTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-TW', { hour12: false })
}

watch(() => props.active, (on) => { if (on && !loaded.value) reload(0) }, { immediate: true })
</script>
