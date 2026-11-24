<!--
  配裝模擬「更換配件」視窗（components/LoadoutSimulator.vue 打開）：上面一條大搜尋框＋分段篩選
  （武器：傷害類型、武器類型；其他：分類、等級…，見 utils/loadoutPicker.js），下面是數值表，
  欄位依配件種類（武器看 DPS、射速…；護盾看 HP、回充…），點欄位標題排序，點一列就換上。
  需要的函式由 LoadoutSimulator provide（'loadout'：itemLabel、typeLabel、primary）。
-->
<template>
  <SfModal id="lo-picker" :open="open" :title="title" icon="bi bi-arrow-left-right" width="1180px" @update:open="$emit('update:open', $event)">
    <div class="lpk-top">
      <div class="lpk-search sf-search-pill">
        <i class="bi bi-search sf-search-pill__icon" aria-hidden="true"></i>
        <input v-model="query" type="search" class="sf-search-pill__input" :placeholder="placeholder" aria-label="搜尋配件">
      </div>
      <div v-for="g in groups" :key="g.key" class="lpk-filter">
        <div :id="`lpk-f-${g.key}`" class="lpk-filter__label">{{ g.label }}</div>
        <div class="lpk-seg" role="group" :aria-labelledby="`lpk-f-${g.key}`">
          <button type="button" class="lpk-seg__btn" :class="{ active: !picked[g.key] }" :aria-pressed="!picked[g.key] ? 'true' : 'false'"
            @click="picked[g.key] = ''">全部</button>
          <button v-for="o in g.options" :key="o.value" type="button" class="lpk-seg__btn" :class="{ active: picked[g.key] === o.value }"
            :aria-pressed="picked[g.key] === o.value ? 'true' : 'false'" @click="picked[g.key] = picked[g.key] === o.value ? '' : o.value">
            {{ o.label }}</button>
        </div>
      </div>
      <!-- 跟資料庫 › 物品一樣的條件：廠商（多選）、只看買得到 -->
      <div v-if="mfrOptions.length > 1" class="lpk-filter lpk-filter--mfr">
        <label class="lpk-filter__label" for="lpk-mfr">廠商</label>
        <MultiSelectFilter id="lpk-mfr" v-model="mfrs" :options="mfrOptions" label="廠商" placeholder="全部" block searchable />
      </div>
      <div v-if="anyBuyable || anyCraftable" class="lpk-filter">
        <div id="lpk-f-buy" class="lpk-filter__label">取得</div>
        <div class="lpk-seg" role="group" aria-labelledby="lpk-f-buy">
          <button type="button" class="lpk-seg__btn" :class="{ active: !acquire }" :aria-pressed="!acquire ? 'true' : 'false'"
            @click="acquire = ''">全部</button>
          <button v-if="anyBuyable" type="button" class="lpk-seg__btn" :class="{ active: acquire === 'buy' }" :aria-pressed="acquire === 'buy' ? 'true' : 'false'"
            @click="acquire = acquire === 'buy' ? '' : 'buy'"><i class="bi bi-cart3 me-1"></i>買得到</button>
          <button v-if="anyCraftable" type="button" class="lpk-seg__btn" :class="{ active: acquire === 'craft' }" :aria-pressed="acquire === 'craft' ? 'true' : 'false'"
            @click="acquire = acquire === 'craft' ? '' : 'craft'"><i class="bi bi-hammer me-1"></i>可製作</button>
        </div>
      </div>
      <button v-if="currentId" type="button" class="btn btn-sm btn-warning lpk-unequip" @click="$emit('choose', null)">
        <i class="bi bi-eraser me-1"></i>卸下</button>
    </div>

    <SfState :loading="loading" :empty="!loading && !rows.length" :empty-text="items.length ? '沒有符合的配件。' : '沒有可以裝的配件。'">
      <div class="table-responsive">
        <table class="table align-middle mb-0 sf-stack lpk-table">
          <thead>
            <tr>
              <SortTh :sort="sort" field="name">名稱</SortTh>
              <SortTh v-for="c in cols" :key="c.key" :sort="sort" :field="c.key" class="text-end"
                :class="{ 'lpk-th--hot': sort.sortKey.value === c.key }">{{ c.label }}</SortTh>
            </tr>
          </thead>
          <tbody>
            <tr v-for="it in sorted" :key="it.id" class="lpk-row" :class="{ 'lpk-row--current': it.id === currentId }"
              tabindex="0" role="button" :aria-label="`換上 ${lo.itemLabel(it)}`"
              @click="pick(it)" @keydown.enter.prevent="pick(it)" @keydown.space.prevent="pick(it)">
              <td class="sf-stack__title">
                <div class="lpk-name">
                  <span class="lpk-size">S{{ it.size }}</span>
                  <div class="min-w-0">
                    <div class="lpk-title">
                      <span>{{ lo.itemLabel(it) }}</span>
                      <span v-if="it.type === 'WeaponGun' && dmgKind(it)" class="lpk-dmg" :class="`lpk-dmg--${dmgKind(it)}`">{{ dmgLabel(dmgKind(it)) }}</span>
                      <span v-if="it.id === currentId" class="lpk-using">使用中</span>
                      <span v-if="it.blueprint" class="lpk-craft" title="可製作"><i class="bi bi-hammer"></i></span>
                    </div>
                    <div class="lpk-sub">{{ subOf(it) }}</div>
                  </div>
                </div>
              </td>
              <td v-for="c in cols" :key="c.key" class="text-end text-nowrap lpk-num" :data-label="c.label"
                :class="{ 'lpk-num--hot': sort.sortKey.value === c.key }">{{ c.fmt(c.get(it), it) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </SfState>
  </SfModal>
</template>

<script setup>
import { filterByName } from '@/utils/nameSearch'
import { computed, inject, reactive, ref, watch } from 'vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import SortTh from '@/components/SortTh.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import { compareValues } from '@/composables/useTableSort'
import { columnsFor, dmgKind, dmgLabel, filterGroups, mainType, weaponKind, weaponKindLabel } from '@/utils/loadoutPicker'
import { manufacturerShort } from '@/utils/vehicle'
import { classLabel } from '@/utils/loadoutLabels'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, default: '更換配件' },
  /** 這一格可以裝的全部配件 */
  items: { type: Array, default: () => [] },
  currentId: { type: String, default: '' },
  loading: { type: Boolean, default: false },
  /** 搜尋框提示用的尺寸：「S3」 */
  slotText: { type: String, default: '' },
})
const emit = defineEmits(['update:open', 'choose'])
const lo = inject('loadout')

