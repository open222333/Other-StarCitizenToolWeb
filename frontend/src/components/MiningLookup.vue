<!--
  礦物參考查詢（唯讀）——共用元件，被兩個地方掛載（同一份實作，各自帶自己的身分）：
    - 後台：views/MiningView.vue（用 apiFetch）
    - 玩家頁：MyPlayerView 的「礦物」分頁（用 playerFetch）
  所以這裡不直接碰 api/index.js 的 miningApi，取資料一律走 `fetcher` prop
  （跟 BlueprintCalculator.vue 是同一個做法）。

  資料來源是 scunpacked-data（StarCitizenWiki 維護的解包資料集），由
  tasks/scdata_sync.py 定期同步，兩種東西都在裡面：

  - 礦床成分（parts）：某種礦床可能含哪些礦物、比例區間（%）、出現機率——
    右側「礦物訊號參考」用這個。
  - 單顆訊號值（signature）：船艦感測器掃到單顆這種礦床時回傳的雷達截面
    基準值（RS）。一叢礦石是這個值的整數倍（遊戲內一叢最多 10 顆），
    例如單顆 3000、掃到 3 顆一叢畫面上就會顯示 9000——左側「回波」就是
    拿玩家輸入的掃描值去反查「單顆值 × 1~10 顆」有沒有對得上。
    少數 FPS 徒手採礦專用的項目沒有這個值（船艦掃描器用不到），
    比對時會被排除。

  兩者都是**靜態**的遊戲設定值，隨改版由 scdata sync 更新，跟玩家實際
  掃描當下看到的畫面應該一致（除非該版本剛好還沒同步到）。

  礦物、礦床、地點的中文名稱都來自 src/sc_zh.py（社群翻譯包 + 少數標準地質/
  天文學術語），查不到就顯示英文名，不會讓畫面掛掉——詳見該檔案的檔頭說明。

  資料量小（目前約 270 個礦床、60 個地點群組），後端 /mining/deposits、
  /mining/locations 都是一次回全部、不分頁，左右兩側的比對/搜尋都在前端做。

  ⚠️ 右側刻意不顯示市場價格：這套系統目前沒有礦物/商品的 UEX 價格資料
  （需要設定 UEX_API_TOKEN 才能同步，且目前也還沒有對應的同步流程），
  硬做一個假數字出來會誤導玩家，所以只顯示訊號值。

  ⚠️ 同一種礦物在不同礦床/尺寸下，單顆基準訊號值其實常常不一樣（例如
  Hephaestanite 實際同時有 4000/4180/4210/4255/4700 好幾種）。右側只能
  顯示一組「1~10 倍」的參考格子，這裡選「出現次數最多」的那組當代表值
  （見 commonSignatureFor()），下方標註這只是常見值，並保留「顯示完整
  礦床明細」把所有變體攤開，不會把資訊藏起來。
