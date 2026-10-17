<!--
  藍圖「品質試算」：每個部位（Frame／Barrel…）放的材料品質 0–1000 會影響成品屬性，
  拖拉每個部位的品質，即時看到各屬性的倍率與綜合加成。

  資料：GET /blueprint/master/<uuid>/quality（scunpacked-data，見 src/models/blueprint_quality.py）；
  計算：utils/craftQuality.js（純函式、有測試）。這裡只負責畫面。
  成品基礎數值：後端回傳 base_stats（物品主檔 raw 裡的數值，見 src/models/item_stats.py），
  屬性名稱對得上的會顯示「原始 → 加成後」（例如傷害減免 40% → 46%）；對不上的只顯示倍率。
-->
<template>
  <div class="bq">
    <div v-if="loading" class="bq-muted py-2">載入品質資料…</div>
    <div v-else-if="error" class="alert alert-warning py-2 mb-0">{{ error }}</div>
    <template v-else-if="data">
      <!-- ① 設定：製作數量（1～6，拉條＋輸入）、全部部位一起設定品質 -->
      <div class="bq-card bq-toolbar mb-3">
        <div class="bq-toolbar__item bq-toolbar__count">
          <label class="fw-semibold mb-0 text-nowrap" :for="`bq-${uid}-count`">製作數量</label>
          <input v-model.number="craftCount" type="range" class="bq-range bq-toolbar__range"
            min="1" :max="COUNT_MAX" step="1" aria-label="製作數量（拉條）">
          <input :id="`bq-${uid}-count`" :value="craftCount" type="number" class="form-control form-control-sm bq-qnum"
            min="1" :max="COUNT_MAX" step="1"
            @change="craftCount = clampCount($event.target.value); $event.target.value = craftCount">
          <span class="bq-muted">個</span>
        </div>
        <div class="bq-toolbar__item">
          <span class="fw-semibold text-nowrap">全部品質</span>
          <div class="btn-group btn-group-sm" role="group" aria-label="全部部位品質">
            <button v-for="p in PRESETS" :key="p.q" type="button" class="btn btn-subtab"
              :class="{ active: allAt(p.q) }" @click="setAll(p.q)">{{ p.label }}</button>
          </div>
        </div>
      </div>

      <!-- ② 需要的材料：每個的用量 × 製作數量 -->
      <h4 class="bq-title">需要的材料<span class="bq-muted fw-normal ms-2">製作 {{ craftCount }} 個</span></h4>
      <div class="row g-2 mb-3">
        <div v-for="m in materials" :key="m.key" class="col-12 col-md-6 col-xl-4">
          <div class="bq-card bq-mat h-100">
            <div class="d-flex justify-content-between align-items-baseline gap-2">
              <span class="fw-semibold">{{ m.label }}</span>
              <span class="bq-mat__total text-nowrap">{{ fmtQty(m.per * craftCount, m.unit) }}</span>
            </div>
            <div class="d-flex justify-content-between gap-2 bq-small">
              <span class="bq-muted">{{ m.slotName }}<template v-if="m.per !== null && craftCount > 1"> · 每個 {{ fmtQty(m.per, m.unit) }}</template></span>
              <span v-if="m.minQuality" class="bq-warn text-nowrap">最低 Q{{ m.minQuality }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="row g-3">
        <!-- ③ 各部位品質（左）→ ④ 成品屬性（右，寬螢幕時跟著捲動固定在畫面上） -->
        <div class="col-12 col-xl-7 order-1">
          <h4 class="bq-title">各部位品質</h4>
          <div v-for="slot in data.slots" :key="slot.key" class="bq-card mb-2">
            <div class="d-flex flex-wrap justify-content-between gap-2 mb-1">
              <span class="fw-bold">{{ slot.name_zh || slot.name }}<span v-if="slot.name_zh" class="bq-muted ms-1">{{ slot.name }}</span></span>
              <span class="text-nowrap">
                <span class="bq-accent">{{ optionLabel(slot.options[0]) }}</span>
                <span v-if="slot.options[0]" class="ms-1">{{ fmtQty(requiredQty(slot), unitOf(slot)) }}</span>
                <span v-if="slot.options.length > 1" class="bq-muted ms-1">（{{ slot.options.length }} 選 {{ slot.required_count }}）</span>
              </span>
            </div>
            <!-- 有設多批材料時，品質＝各批的加權平均（品質 × 數量 加總 ÷ 數量加總），單一品質的拉條改成唯讀 -->
            <div class="d-flex align-items-center gap-2">
              <label class="bq-muted mb-0 text-nowrap" :for="`bq-${uid}-${slot.key}`">{{ hasBatches(slot) ? '平均品質' : '品質' }}</label>
              <input :id="`bq-${uid}-${slot.key}`" v-model.number="qualities[slot.key]" type="range"
                class="flex-grow-1 bq-range" :min="QUALITY_MIN" :max="QUALITY_MAX" step="1" :disabled="hasBatches(slot)"
                :style="{ '--bq-fill': `${(qualities[slot.key] / QUALITY_MAX) * 100}%` }">
              <!-- 輸入值限制在 Q0～Q1000（整數），超出就夾回端點 -->
              <input :value="hasBatches(slot) ? Number(qualities[slot.key].toFixed(1)) : qualities[slot.key]" type="number"
                class="form-control form-control-sm bq-qnum" :disabled="hasBatches(slot)"
                :min="QUALITY_MIN" :max="QUALITY_MAX" step="1" :aria-label="`${slot.name} 品質`"
                @change="qualities[slot.key] = clampQuality($event.target.value); $event.target.value = qualities[slot.key]">
            </div>
            <!-- MIN＝這個材料能用的最低品質、MID＝Q500、MAX＝Q1000；多批材料時改用下面每一批的品質 -->
            <div class="d-flex flex-wrap align-items-center gap-2 mt-1">
              <div v-if="!hasBatches(slot)" class="btn-group btn-group-sm bq-presets" role="group" :aria-label="`${slot.name} 品質快速設定`">
                <button type="button" class="btn btn-info" @click="qualities[slot.key] = Math.max(QUALITY_MIN, minQualityOf(slot))">MIN</button>
                <button type="button" class="btn btn-info" @click="qualities[slot.key] = Math.round((QUALITY_MIN + QUALITY_MAX) / 2)">MID</button>
                <button type="button" class="btn btn-info" @click="qualities[slot.key] = QUALITY_MAX">MAX</button>
              </div>
              <button type="button" class="btn btn-sm btn-success" @click="addBatch(slot)">
                <i class="bi bi-plus-lg me-1"></i>{{ hasBatches(slot) ? '再加一批' : '多批材料' }}
              </button>
            </div>
            <!-- 多批材料：每一批各自的品質與數量 -->
            <div v-if="hasBatches(slot)" class="bq-batches mt-2">
              <!-- 總量固定：拉某一批的數量時，其他沒鎖定的批平均增減，讓總數量維持等於需要量 -->
              <div v-if="requiredQty(slot) !== null" class="form-check mb-2">
                <input :id="`bq-${uid}-${slot.key}-fixed`" class="form-check-input" type="checkbox"
                  :checked="fixedOn(slot)" @change="setFixed(slot, $event.target.checked)">
                <label class="form-check-label" :for="`bq-${uid}-${slot.key}-fixed`">總數量固定為需要量（其他批自動平均調整，鎖定的不動）</label>
              </div>
              <!-- 每一批：品質、數量都可以拉條或輸入數字，平均品質即時重算（不會自動調整其他批的數量） -->
              <div v-for="(b, i) in batches[slot.key]" :key="b.id" class="bq-batch">
                <div class="d-flex align-items-center gap-2 mb-1">
                  <span class="fw-semibold text-nowrap">第 {{ i + 1 }} 批</span>
                  <span v-if="b.quality < minQualityOf(slot)" class="bq-warn">低於最低品質 Q{{ minQualityOf(slot) }}</span>
                  <button v-if="fixedOn(slot)" type="button" class="btn btn-sm btn-info ms-auto" :aria-pressed="b.locked ? 'true' : 'false'"
                    :aria-label="b.locked ? `解除鎖定第 ${i + 1} 批數量` : `鎖定第 ${i + 1} 批數量`" @click="b.locked = !b.locked">
                    <i class="bi me-1" :class="b.locked ? 'bi-lock-fill' : 'bi-unlock'"></i>{{ b.locked ? '已鎖定' : '鎖定' }}
                  </button>
                  <button type="button" class="btn btn-sm btn-danger" :class="{ 'ms-auto': !fixedOn(slot) }" :aria-label="`刪除第 ${i + 1} 批`"
                    @click="removeBatch(slot, i)"><i class="bi bi-trash"></i></button>
                </div>
                <div class="bq-batch__line">
                  <label class="bq-muted mb-0 bq-batch__label" :for="`bq-${uid}-${slot.key}-q${b.id}`">品質</label>
                  <input v-model.number="b.quality" type="range" class="flex-grow-1 bq-range" :min="QUALITY_MIN" :max="QUALITY_MAX" step="1"
                    :style="{ '--bq-fill': `${(b.quality / QUALITY_MAX) * 100}%` }" :aria-label="`第 ${i + 1} 批品質（拉條）`">
                  <input :id="`bq-${uid}-${slot.key}-q${b.id}`" v-model.number="b.quality" type="number" class="form-control form-control-sm bq-qnum"
                    :min="QUALITY_MIN" :max="QUALITY_MAX" step="1"
                    @change="b.quality = clampQuality($event.target.value); $event.target.value = b.quality">
                </div>
                <div class="bq-batch__line">
                  <label class="bq-muted mb-0 bq-batch__label" :for="`bq-${uid}-${slot.key}-n${b.id}`">數量</label>
                  <input :value="b.qty" type="range" class="flex-grow-1 bq-range" min="0" :max="qtySliderMax(slot)" :step="qtyStep(slot)"
                    :disabled="fixedOn(slot) && b.locked"
                    :style="{ '--bq-fill': `${Math.min(1, (Number(b.qty) || 0) / qtySliderMax(slot)) * 100}%` }" :aria-label="`第 ${i + 1} 批數量（拉條）`"
                    @input="b.qty = clampQty($event.target.value); rebalance(slot, b.id)">
                  <input :id="`bq-${uid}-${slot.key}-n${b.id}`" v-model.number="b.qty" type="number" class="form-control form-control-sm bq-qnum"
                    min="0" step="any" :disabled="fixedOn(slot) && b.locked"
                    @change="b.qty = clampQty($event.target.value); rebalance(slot, b.id); $event.target.value = b.qty">
                  <span v-if="unitOf(slot)" class="bq-muted bq-batch__unit">{{ unitOf(slot) }}</span>
                </div>
              </div>
              <div class="bq-small">
                平均品質 <span class="fw-bold bq-accent">Q{{ Number(qualities[slot.key].toFixed(1)) }}</span>
                <span class="bq-muted">（已設定 {{ fmtQty(batchTotal(slot), unitOf(slot)) }}<template v-if="requiredQty(slot) !== null"> ／ 需要 {{ fmtQty(requiredQty(slot), unitOf(slot)) }}</template>）</span>
                <span v-if="requiredQty(slot) !== null && batchTotal(slot) + 1e-9 < requiredQty(slot)" class="bq-warn ms-1">還差 {{ fmtQty(requiredQty(slot) - batchTotal(slot), unitOf(slot)) }}</span>
                <span v-else-if="requiredQty(slot) !== null && batchTotal(slot) > requiredQty(slot) + 1e-9" class="bq-warn ms-1">多了 {{ fmtQty(batchTotal(slot) - requiredQty(slot), unitOf(slot)) }}</span>
              </div>
            </div>
            <div v-if="qualities[slot.key] < minQualityOf(slot)" class="bq-warn">
              低於最低品質 Q{{ minQualityOf(slot) }}，這個材料不能用
            </div>
            <!-- 這個部位目前品質下，各屬性的加成（直接列「屬性 加成」，不再列 Q0／Q500／Q1000 對照表） -->
            <div v-if="slot.modifiers.length" class="bq-mods mt-1">
              <div v-for="m in slot.modifiers" :key="m.key || m.name" class="bq-mod">
                <span>{{ m.name_zh || m.name }}</span>
                <!-- 只顯示目前品質下的值（例如「完整性 1.00」），跟著上面的品質即時變動 -->
                <span class="fw-bold" :class="betterClass(m, modifierAt(m, qualities[slot.key]))">
                  {{ fmtSlotValue(m, modifierAt(m, qualities[slot.key])) }}
                </span>
              </div>
            </div>
            <div v-else class="bq-muted">這個部位的品質不影響屬性</div>
          </div>
        </div>
        <!-- 綜合加成 -->
        <div class="col-12 col-xl-5 order-2">
          <div class="bq-sticky">
          <h4 class="bq-title">綜合加成</h4>
          <div class="row g-2">
            <div v-for="r in combined" :key="r.key" class="col-6">
              <div class="bq-card h-100">
                <div class="bq-muted">{{ r.name_zh || r.name }}</div>
                <div class="bq-value" :class="r.better === true ? 'bq-good' : r.better === false ? 'bq-bad' : ''">
                  {{ fmtModifier(r.value, r.additive) }}
                  <span v-if="!r.additive" class="bq-pct">{{ fmtPercent(r.value) }}</span>
                </div>
                <!-- 原始數值 → 加成後（物品資料裡有這個屬性的才顯示） -->
                <div v-if="baseOf(r)" class="bq-stat">
                  <span class="bq-muted">{{ fmtStat(baseOf(r).value, baseOf(r).unit) }}</span>
                  <i class="bi bi-arrow-right mx-1 bq-muted"></i>
                  <span class="fw-bold" :class="r.better === true ? 'bq-good' : r.better === false ? 'bq-bad' : ''">
                    {{ fmtStat(applyToBase(baseOf(r).value, r.value, r.additive), baseOf(r).unit) }}
                  </span>
                </div>
                <div v-if="r.name_zh" class="bq-muted bq-small">{{ r.name }}</div>
                <!-- 反推：拉條（範圍＝Q0 到 Q1000 做得到的值）或輸入想要的數值（有原始數值時用實際單位，
                     沒有就用倍率），即時算出要多少品質 -->
                <div v-if="rangeOf(r)" class="mt-2">
                  <div class="bq-target">
                    <span class="bq-muted text-nowrap">目標</span>
                    <!-- 輸入值限制在拉條範圍內（Q0～Q1000 做得到的值），超出就夾回最近的端點 -->
                    <input :value="targetValue(r)" type="number" step="any" class="form-control form-control-sm bq-tnum"
                      :min="rangeOf(r).lo" :max="rangeOf(r).hi"
                      :placeholder="targetPlaceholder(r)" :aria-label="`${r.name_zh || r.name} 的目標數值（輸入）`"
                      @change="setTarget(r, clampTarget(r, $event.target.value), true); $event.target.value = targetValue(r)">
                    <span v-if="usesBase(r)" class="bq-muted">{{ baseOf(r).unit }}</span>
                  </div>
                  <div class="btn-group btn-group-sm mt-2 bq-presets" role="group" :aria-label="`${r.name_zh || r.name} 快速設定`">
                    <button type="button" class="btn btn-info" @click="setTarget(r, rangeOf(r).worst)">MIN</button>
                    <button type="button" class="btn btn-info" @click="setTarget(r, (rangeOf(r).lo + rangeOf(r).hi) / 2)">MID</button>
                    <button type="button" class="btn btn-info" @click="setTarget(r, rangeOf(r).best)">MAX</button>
                  </div>
                  <!-- 拉條一律「左＝Q0、右＝Q1000」：最低耐溫、後座力這種數值變小才是變好的屬性，
                       往右拉也是變好，跟其他屬性同方向（拉條本身是 0～1000 的位置，再換算成數值） -->
                  <input :value="rangeOf(r).pos(targetValue(r))" type="range" class="w-100 bq-range mt-2"
                    min="0" max="1000" step="1"
                    :style="{ '--bq-fill': `${rangeOf(r).pos(targetValue(r)) / 10}%` }"
                    :aria-label="`${r.name_zh || r.name} 的目標數值`" @input="setTarget(r, rangeOf(r).val($event.target.value), true)">
                  <div class="d-flex justify-content-between bq-muted bq-small">
                    <span>{{ fmtTargetEnd(r, rangeOf(r).worst) }}</span><span>{{ fmtTargetEnd(r, rangeOf(r).best) }}</span>
                  </div>
                </div>
                <div v-if="targetResults[r.key]" class="bq-small mt-1">
                  <template v-if="targetResults[r.key].reachable">
                    需要品質 <span class="fw-bold bq-accent">Q{{ targetResults[r.key].quality }}</span>
                    <span class="bq-muted">（{{ targetResults[r.key].slotNames }}）</span>
                  </template>
                  <span v-else class="bq-warn">Q1000 也到不了，最多 {{ targetResults[r.key].bestLabel }}</span>
                </div>
              </div>
            </div>
            <div v-if="!combined.length" class="col-12 bq-muted">這張藍圖的材料品質不影響任何屬性。</div>
          </div>
        </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'
import {
  QUALITY_MAX, QUALITY_MIN, applyToBase, combine, fmtModifier, fmtPercent, fmtStat, improves, isAdditive,
  modifierAt, requiredQuality, statKey,
} from '@/utils/craftQuality'
import { loadTranslations, translate } from '@/utils/translations'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 藍圖主檔 uuid */
  blueprintUuid: { type: String, required: true },
})

