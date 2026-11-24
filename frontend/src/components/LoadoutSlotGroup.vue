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
  <div v-else class="lo-group" :class="{ 'lo-group--child': depth > 0, 'lo-pair': pair }">
    <div class="lo-pair__main">
    <div class="lo-row" :class="{ 'lo-row--empty': !first.item, 'lo-row--craft': item?.blueprint, 'lo-row--off': isGun && off }">
      <button v-if="foldable" type="button" class="lo-fold" :aria-expanded="open ? 'true' : 'false'"
        :aria-label="open ? `收起 ${name}` : `展開 ${name}`" @click="open = !open">
        <i class="bi" :class="open ? 'bi-chevron-down' : 'bi-chevron-right'"></i></button>
      <span v-else class="lo-fold lo-fold--none" aria-hidden="true"></span>
      <!-- 可製作的配件：左側品質把手，點上下每個部位各 ±50，按住連續調整 -->
      <div v-if="item?.blueprint" class="lo-qh" role="group" :aria-label="`${name} 品質`">
        <button type="button" class="lo-qh__btn" :aria-label="`${name} 品質加 ${STEP}`" :disabled="lo.avgOf(item) >= 1000"
          @pointerdown="hold(STEP)" @pointerup="release" @pointerleave="release" @pointercancel="release"
          @keydown.enter.prevent="nudge(STEP)" @keydown.space.prevent="nudge(STEP)"><i class="bi bi-chevron-double-up"></i></button>
        <span class="lo-qh__v">{{ lo.avgOf(item) }}</span>
        <button type="button" class="lo-qh__btn" :aria-label="`${name} 品質減 ${STEP}`" :disabled="lo.avgOf(item) <= 0"
          @pointerdown="hold(-STEP)" @pointerup="release" @pointerleave="release" @pointercancel="release"
          @keydown.enter.prevent="nudge(-STEP)" @keydown.space.prevent="nudge(-STEP)"><i class="bi bi-chevron-double-down"></i></button>
      </div>
      <span class="lo-size" :title="`尺寸 ${sizeText}`">S{{ sizeText }}</span>
      <span v-if="nodes.length > 1" class="lo-count">{{ nodes.length }}×</span>
      <button v-if="nodes.length > 1 && first.editable" type="button" class="lo-splitbtn" :aria-label="`${name} 分開設定`"
        title="分開設定（每一格各自更換）" @click="split = true"><i class="bi bi-distribute-vertical"></i></button>
      <div class="flex-grow-1 min-w-0">
        <div class="lo-name" :title="title">{{ name }}<button v-if="item?.buyable" type="button" class="lo-where"
          title="購買地點" :aria-label="`${name} 購買地點`" @click="lo.openInfo(item, 'buy')"><i class="bi bi-cart3"></i></button></div>
        <div class="lo-meta text-truncate">{{ meta }}</div>
      </div>
      <div v-if="item && lo.primary(item)" class="lo-stat text-end">
        <div class="lo-stat__value">{{ lo.primary(item).text }}</div>
        <div class="lo-stat__label">{{ lo.primary(item).label }}<template v-if="isGun && item.stats?.dps"> · 爆發 {{ fmtNum(item.stats.dps) }}</template></div>
      </div>
      <!-- 武器：單格開關電源（關掉的不耗電、不算傷害） -->
      <button v-if="isGun" type="button" class="lo-pwr" :class="{ on: !off }" :aria-pressed="off ? 'false' : 'true'"
        :aria-label="`${name} 電源`" :title="off ? '電源關閉' : '電源開啟'" @click="lo.toggleWeaponPower(nodes)">
        <i class="bi bi-power"></i></button>
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
      <!-- 武器：效率（電源分配）、彈速、射程長條（長條以這艘船裝的武器裡最大的當滿格） -->
      <div v-if="isGun" class="lo-gun">
        <div class="lo-bar" :title="`武器電源效率 ${effPct}%`">
          <span class="lo-bar__l">效率</span>
          <span class="lo-bar__track" role="meter" :aria-valuenow="effPct" aria-valuemin="0" aria-valuemax="100" :aria-label="`${name} 效率`">
            <span class="lo-bar__fill" :class="{ 'lo-bar__fill--low': effPct < 100 }" :style="{ width: `${effPct}%` }"></span></span>
          <span class="lo-bar__v">{{ effPct }}%</span>
        </div>
        <div v-for="b in gunBars" :key="b.key" class="lo-bar">
          <span class="lo-bar__l">{{ b.label }}</span>
          <span class="lo-bar__track" aria-hidden="true"><span class="lo-bar__fill lo-bar__fill--alt" :style="{ width: `${b.pct}%` }"></span></span>
          <span class="lo-bar__v">{{ b.text }}</span>
        </div>
      </div>
      <div v-if="subStats.length" class="lo-sub">
        <span v-for="s in subStats" :key="s.label" class="lo-kv"><span>{{ s.label }}</span>{{ s.text }}</span>
      </div>
    </template>
    </div>
    <!-- 子槽（雲台上的武器、飛彈架上的飛彈）；雲台＋武器在寬卡片上排成左右兩欄，中間連線 -->
    <div v-if="open && groups.length" class="lo-pair__kids">
      <LoadoutSlotGroup v-for="(g, i) in groups" :key="`${g[0].id}-${i}`" :nodes="g" :depth="depth + 1" />
    </div>
  </div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, ref } from 'vue'
