<!--
  一筆維克洛交易的內容（資料庫 › 維克洛的「需要」視窗、物品／藍圖／艦船的「維克洛」視窗共用）：
  需要的物品表（數量、登入時「我有」、取得方式按鈕）＋獎勵＋前置條件。
  取得方式：購買地點＝UEX 在表格裡展開；物品＝物品詳細、藍圖＝配方與品質試算，都再跳出一層視窗（Teleport 到 body）；
  礦物＝跳到礦物分頁找；維克洛換＝這東西也是別的維克洛交易的獎勵（例如維克洛人情），跳到維克洛分頁搜尋它。
  跳到別的分頁前 emit('leave')，外層把自己的視窗關掉。
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
                  <button v-if="r.buyable" type="button" class="btn btn-sm btn-success"
                    :aria-expanded="buyOpen === r.item_uuid ? 'true' : 'false'"
                    @click="buyOpen = buyOpen === r.item_uuid ? '' : r.item_uuid">購買地點</button>
                  <button v-if="r.source === 'item'" type="button" class="btn btn-sm btn-info" aria-haspopup="dialog" @click="openItem(r)">物品</button>
                  <button v-if="r.blueprint" type="button" class="btn btn-sm btn-info" aria-haspopup="dialog" @click="openBlueprint(r)">藍圖</button>
                  <button v-if="isWikeloReward(r)" type="button" class="btn btn-sm btn-info" @click="go('wikelo', r.name_zh || r.name)">維克洛換</button>
                  <button v-if="r.source === 'commodity'" type="button" class="btn btn-sm btn-info" @click="go('minerals', r.master_name || r.name)">礦物</button>
                </div>
              </td>
            </tr>
            <tr v-if="buyOpen && buyOpen === r.item_uuid">
              <td :colspan="hasInventory ? 4 : 3" class="wtp-buy">
                <ItemPriceDetail :key="r.item_uuid" :item-uuid="r.item_uuid" :fetcher="fetcher" player buy-only />
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
        <BlueprintDetailModal ref="bpDetailRef" :fetcher="fetcher" />
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import BlueprintDetailModal from '@/components/BlueprintDetailModal.vue'
import ItemDetail from '@/components/ItemDetail.vue'
import ItemPriceDetail from '@/components/ItemPriceDetail.vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import { getJson } from '@/utils/getJson'
import { KIND_LABEL, loadWikeloIndex, rewardKind, wikeloAmount, wikeloIndex } from '@/utils/wikelo'

const props = defineProps({
  trade: { type: Object, required: true },
  fetcher: { type: Function, default: (...a) => fetch(...a) },
  /** 我的倉庫 [{ item_id, quantity }]；null＝不比對 */
  inventory: { type: Array, default: null },
  highlight: { type: Array, default: () => [] },
})
const emit = defineEmits(['leave'])
const router = useRouter()
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

const buyOpen = ref('')
const isWikeloReward = r => !!r.item_uuid && (wikeloIndex.uuids[r.item_uuid]?.reward || 0) > 0
function go(sub, name) {
  emit('leave')
  router.push({ query: { tab: 'items', sub, find: name } })
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
const bpDetailRef = ref(null)
const openBlueprint = r => bpDetailRef.value?.open({ uuid: r.blueprint, name: r.master_name || r.name, name_zh: r.name_zh })
</script>

<style scoped>
.wtp-label { margin: 0 0 .3rem; color: var(--sf-text-muted); font-size: var(--sf-fs-sm); font-weight: 700; }
.wtp-amount { font-weight: 700; color: var(--sf-accent-2-text, var(--sf-accent-2)); white-space: nowrap; }
.wtp-acts { display: flex; flex-wrap: wrap; gap: .3rem; }
.wtp-buy { background: var(--sf-inset); }
.wtp-hit > td, .wtp-reward.wtp-hit { background: rgba(var(--sf-accent-rgb), .16); }
.wtp-reward { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; border-radius: .35rem; padding: .1rem .2rem; }
.wtp-reward + .wtp-reward { margin-top: .25rem; }
.wtp-kind { margin: 0; font-size: var(--sf-fs-xs); }
.wtp-kind--ship { --wk: var(--sf-accent-rgb); }
.wtp-kind--weapon { --wk: var(--sf-accent-2-rgb); }
.wtp-kind--armor { --wk: var(--bs-success-rgb); }
.wtp-kind--ship, .wtp-kind--weapon, .wtp-kind--armor { border-color: rgba(var(--wk), .7); color: rgb(var(--wk)); }
</style>
