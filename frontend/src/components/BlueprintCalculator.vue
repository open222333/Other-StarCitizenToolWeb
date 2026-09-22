<!--
  藍圖材料試算：選一張藍圖 → 填現有材料 → 算最多可以做幾個。

  這個元件被兩個地方掛載（同一份實作，各自帶自己的身分）：
    - 後台：views/BlueprintCalcView.vue（用 apiFetch，庫存來源是公會共享庫）
    - 玩家頁：MyPlayerView 的「試算」分頁（用 playerFetch，庫存來源是個人庫）
  所以這裡不直接碰任何 store，取資料一律走 `fetcher` prop。

  計算邏輯全部在 utils/craftCalc.js（純函式、有測試：npm run test:calc），
  這個檔案只負責畫面與互動。
-->
<template>
  <div>
    <!-- ── 選藍圖 ─────────────────────────────────────────── -->
    <div :class="[cardClass, 'mb-3']">
      <div class="card-body">
        <label class="form-label small fw-semibold" :for="searchId">藍圖名稱</label>
        <div class="position-relative">
          <input :id="searchId" v-model="keyword" type="text" class="form-control"
            placeholder="輸入藍圖或產出物名稱，例如 Laser Cannon、醫療筆"
            role="combobox" aria-autocomplete="list" :aria-expanded="showResults"
            :aria-controls="listId" :aria-activedescendant="activeOptionId"
            autocomplete="off"
            @input="onSearchInput" @keydown="onSearchKeydown" @blur="onSearchBlur">

          <ul v-if="showResults" :id="listId" class="list-group position-absolute w-100 shadow"
            style="z-index: 20; max-height: 16rem; overflow-y: auto" role="listbox">
            <li v-if="searching" class="list-group-item small hint">搜尋中…</li>
            <li v-else-if="!results.length" class="list-group-item small hint">
              找不到符合的藍圖
            </li>
            <li v-for="(bp, i) in results" :key="bp._id" :id="`${listId}-opt-${i}`"
              role="option" :aria-selected="i === highlighted"
              :class="['list-group-item', 'list-group-item-action', 'small',
                       { active: i === highlighted }]"
              style="cursor: pointer"
              @mousedown.prevent="selectBlueprint(bp)"
              @mousemove="highlighted = i">
              <span class="fw-semibold">{{ bp.name_zh || bp.name }}</span>
              <span v-if="bp.name_zh" class="hint ms-1">{{ bp.name }}</span>
              <span v-if="bp.output_type" class="badge bg-secondary ms-1">
                {{ blueprintTypeLabel(bp.output_type) }}
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div v-if="loadError" class="alert alert-warning py-2">{{ loadError }}</div>

    <div v-if="loadingRecipe" class="text-center hint py-4">
      <span class="spinner-border spinner-border-sm me-2"></span>載入配方…
    </div>

    <!-- ── 試算 ───────────────────────────────────────────── -->
    <template v-else-if="recipe">
      <div :class="[cardClass, 'mb-3']">
        <div class="card-body">
          <div class="d-flex flex-wrap justify-content-between align-items-start gap-2">
            <div>
              <h6 class="fw-bold mb-1">
                {{ recipe.name_zh || recipe.name }}
                <span v-if="recipe.name_zh" class="small hint">{{ recipe.name }}</span>
              </h6>
              <div class="small hint">
                <span v-if="recipe.output_type">{{ blueprintTypeLabel(recipe.output_type) }}</span>
                <span v-if="recipe.craft_time_label"> · 單個製造時間 {{ recipe.craft_time_label }}</span>
                <span v-if="rows.length"> · {{ rows.length }} 種材料</span>
              </div>
            </div>
            <div class="d-flex gap-2">
              <button v-if="stockLoader" class="btn btn-sm btn-outline-secondary"
                :disabled="loadingStock" @click="fillFromStock">
                <span v-if="loadingStock" class="spinner-border spinner-border-sm me-1"></span>
                從{{ stockLabel }}帶入
              </button>
              <button class="btn btn-sm btn-outline-secondary" @click="clearAmounts">清空數量</button>
            </div>
          </div>
        </div>
      </div>

      <!-- 沒有配方資料：要講清楚是「主檔沒同步到」而不是「這張圖不用材料」 -->
      <div v-if="!rows.length" class="alert alert-warning">
        這張藍圖的主檔裡沒有材料資料（遊戲資料同步時可能沒帶到配方明細），
        所以無法試算。可以在後台「系統設定 → 遊戲資料同步」重跑一次同步後再試。
      </div>

      <template v-else>
        <!-- 結果摘要 -->
        <div class="row g-3 mb-3">
          <div class="col-12 col-md-4">
            <div :class="[cardClass, 'h-100', 'text-center', 'py-3']">
              <div class="small hint">最多可以做</div>
              <div class="fw-bold" style="font-size: 2rem; line-height: 1.2">
                {{ result.maxCraftable === null ? '—' : result.maxCraftable }}
              </div>
              <div class="small hint">個</div>
            </div>
          </div>
          <div class="col-12 col-md-8">
            <div :class="[cardClass, 'h-100']">
              <div class="card-body">
                <div v-if="result.maxCraftable === null" class="small hint">
                  這張藍圖的材料需求數量在主檔裡是空的，算不出數量。
                </div>
                <template v-else>
                  <div class="small mb-2">
                    <span class="hint">瓶頸材料：</span>
                    <span v-if="bottleneckNames" class="fw-semibold">{{ bottleneckNames }}</span>
                    <span v-else class="hint">—</span>
                    <span v-if="result.maxCraftable === 0" class="hint">
                      （目前一個都做不出來）
                    </span>
                  </div>
                  <div v-if="totalTime" class="small mb-2">
                    <span class="hint">全部做完約需：</span>{{ totalTime }}
                  </div>
                  <div v-if="!result.reliable" class="small text-warning mb-0">
                    <i class="bi bi-exclamation-triangle me-1"></i>
                    有 {{ result.unknownCount }} 種材料的需求數量主檔沒有資料，
                    已排除在計算之外 —— 實際可做數量可能更少。
                  </div>
                </template>

                <div class="d-flex align-items-center gap-2 mt-2">
                  <label class="form-label small fw-semibold mb-0" :for="targetId">我想做</label>
                  <input :id="targetId" v-model="target" type="number" min="0" step="1"
                    class="form-control form-control-sm" style="max-width: 6rem">
                  <span class="small hint">個</span>
                  <span v-if="result.targetReachable === true" class="small text-success">
                    <i class="bi bi-check-circle me-1"></i>材料夠
                  </span>
                  <span v-else-if="result.targetReachable === false" class="small text-danger">
                    <i class="bi bi-x-circle me-1"></i>材料不夠
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 材料表 -->
        <div :class="cardClass">
          <div class="card-body p-0">
            <div style="overflow-x: auto">
              <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
                  <tr>
                    <th class="ps-3">材料</th>
                    <th class="text-end">每個需要</th>
                    <th style="min-width: 8.5rem">我現有</th>
                    <th class="text-end">這項夠做</th>
                    <th class="text-end">做完剩下</th>
                    <th v-if="result.target > 0" class="text-end pe-3">
                      做 {{ result.target }} 個還缺
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in result.rows" :key="row.key"
                    :class="{ 'row-bottleneck': row.isBottleneck && result.maxCraftable !== null }">
                    <td class="ps-3">
                      <span class="fw-semibold">{{ row.name }}</span>
                    </td>
                    <td class="text-end">
                      <template v-if="row.need">{{ fmt(row.need) }} {{ unitLabel(row.unit) }}</template>
                      <span v-else class="hint" title="主檔沒有這項的數量">未知</span>
                    </td>
                    <td>
                      <div class="d-flex gap-1">
                        <input type="number" min="0"
                          :step="row.unit === UNIT_SCU && amountUnit[row.key] !== 'cscu' ? 0.01 : 1"
                          class="form-control form-control-sm"
                          :value="displayAmount(row)"
                          @input="setDisplayAmount(row, $event.target.value)"
                          :aria-label="`${row.name} 現有數量`">
                        <select v-if="row.unit === UNIT_SCU" :value="amountUnit[row.key] || 'scu'"
                          @change="amountUnit[row.key] = $event.target.value"
                          class="form-select form-select-sm" style="max-width: 6rem"
                          :aria-label="`${row.name} 單位`">
                          <option value="scu">SCU</option>
                          <option value="cscu">cSCU</option>
                        </select>
                      </div>
                    </td>
                    <td class="text-end">
                      <span v-if="row.canMake === null" class="hint">—</span>
                      <span v-else>{{ row.canMake }} 個</span>
                    </td>
                    <td class="text-end hint">
                      <span v-if="row.leftover === null">—</span>
                      <span v-else>{{ fmt(row.leftover) }} {{ unitLabel(row.unit) }}</span>
                    </td>
                    <td v-if="result.target > 0" class="text-end pe-3">
                      <span v-if="row.shortfall === null" class="hint">—</span>
                      <span v-else-if="row.shortfall > 0" class="text-danger fw-semibold">
                        {{ fmt(row.shortfall) }} {{ unitLabel(row.unit) }}
                      </span>
                      <span v-else class="text-success">✓</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div v-if="recipe.dismantle_returns?.length" class="small hint mt-2">
          拆解可回收：{{ recipe.dismantle_returns.map(r => `${r.name} ${r.quantity_scu} SCU`).join('、') }}
        </div>
      </template>
    </template>

    <div v-else class="text-center hint py-5">
      先在上面搜尋並選一張藍圖。
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import {
  calcCraft, craftTimeLabel, normalizeIngredients, stockToHaveMap, unitLabel, UNIT_SCU,
} from '@/utils/craftCalc'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'

