<!-- 藍圖管理列表（規格書第 5 節） -->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold"><i class="bi bi-journal-bookmark me-2 text-primary"></i>藍圖 Blueprint</h5>
      <button class="btn btn-primary btn-sm" @click="bpModalRef.open()">
        <i class="bi bi-plus-lg me-1"></i>新增藍圖
      </button>
    </div>

    <Transition name="alert-slide">
      <div v-if="msg" :class="`alert alert-${msgType} py-2 mb-3`">{{ msg }}</div>
    </Transition>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">Blueprint 名稱</th>
                <th>取得方式</th>
                <th>取得地點</th>
                <th>取得玩家</th>
                <th>狀態</th>
                <th style="width:140px" class="pe-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="6" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!blueprints.length">
                <td colspan="6" class="text-center py-4 text-muted">尚無藍圖資料</td>
              </tr>
              <template v-else>
                <tr v-for="bp in blueprints" :key="bp._id">
                  <td class="ps-3 fw-semibold">{{ bp.name }}</td>
                  <td class="small">{{ bp.acquisition_method || '未知' }}</td>
                  <td class="small">{{ bp.acquisition_location || '—' }}</td>
                  <td class="small">{{ playerName(bp.player_id) }}</td>
                  <td><StatusBadge :status="bp.unlock_status" /></td>
                  <td class="pe-3">
                    <button class="btn btn-sm btn-outline-secondary me-1" @click="bpModalRef.open(bp)">
                      <i class="bi bi-pencil"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger" @click="handleDelete(bp)">
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

    <BlueprintFormModal ref="bpModalRef" :players="playerStore.players" @saved="load" />
    <ConfirmModal       ref="confirmModalRef" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { usePlayerStore } from '@/stores/player'
import { blueprintApi } from '@/api'
import StatusBadge         from '@/components/StatusBadge.vue'
import BlueprintFormModal   from '@/components/BlueprintFormModal.vue'
import ConfirmModal          from '@/components/ConfirmModal.vue'

const playerStore = usePlayerStore()

const blueprints = ref([])
const loading     = ref(false)
const bpModalRef       = ref(null)
const confirmModalRef  = ref(null)
const msg = ref(''); const msgType = ref('success')

function playerName(id) {
  return id ? (playerStore.byId(id)?.player_name || '') : '—'
}

function flash(text, type = 'danger') {
  msg.value = text; msgType.value = type
  setTimeout(() => { msg.value = '' }, 3000)
}

async function load() {
  loading.value = true
  const res = await blueprintApi.list()
  if (res) { const d = await res.json(); blueprints.value = d.data || [] }
  loading.value = false
}

async function handleDelete(bp) {
  const ok = await confirmModalRef.value.confirm(
    `確定要刪除藍圖 <strong>${escHtml(bp.name)}</strong>？`
  )
  if (!ok) return
  const res = await blueprintApi.remove(bp._id)
  if (!res) return
  const data = await res.json()
  if (data.success) load()
  else flash(data.message || '刪除失敗')
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

onMounted(async () => {
  await load()
  if (!playerStore.players.length) await playerStore.load()
})
</script>

<style scoped>
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>