import { childGroups } from '@/utils/loadoutCalc'
import { fmtAuec } from '@/utils/uexCommodity'
import { fmtNum } from '@/utils/navFormat'

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
const subStats = computed(() => (item.value ? lo.secondary(item.value)
  .filter(s => !['EM', 'IR 訊號', '耗電', ...(isGun.value ? ['射程', '彈速'] : [])].includes(s.label)).slice(0, 6) : []))
const foldable = computed(() => groups.value.length > 0 || subStats.value.length > 0 || !!item.value)
// ── 武器 ──
const isGun = computed(() => item.value?.type === 'WeaponGun')
const off = computed(() => isGun.value && lo.isWeaponOff(props.nodes))
const effPct = computed(() => (off.value ? 0 : Math.round(lo.weaponEff() * 100)))
const gunBars = computed(() => {
  const s = item.value?.stats || {}
  const scale = lo.weaponScale()
  const bar = (key, label, v, max, unit) => (v ? { key, label, pct: max ? Math.round((v / max) * 100) : 0, text: `${fmtNum(v)} ${unit}` } : null)
  return [bar('speed', '彈速', s.speed, scale.speed, 'm/s'), bar('range', '射程', s.range, scale.range, 'm')].filter(Boolean)
})
// 雲台／砲塔底下全是武器：寬卡片排成左右兩欄
const pair = computed(() => groups.value.length > 0 && ['Turret', 'TurretBase'].includes(item.value?.type)
  && groups.value.every(g => lo.itemOf(g[0].item)?.type === 'WeaponGun'))
// 品質把手：按一下 ±STEP；按住 400ms 後每 120ms 再調一次
const STEP = 50
const nudge = d => lo.nudgeQuality(item.value, d)
let holdTimer = null
function hold(d) {
  release()
  nudge(d)
  holdTimer = setTimeout(function again() { nudge(d); holdTimer = setTimeout(again, 120) }, 400)
}
function release() { clearTimeout(holdTimer); holdTimer = null }
onBeforeUnmount(release)
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
.lo-row--off { opacity: .55; }
.lo-pwr { flex: none; width: 2rem; height: 2rem; border-radius: 50%; padding: 0; border: 1px solid var(--sf-border);
  background: var(--sf-chip-bg); color: var(--sf-text-muted); display: inline-flex; align-items: center; justify-content: center; }