-->
<template>
  <div class="mining-echo">
    <div class="row g-3 g-lg-4">
      <!-- ══ 左：回波（輸入掃描訊號值 → 反查礦床＋顆數）══ -->
      <div class="col-12 col-lg-6">
        <div class="mining-echo__label">
          <span>回波</span>
        </div>
        <div class="mining-echo__search mb-3">
          <i class="bi bi-search"></i>
          <input v-model="resonanceInput" type="number" min="0" step="1"
            placeholder="輸入掃描到的訊號值（RS）" aria-label="輸入掃描到的訊號值">
          <button v-if="resonanceInput !== ''" type="button" class="mining-echo__clear"
            aria-label="清除" @click="resonanceInput = ''">×</button>
        </div>

        <div v-if="loadingDeposits" class="mining-echo__panel text-center py-4">
          <span class="spinner-border spinner-border-sm me-2"></span>載入中...
        </div>
        <div v-else-if="resonanceInput === ''" class="mining-echo__panel mining-echo__panel--empty text-center py-4">
          請輸入船艦感測器掃描到的訊號值，反查可能是哪個礦床、幾顆
        </div>
        <div v-else-if="!signatureMatches.length" class="mining-echo__panel mining-echo__panel--empty text-center py-4">
          沒有礦床的「單顆訊號值 × 顆數」對得上 {{ resonanceInput }}
        </div>
        <template v-else>
          <div class="mining-echo__panel mining-echo__panel--result">
            <span class="mining-echo__pill">
              <i class="bi bi-check-lg"></i>MATCH ACQUIRED
            </span>
            <h3 class="mining-echo__title">{{ depositLabel(bestMatch) }}</h3>

            <div class="mining-echo__stats">
              <div class="mining-echo__stat">
                <div class="mining-echo__stat-label">CLUSTER SIZE</div>
                <div class="mining-echo__stat-value">{{ bestMatch.rock_count }} <small>RCKS</small></div>
              </div>
              <div class="mining-echo__stat mining-echo__stat--accent">
                <div class="mining-echo__stat-label">TARGET RS</div>
                <div class="mining-echo__stat-value">{{ fmtInt(bestMatch.expected) }} <small>SIG</small></div>
              </div>
              <div class="mining-echo__stat">
                <div class="mining-echo__stat-label">CONFIDENCE</div>
                <div class="mining-echo__stat-value mining-echo__stat-value--ok">{{ fmtConfidence(bestMatch) }}</div>
              </div>
            </div>

            <p class="mining-echo__hint mb-0">可能礦物：{{ partsSummary(bestMatch.parts) }}</p>
          </div>

          <button v-if="signatureMatches.length > 1" type="button"
            class="mining-echo__diagnostics-toggle" @click="showDiagnostics = !showDiagnostics">
            RUN FULL DIAGNOSTICS（還有 {{ signatureMatches.length - 1 }} 筆可能吻合）
            <i class="bi" :class="showDiagnostics ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          </button>

          <div v-show="showDiagnostics" class="mining-echo__panel mining-echo__panel--table mt-2">
            <div style="overflow-x:auto">
              <table class="table table-sm table-hover align-middle mb-0 mining-echo__table">
                <thead>
                  <tr>
                    <th class="ps-3">礦床</th>
                    <th>Tier</th>
                    <th>顆數</th>
                    <th>對應訊號值</th>
                    <th>誤差</th>
                    <th class="pe-3">可能礦物</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(m, idx) in signatureMatches.slice(1)" :key="idx">
                    <td class="ps-3 fw-semibold">{{ depositLabel(m) }}</td>
                    <td>
                      <span v-if="m.tier" class="mining-echo__tag">{{ m.tier }}</span>
                      <span v-else>—</span>
                    </td>
                    <td>{{ m.rock_count }} 顆</td>
                    <td>{{ fmtInt(m.expected) }}</td>
                    <td>{{ fmtDiff(m) }}</td>
                    <td class="pe-3">{{ partsSummary(m.parts) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>

        <p class="mining-echo__footnote">
          同一個數字可能同時符合好幾個礦床（不同顆數也可能湊出接近的值），最佳吻合（誤差最小）當主結果卡，其餘收進上面的完整診斷，實際礦物仍須以遊戲內判讀為準。少數 FPS 徒手採礦專用的礦床沒有船艦掃描訊號值，不會出現在這裡。
        </p>
      </div>

      <!-- ══ 右：礦物訊號參考（輸入名稱 → 常見單顆訊號值 × 1~10 顆）══ -->
      <div class="col-12 col-lg-6">
        <div class="mining-echo__label">
          <span>礦物訊號參考</span>
        </div>
        <div class="mining-echo__search mb-3">
          <i class="bi bi-search"></i>
          <input v-model="mineralQuery" type="search" placeholder="搜尋礦物..."
            aria-label="搜尋礦物名稱" role="combobox" aria-autocomplete="list"
            :aria-expanded="showMineralSuggestions"
            @input="onMineralInput" @focus="onMineralFocus" @blur="onMineralBlur">
          <i class="bi bi-chevron-down mining-echo__chevron"></i>

          <ul v-if="showMineralSuggestions" class="mining-echo__suggest" role="listbox">
            <li v-if="!mineralSuggestions.length" class="mining-echo__suggest-hint">
              找不到符合「{{ mineralQuery }}」的礦物
            </li>
            <li v-for="g in mineralSuggestions" :key="g.resource_key"
              class="mining-echo__suggest-item"
              @mousedown.prevent="selectMineral(g)">
              {{ mineralLabel(g) }}
            </li>
          </ul>
        </div>

        <div v-if="loadingDeposits" class="mining-echo__panel text-center py-4">
          <span class="spinner-border spinner-border-sm me-2"></span>載入中...
        </div>
        <div v-else-if="!selectedMineral" class="mining-echo__panel mining-echo__panel--empty text-center py-4">
          輸入礦物名稱，查詢常見的單顆基準訊號值
        </div>
        <template v-else>
          <div class="mining-echo__panel mining-echo__panel--result">
            <span class="mining-echo__pill mining-echo__pill--muted">
              <i class="bi bi-card-heading"></i>REFERENCE CARD
            </span>
            <h3 class="mining-echo__title">{{ mineralLabel(selectedMineral) }}</h3>

            <div v-if="referenceSignature" class="mining-echo__grid">
              <div v-for="step in referenceSteps" :key="step.n" class="mining-echo__cell">
                <div class="mining-echo__cell-mult">{{ step.n }}X</div>
                <div class="mining-echo__cell-label">SIGNATURE</div>
                <div class="mining-echo__cell-value">{{ fmtInt(step.value) }}</div>
              </div>
            </div>
            <p v-else class="mining-echo__hint mb-0">
              這個礦物沒有船艦掃描訊號值（可能是 FPS 徒手採礦專用）。
            </p>

            <p v-if="referenceSignature" class="mining-echo__footnote mb-0">
              <i class="bi bi-info-circle me-1"></i>數值代表 1～10 顆一叢的掃描訊號值。這是「{{ mineralLabel(selectedMineral) }}」最常見的單顆基準值（{{ fmtInt(referenceSignature) }}）——同礦種在不同礦床/尺寸下基準值可能不同，實際請以遊戲內判讀為準。
              <button type="button" class="btn btn-link btn-sm p-0 ms-1"
                @click="showMineralDetail = !showMineralDetail">
                {{ showMineralDetail ? '收起' : '顯示' }}完整礦床明細
              </button>
            </p>
          </div>

          <div v-show="showMineralDetail" class="mining-echo__panel mining-echo__panel--table mt-2">
            <p v-if="mineralLocations.length" class="mining-echo__hint px-3 pt-3 mb-2">
              可能出現地點：
              <span v-for="loc in mineralLocations" :key="loc.system + '/' + loc.location_name"
                class="mining-echo__tag mining-echo__tag--info me-1" :title="loc.system">
                {{ locationLabel(loc) }}
              </span>
            </p>
            <div style="overflow-x:auto">
              <table class="table table-sm table-hover align-middle mb-0 mining-echo__table">
                <thead>
                  <tr>
                    <th class="ps-3">所屬礦床</th>
                    <th>Tier</th>
                    <th>比例區間</th>
                    <th>機率</th>
                    <th class="pe-3">單顆訊號值</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="dep in mineralDeposits" :key="dep._rowKey">
                    <td class="ps-3 fw-semibold">{{ depositLabel(dep) }}</td>
                    <td>
                      <span v-if="dep.tier" class="mining-echo__tag">{{ dep.tier }}</span>
                      <span v-else>—</span>
                    </td>
                    <td>{{ fmtRange(dep.min_percentage, dep.max_percentage) }}</td>
                    <td>{{ fmtPct(dep.probability) }}</td>
                    <td class="pe-3">
                      <span v-if="dep.signature">{{ fmtInt(dep.signature) }}</span>
                      <span v-else title="這個礦床沒有船艦掃描訊號值（可能是 FPS 徒手採礦專用）">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>

        <p class="mining-echo__footnote">
          礦物、礦床、地點的中文名稱來自社群翻譯包，查不到就顯示英文。這是靜態的遊戲設定值參考表，不是玩家實際掃描到的即時回波。
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  /** 帶身分的 fetch（後台用 apiFetch、玩家頁用 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /**
   * 是否為目前可見的分頁。玩家頁的分頁全部用 v-show（切分頁不重新掛載，
   * 保留使用者輸入到一半的內容），代表這個元件在玩家一進頁面時就已經
   * 掛載了——如果 onMounted 就無條件打兩支 API，等於每個玩家每次開
   * 個人頁都會抓一份礦物參考表，即使他根本沒點進「礦物」分頁。
   * 所以資料改成「第一次變成可見時才載入」，之後切走再切回來不重載。
   * 後台是獨立頁面（MiningView.vue），維持原本「一進頁就載入」，
   * 所以預設值是 true。
   */
  active: { type: Boolean, default: true },
})

