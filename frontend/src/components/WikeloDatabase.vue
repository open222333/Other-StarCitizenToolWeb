<!--
  資料庫 › 維克洛：維克洛（Wikelo Emporium）的全部交易（GET /mission/wikelo，同步項目「維克洛」）。
  每筆一列：交易、獎勵（標種類，點名稱跳到那個東西所在的資料庫分頁）、需要（按鈕跳出視窗）、維克洛聲望；
  登入時多一欄「我的倉庫」：跟倉庫的物品數量比對（inventory prop，[{item_id, quantity}]），可以換／還差幾項。
  需要的視窗內容是 WikeloTradePanel（數量、我有幾個、取得方式按鈕、獎勵、前置條件）。
  搜尋：交易名稱、獎勵或需要的物品名稱（中英文），在前端過濾（全部不到一百筆）。
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
        <div v-if="hasInventory || hasFilter" class="d-flex flex-wrap align-items-center gap-2 mt-2">
          <div v-if="hasInventory" class="sf-pills"><SfToggle v-model="readyOnly">只看我現在能換的</SfToggle></div>
          <button v-if="hasFilter" type="button" class="btn btn-sm btn-warning ms-auto" @click="clearFilters">清除篩選</button>
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
                  <SortTh v-if="hasInventory" :sort="sort" field="ready" class="text-end">我的倉庫</SortTh>
                  <SortTh :sort="sort" field="rep" class="text-end pe-3">維克洛聲望</SortTh>
                </tr>
              </thead>
              <tbody>
                <tr v-for="t in sort.sorted.value" :key="t._id">
                  <td class="ps-3 sf-stack__title">
                    <span class="sf-name">
                      <span class="fw-semibold">{{ t.title_zh || t.title }}</span>
                      <span v-if="t.title_zh" class="sf-name__en">{{ t.title }}</span>
                    </span>
                  </td>
                  <td data-label="獎勵">
                    <div v-for="(r, i) in t.rewards" :key="r.item_uuid || i" class="wk-reward">
                      <span class="sf-chip wk-kind" :class="`wk-kind--${rewardKind(r)}`">{{ KIND_LABEL[rewardKind(r)] }}</span>
                      <button v-if="findSub(r)" type="button" class="btn btn-sm btn-info text-start wk-reward__btn"
                        :aria-label="`到資料庫找 ${r.name_zh || r.name}`" @click="goFind(findSub(r), r)">{{ r.name_zh || r.name }}</button>
                      <span v-else class="fw-semibold">{{ r.name_zh || r.name }}</span>
                      <span v-if="r.amount && r.amount !== 1" class="wk-amount">× {{ r.amount }}</span>
                    </div>
                    <span v-if="!t.rewards?.length">—</span>
                  </td>
                  <td class="text-end text-nowrap" data-label="需要">
                    <button v-if="t.requirements?.length" type="button" class="btn btn-sm btn-info" aria-haspopup="dialog"
                      :aria-label="`${t.title_zh || t.title} 需要的物品`" @click="openTrade(t)">{{ t.requirements.length }} 項</button>
                    <span v-else>—</span>
                  </td>
                  <td v-if="hasInventory" class="text-end text-nowrap" data-label="我的倉庫">
                    <span v-if="progress(t).missing === 0" class="sf-chip sf-chip--ok">可以換</span>
                    <span v-else class="sf-chip sf-chip--todo">還差 {{ progress(t).missing }} 項</span>
                  </td>
                  <td class="text-end text-nowrap pe-3" data-label="維克洛聲望">{{ t.reputation_amount ? `+${fmtInt(t.reputation_amount)}` : '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </SfState>

    <!-- 需要的物品：數量、我有幾個、取得方式；下面是獎勵與前置條件（WikeloTradePanel，跟物品／藍圖／艦船的維克洛視窗共用） -->
    <SfModal id="wk-trade" v-model:open="tradeOpen" :title="trade ? (trade.title_zh || trade.title) : '維克洛交易'" width="1000px">
      <WikeloTradePanel v-if="trade && tradeOpen" :key="trade._id" :trade="trade" :fetcher="fetcher" :inventory="inventory" />
    </SfModal>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import SfToggle from '@/components/SfToggle.vue'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import WikeloTradePanel from '@/components/WikeloTradePanel.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'
import { getJson } from '@/utils/getJson'
import { KIND_LABEL, rewardKind, WIKELO_KINDS as KINDS } from '@/utils/wikelo'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: true },
  /** 我的倉庫（登入才有）：[{ item_id, quantity }]；null＝沒登入，不比對 */
  inventory: { type: Array, default: null },
  /** 站內「到維克洛找這個」帶進來的名稱（MyPlayerView 的 ?find=；例如需要的物品按「維克洛換」） */
  find: { type: Object, default: null },
})
const router = useRouter()