.lo-pwr.on { color: rgb(var(--bs-success-rgb)); border-color: rgba(var(--bs-success-rgb), .6); }
.lo-pwr:hover { color: var(--sf-text-strong); }
.lo-gun { display: grid; grid-template-columns: repeat(auto-fit, minmax(11rem, 1fr)); gap: .2rem 1rem; padding: .35rem .6rem 0 4.6rem; }
.lo-bar { display: flex; align-items: center; gap: .45rem; font-size: var(--sf-fs-xs); }
.lo-bar__l { flex: none; width: 2.2rem; color: var(--sf-text-muted); font-weight: 700; }
.lo-bar__track { flex: 1 1 auto; height: .35rem; border-radius: 999px; background: var(--sf-border); overflow: hidden; min-width: 3rem; }
.lo-bar__fill { display: block; height: 100%; border-radius: inherit; background: rgb(var(--bs-success-rgb)); }
.lo-bar__fill--low { background: var(--sf-accent-2); }
.lo-bar__fill--alt { background: var(--sf-accent); }
.lo-bar__v { flex: none; min-width: 4.5rem; text-align: right; color: var(--sf-text); font-variant-numeric: tabular-nums; }
/* 雲台＋武器：寬卡片左右兩欄，中間一條連線 */
@container lo-sec (min-width: 40rem) {
  .lo-pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.35fr); gap: 0 1.4rem; align-items: start; }
  .lo-pair > .lo-pair__kids { position: relative; }
  .lo-pair > .lo-pair__kids::before { content: ''; position: absolute; left: -1.4rem; top: 1.55rem; width: 1.4rem; border-top: 2px solid var(--sf-accent); }
  .lo-pair > .lo-pair__kids > .lo-group--child { margin-left: 0; padding-left: 0; border-left: 0; }
  .lo-pair > .lo-pair__kids > .lo-group--child + .lo-group--child { margin-top: .2rem; }
  .lo-pair .lo-acq, .lo-pair .lo-sub, .lo-pair .lo-gun { padding-left: .6rem; }
}
.lo-row--craft { border-color: rgba(var(--sf-accent-2-rgb), .6); }
.lo-qh { flex: none; display: flex; flex-direction: column; align-items: center; align-self: stretch; justify-content: center;
  width: 2rem; margin: -.2rem 0; border-radius: .3rem; background: rgba(var(--sf-accent-2-rgb), .12); }
.lo-qh__btn { border: 0; background: none; padding: 0; width: 100%; line-height: 1; color: var(--sf-accent-2); font-size: var(--sf-fs-xs); touch-action: none; }
.lo-qh__btn:hover:not(:disabled) { color: var(--sf-text-strong); }
.lo-qh__btn:disabled { opacity: .35; }
.lo-qh__v { font-size: var(--sf-fs-xs); font-weight: 800; color: var(--sf-text-strong); font-variant-numeric: tabular-nums; }
.lo-size { flex: none; min-width: 2.4rem; text-align: center; font-weight: 700; padding: .1rem .35rem; border-radius: .3rem;
  color: var(--sf-text-strong); background: rgba(var(--sf-accent-rgb), .25); border: 1px solid rgba(var(--sf-accent-rgb), .7); }
.lo-count { flex: none; font-weight: 700; color: var(--sf-accent-2); }
.lo-name { font-weight: 600; color: var(--sf-text-strong); line-height: 1.3;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.lo-where { border: 0; background: none; padding: 0 .2rem; margin-left: .3rem; color: rgb(var(--bs-success-rgb)); font-size: var(--sf-fs-sm);
  vertical-align: baseline; }
.lo-where:hover { color: var(--sf-text-strong); }
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
  .lo-gun { padding-left: 2rem; }
}
@container lo-sec (max-width: 24rem) {
  .lo-stat__label { display: none; }
  .lo-sub { padding-left: .5rem; }
  .lo-acq { padding-left: .5rem; }
  .lo-gun { padding-left: .5rem; }
}
</style>
