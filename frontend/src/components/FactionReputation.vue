<!--
  玩家頁「任務 › 勢力聲望」／「資料庫 › 勢力」展開：輸入勢力名稱（自動完成，中英文皆可）選一個勢力
  （傳 factionId 時直接顯示那個勢力，不出現搜尋卡），列出它的聲望階級（名稱＋門檻分數），
  一個勢力有好幾種聲望（例如紅風物流的立場、貨運）時上面一排按鈕切換，各自一條階級表；
  每一階底下是「要到這個階級才能接」的任務（任務的 min_standing_name 對階級名稱，
  GET /mission/factions/<id>/reputation）；沒有門檻的、門檻對不到階級表的各自一組。
  點任務展開細節（MissionDetail：說明、條件、報酬、聲望異動、冷卻、聲望門檻、獎勵藍圖登記狀況）。
  任務的藍圖欄比照任務列表：任務會給的藍圖自己已登記幾張（預設可用的視同已登記）。
-->
<template>
  <div>
    <div v-if="!fixedId" class="card scifi-card sf-search mb-3">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-6">
            <label class="form-label small fw-semibold mb-1" for="fr-faction">勢力</label>
            <AutocompleteField id="fr-faction" v-model="factionQuery" :search="searchFactions" :get-label="factionName"
              :get-meta="f => `${f.mission_count} 個任務`" :min-chars="0" :debounce-ms="0"
              aria-label="勢力" placeholder="輸入勢力名稱（中英文皆可）" @select="f => { factionId = f?._id || '' }" />
          </div>
        </div>
      </div>
    </div>

    <SfState :loading="loading" :error="failed ? '讀取失敗。' : ''" :empty="!factionId || !data" empty-text="—"
      @retry="loadFaction(factionId)">
      <!-- 好幾種聲望：一種一個按鈕（按鈕上是該種聲望的任務數） -->
      <div v-if="scopes.length > 1" class="btn-group btn-group-sm flex-wrap mb-2" role="group" aria-label="聲望種類">
        <button v-for="(sc, i) in scopes" :key="i" type="button" class="btn btn-subtab" :class="{ active: scopeIndex === i }"
          :aria-pressed="scopeIndex === i ? 'true' : 'false'" @click="scopeIndex = i">
          {{ scopeLabel(sc.scope) }}<span class="fr-scope-count ms-1">{{ scopeMissionCount(i) }}</span>
        </button>
      </div>
      <div v-else-if="scopes.length === 1 && scopes[0].scope" class="mb-2">
        <span class="sf-chip sf-chip--accent mb-0">{{ scopeLabel(scopes[0].scope) }}</span>
      </div>
      <div v-for="g in groups" :key="g.key" class="card scifi-card mb-2">
        <div class="card-body py-2 ps-3 pe-3">
          <button type="button" class="fr-head p-0 text-start w-100" :aria-expanded="isOpen(g.key) ? 'true' : 'false'"
            @click="toggle(g.key)">
            <i class="bi me-1" :class="isOpen(g.key) ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
            <span class="fw-semibold">{{ g.title }}</span>
            <span v-if="g.en" class="small text-muted ms-1">{{ g.en }}</span>
            <span v-if="g.threshold !== null && g.threshold !== undefined" class="fr-threshold ms-2">{{ fmtInt(g.threshold) }} 聲望</span>
            <span class="small text-muted ms-2">{{ g.missions.length }} 個任務</span>
          </button>
        </div>
        <div v-if="isOpen(g.key)" class="card-body p-0 border-top">
            <div v-if="!g.missions.length" class="text-muted ps-3 pe-3 py-2">—</div>
            <div v-else style="overflow-x:auto">
              <table class="table table-hover align-middle mb-0 sf-stack">
                <thead class="table-light">
                  <tr>
                    <th class="ps-3">任務</th>
                    <th>類型</th>
                    <th class="d-none d-md-table-cell">星系</th>
                    <th class="text-end">報酬</th>
                    <th class="text-end pe-3">藍圖</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="m in g.missions" :key="m._id">
                  <template v-for="bp in [bpCounts.get(m)]" :key="m._id">
                  <tr class="fr-row" role="button" tabindex="0" :aria-expanded="openMission === m._id ? 'true' : 'false'"
                    @click="openMission = openMission === m._id ? '' : m._id" @keydown.enter.self="openMission = openMission === m._id ? '' : m._id" @keydown.space.self.prevent="openMission = openMission === m._id ? '' : m._id">
                    <td class="ps-3 sf-stack__title">
                      <i class="bi me-1 small text-muted" :class="openMission === m._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <span class="fw-semibold">{{ m.title_zh || m.title }}</span>
                      <span v-if="m.title_zh" class="small text-muted ms-1">{{ m.title }}</span>
                      <span v-if="m.illegal" class="sf-chip sf-chip--warn ms-1">違法</span>
                      <span v-if="g.key.endsWith('unmatched') && m.min_standing_name" class="sf-chip ms-1">{{ translate('rep_rank', m.min_standing_name) || m.min_standing_name }}</span>
                    </td>
                    <td data-label="類型">{{ m.reward_scope ? typeLabel(m.reward_scope) : '—' }}</td>
                    <td class="d-none d-md-table-cell" data-label="星系">{{ (m.star_systems || []).map(systemLabel).join('、') || '—' }}</td>
                    <td class="text-end text-nowrap" data-label="報酬">{{ rewardLabel(m) }}</td>
                    <td class="text-end text-nowrap pe-3" data-label="藍圖">
                      <span v-if="bp.poolSize && registeredUuids === null">{{ bp.poolSize }} 種</span>
                      <span v-else-if="bp.poolSize" class="fw-semibold"
                        :class="bp.regCount === bp.poolSize ? 'text-success' : 'fr-count'">{{ bp.regCount }} / {{ bp.poolSize }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                  </tr>
                  <tr v-if="openMission === m._id" class="sf-stack__detail">
                    <td colspan="5" class="fr-detail">
                      <div class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">{{ m.title_zh || m.title }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="openMission = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <MissionDetail :mission="m" :registered-uuids="registeredUuids" :ladders="ladderMap" full :fetcher="canRegister ? fetcher : null" @registered="$emit('registered')" />
                    </td>
                  </tr>
                  </template>
                  </template>
                </tbody>
              </table>
            </div>
        </div>
      </div>
    </SfState>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AutocompleteField from '@/components/AutocompleteField.vue'
import MissionDetail from '@/components/MissionDetail.vue'
import SfState from '@/components/SfState.vue'
import { missionPool, registeredInPool } from '@/utils/missionBlueprints'
import { fmtInt, rewardLabel } from '@/utils/mission'
import { loadTranslations, translate } from '@/utils/translations'

defineEmits(['registered'])
const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 第一次變成可見才載入 */
  active: { type: Boolean, default: true },
  /** 我的藍圖的 blueprint_uuid（預設可用的視同已登記） */
  registeredUuids: { type: Array, default: () => [] },
  /** 能不能在任務細節直接登記藍圖（沒登入＝false） */
  canRegister: { type: Boolean, default: true },
  /** 直接顯示這個勢力（不出現搜尋卡）；資料庫 › 勢力展開用 */
  factionId: { type: String, default: '' },
})
const fixedId = computed(() => props.factionId || '')

