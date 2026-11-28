<!--
  航段表「貨物」視窗的內容（RouteLegsTable.vue 開啟貨物規劃時，每一站一個按鈕）：
  這一站要裝／卸哪些貨物、各幾 SCU、最大貨櫃多大（合約常限制 16／8 SCU），每一筆自動拆成貨櫃（utils/crateCombos.js 的 splitCrates）。
  simple（航線規劃表單，還沒排順序）時只填裝卸，不算艙內。
  上面列抵達時貨艙裡有什麼，下面是離開時的貨艙用量（超過容量、卸的比艙內多會標出來）。
  v-model:entries＝[{ key, action: 'load'|'unload', item, scu, max }]；改了就發（上層存起來）。
-->
<template>
  <div>
    <div v-if="!simple" class="d-flex flex-wrap align-items-center gap-2 mb-2">
      <span class="small fw-semibold">抵達時艙內</span>
      <span v-if="!arrivingList.length" class="text-muted small">空的</span>
      <span v-for="a in arrivingList" :key="a.item" class="sf-chip mb-0">{{ a.item }} {{ fmt(a.scu) }} SCU</span>
      <span class="sf-chip sf-chip--accent mb-0 ms-auto">
        {{ fmt(arrivingTotal) }}{{ capacity ? ` / ${fmt(capacity)}` : '' }} SCU</span>
    </div>

    <div v-for="(e, i) in list" :key="e.key" class="scg-row mb-2">
      <div class="row g-2 align-items-end">
        <div class="col-6 col-md-2">
          <span class="form-label small mb-1 d-block">動作</span>
          <SfChoice :id="`${id}-act-${e.key}`" v-model="e.action" required :label="`第 ${i + 1} 筆動作`"
            :options="[{ value: 'load', label: '裝貨' }, { value: 'unload', label: '卸貨' }]" />
        </div>
        <div class="col-6 col-md-4">
          <label class="form-label small mb-1" :for="`${id}-item-${e.key}`">貨物<span class="text-muted ms-1">（選填）</span></label>
          <!-- 自動完成：這條航線填過的／艙內的貨物排前面，再來是商品資料庫（GET /starmap/nav/commodities）；也可以直接打字 -->
          <AutocompleteField :id="`${id}-item-${e.key}`" v-model="e.item" :search="searchItems" :get-label="itemLabel"
            :get-meta="itemMeta" :min-chars="0" :debounce-ms="0" placeholder="例如 Agricium" :aria-label="`第 ${i + 1} 筆貨物`" />
        </div>
        <div class="col-6 col-md-2">
          <label class="form-label small mb-1" :for="`${id}-scu-${e.key}`">SCU</label>
          <input :id="`${id}-scu-${e.key}`" v-model.number="e.scu" type="number" min="0" step="1" inputmode="numeric"
            class="form-control form-control-sm">
        </div>
        <div class="col-4 col-md-2">
          <label class="form-label small mb-1" :for="`${id}-max-${e.key}`">最大貨櫃</label>
          <select :id="`${id}-max-${e.key}`" v-model.number="e.max" class="form-select form-select-sm">
            <option v-for="s in SIZES_DESC" :key="s" :value="s">{{ s }} SCU</option>
          </select>
        </div>
        <div class="col-2 col-md-2 d-flex justify-content-end">
          <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除第 ${i + 1} 筆`" @click="list.splice(i, 1)">
            <i class="bi bi-trash"></i></button>
        </div>
      </div>
      <div v-if="e.scu > 0" class="d-flex flex-wrap align-items-center gap-1 mt-1 small">
        <span class="text-muted">貨櫃</span>
        <span v-for="[s, c] in cratesOf(e)" :key="s" class="sf-chip mb-0"
          :class="e.action === 'load' ? 'sf-chip--accent' : 'sf-chip--ok'">{{ s }} SCU × {{ c }}</span>
        <span class="text-muted">共 {{ crateCount(e) }} 個</span>
        <span v-if="!simple && e.action === 'unload' && shortOf(e)" class="sf-chip sf-chip--warn mb-0">
          艙內只有 {{ fmt(onboardBefore(e)) }} SCU</span>
      </div>
    </div>

    <div class="d-flex flex-wrap gap-2 mt-2">
      <button type="button" class="btn btn-sm btn-success" @click="add('load')"><i class="bi bi-box-arrow-in-down me-1"></i>加裝貨</button>
      <button type="button" class="btn btn-sm btn-success" @click="add('unload')"><i class="bi bi-box-arrow-up me-1"></i>加卸貨</button>
      <button v-if="!simple && arrivingList.length" type="button" class="btn btn-sm btn-primary" @click="unloadAll">
        <i class="bi bi-boxes me-1"></i>全部卸下</button>
    </div>

    <div v-if="simple" class="small text-muted mt-2">規劃後在航線結果的航段表會帶入這些貨物，並算出每站的貨艙用量，可以再調整。</div>
    <div v-if="!simple" class="scg-after mt-3">
      <span class="small fw-semibold">離開時艙內</span>
      <span v-if="!leavingList.length" class="text-muted small">空的</span>
      <span v-for="a in leavingList" :key="a.item" class="sf-chip mb-0">{{ a.item }} {{ fmt(a.scu) }} SCU</span>
      <span class="sf-chip mb-0 ms-auto" :class="over ? 'sf-chip--warn' : 'sf-chip--accent'">
        {{ fmt(leavingTotal) }}{{ capacity ? ` / ${fmt(capacity)}` : '' }} SCU{{ over ? `（超過 ${fmt(leavingTotal - capacity)}）` : '' }}</span>
    </div>
    <div v-if="!simple && capacity" class="progress mt-1" style="height: .5rem" role="progressbar" :aria-valuenow="leavingTotal"
      aria-valuemin="0" :aria-valuemax="capacity" aria-label="離開時貨艙用量">
      <div class="progress-bar" :class="over ? 'bg-danger' : ''" :style="{ width: `${Math.min(100, leavingTotal / capacity * 100)}%` }"></div>
    </div>
  </div>
</template>

<script setup>
import SfChoice from '@/components/SfChoice.vue'
import { computed, reactive, watch } from 'vue'
import AutocompleteField from '@/components/AutocompleteField.vue'
import { splitCrates } from '@/utils/crateCombos'
import { SIZES } from '@/utils/cargoPack'
import { applyCargo, newCargoEntry } from '@/utils/stopCargo'

const props = defineProps({
  id: { type: String, required: true },
  entries: { type: Array, default: () => [] },
  /** 抵達時艙內 { 貨物: SCU } */
  arriving: { type: Object, default: () => ({}) },
  capacity: { type: Number, default: 0 },
  /** 貨物名稱建議（整條航線填過的） */
  items: { type: Array, default: () => [] },
  /** 商品資料庫（GET /starmap/nav/commodities：{ name, name_zh, code }），貨物名稱自動完成用 */
  commodities: { type: Array, default: () => [] },
  /** 表單用（還沒排順序）：不顯示抵達／離開時艙內 */
  simple: { type: Boolean, default: false },
})
const emit = defineEmits(['update:entries'])

const SIZES_DESC = [...SIZES].sort((a, b) => b - a)
const fmt = v => Math.round(Number(v) || 0).toLocaleString('en-US')

const list = reactive(props.entries.map(e => ({ ...e })))
watch(list, () => emit('update:entries', list.map(e => ({ ...e }))), { deep: true })

function add(action, item = '', scu = null) {
  const last = list[list.length - 1]
  list.push(newCargoEntry({ action, item, scu, max: last?.max }))
}
function unloadAll() {
  for (const a of arrivingList.value) {
    const done = list.some(e => e.action === 'unload' && e.item.toLowerCase() === a.item.toLowerCase())
    if (!done) add('unload', a.item, a.scu)
  }
}

const listOf = obj => Object.entries(obj).filter(([, v]) => v > 1e-9).map(([item, scu]) => ({ item, scu }))
const arrivingList = computed(() => listOf(props.arriving))
const arrivingTotal = computed(() => arrivingList.value.reduce((n, a) => n + a.scu, 0))
const leaving = computed(() => applyCargo(props.arriving, list))
const leavingList = computed(() => listOf(leaving.value.onboard))
const leavingTotal = computed(() => leavingList.value.reduce((n, a) => n + a.scu, 0))
const over = computed(() => props.capacity > 0 && leavingTotal.value > props.capacity + 1e-9)

const cratesOf = e => Object.entries(splitCrates(e.scu, e.max)).sort((a, b) => b[0] - a[0])
const crateCount = e => Object.values(splitCrates(e.scu, e.max)).reduce((n, c) => n + c, 0)
// 卸貨時艙內這種貨物有多少（同一站前面幾筆裝卸也算）
function onboardBefore(e) {
  const i = list.indexOf(e)
  return applyCargo(props.arriving, list.slice(0, i)).onboard[leaving.value.nameOf(e.item)] || 0
}
const shortOf = e => (Number(e.scu) || 0) > onboardBefore(e) + 1e-9

const suggestions = computed(() => [...new Set([...arrivingList.value.map(a => a.item), ...props.items])].filter(Boolean))
// 貨物名稱自動完成：常用的（這條航線用過、艙內有的）在前，商品資料庫在後；選了就填「中文（英文）」
const commodityLabel = c => (c.name_zh && c.name_zh !== c.name ? `${c.name_zh}（${c.name}）` : c.name)
const itemLabel = c => (c.recent ? c.name : commodityLabel(c))
const itemMeta = c => (c.recent ? '用過' : c.code || '')
async function searchItems(q) {
  const t = (q || '').trim().toLowerCase()
  // 正在打的字本身（也算在「用過」裡）不列
  const recent = suggestions.value.filter(n => (!t || n.toLowerCase().includes(t)) && n.toLowerCase() !== t)
    .map(name => ({ name, recent: true }))
  const used = new Set(recent.map(r => r.name.toLowerCase()))
  const rows = props.commodities.filter(c => (!t || c.name.toLowerCase().includes(t)
    || (c.name_zh || '').toLowerCase().includes(t) || (c.code || '').toLowerCase() === t)
    && !used.has(commodityLabel(c).toLowerCase()))
  return [...recent, ...rows].slice(0, 50)
}
</script>

<style scoped>
.scg-row { border: 1px solid var(--sf-border); border-radius: .5rem; padding: .5rem .75rem; }
.scg-after { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem .5rem; }
</style>
