<!--
  礦物參考查詢（唯讀）——共用元件，被兩個地方掛載（同一份實作，各自帶自己的身分）：
    - 後台：views/MiningView.vue（用 apiFetch）
    - 玩家頁：MyPlayerView 的「礦物」分頁（用 playerFetch）
  所以這裡不直接碰 api/index.js 的 miningApi，取資料一律走 `fetcher` prop
  （跟 BlueprintCalculator.vue 是同一個做法）。

  資料來源是 scunpacked-data（StarCitizenWiki 維護的解包資料集），由
  tasks/scdata_sync.py 定期同步，兩種東西都在裡面：

  - 礦床成分（parts）：某種礦床可能含哪些礦物、比例區間（%）、出現機率——
    「礦物搜尋」分頁用這個。
  - 單顆訊號值（signature）：船艦感測器掃到單顆這種礦床時回傳的雷達截面
    基準值（RS）。一叢礦石是這個值的整數倍（遊戲內一叢最多 10 顆），
    例如單顆 3000、掃到 3 顆一叢畫面上就會顯示 9000——「回波比對」分頁
    就是拿玩家輸入的掃描值去反查「單顆值 × 1~10 顆」有沒有對得上。
    少數 FPS 徒手採礦專用的項目沒有這個值（船艦掃描器用不到），
    比對時會被排除。

  兩者都是**靜態**的遊戲設定值，隨改版由 scdata sync 更新，跟玩家實際
  掃描當下看到的畫面應該一致（除非該版本剛好還沒同步到）。

  礦物、礦床、地點的中文名稱都來自 src/sc_zh.py（社群翻譯包 + 少數標準地質/
  天文學術語），查不到就顯示英文名，不會讓畫面掛掉——詳見該檔案的檔頭說明。

  資料量小（目前約 270 個礦床、60 個地點群組），後端 /mining/deposits、
  /mining/locations 都是一次回全部、不分頁，兩個分頁的比對/搜尋都在前端做。
