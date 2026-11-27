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
        <span v-for="s in m.star_systems || []" :key="s" class="sf-chip">{{ systemLabel(s) }}</span>
        <span v-if="m.faction_name || m.mission_giver" class="sf-chip">{{ factionLabel(m) }}</span>
        <span v-if="m.reward_scope" class="sf-chip">{{ typeLabel(m.reward_scope) }}</span>
        <span v-if="m.illegal" class="sf-chip sf-chip--warn">違法</span>
      </div>
      <div v-if="m.description_zh || m.description" class="md-desc">{{ m.description_zh || m.description }}</div>
      <details v-if="m.description_zh && m.description" class="mt-1">
        <summary class="md-sub text-muted">英文</summary>
        <div class="md-sub text-muted md-desc mt-1">{{ m.description }}</div>
      </details>
      <div v-if="missionConditions(m)" class="md-sub text-muted mt-2">{{ missionConditions(m) }}</div>
      <dl class="sf-facts md-facts mt-2 mb-0">
        <template v-if="full">
          <dt>報酬</dt>
          <dd class="fw-semibold">{{ rewardLabel(m) }}</dd>
          <dt>聲望異動</dt>
          <dd>
            <div v-for="(r, i) in m.reputation_gained || []" :key="i">
              <span class="fw-semibold" :class="Number(r.amount) < 0 ? 'sf-bad' : 'sf-good'">{{ fmtRep(r.amount) }}</span>
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
            {{ factionLabel(m) }} · <span class="fw-semibold">{{ rankLabel(standing.name) }}</span>
            <span v-if="translate('rep_rank', standing.name)" class="small text-muted ms-1">{{ standing.name }}</span>
            <span v-if="standing.min !== null" class="md-chance ms-1">{{ fmtInt(standing.min) }} 聲望以上</span>
            <span v-if="standing.max" class="text-muted ms-1">（上限 {{ rankLabel(standing.max) }}）</span>
          </template>
          <span v-else class="text-muted">不需聲望</span>
        </dd>
        <dt>接取地點</dt>
        <dd>{{ (m.star_systems || []).map(systemLabel).join('、') || '—' }}</dd>
        <!-- 前置任務：每組「完成其中幾個」，看得到的任務可以點開 -->
        <template v-if="preGroups.length || m.has_prerequisites">
          <dt>前置任務</dt>
          <dd>
            <div v-for="(g, i) in preGroups" :key="i" :class="{ 'mt-1': i }">
              <div v-if="groupNote(g)" class="md-sub text-muted">{{ groupNote(g) }}</div>
              <div class="md-links">
                <template v-for="p in g.missions" :key="p.uuid">
                  <button v-if="p.linkable" type="button" class="btn btn-sm btn-info md-link" @click="openLinked(p.uuid)">{{ p.title_zh || p.title }}</button>
                  <span v-else class="sf-chip">{{ p.title_zh || p.title }}</span>
                </template>
              </div>
            </div>
            <span v-if="!preGroups.length" class="text-muted">有（尚未取得名單）</span>
          </dd>
        </template>
        <template v-if="m.unlocks?.length">
          <dt>完成後可接</dt>
          <dd class="md-links">
            <button v-for="u in m.unlocks" :key="u.uuid" type="button" class="btn btn-sm btn-info md-link" @click="openLinked(u.uuid)">{{ u.title_zh || u.title }}</button>
          </dd>
        </template>
      </dl>
    </div>
    <div class="col-lg-6">
      <div class="md-sub text-muted mb-1">
        獎勵藍圖<template v-if="pool.length">：{{ pool.length }} 種<template v-if="tracking"> · 已登記
          <span class="fw-semibold" :class="registeredCount === pool.length ? 'text-success' : 'md-count'">{{ registeredCount }} / {{ pool.length }}</span></template></template>
        <button v-if="fetcher && unregistered.length > 1" type="button" class="btn btn-sm btn-success ms-2"
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
        <span v-for="(it, j) in p.items || []" :key="it.blueprint_uuid || j" class="sf-chip"
          :class="tracking ? (isRegistered(it) ? 'sf-chip--ok' : 'sf-chip--todo') : ''">
          <i v-if="tracking" class="bi me-1" :class="isRegistered(it) ? 'bi-check-circle-fill' : 'bi-circle'"></i>{{ it.name_zh || it.name }}
          <span v-if="tracking" class="sf-chip__state">{{ bpStateLabel(it, registered) }}</span>
          <button v-if="fetcher && !isRegistered(it)" type="button" class="btn btn-sm btn-success sf-chip__btn"
            :disabled="registering" :aria-label="`登記 ${it.name_zh || it.name}`" @click="register([bpUuid(it)])">登記</button>
        </span>
      </div>
    </div>
    <!-- 點前置／後續任務：跳出視窗看那個任務（視窗裡再點就換成那個任務，不疊視窗） -->
    <!-- Teleport 到 body（任務細節可能已經在勢力聲望視窗裡），外面包 .scifi-page 才吃得到主題（同 RouteLegsTable） -->
    <Teleport v-if="!nested && linkedId" to="body">
    <div class="scifi-page md-linked-host">
    <SfModal id="md-linked" v-model:open="linkedOpen" :title="linked ? (linked.title_zh || linked.title) : '任務'" width="1000px">
      <SfState v-if="linkedLoading" loading />
      <SfState v-else-if="linkedError" :error="linkedError" @retry="openLinked(linkedId)" />
      <MissionDetail v-else-if="linked" :key="linked._id" :mission="linked" :registered-uuids="registeredUuids"
        :ladders="ladders" full nested @open="openLinked" />
    </SfModal>
    </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import { getJson } from '@/utils/getJson'
