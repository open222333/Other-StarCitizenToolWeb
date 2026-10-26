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
        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="close">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="bpm-body">
        <div class="small text-muted mb-2">解鎖任務</div>
        <SfState :loading="loading" :error="failed ? '讀取失敗。' : ''" :empty="!missions.length" empty-text="沒有任務資料。"
          @retry="fetchMissions">
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
            <span v-for="s in m.star_systems || []" :key="s" class="sf-chip">{{ systemLabel(s) }}</span>
            <span v-if="m.faction_name || m.mission_giver" class="sf-chip">{{ factionLabel(m) }}</span>
            <span v-if="m.reward_scope" class="sf-chip">{{ typeLabel(m.reward_scope) }}</span>
            <span v-if="m.shareable" class="sf-chip">可分享</span>
            <span v-if="m.once_only" class="sf-chip">只能接一次</span>
            <span v-if="m.illegal" class="sf-chip sf-chip--warn">違法</span>
          </div>
          <div v-if="infoLine(m)" class="small mt-2">{{ infoLine(m) }}</div>
          <!-- 這個任務會給的所有藍圖（所有獎勵池合起來）：玩家頁標出哪些已登記（含預設可用）、哪些還沒，例如 1 / 10 -->
          <div v-if="m.pool_blueprints?.length > 1 || (registered && m.pool_blueprints?.length)" class="mt-2">
            <div class="small text-muted mb-1">
              任務藍圖 {{ m.pool_blueprints.length }} 種<template v-if="registered"> · 已登記
                <span class="fw-semibold" :class="poolRegisteredCount(m) === m.pool_blueprints.length ? 'text-success' : 'bpm-count'">{{ poolRegisteredCount(m) }} / {{ m.pool_blueprints.length }}</span></template>
            </div>
            <span v-for="b in m.pool_blueprints" :key="b.uuid" class="sf-chip"
              :class="[registered ? (isRegistered(b) ? 'sf-chip--ok' : 'sf-chip--todo') : '', { 'bpm-current': b.uuid === blueprint?.uuid }]">
              <i v-if="registered" class="bi me-1" :class="isRegistered(b) ? 'bi-check-circle-fill' : 'bi-circle'"></i>{{ b.name_zh || b.name }}
              <span v-if="registered" class="sf-chip__state">{{ bpStateLabel(b, registered) }}</span>
            </span>
          </div>
          <details v-if="m.description_zh || m.description" class="mt-2">
            <summary class="small text-muted">任務說明</summary>
            <div class="small mt-1 text-muted bpm-desc">{{ m.description_zh || m.description }}</div>
          </details>
        </div>
        </SfState>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, ref } from 'vue'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'
import { factionLabel, fmtChance, reputationLabel, rewardLabel } from '@/utils/mission'
import { bpStateLabel, isBpRegistered, registeredInPool } from '@/utils/missionBlueprints'
import { loadTranslations, translate } from '@/utils/translations'
import SfState from '@/components/SfState.vue'

const props = defineProps({
  /** 帶身分的 fetch（玩家頁用 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /** 玩家自己已登記的藍圖 uuid；有給才標出獎勵池裡的已登記／未登記（預設可用的視同已登記） */
  registeredUuids: { type: Array, default: null },
})

const registered = computed(() => (props.registeredUuids ? new Set(props.registeredUuids) : null))
const isRegistered = b => isBpRegistered(b, registered.value)
const poolRegisteredCount = m => registeredInPool(m, registered.value)

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
  await fetchMissions()
}

async function fetchMissions() {
  const bp = blueprint.value
  if (!bp?.uuid) return
  missions.value = []
  failed.value = false
  loading.value = true
  const seq = ++requestSeq
  await nextTick()
  dialogEl.value?.focus()
  const res = await props.fetcher(`/mission/for-blueprint/${encodeURIComponent(bp.uuid)}`)
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (seq !== requestSeq) return   // 載入途中已經關掉或換了別張
  if (body?.success) {
    missions.value = body.data || []
    // 星系、類型的中文從翻譯資料庫查（同 MissionDetail），查不到顯示英文
    loadTranslations('location', missions.value.flatMap(m => m.star_systems || []))
    loadTranslations('mission_type', missions.value.map(m => m.reward_scope).filter(Boolean))
  } else failed.value = true
  loading.value = false
}

function typeLabel(s) { return translate('mission_type', s) || s }
function systemLabel(s) { return translate('location', s) || s }

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
.bpm-body { padding: 1rem; max-height: calc(100dvh - 10rem); overflow-y: auto; }
.bpm-mission {
  border: 1px solid var(--sf-border); border-radius: 8px;
  padding: .6rem .75rem; margin-bottom: .6rem; background: var(--sf-inset);
}
.bpm-chance { color: var(--sf-accent-2-text, var(--sf-accent-2)); font-weight: 600; }
.bpm-desc { white-space: pre-line; }
details > summary { cursor: pointer; }
.bpm-current { box-shadow: 0 0 0 1px var(--sf-accent) inset; font-weight: 700; }
.bpm-count { color: var(--sf-text-strong); }
</style>
