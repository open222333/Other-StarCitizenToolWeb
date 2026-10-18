<!--
  玩家頁「任務」分頁的任務列表（唯讀，mission_master）。

  條件全部來自分頁頂端的共用搜尋卡（filters：{ q, scopes, systems, factions, legality, hasBlueprints }），
  走後端分頁／排序（GET /mission/，玩家 token 只看得到玩家頁面顯示的）。
  欄位：任務、類型、勢力、星系、報酬、聲望異動（每個勢力一行）、冷卻時間（秒數換成中文時間）、藍圖。
  藍圖欄比照藍圖分頁：任務會給的所有藍圖（所有獎勵池合起來去重）裡，自己已登記幾張／共幾張
  （registeredUuids＝我的藍圖的 blueprint_uuid；預設可用的視同已登記）。
  點一列展開：說明、條件、每個獎勵池的藍圖（標已登記／未登記、掉落機率）。
-->
<template>
  <!-- 換頁載入中保留舊的列（只變淡），不讓頁面瞬間變短 -->
  <div ref="rootEl" class="sf-scroll-anchor" :class="{ 'sf-list-loading': loading }">
    <SortSelect v-if="isPhone" class="mb-2" :sort="sort" :options="SORT_OPTIONS" />
    <div class="card scifi-card">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0 sf-stack">
            <thead class="table-light">
              <tr>
                <SortTh :sort="sort" field="title_zh" class="ps-3">任務</SortTh>
                <SortTh :sort="sort" field="reward_scope">類型</SortTh>
                <SortTh :sort="sort" field="giver" class="d-none d-md-table-cell">勢力</SortTh>
                <SortTh :sort="sort" field="star_systems" class="d-none d-lg-table-cell">星系</SortTh>
                <SortTh :sort="sort" field="reward" class="text-end">報酬</SortTh>
                <SortTh :sort="sort" field="reputation" class="text-end">聲望</SortTh>
                <SortTh :sort="sort" field="cooldown" class="text-end">冷卻</SortTh>
                <th class="text-end pe-3 text-nowrap">藍圖</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading && !rows.length">
                <td colspan="8" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="8" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取任務資料失敗。</span>
                  <button class="btn btn-sm btn-primary ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="8" class="text-center py-4 text-muted">沒有符合篩選條件的任務。</td>
              </tr>
              <template v-else>
                <template v-for="m in rows" :key="m._id">
                  <tr class="ms-row" role="button" tabindex="0" :aria-expanded="expandedId === m._id ? 'true' : 'false'"
                    @click="toggle(m)" @keydown.enter.self="toggle(m)">
                    <td class="ps-3 sf-stack__title">
                      <i class="bi me-1 small text-muted" :class="expandedId === m._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <span class="fw-semibold">{{ m.title_zh || m.title }}</span>
                      <span v-if="m.title_zh" class="small text-muted ms-1">{{ m.title }}</span>
                      <span v-if="m.illegal" class="ms-chip ms-chip--warn ms-1">違法</span>
                    </td>
                    <td data-label="類型">{{ m.reward_scope ? typeLabel(m.reward_scope) : '—' }}</td>
                    <td class="d-none d-md-table-cell" data-label="勢力">{{ factionLabel(m) }}</td>
                    <td class="d-none d-lg-table-cell" data-label="星系">{{ (m.star_systems || []).map(systemLabel).join('、') || '—' }}</td>
                    <td class="text-end text-nowrap" data-label="報酬">{{ rewardLabel(m) }}</td>
                    <td class="text-end" data-label="聲望">
                      <div v-for="(r, i) in m.reputation_gained || []" :key="i" class="text-nowrap">
                        <span class="fw-semibold" :class="Number(r.amount) < 0 ? 'ms-bad' : 'ms-good'">{{ fmtRep(r.amount) }}</span>
                        <span v-if="r.faction" class="small text-muted ms-1">{{ factionName(r.faction) }}</span>
                      </div>
                      <span v-if="!m.reputation_gained?.length" class="text-muted">—</span>
                    </td>
                    <td class="text-end text-nowrap" data-label="冷卻">{{ fmtCooldown(m.cooldown_seconds) }}</td>
                    <td class="text-end pe-3 text-nowrap" data-label="藍圖">
                      <span v-if="poolOf(m).length" class="fw-semibold"
                        :class="registeredCount(m) === poolOf(m).length ? 'text-success' : 'ms-count'">
                        {{ registeredCount(m) }} / {{ poolOf(m).length }}
                      </span>
                      <span v-else class="text-muted">—</span>
                    </td>
                  </tr>
                  <tr v-if="expandedId === m._id" class="sf-stack__detail">
                    <td colspan="8" class="ms-detail">
                      <div class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">{{ m.title_zh || m.title }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="expandedId = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <div class="row g-3">
                        <div class="col-lg-6">
                          <div class="mb-2">
                            <span v-for="s in m.star_systems || []" :key="s" class="ms-chip">{{ systemLabel(s) }}</span>
                            <span v-if="m.faction_name || m.mission_giver" class="ms-chip">{{ factionLabel(m) }}</span>
                            <span v-if="m.reward_scope" class="ms-chip">{{ typeLabel(m.reward_scope) }}</span>
                          </div>
                          <div v-if="m.description_zh || m.description" class="small ms-desc">{{ m.description_zh || m.description }}</div>
                          <details v-if="m.description_zh && m.description" class="mt-1">
                            <summary class="small text-muted">英文</summary>
                            <div class="small text-muted ms-desc mt-1">{{ m.description }}</div>
                          </details>
                          <div v-if="conditions(m)" class="small text-muted mt-2">{{ conditions(m) }}</div>
                        </div>
                        <div class="col-lg-6">
                          <div class="small text-muted mb-1">
                            獎勵藍圖<template v-if="poolOf(m).length">：{{ poolOf(m).length }} 種 · 已登記
                              <span class="fw-semibold" :class="registeredCount(m) === poolOf(m).length ? 'text-success' : 'ms-count'">{{ registeredCount(m) }} / {{ poolOf(m).length }}</span></template>
                          </div>
                          <div v-if="!m.blueprint_pools?.length" class="small text-muted">—</div>
                          <div v-for="(pool, i) in m.blueprint_pools || []" :key="pool.pool_uuid || i" class="mb-2">
                            <div v-if="pool.drop_chance !== null && pool.drop_chance !== undefined" class="small ms-chance">
                              機率 {{ fmtChance(pool.drop_chance) }}
                              <span v-if="(pool.items || []).length > 1" class="text-muted fw-normal">（{{ pool.items.length }} 張抽一張）</span>
                            </div>
                            <span v-for="(it, j) in pool.items || []" :key="it.blueprint_uuid || j" class="ms-chip"
                              :class="isRegistered(it) ? 'ms-chip--ok' : 'ms-chip--todo'">
                              <i class="bi me-1" :class="isRegistered(it) ? 'bi-check-circle-fill' : 'bi-circle'"></i>{{ it.name_zh || it.name }}
                              <span class="ms-chip__state">{{ isRegistered(it) ? (it.is_available_by_default && !registered.has(it.blueprint_uuid) ? '預設可用' : '已登記') : '未登記' }}</span>
                            </span>
                          </div>
                        </div>
                      </div>
                    </td>
                  </tr>
                </template>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-2">
      <div class="small text-muted">
        共 {{ total }} 筆<span v-if="total"> · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</span>
      </div>
      <div class="btn-group btn-group-sm">
        <button class="btn btn-scifi-outline" :disabled="offset === 0 || loading" @click="goPage(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-scifi-outline" :disabled="offset + limit >= total || loading" @click="goPage(offset + limit)">下一頁</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'
