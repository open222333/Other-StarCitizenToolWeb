<!--
  一筆維克洛交易的內容（資料庫 › 維克洛的「需要」視窗、物品／藍圖／艦船的「維克洛」視窗共用）：
  需要的物品表（數量、登入時「我有」、取得方式按鈕）＋獎勵＋前置條件。
  取得方式的按鈕一律再跳出一層視窗顯示那筆資料（Teleport 到 body，疊在上面，關掉回到原本的視窗）：
    購買地點＝UEX 哪裡買得到、物品＝物品詳細、藍圖＝配方與品質試算、礦物＝礦物資料庫只看這一種（MineralDatabase focus）、
    維克洛換＝換得到它的其他維克洛交易（同一個面板，可以一層層點下去）。
  highlight＝要標出來的物品 uuid（從某個物品的「維克洛」按鈕打開時，標出就是它的那一行）。
-->
<template>
  <div class="wtp">
    <div class="wtp-label">需要</div>
    <div class="table-responsive mb-3">
      <table class="table align-middle mb-0 sf-stack">
        <thead class="table-light">
          <tr>
            <th class="ps-2">物品</th>
            <th class="text-end">數量</th>
            <th v-if="hasInventory" class="text-end">我有</th>
            <th class="pe-2">取得方式</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(r, i) in trade.requirements" :key="r.item_uuid || i">
            <tr :class="{ 'wtp-hit': isHit(r) }">
              <td class="ps-2 sf-stack__title">
                <span class="sf-name">{{ r.name_zh || r.name }}<span v-if="r.name_zh" class="sf-name__en">{{ r.name }}</span></span>
              </td>
              <td class="text-end text-nowrap" data-label="數量"><span class="wtp-amount">{{ wikeloAmount(r) }}</span></td>
              <td v-if="hasInventory" class="text-end text-nowrap" data-label="我有">
                <span v-if="needOf(r) === null">—</span>
                <span v-else :class="haveOf(r) >= needOf(r) ? 'sf-good' : 'sf-bad'" class="fw-semibold">{{ haveOf(r) }}</span>
              </td>
              <td class="pe-2 sf-stack__actions" data-label="取得方式">
                <div class="wtp-acts">
                  <button v-if="r.buyable" type="button" class="btn btn-sm btn-success" aria-haspopup="dialog" @click="openBuy(r)">購買地點</button>
                  <button v-if="r.source === 'item'" type="button" class="btn btn-sm btn-info" aria-haspopup="dialog" @click="openItem(r)">物品</button>
                  <button v-if="r.blueprint" type="button" class="btn btn-sm btn-info" aria-haspopup="dialog" @click="openBlueprint(r)">藍圖</button>
                  <button v-if="isWikeloReward(r)" type="button" class="btn btn-sm btn-info" aria-haspopup="dialog" @click="openExchange(r)">維克洛換</button>
                  <button v-if="r.source === 'commodity'" type="button" class="btn btn-sm btn-info" aria-haspopup="dialog" @click="openMineral(r)">礦物</button>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="!trade.requirements?.length"><td :colspan="hasInventory ? 4 : 3" class="text-muted ps-2">—</td></tr>
        </tbody>
      </table>
    </div>
    <div class="row g-3">
      <div class="col-md-6">
        <div class="wtp-label">獎勵</div>
        <div v-for="(r, i) in trade.rewards" :key="r.item_uuid || i" class="wtp-reward" :class="{ 'wtp-hit': isHit(r) }">
          <span class="sf-chip wtp-kind" :class="`wtp-kind--${rewardKind(r)}`">{{ KIND_LABEL[rewardKind(r)] }}</span>
          <span class="fw-semibold">{{ r.name_zh || r.name }}</span>
          <span v-if="r.amount && r.amount !== 1" class="wtp-amount">× {{ r.amount }}</span>
        </div>
        <div class="d-flex flex-wrap gap-1 mt-1">
          <span v-if="trade.reputation_amount" class="sf-chip sf-chip--accent">維克洛聲望 +{{ fmtInt(trade.reputation_amount) }}</span>
          <span v-if="trade.once_only" class="sf-chip">只能換一次</span>
        </div>
      </div>
      <div v-if="pre.length" class="col-md-6">
        <div class="wtp-label">前置條件</div>
        <div class="d-flex flex-wrap gap-1">
          <span v-for="p in pre" :key="p" class="sf-chip">{{ p }}</span>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div class="scifi-page">
        <SfModal :id="`${uid}-item`" v-model:open="itemOpen" :title="itemRow ? (itemRow.name_zh || itemRow.name) : '物品'" width="900px">
          <SfState :loading="itemLoading" :error="itemError" @retry="loadItem">
            <ItemDetail v-if="itemRow && itemOpen" :key="itemRow._id" :item="itemRow" :fetcher="fetcher" player buy-only />
          </SfState>
        </SfModal>
        <SfModal :id="`${uid}-mineral`" v-model:open="mineralOpen" :title="mineralName ? `${mineralName} · 哪裡挖得到` : '礦物'" width="1100px">
          <MineralDatabase v-if="mineralOpen" :key="mineralQuery" :focus="mineralQuery" :fetcher="fetcher" card-class="card scifi-card" />
        </SfModal>
        <SfModal :id="`${uid}-buy`" v-model:open="buyOpen" :title="buyRow ? `${buyRow.name_zh || buyRow.name} · 購買地點` : '購買地點'" width="900px">
          <ItemPriceDetail v-if="buyOpen && buyRow" :key="buyRow.item_uuid" :item-uuid="buyRow.item_uuid" :fetcher="fetcher" player buy-only />
        </SfModal>
        <!-- 維克洛換：換得到這個物品的其他維克洛交易（同一個面板，可以一層層點下去） -->
        <SfModal :id="`${uid}-ex`" v-model:open="exOpen" :title="exRow ? `${exRow.name_zh || exRow.name} · 跟維克洛換` : '跟維克洛換'" width="1000px">
          <SfState :loading="exLoading" :error="exError" :empty="!exLoading && !exError && !exTrades.length"
            empty-text="沒有換得到它的維克洛交易" @retry="loadExchange">
            <article v-for="t in exTrades" :key="t._id" class="wtp-trade">
              <h5 class="wtp-title">{{ t.title_zh || t.title }}<span v-if="t.title_zh" class="sf-name__en">{{ t.title }}</span></h5>
              <WikeloTradePanel :trade="t" :fetcher="fetcher" :inventory="inventory" :highlight="[exRow.item_uuid]" />
            </article>
          </SfState>
        </SfModal>
        <BlueprintDetailModal ref="bpDetailRef" :fetcher="fetcher" />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, ref } from 'vue'
