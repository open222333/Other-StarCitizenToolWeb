<!--
  配裝模擬的配件詳細（跳出視窗，LoadoutSimulator 打開）：三個分頁
  - 購買：UEX 購買地點與價格（components/ItemPriceDetail.vue）
  - 藍圖：可製作的配件，列配方材料、是否預設可用、解鎖任務（點開 BlueprintMissionsModal）
  - 品質：可製作的配件調每個部位的材料品質（0–1000，拉條共用 QualitySlider），列配方、各部位加成與實際數值；
    底部一次設定全部部位（MIN＝各部位能用的最低品質）；不可製作的固定 Q500
    （配件主檔的數值就是 Q500，見 utils/loadoutCraft.js）
  需要的東西由 LoadoutSimulator provide（'loadout'：itemLabel、typeLabel、qualityData、qualityOf、setQuality、addCart）。
-->
<template>
  <SfModal id="lo-item" :open="open" :title="item ? lo.itemLabel(item) : '配件'" icon="bi bi-box-seam" width="900px"
    @update:open="$emit('update:open', $event)">
    <template v-if="item">
      <div class="lim-head">
        <span class="lim-size">S{{ item.size }}</span>
        <div class="min-w-0">
          <div class="lim-sub">{{ [lo.typeLabel([`${item.type}.${item.sub_type}`]), manufacturerShort(item.manufacturer_name, item.manufacturer),
            item.name_zh && item.name_zh !== item.name ? item.name : ''].filter(x => x && x !== '—').join(' · ') }}</div>
          <div class="d-flex flex-wrap gap-1 mt-1">
            <span v-if="item.buyable" class="lim-tag lim-tag--buy"><i class="bi bi-cart3 me-1"></i>可購買 · 最低 {{ fmtAuec(item.price) }}</span>
            <span v-else class="lim-tag">買不到</span>
            <span v-if="item.blueprint" class="lim-tag lim-tag--craft"><i class="bi bi-hammer me-1"></i>可製作 · Q{{ avg }}</span>
            <span v-else class="lim-tag"><i class="bi bi-lock-fill me-1"></i>不可製作 · Q500</span>
          </div>
        </div>
        <div v-if="tab === 'quality' && item.blueprint" class="lim-big ms-auto" aria-label="整體品質">
          <span class="lim-big__l">整體品質</span><span class="lim-big__v">Q{{ avg }}</span></div>
        <button type="button" class="btn btn-sm btn-success text-nowrap" :class="{ 'ms-auto': !(tab === 'quality' && item.blueprint) }" @click="lo.addCart(item, 1)">
          <i class="bi bi-cart-plus me-1"></i>加入購物車</button>
      </div>

      <div class="lim-tabs" role="tablist">
        <button v-for="t in TABS" :key="t.key" type="button" class="lim-tab" role="tab" :aria-selected="tab === t.key ? 'true' : 'false'"
          :class="{ active: tab === t.key }" @click="tab = t.key"><i :class="t.icon" class="me-1"></i>{{ t.label }}</button>
      </div>

      <!-- 購買 -->
      <div v-if="tab === 'buy'">
        <ItemPriceDetail v-if="item.buyable" :key="item.id" :item-uuid="item.id" :fetcher="fetcher" player buy-only />
        <div v-else class="lim-empty">UEX 沒有這個配件的販售資料<template v-if="item.blueprint">，可以自己製作（看「藍圖」）</template>。</div>
      </div>

      <!-- 藍圖 -->
      <div v-else-if="tab === 'bp'">
        <div v-if="!item.blueprint" class="lim-empty">這個配件沒有藍圖，不能製作。</div>
        <SfState v-else :loading="bpLoading" :error="bpError" @retry="loadBlueprint">
          <template v-if="bp">
            <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
              <span class="fw-semibold">{{ bp.name_zh || bp.name }}</span>
              <span v-if="bp.is_available_by_default" class="lim-tag lim-tag--buy">預設可用</span>
              <span v-if="bp.craft_time_label" class="lim-tag"><i class="bi bi-clock me-1"></i>{{ bp.craft_time_label }}</span>
              <button v-if="bp.unlocking_missions_count" type="button" class="btn btn-sm btn-info ms-auto" @click="openMissions">
                <i class="bi bi-flag me-1"></i>解鎖任務 {{ bp.unlocking_missions_count }} 個</button>
            </div>
            <h4 class="lim-h">材料</h4>
            <div v-if="!bp.ingredients?.length" class="lim-empty">—</div>
            <div v-for="(ing, i) in bp.ingredients || []" :key="i" class="lim-mat">
              <span>{{ materialLabel(ing) }}</span>
              <span class="lim-mat__q">{{ fmtQty(ing) }}<span v-if="ing.min_quality" class="lim-warn ms-2">最低 Q{{ ing.min_quality }}</span></span>
            </div>
          </template>
        </SfState>
      </div>

      <!-- 品質：配方（每個部位的材料與用量）→ 每個部位一張拉條卡 → 實際數值；底部固定列一次設定全部部位 -->
      <div v-else>
        <div v-if="!item.blueprint" class="lim-empty"><i class="bi bi-lock-fill me-1"></i>不可製作的配件固定 Q500（遊戲資料的數值）。</div>
        <SfState v-else :loading="qLoading" :error="qError" @retry="loadQuality">
          <template v-if="qSlots">
            <h4 class="lim-h">配方</h4>
            <div class="lim-recipe mb-3">
              <div v-for="s in qSlots" :key="s.key" class="lim-recipe__row">
                <div class="min-w-0">
                  <div class="fw-semibold">{{ s.name_zh || s.name }}</div>
                  <div class="lim-caps">{{ s.modifiers.map(m => m.name_zh || m.name).join(' · ') || '不影響屬性' }}</div>
                </div>
                <div class="lim-recipe__mat">
                  <span>{{ optLabel(s.options?.[0]) }}</span>
                  <span v-if="s.options?.[0]" class="lim-recipe__qty">· {{ fmtQty(s.options[0]) }}</span>
                  <span v-if="s.options?.length > 1" class="lim-muted ms-1">（{{ s.options.length }} 選 {{ s.required_count || 1 }}）</span>
                </div>
              </div>
            </div>

            <div v-for="s in qSlots" :key="s.key" class="lim-slot">
              <div class="d-flex flex-wrap justify-content-between align-items-baseline gap-2 mb-1">
                <span class="fw-semibold">{{ s.name_zh || s.name }}</span>
                <span v-if="primaryMod(s)" class="text-nowrap">
                  <span class="lim-muted me-1">{{ primaryMod(s).name_zh || primaryMod(s).name }}</span>
                  <b :class="betterClass(primaryMod(s), modifierAt(primaryMod(s), q[s.key]))">{{ fmtMod(primaryMod(s), modifierAt(primaryMod(s), q[s.key])) }}</b>
                </span>
              </div>
              <QualitySlider :model-value="q[s.key]" :name="`${s.name_zh || s.name} 品質`" :min-quality="minQualityOf(s)"
                :ticks="ticksOf(s)" @update:model-value="setOne(s.key, $event)" />
              <div v-if="s.modifiers.length > 1" class="lim-mods mt-1">
                <span v-for="m in s.modifiers.slice(1)" :key="m.key" :class="{ 'lim-muted': !applied(m.key) }">
                  {{ m.name_zh || m.name }} <b :class="betterClass(m, modifierAt(m, q[s.key]))">{{ fmtMod(m, modifierAt(m, q[s.key])) }}</b></span>
              </div>
            </div>

            <h4 class="lim-h mt-3">實際數值</h4>
            <div class="lim-rows">
              <div v-for="r in stats" :key="r.key" class="lim-row">
                <span>{{ r.label }}</span>
                <span class="text-nowrap"><span class="lim-muted">{{ fmtStat(r.before, r.unit) }}</span>
                  <i class="bi bi-arrow-right mx-1 lim-muted"></i>
                  <b :class="r.better === true ? 'sf-good' : r.better === false ? 'sf-bad' : ''">{{ fmtStat(r.after, r.unit) }}</b></span>
              </div>
              <div v-for="r in otherRows" :key="r.key" class="lim-row">
                <span>{{ r.name_zh || r.name }}<span v-if="!applied(r.key)" class="lim-muted ms-1">（配裝模擬沒有計算）</span></span>
                <b :class="r.better === true ? 'sf-good' : r.better === false ? 'sf-bad' : ''">
                  {{ r.additive ? fmtModifier(r.value, true) : fmtPercent(r.value) }}</b>
              </div>
            </div>

            <div class="lim-bar">
              <span class="fw-semibold text-nowrap">全部部位</span>
              <div class="lim-seg" role="group" aria-label="全部部位品質">
                <button v-for="p in PRESETS" :key="p.label" type="button" class="lim-seg__btn" :class="{ active: allAt(p) }"
                  @click="setAll(p)">{{ p.label }}</button>
              </div>
              <button type="button" class="btn btn-sm btn-secondary ms-auto" @click="$emit('update:open', false)">關閉</button>
            </div>
          </template>
        </SfState>
      </div>
    </template>
  </SfModal>