// ── 資料載入（第一次 active 變 true 時才載入一次）───────────────────
const deposits = ref([])
const locations = ref([])
const loadingDeposits = ref(false)
let loaded = false

async function loadData() {
  if (loaded) return
  loaded = true
  loadingDeposits.value = true
  try {
    const [depRes, locRes] = await Promise.all([
      props.fetcher('/mining/deposits'),
      props.fetcher('/mining/locations'),
    ])
    const depData = depRes ? await depRes.json().catch(() => null) : null
    deposits.value = depData?.success ? (depData.data || []) : []
    const locData = locRes ? await locRes.json().catch(() => null) : null
    locations.value = locData?.success ? (locData.data || []) : []
  } finally {
    loadingDeposits.value = false
  }
}

watch(() => props.active, (v) => { if (v) loadData() }, { immediate: true })

// ── 共用：把所有礦床的成分攤平成一份清單，帶著所屬礦床脈絡 ──────────
const flatParts = computed(() => {
  const rows = []
  for (const d of deposits.value) {
    for (const p of (d.parts || [])) {
      rows.push({
        deposit_id: d._id, deposit_name: d.deposit_name, deposit_name_zh: d.deposit_name_zh,
        tier: d.tier, signature: d.signature,
        resource_key: p.resource_key, resource_name: p.resource_name,
        resource_name_zh: p.resource_name_zh,
        min_percentage: p.min_percentage, max_percentage: p.max_percentage,
        probability: p.probability,
      })
    }
  }
  return rows
})