const PRESETS = [{ q: 0, label: 'Q0 最低' }, { q: 500, label: 'Q500 中間' }, { q: 1000, label: 'Q1000 最高' }]
const uid = Math.random().toString(36).slice(2, 8)

const data = ref(null)
const loading = ref(false)
const error = ref('')
const qualities = reactive({})

async function load(id) {
  loading.value = true
  error.value = ''
  data.value = null
  try {
    const res = await props.fetcher(`/blueprint/master/${encodeURIComponent(id)}/quality`)
    const body = res ? await res.json().catch(() => null) : null
    if (!res?.ok || !body?.success) {
      error.value = body?.message || '讀取品質資料失敗，請稍後再試'
      return
    }
    for (const k of Object.keys(qualities)) delete qualities[k]
    for (const k of Object.keys(batches)) delete batches[k]
    for (const k of Object.keys(fixedTotals)) delete fixedTotals[k]
    for (const k of Object.keys(targets)) delete targets[k]
    for (const k of Object.keys(targetResults)) delete targetResults[k]
    for (const slot of body.data.slots || []) qualities[slot.key] = 500
    data.value = body.data
    // 材料名稱的中文（後端沒查到的再用前端翻譯快取補）
    const names = (body.data.slots || []).flatMap(s => (s.options || []).map(o => o.name)).filter(Boolean)
    loadTranslations('mining_resource', names)
    loadTranslations('item', names)
  } finally {
    loading.value = false
  }
}

