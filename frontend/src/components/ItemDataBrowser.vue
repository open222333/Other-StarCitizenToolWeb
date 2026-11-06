<!--
  玩家頁「物品 › 物品資料」：瀏覽物品主檔（item_master），唯讀。

  篩選用「物品資料」自己的搜尋卡（MyPlayerView 傳進 filters：{ q, types, buyable, dismantlable, dismantle }），
  dismantlable（「只看可拆解」）＝ dismantlable=1、dismantle（拆解材料）＝ dismantle=…，兩者都會附 dismantle_hits；名稱＋類型跟
  物品庫存同一組條件；buyable（「只看買得到」勾選，物品資料展開時才出現在搜尋卡上）＝ acquire=buy。
  資料是 GET /item/?with_prices=1（後端分頁，玩家只看得到「玩家頁面顯示」的物品），每筆帶 uex_price
  （列表只顯示最低購買價）。點名稱展開詳細資料（components/ItemDetail.vue：基本欄位、遊戲內說明的數值、
  購買地點；玩家頁不顯示收購）。
  列表外觀跟艦隊（我的艦隊）、任務一樣：卡片＋hover 表格＋表頭排序，點整列展開（手機是底部面板）。
-->
<template>
  <!-- 換頁載入中保留舊的列（只變淡），不讓頁面瞬間變短；變短會讓瀏覽器把畫面捲到下面去。
       列表外觀跟艦隊（我的艦隊）、任務一致：卡片＋hover 表格＋表頭排序（後端排序），點整列展開物品詳細 -->
  <div ref="rootEl" class="sf-scroll-anchor" :class="{ 'sf-list-loading': loading }">
    <SortSelect v-if="isPhone" class="mb-2" :sort="sort" :options="sortOptions" />
    <div class="card scifi-card">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0 sf-stack">
            <thead class="table-light">
              <tr>
                <SortTh :sort="sort" field="name" class="ps-3">物品</SortTh>
                <SortTh :sort="sort" field="type">類型</SortTh>
                <SortTh :sort="sort" field="size" class="d-none d-md-table-cell">尺寸</SortTh>
                <SortTh :sort="sort" field="grade" class="d-none d-md-table-cell">等級</SortTh>
                <SortTh :sort="sort" field="manufacturer_name" class="d-none d-lg-table-cell">廠商</SortTh>
                <!-- 拆解回收欄只有用「拆解材料」或「只看可拆解」篩選時才出現，依所選材料的回收量（SCU 加總）排序 -->
                <SortTh v-if="showDismantle" :sort="sort" field="dismantle_scu" class="text-end">拆解回收</SortTh>
                <th class="text-end pe-3 text-nowrap">最低價</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading && !rows.length">
                <td :colspan="colCount" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中…
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td :colspan="colCount" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取物品資料失敗。</span>
                  <button type="button" class="btn btn-sm btn-primary ms-1" @click="reload(offset)"><i class="bi bi-arrow-clockwise me-1"></i>重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td :colspan="colCount" class="text-center py-4 text-muted">沒有符合條件的物品。</td>
              </tr>
              <template v-else>
                <template v-for="it in rows" :key="it._id">
                  <tr class="idb-row" role="button" tabindex="0" :aria-expanded="openId === it._id ? 'true' : 'false'"
                    @click="toggle(it)" @keydown.enter.self="toggle(it)" @keydown.space.self.prevent="toggle(it)">
                    <td class="ps-3 sf-stack__title">
                      <i class="bi me-1 small text-muted" :class="openId === it._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <span class="fw-semibold">{{ it.name_zh || it.name }}</span>
                      <span v-if="it.name_zh" class="small text-muted ms-1">{{ it.name }}</span>
                      <!-- 拆解會回收的材料（有選材料時只列那幾種；後端 dismantle_hits） -->
                      <span v-if="it.dismantle_hits?.length" class="d-block small text-muted">
                        拆解回收：{{ dismantleHits(it.dismantle_hits, filters?.dismantle).join('、') }}
                      </span>
                    </td>
                    <td data-label="類型">{{ itemTypeLabel(it.type, it.sub_type) || '—' }}</td>
                    <td class="d-none d-md-table-cell" data-label="尺寸">{{ it.size !== null && it.size !== undefined ? `S${it.size}` : '—' }}</td>
                    <td class="d-none d-md-table-cell" data-label="等級">{{ it.grade ?? '—' }}</td>
                    <td class="d-none d-lg-table-cell" data-label="廠商">{{ it.manufacturer_name || it.manufacturer_code || '—' }}</td>
                    <td v-if="showDismantle" class="text-end text-nowrap" data-label="拆解回收">{{ fmtScu(dismantleScu(it)) }}</td>
                    <td class="text-end text-nowrap pe-3" data-label="最低價">
                      <template v-if="it.uex_price?.buy_min">{{ fmtAuec(it.uex_price.buy_min) }} 起</template>
                      <template v-else>—</template>
                    </td>
                  </tr>
                  <tr v-if="openId === it._id" class="sf-stack__detail">
                    <td :colspan="colCount" class="idb-detail">
                      <div class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">{{ it.name_zh || it.name }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="openId = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <ItemDetail :item="it" :fetcher="fetcher" player buy-only />
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
import { scrollToListTop } from '@/utils/scrollAnchor'
import ItemDetail from '@/components/ItemDetail.vue'
import { itemTypeLabel, loadItemTypeZh } from '@/utils/itemType'
import { fmtAuec } from '@/utils/uexCommodity'
import { dismantleHits } from '@/utils/blueprintMaterial'