</template>

<script setup>
import { computed, inject, ref, watch } from 'vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import ItemPriceDetail from '@/components/ItemPriceDetail.vue'
import QualitySlider from '@/components/QualitySlider.vue'
import { QUALITY_MAX, QUALITY_MID, combine, fmtModifier, fmtPercent, fmtStat, improves, isAdditive, minQualityOf, modifierAt } from '@/utils/craftQuality'
import { LOCKED_QUALITY, applied, appliedStats, avgQuality, qualitiesOf } from '@/utils/loadoutCraft'
import { loadMaterialZh, materialLabel } from '@/utils/blueprintMaterial'
import { fmtAuec } from '@/utils/uexCommodity'
import { manufacturerShort } from '@/utils/vehicle'

const props = defineProps({
  open: { type: Boolean, default: false },
  item: { type: Object, default: null },
  /** 打開時的分頁：buy／bp／quality */
  initialTab: { type: String, default: 'buy' },
  fetcher: { type: Function, required: true },
})
const emit = defineEmits(['update:open', 'missions'])
const lo = inject('loadout')

const TABS = [
  { key: 'buy', label: '購買地點', icon: 'bi bi-cart3' },
  { key: 'bp', label: '藍圖', icon: 'bi bi-hammer' },
  { key: 'quality', label: '品質', icon: 'bi bi-sliders' },
]
// 底部的全部部位預設：MIN＝每個部位各自能用的最低品質
const PRESETS = [{ label: 'MIN', q: null }, { label: '500', q: QUALITY_MID }, { label: '750', q: 750 }, { label: '900', q: 900 }, { label: 'MAX', q: QUALITY_MAX }]
const tab = ref('buy')
watch(() => [props.open, props.item?.id], ([o]) => { if (o) tab.value = props.initialTab })

