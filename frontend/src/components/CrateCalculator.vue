<!--
  玩家頁「工具箱 › 貨櫃試算」：一個總量（SCU）可以拆成哪幾種標準貨櫃、各幾個（純前端，算法見 utils/crateCombos.js）。
  勾選可用的貨櫃尺寸；剛好湊得出來就列出最少貨櫃數的組合（以及多 1～2 個的其他拆法），
  湊不出來（例如 106 只用 16／8／4）就列最接近的少一點、多一點兩種。
  只算數量，船的網格擺不擺得下在「工具箱 › 貨艙網格」。
-->
<template>
  <div>
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-3">
            <label class="form-label small fw-semibold mb-1" for="crc-total">總量（SCU）</label>
            <input id="crc-total" v-model.number="total" type="number" min="1" :max="MAX" step="1" inputmode="numeric"
              class="form-control form-control-sm" :class="{ 'is-invalid': tooBig }">
          </div>
          <div class="col-12 col-md-9">
            <span class="form-label small fw-semibold mb-1 d-block" id="crc-sizes-label">可用的貨櫃</span>
            <div class="d-flex flex-wrap align-items-center gap-2" role="group" aria-labelledby="crc-sizes-label">
              <button v-for="s in SIZES_DESC" :key="s" type="button" class="btn btn-sm btn-subtab"
                :class="{ active: sizes.includes(s) }" :aria-pressed="sizes.includes(s) ? 'true' : 'false'" @click="toggle(s)">
                {{ s }} SCU</button>
              <button type="button" class="btn btn-sm btn-primary" @click="sizes = [...SIZES_DESC]">全選</button>
            </div>
          </div>
        </div>
        <div v-if="tooBig" class="small sf-bad mt-2">最多 {{ MAX.toLocaleString('en-US') }} SCU。</div>
      </div>
    </div>

    <SfState :empty="!result.targets.length" :empty-text="!sizes.length ? '至少選一種貨櫃。' : '輸入總量。'">
      <div v-if="!result.exact" class="sf-chip sf-chip--warn mb-2">
        {{ fmt(total) }} SCU 用選的貨櫃湊不剛好，下面是最接近的
      </div>
      <div v-for="t in result.targets" :key="t.amount" :class="[cardClass, 'mb-3']">
        <div class="card-body py-2 ps-3 pe-3 d-flex flex-wrap align-items-center gap-2">
          <span class="fw-semibold fs-5">{{ fmt(t.amount) }} SCU</span>
          <span v-if="t.diff" class="sf-chip mb-0" :class="t.diff < 0 ? 'sf-chip--warn' : 'sf-chip--accent'">
            {{ t.diff < 0 ? `少 ${fmt(-t.diff)} SCU` : `多 ${fmt(t.diff)} SCU 空間` }}</span>
          <span class="text-muted">最少 {{ t.min }} 個貨櫃</span>
        </div>
        <div class="card-body p-0 border-top">
          <div style="overflow-x: auto">
            <table class="table table-hover align-middle mb-0 sf-stack">
              <thead class="table-light">
                <tr>
                  <th class="ps-3">拆法</th>
                  <th v-for="s in shownSizes" :key="s" class="text-end crc-size">{{ s }} SCU</th>
                  <th class="text-end pe-3">貨櫃數</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(o, i) in t.options" :key="i" :class="{ 'crc-best': o.total === t.min }">
                  <td class="ps-3 sf-stack__title">
                    <span v-for="s in shownSizes.filter(s => o.counts[s])" :key="s" class="sf-chip me-1 mb-1"
                      :class="{ 'sf-chip--accent': o.total === t.min }">{{ s }} × {{ o.counts[s] }}</span>
                  </td>
                  <td v-for="s in shownSizes" :key="s" class="text-end crc-size" :data-label="`${s} SCU`"
                    :class="{ 'text-muted': !o.counts[s] }">{{ o.counts[s] || '—' }}</td>
                  <td class="text-end pe-3 fw-semibold" data-label="貨櫃數">{{ o.total }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </SfState>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import SfState from '@/components/SfState.vue'
import { SIZES } from '@/utils/cargoPack'
import { plan } from '@/utils/crateCombos'

defineProps({ cardClass: { type: String, default: 'card' } })

/** 輸入上限（動態規劃的陣列長度跟總量成正比） */
const MAX = 100000
const SIZES_DESC = [...SIZES].sort((a, b) => b - a)
const total = ref(106)
const sizes = ref([...SIZES_DESC])
const fmt = v => Number(v).toLocaleString('en-US')
const tooBig = computed(() => total.value > MAX)

function toggle(s) {
  sizes.value = sizes.value.includes(s) ? sizes.value.filter(x => x !== s) : [...sizes.value, s].sort((a, b) => b - a)
}
// 表格欄位：選了的尺寸（大的在左）
const shownSizes = computed(() => SIZES_DESC.filter(s => sizes.value.includes(s)))
const result = computed(() => {
  const t = Math.floor(Number(total.value) || 0)
  if (t <= 0 || t > MAX || !sizes.value.length) return { exact: false, targets: [] }
  return plan(t, sizes.value, { slack: 2, maxShown: 8 })
})
</script>

<style scoped>
.crc-best > td { background: rgba(var(--sf-accent-rgb), .08); }
/* 手機：各尺寸的數量已經寫在拆法的標籤裡，不再一格一格列 */
@media (max-width: 767.98px) { .crc-size { display: none !important; } }
</style>
