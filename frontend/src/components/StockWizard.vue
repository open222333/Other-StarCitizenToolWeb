<!--
  玩家頁「倉庫 › 新增／異動」：跳出視窗，三步驟。
    1. 地點：星系／行星縮小範圍，選或輸入地點（預設上次送出用的地點，沒有就用定居點）
    2. 物品：搜尋卡跟倉庫同一個元件（InventoryFilterBar：名稱、類型、拆解材料）。物品類型預設只開六種飛船組件
       （量子引擎、護盾、雷達、艦炮、冷卻器、發電機），其他類型要自己勾（記在這台瀏覽器；全部取消＝回到預設），
       清單勾選（components/ItemBulkPicker.vue，換頁也記得、數量不限）；「最近登記」一鍵勾選；「貼上清單」一次比對多行
    3. 數量：已選的物品逐列設定 ＋增加／－減少、數量、備註，「全部送出」
  送出：後端沒有帶正負號的 API，逐列打 /player/inventory/add 或 /remove。成功的從清單拿掉，失敗的留著顯示原因；
  全部成功就回到第 2 步（同一個地點繼續登記），並通知上層重新載入（@done）。
  庫存列表的「異動」：openAdjust(那一列) 直接帶好地點與物品（預設減少），停在第 3 步。
-->
<template>
  <div v-if="open" class="sw-backdrop" @click.self="close">
    <div ref="dialogEl" class="sw-dialog scifi-card" role="dialog" aria-modal="true" aria-labelledby="sw-title" tabindex="-1">
      <div class="sw-head">
        <h3 id="sw-title" class="sw-title"><i class="bi bi-plus-slash-minus me-1"></i>新增／異動</h3>
        <ol class="sw-steps">
          <li v-for="st in STEPS" :key="st.n">
            <button type="button" class="sw-step" :class="{ 'is-active': step === st.n, 'is-done': step > st.n }"
              :disabled="!canGo(st.n)" :aria-current="step === st.n ? 'step' : null" @click="step = st.n">
              <span class="sw-step__no">{{ st.n }}</span>{{ st.label }}
              <span v-if="st.n === 1 && location.trim() && step !== 1" class="sw-step__val">{{ locLabel(location.trim()) }}</span>
              <span v-if="st.n === 2 && picked.length" class="sw-step__val">{{ picked.length }}</span>
            </button>
          </li>
        </ol>
        <button type="button" class="btn btn-sm btn-secondary ms-auto" aria-label="關閉" @click="close">
          <i class="bi bi-x-lg"></i></button>
      </div>

      <div class="sw-body">
        <Transition name="alert-slide">
          <div v-if="success" class="alert alert-success py-2">{{ success }}</div>
        </Transition>

        <!-- ── 1. 地點 ── -->
        <div v-show="step === 1">
          <div class="row g-2">
            <div class="col-6 col-md-3">
              <label class="form-label small fw-semibold mb-1" for="sw-system">星系</label>
              <select id="sw-system" v-model="area.system" class="form-select form-select-sm" @change="area.planet = ''">
                <option value="">全部</option>
                <option v-for="o in areaOpts.systems" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div class="col-6 col-md-3">
              <label class="form-label small fw-semibold mb-1" for="sw-planet">行星</label>
              <select id="sw-planet" v-model="area.planet" class="form-select form-select-sm">
                <option value="">全部</option>
                <option v-for="o in areaOpts.planets" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div class="col-12 col-md-6 position-relative">
              <label class="form-label small fw-semibold mb-1" for="sw-location">地點</label>
              <input id="sw-location" v-model="location" type="text" class="form-control form-control-sm"
                placeholder="輸入或選擇地點…" autocomplete="off" @input="filterLocations" @focus="filterLocations"
                @blur="closeLocations" @keydown.enter.prevent="location.trim() && (step = 2)">
              <ul v-if="locOpen" class="list-group position-absolute w-100 shadow-sm sw-dropdown">
                <li v-for="loc in locResults" :key="loc" class="list-group-item list-group-item-action py-1 px-2"
                  @mousedown.prevent="pickLocation(loc)">{{ locLabel(loc) }}</li>
                <li v-if="!locResults.length" class="list-group-item py-1 px-2 text-muted">沒有符合的地點</li>
              </ul>
            </div>
          </div>
          <div v-if="location.trim()" class="form-text text-success mt-2">
            <i class="bi bi-geo-alt"></i> {{ locLabel(location.trim()) }}</div>
        </div>

        <!-- ── 2. 物品 ── -->
        <div v-show="step === 2">
          <InventoryFilterBar :rows="[]" :show-locations="false" :type-options="allTypeOptions"
            v-model:q="query.q" v-model:types="enabledTypes" v-model:dismantle="query.dismantle"
            :dismantle-options="dismantleOptions" />
          <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
            <template v-if="recentItems.length">
              <span class="small fw-semibold">最近登記</span>
              <button v-for="it in recentItems" :key="it._id" type="button" class="btn btn-sm"
                :class="selectedIds.has(it._id) ? 'btn-secondary' : 'btn-success'" :aria-pressed="selectedIds.has(it._id) ? 'true' : 'false'"
                @click="toggle(it, !selectedIds.has(it._id))">
                <i class="bi me-1" :class="selectedIds.has(it._id) ? 'bi-check-lg' : 'bi-plus-lg'"></i>{{ it.name_zh || it.name }}</button>
            </template>
            <button type="button" class="btn btn-sm ms-auto" :class="pasteOpen ? 'btn-secondary' : 'btn-primary'"
              :aria-expanded="pasteOpen ? 'true' : 'false'" @click="pasteOpen = !pasteOpen">
              <i class="bi me-1" :class="pasteOpen ? 'bi-x-lg' : 'bi-clipboard-plus'"></i>{{ pasteOpen ? '收起貼上清單' : '貼上清單' }}</button>
          </div>

          <div v-if="pasteOpen" class="card scifi-card mb-3">
            <div class="card-body py-3">
              <label class="form-label small fw-semibold mb-1" for="sw-paste">貼上清單</label>
              <textarea id="sw-paste" v-model="pasteText" class="form-control form-control-sm" rows="6"
                :placeholder="'Atlas x2\nBulwark 3\n2 Hunter'"></textarea>
              <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
                <span v-if="pasteLines.length" class="sf-chip" :class="{ 'sf-chip--warn': pasteLines.length > PASTE_MAX }">
                  {{ pasteLines.length }} / {{ PASTE_MAX }} 行</span>
                <button type="button" class="btn btn-sm btn-warning ms-auto" :disabled="!pasteText"
                  @click="pasteText = ''; pasteRows = []"><i class="bi bi-eraser me-1"></i>清除</button>
                <button type="button" class="btn btn-sm btn-primary"
                  :disabled="pasteBusy || !pasteLines.length || pasteLines.length > PASTE_MAX" @click="parsePaste">
                  <span v-if="pasteBusy" class="spinner-border spinner-border-sm me-1"></span>
                  <i v-else class="bi bi-search me-1"></i>比對物品</button>
              </div>
              <div v-if="pasteError" class="text-danger mt-2">{{ pasteError }}</div>
              <div v-if="pasteRows.length" class="mt-3">
                <div v-for="(r, i) in pasteRows" :key="i" class="row g-2 align-items-center mb-2">
                  <div class="col-12 col-md-4 text-truncate sw-muted">{{ r.raw }}</div>
                  <div class="col-8 col-md-6">
                    <select v-model="r.pick" class="form-select form-select-sm" :class="{ 'is-invalid': !r.pick }"
                      :aria-label="`第 ${i + 1} 行的物品`">
                      <option value="">{{ r.candidates.length ? '選擇物品（不加入）' : '找不到物品（不加入）' }}</option>
                      <option v-for="c in r.candidates" :key="c._id" :value="c._id">
                        {{ c.name }}{{ c.name_zh ? `（${c.name_zh}）` : '' }}</option>
                    </select>
                  </div>
                  <div class="col-4 col-md-2">
                    <input v-model.number="r.qty" type="number" min="1" class="form-control form-control-sm"
                      :aria-label="`第 ${i + 1} 行的數量`">
                  </div>
                </div>
                <div class="d-flex flex-wrap align-items-center gap-2">
                  <span class="sf-chip">可加入 {{ pastePicked.length }} / {{ pasteRows.length }} 行</span>
                  <button type="button" class="btn btn-sm btn-success ms-auto" :disabled="!pastePicked.length"
                    @click="applyPaste"><i class="bi bi-plus-lg me-1"></i>加入已選</button>
                </div>
              </div>
            </div>
          </div>

          <ItemBulkPicker :fetcher="fetcher" :active="open && step === 2" :query="pickQuery" :selected-ids="selectedIds"
            @toggle="toggle" />
        </div>

        <!-- ── 3. 數量 ── -->
        <div v-show="step === 3">
          <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
            <span class="sf-chip sf-chip--accent"><i class="bi bi-geo-alt me-1"></i>{{ locLabel(location.trim()) }}</span>
            <span class="sf-chip">{{ picked.length }} 項</span>
            <div v-if="picked.length > 1" class="btn-group btn-group-sm ms-auto" role="group" aria-label="全部改成增加或減少">
              <button type="button" class="btn btn-subtab" @click="setAllDirection('in')">全部 ＋ 增加</button>
              <button type="button" class="btn btn-subtab" @click="setAllDirection('out')">全部 － 減少</button>
            </div>
          </div>
          <div v-for="(r, i) in picked" :key="r.key" class="sw-row" :class="{ 'is-out': r.direction === 'out' }">
            <div class="sw-row__name">
              <div class="fw-semibold text-truncate">{{ r.item.name_zh || r.item.name }}</div>
              <div v-if="r.item.name_zh" class="sw-muted text-truncate">{{ r.item.name }}</div>
            </div>
            <div class="btn-group btn-group-sm" role="group" :aria-label="`第 ${i + 1} 項增加或減少`">
              <button type="button" class="btn btn-subtab" :class="{ active: r.direction === 'in' }"
                @click="r.direction = 'in'">＋ 增加</button>
              <button type="button" class="btn btn-subtab" :class="{ active: r.direction === 'out' }"
                @click="r.direction = 'out'">－ 減少</button>
            </div>
            <div class="input-group input-group-sm sw-qty">
              <button type="button" class="btn btn-info" :aria-label="`第 ${i + 1} 項數量減一`"
                :disabled="(r.quantity || 0) <= 1" @click="r.quantity = Math.max(1, (Number(r.quantity) || 0) - 1)">
                <i class="bi bi-dash-lg"></i></button>
              <input v-model.number="r.quantity" type="number" min="1" class="form-control text-center"
                :aria-label="`第 ${i + 1} 項數量`">
              <button type="button" class="btn btn-info" :aria-label="`第 ${i + 1} 項數量加一`"
                @click="r.quantity = (Number(r.quantity) || 0) + 1"><i class="bi bi-plus-lg"></i></button>
            </div>
            <input v-model="r.note" type="text" class="form-control form-control-sm sw-note" placeholder="備註（選填）"
              :aria-label="`第 ${i + 1} 項備註`">
            <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除第 ${i + 1} 項`" :disabled="submitting"
              @click="picked.splice(i, 1)"><i class="bi bi-trash"></i></button>
            <div v-if="r.error" class="sw-row__error text-danger">{{ r.error }}</div>
          </div>
        </div>
      </div>

      <div class="sw-foot">
        <button v-if="step > 1" type="button" class="btn btn-sm btn-secondary" :disabled="submitting" @click="step--">
          <i class="bi bi-chevron-left me-1"></i>上一步</button>
        <span v-if="step === 2" class="sf-chip" :class="{ 'sf-chip--accent': picked.length }">已選 {{ picked.length }} 項</span>
        <button v-if="step === 2 && picked.length" type="button" class="btn btn-sm btn-warning" @click="picked.splice(0)">
          <i class="bi bi-eraser me-1"></i>清除已選</button>
        <button v-if="step < 3" type="button" class="btn btn-sm btn-primary ms-auto" :disabled="!canGo(step + 1)"
          @click="step++">下一步<i class="bi bi-chevron-right ms-1"></i></button>
        <button v-else type="button" class="btn btn-sm btn-primary ms-auto" :disabled="submitting || !picked.length"
          @click="submit">
          <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>全部送出</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import InventoryFilterBar from '@/components/InventoryFilterBar.vue'
import ItemBulkPicker from '@/components/ItemBulkPicker.vue'
import { useSheet } from '@/composables/useSheet'
import { itemTypeOption, loadItemTypeZh } from '@/utils/itemType'
import { areaOf, areaOptions } from '@/utils/locationArea'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 可選的地點名稱（地點資料庫可存放的地點＋已用過的地點） */
  locations: { type: Array, default: () => [] },
  locLabel: { type: Function, default: v => v },
  locZh: { type: Function, default: () => '' },
  homeLocation: { type: String, default: '' },
  /** 庫存紀錄（由新到舊），「最近登記」用 */
  history: { type: Array, default: () => [] },
  typeOptions: { type: Array, default: () => [] },
  dismantleOptions: { type: Array, default: () => [] },
})
const emit = defineEmits(['done'])

const STEPS = [{ n: 1, label: '地點' }, { n: 2, label: '物品' }, { n: 3, label: '數量' }]
const open = ref(false)
const step = ref(1)
const dialogEl = ref(null)
const { close } = useSheet(open, dialogEl)
const success = ref('')

// ── 1. 地點（上次送出的地點記在這台瀏覽器）──
const LOC_KEY = 'sc_stock_last_location_v1'
const location = ref('')
const area = reactive({ system: '', planet: '' })
const areaOpts = computed(() => areaOptions(props.locations,
  { systems: area.system ? [area.system] : [], planets: area.planet ? [area.planet] : [] },
  { locLabel: props.locLabel, sort: false }))
const locOpen = ref(false)
const locResults = ref([])
function filterLocations() {
  const q = location.value.trim()
  const pool = areaOpts.value.locations.map(o => o.value)
  locResults.value = (q ? pool.filter(l => l.toLowerCase().includes(q.toLowerCase()) || props.locZh(l).includes(q)) : pool)
    .slice(0, 20)
  locOpen.value = true
}
function closeLocations() {
  setTimeout(() => { locOpen.value = false }, 150)
}
function pickLocation(loc) {
  location.value = loc
  locOpen.value = false
  const a = areaOf(loc)
  area.system = a.system || ''
  area.planet = a.planet || ''
}
function readLastLocation() {
  try {
    return localStorage.getItem(LOC_KEY) || ''
  } catch {
    return ''
  }
}

// ── 2. 物品：類型預設只開這六種飛船組件，其他要自己勾（記在這台瀏覽器；全部取消＝回到預設）──
const DEFAULT_TYPES = ['QuantumDrive', 'Shield', 'Radar', 'WeaponGun', 'Cooler', 'PowerPlant']
const TYPES_KEY = 'sc_stock_types_v1'
function readTypes() {
  try {
    const v = JSON.parse(localStorage.getItem(TYPES_KEY) || 'null')
    const ok = Array.isArray(v) ? v.filter(t => typeof t === 'string' && t) : []
    return ok.length ? ok : [...DEFAULT_TYPES]
  } catch {
    return [...DEFAULT_TYPES]
  }
}
const enabledTypes = ref(readTypes())
watch(enabledTypes, (v) => {
  if (!v.length) {
    enabledTypes.value = [...DEFAULT_TYPES]
    return
  }
  try {
    localStorage.setItem(TYPES_KEY, JSON.stringify(v))
  } catch { /* 存不了就算了 */ }
})
const query = reactive({ q: '', dismantle: [] })
const pickQuery = computed(() => ({ ...query, types: enabledTypes.value }))

// 類型選單：玩家看得到的物品有出現的全部類型（GET /item/facets）
const allTypes = ref(null)
async function loadAllTypes() {
  const res = await props.fetcher('/item/facets')
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (!body?.success) return
  const types = body.data.types || []
  loadItemTypeZh(types)
  allTypes.value = types
}
const byLabel = (a, b) => a.label.localeCompare(b.label, 'zh-Hant')
const allTypeOptions = computed(() => (allTypes.value ? allTypes.value.map(itemTypeOption).sort(byLabel)
  : props.typeOptions))

let keySeq = 0
const picked = reactive([])
const selectedIds = computed(() => new Set(picked.map(r => r.item._id)))
function addPicked(item, quantity = 1, direction = 'in') {
  const hit = picked.find(r => r.item._id === item._id)
  if (hit) {
    hit.quantity = (Number(hit.quantity) || 0) + quantity
    return
  }
  picked.push({ key: ++keySeq, item, direction, quantity, note: '', error: '' })
}
function toggle(item, on) {
  if (on) addPicked(item)
  else {
    const i = picked.findIndex(r => r.item._id === item._id)
    if (i >= 0) picked.splice(i, 1)
  }
}

const RECENT_MAX = 8
const recentItems = computed(() => {
  const seen = new Set()
  const out = []
  for (const h of props.history) {
    if (!h.item_id || seen.has(h.item_id) || (h.item_type && !enabledTypes.value.includes(h.item_type))) continue
    seen.add(h.item_id)
    out.push({ _id: h.item_id, name: h.item_name, name_zh: h.item_name_zh })
    if (out.length >= RECENT_MAX) break
  }
  return out
})

// 貼上清單：每行「名稱 數量」（數量在前或後都可以，x2、×2、* 2 都行；沒寫＝1），後端一次比對名稱（照物品範圍）
const PASTE_MAX = 50
const pasteOpen = ref(false)
const pasteText = ref('')
const pasteRows = ref([])
const pasteBusy = ref(false)
const pasteError = ref('')
function parseLine(line) {
  let text = line.replace(/[０-９]/g, c => String.fromCharCode(c.charCodeAt(0) - 0xFEE0))
    .replace(/^\s*[-*•・]\s*/, '').trim()
  if (!text) return null
  let qty = 1
  let m = text.match(/^(.*?)\s*[x×*＊]\s*(\d+)$/i) || text.match(/^(.*\S)\s+(\d+)$/)
  if (m) {
    text = m[1]
    qty = Number(m[2])
  } else if ((m = text.match(/^(\d+)\s*[x×*＊]?\s+(.+)$/i))) {
    qty = Number(m[1])
    text = m[2]
  }
  text = text.trim()
  return text ? { raw: line.trim(), name: text, qty: Math.max(1, qty || 1) } : null
}
const pasteLines = computed(() => pasteText.value.split(/\r?\n/).map(parseLine).filter(Boolean))
const pastePicked = computed(() => pasteRows.value.filter(r => r.pick))
async function parsePaste() {
  const lines = pasteLines.value
  if (!lines.length || lines.length > PASTE_MAX) return
  pasteBusy.value = true
  pasteError.value = ''
  const res = await props.fetcher('/item/match', {
    method: 'POST', body: JSON.stringify({ names: lines.map(l => l.name), types: enabledTypes.value }),
  })
  const data = res ? await res.json().catch(() => null) : null
  pasteBusy.value = false
  if (!res?.ok || !data?.success) {
    pasteError.value = data?.message || '比對失敗。'
    return
  }
  pasteRows.value = lines.map((l, i) => {
    const m = data.data[i] || {}
    return { ...l, candidates: m.candidates || [], pick: m.item?._id || '' }
  })
}
function applyPaste() {
  for (const r of pastePicked.value) {
    const item = r.candidates.find(c => c._id === r.pick)
    if (item) addPicked(item, Math.max(1, Number(r.qty) || 1))
  }
  pasteRows.value = []
  pasteText.value = ''
  pasteOpen.value = false
}

// ── 3. 數量 ──
function setAllDirection(d) {
  for (const r of picked) r.direction = d
}

function canGo(n) {
  if (n <= 1) return true
  if (!location.value.trim()) return false
  return n === 2 || picked.length > 0
}

const submitting = ref(false)
async function submit() {
  const loc = location.value.trim()
  if (!loc || !picked.length) return
  let bad = false
  for (const r of picked) {
    r.error = ''
    if (!(Number(r.quantity) > 0)) {
      r.error = '數量必須大於 0'
      bad = true
    }
  }
  if (bad) return
  try {
    localStorage.setItem(LOC_KEY, loc)
  } catch { /* 存不了就算了 */ }
  submitting.value = true
  success.value = ''
  const batch = [...picked]
  const done = []
  for (const r of batch) {
    const res = await props.fetcher(r.direction === 'in' ? '/player/inventory/add' : '/player/inventory/remove', {
      method: 'POST',
      body: JSON.stringify({ item: r.item._id, quantity: Number(r.quantity), location: loc, note: (r.note || '').trim() }),
    })
    const data = res ? await res.json().catch(() => null) : null
    if (res?.ok && data?.success) done.push(r)
    else r.error = data?.message || (res ? `${r.direction === 'in' ? '增加' : '減少'}失敗` : '網路錯誤，請稍後再試')
  }
  submitting.value = false
  if (!done.length) return
  for (const r of done) {
    const i = picked.indexOf(r)
    if (i >= 0) picked.splice(i, 1)
  }
  success.value = `已處理 ${done.length} 項到 ${props.locLabel(loc)}`
    + (picked.length ? `；${picked.length} 項失敗，請看各項的原因` : '')
  if (!picked.length) step.value = 2
  emit('done')
}

// ── 開啟 ──
function reset() {
  success.value = ''
  if (!allTypes.value) loadAllTypes()
  pasteOpen.value = false
  pasteRows.value = []
  if (!location.value.trim()) {
    const loc = readLastLocation() || props.homeLocation
    if (loc) pickLocation(loc)
  }
}
/** 新增／異動：有地點就從第 2 步開始 */
function openNew() {
  reset()
  step.value = location.value.trim() ? 2 : 1
  open.value = true
}
/** 庫存列表某一列的「異動」：地點、物品帶好（預設減少），停在第 3 步 */
function openAdjust(row) {
  reset()
  pickLocation(row.location || '')
  picked.splice(0)
  picked.push({ key: ++keySeq, item: { _id: row.item_id, name: row.item_name, name_zh: row.item_name_zh },
    direction: 'out', quantity: 1, note: '', error: '' })
  step.value = 3
  open.value = true
}
watch(open, (v) => { if (!v) success.value = '' })

defineExpose({ openNew, openAdjust })
</script>

<style scoped>
.sw-backdrop {
  position: fixed; inset: 0; z-index: 1080;
  display: flex; align-items: flex-start; justify-content: center;
  padding: 2rem 1rem 1rem; background: rgba(2, 6, 15, .72);
}
.sw-dialog {
  width: 100%; max-width: 960px; max-height: calc(100dvh - 3rem); outline: none;
  display: flex; flex-direction: column;
}
.sw-head {
  display: flex; flex-wrap: wrap; align-items: center; gap: .5rem .75rem;
  padding: .75rem 1rem; border-bottom: 1px solid var(--sf-border);
}
.sw-title { font-size: 1.15rem; font-weight: 700; margin: 0; color: var(--sf-text-strong); }
.sw-steps { display: flex; flex-wrap: wrap; gap: .35rem; list-style: none; margin: 0; padding: 0; }
.sw-step {
  display: inline-flex; align-items: center; gap: .4rem; padding: .3rem .7rem; border-radius: 999px;
  border: 1px solid var(--sf-border-hi); background: var(--sf-chip-bg); color: var(--sf-text-muted); font-size: 1rem;
}
.sw-step:disabled { opacity: .5; }
.sw-step.is-active { color: var(--sf-accent-text, var(--sf-accent)); border-color: var(--sf-accent); }
.sw-step.is-done { color: var(--sf-text); }
.sw-step__no {
  display: inline-flex; align-items: center; justify-content: center; width: 1.4rem; height: 1.4rem; border-radius: 50%;
  background: rgba(var(--sf-accent-rgb), .18); font-weight: 700;
}
.sw-step__val { color: var(--sf-text-strong); font-weight: 600; max-width: 14rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sw-body { padding: 1rem; overflow-y: auto; flex: 1 1 auto; }
.sw-foot {
  display: flex; flex-wrap: wrap; align-items: center; gap: .5rem;
  padding: .75rem 1rem; border-top: 1px solid var(--sf-border);
}
.sw-dropdown { z-index: 30; max-height: 240px; overflow-y: auto; }
.sw-dropdown .list-group-item { cursor: pointer; }
.sw-muted { color: var(--sf-text-muted); }
.sw-row {
  display: grid; grid-template-columns: minmax(0, 1fr) auto 9.5rem minmax(8rem, 14rem) auto; gap: .5rem; align-items: center;
  padding: .5rem .75rem; margin-bottom: .5rem; border: 1px solid var(--sf-border); border-radius: .5rem;
}
.sw-row.is-out { border-left: 3px solid rgb(var(--bs-warning-rgb)); }
.sw-row__name { min-width: 0; }
.sw-row__error { grid-column: 1 / -1; }
.sw-qty .form-control { min-width: 3rem; }
@media (max-width: 767.98px) {
  .sw-backdrop { padding: 0; }
  .sw-dialog { max-width: none; max-height: 100dvh; height: 100dvh; border-radius: 0; }
  .sw-row { grid-template-columns: minmax(0, 1fr) auto; }
  .sw-row__name { grid-column: 1 / -1; }
  .sw-note { grid-column: 1 / -1; }
}
</style>
