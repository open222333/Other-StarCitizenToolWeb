<!-- 玩家詳細頁（規格書第 4.2 節） -->
<template>
  <div v-if="player">
    <RouterLink to="/players" class="btn btn-sm btn-outline-secondary mb-3">
      <i class="bi bi-arrow-left me-1"></i>返回玩家列表
    </RouterLink>

    <div class="card shadow-sm border-0 mb-4">
      <div class="card-body">
        <h5 class="fw-bold mb-3"><i class="bi bi-person-badge me-2 text-primary"></i>{{ player.player_name }}</h5>
        <div class="row small">
          <div class="col-sm-4 mb-2"><span class="text-muted">Star Citizen ID</span><div class="fw-semibold">{{ player.star_citizen_id }}</div></div>
          <div class="col-sm-4 mb-2"><span class="text-muted">Discord</span><div class="fw-semibold">{{ player.discord_name || '—' }}</div></div>
          <div class="col-sm-4 mb-2"><span class="text-muted">加入日期</span><div class="fw-semibold">{{ fmtDate(player.created_at) }}</div></div>
        </div>
        <div v-if="player.notes" class="mt-2 small text-muted">備註：{{ player.notes }}</div>
      </div>
    </div>

    <div class="row mb-4 g-3">
      <div class="col-6 col-md-3" v-for="stat in stats" :key="stat.label">
        <div class="card shadow-sm border-0 text-center py-3">
          <div class="fs-4">{{ stat.icon }}</div>
          <div class="fw-bold fs-5">{{ stat.count }}</div>
          <div class="small text-muted">{{ stat.label }}</div>
        </div>
      </div>
    </div>

    <h6 class="fw-bold mb-3"><i class="bi bi-clock-history me-2 text-secondary"></i>玩家取得紀錄</h6>
    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <table class="table table-hover align-middle mb-0">
          <thead class="table-light">
            <tr><th class="ps-3">日期</th><th>地點</th><th>物品</th><th>狀態</th></tr>
          </thead>
          <tbody>
            <tr v-if="loadingLoot"><td colspan="4" class="text-center py-4 text-muted">
              <span class="spinner-border spinner-border-sm me-2"></span>載入中...</td></tr>
            <tr v-else-if="!lootRecords.length"><td colspan="4" class="text-center py-4 text-muted">尚無取得紀錄</td></tr>
            <tr v-else v-for="l in lootRecords" :key="l._id">
              <td class="ps-3 small text-muted">{{ fmtDate(l.obtained_at) }}</td>
              <td class="small">{{ l.location || '—' }}</td>
              <td class="fw-semibold">{{ l.name }}</td>
              <td><StatusBadge :status="l.status" /></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <div v-else class="text-center text-muted py-5">
    <span class="spinner-border spinner-border-sm me-2"></span>載入玩家資料中...
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { usePlayerStore } from '@/stores/player'
import { lootApi, blueprintApi } from '@/api'
import StatusBadge from '@/components/StatusBadge.vue'

const route  = useRoute()
const store  = usePlayerStore()

const lootRecords    = ref([])
const loadingLoot     = ref(false)
const blueprintCount  = ref(0)

const player = computed(() => store.byId(route.params.id))

// 第 5 節「玩家收藏」統計：藍圖／戰利品／武器／裝備數量
const stats = computed(() => {
  const byCategory = (cats) => lootRecords.value.filter(l => cats.includes(l.category)).length
  return [
    { icon: '📘', label: '藍圖',  count: blueprintCount.value },
    { icon: '🎒', label: '戰利品', count: lootRecords.value.length },
    { icon: '🔫', label: '武器',  count: byCategory(['手槍','步槍','SMG','Shotgun','Sniper','重武器','近戰武器']) },
    { icon: '🛡️', label: '裝備',  count: byCategory(['頭盔','防彈衣','背包','防護服','醫療裝備','工具']) },
  ]
})

function fmtDate(d) { return d ? new Date(d).toLocaleDateString('zh-TW') : '—' }

async function loadLoot() {
  loadingLoot.value = true
  const res = await lootApi.list({ player: route.params.id })
  if (res) { const d = await res.json(); lootRecords.value = d.data || [] }
  loadingLoot.value = false
}

async function loadBlueprintCount() {
  const res = await blueprintApi.list({ player_id: route.params.id })
  if (res) { const d = await res.json(); blueprintCount.value = (d.data || []).length }
}

onMounted(async () => {
  if (!store.players.length) await store.load()
  await Promise.all([loadLoot(), loadBlueprintCount()])
})
</script>
