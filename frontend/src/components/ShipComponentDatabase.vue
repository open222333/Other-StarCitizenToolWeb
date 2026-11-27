<!--
  資料庫 › 飛船組件（待辦 P1–P4）：先選組件種類，再列出那個種類的全部組件，每個欄位都能排序。
  資料跟配裝模擬同一份（後端 src/models/loadout.py：/item/loadout/item-types、/item/loadout/items，@public_api，不用登入）。
  篩選：尺寸／等級／分類是直接列出來的選項按鈕（依目前種類實際有的值，可複選），取得是「可購買」「可製作」開關。
  欄位見 utils/componentColumns.js：名稱／尺寸／等級／分類／廠商＋那個種類的全部參數＋電力、冷卻、訊號、耐久、質量、售價；
  整欄都沒有值的不顯示。「取得」欄與篩選：可購買（UEX 買得到）、可製作（有藍圖）；買得到的列有「購買地點」按鈕跳出視窗。
-->
<template>
  <div class="sf-split">
    <div class="card scifi-card sf-search mb-3">
      <div class="card-body py-3">
        <!-- 種類：手機種類太多排不下，改下拉 -->
        <template v-if="isPhone">
          <label class="form-label small fw-semibold mb-1" for="scd-type">種類</label>
          <select id="scd-type" v-model="type" class="form-select mb-2">
            <option v-for="t in types" :key="t.type" :value="t.type">{{ typeName(t.type) }}（{{ t.count }}）</option>
          </select>
        </template>
        <span v-if="!isPhone" id="scd-type-l" class="form-label small fw-semibold mb-1 d-block">種類</span>
        <!-- 種類：一格一張小卡（圖示＋名稱＋數量），選中的實心強調色 -->
        <div v-if="!isPhone" class="scd-types mb-3" role="group" aria-labelledby="scd-type-l">
          <button v-for="t in types" :key="t.type" type="button" class="scd-type"
            :class="{ active: type === t.type }" :aria-pressed="type === t.type ? 'true' : 'false'" @click="type = t.type">
            <i :class="typeIcon(t.type)" class="scd-type__icon" aria-hidden="true"></i>
            <span class="scd-type__name">{{ typeName(t.type) }}</span>
            <span class="scd-type__n">{{ t.count }}</span>
          </button>
        </div>
        <div class="row g-2 align-items-end">
          <div class="col col-md-4">
            <label class="form-label small fw-semibold mb-1" for="scd-q">名稱</label>
            <input id="scd-q" v-model="query" type="search" class="form-control" placeholder="中英文名稱、廠商…" autocomplete="off">
          </div>
          <SfFilterSheet :count="sheetCount" title="組件篩選" @clear="clearSheet">
            <div class="col-12 col-md-4">
              <label class="form-label small mb-1" for="scd-mfr">廠商</label>
              <MultiSelectFilter id="scd-mfr" v-model="mfrs" :options="mfrOptions" label="廠商" placeholder="全部" block searchable />
            </div>
            <!-- 取得：開關，打開＝只列可購買／可製作的（兩個都開＝兩種都行的） -->
            <div class="col-12 col-md-4">
              <span class="form-label small mb-1 d-block">取得</span>
              <div class="sf-pills sf-pills--field">
                <SfToggle v-model="buyOnly" icon="bi bi-cart3">可購買</SfToggle>
                <SfToggle v-model="craftOnly" icon="bi bi-hammer">可製作</SfToggle>
              </div>
            </div>
            <!-- 尺寸／等級／分類：選項直接列出來（依目前種類有的值），可以複選；都沒選＝全部 -->
            <div v-for="g in chipGroups" :key="g.key" class="col-12">
              <span :id="`scd-${g.key}-l`" class="form-label small mb-1 d-block">{{ g.label }}</span>
              <div class="sf-pills" role="group" :aria-labelledby="`scd-${g.key}-l`">
                <button v-for="o in g.options" :key="o.value" type="button" class="sf-pill scd-opt"
                  :class="[`scd-opt--${g.key}`, { active: g.model.value.includes(o.value) }]" :aria-pressed="g.model.value.includes(o.value) ? 'true' : 'false'"
                  @click="toggleOpt(g.model, o.value)">{{ o.label }}<span class="scd-count">{{ o.count }}</span></button>
              </div>
            </div>
          </SfFilterSheet>
        </div>
      </div>
    </div>

    <SfState :loading="loading && !items.length" :empty="!shown.length"
      :empty-text="items.length ? '沒有符合條件的組件。' : '這個種類目前沒有資料。'">
      <SortSelect v-if="isPhone" class="mb-2" :sort="sort" :options="sortOptions" />
      <div class="card scifi-card" :class="{ 'sf-list-loading': loading }">
        <div class="card-body p-0">
          <div class="scd-scroll">
            <table class="table table-hover align-middle mb-0 sf-stack scd-table">
              <thead class="table-light">
                <tr>
                  <SortTh v-for="(c, i) in cols" :key="c.key" :sort="sort" :field="c.key"
                    :class="[i === 0 ? 'ps-3' : c.left ? 'text-nowrap' : 'text-end text-nowrap', { 'pe-3': i === cols.length - 1 }]">
                    {{ c.label }}<span v-if="c.unit" class="scd-unit">{{ c.unit }}</span>
                  </SortTh>
                </tr>
              </thead>
              <tbody>
                <tr v-for="it in sort.sorted.value" :key="it.id">
                  <td class="ps-3 sf-stack__title">
                    <span class="fw-semibold">{{ it.name_zh || it.name }}</span>
                    <span v-if="it.name_zh && it.name_zh !== it.name" class="sf-name__en">{{ it.name }}</span>
                  </td>
                  <td v-for="(c, i) in cols.slice(1)" :key="c.key" class="text-nowrap"
                    :class="{ 'text-end': !c.left, 'scd-na': c.get(it) == null, 'scd-wide': c.wide, 'pe-3': i === cols.length - 2 }"
                    :data-label="c.unit ? `${c.label}（${c.unit}）` : c.label">
                    <!-- 取得：買得到的是「購買地點」按鈕（跳出視窗），可製作另外標 -->
                    <template v-if="c.key === 'acquire'">
                      <button v-if="it.buyable" type="button" class="btn btn-sm btn-success text-nowrap scd-buy"
                        :aria-label="`${it.name_zh || it.name} 購買地點`" @click="openBuy(it)">
                        <i class="bi bi-cart3 me-1"></i>購買地點</button>
                      <span v-if="it.blueprint" class="sf-chip scd-craft" :class="{ 'ms-1': it.buyable }">
                        <i class="bi bi-hammer me-1"></i>可製作</span>
                      <template v-if="!it.buyable && !it.blueprint">—</template>
                    </template>
                    <template v-else>{{ c.fmt(c.get(it), it) }}</template>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </SfState>

    <!-- 購買地點（UEX 玩家回報的價格，components/ItemPriceDetail.vue） -->
    <SfModal id="scd-buy" v-model:open="buyOpen" :title="buyItem ? (buyItem.name_zh || buyItem.name) : '購買地點'"
      icon="bi bi-cart3" width="760px">
      <ItemPriceDetail v-if="buyItem" :key="buyItem.id" :item-uuid="buyItem.id" :fetcher="fetcher" player buy-only />
    </SfModal>
  </div>