const query = ref('')
const picked = reactive({})
const mfrs = ref([])
const acquire = ref('')
const mfrKey = it => it.manufacturer || it.manufacturer_name || ''
const mfrOptions = computed(() => {
  const seen = new Map()
  for (const it of props.items) {
    const k = mfrKey(it)
    if (k && !seen.has(k)) seen.set(k, manufacturerShort(it.manufacturer_name, it.manufacturer))
  }
  return [...seen].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, 'zh-Hant'))
})
const anyBuyable = computed(() => props.items.some(it => it.buyable))
const anyCraftable = computed(() => props.items.some(it => it.blueprint))
const groups = computed(() => filterGroups(props.items, lo.typeLabel))
const main = computed(() => mainType(props.items, picked.type))
// 最後一欄是價格（UEX 最低購買價，買不到是「—」）
const PRICE_COL = { key: 'price', label: '價格 aUEC', get: it => it.price ?? null, fmt: v => (v == null ? '—' : Math.round(v).toLocaleString('en-US')) }
const cols = computed(() => [...columnsFor(main.value, lo.primary), PRICE_COL])
const placeholder = computed(() => `搜尋 ${[props.slotText, main.value ? lo.typeLabel([main.value]) : '配件'].filter(Boolean).join(' ')}…`)

const rows = computed(() => {
  const mf = new Set(mfrs.value)
  const base = props.items.filter(it => groups.value.every(g => !picked[g.key] || g.get(it) === picked[g.key])
    && (!mf.size || mf.has(mfrKey(it)))
    && (!acquire.value || (acquire.value === 'buy' ? it.buyable : !!it.blueprint)))
  return filterByName(base, query.value, it => [it.name, it.name_zh, it.manufacturer, it.manufacturer_name, it.class_name,
    manufacturerShort(it.manufacturer_name, it.manufacturer)]).rows
})

