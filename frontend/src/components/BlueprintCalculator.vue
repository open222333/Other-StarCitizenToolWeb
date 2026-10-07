<!--
  藍圖材料試算：選一張藍圖 → 輸入要做幾個 → 列出每種材料總共需要多少。
  （原本「填現有材料／從個人庫帶入、算最多可做幾個」的部分已拿掉，使用者要求只留需求量。）
  藍圖與礦物材料附上 sc-datahub.com 的對應頁面（網址規則見 utils/blueprintMaterial.js）。

  掛在玩家頁 MyPlayerView「我的藍圖」每一列的「材料」展開（用 playerFetch）。
  後台原本也有一個入口（公會共享庫），已移除——後台只看資料庫，不重複玩家
  頁的功能。取資料仍一律走 `fetcher` prop，不直接碰任何 store。

  `blueprint`：指定一張藍圖（{_id, name, name_zh}）時不顯示搜尋框，直接載入那張的配方——
  玩家頁「我的藍圖」每一列的「材料」展開就是用這個模式（原本獨立的「試算」分頁已併進去）。

  計算邏輯全部在 utils/craftCalc.js（純函式、有測試：npm run test:calc），
  這個檔案只負責畫面與互動。
-->
<template>
  <div>
    <!-- ── 選藍圖（指定了 blueprint 就不需要）──────────────── -->
    <div v-if="!blueprint" :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body">
        <label class="form-label small fw-semibold" :for="searchId">藍圖名稱</label>
        <div class="position-relative">
          <input :id="searchId" v-model="keyword" type="text" class="form-control"
            placeholder="搜尋藍圖"
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
            <a v-if="blueprintDatahubUrl(recipe.name)" class="btn btn-sm btn-primary"
              :href="blueprintDatahubUrl(recipe.name)" target="_blank" rel="noopener noreferrer">
              sc-datahub<i class="bi bi-box-arrow-up-right ms-1"></i>
            </a>
          </div>
          <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
            <label class="form-label fw-semibold mb-0" :for="targetId">要做</label>
            <input :id="targetId" v-model="target" type="number" min="1" step="1"
              class="form-control form-control-sm" style="max-width: 6rem">
            <span>個</span>
            <span v-if="totalTime" class="hint ms-2">全部做完約需 {{ totalTime }}</span>
          </div>
        </div>
      </div>

      <!-- 沒有配方資料：要講清楚是「主檔沒同步到」而不是「這張圖不用材料」 -->
      <div v-if="!rows.length" class="alert alert-warning">
        這張藍圖的主檔裡沒有材料資料（遊戲資料同步時可能沒帶到配方明細），所以無法試算。
      </div>

      <template v-else>
        <div :class="cardClass">
          <div class="card-body p-0">
            <div style="overflow-x: auto">
              <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
                  <tr>
                    <th class="ps-3">材料</th>
                    <th class="text-end">每個需要</th>
                    <th class="text-end">做 {{ count }} 個需要</th>
                    <th class="pe-3"></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in rows" :key="row.key">
                    <td class="ps-3">
                      <span class="fw-semibold">{{ materialLabel(row) }}</span>
                    </td>
                    <td class="text-end">
                      <template v-if="row.need">{{ qtyLabel(row.need, row.unit) }}</template>
                      <span v-else class="hint" title="主檔沒有這項的數量">未知</span>
                    </td>
                    <td class="text-end fw-semibold">
                      <template v-if="row.need">{{ qtyLabel(row.need * count, row.unit) }}</template>
                      <span v-else class="hint">—</span>
                    </td>
                    <td class="pe-3 text-end">
                      <a v-if="materialDatahubUrl(row)" class="btn btn-sm btn-primary"
                        :href="materialDatahubUrl(row)" target="_blank" rel="noopener noreferrer"
                        :aria-label="`${row.name} 在 sc-datahub 的頁面`">
                        sc-datahub<i class="bi bi-box-arrow-up-right ms-1"></i>
                      </a>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div v-if="recipe.dismantle_returns?.length" class="small hint mt-2">
          拆解可回收：{{ recipe.dismantle_returns.map(r => `${materialLabel(r)} ${qtyLabel(r.quantity_scu, UNIT_SCU)}`).join('、') }}
        </div>
      </template>
    </template>

    <div v-else-if="!blueprint" class="text-center hint py-5">
      先在上面搜尋並選一張藍圖。
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { craftTimeLabel, normalizeIngredients, unitLabel, UNIT_SCU } from '@/utils/craftCalc'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'
import {
  blueprintDatahubUrl, loadMaterialZh, materialDatahubUrl, materialLabel,
} from '@/utils/blueprintMaterial'