</template>

<script setup>
import SfToggle from '@/components/SfToggle.vue'
import { computed, ref, watch } from 'vue'
import ItemPriceDetail from '@/components/ItemPriceDetail.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import SfModal from '@/components/SfModal.vue'
import SfFilterSheet from '@/components/SfFilterSheet.vue'
import SfState from '@/components/SfState.vue'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'
import { baseColumns, componentColumns, visibleColumns } from '@/utils/componentColumns'
import { getJson } from '@/utils/getJson'
import { classLabel, loadLoadoutZh, typeLabel } from '@/utils/loadoutLabels'
import { manufacturerLabel } from '@/utils/vehicle'
import { toast } from '@/utils/toast'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 目前顯示中（第一次顯示才載資料） */
  active: { type: Boolean, default: false },
})

const { isPhone } = useBreakpoint()
const types = ref([])          // [{ type, count }]
const type = ref('')
const byType = ref({})         // type → 組件清單（查過的留著）
const loading = ref(false)
const query = ref('')
const sizes = ref([])
const grades = ref([])
const classes = ref([])
const mfrs = ref([])
// 取得方式開關：打開的都要符合（兩個都開＝兩種都行的）
const buyOnly = ref(false)
const craftOnly = ref(false)
const buyOpen = ref(false)
const buyItem = ref(null)
function openBuy(it) {
  buyItem.value = it
  buyOpen.value = true
}