// 排序：數值欄第一次點由大到小（越大越好的居多），名稱由小到大；同一欄再點反過來
const sortKey = ref('')
const sortDir = ref('desc')
const sort = {
  sortKey, sortDir,
  toggle(field) {
    if (sortKey.value === field) sortDir.value = sortDir.value === 'desc' ? 'asc' : 'desc'
    else { sortKey.value = field; sortDir.value = field === 'name' ? 'asc' : 'desc' }
  },
}
const sorted = computed(() => {
  const key = sortKey.value
  const get = key === 'name' ? it => lo.itemLabel(it) : cols.value.find(c => c.key === key)?.get
  if (!get) return rows.value
  const sign = sortDir.value === 'desc' ? -1 : 1
  return [...rows.value].sort((a, b) => {
    const va = get(a); const vb = get(b)
    if (va == null && vb == null) return 0
    if (va == null) return 1             // 沒有數值的排最後
    if (vb == null) return -1
    return sign * compareValues(va, vb)
  })
})

// 每次打開：清掉搜尋、篩選，排序回到這種配件的主要數值
watch(() => [props.open, props.items], ([o]) => {
  if (!o) return
  query.value = ''
  mfrs.value = []
  acquire.value = ''
  for (const k of Object.keys(picked)) delete picked[k]
  sortKey.value = cols.value.find(c => c.first)?.key || 'name'
  sortDir.value = sortKey.value === 'name' ? 'asc' : 'desc'
}, { immediate: true })

// 換了「種類」篩選，欄位跟著換：排序回到新欄位的主要數值
watch(main, () => {
  if (sortKey.value === 'name' || cols.value.some(c => c.key === sortKey.value)) return
  sortKey.value = cols.value.find(c => c.first)?.key || 'name'
  sortDir.value = 'desc'
})

function subOf(it) {
  const kind = it.type === 'WeaponGun' ? weaponKindLabel(weaponKind(it))
    : it.type !== main.value ? lo.typeLabel([`${it.type}.${it.sub_type}`])
      : [it.grade, classLabel(it.item_class)].filter(Boolean).join(' ')
  const en = it.name_zh && it.name_zh !== it.name ? it.name : ''
  return [manufacturerShort(it.manufacturer_name, it.manufacturer), kind, en].filter(x => x && x !== '—').join(' · ')
}
function pick(it) {
  if (it.id === props.currentId) return
  emit('choose', it)
}
</script>

<style scoped>
/* ── 上方：大搜尋框＋分段篩選 ── */
.lpk-top { display: flex; flex-wrap: wrap; align-items: flex-end; gap: .75rem 1rem; margin-bottom: 1rem; }
.lpk-search { flex: 1 1 18rem; min-width: 14rem; }
.lpk-filter { flex: 0 1 auto; min-width: 0; }
.lpk-filter__label { display: block; font-size: var(--sf-fs-xs); font-weight: 700; letter-spacing: .08em; color: var(--sf-text-muted); margin-bottom: .3rem; }
.lpk-seg { display: inline-flex; flex-wrap: wrap; gap: .2rem; padding: .25rem; border-radius: .6rem;
  background: var(--sf-chip-bg); border: 1px solid var(--sf-border); }
.lpk-seg__btn { border: 0; background: none; padding: .3rem .75rem; border-radius: .45rem; font-size: var(--sf-fs-sm); font-weight: 600;
  color: var(--sf-text); white-space: nowrap; transition: background-color .15s, color .15s; }
