<!--
  玩家頁「資料庫 › 礦物」：每種礦物可以在哪裡挖到（唯讀，不用登入）。

  資料跟「工具箱 › 礦物回波」（components/MiningLookup.vue）同一份 scunpacked-data：
    - GET /mining/deposits：礦床成分（parts：礦物、含量範圍 %、出現機率）
    - GET /mining/locations：各地點（星系、類型）的礦床群組（船載／地面載具／手持／採集）與各礦床的佔比
  兩份合起來：礦物 → 有哪些地點的哪一種採集方式會出現含有它的礦床。
  「出現率」＝那一類礦床在該地點同一群組裡的佔比 × 礦床含有這種礦物的機率（遊戲資料的相對值，不是實際刷新次數）。
  打撈、殘骸、化石、戰利品箱這些群組不列。
-->
<template>
  <div>
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-4">
            <label class="form-label small fw-semibold mb-1" for="mdb-q">礦物名稱</label>
            <input id="mdb-q" v-model="query" type="search" class="form-control form-control-sm"
              placeholder="中英文皆可" autocomplete="off">
          </div>
          <div class="col-6 col-md-2">
            <label class="form-label small fw-semibold mb-1" for="mdb-system">星系</label>
            <select id="mdb-system" v-model="system" class="form-select form-select-sm">
              <option value="">全部</option>
              <option v-for="s in systems" :key="s" :value="s">{{ systemLabel(s) }}</option>
            </select>
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label small fw-semibold mb-1" for="mdb-place">地點</label>
            <select id="mdb-place" v-model="place" class="form-select form-select-sm">
              <option value="">全部</option>
              <option v-for="p in placeOptions" :key="p.key" :value="p.key">{{ p.label }}</option>
            </select>
          </div>
          <div class="col-12 col-md-3">
            <label class="form-label small fw-semibold mb-1" for="mdb-method">採集方式</label>
            <select id="mdb-method" v-model="method" class="form-select form-select-sm">
              <option value="">全部</option>
              <option v-for="m in METHODS" :key="m.key" :value="m.key">{{ m.label }}</option>
            </select>
          </div>
        </div>
        <div v-if="hasFilter" class="d-flex flex-wrap align-items-center gap-2 mt-2">
          <span class="small text-muted">符合 {{ rows.length }} 種礦物</span>
          <button type="button" class="btn btn-sm btn-warning ms-auto" @click="clearFilters">清除篩選</button>
        </div>
      </div>
    </div>

    <SfState :loading="loading" :error="error" :empty="loaded && !rows.length"
      :empty-text="minerals.length ? '沒有符合條件的礦物。' : '尚無礦物資料。'" @retry="load">
      <SortSelect v-if="isPhone" class="mb-2" :sort="sort" :options="SORT_OPTIONS" />
      <div :class="cardClass">
        <div class="card-body p-0">
          <div style="overflow-x: auto">
            <table class="table table-hover align-middle mb-0 sf-stack">
              <thead class="table-light">
                <tr>
                  <SortTh :sort="sort" field="name" class="ps-3">礦物</SortTh>
                  <th>採集方式</th>
                  <SortTh :sort="sort" field="places" class="text-end">地點數</SortTh>
                  <SortTh :sort="sort" field="content" class="text-end">最高含量</SortTh>
                  <SortTh :sort="sort" field="chance" class="text-end">最高出現率</SortTh>
                  <th class="d-none d-lg-table-cell">主要地點</th>
                  <th class="pe-3"></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="m in sort.sorted.value" :key="m.key">
                  <tr>
                    <td class="ps-3 sf-stack__title">
                      <span class="fw-semibold">{{ m.name_zh || m.name }}</span>
                      <span v-if="m.name_zh" class="small text-muted ms-1">{{ m.name }}</span>
                      <span v-if="m.uex_code" class="sf-chip sf-chip--accent ms-1">{{ m.uex_code }}</span>
                    </td>
                    <td data-label="採集方式">
                      <span v-for="k in m.methods" :key="k" class="sf-chip me-1">{{ methodLabel(k) }}</span>
                    </td>
                    <td class="text-end" data-label="地點數">{{ m.places }}</td>
                    <td class="text-end text-nowrap" data-label="最高含量">{{ pct(m.content) }}</td>
                    <td class="text-end text-nowrap" data-label="最高出現率">{{ pct(m.chance * 100, 2) }}</td>
                    <td class="d-none d-lg-table-cell small" data-label="主要地點">
                      {{ m.top.map(o => placeLabel(o)).join('、') }}<template v-if="m.places > m.top.length"> …</template>
                    </td>
                    <td class="text-end pe-3 sf-stack__actions">
                      <button type="button" class="btn btn-sm btn-info text-nowrap" :aria-expanded="openKey === m.key ? 'true' : 'false'"
                        @click="openKey = openKey === m.key ? '' : m.key">
                        <i class="bi me-1" :class="openKey === m.key ? 'bi-chevron-up' : 'bi-chevron-down'"></i>地點
                      </button>
                    </td>
                  </tr>
                  <tr v-if="openKey === m.key" class="sf-stack__detail">
                    <td colspan="7" class="mdb-detail">
                      <div class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">{{ m.name_zh || m.name }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="openKey = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <table class="table table-sm align-middle mb-0 mdb-sub">
                        <thead>
                          <tr>
                            <th>地點</th><th>星系</th><th>類型</th><th>採集方式</th><th>礦床</th>
                            <th class="text-end">含量</th><th class="text-end">出現率</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="o in m.occurrences" :key="o.key">
                            <td data-label="地點" class="fw-semibold">{{ placeLabel(o) }}</td>
                            <td data-label="星系">{{ systemLabel(o.system) }}</td>
                            <td data-label="類型">{{ typeLabel(o.type) }}</td>
                            <td data-label="採集方式">{{ methodLabel(o.method) }}</td>
                            <td data-label="礦床">{{ o.deposits.join('、') }}</td>
                            <td class="text-end text-nowrap" data-label="含量">{{ range(o.min, o.max) }}</td>
                            <td class="text-end text-nowrap" data-label="出現率">{{ pct(o.chance * 100, 2) }}</td>
                          </tr>
                        </tbody>
                      </table>
                    </td>
                  </tr>
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
import { computed, ref, watch } from 'vue'
import SfState from '@/components/SfState.vue'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 分頁第一次變成可見才載入 */
  active: { type: Boolean, default: true },
  cardClass: { type: String, default: 'card' },
})