// 種類按鈕的順序：常查的核心組件在前，其他照數量
const TYPE_ORDER = ['Shield', 'PowerPlant', 'Cooler', 'QuantumDrive', 'WeaponGun', 'Missile', 'Radar',
  'MissileLauncher', 'WeaponDefensive', 'Turret', 'WeaponMining', 'JumpDrive']
// 種類圖示（沒列到的用通用的方塊）
const TYPE_ICON = {
  Shield: 'bi-shield-fill', PowerPlant: 'bi-lightning-charge-fill', Cooler: 'bi-snow', QuantumDrive: 'bi-rocket-takeoff',
  WeaponGun: 'bi-crosshair', Missile: 'bi-send-fill', Radar: 'bi-broadcast', MissileLauncher: 'bi-grid-3x3-gap-fill',
  WeaponDefensive: 'bi-shield-shaded', Turret: 'bi-bullseye', WeaponMining: 'bi-gem', JumpDrive: 'bi-stars',
  TractorBeam: 'bi-magnet-fill', BombLauncher: 'bi-box-arrow-down', SalvageHead: 'bi-recycle', Bomb: 'bi-box-fill',
  MiningModifier: 'bi-sliders', TurretBase: 'bi-bullseye',
}
const typeIcon = t => `bi ${TYPE_ICON[t] || 'bi-box-seam'}`
const typeName = t => typeLabel([t]) || t
const items = computed(() => byType.value[type.value] || [])

async function loadTypes() {
  const { ok, data, message } = await getJson(props.fetcher, '/item/loadout/item-types', undefined, '讀取組件種類失敗')
  if (!ok) { toast(message, 'danger'); return }
  const rank = t => { const i = TYPE_ORDER.indexOf(t); return i < 0 ? TYPE_ORDER.length : i }
  types.value = (data || []).slice().sort((a, b) => rank(a.type) - rank(b.type) || b.count - a.count)
  loadLoadoutZh(types.value.map(t => ({ type: t.type })))
  if (!type.value && types.value.length) type.value = types.value[0].type
}

async function loadItems(t) {
  if (!t || byType.value[t]) return
  loading.value = true
  const { ok, data, message } = await getJson(props.fetcher, `/item/loadout/items?types=${encodeURIComponent(t)}`,
    undefined, '讀取組件失敗')
  loading.value = false
  if (!ok) { toast(message, 'danger'); return }
  // 子槽帶出來的預設配件（例如砲塔上的武器）不是這個種類，不列
  const rows = (data || []).filter(it => it.type === t)
  byType.value = { ...byType.value, [t]: rows }
  loadLoadoutZh(rows)
}

let started = false
watch(() => props.active, (on) => {
  if (on && !started) { started = true; loadTypes() }
}, { immediate: true })

// 換種類：條件清掉（尺寸、等級每種不一樣），排序回預設
watch(type, (t) => {
  sizes.value = []
  grades.value = []
  classes.value = []
  mfrs.value = []
  buyOnly.value = false
  craftOnly.value = false
  sort.set('')
  loadItems(t)
})

