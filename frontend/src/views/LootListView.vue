<!-- 戰利品管理列表（規格書第 6、12 節） -->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
      <h5 class="mb-0 fw-bold"><i class="bi bi-bag me-2 text-primary"></i>戰利品</h5>
      <div class="d-flex gap-2">
        <SearchBox v-model="store.keyword" placeholder="搜尋物品名稱 / 地點..." />
        <button class="btn btn-primary btn-sm" @click="openCreate">
          <i class="bi bi-plus-lg me-1"></i>新增戰利品
        </button>
      </div>
    </div>

    <FilterBar v-model="store.filters" :options="filterOptions" @reset="store.resetFilters" />

    <Transition name="alert-slide">
      <div v-if="msg" :class="`alert alert-${msgType} py-2 mb-3`">{{ msg }}</div>
    </Transition>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">物品</th>
                <th>類型</th>
                <th>稀有度</th>
                <th>取得地點</th>
                <th>取得玩家</th>
                <th>目前持有人</th>
                <th>狀態</th>
                <th style="width:140px" class="pe-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="store.loading">
                <td colspan="8" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!store.filtered.length">
                <td colspan="8" class="text-center py-4 text-muted">沒有符合條件的戰利品</td>
              </tr>
              <template v-else>
                <tr v-for="item in store.filtered" :key="item._id">
                  <td class="ps-3 fw-semibold">{{ item.name }}</td>
                  <td class="small">{{ item.category || '未分類' }}</td>
                  <td><RarityTag :rarity="item.rarity" /></td>
                  <td class="small">{{ item.location || '—' }}</td>
                  <td class="small">{{ playerName(item.obtained_by) }}</td>
                  <td class="small">{{ playerName(item.current_owner) || '團隊倉庫' }}</td>
                  <td><StatusBadge :status="item.status" /></td>
                  <td class="pe-3">
                    <button class="btn btn-sm btn-outline-secondary me-1" @click="openEdit(item)">
                      <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" @click="handleDelete(item)">
                      <i class="bi bi-trash"></i>
                    </button>
                  </td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <LootFormModal ref="lootModalRef" :players="playerStore.players" @saved="onSaved" />
    <ConfirmModal  ref="confirmModalRef" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useLootStore } from '@/stores/loot'
import { usePlayerStore } from '@/stores/player'
import { lootApi } from '@/api'
import SearchBox      from '@/components/SearchBox.vue'
import FilterBar       from '@/components/FilterBar.vue'
import RarityTag        from '@/components/RarityTag.vue'
import StatusBadge       from '@/components/StatusBadge.vue'
import LootFormModal      from '@/components/LootFormModal.vue'
import ConfirmModal        from '@/components/ConfirmModal.vue'

const store       = useLootStore()
const playerStore = usePlayerStore()

const lootModalRef    = ref(null)
const confirmModalRef = ref(null)
const msg = ref(''); const msgType = ref('success')

// 篩選下拉選單選項：從目前已載入的資料動態萃取（避免另開一組靜態設定檔）
const filterOptions = computed(() => ({
  categories: [...new Set(store.items.map(i => i.category).filter(Boolean))],
  rarities:   ['Common', 'Uncommon', 'Rare', 'Very Rare', 'Epic', 'Legendary', 'Unknown'],
  locations:  [...new Set(store.items.map(i => i.location).filter(Boolean))],
  statuses: [
    { value: 'in_stock',    label: '📦 庫存中' },
    { value: 'held',        label: '🎒 玩家持有' },
    { value: 'equipped',    label: '🔫 已裝備' },
    { value: 'transferred', label: '🤝 已轉交' },
    { value: 'sold',        label: '💰 已出售' },
    { value: 'lost',        label: '💀 已遺失' },
    { value: 'consumed',    label: '🗑️ 已消耗' },
    { value: 'unconfirmed', label: '❓ 未確認' },
  ],
}))

function playerName(id) {
  return id ? (playerStore.byId(id)?.player_name || '') : ''
}

function flash(text, type = 'danger') {
  msg.value = text; msgType.value = type
  setTimeout(() => { msg.value = '' }, 3000)
}

function openCreate() { lootModalRef.value.open() }
function openEdit(item) { lootModalRef.value.open(item) }

async function onSaved() { await store.load() }

async function handleDelete(item) {
  const ok = await confirmModalRef.value.confirm(
    `確定要刪除戰利品 <strong>${escHtml(item.name)}</strong>？`
  )
  if (!ok) return
  const res = await lootApi.remove(item._id)
  if (!res) return
  const data = await res.json()
  if (data.success) store.load()
  else flash(data.message || '刪除失敗')
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

onMounted(async () => {
  await store.load()
  if (!playerStore.players.length) await playerStore.load()
})
</script>

<style scoped>
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>
