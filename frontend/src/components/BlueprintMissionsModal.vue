<!--
  玩家頁：點藍圖名稱彈出「解鎖任務」（哪些任務會給這張藍圖、機率多少）。

  資料來自本地任務資料庫（GET /mission/for-blueprint/<uuid>，見 app/mission/view.py），
  取資料走 `fetcher` prop（玩家頁傳 playerFetch），不直接碰 api/index.js。
  掛在 MyPlayerView 的 .scifi-page 裡，沿用玩家頁的深色主題 token。

  用法：<BlueprintMissionsModal ref="m" :fetcher="..." /> → m.value.open({ uuid, name, name_zh, output_type })
  藍圖名稱要不要做成可以點，看後端給的 mission_count（> 0 才有任務可看）。
-->
<template>
  <div v-if="visible" class="bpm-backdrop" @click.self="close" @keydown.esc="close">
    <div ref="dialogEl" class="bpm-dialog scifi-card" role="dialog" aria-modal="true"
      :aria-label="`${title} 解鎖任務`" tabindex="-1">
      <div class="bpm-head">
        <div class="min-w-0">
          <div class="fw-semibold text-truncate">{{ title }}</div>
          <div class="small text-muted text-truncate">{{ subtitle }}</div>
        </div>
        <button type="button" class="btn btn-sm bpm-close" aria-label="關閉" @click="close">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="bpm-body">
        <div class="small text-muted mb-2">解鎖任務</div>
        <div v-if="loading" class="text-muted small">載入中…</div>
        <div v-else-if="failed" class="text-warning small">讀取失敗。</div>
        <div v-else-if="!missions.length" class="text-muted small">沒有任務資料。</div>
        <template v-else>
        <div v-for="m in missions" :key="m._id" class="bpm-mission">
          <div class="d-flex justify-content-between flex-wrap gap-1">
            <div class="fw-semibold">
              {{ m.title_zh || m.title }}
              <span v-if="m.title_zh" class="small text-muted fw-normal ms-1">{{ m.title }}</span>
            </div>
            <!-- 上游列表沒給機率時（include=blueprints 的形狀）就不顯示 -->
            <div v-if="m.chance !== null && m.chance !== undefined" class="bpm-chance text-nowrap">
              機率 {{ fmtChance(m.chance) }}
              <span v-if="m.pool_size > 1" class="small text-muted fw-normal">（{{ m.pool_size }} 張抽一張）</span>
            </div>
          </div>
          <div class="mt-1">
            <span v-for="s in m.star_systems || []" :key="s" class="bpm-chip">{{ s }}</span>
            <span v-if="m.faction_name || m.mission_giver" class="bpm-chip">{{ factionLabel(m) }}</span>
            <span v-if="m.reward_scope" class="bpm-chip">{{ m.reward_scope }}</span>
            <span v-if="m.shareable" class="bpm-chip">可分享</span>
            <span v-if="m.once_only" class="bpm-chip">只能接一次</span>
            <span v-if="m.illegal" class="bpm-chip bpm-chip--warn">違法</span>
          </div>
          <div v-if="infoLine(m)" class="small mt-2">{{ infoLine(m) }}</div>
          <details v-if="m.description_zh || m.description" class="mt-2">
            <summary class="small text-muted">任務說明</summary>
            <div class="small mt-1 text-muted bpm-desc">{{ m.description_zh || m.description }}</div>
          </details>
        </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'
import { factionLabel, fmtChance, reputationLabel, rewardLabel } from '@/utils/mission'

const props = defineProps({
  /** 帶身分的 fetch（玩家頁用 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
})

const visible = ref(false)
const blueprint = ref(null)
const missions = ref([])
const loading = ref(false)
const failed = ref(false)
const dialogEl = ref(null)
let requestSeq = 0

const title = computed(() => blueprint.value?.name_zh || blueprint.value?.name || '')
const subtitle = computed(() => {
  const bp = blueprint.value || {}
  const parts = []
  if (bp.name_zh && bp.name) parts.push(bp.name)
  if (bp.output_type) parts.push(blueprintTypeLabel(bp.output_type))
  return parts.join(' · ')
})

async function open(bp) {
  if (!bp?.uuid) return
  blueprint.value = bp
  visible.value = true
  missions.value = []
  failed.value = false
  loading.value = true
  const seq = ++requestSeq
  await nextTick()
  dialogEl.value?.focus()
  const res = await props.fetcher(`/mission/for-blueprint/${encodeURIComponent(bp.uuid)}`)
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (seq !== requestSeq) return   // 載入途中已經關掉或換了別張
  if (body?.success) missions.value = body.data || []
  else failed.value = true
  loading.value = false
}

function infoLine(m) {
  const parts = []
  const reward = rewardLabel(m)
  if (reward !== '—') parts.push(`報酬 ${reward}`)
  if (reputationLabel(m)) parts.push(`聲望 ${reputationLabel(m)}`)
  if (m.cooldown_label) parts.push(`冷卻 ${m.cooldown_label}`)
  return parts.join(' · ')
}

function close() {
  requestSeq++
  visible.value = false
}

defineExpose({ open, close })
</script>

<style scoped>
.bpm-backdrop {
  position: fixed; inset: 0; z-index: 1080;
  display: flex; align-items: flex-start; justify-content: center;
  padding: 4rem 1rem 1rem;
  background: rgba(2, 6, 15, .72);
}
.bpm-dialog { width: 100%; max-width: 640px; outline: none; }
.bpm-head {
  display: flex; justify-content: space-between; align-items: center; gap: .5rem;
  padding: .8rem 1rem; border-bottom: 1px solid var(--sf-border);
}
.min-w-0 { min-width: 0; }
.bpm-close { color: var(--sf-text-muted); border: 0; }
.bpm-close:hover { color: var(--sf-text-strong); }
.bpm-body { padding: 1rem; max-height: calc(100dvh - 10rem); overflow-y: auto; }
.bpm-mission {
  border: 1px solid var(--sf-border); border-radius: 8px;
  padding: .6rem .75rem; margin-bottom: .6rem; background: var(--sf-inset);
}
.bpm-chance { color: var(--sf-accent-2-text, var(--sf-accent-2)); font-weight: 600; }
.bpm-chip {
  display: inline-block; font-size: .72rem; margin: 0 .25rem .2rem 0; padding: 0 .5rem;
  border: 1px solid var(--sf-border-hi); border-radius: 999px; color: var(--sf-text-muted);
}
.bpm-chip--warn { border-color: rgba(var(--bs-danger-rgb), .6); color: rgb(var(--bs-danger-rgb)); }
.bpm-desc { white-space: pre-line; }
details > summary { cursor: pointer; }
</style>