import { factionLabel, fmtChance, fmtInt, rewardLabel } from '@/utils/mission'
import { loadTranslations, translate } from '@/utils/translations'
import { scrollToListTop } from '@/utils/scrollAnchor'

const props = defineProps({
  /** 帶身分的 fetch（玩家頁傳 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /** 分頁第一次變成可見才載入 */
  active: { type: Boolean, default: true },
  /** 共用搜尋卡的條件 { q, scopes, systems, factions, legality, hasBlueprints } */
  filters: { type: Object, required: true },
  /** 我的藍圖的 blueprint_uuid（預設可用的視同已登記） */
  registeredUuids: { type: Array, default: () => [] },
})

const SORT_OPTIONS = [{ field: 'title_zh', label: '任務' }, { field: 'reward_scope', label: '類型' },
  { field: 'giver', label: '勢力' }, { field: 'reward', label: '報酬' },
  { field: 'reputation', label: '聲望' }, { field: 'cooldown', label: '冷卻' }]
const { isPhone } = useBreakpoint()

const limit = 50
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const expandedId = ref('')

const registered = computed(() => new Set(props.registeredUuids))
function isRegistered(it) {
  return !!it.is_available_by_default || registered.value.has(it.blueprint_uuid)
}
/** 任務會給的所有藍圖（所有獎勵池合起來，同一張只算一次） */
function poolOf(m) {
  const seen = new Map()
  for (const p of m.blueprint_pools || []) {
    for (const it of p.items || []) if (it.blueprint_uuid && !seen.has(it.blueprint_uuid)) seen.set(it.blueprint_uuid, it)
  }
  return [...seen.values()]
}
// 類型、星系的中文從翻譯資料庫查（mission_type 是人工條目、星系走 location），查不到顯示英文
function typeLabel(s) { return translate('mission_type', s) || s }
function systemLabel(s) { return translate('location', s) || s }