.lpk-seg__btn:hover { color: var(--sf-text-strong); background: var(--sf-hover-bg); }
.lpk-seg__btn:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: 1px; }
.lpk-seg__btn.active { color: var(--sf-text-strong); background: rgba(var(--sf-accent-rgb), .28); }
.lpk-filter--mfr { flex: 0 1 14rem; min-width: 11rem; }
.lpk-filter--mfr :deep(.multi-select-filter__btn) { height: 2.45rem; }
.lpk-unequip { align-self: flex-end; margin-left: auto; }
.lpk-craft { color: var(--sf-accent-2); font-size: var(--sf-fs-sm); }

/* ── 表格 ── */
.lpk-table { --bs-table-bg: transparent; border-collapse: separate; border-spacing: 0 .4rem; }
.lpk-table thead th { font-size: var(--sf-fs-xs); font-weight: 700; letter-spacing: .06em; color: var(--sf-text-muted);
  border: 0; padding: .3rem .6rem; }
.lpk-table thead th.lpk-th--hot { color: var(--sf-accent-2); }
.lpk-row { cursor: pointer; }
.lpk-row td { background: var(--sf-chip-bg); border-top: 1px solid var(--sf-border); border-bottom: 1px solid var(--sf-border);
  padding: .6rem; transition: background-color .12s; }
.lpk-row td:first-child { border-left: 1px solid var(--sf-border); border-radius: .5rem 0 0 .5rem; }
.lpk-row td:last-child { border-right: 1px solid var(--sf-border); border-radius: 0 .5rem .5rem 0; }
.lpk-row:hover td { background: var(--sf-hover-bg); }
.lpk-row:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: -2px; }
.lpk-row--current td { background: rgba(var(--sf-accent-rgb), .14); border-color: rgba(var(--sf-accent-rgb), .6); cursor: default; }
.lpk-name { display: flex; align-items: center; gap: .75rem; min-width: 14rem; }
.lpk-size { flex: none; display: inline-flex; align-items: center; justify-content: center; width: 2.6rem; height: 2.6rem;
  border-radius: .5rem; font-weight: 800; font-size: var(--sf-fs-base); color: var(--sf-accent-2-ink, #0b1020); background: var(--sf-accent-2); }
.lpk-title { display: flex; flex-wrap: wrap; align-items: center; gap: .4rem; font-weight: 700; font-size: var(--sf-fs-base);
  color: var(--sf-text-strong); line-height: 1.3; }
.lpk-sub { font-size: var(--sf-fs-sm); color: var(--sf-text-muted); margin-top: .1rem; }
.lpk-dmg { font-size: var(--sf-fs-xs); font-weight: 700; letter-spacing: .04em; padding: .05rem .4rem; border-radius: .25rem;
  color: var(--sf-text); background: var(--sf-hover-bg); border: 1px solid var(--sf-border); }
.lpk-dmg--energy { color: #ffbf5e; border-color: rgba(255, 191, 94, .45); background: rgba(255, 191, 94, .12); }
.lpk-dmg--physical { color: #a9b8cc; }
.lpk-dmg--distortion { color: #7fc8ff; border-color: rgba(127, 200, 255, .45); background: rgba(127, 200, 255, .12); }
.lpk-using { font-size: var(--sf-fs-xs); font-weight: 700; padding: .05rem .45rem; border-radius: .25rem;
  color: var(--sf-accent-ink, #041018); background: var(--sf-accent); }
.lpk-table td.lpk-num { font-weight: 700; font-size: var(--sf-fs-base); color: var(--sf-text-strong); font-variant-numeric: tabular-nums; }
.lpk-table td.lpk-num--hot { color: rgb(var(--bs-success-rgb)); }
:root[data-sf-mode='light'] .lpk-dmg--energy { color: #9a5b00; }
:root[data-sf-mode='light'] .lpk-dmg--distortion { color: #0b5d9a; }
.min-w-0 { min-width: 0; }
@media (max-width: 575.98px) {
  .lpk-name { min-width: 0; }
  .lpk-unequip { margin-left: 0; }
}
</style>