watch(() => props.blueprintUuid, (id) => { if (id) load(id) }, { immediate: true })

const combined = computed(() => (data.value ? combine(data.value.slots, qualities) : []))

/** 這個屬性的成品基礎數值（base_stats 用正規化的英文名稱查） */
const baseOf = r => data.value?.base_stats?.[statKey(r.name)] || null

// ── 反推品質：輸入目標數值 → 影響這個屬性的部位最少要多少品質 ──────────────
const targets = reactive({})
const targetResults = reactive({})

/** 有原始數值（而且不是 0）就用實際數值輸入，否則輸入倍率／加減值 */
const usesBase = r => !!baseOf(r) && (r.additive || baseOf(r).value !== 0)

function targetPlaceholder(r) {
  if (usesBase(r)) return `目標數值${baseOf(r).unit ? `（${baseOf(r).unit}）` : ''}`
  return r.additive ? '目標加減值' : '目標倍率，例如 1.1'
}

/** 拉條範圍：Q0 到 Q1000 這個屬性做得到的值（其他部位維持目前品質），用畫面上的單位。
 *  worst＝Q0 的值（拉條左端、MIN）、best＝Q1000 的值（右端、MAX）；lo／hi 是數值上的大小（夾輸入範圍用）。
 *  pos(v)／val(p)：數值 ↔ 拉條位置 0～1000，數值變小才是變好的屬性也是往右變好。 */