-->
<template>
  <div>
    <ul class="nav nav-tabs mb-3" role="tablist">
      <li class="nav-item" role="presentation">
        <button type="button" class="nav-link" :class="{ active: activeTab === 'resonance' }"
          role="tab" :aria-selected="activeTab === 'resonance'" @click="activeTab = 'resonance'">
          回波比對
        </button>
      </li>
      <li class="nav-item" role="presentation">
        <button type="button" class="nav-link" :class="{ active: activeTab === 'search' }"
          role="tab" :aria-selected="activeTab === 'search'" @click="activeTab = 'search'">
          礦物搜尋
        </button>
      </li>
    </ul>

    <!-- ══ 回波比對：輸入掃描訊號值 → 反查礦床＋顆數 ══ -->
    <div v-show="activeTab === 'resonance'" role="tabpanel">
      <div :class="[cardClass, 'mb-3']">
        <div class="card-body py-2">
          <div class="d-flex flex-wrap align-items-center gap-2">
            <label class="small hint mb-0" for="resonance-input">輸入掃描到的訊號值（RS）</label>
            <input id="resonance-input" v-model="resonanceInput" type="number" min="0" step="1"
              class="form-control form-control-sm" style="max-width: 12rem" placeholder="例如 12855">
            <button v-if="resonanceInput" type="button" class="btn btn-sm btn-link" @click="resonanceInput = ''">
              清除
            </button>
          </div>
          <p class="small hint mb-0 mt-1">
            一叢礦石的訊號值＝單顆基準值 × 顆數（1～10 顆），這裡幫你反推可能是哪個礦床、幾顆。
          </p>
        </div>
      </div>

      <div v-if="loadingDeposits" :class="[cardClass, 'mb-4']">
        <div class="card-body text-center py-4 hint">
          <span class="spinner-border spinner-border-sm me-2"></span>載入中...
        </div>
      </div>

      <div v-else-if="resonanceInput === ''" :class="[cardClass, 'mb-4']">
        <div class="card-body text-center py-4 hint">
          請輸入船艦感測器掃描到的訊號值，反查可能是哪個礦床、幾顆
        </div>
      </div>

      <div v-else-if="!signatureMatches.length" :class="[cardClass, 'mb-4']">
        <div class="card-body text-center py-4 hint">
          沒有礦床的「單顆訊號值 × 顆數」對得上 {{ resonanceInput }}
        </div>
      </div>

      <template v-else>
        <!-- 最佳吻合（誤差最小的一筆）當主結果卡，其餘收進下面可展開的完整診斷 -->
        <div :class="[cardClass, 'mb-3 border-success']">
          <div class="card-body">
            <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
              <span class="badge bg-success-subtle text-success-emphasis">
                <i class="bi bi-check-circle-fill me-1"></i>比對成功
              </span>
              <span v-if="bestMatch.tier" class="badge bg-secondary-subtle text-secondary-emphasis">{{ bestMatch.tier }}</span>
            </div>
            <h4 class="mb-3">{{ depositLabel(bestMatch) }}</h4>
            <div class="row g-2 mb-2">
              <div class="col-6 col-md-4">
                <div class="border rounded p-2 text-center h-100">
                  <div class="small hint">顆數</div>
                  <div class="fs-5 fw-semibold">{{ bestMatch.rock_count }} 顆</div>
                </div>
              </div>
              <div class="col-6 col-md-4">
                <div class="border rounded p-2 text-center h-100">
                  <div class="small hint">對應訊號值</div>
                  <div class="fs-5 fw-semibold">{{ fmtInt(bestMatch.expected) }}</div>
                </div>
              </div>
              <div v-if="!isFullConfidence(bestMatch)" class="col-6 col-md-4">
                <div class="border rounded p-2 text-center h-100">
                  <div class="small hint">信心度</div>
                  <div class="fs-5 fw-semibold">{{ fmtConfidence(bestMatch) }}</div>
                </div>
              </div>
            </div>
            <p class="small hint mb-0">可能礦物：{{ partsSummary(bestMatch.parts) }}</p>
          </div>
        </div>

        <button v-if="signatureMatches.length > 1" type="button"
          class="btn btn-sm btn-outline-secondary mb-3" @click="showDiagnostics = !showDiagnostics">
          <i class="bi" :class="showDiagnostics ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          完整診斷：還有 {{ signatureMatches.length - 1 }} 筆可能吻合
        </button>

        <div v-show="showDiagnostics" :class="[cardClass, 'mb-4']">
          <div class="card-body p-0">
            <div style="overflow-x:auto">
              <table class="table table-hover align-middle mb-0">
                <thead class="table-light">
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
                      <span v-if="m.tier" class="badge bg-secondary-subtle text-secondary-emphasis">{{ m.tier }}</span>
                      <span v-else class="hint">—</span>
                    </td>
                    <td>{{ m.rock_count }} 顆</td>
                    <td>{{ fmtInt(m.expected) }}</td>
                    <td class="hint">{{ fmtDiff(m) }}</td>
                    <td class="pe-3">{{ partsSummary(m.parts) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </template>

      <p class="small hint">
        同一個數字可能同時符合好幾個礦床（不同顆數也可能湊出接近的值），最佳吻合（誤差最小）當主結果卡，其餘收進上面的完整診斷，實際礦物仍須以遊戲內判讀為準。
        少數 FPS 徒手採礦專用的礦床沒有船艦掃描訊號值，不會出現在這裡。
      </p>
    </div>

    <!-- ══ 礦物搜尋：輸入名稱 → 礦物資訊 ══ -->
    <div v-show="activeTab === 'search'" role="tabpanel">
      <div :class="[cardClass, 'mb-3']">
        <div class="card-body py-2">
          <div class="d-flex flex-wrap align-items-center gap-2">
            <input v-model="mineralQuery" type="search" class="form-control form-control-sm"
              style="max-width: 16rem" placeholder="搜尋礦物名稱（中文或英文皆可）...">
            <button v-if="mineralQuery" type="button" class="btn btn-sm btn-link" @click="mineralQuery = ''">
              清除
            </button>
          </div>
        </div>
      </div>

      <div v-if="loadingDeposits" class="text-center py-4 hint">
        <span class="spinner-border spinner-border-sm me-2"></span>載入中...
      </div>
      <div v-else-if="!mineralGroups.length" class="text-center py-4 hint">
        找不到符合「{{ mineralQuery }}」的礦物
      </div>
      <template v-else>
        <div v-for="g in mineralGroups" :key="g.resource_key" :class="[cardClass, 'mb-4']">
          <div class="card-body">
          <h6 class="fw-bold mb-1">
            {{ mineralLabel(g) }}
            <span class="small hint fw-normal">({{ g.resource_key }})</span>
          </h6>
          <p v-if="locationsFor(g).length" class="small hint mb-2">
            可能出現地點：
            <span v-for="loc in locationsFor(g)" :key="loc.system + '/' + loc.location_name"
              class="badge bg-info-subtle text-info-emphasis border me-1" :title="loc.system">
              {{ locationLabel(loc) }}
            </span>
          </p>
          <div style="overflow-x:auto">
            <table class="table table-sm table-hover align-middle mb-0">
              <thead class="table-light">
                <tr>
                  <th>所屬礦床</th>
                  <th>Tier</th>
                  <th>比例區間</th>
                  <th>機率</th>
                  <th>單顆訊號值</th>
                </tr>
              </thead>
              <tbody>
                <template v-for="dep in dedupedDeposits(g)" :key="dep._rowKey">
                  <tr :style="dep.signature ? 'cursor:pointer' : ''"
                    @click="dep.signature && toggleDepositExpand(dep._rowKey)">
                    <td>
                      <i v-if="dep.signature" class="bi me-1"
                        :class="expandedDeposits.has(dep._rowKey) ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      {{ depositLabel(dep) }}
                    </td>
                    <td>
                      <span v-if="dep.tier" class="badge bg-secondary-subtle text-secondary-emphasis">{{ dep.tier }}</span>
                      <span v-else class="hint">—</span>
                    </td>
                    <td>{{ fmtRange(dep.min_percentage, dep.max_percentage) }}</td>
                    <td>{{ fmtPct(dep.probability) }}</td>
                    <td>
                      <span v-if="dep.signature">{{ fmtInt(dep.signature) }}</span>
                      <span v-else class="hint" title="這個礦床沒有船艦掃描訊號值（可能是 FPS 徒手採礦專用）">—</span>
                    </td>
                  </tr>
                  <tr v-if="dep.signature && expandedDeposits.has(dep._rowKey)">
                    <td colspan="5" class="pb-3">
                      <div class="small hint mb-1">一叢礦石可能有 1～10 顆，掃描器讀到的整叢訊號值＝單顆 × 顆數：</div>
                      <div class="d-flex flex-wrap gap-2">
                        <span v-for="step in signatureSteps(dep.signature)" :key="step.n"
                          class="badge bg-light text-dark border">
                          {{ step.n }} 顆＝{{ fmtInt(step.value) }}
                        </span>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'

const props = defineProps({
  /** 帶身分的 fetch（後台用 apiFetch、玩家頁用 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /**
   * 卡片的 class。後台是淺色卡，玩家頁是 scifi 深色卡——跟
   * BlueprintCalculator.vue 同樣的理由：元件自己寫死的話某一邊的卡片
   * 顏色跟文字顏色會對不上，整段說明文字直接消失。
   */
  cardClass: { type: String, default: 'card shadow-sm border-0' },
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

const activeTab = ref('resonance')

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
  // Probability 是 0~1 的小數；MinPercentage/MaxPercentage 本來就是 0~100，用 fmtRange()。
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

// ── 回波比對：輸入船艦掃描訊號值 → 反查「單顆基準值 × 1~10 顆」───────
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

// 排序後的第一筆＝誤差最小的最佳吻合，回波比對分頁的主結果卡用這筆。
const bestMatch = computed(() => signatureMatches.value[0] || null)

function fmtConfidence(m) {
  // 訊號值比對是「單顆基準值 × 顆數」的確定性算式，不是機率——這裡的信心度
  // 只是把已經算出來、在 SIGNATURE_TOLERANCE 容許範圍內的誤差換算成好懂的
  // 百分比顯示，不是額外的統計模型。
  const pct = Math.max(0, Math.min(100, 100 - (m.diff / m.expected) * 100))
  return `${pct.toFixed(1)}%`
}

// 100.0%（完全吻合，誤差 < 0.5）不用另外顯示信心度卡——跟 fmtDiff()
// 判斷「完全吻合」用同一個門檻，主結果卡已經有「比對成功」徽章，
// 完全吻合時信心度必然是 100%，這格只是佔位、不提供額外資訊。
function isFullConfidence(m) {
  return m.diff < 0.5
}

function fmtDiff(m) {
  if (m.diff < 0.5) return '完全吻合'
  const pct = (m.diff / m.expected) * 100
  return `±${fmtInt(m.diff)}（${pct.toFixed(1)}%）`
}

// ── 礦物搜尋：輸入名稱（中/英皆可）→ 依礦物分組列出礦床明細 ─────────
const mineralQuery = ref('')

const mineralGroups = computed(() => {
  const raw = mineralQuery.value.trim()
  const q = raw.toLowerCase()

  // 不輸入就顯示全部（可瀏覽），輸入了才用子字串篩選——一律是「包含」不是
  // 「完全相等」，邊打邊即時篩選（Vue 的 computed 本來就會跟著 v-model 重算，
  // 不用另外做防抖或按鈕觸發）。
  const source = raw
    ? flatParts.value.filter(p =>
        (p.resource_name || '').toLowerCase().includes(q) ||
        (p.resource_name_zh || '').includes(raw) ||
        (p.resource_key || '').toLowerCase().includes(q))
    : flatParts.value

  const byKey = new Map()
  for (const p of source) {
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

// ── 礦物搜尋：同一種礦床常常在資料集裡有好幾筆幾乎一樣的紀錄（不同大小/
// 版本的礦床模板，但成分比例、機率、單顆訊號值完全相同）──直接照原始
// 筆數畫表格會出現一長串看起來一模一樣的「Asteroid (C-Type)」列。
// 這裡依「礦床名稱＋Tier＋比例區間＋機率＋單顆訊號值」去重，值真的不同
// 的變體（例如同名礦床但機率不同）還是會各自留一列，只是把完全重複的
// 紀錄合併掉。
//
// 注意：這裡只影響表格顯示，「可能出現地點」的 locationsFor() 還是吃
// 原始、沒去重的 group.deposits，不然去重會連帶漏掉某些變體才出現的地點。
function dedupedDeposits(group) {
  const seen = new Map()
  for (const dep of group.deposits) {
    const key = [
      group.resource_key, dep.deposit_name, dep.tier,
      dep.min_percentage, dep.max_percentage, dep.probability, dep.signature,
    ].join('|')
    if (!seen.has(key)) seen.set(key, { ...dep, _rowKey: key })
  }
  return Array.from(seen.values())
}

// 哪些礦床列被展開了（顯示 1~10 顆的整叢訊號值）。reactive(Set) 在 Vue 3
// 是響應式的，add/delete/has 都會正確觸發重新渲染。
const expandedDeposits = reactive(new Set())

function toggleDepositExpand(key) {
  if (expandedDeposits.has(key)) expandedDeposits.delete(key)
  else expandedDeposits.add(key)
}

/** 單顆基準值 × 1~10 顆，給「點開礦床列」用——邏輯跟回波比對分頁的
 *  1~10 顆迴圈是同一個算法，只是這裡是正向列出、不是反查。 */
function signatureSteps(signature) {
  return Array.from({ length: 10 }, (_, i) => ({ n: i + 1, value: signature * (i + 1) }))
}

function locationsFor(group) {
  const depositIds = new Set(group.deposits.map(d => d.deposit_id))
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
}
</script>

<style scoped>
/* 次要文字：用 opacity 而不是固定灰色，這樣在後台的淺色卡與玩家頁的
   深色 scifi 卡上都讀得到（Bootstrap 的 .text-muted 在深底上會消失，
   跟 BlueprintCalculator.vue 踩過的坑一樣）。 */
.hint {
  opacity: .72;
}
</style>
