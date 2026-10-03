<!--
  後台「礦物」頁：直接看礦物資料庫（唯讀）。

  跟玩家頁的「礦物」分頁（components/MiningLookup.vue，回波反查／訊號參考）
  刻意分開——後台是用來檢查資料庫內容與中文對照，不提供玩家端的查詢功能。

  資料：
    - 礦床：mining_deposit_master（GET /mining/deposits）
    - 地點：mining_location_master（GET /mining/locations，礦床已展開成名稱）
    - 礦物：沒有獨立的 collection，從礦床的成分（parts）彙整而來
  三者都由 tasks/scdata_sync.py 從 scunpacked-data 同步。資料量小（約 270 個
  礦床、60 多個地點），一次載入、篩選都在前端做。

  玩家頁面顯示：三個分頁都有開關（PlayerVisibleToggle，規則見 src/models/visibility.py）。
  礦床、地點的狀態在各自的文件上；礦物沒有文件，狀態另外拿（GET /item/visibility/minerals）。
  玩家端的 /mining/deposits、/mining/locations 後端本來就會拿掉不顯示的。

  中文對照：一律用 utils/translations.js 即時查資料庫 sc_translations（跟全站
  同一個來源），查不到才退回同步當下存進礦床／地點文件的 *_zh 快照。
  「只看沒有中文」用來找翻譯包缺的條目（要補的話加到
  src/data/sc_translation_manual.json）。