function rangeOf(r) {
  const res = requiredQuality(data.value?.slots, qualities, r.key, 1)
  if (!res) return null
  const base = usesBase(r) ? baseOf(r) : null
  const show = v => (base ? applyToBase(base.value, v, r.additive) : v)
  const a = show(res.worst)
  const b = show(res.best)
  const lo = Math.min(a, b)
  const hi = Math.max(a, b)
  if (!(hi > lo)) return null
  const step = r.additive && !base ? 1 : Number(((hi - lo) / 1000).toPrecision(2))
  const pos = v => Math.round(Math.min(1000, Math.max(0, ((Number(v) - a) / (b - a)) * 1000)))
  const val = p => a + (Number(p) / 1000) * (b - a)
  return { lo, hi, worst: a, best: b, step, pos, val }
}

/** 目前的目標值：沒設過就用現在的數值 */
function targetValue(r) {
  if (targets[r.key] !== undefined && targets[r.key] !== '') {
    // MIN／MID／MAX 存的是不捨入的實際值（反推才準），顯示時才捨入
    const v = Number(targets[r.key])
    return Number.isNaN(v) ? targets[r.key] : Number(v.toFixed(usesBase(r) ? 2 : 3))
  }
  const base = usesBase(r) ? baseOf(r) : null
  const v = base ? applyToBase(base.value, r.value, r.additive) : r.value
  return Number(v.toFixed(3))
}