function mineralLabel(p) {
  if (p.resource_name_zh) return `${p.resource_name_zh}（${p.resource_name || p.resource_key}）`
  return p.resource_name || p.resource_key
}

function depositLabel(d) {
  if (d.deposit_name_zh) return `${d.deposit_name_zh}（${d.deposit_name}）`
  return d.deposit_name
}

function locationLabel(loc) {
  if (loc.location_name_zh) return `${loc.location_name_zh}（${loc.location_name}）`
  return loc.location_name
}

function fmtPct(v) {
  if (v === null || v === undefined) return '—'
  return `${Math.round(v * 100)}%`
}

function fmtRange(min, max) {
  if (min === null || min === undefined || max === null || max === undefined) return '—'
  return `${min}–${max}%`
}

function fmtInt(v) {
  if (v === null || v === undefined) return '—'
  return Math.round(v).toLocaleString('en-US')
}

function partsSummary(parts) {
  if (!parts || !parts.length) return '—'
  return parts.map(p => {
    const label = mineralLabel(p)
    const range = fmtRange(p.min_percentage, p.max_percentage)
    return `${label} ${range}`
  }).join('、')
}

// ── 左：回波 —— 輸入船艦掃描訊號值 → 反查「單顆基準值 × 1~10 顆」───────
//
// 遊戲內一叢礦石最多 10 顆，掃描器回傳的整叢訊號值是「單顆基準值 × 顆數」
// 的整數倍——這是確定性的算式，不是機率，所以容許誤差抓很小（1.5%）
// 只是為了吸收顯示位數捨入，不是真的在做模糊比對。
const SIGNATURE_TOLERANCE = 0.015

const resonanceInput = ref('')

// 使用者改輸入值時，先前展開的完整診斷區塊沒必要留著（結果已經不一樣了）。
const showDiagnostics = ref(false)
watch(resonanceInput, () => { showDiagnostics.value = false })

const signatureMatches = computed(() => {
  const v = parseFloat(resonanceInput.value)
  if (!v || Number.isNaN(v) || v <= 0) return []

  const seen = new Set()
  const matches = []
  for (const d of deposits.value) {
    const sig = d.signature
    if (!sig || sig <= 0) continue
    // 同一種礦床在資料集裡常常有好幾個變體（一般/大顆/小顆模型），
    // 成分與單顆訊號值完全一樣——用「礦床名稱＋Tier＋顆數」去重，
    // 不然畫面會出現好幾筆一模一樣的結果。
    const dedupeKey = `${d.deposit_name}__${d.tier}`
    for (let n = 1; n <= 10; n++) {
      const expected = sig * n
      const diff = Math.abs(v - expected)
      if (diff / expected > SIGNATURE_TOLERANCE) continue
      const key = `${dedupeKey}__${n}`
      if (seen.has(key)) continue
      seen.add(key)
      matches.push({
        deposit_name: d.deposit_name, deposit_name_zh: d.deposit_name_zh,
        tier: d.tier, rock_count: n,
        expected, diff, parts: d.parts,
      })
    }
  }
  matches.sort((a, b) => a.diff - b.diff)
  return matches
})