// 獎勵名稱點下去要跳到哪個資料庫分頁
function findSub(r) {
  if (r.source === 'vehicle') return 'vehicles'
  if (r.source === 'item') return 'data'
  return ''
}
function goFind(sub, r) {
  tradeOpen.value = false
  router.push({ query: { tab: 'items', sub, find: r.master_name || r.name } })
}

const rows = ref([])
const loading = ref(false)
const error = ref('')
const query = ref('')
const kinds = ref([])
const readyOnly = ref(false)
watch(() => props.find, (v) => { if (v?.q) { query.value = v.q; kinds.value = []; readyOnly.value = false } }, { immediate: true })
const hasFilter = computed(() => !!query.value.trim() || kinds.value.length > 0 || readyOnly.value)
function clearFilters() { query.value = ''; kinds.value = []; readyOnly.value = false }

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

// ── 對照我的倉庫：{物品 uuid: 數量}；SCU 計的（礦物、商品）倉庫沒有，算還差 ──
const hasInventory = computed(() => Array.isArray(props.inventory))
const stock = computed(() => {
  const out = {}
  for (const r of props.inventory || []) if (r.item_id) out[r.item_id] = (out[r.item_id] || 0) + (r.quantity || 0)
  return out
})
const needOf = r => (r.amount !== null && r.amount !== undefined ? r.amount : null)
const haveOf = r => stock.value[r.item_uuid] || 0
function progress(t) {
  const missing = (t.requirements || []).filter(r => needOf(r) === null || haveOf(r) < needOf(r)).length
  return { missing }
}
const { isPhone } = useBreakpoint()
const fmtInt = n => Number(n).toLocaleString('zh-TW')
const SORT_OPTIONS = computed(() => [{ field: 'title', label: '交易' }, { field: 'reward', label: '獎勵' }, { field: 'reqs', label: '需要' },
  ...(hasInventory.value ? [{ field: 'ready', label: '我的倉庫' }] : []), { field: 'rep', label: '維克洛聲望' }])

// 需要的視窗
const tradeOpen = ref(false)
const trade = ref(null)
function openTrade(t) {
  trade.value = t
  tradeOpen.value = true
}

const shown = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rows.value.filter((t) => {
    if (kinds.value.length && !(t.rewards || []).some(r => kinds.value.includes(rewardKind(r)))) return false
    if (readyOnly.value && hasInventory.value && progress(t).missing > 0) return false
    if (!q) return true
    const texts = [t.title, t.title_zh, ...[...(t.rewards || []), ...(t.requirements || [])].flatMap(r => [r.name, r.name_zh])]
    return texts.some(s => (s || '').toLowerCase().includes(q))
  })
})
const sort = useTableSort(shown, { accessors: {
  title: t => t.title_zh || t.title,
  reward: t => (t.rewards?.[0] ? t.rewards[0].name_zh || t.rewards[0].name : ''),
  reqs: t => t.requirements?.length || 0,
  ready: t => progress(t).missing,
  rep: t => t.reputation_amount || 0,
} })
</script>

<style scoped>
.wk-reward { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; }
.wk-reward + .wk-reward { margin-top: .25rem; }
.wk-reward__btn { white-space: normal; font-weight: 600; }
.wk-kind { margin: 0; font-size: var(--sf-fs-xs); }
.wk-kind--ship { --wk: var(--sf-accent-rgb); }
.wk-kind--weapon { --wk: var(--sf-accent-2-rgb); }
.wk-kind--armor { --wk: var(--bs-success-rgb); }
.wk-kind--ship, .wk-kind--weapon, .wk-kind--armor { border-color: rgba(var(--wk), .7); color: rgb(var(--wk)); }
.wk-amount { font-weight: 700; color: var(--sf-accent-2-text, var(--sf-accent-2)); white-space: nowrap; }
.wk-label { margin: 0 0 .3rem; color: var(--sf-text-muted); font-size: var(--sf-fs-sm); font-weight: 700; }
.wk-acts { display: flex; flex-wrap: wrap; gap: .3rem; }
.wk-buy { background: var(--sf-inset); }
</style>