/** fromSlider：拉條的值四捨五入到 2 位小數（倍率 3 位），避免出現 -79.996 這種數字 */
function setTarget(r, value, fromSlider = false) {
  const digits = usesBase(r) ? 2 : 3
  targets[r.key] = fromSlider ? String(Number(Number(value).toFixed(digits))) : value
  calcTarget(r)
}

/** 各部位的屬性值：倍率直接顯示數字（1.00），加減值帶正負號（+1／-1） */
function fmtSlotValue(m, v) {
  if (v === null || v === undefined) return '—'
  return isAdditive(m) ? fmtModifier(v, true) : Number(v).toFixed(2)
}

/** 目標輸入值夾在拉條範圍內；不是數字就維持原輸入（讓 calcTarget 忽略） */
function clampTarget(r, value) {
  const range = rangeOf(r)
  const v = Number(value)
  if (value === '' || Number.isNaN(v) || !range) return value
  return Math.min(range.hi, Math.max(range.lo, v))
}

// ── 多批材料：同一個部位用好幾批不同品質的材料，品質取加權平均 ───────────────
//    平均品質 = (品質1 × 數量1 + … + 品質N × 數量N) ÷ (數量1 + … + 數量N)
const batches = reactive({})
let batchSeq = 0
const hasBatches = slot => (batches[slot.key] || []).length > 0
/** 這個部位需要的材料總量（第一個選項的用量 × 製作數量） */
function requiredQty(slot) {
  const { per } = perUnit(slot.options?.[0])
  return per === null ? null : per * craftCount.value
}
/** 新增一批時的預設數量：還沒分配到的量（都分配完了就用總量） */
function defaultQty(slot) {
  const need = requiredQty(slot)
  if (need === null) return 1
  const left = need - batchTotal(slot)
  return Number((left > 0 ? left : need).toFixed(3))
}
function unitOf(slot) {
  const o = slot.options?.[0]
  if (o?.quantity_scu !== null && o?.quantity_scu !== undefined) return 'SCU'
  if (o?.quantity !== null && o?.quantity !== undefined) return '個'
  return ''
}
function addBatch(slot) {
  const list = batches[slot.key] || (batches[slot.key] = [])
  // 第一批沿用目前的品質，之後新增的也先沿用目前（平均）品質，再自己改；
  // 總量固定時，新的一批先拿還沒分配到的量（可能是 0，之後拉它時其他批會自動讓出）
  const need = requiredQty(slot)
  const qty = fixedOn(slot) && need !== null ? roundQty(slot, Math.max(0, need - batchTotal(slot))) : defaultQty(slot)
  list.push({ id: ++batchSeq, quality: Math.round(qualities[slot.key] ?? 500), qty, locked: false })
}
function removeBatch(slot, i) {
  batches[slot.key].splice(i, 1)
  if (!batches[slot.key].length) delete batches[slot.key]
  else rebalance(slot, null)   // 刪掉的量平均分給沒鎖定的批
}

