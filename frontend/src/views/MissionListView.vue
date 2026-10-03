<!--
  後台「任務資料庫」（唯讀）。

  資料是 mission_master（tasks/scdata_sync.py 從 Star Citizen Wiki API 同步，
  /missions?include=blueprints），這裡只讀不寫。1,786 筆左右，走後端分頁／篩選
  （GET /mission/，類型／星系／勢力／合法性可多選）。點一列展開說明、條件與獎勵藍圖。

  中文：標題、說明、發布者、勢力名稱都是同步時從 sc_translations 比對好的 *_zh
  欄位（見 src/sc_zh.py 的 mission_text_zh）；「只看沒有中文」用來找沒對到的。

  網址參數：?id=<任務 uuid> 只列那一筆並展開（藍圖資料庫的「解鎖任務」、勢力資料庫
  點任務名稱會跳過來）；?faction=<勢力 uuid> 預先篩選勢力。
-->
<template>
  <div>
    <h5 class="mb-3 fw-bold"><i class="bi bi-flag me-2 text-primary"></i>任務資料庫</h5>

    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm"
            style="max-width: 14rem" placeholder="搜尋英文或中文標題..." @change="reload(0)">
          <MultiSelectFilter :model-value="scopes" label="類型" :options="facets.reward_scopes" searchable
            @update:model-value="v => { scopes = v; reload(0) }" />
          <MultiSelectFilter :model-value="systems" label="星系" :options="facets.star_systems"
            @update:model-value="v => { systems = v; reload(0) }" />
          <MultiSelectFilter :model-value="factions" label="勢力" :options="factionOptions" searchable
            @update:model-value="v => { factions = v; reload(0) }" />
          <MultiSelectFilter :model-value="legality" label="合法性" :options="LEGALITY_OPTIONS"
            @update:model-value="v => { legality = v; reload(0) }" />
          <div class="form-check form-check-inline mb-0 ms-1">
            <input id="mission-has-bp" v-model="hasBlueprints" class="form-check-input" type="checkbox"
              @change="reload(0)">
            <label class="form-check-label small" for="mission-has-bp">只看會給藍圖</label>
          </div>
          <div class="form-check form-check-inline mb-0">
            <input id="mission-missing-zh" v-model="missingZh" class="form-check-input" type="checkbox"
              @change="reload(0)">
            <label class="form-check-label small" for="mission-missing-zh">只看沒有中文</label>
          </div>
          <select v-model="playerVisible" class="form-select form-select-sm w-auto" aria-label="玩家頁面顯示"
            @change="reload(0)">
            <option value="">玩家頁面：全部</option>
            <option value="1">玩家頁面：顯示</option>
            <option value="0">玩家頁面：不顯示</option>
          </select>
          <button v-if="hasActiveFilters" type="button" class="btn btn-sm btn-link" @click="resetFilters">
            清除全部篩選
          </button>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0 small">
            <thead class="table-light">
              <tr>
                <th class="ps-3">任務（英文）</th>
                <th>中文</th>
                <th>類型</th>
                <th>勢力／NPC</th>
                <th>星系</th>
                <th>合法</th>
                <th class="text-end text-nowrap">報酬</th>
                <th class="text-end text-nowrap">藍圖</th>
                <th class="pe-3 text-nowrap">玩家頁面</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="9" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="9" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取任務資料失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="9" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的任務。' : '尚無任務資料' }}
                </td>
              </tr>
              <template v-else>
                <template v-for="m in rows" :key="m._id">
                  <tr class="row-click" role="button" tabindex="0"
                    :aria-expanded="expandedId === m._id ? 'true' : 'false'"
                    @click="toggle(m)" @keydown.enter="toggle(m)">
                    <td class="ps-3">
                      <i class="bi me-1 text-muted" :class="expandedId === m._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <span class="fw-semibold">{{ m.title }}</span>
                      <div class="text-muted font-monospace ms-3 debug-name">{{ m.debug_name }}</div>
                    </td>
                    <td class="text-nowrap">
                      <span v-if="m.title_zh">{{ m.title_zh }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td>{{ m.reward_scope || '—' }}</td>
                    <td>
                      <RouterLink v-if="m.faction_uuid" :to="{ path: '/factions', query: { id: m.faction_uuid } }"
                        @click.stop>{{ zhPair(m.faction_name, m.faction_name_zh) }}</RouterLink>
                      <span v-else>{{ zhPair(m.mission_giver, m.mission_giver_zh) || '—' }}</span>
                    </td>
                    <td>{{ (m.star_systems || []).join('、') || '—' }}</td>
                    <td>
                      <span class="badge" :class="m.illegal ? 'text-bg-danger' : 'text-bg-success'">
                        {{ m.illegal ? '違法' : '合法' }}
                      </span>
                    </td>
                    <td class="text-end text-nowrap">{{ rewardLabel(m) }}</td>
                    <td class="text-end">
                      <span v-if="m.blueprint_uuids?.length" class="badge text-bg-primary">{{ m.blueprint_uuids.length }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td class="pe-3">
                      <PlayerVisibleToggle dataset="missions" :doc-id="m._id" :row="m" />
                    </td>
                  </tr>
                  <tr v-if="expandedId === m._id">
                    <td colspan="9" class="detail-cell ps-5 pe-3 py-3">
                      <div class="row g-3">
                        <div class="col-lg-7">
                          <div class="fw-semibold mb-1">說明</div>
                          <div v-if="m.description_zh" class="pre-line">{{ m.description_zh }}</div>
                          <details v-if="m.description" :open="!m.description_zh" class="mt-1">
                            <summary class="text-muted">英文</summary>
                            <div class="pre-line text-muted mt-1">{{ m.description }}</div>
                          </details>
                          <div v-if="!m.description && !m.description_zh" class="text-muted">—</div>
                          <div class="mt-2 text-muted">{{ conditions(m) }}</div>
                          <div v-if="reputationLabel(m)" class="mt-1 text-muted">聲望 {{ reputationLabel(m) }}</div>
                          <div v-if="m.hauling_summary?.length" class="mt-1 text-muted">
                            運送 {{ m.hauling_summary.map(haulLabel).join('、') }}
                          </div>
                        </div>
                        <div class="col-lg-5">
                          <div class="fw-semibold mb-1">獎勵藍圖</div>
                          <div v-if="!m.blueprint_pools?.length" class="text-muted">—</div>
                          <div v-for="(pool, i) in m.blueprint_pools || []" :key="pool.pool_uuid || i" class="mb-2">
                            <div v-if="pool.drop_chance !== null && pool.drop_chance !== undefined" class="text-muted">
                              掉落機率 {{ fmtChance(pool.drop_chance) }}
                              <span v-if="(pool.items || []).length > 1"> · {{ pool.items.length }} 張抽一張</span>
                            </div>
                            <ul class="list-unstyled mb-0">
                              <li v-for="(it, j) in pool.items || []" :key="it.blueprint_uuid || j">
                                {{ zhPair(it.name, it.name_zh) }}
                              </li>
                            </ul>
                          </div>
                        </div>
                        <div class="col-12 text-muted meta-line">
                          UUID <span class="font-monospace">{{ m._id }}</span>
                          <span v-if="m.game_version"> · {{ m.game_version }}</span>
                          <span v-if="m.title_key"> · <span class="font-monospace">{{ m.title_key }}</span></span>
                          <template v-if="m.web_url"> · <a :href="m.web_url" target="_blank" rel="noopener noreferrer">wiki</a></template>
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
        <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading"
          @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-outline-secondary" :disabled="offset + limit >= total || loading"
          @click="reload(offset + limit)">下一頁</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { missionApi } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import PlayerVisibleToggle from '@/components/PlayerVisibleToggle.vue'
import { fmtChance, fmtInt, reputationLabel, rewardLabel, zhPair } from '@/utils/mission'

const LEGALITY_OPTIONS = [
  { value: 'legal', label: '合法' },
  { value: 'illegal', label: '違法' },
]

const route = useRoute()
const router = useRouter()

const limit = 50
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const expandedId = ref('')

const facets = ref({ reward_scopes: [], star_systems: [], factions: [] })
const query = ref('')
const scopes = ref([])
const systems = ref([])
const factions = ref([])
const legality = ref([])
const hasBlueprints = ref(false)
const missingZh = ref(false)
const playerVisible = ref('')
// 從別頁跳過來指定的單一任務（?id=）
const onlyId = ref('')

const factionOptions = computed(() => facets.value.factions.map(f => ({
  value: f.uuid, label: `${zhPair(f.name, f.name_zh)}（${f.count}）`,
})))

const hasActiveFilters = computed(() => !!query.value.trim() || scopes.value.length > 0
  || systems.value.length > 0 || factions.value.length > 0 || legality.value.length > 0
  || hasBlueprints.value || missingZh.value || !!playerVisible.value || !!onlyId.value)

async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  const res = await missionApi.list({
    q: query.value.trim(),
    reward_scope: scopes.value,
    star_system: systems.value,
    faction_uuid: factions.value,
    legality: legality.value,
    has_blueprints: hasBlueprints.value ? 1 : '',
    missing_zh: missingZh.value ? 1 : '',
    player_visible: playerVisible.value,
    id: onlyId.value,
    limit, offset: newOffset,
  })
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (body?.success) {
    rows.value = body.data || []
    total.value = body.total || 0
    // 指定單一任務時直接展開
    expandedId.value = onlyId.value && rows.value.length === 1 ? rows.value[0]._id : ''
  } else {
    rows.value = []
    total.value = 0
    loadFailed.value = true
  }
  loading.value = false
}

function resetFilters() {
  query.value = ''
  scopes.value = []
  systems.value = []
  factions.value = []
  legality.value = []
  hasBlueprints.value = false
  missingZh.value = false
  playerVisible.value = ''
  if (onlyId.value || route.query.faction) {
    onlyId.value = ''
    router.replace({ query: {} })
  }
  reload(0)
}

function toggle(m) {
  expandedId.value = expandedId.value === m._id ? '' : m._id
}

function conditions(m) {
  const parts = []
  if (m.cooldown_label) parts.push(`冷卻 ${m.cooldown_label}`)
  if (m.shareable) parts.push('可分享')
  parts.push(m.once_only ? '只能接一次' : '可重複接')
  if (m.has_combat) {
    const lo = m.enemy_count_min, hi = m.enemy_count_max
    parts.push(lo || hi ? `戰鬥（敵人 ${lo ?? '?'}–${hi ?? '?'}）` : '戰鬥')
  }
  if (m.min_crime_stat !== null && m.min_crime_stat !== undefined
      && m.max_crime_stat !== null && m.max_crime_stat !== undefined) {
    parts.push(`犯罪等級 ${m.min_crime_stat}–${m.max_crime_stat}`)
  }
  if (m.min_standing_name && !m.min_standing_name.includes('PLACEHOLDER')) parts.push(`聲望門檻 ${m.min_standing_name}`)
  if (m.has_chain) parts.push('任務鏈')
  if (m.has_prerequisites) parts.push('有前置條件')
  if (m.max_players_per_instance > 1) parts.push(`最多 ${m.max_players_per_instance} 人`)
  return parts.join(' · ')
}

function haulLabel(h) {
  const lo = h.min_amount, hi = h.max_amount
  const qty = lo === hi || hi === null || hi === undefined ? fmtInt(lo) : `${fmtInt(lo)}–${fmtInt(hi)}`
  return `${h.name} × ${qty}`
}

async function loadFacets() {
  const res = await missionApi.facets()
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (body?.success) facets.value = { reward_scopes: [], star_systems: [], factions: [], ...body.data }
}

function applyRouteQuery() {
  onlyId.value = typeof route.query.id === 'string' ? route.query.id : ''
  if (typeof route.query.faction === 'string' && route.query.faction) {
    factions.value = [route.query.faction]
  }
}

// 已經在這頁時又從別頁連過來（例如勢力頁點了另一個任務）
watch(() => [route.query.id, route.query.faction], () => {
  applyRouteQuery()
  reload(0)
})

onMounted(() => {
  applyRouteQuery()
  loadFacets()
  reload(0)
})
</script>

<style scoped>
.row-click { cursor: pointer; }
.detail-cell { background: var(--bs-tertiary-bg); }
.debug-name { font-size: .75rem; }
.meta-line { font-size: .75rem; }
.pre-line { white-space: pre-line; }
details > summary { cursor: pointer; }
</style>