const props = defineProps({
  /** 帶身分的 fetch（後台用 apiFetch、玩家頁用 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /** 可選：載入庫存列的函式，收到材料列、回傳 [{item_id, quantity, total_scu}] */
  stockLoader: { type: Function, default: null },
  /** 「從○○帶入」按鈕上的字 */
  stockLabel: { type: String, default: '庫存' },
  /**
   * 卡片的 class。後台是淺色卡，玩家頁是 scifi 深色卡 ——
   * 元件自己寫死 `scifi-card` 的話，後台主題下卡片會變深色而文字留在深灰，
   * 整段說明文字直接消失（已用截圖確認過這個災難）。
   */
  cardClass: { type: String, default: 'card shadow-sm border-0' },
})

// 同一頁可能掛兩個實例（理論上），id 不能寫死，否則 label/aria 會指到別人
const uid = Math.random().toString(36).slice(2, 8)
const searchId = `bpcalc-q-${uid}`
const listId = `bpcalc-list-${uid}`
const targetId = `bpcalc-target-${uid}`

const keyword = ref('')
const results = ref([])
const searching = ref(false)
const showResults = ref(false)
const highlighted = ref(-1)

const recipe = ref(null)
const loadingRecipe = ref(false)
const loadError = ref('')
const loadingStock = ref(false)