// ── 總量固定：每個部位各自設定（預設開），拉一批時其他沒鎖定的批平均增減 ──
const fixedTotals = reactive({})
const fixedOn = slot => requiredQty(slot) !== null && fixedTotals[slot.key] !== false
function setFixed(slot, on) {
  fixedTotals[slot.key] = on
  if (on) rebalance(slot, null)
}
function roundQty(slot, v) {
  return unitOf(slot) === 'SCU' ? Math.round(v * 1000) / 1000 : Math.round(v)
}
/**
 * 讓這個部位的總數量等於需要量。changedId＝剛被拉動的那一批（它的值優先保留，只夾在可用範圍內）；
 * 差額由「沒鎖定、也不是剛拉的」那幾批平均分攤，扣到 0 的就停在 0、其餘的繼續分攤。
 * 沒有可以調整的批時，剛拉的那一批就固定成剩下的量。
 */
function rebalance(slot, changedId) {
  if (!fixedOn(slot)) return
  const need = requiredQty(slot)
  const list = batches[slot.key]
  if (need === null || !list?.length) return
  const changed = list.find(b => b.id === changedId) || null
  const locked = list.filter(b => b.locked && b !== changed)
  const free = list.filter(b => !b.locked && b !== changed)
  const lockedSum = locked.reduce((n, b) => n + (Number(b.qty) || 0), 0)
  const room = Math.max(0, need - lockedSum)
  if (changed) changed.qty = roundQty(slot, free.length ? Math.min(room, Math.max(0, Number(changed.qty) || 0)) : room)
  const target = Math.max(0, room - (changed ? changed.qty : 0))
  if (!free.length) return
  // 平均分攤差額；減少時扣到 0 的批先退出，剩下的批再平均分攤
  let pool = free.slice()
  let goal = target
  for (let guard = 0; guard < 50 && pool.length; guard++) {
    const current = pool.reduce((n, b) => n + (Number(b.qty) || 0), 0)
    const share = (goal - current) / pool.length
    const floored = pool.filter(b => (Number(b.qty) || 0) + share < 0)
    if (!floored.length) { pool.forEach(b => { b.qty = (Number(b.qty) || 0) + share }); break }
    floored.forEach(b => { b.qty = 0 })
    pool = pool.filter(b => !floored.includes(b))
  }
  // 捨入到 0.001 SCU（或整數個），誤差補到最多的那一批，總和才會剛好等於需要量
  free.forEach(b => { b.qty = roundQty(slot, b.qty) })
  const diff = roundQty(slot, target - free.reduce((n, b) => n + b.qty, 0))
  if (diff) {
    const biggest = free.reduce((a, b) => (b.qty > a.qty ? b : a))
    biggest.qty = roundQty(slot, Math.max(0, biggest.qty + diff))
  }
}
// 製作數量一改，需要量跟著變：總量固定的部位重新分攤
function batchTotal(slot) {
  return (batches[slot.key] || []).reduce((n, b) => n + (Number(b.qty) || 0), 0)
}
/** 數量拉條的上限＝這個部位需要的總量（沒有用量資料時 10）；SCU 用 0.001 的刻度、個數用 1 */
function qtySliderMax(slot) {
  const need = requiredQty(slot)
  return need && need > 0 ? need : 10
}
function qtyStep(slot) {
  return unitOf(slot) === 'SCU' ? 0.001 : 1
}
function clampQty(value) {
  const v = Number(value)
  return Number.isNaN(v) || v < 0 ? 0 : v
}
// 各批品質／數量一改，部位品質就換成加權平均（總數量是 0 時用各批品質的簡單平均）
watch(batches, () => {
  for (const [key, list] of Object.entries(batches)) {
    if (!list.length) continue
    const total = list.reduce((n, b) => n + (Number(b.qty) || 0), 0)
    qualities[key] = total > 0
      ? list.reduce((n, b) => n + (Number(b.quality) || 0) * (Number(b.qty) || 0), 0) / total
      : list.reduce((n, b) => n + (Number(b.quality) || 0), 0) / list.length
  }
}, { deep: true })