import BlueprintDetailModal from '@/components/BlueprintDetailModal.vue'
import ItemDetail from '@/components/ItemDetail.vue'
import ItemPriceDetail from '@/components/ItemPriceDetail.vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import { getJson } from '@/utils/getJson'
import { KIND_LABEL, loadWikeloIndex, rewardKind, wikeloAmount, wikeloIndex } from '@/utils/wikelo'

const MineralDatabase = defineAsyncComponent(() => import('@/components/MineralDatabase.vue'))

const props = defineProps({
  trade: { type: Object, required: true },
  fetcher: { type: Function, default: (...a) => fetch(...a) },
  /** 我的倉庫 [{ item_id, quantity }]；null＝不比對 */
  inventory: { type: Array, default: null },
  highlight: { type: Array, default: () => [] },
})
const uid = `wtp-${Math.random().toString(36).slice(2, 8)}`
onMounted(() => { loadWikeloIndex(props.fetcher) })

const fmtInt = n => Number(n).toLocaleString('zh-TW')
const isHit = r => !!r.item_uuid && props.highlight.includes(r.item_uuid)
const pre = computed(() => [...new Set((props.trade.prerequisite_groups || [])
  .flatMap(g => [...(g.missions || []).map(m => m.title), ...(g.required_tags || [])]))])

// 對照倉庫：SCU 計的（礦物、商品）沒有數量可比
const hasInventory = computed(() => Array.isArray(props.inventory))
const stock = computed(() => {
  const out = {}
  for (const r of props.inventory || []) if (r.item_id) out[r.item_id] = (out[r.item_id] || 0) + (r.quantity || 0)
  return out
})
const needOf = r => (r.amount !== null && r.amount !== undefined ? r.amount : null)
const haveOf = r => stock.value[r.item_uuid] || 0

