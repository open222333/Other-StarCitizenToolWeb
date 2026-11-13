<!--
  戰術小隊分配表的分享連結（公開頁，不用登入）：/player/squad/<分享碼>。
  唯讀，版面跟玩家頁的唯讀模式共用 components/SquadBoardView.vue；資料只有白名單欄位（src/models/squad.py 的 public_view）。
  加 noindex，不讓搜尋引擎收錄。
-->
<template>
  <div class="scifi-page sqs-page">
    <div class="sqs-wrap">
      <header class="d-flex flex-wrap align-items-center gap-2 mb-3">
        <span class="sqs-brand"><i class="bi bi-people-fill me-2" style="color: var(--sf-accent)"></i>戰術小隊分配表</span>
        <RouterLink :to="PLAYER_HOME" class="btn btn-sm btn-outline-secondary ms-auto">
          <i class="bi bi-house me-1"></i>前往玩家頁</RouterLink>
      </header>
      <SfState :loading="loading" :error="error" @retry="load">
        <SquadBoardView v-if="board" :board="board" />
        <div v-if="board" class="small text-muted mt-3 text-end">最後更新：{{ fmtTs(board.updated_at) }}</div>
      </SfState>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import SfState from '@/components/SfState.vue'
import SquadBoardView from '@/components/SquadBoardView.vue'
import { PLAYER_HOME } from '@/router'
import { usePlayerAuthStore } from '@/stores/playerAuth'

const route = useRoute()
const playerAuth = usePlayerAuthStore()
const board = ref(null)
const loading = ref(true)
const error = ref('')

function fmtTs(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  return Number.isNaN(d.getTime()) ? ts : d.toLocaleString('zh-TW', { hour12: false })
}

async function load() {
  loading.value = true
  error.value = ''
  const res = await playerAuth.playerFetch(`/player/squads/shared/${encodeURIComponent(String(route.params.token || ''))}`)
  const data = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!res || !res.ok || !data?.success) {
    error.value = res?.status === 404 ? '這個連結已失效（分享已關閉或連結已重新產生）。' : (data?.message || '讀取失敗，請稍後再試。')
    return
  }
  board.value = data.data
  document.title = `${data.data.title} · 戰術小隊分配表`
}

// 不讓搜尋引擎收錄
let robots = null
onMounted(() => {
  robots = document.createElement('meta')
  robots.name = 'robots'
  robots.content = 'noindex, nofollow'
  document.head.appendChild(robots)
  load()
})
onBeforeUnmount(() => robots?.remove())
</script>

<style scoped>
.sqs-page { min-height: 100vh; padding: 1rem; }
.sqs-wrap { max-width: 96rem; margin: 0 auto; }
.sqs-brand { font-size: 1.15rem; font-weight: 700; color: var(--sf-text-strong, var(--sf-text)); }
</style>