// ── 藍圖 ──
const bp = ref(null)
const bpLoading = ref(false)
const bpError = ref('')
async function loadBlueprint() {
  const uuid = props.item?.blueprint
  if (!uuid) return
  bpLoading.value = true
  bpError.value = ''
  const res = await props.fetcher(`/blueprint/master/${encodeURIComponent(uuid)}`)
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (props.item?.blueprint !== uuid) return
  bpLoading.value = false
  if (!body?.success) { bpError.value = '讀取藍圖失敗。'; return }
  bp.value = body.data
  loadMaterialZh(bp.value)
}
function openMissions() {
  emit('missions', { uuid: bp.value._id, name: bp.value.name, name_zh: bp.value.name_zh, output_type: bp.value.output_type })
}
function fmtQty(m) {
  if (m.quantity_scu != null) return `${m.quantity_scu} SCU`
  if (m.quantity != null) return `× ${m.quantity}`
  return '—'
}

// ── 品質 ──
const qSlots = ref(null)
const qLoading = ref(false)
const qError = ref('')
async function loadQuality() {
  const uuid = props.item?.blueprint
  if (!uuid) return
  qLoading.value = true
  qError.value = ''
  const slots = await lo.qualityData(uuid)
  if (props.item?.blueprint !== uuid) return
  qLoading.value = false
  if (!slots) { qError.value = '讀取品質資料失敗。'; return }
  qSlots.value = slots
}
const q = computed(() => qualitiesOf(qSlots.value, lo.qualityOf(props.item?.id)))
const rows = computed(() => combine(qSlots.value || [], q.value))
const avg = computed(() => (qSlots.value ? avgQuality(qSlots.value, lo.qualityOf(props.item?.id)) : lo.avgOf(props.item)))
const presetOf = (p, s) => (p.q === null ? minQualityOf(s) : p.q)
const allAt = p => (qSlots.value || []).every(s => q.value[s.key] === presetOf(p, s))
function setAll(p) {
  lo.setQuality(props.item.id, Object.fromEntries(qSlots.value.map(s => [s.key, presetOf(p, s)])))
}
function setOne(key, v) {
  lo.setQuality(props.item.id, { ...q.value, [key]: Math.round(Number(v)) })
}
// 實際數值：配裝模擬有反映、配件也有這個數值的列「原本 → 調整後」；其他屬性列綜合加成
const stats = computed(() => (qSlots.value ? appliedStats(props.item, qSlots.value, q.value) : []))
const otherRows = computed(() => {
  const shown = new Set(stats.value.map(r => r.key.split(':')[0]))
  return rows.value.filter(r => !shown.has(r.key))
})
// 每個部位標題列顯示的屬性：配裝模擬有反映的優先
const primaryMod = s => s.modifiers.find(m => applied(m.key)) || s.modifiers[0] || null
const fmtMod = (m, v) => (isAdditive(m) ? fmtModifier(v, true) : fmtPercent(v))
function betterClass(m, v) {
  const b = improves(m, v)
  return b === true ? 'sf-good' : b === false ? 'sf-bad' : ''
}
// 拉條刻度：主要屬性在 Q0／Q500／Q1000 的加成（例如 −10%／0%／+10%）
function ticksOf(s) {
  const m = primaryMod(s)
  if (!m) return []
  return [0, QUALITY_MID, QUALITY_MAX].map(qv => ({ q: qv, label: fmtMod(m, modifierAt(m, qv)) || '—' }))
}
const optLabel = o => (o ? o.name_zh || o.name || '—' : '—')

