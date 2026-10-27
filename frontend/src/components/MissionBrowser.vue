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
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中…
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="8" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取任務資料失敗。</span>
                  <button type="button" class="btn btn-sm btn-primary ms-1" @click="reload(offset)"><i class="bi bi-arrow-clockwise me-1"></i>重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="8" class="text-center py-4 text-muted">沒有符合篩選條件的任務。</td>
              </tr>
              <template v-else>
                <template v-for="{ m, poolSize, regCount } in rowViews" :key="m._id">
                  <tr class="ms-row" role="button" tabindex="0" :aria-expanded="expandedId === m._id ? 'true' : 'false'"
                    @click="toggle(m)" @keydown.enter.self="toggle(m)" @keydown.space.self.prevent="toggle(m)">
                    <td class="ps-3 sf-stack__title">
                      <i class="bi me-1 small text-muted" :class="expandedId === m._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <span class="fw-semibold">{{ m.title_zh || m.title }}</span>
                      <span v-if="m.title_zh" class="small text-muted ms-1">{{ m.title }}</span>
                      <span v-if="m.illegal" class="sf-chip sf-chip--warn ms-1">違法</span>
                    </td>
                    <td data-label="類型">{{ m.reward_scope ? typeLabel(m.reward_scope) : '—' }}</td>
                    <td class="d-none d-md-table-cell" data-label="勢力">{{ factionLabel(m) }}</td>
                    <td class="d-none d-lg-table-cell" data-label="星系">{{ (m.star_systems || []).map(systemLabel).join('、') || '—' }}</td>
                    <td class="text-end text-nowrap" data-label="報酬">{{ rewardLabel(m) }}</td>
                    <td class="text-end" data-label="聲望">
                      <div v-for="(r, i) in m.reputation_gained || []" :key="i" class="text-nowrap">
                        <span class="fw-semibold" :class="Number(r.amount) < 0 ? 'sf-bad' : 'sf-good'">{{ fmtRep(r.amount) }}</span>
                        <span v-if="r.faction" class="small text-muted ms-1">{{ factionName(r.faction) }}</span>
                      </div>
                      <span v-if="!m.reputation_gained?.length" class="text-muted">—</span>
                    </td>
                    <td class="text-end text-nowrap" data-label="冷卻">{{ fmtCooldown(m.cooldown_seconds) }}</td>
                    <td class="text-end pe-3 text-nowrap" data-label="藍圖">
                      <span v-if="poolSize" class="fw-semibold"
                        :class="regCount === poolSize ? 'text-success' : 'ms-count'">
                        {{ regCount }} / {{ poolSize }}
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
                      <MissionDetail :mission="m" :registered-uuids="registeredUuids" :ladders="ladders" :fetcher="fetcher" @registered="$emit('registered')" />
                    </td>
                  </tr>
                </template>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <SfPager class="mt-2" :total="total" :offset="offset" :limit="limit" :loading="loading" @page="goPage" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import SfPager from '@/components/SfPager.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'
import { factionLabel, fmtCooldown, fmtRep, rewardLabel } from '@/utils/mission'
import MissionDetail from '@/components/MissionDetail.vue'
import { missionPool, registeredInPool } from '@/utils/missionBlueprints'
import { loadTranslations, translate } from '@/utils/translations'
import { scrollToListTop } from '@/utils/scrollAnchor'

defineEmits(['registered'])
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
// 類型、星系的中文從翻譯資料庫查（mission_type 是人工條目、星系走 location），查不到顯示英文
function typeLabel(s) { return translate('mission_type', s) || s }
function systemLabel(s) { return translate('location', s) || s }


function factionName(s) { return translate('faction', s) || s }
// 聲望門檻的分數表（GET /mission/factions/ladders），傳給 MissionDetail
const ladders = ref({})

// 每列的藍圖數／已登記數只算一次（不要在模板裡每列呼叫好幾次 missionPool）
const rowViews = computed(() => rows.value.map(m => ({
  m, poolSize: missionPool(m).length, regCount: registeredInPool(m, registered.value),
})))

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
    has_reward: f.hasReward ? 1 : '',
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
  props.fetcher('/mission/factions/ladders').then(res => (res?.ok ? res.json() : null))
    .then(body => { if (body?.success) ladders.value = body.data || {} }).catch(() => {})
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
.ms-count { color: var(--sf-text-strong); }
</style>
