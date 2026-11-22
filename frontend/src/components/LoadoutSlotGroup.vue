<!--
  配裝模擬的一組槽位（components/LoadoutSimulator.vue）：同一層一模一樣的幾格合成一列顯示「N×」，
  換配件時整組一起換；子槽（砲塔上的武器、飛彈架上的飛彈）縮排列在下面，遞迴用自己。
  需要的函式由 LoadoutSimulator provide（'loadout'：itemOf、open、primary、secondary、itemLabel）。
  有子槽或數值列的可以摺疊（左邊的箭頭）；卡片窄的時候（容器查詢，見 LoadoutSimulator 的 .lo-sec）按鈕只留圖示、
  縮排變小、名稱可以換兩行，避免擠在一起。
-->
<template>
  <!-- 分開設定：同樣的幾格拆成一格一列，各自更換（換成不同配件後本來就會分開；換回一樣的會再合併） -->
  <div v-if="split && nodes.length > 1" class="lo-split">
    <div class="lo-split__head" :class="{ 'lo-split__head--child': depth > 0 }">
      <span>{{ nodes.length }} 格分開設定</span>
      <button type="button" class="lo-acq__btn ms-auto" @click="split = false"><i class="bi bi-arrows-collapse me-1"></i>合併</button>
    </div>
    <LoadoutSlotGroup v-for="n in nodes" :key="n.id" :nodes="[n]" :depth="depth" />
  </div>
  <div v-else class="lo-group" :class="{ 'lo-group--child': depth > 0 }">
    <div class="lo-row" :class="{ 'lo-row--empty': !first.item }">
      <button v-if="foldable" type="button" class="lo-fold" :aria-expanded="open ? 'true' : 'false'"
        :aria-label="open ? `收起 ${name}` : `展開 ${name}`" @click="open = !open">
        <i class="bi" :class="open ? 'bi-chevron-down' : 'bi-chevron-right'"></i></button>
      <span v-else class="lo-fold lo-fold--none" aria-hidden="true"></span>
      <span class="lo-size" :title="`尺寸 ${sizeText}`">S{{ sizeText }}</span>
      <span v-if="nodes.length > 1" class="lo-count">{{ nodes.length }}×</span>
      <button v-if="nodes.length > 1 && first.editable" type="button" class="lo-splitbtn" :aria-label="`${name} 分開設定`"
        title="分開設定（每一格各自更換）" @click="split = true"><i class="bi bi-distribute-vertical"></i></button>
      <div class="flex-grow-1 min-w-0">
        <div class="lo-name" :title="title">{{ name }}</div>
        <div class="lo-meta text-truncate">{{ meta }}</div>
      </div>
      <div v-if="item && lo.primary(item)" class="lo-stat text-end">
        <div class="lo-stat__value">{{ lo.primary(item).text }}</div>
        <div class="lo-stat__label">{{ lo.primary(item).label }}</div>
      </div>
      <button v-if="first.editable" type="button" class="btn btn-sm btn-primary text-nowrap"
        :aria-label="`更換 ${name}`" @click="lo.open(nodes)"><i class="bi bi-arrow-left-right"></i><span class="lo-btn-text ms-1">更換</span></button>
      <span v-else class="lo-lock" title="這一格不能更換" aria-label="不能更換"><i class="bi bi-lock-fill"></i></span>
    </div>
    <template v-if="open">
      <!-- 取得方式：價格（點開購買地點）、可製作＋品質（點開調品質）／不可製作固定 Q500、加入購物車 -->
      <div v-if="item" class="lo-acq">
        <button v-if="item.buyable" type="button" class="lo-acq__btn lo-acq__btn--buy" @click="lo.openInfo(item, 'buy')">
          <i class="bi bi-cart3 me-1"></i>{{ fmtAuec(item.price) }}</button>
        <button v-if="item.blueprint" type="button" class="lo-acq__btn lo-acq__btn--craft" @click="lo.openInfo(item, 'quality')">
          <i class="bi bi-hammer me-1"></i>可製作 Q{{ lo.avgOf(item) }}</button>
        <span v-else class="lo-acq__lock" title="不可製作，固定 Q500"><i class="bi bi-lock-fill me-1"></i>Q500</span>
        <button v-if="!item.buyable && !item.blueprint" type="button" class="lo-acq__btn" @click="lo.openInfo(item, 'buy')">
          <i class="bi bi-info-circle me-1"></i>取得</button>
        <button type="button" class="lo-acq__btn lo-acq__btn--cart" :aria-label="`${name} 加入購物車`" @click="lo.addCart(item, nodes.length)">
          <i class="bi bi-cart-plus"></i><span class="lo-btn-text ms-1">加入</span><template v-if="nodes.length > 1"> ×{{ nodes.length }}</template></button>
      </div>
      <div v-if="subStats.length" class="lo-sub">
        <span v-for="s in subStats" :key="s.label" class="lo-kv"><span>{{ s.label }}</span>{{ s.text }}</span>
      </div>
      <LoadoutSlotGroup v-for="(g, i) in groups" :key="`${g[0].id}-${i}`" :nodes="g" :depth="depth + 1" />
    </template>
  </div>