// 排序後的第一筆＝誤差最小的最佳吻合，主結果卡用這筆。
const bestMatch = computed(() => signatureMatches.value[0] || null)

function fmtConfidence(m) {
  // 訊號值比對是「單顆基準值 × 顆數」的確定性算式，不是機率——這裡的信心度
  // 只是把已經算出來、在 SIGNATURE_TOLERANCE 容許範圍內的誤差換算成好懂的
  // 百分比顯示，不是額外的統計模型。
  const pct = Math.max(0, Math.min(100, 100 - (m.diff / m.expected) * 100))
  return `${pct.toFixed(1)}%`
}

function fmtDiff(m) {
  if (m.diff < 0.5) return '完全吻合'
  const pct = (m.diff / m.expected) * 100
  return `±${fmtInt(m.diff)}（${pct.toFixed(1)}%）`
}

// ── 右：礦物訊號參考 —— 輸入名稱（中/英皆可）→ 選定一種礦物 ─────────
//
// 跟左側「即時反查」不同，這裡是「打字看候選、選定才顯示參考卡」的
// autocomplete 互動（跟 AutocompleteField.vue／BlueprintCalculator.vue
// 選藍圖欄位同一套邏輯）——因為同一個名稱關鍵字常常同時對到好幾種礦物
// （例如「Ore」），選單只篩不定，必須讓使用者明確選定一個才能決定
// 右側參考卡要顯示誰。
const mineralGroups = computed(() => {
  const byKey = new Map()
  for (const p of flatParts.value) {
    if (!byKey.has(p.resource_key)) {
      byKey.set(p.resource_key, {
        resource_key: p.resource_key, resource_name: p.resource_name,
        resource_name_zh: p.resource_name_zh, deposits: [],
      })
    }
    byKey.get(p.resource_key).deposits.push(p)
  }
  return Array.from(byKey.values())
    .sort((a, b) => mineralLabel(a).localeCompare(mineralLabel(b), 'zh-Hant'))
})

const mineralQuery = ref('')
const selectedMineral = ref(null)
const showMineralSuggestions = ref(false)
const showMineralDetail = ref(false)

const mineralSuggestions = computed(() => {
  const raw = mineralQuery.value.trim()
  if (!raw) return mineralGroups.value.slice(0, 20)
  const q = raw.toLowerCase()
  return mineralGroups.value.filter(g =>
    (g.resource_name || '').toLowerCase().includes(q) ||
    (g.resource_name_zh || '').includes(raw) ||
    (g.resource_key || '').toLowerCase().includes(q)
  ).slice(0, 20)
})

function onMineralInput() {
  // 文字改了就代表使用者還沒重新選定——先撤銷上一次選定的礦物，避免
  // 參考卡繼續顯示一個跟輸入框文字對不上的舊結果。
  selectedMineral.value = null
  showMineralSuggestions.value = true
  showMineralDetail.value = false
}

function onMineralFocus() {
  showMineralSuggestions.value = true
}

function onMineralBlur() {
  // 延遲關閉，讓候選項的 mousedown 先觸發選定（同 AutocompleteField.vue 的理由）。
  setTimeout(() => { showMineralSuggestions.value = false }, 120)
}

function selectMineral(g) {
  selectedMineral.value = g
  mineralQuery.value = mineralLabel(g)
  showMineralSuggestions.value = false
  showMineralDetail.value = false
}

/** 選定礦物在所有礦床變體下最常出現的單顆基準訊號值（眾數）。
 *  同礦種在不同礦床/尺寸下基準值常常不一樣，這裡只能挑一組當代表值，
 *  平手時選數值較小的那組（決定性、不隨機）。查無任何訊號值回傳 null。 */
const referenceSignature = computed(() => {
  if (!selectedMineral.value) return null
  const counts = new Map()
  for (const dep of selectedMineral.value.deposits) {
    if (!dep.signature) continue
    counts.set(dep.signature, (counts.get(dep.signature) || 0) + 1)
  }
  if (!counts.size) return null
  let best = null
  for (const [sig, count] of counts) {
    if (!best || count > best.count || (count === best.count && sig < best.sig)) {
      best = { sig, count }
    }
  }
  return best.sig
})

/** 單顆基準值 × 1~10 顆——給右側參考卡的格子用。 */
const referenceSteps = computed(() => {
  const sig = referenceSignature.value
  if (!sig) return []
  return Array.from({ length: 10 }, (_, i) => ({ n: i + 1, value: sig * (i + 1) }))
})