-->
<template>
  <div>
    <h5 class="mb-3 fw-bold"><i class="bi bi-gem me-2 text-primary"></i>礦物資料庫</h5>

    <ul class="nav nav-tabs mb-3">
      <li v-for="t in TABS" :key="t.key" class="nav-item">
        <button type="button" class="nav-link" :class="{ active: tab === t.key }" @click="tab = t.key">
          {{ t.label }}
          <span class="badge bg-secondary-subtle text-secondary-emphasis ms-1">{{ counts[t.key] }}</span>
        </button>
      </li>
    </ul>

    <!-- ── 篩選 ────────────────────────────────────────────── -->
    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm"
            style="max-width: 14rem" placeholder="搜尋英文或中文名稱...">
          <MultiSelectFilter v-if="tab !== 'locations'" v-model="tiers" label="Tier" :options="tierOptions" />
          <MultiSelectFilter v-if="tab === 'locations'" v-model="systems" label="星系" :options="systemOptions" />
          <div class="form-check form-check-inline mb-0 ms-1">
            <input id="mining-missing-zh" v-model="missingZhOnly" class="form-check-input" type="checkbox">
            <label class="form-check-label small" for="mining-missing-zh">只看沒有中文</label>
          </div>
          <select v-model="playerVisible" class="form-select form-select-sm w-auto" aria-label="玩家頁面顯示">
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
        <div v-if="loading" class="text-center py-4 text-muted">
          <span class="spinner-border spinner-border-sm me-2"></span>載入中...
        </div>
        <div v-else-if="loadFailed" class="text-center py-4">
          <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取礦物資料失敗。</span>
          <button class="btn btn-sm btn-link p-0 ms-1" @click="load">重試</button>
        </div>
        <div v-else style="overflow-x:auto">
          <!-- ── 礦物 ── -->
          <table v-if="tab === 'minerals'" class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">礦物（英文）</th>
                <th>中文</th>
                <th>Key</th>
                <th class="text-end">RS</th>
                <th>所在礦床</th>
                <th class="pe-3 text-nowrap">玩家頁面</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredMinerals.length">
                <td colspan="6" class="text-center py-4 text-muted">{{ emptyText }}</td>
              </tr>
              <tr v-for="m in filteredMinerals" :key="m.key">
                <td class="ps-3 fw-semibold">{{ m.name }}</td>
                <td><ZhCell :zh="m.zh" /></td>
                <td class="small text-muted font-monospace">{{ m.key }}</td>
                <td class="small text-end text-nowrap">
                  <span v-if="!m.signatures.length" class="text-muted">—</span>
                  <template v-else>{{ m.signatures.map(fmtInt).join('／') }}</template>
                </td>
                <td class="small">
                  <details>
                    <summary>{{ m.deposits.length }} 個礦床</summary>
                    <ul class="list-unstyled mb-0 mt-1">
                      <li v-for="d in m.deposits" :key="d.id">
                        {{ pair(d.name, d.zh) }}
                        <span class="text-muted">· {{ d.tier || '—' }} · RS {{ fmtInt(d.signature) }} · {{ fmtRange(d.min, d.max) }} · 機率 {{ fmtPct(d.probability) }}</span>
                      </li>
                    </ul>
                  </details>
                </td>
                <td class="pe-3">
                  <PlayerVisibleToggle dataset="minerals" :doc-id="m.key" :row="mineralState(m.key)" />
                </td>
              </tr>
            </tbody>
          </table>

          <!-- ── 礦床 ── -->
          <table v-else-if="tab === 'deposits'" class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">礦床（英文）</th>
                <th>中文</th>
                <th>Tier</th>
                <th class="text-end">RS</th>
                <th>成分</th>
                <th>出現地點</th>
                <th class="pe-3 text-nowrap">玩家頁面</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredDeposits.length">
                <td colspan="7" class="text-center py-4 text-muted">{{ emptyText }}</td>
              </tr>
              <tr v-for="d in filteredDeposits" :key="d._id">
                <td class="ps-3">
                  <div class="fw-semibold">{{ d.deposit_name }}</div>
                  <div class="small text-muted font-monospace">{{ d.key }}</div>
                </td>
                <td><ZhCell :zh="d.zh" /></td>
                <td class="small">{{ d.tier || '—' }}</td>
                <td class="text-end small">{{ fmtInt(d.signature) }}</td>
                <td class="small">
                  <div v-for="(p, idx) in d.parts" :key="idx">
                    {{ pair(p.resource_name || p.resource_key, p.zh) }}
                    <span class="text-muted">· {{ fmtRange(p.min_percentage, p.max_percentage) }} · 機率 {{ fmtPct(p.probability) }}</span>
                  </div>
                </td>
                <td class="small">
                  <span v-if="!d.locations.length" class="text-muted">—</span>
                  <details v-else>
                    <summary>{{ d.locations.length }} 個地點</summary>
                    <ul class="list-unstyled mb-0 mt-1">
                      <li v-for="loc in d.locations" :key="loc.key">
                        {{ pair(loc.name, loc.zh) }}<span class="text-muted"> · {{ loc.system || '—' }}</span>
                      </li>
                    </ul>
                  </details>
                </td>
                <td class="pe-3">
                  <PlayerVisibleToggle dataset="mining_deposits" :doc-id="d._id" :row="depositById.get(d._id) || d" />
                </td>
              </tr>
            </tbody>
          </table>

          <!-- ── 地點 ── -->
          <table v-else class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">地點（英文）</th>
                <th>中文</th>
                <th>星系</th>
                <th>礦床群組</th>
                <th class="pe-3 text-nowrap">玩家頁面</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!filteredLocations.length">
                <td colspan="5" class="text-center py-4 text-muted">{{ emptyText }}</td>
              </tr>
              <tr v-for="loc in filteredLocations" :key="loc._id">
                <td class="ps-3">
                  <div class="fw-semibold">{{ loc.location_name }}</div>
                  <div class="small text-muted font-monospace">{{ loc.provider_name }}</div>
                </td>
                <td><ZhCell :zh="loc.zh" /></td>
                <td class="small">{{ loc.system || '—' }}</td>
                <td class="small">
                  <details v-for="g in loc.groups" :key="g.group_name">
                    <summary>
                      {{ g.group_name }}
                      <span class="text-muted">· {{ fmtPct(g.group_probability) }} · {{ g.deposits.length }} 個礦床</span>
                    </summary>
                    <ul class="list-unstyled mb-1 mt-1 ms-3">
                      <li v-for="dep in g.deposits" :key="dep.resource_uuid">
                        <template v-if="dep.deposit_name">{{ pair(dep.deposit_name, dep.zh) }}</template>
                        <span v-else class="text-muted font-monospace">{{ dep.resource_uuid }}</span>
                        <span class="text-muted"> · {{ dep.tier || '—' }} · {{ fmtPct(dep.relative_probability) }}</span>
                      </li>
                    </ul>
                  </details>
                </td>
                <td class="pe-3">
                  <PlayerVisibleToggle dataset="mining_locations" :doc-id="loc._id" :row="locationById.get(loc._id) || loc" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div v-if="!loading && !loadFailed" class="small text-muted mt-2">
      共 {{ currentTotal }} 筆<span v-if="hasActiveFilters"> · 符合 {{ currentShown }} 筆</span>
    </div>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref, watch } from 'vue'
import { miningApi, visibilityApi } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import PlayerVisibleToggle from '@/components/PlayerVisibleToggle.vue'
import { loadTranslations, translate } from '@/utils/translations'
import { ownSignatures } from '@/utils/miningSignature'

const TABS = [
  { key: 'minerals',  label: '礦物' },
  { key: 'deposits',  label: '礦床' },
  { key: 'locations', label: '地點' },
]
const TIER_ORDER = ['common', 'uncommon', 'rare', 'epic', 'legendary']
const TIER_NONE = '__none__'

// 中文欄：有就顯示，沒有就淡色的「—」
const ZhCell = (props) => props.zh
  ? h('span', props.zh)
  : h('span', { class: 'text-muted' }, '—')
