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
      <!-- 全部部位一起設定 -->
      <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
        <span class="fw-semibold">全部品質</span>
        <div class="btn-group btn-group-sm" role="group" aria-label="全部部位品質">
          <button v-for="p in PRESETS" :key="p.q" type="button" class="btn btn-subtab"
            :class="{ active: allAt(p.q) }" @click="setAll(p.q)">{{ p.label }}</button>
        </div>
      </div>

      <!-- 需要的材料 -->
      <h4 class="bq-title">需要的材料</h4>
      <div class="row g-2 mb-3">
        <div v-for="m in materials" :key="m.key" class="col-12 col-md-6 col-xl-4">
          <div class="bq-card h-100">
            <div class="d-flex justify-content-between gap-2">
              <span class="fw-semibold">{{ m.label }}</span>
              <span class="bq-accent text-nowrap">{{ m.qty }}</span>
            </div>
            <div class="bq-warn">最低品質 Q{{ m.minQuality }}</div>
          </div>
        </div>
      </div>

      <div class="row g-3">
        <!-- 綜合加成 -->
        <div class="col-12 col-xl-5">
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

        <!-- 各部位 -->
        <div class="col-12 col-xl-7">
          <h4 class="bq-title">各部位</h4>
          <div v-for="slot in data.slots" :key="slot.key" class="bq-card mb-2">
            <div class="d-flex flex-wrap justify-content-between gap-2 mb-1">
              <span class="fw-bold">{{ slot.name_zh || slot.name }}<span v-if="slot.name_zh" class="bq-muted ms-1">{{ slot.name }}</span></span>
              <span class="text-nowrap">
                <span class="bq-accent">{{ optionLabel(slot.options[0]) }}</span>
                <span v-if="slot.options[0]" class="ms-1">{{ optionQty(slot.options[0]) }}</span>
                <span v-if="slot.options.length > 1" class="bq-muted ms-1">（{{ slot.options.length }} 選 {{ slot.required_count }}）</span>
              </span>
            </div>
            <div class="d-flex align-items-center gap-2">
              <label class="bq-muted mb-0 text-nowrap" :for="`bq-${uid}-${slot.key}`">品質</label>
              <input :id="`bq-${uid}-${slot.key}`" v-model.number="qualities[slot.key]" type="range"
                class="flex-grow-1 bq-range" :min="QUALITY_MIN" :max="QUALITY_MAX" step="1"
                :style="{ '--bq-fill': `${(qualities[slot.key] / QUALITY_MAX) * 100}%` }">
              <!-- 輸入值限制在 Q0～Q1000（整數），超出就夾回端點 -->
              <input :value="qualities[slot.key]" type="number" class="form-control form-control-sm bq-qnum"
                :min="QUALITY_MIN" :max="QUALITY_MAX" step="1" :aria-label="`${slot.name} 品質`"
                @change="qualities[slot.key] = clampQuality($event.target.value); $event.target.value = qualities[slot.key]">
            </div>
            <!-- MIN＝這個材料能用的最低品質、MID＝Q500、MAX＝Q1000 -->
            <div class="btn-group btn-group-sm mt-1 bq-presets" role="group" :aria-label="`${slot.name} 品質快速設定`">
              <button type="button" class="btn btn-info" @click="qualities[slot.key] = Math.max(QUALITY_MIN, minQualityOf(slot))">MIN</button>
              <button type="button" class="btn btn-info" @click="qualities[slot.key] = Math.round((QUALITY_MIN + QUALITY_MAX) / 2)">MID</button>
              <button type="button" class="btn btn-info" @click="qualities[slot.key] = QUALITY_MAX">MAX</button>
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

function optionQty(o) {
  if (!o) return ''
  if (o.quantity_scu !== null && o.quantity_scu !== undefined) return `${o.quantity_scu} SCU`
  if (o.quantity !== null && o.quantity !== undefined) return `${o.quantity} 個`
  return ''
}

const materials = computed(() => (data.value?.slots || []).flatMap(slot => (slot.options || []).map((o, i) => ({
  key: `${slot.key}|${i}`, label: optionLabel(o), qty: optionQty(o), minQuality: o.min_quality || 0,
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
.bq-qnum { width: 5.5rem; }
.bq-table { --bs-table-bg: transparent; color: var(--sf-text); }
.bq-table th { color: var(--sf-text-muted); font-weight: 600; border-color: var(--sf-border); }
.bq-table td { border-color: var(--sf-border); }
.bq-mods { display: grid; grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr)); gap: .25rem 1rem; }
.bq-mod { display: flex; justify-content: flex-start; gap: .5rem; padding: .2rem 0; border-bottom: 1px solid var(--sf-border); }
.bq-presets .btn { min-width: 3.2rem; font-weight: 700; letter-spacing: .03em; }
</style>