// 同一種礦床常常在資料集裡有好幾筆幾乎一樣的紀錄（不同大小/版本的礦床
// 模板，但成分比例、機率、單顆訊號值完全相同）——依「礦床名稱＋Tier＋
// 比例區間＋機率＋單顆訊號值」去重，值真的不同的變體還是會各自留一筆。
const mineralDeposits = computed(() => {
  if (!selectedMineral.value) return []
  const seen = new Map()
  for (const dep of selectedMineral.value.deposits) {
    const key = [
      selectedMineral.value.resource_key, dep.deposit_name, dep.tier,
      dep.min_percentage, dep.max_percentage, dep.probability, dep.signature,
    ].join('|')
    if (!seen.has(key)) seen.set(key, { ...dep, _rowKey: key })
  }
  return Array.from(seen.values())
})

const mineralLocations = computed(() => {
  if (!selectedMineral.value) return []
  const depositIds = new Set(selectedMineral.value.deposits.map(d => d.deposit_id))
  const seen = new Set()
  const result = []
  for (const loc of locations.value) {
    if (!loc.location_name) continue
    let hit = false
    for (const g of (loc.groups || [])) {
      for (const dep of (g.deposits || [])) {
        if (depositIds.has(dep.resource_uuid)) { hit = true; break }
      }
      if (hit) break
    }
    if (!hit) continue
    const key = `${loc.system}/${loc.location_name}`
    if (seen.has(key)) continue
    seen.add(key)
    result.push({ system: loc.system, location_name: loc.location_name, location_name_zh: loc.location_name_zh })
  }
  return result.sort((a, b) => (a.system || '').localeCompare(b.system || '') || a.location_name.localeCompare(b.location_name))
})
</script>

<style scoped>
/* 自成一體的深色「終端機」卡片——不管掛在後台淺色頁還是玩家深色 scifi
   頁，都用自己固定的深色底＋青色 accent，跟畫面其餘部分的主題脫鉤。
   理由：這組畫面模仿的是儀表板 HUD 觀感，硬要跟著淺色主題走（例如
   後台）會整個看起來不協調；比照螢幕截圖，卡片本身就是深色的。 */
.mining-echo {
  --me-bg: #0a0f16;
  --me-panel: #0d141d;
  --me-border: rgba(84, 209, 223, .35);
  --me-border-hi: rgba(84, 209, 223, .7);
  --me-accent: #22d3ee;
  --me-text: #e7f6f8;
  --me-text-dim: rgba(231, 246, 248, .62);
  font-variant-numeric: tabular-nums;
}

.mining-echo__label {
  display: flex;
  align-items: center;
  gap: .5rem;
  font-size: .78rem;
  font-weight: 700;
  letter-spacing: .12em;
  color: var(--me-accent);
  margin-bottom: .6rem;
}
.mining-echo__label::before,
.mining-echo__label::after {
  content: '';
  flex: 1 1 auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--me-border-hi), transparent);
}

.mining-echo__search {
  position: relative;
  display: flex;
  align-items: center;
  gap: .5rem;
  background: var(--me-panel);
  border: 1px solid var(--me-border);
  border-radius: .4rem;
  padding: .55rem .75rem;
  color: var(--me-text);
}
.mining-echo__search > i:first-child { color: var(--me-accent); }
.mining-echo__search input {
  flex: 1 1 auto;
  min-width: 0;
  background: transparent;
  border: 0;
  color: var(--me-text);
  font-weight: 600;
  outline: none;
}
.mining-echo__search input::placeholder { color: var(--me-text-dim); }
.mining-echo__chevron { color: var(--me-text-dim); }
.mining-echo__clear {
  background: transparent;
  border: 0;
  color: var(--me-text-dim);
  font-size: 1.1rem;
  line-height: 1;
  padding: 0 .25rem;
}
.mining-echo__clear:hover { color: var(--me-text); }

