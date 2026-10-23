<!--
  玩家頁任務展開的細節（任務列表 MissionBrowser、勢力聲望 FactionReputation 共用）：
  標籤、說明、條件、聲望門檻、接取地點、（full 時）報酬／聲望異動／冷卻，以及每個獎勵池的藍圖
  （標已登記／未登記／預設可用、掉落機率）。
  有傳 fetcher 時，未登記的藍圖旁有「登記」按鈕（也可一次登記全部未登記的），取得方式記「任務」。
  ladders＝{faction_uuid: [{name, min_reputation}]}，用來把任務的 min_standing_name 換成門檻分數。
-->
<template>
  <div class="row g-3">
    <div class="col-lg-6">
      <div class="mb-2">
        <span v-for="s in m.star_systems || []" :key="s" class="md-chip">{{ systemLabel(s) }}</span>
        <span v-if="m.faction_name || m.mission_giver" class="md-chip">{{ factionLabel(m) }}</span>
        <span v-if="m.reward_scope" class="md-chip">{{ typeLabel(m.reward_scope) }}</span>
        <span v-if="m.illegal" class="md-chip md-chip--warn">違法</span>
      </div>
      <div v-if="m.description_zh || m.description" class="md-desc">{{ m.description_zh || m.description }}</div>
      <details v-if="m.description_zh && m.description" class="mt-1">
        <summary class="md-sub text-muted">英文</summary>
        <div class="md-sub text-muted md-desc mt-1">{{ m.description }}</div>
      </details>
      <div v-if="missionConditions(m)" class="md-sub text-muted mt-2">{{ missionConditions(m) }}</div>
      <dl class="md-facts mt-2 mb-0">
        <template v-if="full">
          <dt>報酬</dt>
          <dd class="fw-semibold">{{ rewardLabel(m) }}</dd>
          <dt>聲望異動</dt>
          <dd>
            <div v-for="(r, i) in m.reputation_gained || []" :key="i">
              <span class="fw-semibold" :class="Number(r.amount) < 0 ? 'md-bad' : 'md-good'">{{ fmtRep(r.amount) }}</span>
              <span v-if="r.faction" class="text-muted ms-1">{{ factionName(r.faction) }}</span>
            </div>
            <span v-if="!m.reputation_gained?.length" class="text-muted">—</span>
          </dd>
          <dt>冷卻</dt>
          <dd>{{ fmtCooldown(m.cooldown_seconds) }}</dd>
        </template>
        <dt>聲望門檻</dt>
        <dd>
          <template v-if="standing">
            {{ factionLabel(m) }} · <span class="fw-semibold">{{ standing.name }}</span>
            <span v-if="standing.min !== null" class="md-chance ms-1">{{ fmtInt(standing.min) }} 聲望以上</span>
            <span v-if="standing.max" class="text-muted ms-1">（上限 {{ standing.max }}）</span>
          </template>
          <span v-else class="text-muted">不需聲望</span>
        </dd>
        <dt>接取地點</dt>
        <dd>{{ (m.star_systems || []).map(systemLabel).join('、') || '—' }}</dd>
      </dl>
    </div>
    <div class="col-lg-6">
      <div class="md-sub text-muted mb-1">
        獎勵藍圖<template v-if="pool.length">：{{ pool.length }} 種 · 已登記
          <span class="fw-semibold" :class="registeredCount === pool.length ? 'text-success' : 'md-count'">{{ registeredCount }} / {{ pool.length }}</span></template>
        <button v-if="fetcher && unregistered.length > 1" type="button" class="btn btn-sm btn-success py-0 ms-2"
          :disabled="registering" @click="register(unregistered.map(bpUuid))">
          <i class="bi bi-plus-lg me-1"></i>登記全部未登記（{{ unregistered.length }}）
        </button>
      </div>
      <div v-if="message" class="md-sub mb-1" :class="messageOk ? 'text-success' : 'text-warning'">{{ message }}</div>
      <div v-if="!m.blueprint_pools?.length" class="md-sub text-muted">—</div>
      <div v-for="(p, i) in m.blueprint_pools || []" :key="p.pool_uuid || i" class="mb-2">
        <div v-if="p.drop_chance !== null && p.drop_chance !== undefined" class="md-sub md-chance">
          機率 {{ fmtChance(p.drop_chance) }}
          <span v-if="(p.items || []).length > 1" class="text-muted fw-normal">（{{ p.items.length }} 張抽一張）</span>
        </div>
        <span v-for="(it, j) in p.items || []" :key="it.blueprint_uuid || j" class="md-chip"
          :class="isRegistered(it) ? 'md-chip--ok' : 'md-chip--todo'">
          <i class="bi me-1" :class="isRegistered(it) ? 'bi-check-circle-fill' : 'bi-circle'"></i>{{ it.name_zh || it.name }}
          <span class="md-chip__state">{{ bpStateLabel(it, registered) }}</span>
          <button v-if="fetcher && !isRegistered(it)" type="button" class="btn btn-success md-chip__btn"
            :disabled="registering" :aria-label="`登記 ${it.name_zh || it.name}`" @click="register([bpUuid(it)])">登記</button>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { factionLabel, fmtChance, fmtCooldown, fmtInt, fmtRep, missionConditions, rewardLabel } from '@/utils/mission'