/** 地點的礦床群組 → 採集方式（其餘群組：打撈、殘骸、化石、戰利品箱不列） */
const METHODS = [
  { key: 'ship', label: '船載採礦', re: /^spaceship/i },
  { key: 'vehicle', label: '地面載具', re: /^groundvehicle/i },
  { key: 'fps', label: '手持採礦', re: /^fps/i },
  { key: 'harvest', label: '採集', re: /^(ha(r)?vestables?|plants?)$/i },
]
const methodOf = group => METHODS.find(m => m.re.test(group || ''))?.key || ''
const methodLabel = k => METHODS.find(m => m.key === k)?.label || k
const TYPE_LABEL = { planet: '行星', moon: '衛星', lagrange: '拉格朗日點', belt: '小行星帶', cluster: '小行星群',
  cave: '洞穴', special: '特殊地點' }
const typeLabel = t => (t ? TYPE_LABEL[t] || t : '—')
const SYSTEM_LABEL = { Stanton: '斯坦頓', Pyro: '派羅', Nyx: '尼克斯' }
const systemLabel = s => (s ? (SYSTEM_LABEL[s] ? `${SYSTEM_LABEL[s]}（${s}）` : s) : '—')
const placeLabel = o => (o.name_zh && o.name_zh !== o.name ? `${o.name_zh}（${o.name}）` : o.name)
// 遊戲資料裡還沒補名稱的會是 <= PLACEHOLDER =>，改用 key
const realName = s => (s && !s.includes('<=') ? s : '')
const pct = (v, digits = 0) => (v == null || !Number.isFinite(v) ? '—'
  : `${Number(v).toLocaleString('en-US', { maximumFractionDigits: digits })}%`)
const range = (min, max) => (min == null || max == null ? '—' : min === max ? `${min}%` : `${min}–${max}%`)

// ── 資料 ──
const deposits = ref([])
const locations = ref([])
const loading = ref(false)
const loaded = ref(false)
const error = ref('')
async function load() {
  loading.value = true
  error.value = ''
  const [d, l] = await Promise.all(['/mining/deposits', '/mining/locations'].map(async url => {
    const res = await props.fetcher(url)
    const body = res ? await res.json().catch(() => null) : null
    return res?.ok && body?.success ? body.data || [] : null
  }))
  loading.value = false
  if (!d || !l) {
    error.value = '讀取失敗。'
    return
  }
  deposits.value = d
  locations.value = l
  loaded.value = true
}
watch(() => props.active, on => { if (on && !loaded.value && !loading.value) load() }, { immediate: true })