.mining-echo__suggest {
  position: absolute;
  z-index: 30;
  top: calc(100% + .25rem);
  left: 0;
  right: 0;
  max-height: 16rem;
  overflow-y: auto;
  margin: 0;
  padding: .3rem;
  list-style: none;
  background: var(--me-panel);
  border: 1px solid var(--me-border);
  border-radius: .4rem;
  box-shadow: 0 .5rem 1.2rem rgba(0, 0, 0, .5);
}
.mining-echo__suggest-item {
  padding: .4rem .6rem;
  border-radius: .3rem;
  cursor: pointer;
  color: var(--me-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mining-echo__suggest-item:hover { background: rgba(34, 211, 238, .12); }
.mining-echo__suggest-hint {
  padding: .4rem .6rem;
  color: var(--me-text-dim);
  font-size: .85em;
}

.mining-echo__panel {
  background: var(--me-panel);
  border: 1px solid var(--me-border);
  border-radius: .5rem;
  color: var(--me-text);
  padding: 1.1rem 1.25rem;
}
.mining-echo__panel--empty { color: var(--me-text-dim); }
.mining-echo__panel--result { border-color: var(--me-border-hi); }
.mining-echo__panel--table { padding: 0; }
.mining-echo__panel--table table { color: var(--me-text); }

.mining-echo__pill {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .08em;
  color: var(--me-accent);
  background: rgba(34, 211, 238, .12);
  border: 1px solid var(--me-border);
  border-radius: .3rem;
  padding: .25rem .55rem;
  margin-bottom: .75rem;
}
.mining-echo__pill--muted {
  color: var(--me-text-dim);
  background: rgba(255, 255, 255, .04);
}

.mining-echo__title {
  font-weight: 800;
  letter-spacing: .02em;
  margin-bottom: 1rem;
  word-break: break-word;
}

.mining-echo__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .6rem;
  margin-bottom: .75rem;
}
.mining-echo__stat {
  background: rgba(255, 255, 255, .03);
  border: 1px solid var(--me-border);
  border-radius: .4rem;
  padding: .6rem .5rem;
  text-align: center;
}
.mining-echo__stat--accent { border-color: var(--me-border-hi); }
.mining-echo__stat-label {
  font-size: .68rem;
  letter-spacing: .08em;
  color: var(--me-text-dim);
  margin-bottom: .2rem;
}
.mining-echo__stat-value {
  font-size: 1.35rem;
  font-weight: 800;
}
.mining-echo__stat-value small { font-size: .6em; font-weight: 600; opacity: .75; }
.mining-echo__stat-value--ok { color: #34d399; }

.mining-echo__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .5rem;
  margin-bottom: .75rem;
}
@media (min-width: 400px) {
  .mining-echo__grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}
.mining-echo__cell {
  background: rgba(255, 255, 255, .03);
  border: 1px solid var(--me-border);
  border-radius: .4rem;
  padding: .5rem .4rem;
  text-align: center;
}
.mining-echo__cell-mult {
  position: absolute;
  font-size: .65rem;
  font-weight: 700;
  color: var(--me-text-dim);
}
.mining-echo__cell { position: relative; }
.mining-echo__cell-mult { top: .3rem; right: .4rem; }
.mining-echo__cell-label {
  font-size: .6rem;
  letter-spacing: .06em;
  color: var(--me-text-dim);
  margin-top: .6rem;
}
.mining-echo__cell-value {
  font-size: 1.05rem;
  font-weight: 800;
}

.mining-echo__hint { color: var(--me-text-dim); font-size: .85rem; }
.mining-echo__footnote {
  color: var(--me-text-dim);
  font-size: .78rem;
  opacity: .85;
  margin-top: .6rem;
}

.mining-echo__diagnostics-toggle {
  width: 100%;
  background: var(--me-panel);
  border: 1px dashed var(--me-border);
  border-radius: .4rem;
  color: var(--me-text-dim);
  font-size: .78rem;
  letter-spacing: .04em;
  padding: .5rem .75rem;
  margin-top: .6rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: .4rem;
}
.mining-echo__diagnostics-toggle:hover { color: var(--me-text); border-color: var(--me-border-hi); }

.mining-echo__tag {
  display: inline-block;
  font-size: .72rem;
  background: rgba(255, 255, 255, .06);
  border: 1px solid var(--me-border);
  border-radius: .25rem;
  padding: .05rem .4rem;
}
.mining-echo__tag--info { color: var(--me-accent); }

.mining-echo__table thead th {
  color: var(--me-text-dim);
  font-size: .72rem;
  letter-spacing: .05em;
  border-bottom-color: var(--me-border);
  background: transparent;
}
.mining-echo__table tbody td {
  border-color: var(--me-border);
  font-size: .85rem;
}
.mining-echo__table tbody tr:hover { background: rgba(34, 211, 238, .06); }
</style>