ZhCell.props = ['zh']

const tab = ref('minerals')
const rawDeposits  = ref([])
const rawLocations = ref([])
const loading    = ref(false)
const loadFailed = ref(false)

const query = ref('')
const tiers = ref([])
const systems = ref([])
const missingZhOnly = ref(false)
const playerVisible = ref('')
// 礦物的玩家頁面顯示狀態 {resource_key: {...}}（礦物沒有自己的文件，另外拿）
const mineralStates = ref({})

// 切分頁時，只對那一頁有意義的篩選清掉，避免看不到的條件還在作用
watch(tab, (t) => {
  if (t === 'locations') tiers.value = []
  else systems.value = []
})

async function load() {
  loading.value = true
  loadFailed.value = false
  try {
    const [depRes, locRes, visRes] = await Promise.all([
      miningApi.listDeposits(), miningApi.listLocations(), visibilityApi.minerals()])
    const vis = visRes?.ok ? await visRes.json().catch(() => null) : null
    const dep = depRes?.ok ? await depRes.json().catch(() => null) : null
    const loc = locRes?.ok ? await locRes.json().catch(() => null) : null
    if (!dep?.success || !loc?.success) {
      loadFailed.value = true
      return
    }
    rawDeposits.value  = dep.data || []
    const states = vis?.success ? (vis.data || {}) : {}
    for (const d of rawDeposits.value) {
      for (const p of (d.parts || [])) {
        const key = p.resource_key || p.resource_name
        if (key && !states[key]) states[key] = { player_visible: true }
      }
    }
    mineralStates.value = states
    rawLocations.value = loc.data || []
    loadZh()
  } finally {
    loading.value = false
  }
}

function loadZh() {
  const resources = new Set()
  const depositNames = new Set()
  const locationNames = new Set()
  for (const d of rawDeposits.value) {
    if (d.deposit_name) depositNames.add(d.deposit_name)
    for (const p of (d.parts || [])) if (p.resource_name) resources.add(p.resource_name)
  }
  for (const loc of rawLocations.value) if (loc.location_name) locationNames.add(loc.location_name)
  loadTranslations('mining_resource', [...resources])
  loadTranslations('mining_deposit', [...depositNames])
  loadTranslations('location', [...locationNames])
}

const resourceZh = (p) => translate('mining_resource', p.resource_name) || p.resource_name_zh || ''
const depositZh  = (d) => translate('mining_deposit', d.deposit_name) || d.deposit_name_zh || ''
const locationZh = (l) => translate('location', l.location_name) || l.location_name_zh || ''

// ── 彙整 ────────────────────────────────────────────────────────────

const depositById = computed(() => new Map(rawDeposits.value.map(d => [d._id, d])))
const locationById = computed(() => new Map(rawLocations.value.map(l => [l._id, l])))

// 載入時就把每個礦物都放進 mineralStates（切換時要寫回同一個 reactive 物件）
const mineralState = key => mineralStates.value[key] || { player_visible: true }

function matchesVisible(row) {
  if (!playerVisible.value) return true
  return (row?.player_visible !== false) === (playerVisible.value === '1')
}

// 礦床 uuid → 出現的地點（同名地點只列一次）
const locationsByDeposit = computed(() => {
  const out = new Map()
  for (const loc of rawLocations.value) {
    const entry = { key: `${loc.system}/${loc.location_name}`, name: loc.location_name, zh: locationZh(loc), system: loc.system }
    for (const g of (loc.groups || [])) {
      for (const dep of (g.deposits || [])) {
        if (!out.has(dep.resource_uuid)) out.set(dep.resource_uuid, new Map())
        out.get(dep.resource_uuid).set(entry.key, entry)
      }
    }
  }
  return out
})

const deposits = computed(() => rawDeposits.value.map(d => ({
  ...d,
  zh: depositZh(d),
  parts: (d.parts || []).map(p => ({ ...p, zh: resourceZh(p) })),
  locations: [...(locationsByDeposit.value.get(d._id)?.values() || [])]
    .sort((a, b) => (a.system || '').localeCompare(b.system || '') || a.name.localeCompare(b.name)),
})))