import { translate } from '@/utils/translations'
import { bpStateLabel, bpUuid, isBpRegistered, missionPool, registeredInPool } from '@/utils/missionBlueprints'

const props = defineProps({
  mission: { type: Object, required: true },
  /** 我的藍圖的 blueprint_uuid（預設可用的視同已登記） */
  registeredUuids: { type: Array, default: () => [] },
  /** {faction_uuid: [{name, min_reputation}]} */
  ladders: { type: Object, default: () => ({}) },
  /** 也列出報酬、聲望異動、冷卻（任務列表已經有這幾欄就不用） */
  full: { type: Boolean, default: false },
  /** 有給（玩家頁 playerFetch）才顯示「登記」按鈕：POST /player/blueprints/bulk，登記完 emit('registered') */
  fetcher: { type: Function, default: null },
})
const emit = defineEmits(['registered'])

const m = computed(() => props.mission)
const registered = computed(() => new Set(props.registeredUuids))
const isRegistered = it => isBpRegistered(it, registered.value)
const pool = computed(() => missionPool(m.value))
const registeredCount = computed(() => registeredInPool(m.value, registered.value))
const unregistered = computed(() => pool.value.filter(it => !isRegistered(it)))

// 直接在任務細節登記沒登記的藍圖（取得方式記「任務」）
const registering = ref(false)
const message = ref('')
const messageOk = ref(true)
async function register(uuids) {
  const ids = uuids.filter(Boolean)
  if (!ids.length || registering.value || !props.fetcher) return
  registering.value = true
  message.value = ''
  try {
    const res = await props.fetcher('/player/blueprints/bulk', {
      method: 'POST',
      body: JSON.stringify({ blueprint_uuids: ids, acquisition_method: '任務' }),
    })
    const data = res ? await res.json().catch(() => null) : null
    if (!res?.ok || !data?.success) {
      messageOk.value = false
      message.value = data?.message || '登記失敗，請稍後再試'
      return
    }
    messageOk.value = !!data.added
    message.value = `已登記 ${data.added} 張${data.skipped ? `，跳過 ${data.skipped} 張（已登記過）` : ''}`
    emit('registered')
  } finally {
    registering.value = false
  }
}

function typeLabel(s) { return translate('mission_type', s) || s }
function systemLabel(s) { return translate('location', s) || s }
function factionName(s) { return translate('faction', s) || s }

const realStanding = s => (typeof s === 'string' && s.trim() && !/placeholder/i.test(s) ? s.trim() : '')
const standing = computed(() => {
  const name = realStanding(m.value.min_standing_name)
  if (!name) return null
  const step = (props.ladders[m.value.faction_uuid] || []).find(x => (x.name || '').toLowerCase() === name.toLowerCase())
  return { name, min: step?.min_reputation ?? null, max: realStanding(m.value.max_standing_name) }
})
</script>

<style scoped>
.md-desc { white-space: pre-line; }
.md-sub { font-size: .9rem; }
.md-chance { color: var(--sf-accent-2-text, var(--sf-accent-2)); font-weight: 600; }
.md-count { color: var(--sf-text-strong); }
.md-good { color: rgb(var(--bs-success-rgb)); }
.md-bad { color: rgb(var(--bs-danger-rgb)); }
.md-facts { display: grid; grid-template-columns: auto 1fr; gap: .2rem .75rem; font-size: .95rem; }
.md-facts dt { color: var(--sf-text-muted); font-weight: 600; }
.md-facts dd { margin: 0; }
.md-chip {
  display: inline-block; font-size: .9rem; margin: 0 .25rem .25rem 0; padding: 0 .5rem;
  border: 1px solid var(--sf-border-hi); border-radius: 999px; color: var(--sf-text-muted);
}
.md-chip--warn { border-color: rgba(var(--bs-danger-rgb), .6); color: rgb(var(--bs-danger-rgb)); }
.md-chip--ok { border-color: rgba(var(--bs-success-rgb), .7); color: rgb(var(--bs-success-rgb)); }
.md-chip--todo { border-style: dashed; }
.md-chip__state { margin-left: .35rem; font-size: .9em; opacity: .85; }
.md-chip__btn { margin-left: .4rem; padding: 0 .4rem; font-size: .85rem; line-height: 1.4; border-radius: 999px; }
details > summary { cursor: pointer; }
</style>