// 選項：目前種類的組件實際有的值（附數量），數字照大小、文字照字母排
function option(values, label) {
  const counts = new Map()
  for (const v of values) if (v != null && v !== '') counts.set(v, (counts.get(v) || 0) + 1)
  return [...counts].sort(([a], [b]) => (typeof a === 'number' ? a - b : String(a).localeCompare(String(b))))
    .map(([v, count]) => ({ value: String(v), label: label(v), count }))
}
function toggleOpt(model, value) {
  model.value = model.value.includes(value) ? model.value.filter(v => v !== value) : [...model.value, value]
}
const sizeOptions = computed(() => option(items.value.map(it => it.size), v => `S${v}`))
const gradeOptions = computed(() => option(items.value.map(it => it.grade), v => v))
const classOptions = computed(() => option(items.value.map(it => it.item_class), v => classLabel(v)))
const mfrOptions = computed(() => option(items.value.map(it => it.manufacturer), v => {
  const it = items.value.find(x => x.manufacturer === v)
  return manufacturerLabel(it?.manufacturer_name, v)
}))
// 選項少於 2 個的分組不列（例如全部都是 S1，選了也沒差）
const chipGroups = computed(() => [
  { key: 'size', label: '尺寸', model: sizes, options: sizeOptions.value },
  { key: 'grade', label: '等級', model: grades, options: gradeOptions.value },
  { key: 'class', label: '分類', model: classes, options: classOptions.value },
].filter(g => g.options.length > 1))
const sheetCount = computed(() => sizes.value.length + grades.value.length + classes.value.length + mfrs.value.length
  + (buyOnly.value ? 1 : 0) + (craftOnly.value ? 1 : 0))
function clearSheet() {
  sizes.value = []
  grades.value = []
  classes.value = []
  mfrs.value = []
  buyOnly.value = false
  craftOnly.value = false
}

const shown = computed(() => {
  const q = query.value.trim().toLowerCase()
  const has = (sel, v) => !sel.length || sel.includes(String(v ?? ''))
  return items.value.filter(it => has(sizes.value, it.size) && has(grades.value, it.grade)
    && has(classes.value, it.item_class) && has(mfrs.value, it.manufacturer)
    && (!buyOnly.value || it.buyable) && (!craftOnly.value || it.blueprint)
    && (!q || [it.name, it.name_zh, it.manufacturer, it.manufacturer_name, it.class_name]
      .some(v => (v || '').toLowerCase().includes(q))))
})

// 欄位：基本欄＋這個種類有值的參數欄
const cols = computed(() => [
  ...baseColumns(classLabel),
  ...visibleColumns(componentColumns(type.value), items.value),
])
const accessors = {}
watch(cols, (list) => {
  for (const k of Object.keys(accessors)) delete accessors[k]
  for (const c of list) accessors[c.key] = c.get
}, { immediate: true })
const sort = useTableSort(shown, { accessors })
const sortOptions = computed(() => cols.value.map(c => ({ field: c.key, label: c.label })))
</script>