const factions = ref([])
const factionId = ref(props.factionId || '')
const factionQuery = ref('')
const openMission = ref('')
// 這個勢力目前選的那種聲望的階級表，給 MissionDetail 換算聲望門檻分數
const ladderMap = computed(() => (data.value
  ? { [data.value.faction._id]: ((scopes.value[scopeIndex.value] || scopes.value[0])?.ranks || []).map(r => ({ name: r.name, min_reputation: r.min_reputation })) }
  : {}))
// 本地清單比對：中文、英文、翻譯資料庫查到的中文都算
async function searchFactions(q) {
  const t = (q || '').trim().toLowerCase()
  return factions.value.filter(f => !t || [f.name, f.name_zh, translate('faction', f.name)]
    .some(x => (x || '').toLowerCase().includes(t)))
}
const data = ref(null)
const loading = ref(false)
const failed = ref(false)
const openKeys = reactive({})

async function getJson(path) {
  const res = await props.fetcher(path)
  return res?.ok ? await res.json().catch(() => null) : null
}

function factionName(f) {
  return f.name_zh ? `${f.name_zh}（${f.name}）` : (translate('faction', f.name) || f.name)
}
function typeLabel(s) { return translate('mission_type', s) || s }
function systemLabel(s) { return translate('location', s) || s }

const registered = computed(() => new Set(props.registeredUuids || []))