/** 部位品質夾在 Q0～Q1000 的整數；輸入不是數字就回到 Q0 */
function clampQuality(value) {
  const v = Math.round(Number(value))
  if (Number.isNaN(v)) return QUALITY_MIN
  return Math.min(QUALITY_MAX, Math.max(QUALITY_MIN, v))
}

function fmtTargetEnd(r, v) {
  return usesBase(r) ? fmtStat(v, baseOf(r).unit) : fmtModifier(v, r.additive)
}

function calcTarget(r) {
  let t = Number(targets[r.key])
  if (targets[r.key] === '' || Number.isNaN(t)) return
  // 目標值會四捨五入到 2～3 位小數（例如 Q1000 是 ×1.10289，顯示成 ×1.103），
  // 直接拿去反推會比 Q1000 還高一點點、被判成「Q1000 也到不了」。
  // 輸入本來就限制在拉條範圍內，超出的部分只會是捨入誤差，所以夾回 Q0～Q1000 的實際端點再算。
  const range = rangeOf(r)
  if (range) t = Math.min(range.hi, Math.max(range.lo, t))
  const base = usesBase(r) ? baseOf(r) : null
  const goal = base ? (r.additive ? t - base.value : t / base.value) : t
  const res = requiredQuality(data.value.slots, qualities, r.key, goal)
  if (!res) { delete targetResults[r.key]; return }
  const names = (data.value.slots || []).filter(s => res.slotKeys.includes(s.key)).map(s => s.name_zh || s.name)
  targetResults[r.key] = {
    ...res,
    slotNames: names.join('、'),
    bestLabel: base ? fmtStat(applyToBase(base.value, res.best, r.additive), base.unit)
      : `${fmtModifier(res.best, r.additive)}`,
  }
}

function setAll(q) {
  // 全部品質一鍵設定時，多批材料的設定一起清掉（不然平均品質會跟一鍵設定的值打架）
  for (const k of Object.keys(batches)) delete batches[k]
  for (const k of Object.keys(fixedTotals)) delete fixedTotals[k]
  for (const k of Object.keys(qualities)) qualities[k] = q
}
const allAt = q => Object.keys(qualities).length > 0 && Object.values(qualities).every(v => v === q)

function minQualityOf(slot) {
  return Math.min(...(slot.options || []).map(o => o.min_quality || 0), Infinity) === Infinity
    ? 0 : Math.min(...slot.options.map(o => o.min_quality || 0))
}

function optionLabel(o) {
  if (!o) return '—'
  const zh = o.name_zh || translate(o.kind === 'resource' ? 'mining_resource' : 'item', o.name) || ''
  return zh ? `${zh}（${o.name}）` : o.name
}

// ── 製作數量：材料用量 × 數量（數字輸入，1～999）──
const COUNT_MAX = 6
const craftCount = ref(1)
function clampCount(value) {
  const v = Math.round(Number(value))
  if (Number.isNaN(v) || v < 1) return 1
  return Math.min(COUNT_MAX, v)
}
watch(craftCount, v => { const c = clampCount(v); if (c !== v) craftCount.value = c })
watch(craftCount, () => { for (const slot of data.value?.slots || []) rebalance(slot, null) })