const amounts = reactive({})
const target = ref('')

// ── SCU 材料的輸入單位（SCU／cSCU）─────────────────────────────
//
// amounts[row.key] 永遠存「這一列原生單位」的數值（SCU 材料就是 SCU，
// 跟 craftCalc.js 的計算邏輯、stockToHaveMap()／從庫存帶入的值都用同一個
// 單位，不然瓶頸／缺料的算法要到處做單位轉換，很容易漏掉一個地方）。
// amountUnit 只是「使用者這一列想用哪個單位打字」的畫面狀態，輸入框
// 顯示、輸入的當下即時換算成/從 SCU，換算只發生在這裡兩個函式，
// 不影響任何試算邏輯。
// 預設 'scu'：沒選過的話行為跟改動前一樣（直接打 SCU，可以打小數）。
const amountUnit = reactive({})

/** 換算到最多 4 位小數，避免 0.07 * 100 這種浮點誤差顯示成 7.000000000000001。 */
function round(value, decimals) {
  const f = 10 ** decimals
  return Math.round(value * f) / f
}

/** 依這一列目前選的單位，把 amounts[row.key]（永遠是 SCU）換算成畫面上該顯示的值。 */
function displayAmount(row) {
  const raw = amounts[row.key]
  if (raw === undefined || raw === null || raw === '') return raw ?? ''
  if (row.unit === UNIT_SCU && amountUnit[row.key] === 'cscu') {
    const n = Number(raw)
    return Number.isFinite(n) ? round(n * 100, 2) : raw
  }
  return raw
}

/** 使用者在輸入框打字時：把畫面上的值（可能是 cSCU）換算回 SCU 存進 amounts。 */
function setDisplayAmount(row, value) {
  if (value === '') { amounts[row.key] = ''; return }
  const n = Number(value)
  if (!Number.isFinite(n)) return
  amounts[row.key] = (row.unit === UNIT_SCU && amountUnit[row.key] === 'cscu')
    ? round(n / 100, 4)
    : n
}

const activeOptionId = computed(() =>
  highlighted.value >= 0 ? `${listId}-opt-${highlighted.value}` : undefined)

const rows = computed(() => normalizeIngredients(recipe.value))
const result = computed(() => calcCraft(rows.value, amounts, target.value))

const bottleneckNames = computed(() => result.value.rows
  .filter(row => row.isBottleneck)
  .map(row => row.name)
  .join('、'))

const totalTime = computed(() => craftTimeLabel(
  recipe.value?.craft_time_seconds, result.value.maxCraftable))

/** 小數只在需要時顯示，避免 4 變成 4.00 */
function fmt(value) {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100)
}

// ── 搜尋（debounce + 過期回應防護）────────────────────────────
//
// seq 是「這是第幾次搜尋」的序號：慢回應回來時如果已經不是最新一次，
// 就整包丟掉。少了這道防護，打字快的時候先送出的舊結果會蓋掉新結果
// （這個專案別處踩過同樣的坑）。
let searchTimer = null
let seq = 0