</template>

<script setup>
import { computed, inject, ref } from 'vue'
import { childGroups } from '@/utils/loadoutCalc'
import { fmtAuec } from '@/utils/uexCommodity'

const props = defineProps({
  nodes: { type: Array, required: true },
  depth: { type: Number, default: 0 },
})
const lo = inject('loadout')
const first = computed(() => props.nodes[0])
const item = computed(() => lo.itemOf(first.value.item))
const groups = computed(() => childGroups(props.nodes, lo.itemOf))
// 摺疊：有子槽或數值列才有箭頭（整區摺疊在 LoadoutSimulator 的區塊標題）
const open = ref(true)
const split = ref(false)
const sizeText = computed(() => {
  const n = first.value
  if (item.value?.size != null) return item.value.size
  return n.min === n.max || !n.max ? n.min : `${n.min}–${n.max}`
})
const name = computed(() => (item.value ? lo.itemLabel(item.value)
  : first.value.item ? first.value.name || lo.typeLabel(first.value.types) : '（空）'))
const title = computed(() => (item.value ? `${item.value.name}（${item.value.class_name}）`
  : [name.value, first.value.item_class_name].filter(Boolean).join('（') + (first.value.item_class_name ? '）' : '')))
// 列表只放前幾個數值（訊號、耗電這些在更換視窗看）
const subStats = computed(() => (item.value ? lo.secondary(item.value).filter(s => !['EM', 'IR 訊號', '耗電'].includes(s.label)).slice(0, 6) : []))
const foldable = computed(() => groups.value.length > 0 || subStats.value.length > 0 || !!item.value)
const meta = computed(() => {
  const it = item.value
  if (!it) return lo.typeLabel(first.value.types)
  return [lo.typeLabel([`${it.type}.${it.sub_type}`]), it.name_zh && it.name_zh !== it.name ? it.name : '',
    it.manufacturer, [it.grade, lo.classLabel(it.item_class)].filter(Boolean).join(' ')].filter(Boolean).join(' · ')
})
</script>

<style scoped>
.lo-group--child { margin-left: .85rem; padding-left: .6rem; border-left: 2px solid var(--sf-border); }
.lo-fold { flex: none; width: 1.5rem; height: 1.5rem; display: inline-flex; align-items: center; justify-content: center; padding: 0;
  border: 0; border-radius: .3rem; background: none; color: var(--sf-text-muted); }
.lo-fold:hover { color: var(--sf-text-strong); background: var(--sf-hover-bg); }
.lo-fold:focus-visible { outline: 2px solid var(--sf-accent); }
.lo-fold--none { pointer-events: none; }
.lo-row { display: flex; align-items: center; gap: .5rem; padding: .45rem .55rem; margin-top: .4rem;
  border: 1px solid var(--sf-border); border-radius: .4rem; background: var(--sf-chip-bg); }