const props = defineProps({
  /** 帶身分的 fetch（玩家頁傳 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /** 「倉庫」分頁頂端共用搜尋卡的條件：{ q, types, buyable } */
  filters: { type: Object, default: () => ({}) },
  /** 點開才載入（玩家頁用 v-show 一直掛著） */
  active: { type: Boolean, default: true },
})

const limit = 30
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const openId = ref('')

let seq = 0
async function reload(nextOffset = 0) {
  offset.value = Math.max(0, nextOffset)
  loading.value = true
  loadFailed.value = false
  const mine = ++seq
  const f = props.filters || {}
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset.value), with_prices: '1' })
  if (f.q) params.set('q', f.q)
  ;(f.types || []).forEach(v => params.append('type', v))
  if (f.buyable) params.append('acquire', 'buy')
  ;(f.dismantle || []).forEach(v => params.append('dismantle', v))
  if (f.dismantlable) params.append('dismantlable', '1')
  for (const [k, v] of Object.entries(sort.params.value)) params.set(k, v)
  const res = await props.fetcher(`/item/?${params.toString()}`)
  const data = res ? await res.json().catch(() => null) : null
  if (mine !== seq) return
  loading.value = false
  if (!data?.success) {
    rows.value = []
    total.value = 0
    loadFailed.value = true
    return
  }
  rows.value = data.data || []
  total.value = data.total || 0
  loadItemTypeZh(rows.value.map(r => r.type), rows.value.map(r => r.sub_type))
  openId.value = ''
}

// ── 欄位名稱＋排序（後端排序：name／type／size／grade／manufacturer_name／dismantle_scu）──
const showDismantle = computed(() => !!(props.filters?.dismantle?.length || props.filters?.dismantlable))
// 手機沒有表頭，另外給排序下拉（SortSelect）
const sortOptions = computed(() => [
  { field: 'name', label: '物品' },
  { field: 'type', label: '類型' },
  { field: 'size', label: '尺寸' },
  { field: 'grade', label: '等級' },
  { field: 'manufacturer_name', label: '廠商' },
  ...(showDismantle.value ? [{ field: 'dismantle_scu', label: '拆解回收' }] : []),
])
const colCount = computed(() => (showDismantle.value ? 7 : 6))
const { isPhone } = useBreakpoint()
function toggle(it) {
  openId.value = openId.value === it._id ? '' : it._id
}
const sort = useTableSort(null, { onChange: () => reload(0) })

/** 這個物品拆解回收的 SCU（有選材料時只算那幾種，跟後端 dismantle_scu 排序一致） */
function dismantleScu(it) {
  const names = props.filters?.dismantle || []
  return (it.dismantle_hits || []).filter(h => !names.length || names.includes(h.name))
    .reduce((n, h) => n + (h.quantity_scu || 0), 0)
}
function fmtScu(v) {
  return v ? `${Number(v.toFixed(3))} SCU` : '—'
}

let loaded = false
let timer = null
watch(() => props.active, (v) => {
  if (!v || loaded) return
  loaded = true
  reload(0)
}, { immediate: true })
// 共用搜尋卡每打一個字就會換一次 filters，等停手 300ms 再查；還沒展開過就先不查
watch(() => props.filters, (f, old) => {
  // 剛開始用拆解材料篩選、還沒自己選排序時，預設依回收量由多到少；拆解欄消失時取消這個排序
  const nowDismantle = !!(f?.dismantle?.length || f?.dismantlable)
  if (nowDismantle && !sort.sortKey.value) { sort.sortKey.value = 'dismantle_scu'; sort.sortDir.value = 'desc' }
  if (!nowDismantle && sort.sortKey.value === 'dismantle_scu') sort.sortKey.value = ''
  if (!loaded) return
  clearTimeout(timer)
  timer = setTimeout(() => reload(0), 300)
}, { deep: true })
onBeforeUnmount(() => clearTimeout(timer))

defineExpose({ refresh: () => { if (loaded) reload(offset.value) } })

// 上一頁／下一頁：載入後把列表頂端捲回畫面（不然會停在最下方的分頁按鈕，見 utils/scrollAnchor.js）
const rootEl = ref(null)
async function goPage(newOffset) {
  await reload(newOffset)
  scrollToListTop(rootEl.value)
}
</script>

<style scoped>
.idb-row { cursor: pointer; }
.idb-detail { background: var(--sf-inset); }
</style>
