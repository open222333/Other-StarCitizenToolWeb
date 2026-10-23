<!--
  玩家頁「任務 › 勢力聲望」：輸入勢力名稱（自動完成，中英文皆可）選一個勢力，列出它的聲望階級（名稱＋門檻分數），
  每一階底下是「要到這個階級才能接」的任務（任務的 min_standing_name 對階級名稱，
  GET /mission/factions/<id>/reputation）；沒有門檻的、門檻對不到階級表的各自一組。
  點任務展開細節（MissionDetail：說明、條件、報酬、聲望異動、冷卻、聲望門檻、獎勵藍圖登記狀況）。
  任務的藍圖欄比照任務列表：任務會給的藍圖自己已登記幾張（預設可用的視同已登記）。
-->
<template>
  <div>
    <div class="row g-2 align-items-end mb-3">
      <div class="col-12 col-md-6">
        <label class="form-label small fw-semibold mb-1" for="fr-faction">勢力</label>
        <AutocompleteField id="fr-faction" v-model="factionQuery" :search="searchFactions" :get-label="factionName"
          :get-meta="f => `${f.mission_count} 個任務`" :min-chars="0" :debounce-ms="0"
          aria-label="勢力" placeholder="輸入勢力名稱（中英文皆可）" @select="f => { factionId = f?._id || '' }" />
      </div>
    </div>

    <div v-if="!factionId" class="text-muted small">—</div>
    <div v-else-if="loading" class="text-muted small">載入中…</div>
    <div v-else-if="failed" class="text-warning small">讀取失敗。</div>
    <template v-else-if="data">
      <div v-for="g in groups" :key="g.key" class="card scifi-card mb-2">
        <div class="card-body py-2">
          <button type="button" class="btn btn-link p-0 text-start w-100 fr-head" :aria-expanded="isOpen(g.key) ? 'true' : 'false'"
            @click="toggle(g.key)">
            <i class="bi me-1" :class="isOpen(g.key) ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
            <span class="fw-semibold">{{ g.title }}</span>
            <span v-if="g.threshold !== null && g.threshold !== undefined" class="fr-threshold ms-2">{{ fmtInt(g.threshold) }} 聲望</span>
            <span class="small text-muted ms-2">{{ g.missions.length }} 個任務</span>
          </button>
          <div v-if="isOpen(g.key)" class="mt-2">
            <div v-if="!g.missions.length" class="small text-muted">—</div>
            <div v-else style="overflow-x:auto">
              <table class="table table-sm table-hover align-middle mb-0 sf-stack">
                <thead class="table-light">
                  <tr>
                    <th class="ps-2">任務</th>
                    <th>類型</th>
                    <th class="d-none d-md-table-cell">星系</th>
                    <th class="text-end">報酬</th>
                    <th class="text-end pe-2">藍圖</th>
                  </tr>
                </thead>
                <tbody>
                  <template v-for="m in g.missions" :key="m._id">
                  <tr class="fr-row" role="button" tabindex="0" :aria-expanded="openMission === m._id ? 'true' : 'false'"
                    @click="openMission = openMission === m._id ? '' : m._id" @keydown.enter.self="openMission = openMission === m._id ? '' : m._id">
                    <td class="ps-2 sf-stack__title">
                      <i class="bi me-1 small text-muted" :class="openMission === m._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <span class="fw-semibold">{{ m.title_zh || m.title }}</span>
                      <span v-if="m.title_zh" class="small text-muted ms-1">{{ m.title }}</span>
                      <span v-if="m.illegal" class="fr-chip fr-chip--warn ms-1">違法</span>
                      <span v-if="g.key === 'unmatched' && m.min_standing_name" class="fr-chip ms-1">{{ m.min_standing_name }}</span>
                    </td>
                    <td data-label="類型">{{ m.reward_scope ? typeLabel(m.reward_scope) : '—' }}</td>
                    <td class="d-none d-md-table-cell" data-label="星系">{{ (m.star_systems || []).map(systemLabel).join('、') || '—' }}</td>
                    <td class="text-end text-nowrap" data-label="報酬">{{ rewardLabel(m) }}</td>
                    <td class="text-end text-nowrap pe-2" data-label="藍圖">
                      <span v-if="poolOf(m).length" class="fw-semibold"
                        :class="registeredCount(m) === poolOf(m).length ? 'text-success' : 'fr-count'">{{ registeredCount(m) }} / {{ poolOf(m).length }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                  </tr>
                  <tr v-if="openMission === m._id" class="sf-stack__detail">
                    <td colspan="5" class="fr-detail">
                      <div class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">{{ m.title_zh || m.title }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="openMission = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <MissionDetail :mission="m" :registered-uuids="registeredUuids" :ladders="ladderMap" full />
                    </td>
                  </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import AutocompleteField from '@/components/AutocompleteField.vue'
import MissionDetail from '@/components/MissionDetail.vue'
import { fmtInt, rewardLabel } from '@/utils/mission'
import { loadTranslations, translate } from '@/utils/translations'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 第一次變成可見才載入 */
  active: { type: Boolean, default: true },
  /** 我的藍圖的 blueprint_uuid（預設可用的視同已登記） */
  registeredUuids: { type: Array, default: () => [] },
})