.lo-row--empty { opacity: .7; border-style: dashed; }
.lo-size { flex: none; min-width: 2.4rem; text-align: center; font-weight: 700; padding: .1rem .35rem; border-radius: .3rem;
  color: var(--sf-text-strong); background: rgba(var(--sf-accent-rgb), .25); border: 1px solid rgba(var(--sf-accent-rgb), .7); }
.lo-count { flex: none; font-weight: 700; color: var(--sf-accent-2); }
.lo-name { font-weight: 600; color: var(--sf-text-strong); line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.lo-meta { font-size: var(--sf-fs-sm); color: var(--sf-text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lo-stat { flex: none; line-height: 1.1; }
.lo-stat__value { font-weight: 700; font-size: var(--sf-fs-md); color: var(--sf-accent); }
.lo-stat__label { font-size: var(--sf-fs-xs); color: var(--sf-text-muted); }
.lo-lock { flex: none; width: 2rem; text-align: center; color: var(--sf-text-muted); }
.lo-splitbtn { flex: none; width: 1.6rem; height: 1.6rem; padding: 0; border-radius: .3rem; border: 1px solid var(--sf-border);
  background: var(--sf-chip-bg); color: var(--sf-text); display: inline-flex; align-items: center; justify-content: center; }
.lo-splitbtn:hover { border-color: var(--sf-accent); color: var(--sf-text-strong); }
.lo-split__head { display: flex; align-items: center; gap: .5rem; margin-top: .5rem; font-size: var(--sf-fs-xs); font-weight: 700;
  color: var(--sf-text-muted); }
.lo-split__head--child { margin-left: .85rem; padding-left: .6rem; }
.lo-acq { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem; padding: .35rem .6rem 0 4.6rem; }
.lo-acq__btn { display: inline-flex; align-items: center; padding: .1rem .5rem; border-radius: .3rem; font-size: var(--sf-fs-xs); font-weight: 700;
  color: var(--sf-text); background: var(--sf-chip-bg); border: 1px solid var(--sf-border); }
.lo-acq__btn:hover { border-color: var(--sf-accent); color: var(--sf-text-strong); }
.lo-acq__btn--buy { color: rgb(var(--bs-success-rgb)); border-color: rgba(var(--bs-success-rgb), .5); }
.lo-acq__btn--craft { color: var(--sf-accent-2); border-color: rgba(var(--sf-accent-2-rgb), .55); }
.lo-acq__btn--cart { margin-left: auto; }
.lo-acq__lock { font-size: var(--sf-fs-xs); font-weight: 700; color: var(--sf-text-muted); }
.lo-sub { display: flex; flex-wrap: wrap; gap: .2rem .9rem; padding: .3rem .6rem 0 4.6rem; font-size: var(--sf-fs-sm); color: var(--sf-text); }
.lo-kv span { color: var(--sf-text-muted); margin-right: .3rem; }
.min-w-0 { min-width: 0; }
/* 卡片窄（容器查詢，容器是 LoadoutSimulator 的 .lo-sec）：按鈕只留圖示、縮排變小、數值列不縮排 */
@container lo-sec (max-width: 34rem) {
  .lo-btn-text { display: none; }
  .lo-group--child { margin-left: .4rem; padding-left: .45rem; }
  .lo-row { gap: .4rem; padding: .4rem .45rem; }
  .lo-size { min-width: 2.1rem; }
  .lo-stat__value { font-size: var(--sf-fs-base); }
  .lo-sub { padding-left: 2rem; gap: .15rem .7rem; }
  .lo-acq { padding-left: 2rem; }
}
@container lo-sec (max-width: 24rem) {
  .lo-stat__label { display: none; }
  .lo-sub { padding-left: .5rem; }
  .lo-acq { padding-left: .5rem; }
}
</style>