const props = defineProps({
  /** 帶身分的 fetch（後台用 apiFetch、玩家頁用 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /**
   * 卡片的 class。後台是淺色卡，玩家頁是 scifi 深色卡 ——
   * 元件自己寫死 `scifi-card` 的話，後台主題下卡片會變深色而文字留在深灰，
   * 整段說明文字直接消失（已用截圖確認過這個災難）。
   */
  cardClass: { type: String, default: 'card shadow-sm border-0' },
  /** 指定藍圖 {_id: 藍圖 uuid, name, name_zh}：不顯示搜尋框，直接載入這張的配方 */
  blueprint: { type: Object, default: null },
})

const currentId = ref('')


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

const target = ref(1)

const activeOptionId = computed(() =>
  highlighted.value >= 0 ? `${listId}-opt-${highlighted.value}` : undefined)

const rows = computed(() => normalizeIngredients(recipe.value))
/** 要做幾個（空白或不合法當 1） */
const count = computed(() => {
  const n = Math.floor(Number(target.value))
  return Number.isFinite(n) && n > 0 ? n : 1
})

const totalTime = computed(() => craftTimeLabel(recipe.value?.craft_time_seconds, count.value))

/** 小數只在需要時顯示，避免 4 變成 4.00 */
function fmt(value) {
  if (value === null || value === undefined) return '—'
  return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100)
}

/** 數量＋單位；SCU 另外附上 cSCU（1 SCU = 100 cSCU），例如「0.05 SCU（5 cSCU）」 */
function qtyLabel(value, unit) {
  if (value === null || value === undefined) return '—'
  if (unit === UNIT_SCU) return `${fmt(value)} SCU（${fmt(value * 100)} cSCU）`
  return `${fmt(value)} ${unitLabel(unit)}`
}

// ── 搜尋（debounce + 過期回應防護）────────────────────────────
//
// seq 是「這是第幾次搜尋」的序號：慢回應回來時如果已經不是最新一次，
// 就整包丟掉。少了這道防護，打字快的時候先送出的舊結果會蓋掉新結果
// （這個專案別處踩過同樣的坑）。
let searchTimer = null
let seq = 0

function onSearchInput() {
  highlighted.value = -1
  clearTimeout(searchTimer)
  const q = keyword.value.trim()
  showResults.value = true
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
  currentId.value = bp._id || ''
  const mine = ++recipeSeq
  showResults.value = false
  keyword.value = bp.name_zh || bp.name || ''
  loadError.value = ''
  loadingRecipe.value = true
  recipe.value = null
  target.value = 1

  try {
    const res = await props.fetcher(`/blueprint/master/${bp._id}`)
    if (mine !== recipeSeq) return          // 已經有更新的一次選取
    const data = res ? await res.json().catch(() => null) : null
    if (mine !== recipeSeq) return
    if (data?.success) {
      recipe.value = data.data
      loadMaterialZh(data.data)   // 材料（礦物／物品）的中文
    } else {
      loadError.value = data?.message || '讀取配方失敗，請稍後再試'
    }
  } finally {
    if (mine === recipeSeq) loadingRecipe.value = false
  }
}

onBeforeUnmount(() => clearTimeout(searchTimer))
// 指定了藍圖（「我的藍圖」的材料展開）：一掛上就載入，換藍圖就重載。放在最後，
// 確保 selectBlueprint 用到的變數都已經宣告。
watch(() => props.blueprint?._id, (id) => { if (id) selectBlueprint(props.blueprint) }, { immediate: true })
</script>

<style scoped>
/* 次要文字：用 opacity 而不是固定灰色，這樣在後台的淺色卡與玩家頁的
   深色 scifi 卡上都讀得到（Bootstrap 的 .text-muted 在深底上會消失）。 */
.hint {
  opacity: .72;
}
</style>
