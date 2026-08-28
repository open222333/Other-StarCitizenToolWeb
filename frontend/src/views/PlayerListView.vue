<!-- 玩家管理列表（規格書第 4 節） -->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold"><i class="bi bi-people me-2 text-primary"></i>玩家</h5>
      <div class="d-flex gap-2">
        <SearchBox v-model="keyword" placeholder="搜尋玩家名稱 / SCID..." />
        <button class="btn btn-primary btn-sm" @click="playerModalRef.open()">
          <i class="bi bi-plus-lg me-1"></i>新增玩家
        </button>
      </div>
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
                <th class="ps-3">玩家名稱</th>
                <th>Star Citizen ID</th>
                <th>Discord</th>
                <th>加入日期</th>
                <th style="width:160px" class="pe-3">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="store.loading">
                <td colspan="5" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!filtered.length">
                <td colspan="5" class="text-center py-4 text-muted">尚無玩家資料</td>
              </tr>
              <template v-else>
                <tr v-for="p in filtered" :key="p._id" class="cursor-pointer" @click="goDetail(p._id)">
                  <td class="ps-3 fw-semibold">{{ p.player_name }}</td>
                  <td class="small text-muted">{{ p.star_citizen_id }}</td>
                  <td class="small">{{ p.discord_name || '—' }}</td>
                  <td class="text-muted small">{{ fmtDate(p.created_at) }}</td>
                  <td class="pe-3" @click.stop>
                    <button class="btn btn-sm btn-outline-secondary me-1" @click="playerModalRef.open(p)">
                      <i class="bi bi-pencil"></i> 編輯
                    </button>
                    <button class="btn btn-sm btn-outline-danger" @click="handleDelete(p)">
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

    <PlayerFormModal ref="playerModalRef" @saved="onSaved" />
    <ConfirmModal    ref="confirmModalRef" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { usePlayerStore } from '@/stores/player'
import { playerApi } from '@/api'
import SearchBox        from '@/components/SearchBox.vue'
import PlayerFormModal   from '@/components/PlayerFormModal.vue'
import ConfirmModal      from '@/components/ConfirmModal.vue'

const router = useRouter()
const store  = usePlayerStore()
const keyword = ref('')

const playerModalRef  = ref(null)
const confirmModalRef = ref(null)
const msg = ref(''); const msgType = ref('success')

const filtered = computed(() => {
  if (!keyword.value) return store.players
  const kw = keyword.value.toLowerCase()
  return store.players.filter(p =>
    `${p.player_name} ${p.star_citizen_id} ${p.discord_name || ''}`.toLowerCase().includes(kw)
  )
})

function fmtDate(d) { return d ? new Date(d).toLocaleDateString('zh-TW') : '—' }
function goDetail(id) { router.push(`/players/${id}`) }

function flash(text, type = 'danger') {
  msg.value = text; msgType.value = type
  setTimeout(() => { msg.value = '' }, 3000)
}

async function onSaved() { await store.load() }

async function handleDelete(p) {
  const ok = await confirmModalRef.value.confirm(
    `確定要刪除玩家 <strong>${escHtml(p.player_name)}</strong>？`
  )
  if (!ok) return
  const res = await playerApi.remove(p._id)
  if (!res) return
  const data = await res.json()
  if (data.success) store.load()
  else flash(data.message || '刪除失敗')
}

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}

onMounted(() => store.load())
</script>

<style scoped>
.cursor-pointer { cursor: pointer; }
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>