/** 礦物 → 出現的地方（同一個地點、同一種採集方式合成一筆：含量取最大範圍、出現率取最高） */
const minerals = computed(() => {
  const depById = new Map(deposits.value.map(d => [d._id, d]))
  const byKey = new Map()
  for (const loc of locations.value) {
    for (const g of loc.groups || []) {
      const method = methodOf(g.group_name)
      if (!method) continue
      for (const dref of g.deposits || []) {
        const dep = depById.get(dref.resource_uuid)
        if (!dep) continue
        for (const p of dep.parts || []) {
          const key = p.resource_key || p.resource_name
          if (!key) continue
          let m = byKey.get(key)
          if (!m) {
            m = { key, name: realName(p.resource_name) || key.replace(/_/g, ' '), name_zh: p.resource_name_zh || '', uex_code: p.uex?.code || '',
              occ: new Map() }
            byKey.set(key, m)
          }
          const okey = `${loc.system}|${loc.location_name}|${method}`
          const chance = (dref.relative_probability ?? 0) * (p.probability ?? 1)
          let o = m.occ.get(okey)
          if (!o) {
            o = { key: okey, system: loc.system, name: loc.location_name, name_zh: loc.location_name_zh, type: loc.location_type,
              method, deposits: [], min: p.min_percentage, max: p.max_percentage, chance: 0 }
            m.occ.set(okey, o)
          }
          const depName = dep.deposit_name_zh || dep.deposit_name
          if (depName && !o.deposits.includes(depName)) o.deposits.push(depName)
          if (p.min_percentage != null && (o.min == null || p.min_percentage < o.min)) o.min = p.min_percentage
          if (p.max_percentage != null && (o.max == null || p.max_percentage > o.max)) o.max = p.max_percentage
          o.chance = Math.max(o.chance, chance)
        }
      }
    }
  }
  return [...byKey.values()].map(m => ({ ...m, all: [...m.occ.values()] }))
})

// ── 篩選 ──
const query = ref('')
const system = ref('')
const place = ref('')
const method = ref('')
const systems = computed(() => [...new Set(locations.value.map(l => l.system).filter(Boolean))].sort())
const placeOptions = computed(() => {
  const seen = new Map()
  for (const l of locations.value) {
    if (!l.location_name || (system.value && l.system !== system.value)) continue
    const key = `${l.system}|${l.location_name}`
    if (!seen.has(key)) seen.set(key, { key, label: placeLabel({ name: l.location_name, name_zh: l.location_name_zh }), system: l.system })
  }
  return [...seen.values()].sort((a, b) => a.system.localeCompare(b.system) || a.label.localeCompare(b.label))
})
watch(system, () => { if (place.value && !placeOptions.value.some(p => p.key === place.value)) place.value = '' })
const hasFilter = computed(() => !!(query.value.trim() || system.value || place.value || method.value))
function clearFilters() {
  query.value = ''
  system.value = ''
  place.value = ''
  method.value = ''
}

const rows = computed(() => {
  const q = query.value.trim().toLowerCase()
  const out = []
  for (const m of minerals.value) {
    if (q && ![m.name, m.name_zh, m.key, m.uex_code].some(x => (x || '').toLowerCase().includes(q))) continue
    const occ = m.all.filter(o => (!system.value || o.system === system.value)
      && (!place.value || `${o.system}|${o.name}` === place.value)
      && (!method.value || o.method === method.value))
    if (!occ.length) continue
    occ.sort((a, b) => b.chance - a.chance || (b.max ?? 0) - (a.max ?? 0))
    const placeKeys = new Set(occ.map(o => `${o.system}|${o.name}`))
    const top = []
    for (const o of occ) {
      if (top.length >= 3) break
      if (!top.some(x => x.system === o.system && x.name === o.name)) top.push(o)
    }
    out.push({
      key: m.key, name: m.name, name_zh: m.name_zh, uex_code: m.uex_code, occurrences: occ, top,
      methods: METHODS.map(x => x.key).filter(k => occ.some(o => o.method === k)),
      places: placeKeys.size,
      content: Math.max(...occ.map(o => o.max ?? 0)),
      chance: Math.max(...occ.map(o => o.chance)),
    })
  }
  return out
})

// ── 排序、展開 ──
const SORT_OPTIONS = [{ field: 'name', label: '礦物' }, { field: 'places', label: '地點數' },
  { field: 'content', label: '最高含量' }, { field: 'chance', label: '最高出現率' }]
const sort = useTableSort(rows, { key: 'name', accessors: { name: m => m.name_zh || m.name } })
const openKey = ref('')
const { isPhone } = useBreakpoint()
</script>

<style scoped>
.mdb-detail { background: var(--sf-chip-bg); }
.mdb-sub { --bs-table-bg: transparent; font-size: .95rem; }
.mdb-sub th { font-size: .8rem; color: var(--sf-text-muted); font-weight: 600; }
</style>