<style scoped>
.scd-count { margin-left: .35rem; opacity: .75; }
/* 種類小卡：自動排滿一列，圖示＋名稱＋數量膠囊；hover 微亮、選中實心強調色加光暈 */
.scd-types { display: grid; grid-template-columns: repeat(auto-fill, minmax(10.5rem, 1fr)); gap: .5rem; }
.scd-type {
  display: flex; align-items: center; gap: .55rem; min-width: 0; padding: .55rem .75rem; text-align: left;
  border: 1px solid rgba(var(--sf-accent-rgb), .35); border-radius: .65rem;
  background: linear-gradient(135deg, rgba(var(--sf-accent-rgb), .1), rgba(var(--sf-accent-rgb), .02));
  color: var(--sf-text-strong); font-weight: 600; font-size: var(--sf-fs-sm);
  transition: border-color .15s, background .15s, box-shadow .15s, transform .15s;
}
.scd-type:hover:not(.active) {
  border-color: rgb(var(--sf-accent-rgb)); background: rgba(var(--sf-accent-rgb), .18); transform: translateY(-1px);
}
.scd-type.active {
  border-color: rgb(var(--sf-accent-rgb));
  background: linear-gradient(135deg, rgba(var(--sf-accent-rgb), .55), rgba(var(--sf-accent-rgb), .3));
  box-shadow: 0 0 0 1px rgb(var(--sf-accent-rgb)), 0 .25rem .9rem rgba(var(--sf-accent-rgb), .4);
}
.scd-type__icon {
  flex: none; display: grid; place-items: center; width: 1.9rem; height: 1.9rem; border-radius: .5rem;
  background: rgba(var(--sf-accent-rgb), .2); color: rgb(var(--sf-accent-rgb)); font-size: 1rem;
}
.scd-type.active .scd-type__icon { background: rgba(255, 255, 255, .18); color: var(--sf-text-strong); }
.scd-type__name { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.scd-type__n {
  flex: none; padding: .05rem .5rem; border-radius: 999px; font-size: var(--sf-fs-xs); font-weight: 700;
  background: rgba(var(--sf-accent-rgb), .18); color: var(--sf-text);
}
.scd-type.active .scd-type__n { background: rgba(0, 0, 0, .25); color: var(--sf-text-strong); }
@media (prefers-reduced-motion: reduce) { .scd-type { transition: none; } .scd-type:hover:not(.active) { transform: none; } }
/* 尺寸／等級／分類的選項：全站膠囊樣式（scifi-theme.css 的 .sf-pill），每組換一個顏色（尺寸＝主強調色、等級＝黃、分類＝綠） */
.scd-opt--grade { --sf-accent-rgb: var(--bs-warning-rgb); }
.scd-opt--class { --sf-accent-rgb: var(--bs-success-rgb); }
.scd-opt .scd-count { margin-left: 0; opacity: .85; }
/* 購買地點：比一般按鈕更醒目的綠色（實心底、粗體） */
.scifi-page .btn.scd-buy {
  font-weight: 700; color: var(--sf-text-strong);
  background: rgba(var(--bs-success-rgb), .4); border-color: rgb(var(--bs-success-rgb));
}
.scifi-page .btn.scd-buy:hover { background: rgba(var(--bs-success-rgb), .6); }
.scd-buy .bi { color: rgb(var(--bs-success-rgb)); }
/* 可製作：跟配裝模擬的「可製作」同一個顏色（次要強調色），實心底、粗體，跟綠色的購買地點按鈕一眼分得出來 */
.scifi-page .sf-chip.scd-craft {
  white-space: nowrap; font-weight: 700; color: var(--sf-text-strong);
  background: rgba(var(--sf-accent-2-rgb), .35); border-color: rgb(var(--sf-accent-2-rgb));
}
.scd-craft .bi { color: rgb(var(--sf-accent-2-rgb)); }
.scd-unit { display: block; font-size: var(--sf-fs-xs); font-weight: 400; color: var(--sf-text-muted); }
.scd-scroll { overflow-x: auto; }
.scd-table th, .scd-table td { white-space: nowrap; }
.scd-table td.scd-na { color: var(--sf-text-muted); }
/* 手機卡片：這一筆沒有值的參數整格不顯示，免得滿滿的「—」 */
@media (max-width: 767.98px) {
  .scifi-page table.sf-stack.scd-table td.scd-na[data-label] { display: none !important; }
  .scd-table th, .scd-table td { white-space: normal; }
  /* 長的文字（電源分段、傷害類型）佔整列 */
  .scifi-page table.sf-stack.scd-table tr:not(.sf-stack__detail) > td.scd-wide { flex-basis: 100%; }
}
</style>
