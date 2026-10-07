<!--
  藍圖「品質試算」：每個部位（Frame／Barrel…）放的材料品質 0–1000 會影響成品屬性，
  拖拉每個部位的品質，即時看到各屬性的倍率與綜合加成。

  資料：GET /blueprint/master/<uuid>/quality（scunpacked-data，見 src/models/blueprint_quality.py）；
  計算：utils/craftQuality.js（純函式、有測試）。這裡只負責畫面。
  只顯示倍率／加減值，不顯示成品的實際數值（例如射速 RPM）——成品基礎數值目前沒有可靠來源。
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
                <div v-if="r.name_zh" class="bq-muted bq-small">{{ r.name }}</div>
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
              <input v-model.number="qualities[slot.key]" type="number" class="form-control form-control-sm bq-qnum"
                :min="QUALITY_MIN" :max="QUALITY_MAX" :aria-label="`${slot.name} 品質`">
            </div>
            <div v-if="qualities[slot.key] < minQualityOf(slot)" class="bq-warn">
              低於最低品質 Q{{ minQualityOf(slot) }}，這個材料不能用
            </div>
            <div v-if="slot.modifiers.length" style="overflow-x: auto">
              <table class="table table-sm align-middle mb-0 mt-1 bq-table">
                <thead>
                  <tr><th>屬性</th><th class="text-end">Q0</th><th class="text-end">Q500</th><th class="text-end">Q1000</th><th class="text-end">目前</th></tr>
                </thead>
                <tbody>
                  <tr v-for="m in slot.modifiers" :key="m.key || m.name">
                    <td>{{ m.name_zh || m.name }}</td>
                    <td class="text-end bq-muted">{{ fmtModifier(modifierAt(m, 0), isAdditive(m)) }}</td>
                    <td class="text-end bq-muted">{{ fmtModifier(modifierAt(m, 500), isAdditive(m)) }}</td>
                    <td class="text-end bq-muted">{{ fmtModifier(modifierAt(m, 1000), isAdditive(m)) }}</td>
                    <td class="text-end fw-bold">
                      <!-- 顏色放在 span 上：Bootstrap 表格會用 --bs-table-color 蓋掉 td 上的文字顏色 -->
                      <span :class="betterClass(m, modifierAt(m, qualities[slot.key]))">
                        {{ fmtModifier(modifierAt(m, qualities[slot.key]), isAdditive(m)) }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
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
  QUALITY_MAX, QUALITY_MIN, combine, fmtModifier, fmtPercent, improves, isAdditive, modifierAt,
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
</style>
