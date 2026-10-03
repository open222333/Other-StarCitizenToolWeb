<!--
  後台「勢力資料庫」（唯讀）。

  資料是 faction_master（tasks/scdata_sync.py 從 Star Citizen Wiki API 同步，
  列表再逐筆補 /factions/<uuid> 明細），約 64 筆，一次載入、篩選在前端做。
  任務數由本地任務資料庫統計（GET /mission/factions）。點一列展開介紹、
  聲望階級與它發布的任務（GET /mission/factions/<uuid>）。

  中文：名稱與介紹欄位是同步時從翻譯包同前綴的 RepUI 條目比對好的 *_zh
  （見 src/sc_zh.py 的 faction_texts_zh）。

  網址參數：?id=<勢力 uuid> 直接展開那一筆（任務資料庫點勢力名稱會跳過來）。
-->
<template>
  <div>
    <h5 class="mb-3 fw-bold"><i class="bi bi-people me-2 text-primary"></i>勢力資料庫</h5>

    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm"
            style="max-width: 14rem" placeholder="搜尋英文或中文名稱...">
          <MultiSelectFilter v-model="types" label="類型" :options="typeOptions" />
          <div class="form-check form-check-inline mb-0 ms-1">
            <input id="faction-has-rep" v-model="hasReputation" class="form-check-input" type="checkbox">
            <label class="form-check-label small" for="faction-has-rep">只看有聲望</label>
          </div>
          <div class="form-check form-check-inline mb-0">
            <input id="faction-has-missions" v-model="hasMissions" class="form-check-input" type="checkbox">
            <label class="form-check-label small" for="faction-has-missions">只看有任務</label>
          </div>
          <div class="form-check form-check-inline mb-0">
            <input id="faction-missing-zh" v-model="missingZh" class="form-check-input" type="checkbox">
            <label class="form-check-label small" for="faction-missing-zh">只看沒有中文</label>
          </div>
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
                <th class="ps-3">勢力（英文）</th>
                <th>中文</th>
                <th>類型</th>
                <th>合法</th>
                <th>NPC</th>
                <th>聲望</th>
                <th class="text-end">任務數</th>
                <th class="text-end pe-3">給藍圖的任務</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="8" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="8" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取勢力資料失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="load">重試</button>
                </td>
              </tr>
              <tr v-else-if="!filtered.length">
                <td colspan="8" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的勢力。' : '尚無勢力資料' }}
                </td>
              </tr>
              <template v-else>
                <template v-for="f in filtered" :key="f._id">
                  <tr :ref="el => { if (el) rowEls[f._id] = el }" class="row-click" role="button" tabindex="0"
                    :aria-expanded="expandedId === f._id ? 'true' : 'false'"
                    @click="toggle(f)" @keydown.enter="toggle(f)">
                    <td class="ps-3">
                      <i class="bi me-1 text-muted" :class="expandedId === f._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <span class="fw-semibold">{{ f.name }}</span>
                    </td>
                    <td class="text-nowrap">
                      <span v-if="f.name_zh">{{ f.name_zh }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td>{{ f.faction_type || '—' }}</td>
                    <td>
                      <span v-if="f.lawful === true" class="badge text-bg-success">合法</span>
                      <span v-else-if="f.lawful === false" class="badge text-bg-danger">非法</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td>{{ yesNo(f.is_npc) }}</td>
                    <td>{{ f.has_reputation === true ? '有' : f.has_reputation === false ? '無' : '—' }}</td>
                    <td class="text-end">
                      <RouterLink v-if="f.mission_count" :to="{ path: '/missions', query: { faction: f._id } }"
                        @click.stop>{{ f.mission_count }}</RouterLink>
                      <span v-else class="text-muted">0</span>
                    </td>
                    <td class="text-end pe-3">
                      <span v-if="f.blueprint_mission_count">{{ f.blueprint_mission_count }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                  </tr>
                  <tr v-if="expandedId === f._id">
                    <td colspan="8" class="detail-cell ps-5 pe-3 py-3">
                      <div class="row g-3">
                        <div class="col-lg-6">
                          <div class="fw-semibold mb-1">說明</div>
                          <div v-if="f.description_zh" class="pre-line">{{ f.description_zh }}</div>
                          <details v-if="f.description" :open="!f.description_zh" class="mt-1">
                            <summary class="text-muted">英文</summary>
                            <div class="pre-line text-muted mt-1">{{ f.description }}</div>
                          </details>
                          <div v-if="!f.description && !f.description_zh" class="text-muted">—</div>
                          <dl class="row mb-0 mt-2 info-list">
                            <template v-for="row in infoRows(f)" :key="row.label">
                              <dt class="col-4 col-xl-3 text-muted fw-normal">{{ row.label }}</dt>
                              <dd class="col-8 col-xl-9 mb-1">{{ row.value }}</dd>
                            </template>
                          </dl>
                        </div>
                        <div class="col-lg-3">
                          <div class="fw-semibold mb-1">聲望階級</div>
                          <div v-if="!ladder(f).length" class="text-muted">—</div>
                          <div v-for="(step, i) in ladder(f)" :key="i">
                            {{ step.name }}<span v-if="step.value !== null" class="text-muted"> · {{ fmtInt(step.value) }}</span>
                          </div>
                        </div>
                        <div class="col-lg-3">
                          <div class="fw-semibold mb-1">發布的任務</div>
                          <div v-if="detailLoading" class="text-muted">
                            <span class="spinner-border spinner-border-sm me-1"></span>載入中...
                          </div>
                          <div v-else-if="!detail" class="text-warning">讀取失敗。</div>
                          <div v-else-if="!detail.missions?.length" class="text-muted">—</div>
                          <ul v-else class="list-unstyled mb-0 mission-list">
                            <li v-for="m in detail.missions" :key="m._id">
                              <RouterLink :to="{ path: '/missions', query: { id: m._id } }">{{ zhPair(m.title, m.title_zh) }}</RouterLink>
                              <span v-if="m.blueprint_count" class="badge text-bg-primary ms-1">{{ m.blueprint_count }}</span>
                            </li>
                          </ul>
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

    <div v-if="!loading && !loadFailed" class="small text-muted mt-2">
      共 {{ factions.length }} 筆<span v-if="hasActiveFilters"> · 符合 {{ filtered.length }} 筆</span>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { missionApi } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import { fmtInt, zhPair } from '@/utils/mission'

const route = useRoute()

const factions = ref([])
const loading = ref(false)
const loadFailed = ref(false)

const query = ref('')
const types = ref([])
const hasReputation = ref(false)
const hasMissions = ref(false)
const missingZh = ref(false)

const expandedId = ref('')
const detail = ref(null)
const detailLoading = ref(false)
const rowEls = {}

const typeOptions = computed(() =>
  [...new Set(factions.value.map(f => f.faction_type).filter(Boolean))].sort())

const hasActiveFilters = computed(() => !!query.value.trim() || types.value.length > 0
  || hasReputation.value || hasMissions.value || missingZh.value)

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return factions.value.filter(f =>
    (!q || [f.name, f.name_zh].some(t => (t || '').toLowerCase().includes(q)))
    && (!types.value.length || types.value.includes(f.faction_type))
    && (!hasReputation.value || f.has_reputation)
    && (!hasMissions.value || f.mission_count > 0)
    && (!missingZh.value || !f.name_zh))
})