// 購買地點（UEX）
const buyOpen = ref(false)
const buyRow = ref(null)
function openBuy(r) { buyRow.value = r; buyOpen.value = true }

// 維克洛換：GET /mission/wikelo/by-item 的 reward（換得到它的交易）
const isWikeloReward = r => !!r.item_uuid && (wikeloIndex.uuids[r.item_uuid]?.reward || 0) > 0
const exOpen = ref(false)
const exRow = ref(null)
const exTrades = ref([])
const exLoading = ref(false)
const exError = ref('')
async function loadExchange() {
  exLoading.value = true
  exError.value = ''
  const res = await getJson(props.fetcher, `/mission/wikelo/by-item?uuid=${encodeURIComponent(exRow.value.item_uuid)}`, undefined, '讀取維克洛交易失敗')
  exLoading.value = false
  if (!res.ok) { exError.value = res.message; return }
  exTrades.value = res.data?.reward || []
}
function openExchange(r) {
  exRow.value = r
  exTrades.value = []
  exOpen.value = true
  loadExchange()
}

// 物品詳細（GET /item/<uuid>，跟資料庫 › 物品展開的一樣）
const itemOpen = ref(false)
const itemRow = ref(null)
const itemLoading = ref(false)
const itemError = ref('')
let itemUuid = ''
async function loadItem() {
  itemLoading.value = true
  itemError.value = ''
  const res = await getJson(props.fetcher, `/item/${encodeURIComponent(itemUuid)}`, undefined, '讀取物品失敗')
  itemLoading.value = false
  if (!res.ok) { itemError.value = res.message; return }
  itemRow.value = res.data
}
function openItem(r) {
  itemUuid = r.item_uuid
  itemRow.value = { _id: r.item_uuid, name: r.master_name || r.name, name_zh: r.name_zh }
  itemOpen.value = true
  loadItem()
}
// 礦物：跳出礦物資料庫只看這一種（哪裡挖得到、用在哪些藍圖／任務）
const mineralOpen = ref(false)
const mineralQuery = ref('')
const mineralName = ref('')
function openMineral(r) {
  mineralQuery.value = r.master_name || r.name
  mineralName.value = r.name_zh || r.name
  mineralOpen.value = true
}
const bpDetailRef = ref(null)
const openBlueprint = r => bpDetailRef.value?.open({ uuid: r.blueprint, name: r.master_name || r.name, name_zh: r.name_zh })
</script>

<style scoped>
.wtp-label { margin: 0 0 .3rem; color: var(--sf-text-muted); font-size: var(--sf-fs-sm); font-weight: 700; }
.wtp-amount { font-weight: 700; color: var(--sf-accent-2-text, var(--sf-accent-2)); white-space: nowrap; }
.wtp-acts { display: flex; flex-wrap: wrap; gap: .3rem; }
.wtp-trade { padding: .75rem; border: 1px solid var(--sf-border); border-radius: .5rem; background: var(--sf-inset); }
.wtp-trade + .wtp-trade { margin-top: .75rem; }
.wtp-title { margin: 0 0 .6rem; font-size: var(--sf-fs-md); font-weight: 700; color: var(--sf-text-strong); }
.wtp-title .sf-name__en { display: block; font-size: var(--sf-fs-sm); font-weight: 400; }
.wtp-hit > td, .wtp-reward.wtp-hit { background: rgba(var(--sf-accent-rgb), .16); }
.wtp-reward { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; border-radius: .35rem; padding: .1rem .2rem; }
.wtp-reward + .wtp-reward { margin-top: .25rem; }
.wtp-kind { margin: 0; font-size: var(--sf-fs-xs); }
.wtp-kind--ship { --wk: var(--sf-accent-rgb); }
.wtp-kind--weapon { --wk: var(--sf-accent-2-rgb); }
.wtp-kind--armor { --wk: var(--bs-success-rgb); }
.wtp-kind--ship, .wtp-kind--weapon, .wtp-kind--armor { border-color: rgba(var(--wk), .7); color: rgb(var(--wk)); }
</style>