const factions = ref([])
const factionId = ref('')
const factionQuery = ref('')
const openMission = ref('')
// 這個勢力的聲望階級表，給 MissionDetail 換算聲望門檻分數
const ladderMap = computed(() => (data.value
  ? { [data.value.faction._id]: (data.value.ranks || []).map(r => ({ name: r.name, min_reputation: r.min_reputation })) }
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

const registered = computed(() => new Set(props.registeredUuids))
function poolOf(m) {
  const seen = new Map()
  for (const p of m.blueprint_pools || []) {
    for (const it of p.items || []) if (it.blueprint_uuid && !seen.has(it.blueprint_uuid)) seen.set(it.blueprint_uuid, it)
  }
  return [...seen.values()]
}
function registeredCount(m) {
  return poolOf(m).filter(it => it.is_available_by_default || registered.value.has(it.blueprint_uuid)).length
}

// 沒門檻 → 各階級（依階級表順序）→ 門檻對不到階級表的
const groups = computed(() => {
  const d = data.value
  if (!d) return []
  const out = [{ key: 'open', title: '不需聲望', threshold: null, missions: d.open || [] }]
  ;(d.ranks || []).forEach((r, i) => out.push({ key: `rank-${i}`, title: r.name, threshold: r.min_reputation, missions: r.missions || [] }))
  if ((d.unmatched || []).length) out.push({ key: 'unmatched', title: '其他聲望門檻', threshold: null, missions: d.unmatched })
  return out
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
  const all = [...(data.value?.open || []), ...(data.value?.unmatched || []), ...(data.value?.ranks || []).flatMap(r => r.missions)]
  loadTranslations('mission_type', all.map(m => m.reward_scope))
  loadTranslations('location', all.flatMap(m => m.star_systems || []))
  loadTranslations('faction', all.flatMap(m => (m.reputation_gained || []).map(r => r.faction)))
}
watch(factionId, loadFaction)

let loaded = false
watch(() => props.active, async (v) => {
  if (!v || loaded) return
  loaded = true
  const body = await getJson('/mission/factions')
  const list = (body?.success ? body.data : []).filter(f => f.mission_count > 0)
  loadTranslations('faction', list.map(f => f.name))
  factions.value = list.sort((a, b) => (a.name_zh || a.name).localeCompare(b.name_zh || b.name, 'zh-Hant'))
}, { immediate: true })
</script>

<style scoped>
.fr-head { color: var(--sf-text-strong); text-decoration: none; }
.fr-threshold { color: var(--sf-accent-2-text, var(--sf-accent-2)); font-weight: 600; font-size: .9rem; }
.fr-count { color: var(--sf-text-strong); }
.fr-row { cursor: pointer; }
.fr-detail { background: var(--sf-inset); }
.fr-chip {
  display: inline-block; font-size: .72rem; padding: 0 .45rem;
  border: 1px solid var(--sf-border-hi); border-radius: 999px; color: var(--sf-text-muted);
}
.fr-chip--warn { border-color: rgba(var(--bs-danger-rgb), .6); color: rgb(var(--bs-danger-rgb)); }
</style>