// ── 聲望種類（舊版後端只有 ranks：當成一種） ──
const scopes = computed(() => {
  const d = data.value
  if (!d) return []
  return d.scopes?.length ? d.scopes : [{ scope: null, ranks: d.ranks || [] }]
})
const scopeIndex = ref(0)
/** 種類名稱：遊戲翻譯（跟任務類型同一份）→ 英文；沒有名稱的叫「聲望」 */
function scopeLabel(sc) { return sc ? (translate('mission_type', sc) || sc) : '聲望' }
/** 沒門檻／門檻對不到的任務，屬不屬於這種聲望：任務會給這種聲望、或沒寫給哪種（只有一種時全部算） */
function inScope(m, sc) {
  if (scopes.value.length <= 1 || !sc) return true
  const list = m.rep_scopes || []
  return !list.length || list.some(x => x.toLowerCase() === sc.toLowerCase())
}
function scopeMissionCount(i) {
  const sc = scopes.value[i]
  const d = data.value
  if (!sc || !d) return 0
  return (sc.ranks || []).reduce((n, r) => n + (r.missions || []).length, 0)
    + [...(d.open || []), ...(d.unmatched || [])].filter(m => inScope(m, sc.scope)).length
}
// 沒門檻 → 各階級（依這種聲望的階級表順序）→ 門檻對不到階級表的
const groups = computed(() => {
  const d = data.value
  const sc = scopes.value[scopeIndex.value] || scopes.value[0]
  if (!d || !sc) return []
  const pre = `${scopeIndex.value}-`
  const out = [{ key: `${pre}open`, title: '不需聲望', threshold: null, missions: (d.open || []).filter(m => inScope(m, sc.scope)) }]
  ;(sc.ranks || []).forEach((r, i) => out.push({ key: `${pre}rank-${i}`, title: translate('rep_rank', r.name) || r.name,
    en: translate('rep_rank', r.name) ? r.name : '', threshold: r.min_reputation, missions: r.missions || [] }))
  const um = (d.unmatched || []).filter(m => inScope(m, sc.scope))
  if (um.length) out.push({ key: `${pre}unmatched`, title: '其他聲望門檻', threshold: null, missions: um })
  return out
})
// 每個任務的藍圖數／已登記數只算一次（key 是任務物件本身）
const bpCounts = computed(() => {
  const map = new Map()
  for (const g of groups.value) {
    for (const m of g.missions) map.set(m, { poolSize: missionPool(m).length, regCount: registeredInPool(m, registered.value) })
  }
  return map
})
function isOpen(key) {
  return openKeys[key] ?? groups.value.find(g => g.key === key)?.missions.length > 0
}
function toggle(key) { openKeys[key] = !isOpen(key) }

async function loadFaction(id) {
  if (!id) { data.value = null; return }
  loading.value = true
  failed.value = false
  Object.keys(openKeys).forEach(k => delete openKeys[k])
  openMission.value = ''
  const body = await getJson(`/mission/factions/${encodeURIComponent(id)}/reputation`)
  if (factionId.value !== id) return
  data.value = body?.success ? body.data : null
  failed.value = !body?.success
  loading.value = false
  scopeIndex.value = 0
  const all = [...(data.value?.open || []), ...(data.value?.unmatched || []),
    ...(data.value?.scopes || [{ ranks: data.value?.ranks || [] }]).flatMap(sc => (sc.ranks || []).flatMap(r => r.missions || []))]
  loadTranslations('mission_type', (data.value?.scopes || []).map(sc => sc.scope))
  loadTranslations('rep_rank', (data.value?.unmatched || []).map(m => m.min_standing_name))
  loadTranslations('rep_rank', (data.value?.scopes || [{ ranks: data.value?.ranks || [] }]).flatMap(sc => (sc.ranks || []).map(r => r.name)))
  loadTranslations('mission_type', all.map(m => m.reward_scope))
  loadTranslations('location', all.flatMap(m => m.star_systems || []))
  loadTranslations('faction', all.flatMap(m => (m.reputation_gained || []).map(r => r.faction)))
}
watch(factionId, loadFaction)
watch(() => props.factionId, id => { if (id) factionId.value = id })
// 指定了勢力：一開始就載入（不用等勢力清單）
if (props.factionId) loadFaction(props.factionId)

let loaded = false
watch(() => props.active, async (v) => {
  if (!v || loaded || fixedId.value) return
  loaded = true
  const body = await getJson('/mission/factions')
  const list = (body?.success ? body.data : []).filter(f => f.mission_count > 0)
  loadTranslations('faction', list.map(f => f.name))
  factions.value = list.sort((a, b) => (a.name_zh || a.name).localeCompare(b.name_zh || b.name, 'zh-Hant'))
}, { immediate: true })
</script>

<style scoped>
.fr-head { display: block; background: none; border: 0; color: var(--sf-text-strong); }
.fr-threshold { color: var(--sf-accent-2-text, var(--sf-accent-2)); font-weight: 600; font-size: .9rem; }
.fr-count { color: var(--sf-text-strong); }
.fr-row { cursor: pointer; }
.fr-detail { background: var(--sf-inset); }
.fr-scope-count { opacity: .75; font-size: .85em; }
</style>