const minerals = computed(() => {
  const byKey = new Map()
  for (const d of deposits.value) {
    d.parts.forEach((p, idx) => {
      const key = p.resource_key || p.resource_name
      if (!key) return
      if (!byKey.has(key)) byKey.set(key, { key, name: p.resource_name || key, zh: p.zh, deposits: [], tiers: new Set() })
      const m = byKey.get(key)
      m.deposits.push({
        // 同一個礦床可能有兩筆同礦物的成分（比例區間不同），id 要帶索引
        id: `${d._id}/${idx}`, name: d.deposit_name, zh: d.zh, tier: d.tier, signature: d.signature,
        min: p.min_percentage, max: p.max_percentage, probability: p.probability,
      })
      m.tiers.add(d.tier || TIER_NONE)
    })
  }
  // 礦物本身沒有 RS（掃描到的是岩石＝礦床），取跟礦物同名的礦床的單顆 RS，
  // 跟玩家頁同一套規則（utils/miningSignature.js）
  for (const m of byKey.values()) {
    m.signatures = ownSignatures(m.name, m.deposits.map(d => ({ deposit_name: d.name, signature: d.signature, tier: d.tier })))
      .map(s => s.signature)
  }
  return [...byKey.values()].sort((a, b) => a.name.localeCompare(b.name))
})

const locations = computed(() => rawLocations.value.map(loc => ({
  ...loc,
  zh: locationZh(loc),
  groups: (loc.groups || []).map(g => ({
    ...g,
    deposits: (g.deposits || []).map(dep => ({
      ...dep,
      zh: dep.deposit_name ? (translate('mining_deposit', dep.deposit_name)
        || depositById.value.get(dep.resource_uuid)?.deposit_name_zh || '') : '',
    })).sort((a, b) => (b.relative_probability || 0) - (a.relative_probability || 0)),
  })),
})))

// ── 篩選 ────────────────────────────────────────────────────────────

const tierOptions = computed(() => {
  const present = new Set(rawDeposits.value.map(d => d.tier || TIER_NONE))
  const known = TIER_ORDER.filter(t => present.has(t))
  const others = [...present].filter(t => t !== TIER_NONE && !TIER_ORDER.includes(t)).sort()
  const opts = [...known, ...others].map(t => ({ value: t, label: t }))
  if (present.has(TIER_NONE)) opts.push({ value: TIER_NONE, label: '無 Tier' })
  return opts
})

const systemOptions = computed(() =>
  [...new Set(rawLocations.value.map(l => l.system).filter(Boolean))].sort())

function matchesText(...texts) {
  const q = query.value.trim().toLowerCase()
  if (!q) return true
  return texts.some(t => (t || '').toLowerCase().includes(q))
}

const filteredMinerals = computed(() => minerals.value.filter(m =>
  matchesText(m.name, m.zh, m.key)
  && (!missingZhOnly.value || !m.zh)
  && (!tiers.value.length || tiers.value.some(t => m.tiers.has(t)))
  && matchesVisible(mineralStates.value[m.key])))

const filteredDeposits = computed(() => deposits.value.filter(d =>
  matchesText(d.deposit_name, d.zh, d.key, ...d.parts.flatMap(p => [p.resource_name, p.zh]))
  && (!missingZhOnly.value || !d.zh || d.parts.some(p => !p.zh))
  && (!tiers.value.length || tiers.value.includes(d.tier || TIER_NONE))
  && matchesVisible(d)))

const filteredLocations = computed(() => locations.value.filter(l =>
  matchesText(l.location_name, l.zh, l.provider_name)
  && (!missingZhOnly.value || !l.zh)
  && (!systems.value.length || systems.value.includes(l.system))
  && matchesVisible(l)))

const counts = computed(() => ({
  minerals: minerals.value.length,
  deposits: rawDeposits.value.length,
  locations: rawLocations.value.length,
}))

const currentTotal = computed(() => counts.value[tab.value])
const currentShown = computed(() => ({
  minerals: filteredMinerals.value.length,
  deposits: filteredDeposits.value.length,
  locations: filteredLocations.value.length,
}[tab.value]))

const hasActiveFilters = computed(() =>
  !!query.value.trim() || tiers.value.length > 0 || systems.value.length > 0 || missingZhOnly.value
  || !!playerVisible.value)

const emptyText = computed(() => hasActiveFilters.value ? '沒有符合篩選條件的資料。' : '尚無資料')

function resetFilters() {
  query.value = ''
  tiers.value = []
  systems.value = []
  missingZhOnly.value = false
  playerVisible.value = ''
}

// ── 顯示格式 ────────────────────────────────────────────────────────

function pair(en, zh) {
  return zh ? `${zh}（${en}）` : en
}
function fmtRange(min, max) {
  if (min === null || min === undefined || max === null || max === undefined) return '—'
  return `${min}–${max}%`
}
function fmtPct(v) {
  if (v === null || v === undefined) return '—'
  const pct = v * 100
  return `${pct >= 10 || pct === 0 ? Math.round(pct) : pct.toFixed(pct >= 1 ? 1 : 2)}%`
}
function fmtInt(v) {
  if (!v) return '—'
  return Math.round(v).toLocaleString('en-US')
}

onMounted(load)
</script>

<style scoped>
details > summary { cursor: pointer; }
</style>
