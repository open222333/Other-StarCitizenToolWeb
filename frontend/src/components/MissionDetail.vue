<!--
  玩家頁任務展開的細節（任務列表 MissionBrowser、勢力聲望 FactionReputation 共用）：
  標籤、說明、條件、聲望門檻、接取地點、（full 時）報酬／聲望異動／冷卻，以及每個獎勵池的藍圖
  （標已登記／未登記／預設可用、掉落機率）。
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
      <div v-if="m.description_zh || m.description" class="small md-desc">{{ m.description_zh || m.description }}</div>
      <details v-if="m.description_zh && m.description" class="mt-1">
        <summary class="small text-muted">英文</summary>
        <div class="small text-muted md-desc mt-1">{{ m.description }}</div>
      </details>
      <div v-if="missionConditions(m)" class="small text-muted mt-2">{{ missionConditions(m) }}</div>
      <dl class="md-facts small mt-2 mb-0">
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
      <div class="small text-muted mb-1">
        獎勵藍圖<template v-if="pool.length">：{{ pool.length }} 種 · 已登記
          <span class="fw-semibold" :class="registeredCount === pool.length ? 'text-success' : 'md-count'">{{ registeredCount }} / {{ pool.length }}</span></template>
      </div>
      <div v-if="!m.blueprint_pools?.length" class="small text-muted">—</div>
      <div v-for="(p, i) in m.blueprint_pools || []" :key="p.pool_uuid || i" class="mb-2">
        <div v-if="p.drop_chance !== null && p.drop_chance !== undefined" class="small md-chance">
          機率 {{ fmtChance(p.drop_chance) }}
          <span v-if="(p.items || []).length > 1" class="text-muted fw-normal">（{{ p.items.length }} 張抽一張）</span>
        </div>
        <span v-for="(it, j) in p.items || []" :key="it.blueprint_uuid || j" class="md-chip"
          :class="isRegistered(it) ? 'md-chip--ok' : 'md-chip--todo'">
          <i class="bi me-1" :class="isRegistered(it) ? 'bi-check-circle-fill' : 'bi-circle'"></i>{{ it.name_zh || it.name }}
          <span class="md-chip__state">{{ isRegistered(it) ? (it.is_available_by_default && !registered.has(it.blueprint_uuid) ? '預設可用' : '已登記') : '未登記' }}</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { factionLabel, fmtChance, fmtCooldown, fmtInt, fmtRep, missionConditions, rewardLabel } from '@/utils/mission'
import { translate } from '@/utils/translations'

const props = defineProps({
  mission: { type: Object, required: true },
  /** 我的藍圖的 blueprint_uuid（預設可用的視同已登記） */
  registeredUuids: { type: Array, default: () => [] },
  /** {faction_uuid: [{name, min_reputation}]} */
  ladders: { type: Object, default: () => ({}) },
  /** 也列出報酬、聲望異動、冷卻（任務列表已經有這幾欄就不用） */
  full: { type: Boolean, default: false },
})

const m = computed(() => props.mission)
const registered = computed(() => new Set(props.registeredUuids))
function isRegistered(it) {
  return !!it.is_available_by_default || registered.value.has(it.blueprint_uuid)
}
/** 任務會給的所有藍圖（所有獎勵池合起來，同一張只算一次） */
const pool = computed(() => {
  const seen = new Map()
  for (const p of m.value.blueprint_pools || []) {
    for (const it of p.items || []) if (it.blueprint_uuid && !seen.has(it.blueprint_uuid)) seen.set(it.blueprint_uuid, it)
  }
  return [...seen.values()]
})
const registeredCount = computed(() => pool.value.filter(isRegistered).length)

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
.md-chance { color: var(--sf-accent-2-text, var(--sf-accent-2)); font-weight: 600; }
.md-count { color: var(--sf-text-strong); }
.md-good { color: rgb(var(--bs-success-rgb)); }
.md-bad { color: rgb(var(--bs-danger-rgb)); }
.md-facts { display: grid; grid-template-columns: auto 1fr; gap: .2rem .75rem; }
.md-facts dt { color: var(--sf-text-muted); font-weight: 600; }
.md-facts dd { margin: 0; }
.md-chip {
  display: inline-block; font-size: .75rem; margin: 0 .25rem .25rem 0; padding: 0 .5rem;
  border: 1px solid var(--sf-border-hi); border-radius: 999px; color: var(--sf-text-muted);
}
.md-chip--warn { border-color: rgba(var(--bs-danger-rgb), .6); color: rgb(var(--bs-danger-rgb)); }
.md-chip--ok { border-color: rgba(var(--bs-success-rgb), .7); color: rgb(var(--bs-success-rgb)); }
.md-chip--todo { border-style: dashed; }
.md-chip__state { margin-left: .35rem; font-size: .78em; opacity: .85; }
details > summary { cursor: pointer; }
</style>