// 換了配件或打開時重新載（藍圖、品質資料）
watch(() => [props.open, props.item?.id], ([o]) => {
  if (!o) return
  bp.value = null
  qSlots.value = null
  if (props.item?.blueprint) {
    loadBlueprint()
    loadQuality()
  }
}, { immediate: true })
defineExpose({ LOCKED_QUALITY })
</script>

<style scoped>
.lim-head { display: flex; align-items: center; gap: .85rem; margin-bottom: 1rem; flex-wrap: wrap; }
.lim-size { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 2.8rem; height: 2.8rem; border-radius: .5rem;
  font-weight: 800; color: var(--sf-accent-2-ink, #0b1020); background: var(--sf-accent-2); }
.lim-sub { color: var(--sf-text-muted); font-size: var(--sf-fs-sm); }
.lim-tag { display: inline-flex; align-items: center; padding: .1rem .5rem; border-radius: .3rem; font-size: var(--sf-fs-xs); font-weight: 700;
  color: var(--sf-text); background: var(--sf-chip-bg); border: 1px solid var(--sf-border); }
.lim-tag--buy { color: rgb(var(--bs-success-rgb)); border-color: rgba(var(--bs-success-rgb), .5); }
.lim-tag--craft { color: var(--sf-accent-2); border-color: rgba(var(--sf-accent-2-rgb), .55); }
.lim-tabs { display: flex; gap: .25rem; border-bottom: 1px solid var(--sf-border); margin-bottom: 1rem; overflow-x: auto; }
.lim-tab { border: 0; background: none; padding: .5rem .9rem; font-weight: 700; color: var(--sf-text); position: relative; white-space: nowrap; }
.lim-tab:hover { color: var(--sf-text-strong); }
.lim-tab.active { color: var(--sf-accent-text, var(--sf-accent)); }
.lim-tab.active::after { content: ''; position: absolute; left: .6rem; right: .6rem; bottom: -1px; height: 3px; border-radius: 3px 3px 0 0; background: var(--sf-accent); }
.lim-empty { color: var(--sf-text-muted); padding: .75rem 0; }
.lim-h { font-size: var(--sf-fs-md); font-weight: 800; color: var(--sf-text-strong); margin-bottom: .5rem; }
.lim-mat { display: flex; justify-content: space-between; gap: .75rem; padding: .4rem 0; border-bottom: 1px solid var(--sf-border); }
.lim-mat__q { font-weight: 700; color: var(--sf-text-strong); white-space: nowrap; }
.lim-warn { color: var(--sf-accent-2); font-size: var(--sf-fs-sm); }
.lim-seg { display: inline-flex; gap: .2rem; padding: .2rem; border-radius: .5rem; background: var(--sf-chip-bg); border: 1px solid var(--sf-border); }
.lim-seg__btn { border: 0; background: none; padding: .2rem .6rem; border-radius: .35rem; font-weight: 600; color: var(--sf-text); font-size: var(--sf-fs-sm); }
.lim-seg__btn.active { background: rgba(var(--sf-accent-rgb), .28); color: var(--sf-text-strong); }
.lim-slot { padding: .6rem .75rem; margin-bottom: .5rem; border: 1px solid var(--sf-border); border-radius: .5rem; background: var(--sf-chip-bg); }
.lim-mods { display: flex; flex-wrap: wrap; gap: .2rem .75rem; font-size: var(--sf-fs-sm); color: var(--sf-text); }
.lim-muted { color: var(--sf-text-muted); }
.lim-rows { display: flex; flex-direction: column; }
.lim-row { display: flex; justify-content: space-between; gap: .75rem; padding: .35rem 0; border-bottom: 1px solid var(--sf-border); }
.lim-recipe { display: flex; flex-direction: column; border: 1px solid var(--sf-border); border-radius: .5rem; }
.lim-recipe__row { display: flex; justify-content: space-between; align-items: center; gap: .75rem; padding: .5rem .75rem; }
.lim-recipe__row + .lim-recipe__row { border-top: 1px solid var(--sf-border); }
.lim-recipe__mat { text-align: right; font-weight: 600; color: var(--sf-text-strong); }
.lim-recipe__qty { color: var(--sf-accent-2); margin-left: .25rem; white-space: nowrap; }
.lim-caps { font-size: var(--sf-fs-xs); letter-spacing: .06em; text-transform: uppercase; color: var(--sf-text-muted); }
.lim-big { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.1; }
.lim-big__l { font-size: var(--sf-fs-xs); color: var(--sf-text-muted); }
.lim-big__v { font-size: var(--sf-fs-xl); font-weight: 800; color: var(--sf-accent-2); font-variant-numeric: tabular-nums; }
.lim-bar { position: sticky; bottom: 0; z-index: 1; display: flex; flex-wrap: wrap; align-items: center; gap: .6rem;
  margin: 1rem -.25rem 0; padding: .6rem .75rem; border: 1px solid var(--sf-border); border-radius: .5rem;
  background: var(--sf-panel, var(--sf-bg)); box-shadow: 0 -6px 16px rgba(0, 0, 0, .25); }
.min-w-0 { min-width: 0; }
</style>
