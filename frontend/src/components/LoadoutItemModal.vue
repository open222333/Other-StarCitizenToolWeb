<!--
  配裝模擬的配件詳細（跳出視窗，LoadoutSimulator 打開）：三個分頁
  - 購買：UEX 購買地點與價格（components/ItemPriceDetail.vue）
  - 藍圖：可製作的配件，列配方材料、是否預設可用、解鎖任務（點開 BlueprintMissionsModal）
  - 品質：可製作的配件調每個部位的材料品質（0–1000），即時看加成；不可製作的固定 Q500
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
        <button type="button" class="btn btn-sm btn-success ms-auto text-nowrap" @click="lo.addCart(item, 1)">
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

      <!-- 品質 -->
      <div v-else>
        <div v-if="!item.blueprint" class="lim-empty"><i class="bi bi-lock-fill me-1"></i>不可製作的配件固定 Q500（遊戲資料的數值）。</div>
        <SfState v-else :loading="qLoading" :error="qError" @retry="loadQuality">
          <template v-if="qSlots">
            <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
              <span class="fw-semibold">全部部位</span>
              <div class="lim-seg" role="group" aria-label="全部部位品質">
                <button v-for="p in PRESETS" :key="p" type="button" class="lim-seg__btn" :class="{ active: allAt(p) }" @click="setAll(p)">Q{{ p }}</button>
              </div>
            </div>
            <div v-for="s in qSlots" :key="s.key" class="lim-slot">
              <div class="d-flex justify-content-between align-items-baseline gap-2">
                <span class="fw-semibold">{{ s.name_zh || s.name }}</span>
                <span class="lim-q">Q{{ q[s.key] }}</span>
              </div>
              <input type="range" class="form-range" min="0" max="1000" step="10" :value="q[s.key]"
                :aria-label="`${s.name_zh || s.name} 品質`" @input="setOne(s.key, $event.target.value)">
              <div class="lim-mods">
                <span v-for="m in s.modifiers" :key="m.key" :class="{ 'lim-muted': !applied(m.key) }">{{ m.name_zh || m.name }}</span>
              </div>
            </div>
            <h4 class="lim-h mt-3">綜合加成</h4>
            <div class="lim-rows">
              <div v-for="r in rows" :key="r.key" class="lim-row">
                <span>{{ r.name_zh || r.name }}<span v-if="!applied(r.key)" class="lim-muted ms-1">（配裝模擬沒有計算）</span></span>
                <b :class="r.better === true ? 'sf-good' : r.better === false ? 'sf-bad' : ''">
                  {{ r.additive ? fmtModifier(r.value, true) : fmtPercent(r.value) }}</b>
              </div>
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
import { combine, fmtModifier, fmtPercent } from '@/utils/craftQuality'
import { LOCKED_QUALITY, applied, avgQuality, qualitiesOf } from '@/utils/loadoutCraft'
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
const PRESETS = [0, 250, 500, 750, 1000]
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
const allAt = p => Object.values(q.value).every(v => v === p)
function setAll(p) {
  lo.setQuality(props.item.id, Object.fromEntries(qSlots.value.map(s => [s.key, p])))
}
function setOne(key, v) {
  lo.setQuality(props.item.id, { ...q.value, [key]: Math.round(Number(v)) })
}

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
.lim-q { font-weight: 800; color: var(--sf-accent-2); font-variant-numeric: tabular-nums; }
.lim-mods { display: flex; flex-wrap: wrap; gap: .2rem .75rem; font-size: var(--sf-fs-sm); color: var(--sf-text); }
.lim-muted { color: var(--sf-text-muted); }
.lim-rows { display: flex; flex-direction: column; }
.lim-row { display: flex; justify-content: space-between; gap: .75rem; padding: .35rem 0; border-bottom: 1px solid var(--sf-border); }
.min-w-0 { min-width: 0; }
</style>
