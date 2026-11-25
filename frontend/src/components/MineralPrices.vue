<!--
  礦物資料庫詳細的「買賣價格」：礦物關聯到的 UEX 商品（精煉品 uex.id、原礦 uex.raw_id）各自
  哪裡買得到（GET /player/commodities/buy-locations）、哪裡收（GET /mining/sell-prices，跟礦物回波卡片同一份）。
  掛上去才查；每區先列最高（收購）／最低（購買）的幾處，可以展開全部。
-->
<template>
  <div>
    <p v-if="!sections.length" class="small text-muted mb-0">這種礦物還沒對應到 UEX 商品，沒有價格資料。</p>
    <div v-for="s in sections" :key="s.id" class="mp-sec">
      <div class="mp-head">{{ s.label }}<span v-if="s.code" class="sf-chip sf-chip--accent ms-1">{{ s.code }}</span></div>
      <div class="row g-2">
        <div v-for="side in SIDES" :key="side.key" class="col-12 col-lg-6">
          <div class="mp-side">
            <div class="mp-side__t">{{ side.label }}
              <span v-if="rowsOf(s.id, side.key)" class="small text-muted fw-normal ms-1">{{ rowsOf(s.id, side.key).length }} 處</span></div>
            <div v-if="!rowsOf(s.id, side.key)" class="small text-muted"><span class="spinner-border spinner-border-sm me-1"></span>載入中…</div>
            <div v-else-if="!rowsOf(s.id, side.key).length" class="small text-muted">{{ side.empty }}</div>
            <template v-else>
              <div v-for="r in shown(s.id, side.key)" :key="r.key" class="mp-row">
                <span class="mp-row__p">{{ fmtAuec(r.price) }}</span>
                <span class="min-w-0 text-truncate">{{ r.name }}<span v-if="r.place && !r.name.includes(r.place)" class="text-muted ms-1">{{ locationZh(r.place) }}</span></span>
                <span v-if="r.system" class="sf-chip ms-auto">{{ locationZh(r.system) }}</span>
              </div>
              <button v-if="rowsOf(s.id, side.key).length > PREVIEW" type="button" class="btn btn-sm btn-secondary mt-1"
                @click="toggle(s.id, side.key)">{{ expanded[`${s.id}:${side.key}`] ? '收起' : `顯示全部 ${rowsOf(s.id, side.key).length} 處` }}</button>
            </template>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, watch } from 'vue'
import { getJson as fetchJson } from '@/utils/getJson'
import { fmtAuec, loadLocationZh, locationZh } from '@/utils/uexCommodity'

const props = defineProps({
  /** 礦床成分的 uex：{ id, code, raw_id, raw_code, is_raw } */
  uex: { type: Object, default: null },
  fetcher: { type: Function, required: true },
})
const PREVIEW = 5
const SIDES = [
  { key: 'sell', label: '收購價（每 SCU）', empty: '沒有終端收購。' },
  { key: 'buy', label: '購買價（每 SCU）', empty: '沒有終端販售。' },
]
const sections = computed(() => {
  const u = props.uex
  if (!u) return []
  const out = []
  if (u.id) out.push({ id: String(u.id), label: u.is_raw ? '原礦' : '精煉品', code: u.code })
  if (u.raw_id && String(u.raw_id) !== String(u.id)) out.push({ id: String(u.raw_id), label: '原礦', code: u.raw_code })
  return out
})
const data = reactive({})        // `${id}:${side}` → rows（undefined＝載入中）
const expanded = reactive({})
const rowsOf = (id, side) => data[`${id}:${side}`]
const shown = (id, side) => (expanded[`${id}:${side}`] ? rowsOf(id, side) : rowsOf(id, side).slice(0, PREVIEW))
const toggle = (id, side) => { expanded[`${id}:${side}`] = !expanded[`${id}:${side}`] }

const getJson = async url => (await fetchJson(props.fetcher, url)).data ?? null
const leaf = (t, price, date) => ({ key: t?.id || t?.name, name: t?.name || '—', place: t?.place, system: t?.star_system, price, date })

async function load() {
  const ids = sections.value.map(s => s.id)
  if (!ids.length) return
  const sell = await getJson(`/mining/sell-prices?${ids.map(id => `id=${encodeURIComponent(id)}`).join('&')}`)
  for (const id of ids) data[`${id}:sell`] = (sell?.[id] || []).map(r => leaf(r.terminal, r.price_sell, r.date_modified))
  await Promise.all(ids.map(async (id) => {
    const buy = await getJson(`/player/commodities/buy-locations?id=${encodeURIComponent(id)}`)
    data[`${id}:buy`] = (buy?.locations || []).map(l => leaf(l.terminal, l.items?.[0]?.price_buy, l.items?.[0]?.date_modified))
      .sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity))
  }))
  // 地點、星系的中文從翻譯資料庫查
  loadLocationZh(Object.values(data).flatMap(rows => (rows || []).flatMap(r => [r.place, r.system])))
}
watch(() => props.uex, load, { immediate: true })
</script>

<style scoped>
.mp-sec + .mp-sec { margin-top: .75rem; }
.mp-head { font-weight: 700; color: var(--sf-text-strong); margin-bottom: .35rem; }
.mp-side { padding: .5rem .65rem; border: 1px solid var(--sf-border); border-radius: .4rem; height: 100%; }
.mp-side__t { font-weight: 600; font-size: var(--sf-fs-sm); margin-bottom: .25rem; }
.mp-row { display: flex; align-items: center; gap: .6rem; padding: .2rem 0; font-size: var(--sf-fs-sm); border-top: 1px solid var(--sf-border); }
.mp-row__p { flex: none; min-width: 6.5rem; font-weight: 700; color: var(--sf-text-strong); font-variant-numeric: tabular-nums; }
.min-w-0 { min-width: 0; }
</style>
