<!--
  資料庫 › 維克洛：維克洛（Wikelo Emporium）的全部交易（GET /mission/wikelo，同步項目「維克洛」），
  每筆一列（交易、獎勵、需要幾項、維克洛聲望），點一列展開要交的物品與數量、獎勵、前置條件。
  搜尋：交易名稱、獎勵或需求物品名稱（中英文），在前端過濾（全部不到一百筆）。
-->
<template>
  <div class="sf-split">
    <div class="card scifi-card sf-search mb-3">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-6">
            <label class="form-label small fw-semibold mb-1" for="wk-q">搜尋</label>
            <input id="wk-q" v-model="query" type="search" class="form-control" placeholder="交易、獎勵或需要的物品（中英文）" autocomplete="off">
          </div>
          <div class="col-12 col-md-6">
            <label class="form-label small fw-semibold mb-1" for="wk-kind">獎勵</label>
            <MultiSelectFilter id="wk-kind" v-model="kinds" :options="KINDS" label="獎勵種類" placeholder="全部" block />
          </div>
        </div>
      </div>
    </div>
    <SfState :loading="loading" :error="error" :empty="!loading && !error && !shown.length"
      :empty-text="rows.length ? '沒有符合條件的交易' : '尚無維克洛交易資料'" @retry="load">
      <SortSelect v-if="isPhone" class="mb-2" :sort="sort" :options="SORT_OPTIONS" />
      <div class="card scifi-card">
        <div class="card-body p-0">
          <div style="overflow-x: auto">
            <table class="table table-hover align-middle mb-0 sf-stack">
              <thead class="table-light">
                <tr>
                  <SortTh :sort="sort" field="title" class="ps-3">交易</SortTh>
                  <SortTh :sort="sort" field="reward">獎勵</SortTh>
                  <SortTh :sort="sort" field="reqs" class="text-end">需要</SortTh>
                  <SortTh :sort="sort" field="rep" class="text-end pe-3">維克洛聲望</SortTh>
                </tr>
              </thead>
              <tbody>
                <template v-for="t in sort.sorted.value" :key="t._id">
                  <tr class="wk-row" role="button" tabindex="0" :aria-expanded="openId === t._id ? 'true' : 'false'"
                    @click="toggle(t)" @keydown.enter.self="toggle(t)" @keydown.space.self.prevent="toggle(t)">
                    <td class="ps-3 sf-stack__title">
                      <i class="bi me-1 small text-muted" :class="openId === t._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <span class="sf-name">
                        <span class="fw-semibold">{{ t.title_zh || t.title }}</span>
                        <span v-if="t.title_zh" class="sf-name__en">{{ t.title }}</span>
                      </span>
                    </td>
                    <td data-label="獎勵">
                      <div v-for="(r, i) in t.rewards" :key="r.item_uuid || i" class="wk-reward">
                        {{ r.name_zh || r.name }}<span v-if="r.amount && r.amount !== 1" class="wk-amount ms-1">× {{ r.amount }}</span>
                      </div>
                      <span v-if="!t.rewards?.length">—</span>
                    </td>
                    <td class="text-end text-nowrap" data-label="需要">{{ t.requirements?.length ? `${t.requirements.length} 項` : '—' }}</td>
                    <td class="text-end text-nowrap pe-3" data-label="維克洛聲望">{{ t.reputation_amount ? `+${fmtInt(t.reputation_amount)}` : '—' }}</td>
                  </tr>
                  <tr v-if="openId === t._id" class="sf-stack__detail">
                    <td colspan="4" class="wk-detail">
                      <div class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">{{ t.title_zh || t.title }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="openId = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <div class="row g-3">
                        <div class="col-lg-7">
                          <div class="wk-label">需要</div>
                          <ul class="wk-list">
                            <li v-for="(r, i) in t.requirements" :key="r.item_uuid || i">
                              <span class="sf-name">{{ r.name_zh || r.name }}<span v-if="r.name_zh" class="sf-name__en">{{ r.name }}</span></span>
                              <span class="wk-amount">{{ wikeloAmount(r) }}</span>
                            </li>
                            <li v-if="!t.requirements?.length" class="text-muted">—</li>
                          </ul>
                        </div>
                        <div class="col-lg-5">
                          <div class="wk-label">獎勵</div>
                          <ul class="wk-list">
                            <li v-for="(r, i) in t.rewards" :key="r.item_uuid || i">
                              <span class="sf-name fw-semibold">{{ r.name_zh || r.name }}<span v-if="r.name_zh" class="sf-name__en">{{ r.name }}</span></span>
                              <span v-if="r.amount" class="wk-amount">× {{ r.amount }}</span>
                            </li>
                          </ul>
                          <template v-if="preOf(t).length">
                            <div class="wk-label">前置條件</div>
                            <div class="d-flex flex-wrap gap-1">
                              <span v-for="p in preOf(t)" :key="p" class="sf-chip">{{ p }}</span>
                            </div>
                          </template>
                          <div v-if="t.once_only" class="mt-2"><span class="sf-chip">只能換一次</span></div>
                        </div>
                      </div>
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
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import SfState from '@/components/SfState.vue'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'
import { getJson } from '@/utils/getJson'
import { wikeloAmount } from '@/utils/wikelo'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: true },
})

