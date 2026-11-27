<!--
  艦船資料列上的「船價」按鈕＋跳出視窗（資料庫 › 艦船用）：RSI 商店的美金價（真錢贊助價，不是遊戲內 aUEC）與上架紀錄。

  有船價資料（utils/shipPrices.js 共用一份，GET /item/ship-prices）的船才出現按鈕；
  按了跳出視窗才抓這艘船的每段上架期間（GET /item/ship-prices/detail?key=）。
  來源是 RSI 官方商店（排程「CCU」，官方確認）＋ Open Hangar（排程「Open Hangar 歷史」，2021-11 起的歷史紀錄，
  CC BY 4.0，所以視窗底下要標註來源）。同種類的期間兩邊重疊時後端只留 RSI 的。見 src/models/ccu.py。

  時間軸：每種販售方式一條（單買／Warbond／其他），橫軸是時間；滑到或聚焦某一段，下面那行顯示它的期間與價格。
  同樣的資料在時間軸下面的表格也有（來源、可信度只在表格）。
-->
<template>
  <button v-if="summary" type="button" class="btn btn-sm btn-info" :class="buttonClass"
    :aria-label="`${name} 的船價`" aria-haspopup="dialog" @click="show">
    <i class="bi bi-currency-dollar me-1"></i>船價</button>
  <Teleport v-if="summary" to="body">
    <div class="scifi-page spb-host">
      <SfModal :id="uid" v-model:open="open" :title="`${name} 船價`" icon="bi bi-currency-dollar" width="1000px">
        <template v-if="open">
          <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
            <span v-if="summary.warbond_now" class="sf-chip sf-chip--accent mb-0"><i class="bi bi-lightning-charge me-1"></i>Warbond 販售中</span>
            <span v-else-if="summary.on_sale" class="sf-chip sf-chip--ok mb-0"><i class="bi bi-check-lg me-1"></i>販售中</span>
            <span v-else class="sf-chip mb-0">未販售</span>
            <span class="sf-chip mb-0">標準價 {{ usd(summary.msrp) }}</span>
            <span v-if="summary.price_now != null" class="sf-chip mb-0">現價 {{ usd(summary.price_now) }}</span>
            <span v-if="summary.last_warbond" class="sf-chip mb-0">上次 Warbond {{ usd(summary.last_warbond.price) }}
              <span class="sf-chip__state">{{ summary.last_warbond.end ? day(summary.last_warbond.end) : '進行中' }}</span></span>
            <span v-if="summary.avail" class="sf-chip mb-0">{{ availLabel(summary.avail) }}</span>
          </div>
          <SfState :loading="loading" :error="error" :empty="!!detail && !detail.periods.length"
            empty-text="沒有上架紀錄。" @retry="load">
            <template v-if="detail">
          <!-- 時間軸 -->
          <div class="spb-tl" role="group" :aria-label="`${name} 上架時間軸`" @mouseleave="hover = null; note = ''">
            <div v-for="lane in lanes" :key="lane.key" class="spb-tl__lane">
              <div class="spb-tl__label">{{ lane.label }}</div>
              <div class="spb-tl__track">
                <button v-for="(p, i) in lane.periods" :key="i" type="button"
                  class="spb-tl__seg" :class="[`spb-tl__seg--${lane.key}`, { 'is-open': !p.end, 'is-active': hover === p }]"
                  :style="segStyle(p)" :aria-label="describe(p)"
                  @mouseenter="hover = p" @focus="hover = p" @blur="hover = null"></button>
              </div>
            </div>
            <!-- 價格走勢：每段上架畫在它的價格高度上，同一種販售方式用階梯線連起來（看漲價與 Warbond 價差） -->
            <div class="spb-tl__title">價格（美金）</div>
            <div class="spb-tl__lane spb-tl__lane--chart">
              <div class="spb-tl__label spb-tl__label--y">
                <span v-for="t in priceTicks" :key="t.v" class="spb-tl__ytick" :style="{ bottom: t.bottom + '%' }">{{ usd(t.v) }}</span>
              </div>
              <div class="spb-tl__track spb-tl__track--price">
                <span v-for="t in priceTicks" :key="t.v" class="spb-tl__grid" :style="{ bottom: t.bottom + '%' }"></span>
                <svg class="spb-tl__lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                  <polyline v-for="l in priceLines" :key="l.key" :points="l.points" :class="`spb-tl__line--${l.key}`" />
                </svg>
                <template v-for="lane in lanes" :key="lane.key">
                  <button v-for="(p, i) in lane.periods.filter(x => x.price != null)" :key="lane.key + i" type="button"
                    class="spb-tl__seg spb-tl__seg--price" :class="[`spb-tl__seg--${lane.key}`, { 'is-active': hover === p }]"
                    :style="priceStyle(p)" :aria-label="describe(p)"
                    @mouseenter="hover = p" @focus="hover = p" @blur="hover = null"></button>
                </template>
              </div>
            </div>
            <!-- 每年上架天數：一年一組，跟上面的年份對齊 -->
            <div class="spb-tl__title">每年上架天數</div>
            <div class="spb-tl__lane spb-tl__lane--chart">
              <div class="spb-tl__label spb-tl__label--y">
                <span class="spb-tl__ytick" style="bottom: 100%">{{ dayMax }} 天</span>
                <span class="spb-tl__ytick" style="bottom: 0">0</span>
              </div>
              <div class="spb-tl__track spb-tl__track--days">
                <div v-for="y in years" :key="y.year" class="spb-tl__year" :style="{ left: y.left + '%', width: y.width + '%' }">
                  <button v-for="b in y.bars" :key="b.key" type="button" class="spb-tl__bar" :class="`spb-tl__seg--${b.key}`"
                    :style="{ height: `max(2px, ${b.days / dayMax * 100}%)` }" :aria-label="b.text"
                    @mouseenter="note = b.text" @focus="note = b.text" @mouseleave="note = ''" @blur="note = ''"></button>
                </div>
              </div>
            </div>
            <div class="spb-tl__lane spb-tl__lane--axis" aria-hidden="true">
              <div class="spb-tl__label"></div>
              <div class="spb-tl__track spb-tl__track--axis">
                <span v-for="t in ticks" :key="t.label" class="spb-tl__tick" :style="{ left: t.left + '%' }">{{ t.label }}</span>
              </div>
            </div>
            <div class="spb-tl__readout" aria-live="polite">{{ hover ? describe(hover) : note || '\u00a0' }}</div>
          </div>

          <div style="overflow-x: auto">
          <table class="table table-sm align-middle mb-0 spb-sub sf-stack">
            <thead>
              <tr>
                <th>開始</th><th>結束</th><th>販售方式</th>
                <th class="text-end">價格</th><th class="text-end d-none d-md-table-cell">當時標準價</th><th class="text-end">折扣</th>
                <th>來源</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(p, i) in detail.periods" :key="i" :class="{ 'spb-row-active': hover === p }">
                <td data-label="開始" class="text-nowrap">{{ day(p.start) }}</td>
                <td data-label="結束" class="text-nowrap">{{ p.end ? day(p.end) : '進行中' }}</td>
                <td data-label="販售方式">{{ typeLabel(p.sale_type) }}</td>
                <td class="text-end text-nowrap fw-semibold" data-label="價格">{{ usd(p.price) }}</td>
                <td class="text-end text-nowrap d-none d-md-table-cell" data-label="當時標準價">{{ usd(p.msrp) }}</td>
                <td class="text-end text-nowrap" data-label="折扣">{{ off(p) }}</td>
                <td data-label="來源">
                  <span class="sf-chip" :class="{ 'sf-chip--ok': p.source === 'rsi' }">{{ p.source === 'rsi' ? 'RSI' : 'Open Hangar' }}</span>
                  <span class="small text-muted ms-1 d-none d-md-inline">{{ p.credibility }}</span>
                </td>
              </tr>
            </tbody>
          </table>
          </div>
            </template>
          </SfState>
          <p v-if="priceAttribution" class="small text-muted mt-3 mb-0">{{ priceAttribution }}</p>
        </template>
      </SfModal>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import { loadShipPrices, priceAttribution, priceByKey, priceByVehicle } from '@/utils/shipPrices'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 載具主檔 uuid */
  vehicleUuid: { type: String, default: '' },
  /** 對不到載具的船（概念船）直接給船價摘要的 key（見 src/models/ccu.py 的 concept_ships） */
  priceKey: { type: String, default: '' },
  name: { type: String, default: '' },
  buttonClass: { type: String, default: '' },
})