function factionName(s) { return translate('faction', s) || s }
function fmtRep(v) {
  const n = Number(v)
  return Number.isFinite(n) ? `${n > 0 ? '+' : ''}${fmtInt(n)}` : '—'
}
/** 冷卻秒數 → 「45 秒」「10 分」「2 時 30 分」「1 天 4 時」 */
function fmtCooldown(sec) {
  const s = Number(sec)
  if (!Number.isFinite(s) || s <= 0) return '—'
  if (s < 60) return `${Math.round(s)} 秒`
  const m = Math.round(s / 60)
  if (m < 60) return `${m} 分`
  const h = Math.floor(m / 60), rm = m % 60
  if (h < 24) return rm ? `${h} 時 ${rm} 分` : `${h} 時`
  const d = Math.floor(h / 24), rh = h % 24
  return rh ? `${d} 天 ${rh} 時` : `${d} 天`
}

function registeredCount(m) {
  return poolOf(m).filter(isRegistered).length
}

function conditions(m) {
  const parts = []
  if (m.shareable) parts.push('可分享')
  parts.push(m.once_only ? '只能接一次' : '可重複接')
  if (m.has_combat) {
    const lo = m.enemy_count_min, hi = m.enemy_count_max
    parts.push(lo || hi ? `戰鬥（敵人 ${lo ?? '?'}–${hi ?? '?'}）` : '戰鬥')
  }
  if (m.has_chain) parts.push('任務鏈')
  if (m.has_prerequisites) parts.push('有前置條件')
  if (m.max_players_per_instance > 1) parts.push(`最多 ${m.max_players_per_instance} 人`)
  return parts.join(' · ')
}

function query(params) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach(x => sp.append(k, x))
    else if (v !== '' && v !== null && v !== undefined) sp.append(k, v)
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

// 點表頭排序（後端，見 src/models/mission.py 的 SORT_FIELDS）
const sort = useTableSort(null, { onChange: () => reload(0) })

let seq = 0
async function reload(newOffset = 0) {
  const my = ++seq
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  expandedId.value = ''
  const f = props.filters
  const res = await props.fetcher(`/mission/${query({
    q: (f.q || '').trim(),
    reward_scope: f.scopes || [],
    star_system: f.systems || [],
    faction_uuid: f.factions || [],
    legality: f.legality || [],
    has_blueprints: f.hasBlueprints ? 1 : '',
    ...sort.params.value,
    limit, offset: newOffset,
  })}`)
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (my !== seq) return   // 已經有更新的查詢
  if (body?.success) {
    rows.value = body.data || []
    total.value = body.total || 0
    loadTranslations('mission_type', rows.value.map(m => m.reward_scope))
    loadTranslations('location', rows.value.flatMap(m => m.star_systems || []))
    loadTranslations('faction', rows.value.flatMap(m => (m.reputation_gained || []).map(r => r.faction)))
  } else {
    rows.value = []
    total.value = 0
    loadFailed.value = true
  }
  loading.value = false
}

function toggle(m) {
  expandedId.value = expandedId.value === m._id ? '' : m._id
}

let loaded = false
watch(() => props.active, (v) => {
  if (!v || loaded) return
  loaded = true
  reload(0)
}, { immediate: true })

// 共用搜尋卡每打一個字就會換一次，等停手 300ms 再查
let timer = null
watch(() => props.filters, () => {
  if (!loaded) return
  clearTimeout(timer)
  timer = setTimeout(() => reload(0), 300)
}, { deep: true })
onBeforeUnmount(() => clearTimeout(timer))

// 上一頁／下一頁：載入後把列表頂端捲回畫面（見 utils/scrollAnchor.js）
const rootEl = ref(null)
async function goPage(newOffset) {
  await reload(newOffset)
  scrollToListTop(rootEl.value)
}

defineExpose({ reload: () => reload(offset.value) })
</script>

<style scoped>
.ms-row { cursor: pointer; }
.ms-detail { background: var(--sf-inset); }
.ms-desc { white-space: pre-line; }
.ms-chance { color: var(--sf-accent-2-text, var(--sf-accent-2)); font-weight: 600; }
.ms-count { color: var(--sf-text-strong); }
.ms-good { color: rgb(var(--bs-success-rgb)); }
.ms-bad { color: rgb(var(--bs-danger-rgb)); }
.ms-chip {
  display: inline-block; font-size: .75rem; margin: 0 .25rem .25rem 0; padding: 0 .5rem;
  border: 1px solid var(--sf-border-hi); border-radius: 999px; color: var(--sf-text-muted);
}
.ms-chip--warn { border-color: rgba(var(--bs-danger-rgb), .6); color: rgb(var(--bs-danger-rgb)); }
.ms-chip--ok { border-color: rgba(var(--bs-success-rgb), .7); color: rgb(var(--bs-success-rgb)); }
.ms-chip--todo { border-style: dashed; }
.ms-chip__state { margin-left: .35rem; font-size: .78em; opacity: .85; }
details > summary { cursor: pointer; }
</style>