// 獎勵種類：依獎勵物品的主檔種類（type）分；載具主檔沒有 type 的歸「艦船」
const KINDS = [
  { value: 'ship', label: '艦船' },
  { value: 'weapon', label: '武器' },
  { value: 'armor', label: '護甲' },
  { value: 'other', label: '其他' },
]
function rewardKind(r) {
  const t = r.type || ''
  if (!t || /vehicle|ship/i.test(t)) return /favor|scrip/i.test(r.name || '') ? 'other' : 'ship'
  if (/^Weapon/i.test(t)) return 'weapon'
  if (/^Char_Armor|Suit/i.test(t)) return 'armor'
  return 'other'
}

const rows = ref([])
const loading = ref(false)
const error = ref('')
const query = ref('')
const kinds = ref([])

async function load() {
  loading.value = true
  error.value = ''
  const res = await getJson(props.fetcher, '/mission/wikelo', undefined, '讀取維克洛交易失敗')
  loading.value = false
  if (!res.ok) { error.value = res.message; return }
  rows.value = res.data || []
}
let loaded = false
watch(() => props.active, v => { if (v && !loaded) { loaded = true; load() } }, { immediate: true })

const { isPhone } = useBreakpoint()
const openId = ref('')
const toggle = t => { openId.value = openId.value === t._id ? '' : t._id }
const fmtInt = n => Number(n).toLocaleString('zh-TW')
const preOf = t => [...new Set((t.prerequisite_groups || []).flatMap(g => [...(g.missions || []).map(m => m.title), ...(g.required_tags || [])]))]
const SORT_OPTIONS = [{ field: 'title', label: '交易' }, { field: 'reward', label: '獎勵' }, { field: 'reqs', label: '需要' }, { field: 'rep', label: '維克洛聲望' }]
const shown = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rows.value.filter((t) => {
    if (kinds.value.length && !(t.rewards || []).some(r => kinds.value.includes(rewardKind(r)))) return false
    if (!q) return true
    const texts = [t.title, t.title_zh, ...[...(t.rewards || []), ...(t.requirements || [])].flatMap(r => [r.name, r.name_zh])]
    return texts.some(s => (s || '').toLowerCase().includes(q))
  })
})
const sort = useTableSort(shown, { accessors: {
  title: t => t.title_zh || t.title,
  reward: t => (t.rewards?.[0] ? t.rewards[0].name_zh || t.rewards[0].name : ''),
  reqs: t => t.requirements?.length || 0,
  rep: t => t.reputation_amount || 0,
} })
</script>

<style scoped>
.wk-row { cursor: pointer; }
.wk-reward { font-weight: 600; color: var(--sf-text-strong); }
.wk-amount { font-weight: 700; color: var(--sf-accent-2-text, var(--sf-accent-2)); white-space: nowrap; }
.wk-detail { background: var(--sf-inset); }
.wk-label { margin: 0 0 .3rem; color: var(--sf-text-muted); font-size: var(--sf-fs-sm); font-weight: 700; }
.wk-list { list-style: none; margin: 0 0 .75rem; padding: 0; }
.wk-list li {
  display: flex; align-items: baseline; justify-content: space-between; gap: .75rem;
  padding: .3rem .5rem; border-bottom: 1px solid rgba(var(--sf-accent-rgb), .12);
}
.wk-list li:last-child { border-bottom: 0; }
</style>