import { factionLabel, fmtChance, fmtCooldown, fmtInt, fmtRep, missionConditions, rewardLabel } from '@/utils/mission'
import { loadTranslations, translate } from '@/utils/translations'
import { bpStateLabel, bpUuid, isBpRegistered, missionPool, registeredInPool } from '@/utils/missionBlueprints'

const props = defineProps({
  mission: { type: Object, required: true },
  /** 我的藍圖的 blueprint_uuid（預設可用的視同已登記）；null＝沒登入，不顯示登記狀態 */
  registeredUuids: { type: Array, default: () => [] },
  /** {faction_uuid: [{name, min_reputation}]} */
  ladders: { type: Object, default: () => ({}) },
  /** 也列出報酬、聲望異動、冷卻（任務列表已經有這幾欄就不用） */
  full: { type: Boolean, default: false },
  /** 有給（玩家頁 playerFetch）才顯示「登記」按鈕：POST /player/blueprints/bulk，登記完 emit('registered') */
  fetcher: { type: Function, default: null },
  /** 在「前置／後續任務」視窗裡：點任務改 emit('open', uuid)，由外層換內容 */
  nested: { type: Boolean, default: false },
})
const emit = defineEmits(['registered', 'open'])

const m = computed(() => props.mission)
const tracking = computed(() => props.registeredUuids !== null)
const registered = computed(() => new Set(props.registeredUuids || []))
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
// 聲望階級名稱：翻譯包有就顯示中文（RepStanding_*，見後端 sc_zh.rep_rank_zh）
function rankLabel(s) { return translate('rep_rank', s) || s }

const realStanding = s => (typeof s === 'string' && s.trim() && !/placeholder/i.test(s) ? s.trim() : '')
const standing = computed(() => {
  const name = realStanding(m.value.min_standing_name)
  if (!name) return null
  const step = (props.ladders[m.value.faction_uuid] || []).find(x => (x.name || '').toLowerCase() === name.toLowerCase())
  return { name, min: step?.min_reputation ?? null, max: realStanding(m.value.max_standing_name) }
})
watch(standing, s => { if (s) loadTranslations('rep_rank', [s.name, s.max]) }, { immediate: true })

// 前置任務組：required_count 少於列出的任務數＝「其中幾個」，否則全部都要
const preGroups = computed(() => (m.value.prerequisite_groups || []).filter(g => g.missions?.length))
function groupNote(g) {
  const n = g.missions.length
  if (g.required_count && g.required_count < n) return `完成其中 ${g.required_count} 個`
  return n > 1 ? '全部完成' : ''
}

// 點前置／後續任務：GET /mission/<id>（公開端點，看得到的才回）
const linkedOpen = ref(false)
const linked = ref(null)
const linkedLoading = ref(false)
const linkedError = ref('')
const linkedId = ref('')
let linkSeq = 0
async function openLinked(id) {
  if (props.nested) { emit('open', id); return }
  const my = ++linkSeq
  const first = !linkedId.value
  linkedId.value = id
  // 視窗第一次用到才掛上，等掛好再打開（開啟時焦點移進視窗）
  if (first) await nextTick()
  linkedOpen.value = true
  linkedLoading.value = true
  linkedError.value = ''
  const { ok, data, message: msg } = await getJson(fetch, `/mission/${encodeURIComponent(id)}`, undefined, '讀取任務失敗')
  if (my !== linkSeq) return
  linkedLoading.value = false
  if (!ok) { linked.value = null; linkedError.value = msg; return }
  linked.value = data
  loadTranslations('mission_type', [data.reward_scope])
  loadTranslations('location', data.star_systems || [])
  loadTranslations('faction', (data.reputation_gained || []).map(r => r.faction))
}
</script>

<style scoped>
.md-desc { white-space: pre-line; }
.md-sub { font-size: .9rem; }
.md-chance { color: var(--sf-accent-2-text, var(--sf-accent-2)); font-weight: 600; }
.md-count { color: var(--sf-text-strong); }
.md-facts { font-size: .95rem; }
.md-linked-host { display: contents; }
.md-links { display: flex; flex-wrap: wrap; gap: .35rem; }
.md-link { text-align: left; white-space: normal; }
details > summary { cursor: pointer; }
</style>