function resetFilters() {
  query.value = ''
  types.value = []
  hasReputation.value = false
  hasMissions.value = false
  missingZh.value = false
}

async function load() {
  loading.value = true
  loadFailed.value = false
  try {
    const res = await missionApi.factions()
    const body = res?.ok ? await res.json().catch(() => null) : null
    if (body?.success) factions.value = body.data || []
    else loadFailed.value = true
  } finally {
    loading.value = false
  }
}

async function open(id) {
  expandedId.value = id
  detail.value = null
  detailLoading.value = true
  const res = await missionApi.faction(id)
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (expandedId.value !== id) return   // 載入途中已經點了別列
  detail.value = body?.success ? body.data : null
  detailLoading.value = false
}

function toggle(f) {
  if (expandedId.value === f._id) {
    expandedId.value = ''
    return
  }
  open(f._id)
}

function yesNo(v) {
  return v === true ? '是' : v === false ? '否' : '—'
}

function infoRows(f) {
  const rows = [
    ['總部', f.headquarters, f.headquarters_zh],
    ['領導', f.leadership, f.leadership_zh],
    ['成立', f.founded, f.founded_zh],
    ['主要業務', f.focus, f.focus_zh],
    ['活動範圍', f.area, f.area_zh],
  ].filter(([, en, zh]) => en || zh)
    .map(([label, en, zh]) => ({ label, value: zh && en && zh !== String(en) ? `${zh}（${en}）` : (zh || en) }))
  const flags = []
  if (f.able_to_arrest !== undefined && f.able_to_arrest !== null) flags.push(`可逮捕：${yesNo(f.able_to_arrest)}`)
  if (f.polices_criminality !== undefined && f.polices_criminality !== null) flags.push(`取締犯罪：${yesNo(f.polices_criminality)}`)
  if (f.default_reaction) flags.push(`預設態度：${typeof f.default_reaction === 'string' ? f.default_reaction : JSON.stringify(f.default_reaction)}`)
  if (flags.length) rows.push({ label: '其他', value: flags.join(' · ') })
  return rows
}

// reputation_ladder 的結構隨上游變動，盡量抓出「名稱 + 門檻」，抓不到就略過
function ladder(f) {
  let list = f.reputation_ladder
  if (list && !Array.isArray(list) && typeof list === 'object') {
    list = list.ranks || list.standings || list.steps || Object.values(list).find(Array.isArray) || []
  }
  if (!Array.isArray(list)) return []
  return list.map(step => {
    if (typeof step === 'string') return { name: step, value: null }
    if (!step || typeof step !== 'object') return null
    const name = step.display_name || step.name || step.title || step.label
    const value = ['min_reputation', 'reputation', 'min', 'threshold', 'value']
      .map(k => step[k]).find(v => typeof v === 'number')
    return name ? { name, value: value ?? null } : null
  }).filter(Boolean)
}

async function openFromRoute() {
  const id = typeof route.query.id === 'string' ? route.query.id : ''
  if (!id || !factions.value.some(f => f._id === id)) return
  resetFilters()
  await open(id)
  await nextTick()
  rowEls[id]?.scrollIntoView({ block: 'center' })
}

watch(() => route.query.id, openFromRoute)

onMounted(async () => {
  await load()
  openFromRoute()
})
</script>

<style scoped>
.row-click { cursor: pointer; }
.detail-cell { background: var(--bs-tertiary-bg); }
.pre-line { white-space: pre-line; }
.info-list { font-size: .85rem; }
.mission-list { max-height: 16rem; overflow-y: auto; }
details > summary { cursor: pointer; }
</style>