/** 每個材料的單位用量（SCU 或個）與單位 */
function perUnit(o) {
  if (o?.quantity_scu !== null && o?.quantity_scu !== undefined) return { per: Number(o.quantity_scu), unit: 'SCU' }
  if (o?.quantity !== null && o?.quantity !== undefined) return { per: Number(o.quantity), unit: '個' }
  return { per: null, unit: '' }
}
function fmtQty(v, unit) {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  const n = unit === 'SCU' ? Number(v.toFixed(3)) : Math.round(v)
  return `${n.toLocaleString('en-US')}${unit ? ` ${unit}` : ''}`
}

const materials = computed(() => (data.value?.slots || []).flatMap(slot => (slot.options || []).map((o, i) => ({
  key: `${slot.key}|${i}`, label: optionLabel(o), minQuality: o.min_quality || 0,
  slotName: slot.name_zh || slot.name, ...perUnit(o),
}))))

function betterClass(m, value) {
  const b = improves(m, value)
  return b === true ? 'bq-good' : b === false ? 'bq-bad' : ''
}

</script>

<style scoped>
.bq-title {
  font-size: .95rem; font-weight: 700; letter-spacing: .12em;
  color: var(--sf-accent-text, var(--sf-accent)); margin: 0 0 .5rem;
}
.bq-card {
  background: var(--sf-panel-2); border: 1px solid var(--sf-border); border-radius: 8px;
  padding: .65rem .8rem; color: var(--sf-text);
}
.bq-muted { color: var(--sf-text-muted); }
.bq-small { font-size: .9rem; }
.bq-accent { color: var(--sf-accent-text, var(--sf-accent)); }
.bq-warn { color: var(--sf-accent-2); font-weight: 600; font-size: .95rem; }
.bq-value { font-size: 1.4rem; font-weight: 700; color: var(--sf-text-strong); }
.bq-pct { font-size: .95rem; margin-left: .35rem; }
.bq-stat { font-size: 1.05rem; margin-top: .15rem; }
.bq-target { display: flex; align-items: center; gap: .5rem; }
.bq-tnum { width: 7rem; flex: 0 0 auto; }
.bq-good { color: rgb(var(--bs-success-rgb)); }
.bq-bad { color: rgb(var(--bs-danger-rgb)); }
.bq-range {
  /* 自己畫軌道：Bootstrap 的 form-range 在深色主題上軌道幾乎看不到 */
  -webkit-appearance: none; appearance: none; min-width: 6rem;
  height: .45rem; border-radius: 999px; cursor: pointer;
  background: linear-gradient(to right, var(--sf-accent) var(--bq-fill, 50%), var(--sf-border) var(--bq-fill, 50%));
}
.bq-range::-webkit-slider-thumb {
  -webkit-appearance: none; width: 1.1rem; height: 1.1rem; border-radius: 50%;
  background: var(--sf-accent); border: 2px solid var(--sf-text-strong);
}
.bq-range::-moz-range-thumb {
  width: 1.1rem; height: 1.1rem; border-radius: 50%;
  background: var(--sf-accent); border: 2px solid var(--sf-text-strong);
}
.bq-range:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: 3px; }
.bq-toolbar__range { width: 160px; max-width: 40vw; }
.bq-qnum { width: 5.5rem; }
.bq-table { --bs-table-bg: transparent; color: var(--sf-text); }
.bq-table th { color: var(--sf-text-muted); font-weight: 600; border-color: var(--sf-border); }
.bq-table td { border-color: var(--sf-border); }
.bq-mods { display: grid; grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr)); gap: .25rem 1rem; }
.bq-mod { display: flex; justify-content: flex-start; gap: .5rem; padding: .2rem 0; border-bottom: 1px solid var(--sf-border); }
.bq-presets .btn { min-width: 3.2rem; font-weight: 700; letter-spacing: .03em; }
.bq-batches { border-top: 1px dashed var(--sf-border); padding-top: .5rem; }
.bq-batch { padding: .45rem .6rem; margin-bottom: .45rem; border: 1px solid var(--sf-border); border-radius: 6px; }
.bq-batch__line { display: flex; align-items: center; gap: .5rem; margin-top: .25rem; }
.bq-batch__label { width: 2.5rem; flex: 0 0 auto; }
.bq-batch__unit { width: 2.2rem; flex: 0 0 auto; }
.bq-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: .75rem 1.5rem; }
.bq-toolbar__item { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; }
.bq-toolbar__count { flex: 0 0 auto; }
.bq-mat__total { font-size: 1.15rem; font-weight: 700; color: var(--sf-accent-text, var(--sf-accent)); }
@media (min-width: 1200px) {
  .bq-sticky { position: sticky; top: calc(var(--sf-topbar-h, 53px) + var(--sf-tabs-h, 53px) + .5rem); }
}
</style>