function onSearchInput() {
  showResults.value = true
  highlighted.value = -1
  clearTimeout(searchTimer)
  const q = keyword.value.trim()
  if (q.length < 2) {
    results.value = []
    searching.value = false
    seq += 1        // 讓還在飛的請求作廢
    return
  }
  searching.value = true
  searchTimer = setTimeout(() => runSearch(q), 300)
}

async function runSearch(q) {
  const mine = ++seq
  const res = await props.fetcher(
    `/blueprint/master/search?q=${encodeURIComponent(q)}&limit=20`)
  if (mine !== seq) return        // 已經有更新的一次搜尋，這包過期了
  const data = res ? await res.json().catch(() => null) : null
  if (mine !== seq) return
  results.value = data?.success ? (data.data || []) : []
  searching.value = false
}

function onSearchKeydown(event) {
  if (event.key === 'Escape') { showResults.value = false; return }
  if (!showResults.value || !results.value.length) return

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    highlighted.value = (highlighted.value + 1) % results.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    highlighted.value = highlighted.value <= 0
      ? results.value.length - 1
      : highlighted.value - 1
  } else if (event.key === 'Enter') {
    event.preventDefault()
    selectBlueprint(results.value[highlighted.value >= 0 ? highlighted.value : 0])
  }
}

function onSearchBlur() {
  // 延遲關閉，否則點選項時清單會先消失（mousedown 已經處理選取，這裡只收尾）
  setTimeout(() => { showResults.value = false }, 120)
}

// ── 載入配方 ──────────────────────────────────────────────────

// 載入配方也要有過期回應防護：先點 A（慢）再點 B（快）的話，
// A 的回應晚到會蓋掉 B 的配方 —— 畫面標題顯示 B、材料表卻是 A 的。
let recipeSeq = 0

async function selectBlueprint(bp) {
  if (!bp) return
  const mine = ++recipeSeq
  showResults.value = false
  keyword.value = bp.name_zh || bp.name || ''
  loadError.value = ''
  loadingRecipe.value = true
  recipe.value = null
  clearAmounts()

  try {
    const res = await props.fetcher(`/blueprint/master/${bp._id}`)
    if (mine !== recipeSeq) return          // 已經有更新的一次選取
    const data = res ? await res.json().catch(() => null) : null
    if (mine !== recipeSeq) return
    if (data?.success) {
      recipe.value = data.data
    } else {
      loadError.value = data?.message || '讀取配方失敗，請稍後再試'
    }
  } finally {
    if (mine === recipeSeq) loadingRecipe.value = false
  }
}

function clearAmounts() {
  Object.keys(amounts).forEach(key => { delete amounts[key] })
}

async function fillFromStock() {
  if (!props.stockLoader) return
  loadingStock.value = true
  loadError.value = ''
  try {
    // loader 可以回陣列（舊契約）或 { rows, failed }。failed 一定要講出來 ——
    // 靜默跳過讀取失敗的材料會讓它留空、被當成 0，畫面就會顯示
    // 「最多可做 0 個」並把它標成瓶頸，而使用者完全不知道那只是讀取失敗。
    const loaded = await props.stockLoader(rows.value)
    const stockRows = Array.isArray(loaded) ? loaded : (loaded?.rows || [])
    const failed = Array.isArray(loaded) ? 0 : (loaded?.failed || 0)

    const found = stockToHaveMap(rows.value, stockRows)
    // 只覆蓋庫存裡真的有的材料，其他保留使用者自己填的值
    Object.entries(found).forEach(([key, value]) => { amounts[key] = value })

    if (failed) {
      loadError.value = `有 ${failed} 種材料的${props.stockLabel}數量讀取失敗，`
        + '那幾列請手動確認後再看試算結果。'
    } else if (!Object.keys(found).length) {
      loadError.value = `${props.stockLabel}裡沒有這張藍圖需要的任何材料，請手動填入。`
    }
  } catch {
    loadError.value = `讀取${props.stockLabel}失敗，請稍後再試。`
  } finally {
    loadingStock.value = false
  }
}

onBeforeUnmount(() => clearTimeout(searchTimer))
</script>

<style scoped>
/* 瓶頸列淡黃底，不用文字說明也能一眼看出卡在哪一種材料 */
.row-bottleneck > td {
  background: rgba(255, 193, 7, .12);
}

/* 次要文字：用 opacity 而不是固定灰色，這樣在後台的淺色卡與玩家頁的
   深色 scifi 卡上都讀得到（Bootstrap 的 .text-muted 在深底上會消失）。 */
.hint {
  opacity: .72;
}
</style>