const uid = `spb-${Math.random().toString(36).slice(2, 8)}`
const open = ref(false)
const summary = computed(() => (props.vehicleUuid ? priceByVehicle.value.get(props.vehicleUuid) : null)
  || (props.priceKey ? priceByKey.value.get(props.priceKey) : null) || null)

/** Open Hangar 的出現頻率 */
const AVAIL = { always: '常駐', often: '常出現', sometimes: '偶爾', rarely: '少見', hardly: '極少見', events: '只在活動', new: '新船' }
const availLabel = k => AVAIL[k] || '—'
/** 時間軸的三條：代碼 U 的意義 Open Hangar 沒說明，先叫「其他」 */
const TYPES = [{ key: 'standard', label: '單買' }, { key: 'warbond', label: 'Warbond' }, { key: 'code_u', label: '其他' }]
const typeLabel = t => TYPES.find(x => x.key === t)?.label || t || '—'

const usd = v => (v == null ? '—' : `$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 2 })}`)
const pad = n => String(n).padStart(2, '0')
function day(v) {
  const d = new Date(v)
  return Number.isNaN(d.getTime()) ? '—' : `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
const off = p => (p.price != null && p.msrp && p.price < p.msrp ? `-${Math.round((1 - p.price / p.msrp) * 100)}%` : '—')
const describe = p => `${typeLabel(p.sale_type)}　${day(p.start)} ～ ${p.end ? day(p.end) : '進行中'}　${usd(p.price)}`
  + (off(p) !== '—' ? `（${off(p)}）` : '')

// ── 這艘船的上架紀錄（開視窗才抓，抓過就留著） ──
const detail = ref(null)
const loading = ref(false)
const error = ref('')
const hover = ref(null)
/** 滑到「每年上架天數」的長條時顯示的文字 */
const note = ref('')
async function load() {
  const key = summary.value?.key
  if (!key) return
  loading.value = true
  error.value = ''
  const res = await props.fetcher(`/item/ship-prices/detail?key=${encodeURIComponent(key)}`)
  const body = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!res?.ok || !body?.success) {
    error.value = '讀取失敗。'
    return
  }
  detail.value = body.data
}
function show() {
  open.value = true
  hover.value = null
  if (!detail.value && !loading.value) load()
}

// ── 時間軸：從最早一段的那年 1 月到現在 ──
const span = computed(() => {
  const periods = detail.value?.periods || []
  const now = Date.now()
  const first = Math.min(now, ...periods.map(p => new Date(p.start).getTime()).filter(Number.isFinite))
  const start = new Date(new Date(first).getFullYear(), 0, 1).getTime()
  return { start, end: now, len: Math.max(1, now - start) }
})
const pos = t => Math.min(100, Math.max(0, (t - span.value.start) / span.value.len * 100))
function segStyle(p) {
  const left = pos(new Date(p.start).getTime())
  const right = pos(p.end ? new Date(p.end).getTime() : span.value.end)
  return { left: `${left}%`, width: `max(4px, ${Math.max(0, right - left)}%)` }
}
const lanes = computed(() => TYPES
  .map(t => ({ ...t, periods: (detail.value?.periods || []).filter(p => p.sale_type === t.key) }))
  .filter(l => l.periods.length))
const ticks = computed(() => {
  const out = []
  const y0 = new Date(span.value.start).getFullYear()
  const y1 = new Date(span.value.end).getFullYear()
  for (let y = y0; y <= y1; y += 1) out.push({ label: String(y), left: pos(new Date(y, 0, 1).getTime()) })
  return out
})

// ── 價格走勢：縱軸是價格（上下各留一點空間，不從 0 開始——看的是變化） ──
const priceScale = computed(() => {
  const prices = (detail.value?.periods || []).map(p => p.price).filter(v => v != null)
  if (!prices.length) return { min: 0, max: 1, ticks: [] }
  const lo = Math.min(...prices)
  const hi = Math.max(...prices)
  const step = [1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500].find(n => (hi - lo) / n <= 4) || 1000
  const min = Math.max(0, Math.floor(lo / step) * step - (lo % step === 0 ? step : 0))
  const max = Math.ceil(hi / step) * step + (hi % step === 0 ? step : 0)
  const ticks = []
  for (let v = min; v <= max; v += step) ticks.push(v)
  return { min, max, ticks }
})
const priceY = v => (v - priceScale.value.min) / Math.max(1, priceScale.value.max - priceScale.value.min) * 100
const priceTicks = computed(() => priceScale.value.ticks.map(v => ({ v, bottom: priceY(v) })))
function priceStyle(p) {
  const { left, width } = segStyle(p)
  return { left, width, bottom: `calc(${priceY(p.price)}% - 3px)` }
}
/** 同一種販售方式照時間連成階梯線（價格到下一次上架才變） */
const priceLines = computed(() => lanes.value.map(l => {
  const pts = l.periods.filter(p => p.price != null)
    .map(p => ({ x0: pos(new Date(p.start).getTime()), x1: pos(p.end ? new Date(p.end).getTime() : span.value.end), y: 100 - priceY(p.price) }))
    .sort((a, b) => a.x0 - b.x0)
  const out = []
  pts.forEach((pt, i) => {
    if (i) out.push(`${pt.x0},${pts[i - 1].y}`)
    out.push(`${pt.x0},${pt.y}`, `${pt.x1},${pt.y}`)
  })
  return { key: l.key, points: out.join(' ') }
}).filter(l => l.points))

// ── 每年上架天數（同一種販售方式重疊的期間不重複算） ──
const DAY = 86400000
const years = computed(() => {
  const out = []
  const y0 = new Date(span.value.start).getFullYear()
  const y1 = new Date(span.value.end).getFullYear()
  for (let y = y0; y <= y1; y += 1) {
    const a = new Date(y, 0, 1).getTime()
    const b = Math.min(new Date(y + 1, 0, 1).getTime(), span.value.end)
    const bars = lanes.value.map(l => {
      const cuts = l.periods.map(p => [Math.max(a, new Date(p.start).getTime()), Math.min(b, p.end ? new Date(p.end).getTime() : span.value.end)])
        .filter(([s, e]) => e > s).sort((p, q) => p[0] - q[0])
      let total = 0
      let end = 0
      for (const [s, e] of cuts) {
        if (e <= end) continue
        total += e - Math.max(s, end)
        end = e
      }
      const days = Math.max(total ? 1 : 0, Math.round(total / DAY))
      return { key: l.key, days, text: `${y} 年　${l.label}　上架 ${days} 天` }
    }).filter(x => x.days)
    out.push({ year: y, left: pos(a), width: pos(b) - pos(a), bars })
  }
  return out
})
const dayMax = computed(() => {
  const m = Math.max(0, ...years.value.flatMap(y => y.bars.map(b => b.days)))
  return m > 180 ? 366 : m > 90 ? 180 : m > 30 ? 90 : 30
})

// 船價摘要整站共用一份，第一個按鈕掛上來時載入
onMounted(() => { loadShipPrices(props.fetcher) })
</script>

<style scoped>
/* 視窗 Teleport 到 body，外面包一層 .scifi-page 才吃得到玩家頁的主題樣式；本身不佔版面 */
.spb-host { display: contents; }
.spb-sub { --bs-table-bg: transparent; font-size: .95rem; }
.spb-sub th { white-space: nowrap; font-size: .8rem; color: var(--sf-text-muted); font-weight: 600; }
.spb-row-active > td { background: rgba(var(--sf-accent-rgb, 77, 208, 255), .12); }

.spb-tl { padding: .5rem .25rem 0; margin-bottom: .75rem; }
.spb-tl__lane { display: flex; align-items: center; gap: .75rem; margin-bottom: 6px; }
.spb-tl__label { flex: 0 0 5.5rem; font-size: .9rem; color: var(--sf-text); text-align: right; }
.spb-tl__track { position: relative; flex: 1 1 auto; height: 18px; border-radius: 4px; background: var(--sf-chip-bg); }
.spb-tl__seg {
  position: absolute; top: 0; height: 100%; padding: 0; border: 0; border-radius: 4px;
  /* 相鄰兩段之間留一條底色的縫 */
  box-shadow: 0 0 0 1px var(--sf-panel, #0b1522);
  cursor: default;
}
.spb-tl__seg--standard { background: var(--sf-accent); }
.spb-tl__seg--warbond { background: var(--sf-accent-2); }
.spb-tl__seg--code_u { background: var(--sf-text-muted); }
/* 還在賣的：右邊不收圓角，表示延伸到現在 */
.spb-tl__seg.is-open { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.spb-tl__seg.is-active, .spb-tl__seg:focus-visible { outline: 2px solid var(--sf-text-strong, #fff); outline-offset: 1px; z-index: 1; }
.spb-tl__title { margin: 18px 0 10px 6.25rem; font-size: .85rem; font-weight: 600; color: var(--sf-text-muted); }
.spb-tl__lane--chart { align-items: stretch; }
.spb-tl__label--y { position: relative; }
.spb-tl__ytick { position: absolute; right: 0; transform: translateY(50%); font-size: .75rem; line-height: 1; color: var(--sf-text-muted); white-space: nowrap; }
.spb-tl__track--price { height: 120px; background: none; border-radius: 0; }
.spb-tl__track--days { height: 56px; background: none; border-radius: 0; border-bottom: 1px solid var(--sf-border); }
.spb-tl__grid { position: absolute; left: 0; right: 0; height: 0; border-top: 1px solid var(--sf-border); opacity: .6; }
.spb-tl__lines { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
.spb-tl__lines polyline { fill: none; stroke-width: 1.5; vector-effect: non-scaling-stroke; opacity: .55; }
.spb-tl__line--standard { stroke: var(--sf-accent); }
.spb-tl__line--warbond { stroke: var(--sf-accent-2); }
.spb-tl__line--code_u { stroke: var(--sf-text-muted); stroke-dasharray: 3 3; }
.spb-tl__seg--price { top: auto; height: 6px; min-width: 6px; border-radius: 3px; }
.spb-tl__year { position: absolute; bottom: 0; top: 0; display: flex; align-items: flex-end; justify-content: center; gap: 2px; padding: 0 3px; }
.spb-tl__bar { flex: 0 1 14px; min-width: 4px; padding: 0; border: 0; border-radius: 4px 4px 0 0; cursor: default; }
.spb-tl__bar:hover, .spb-tl__bar:focus-visible { outline: 2px solid var(--sf-text-strong, #fff); outline-offset: 1px; }
.spb-tl__lane--axis { margin-bottom: 0; }
.spb-tl__track--axis { height: 1.2rem; background: none; border-top: 1px solid var(--sf-border); border-radius: 0; }
.spb-tl__tick { position: absolute; top: 2px; font-size: .75rem; color: var(--sf-text-muted); padding-left: 3px; border-left: 1px solid var(--sf-border); line-height: 1; }
.spb-tl__readout { margin-left: 6.25rem; margin-top: .25rem; min-height: 1.5rem; font-size: .95rem; color: var(--sf-text-strong, var(--sf-text)); }
@media (max-width: 767.98px) {
  .spb-tl__label { flex-basis: 4.5rem; font-size: .8rem; }
  .spb-tl__readout { margin-left: 0; }
  .spb-tl__title { margin-left: 5.25rem; }
}
</style>
