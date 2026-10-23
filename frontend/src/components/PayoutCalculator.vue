<!--
  玩家頁「酬勞分配」：輸入總金額、人數、稅率，每個人可以調成數（預設每人 1 成＝平均分），
  列出每個人的稅前金額、稅、稅後金額。純前端計算；成員名單、成數、稅率記在這台瀏覽器（localStorage），金額不記。

  金額以 aUEC 整數計：稅前依成數比例分，四捨五入後的零頭用「最大餘數法」補給小數部分最大的人，
  所以稅前合計一定等於總金額；稅＝稅前 × 稅率（四捨五入），稅後＝稅前 − 稅。
-->
<template>
  <div>
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-5">
            <label class="form-label small fw-semibold mb-1" for="payout-total">總金額</label>
            <div class="input-group">
              <input id="payout-total" v-model.number="total" type="number" class="form-control" min="0" step="1" placeholder="0">
              <span class="input-group-text">aUEC</span>
            </div>
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label small fw-semibold mb-1" for="payout-count">人數</label>
            <input id="payout-count" :value="count" type="number" class="form-control" min="1" :max="MAX_PEOPLE" step="1"
              @change="setCount($event.target.value); $event.target.value = count">
          </div>
          <div class="col-6 col-md-4">
            <label class="form-label small fw-semibold mb-1" for="payout-tax">稅率</label>
            <div class="input-group">
              <input id="payout-tax" v-model.number="taxPct" type="number" class="form-control" min="0" max="100" step="0.1">
              <span class="input-group-text">%</span>
            </div>
          </div>
        </div>
        <div class="d-flex flex-wrap gap-2 mt-3">
          <button type="button" class="btn btn-sm btn-warning" :disabled="isEven" @click="resetShares">
            <i class="bi bi-distribute-horizontal me-1"></i>平均分配
          </button>
          <button type="button" class="btn btn-sm btn-success" :disabled="count >= MAX_PEOPLE" @click="setCount(count + 1)">
            <i class="bi bi-person-plus me-1"></i>加一人
          </button>
        </div>
      </div>
    </div>

    <div :class="cardClass">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0 sf-stack">
            <thead class="table-light">
              <tr>
                <th class="ps-3">成員</th>
                <th class="text-end">成數</th>
                <th class="text-end">比例</th>
                <th class="text-end">稅前</th>
                <th class="text-end">稅</th>
                <th class="text-end">稅後</th>
                <th class="pe-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(p, i) in rows" :key="p.id">
                <td class="ps-3 sf-stack__title">
                  <input v-model="people[i].name" type="text" class="form-control form-control-sm payout-name"
                    :placeholder="`成員 ${i + 1}`" :aria-label="`第 ${i + 1} 位成員名稱`">
                </td>
                <td class="text-end" data-label="成數">
                  <input v-model.number="people[i].share" type="number" class="form-control form-control-sm payout-share ms-auto"
                    min="0" step="0.1" :aria-label="`第 ${i + 1} 位成員成數`" @change="people[i].share = clampShare(people[i].share)">
                </td>
                <td class="text-end text-nowrap" data-label="比例">{{ fmtPct(p.ratio) }}</td>
                <td class="text-end text-nowrap" data-label="稅前">{{ fmt(p.gross) }}</td>
                <td class="text-end text-nowrap payout-tax" data-label="稅">{{ p.tax ? `−${fmt(p.tax)}` : '0' }}</td>
                <td class="text-end text-nowrap fw-bold payout-net" data-label="稅後">{{ fmt(p.net) }}</td>
                <td class="text-end pe-3 sf-stack__actions">
                  <button type="button" class="btn btn-sm btn-danger" :disabled="count <= 1" :aria-label="`移除第 ${i + 1} 位成員`"
                    @click="removeAt(i)"><i class="bi bi-trash"></i></button>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr class="payout-sum">
                <td class="ps-3 fw-semibold">合計</td>
                <td class="text-end" data-label="成數">{{ fmtShare(shareSum) }}</td>
                <td class="text-end" data-label="比例">{{ shareSum > 0 ? '100%' : '—' }}</td>
                <td class="text-end text-nowrap fw-semibold" data-label="稅前">{{ fmt(sum.gross) }}</td>
                <td class="text-end text-nowrap payout-tax" data-label="稅">{{ sum.tax ? `−${fmt(sum.tax)}` : '0' }}</td>
                <td class="text-end text-nowrap fw-bold payout-net" data-label="稅後">{{ fmt(sum.net) }}</td>
                <td class="pe-3"></td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'

defineProps({
  cardClass: { type: String, default: 'card' },
})

const MAX_PEOPLE = 50
let idSeq = 0
const newPerson = () => ({ id: ++idSeq, name: '', share: 1 })

// 成員名單、成數、稅率記在這台瀏覽器（下次打開不用重打）；金額每次不同，不記
const STORAGE_KEY = 'sc_payout_v1'
function loadSaved() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')
    if (!saved || !Array.isArray(saved.people) || !saved.people.length) return null
    return {
      taxPct: Number.isFinite(Number(saved.taxPct)) ? Number(saved.taxPct) : 0.5,
      people: saved.people.slice(0, MAX_PEOPLE).map(p => ({
        ...newPerson(), name: String(p.name || '').slice(0, 40), share: Number(p.share) >= 0 ? Number(p.share) : 1,
      })),
    }
  } catch {
    return null
  }
}
const saved = loadSaved()

const total = ref(null)
const taxPct = ref(saved ? saved.taxPct : 0.5)
const people = reactive(saved ? saved.people : [newPerson(), newPerson()])
watch([taxPct, () => people.map(p => [p.name, p.share])], () => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      taxPct: taxPct.value, people: people.map(p => ({ name: p.name, share: p.share })),
    }))
  } catch { /* 無痕模式等存不了就算了 */ }
}, { deep: true })
const count = computed(() => people.length)

function setCount(value) {
  const n = Math.max(1, Math.min(MAX_PEOPLE, Math.round(Number(value) || 1)))
  while (people.length < n) people.push(newPerson())
  if (people.length > n) people.splice(n)
}
function removeAt(i) {
  if (people.length > 1) people.splice(i, 1)
}
function clampShare(v) {
  const n = Number(v)
  return Number.isFinite(n) && n >= 0 ? Math.round(n * 100) / 100 : 0
}
function resetShares() {
  people.forEach(p => { p.share = 1 })
}

const shareSum = computed(() => people.reduce((s, p) => s + (Number(p.share) > 0 ? Number(p.share) : 0), 0))
const isEven = computed(() => people.every(p => Number(p.share) === Number(people[0].share)))

// 稅前：依成數比例分總金額，取整數後用最大餘數法把零頭補齊，合計＝總金額
const rows = computed(() => {
  const amount = Math.max(0, Math.round(Number(total.value) || 0))
  const sum = shareSum.value
  const rate = Math.min(100, Math.max(0, Number(taxPct.value) || 0)) / 100
  const exact = people.map(p => (sum > 0 ? amount * Math.max(0, Number(p.share) || 0) / sum : 0))
  const gross = exact.map(Math.floor)
  let left = amount - gross.reduce((a, b) => a + b, 0)
  if (sum > 0) {
    const order = exact.map((v, i) => [v - Math.floor(v), i]).sort((a, b) => b[0] - a[0])
    for (let k = 0; left > 0 && k < order.length; k++, left--) gross[order[k][1]] += 1
  }
  return people.map((p, i) => {
    const tax = Math.round(gross[i] * rate)
    return { id: p.id, ratio: sum > 0 ? Math.max(0, Number(p.share) || 0) / sum : 0, gross: gross[i], tax, net: gross[i] - tax }
  })
})
const sum = computed(() => rows.value.reduce((s, r) => ({
  gross: s.gross + r.gross, tax: s.tax + r.tax, net: s.net + r.net,
}), { gross: 0, tax: 0, net: 0 }))

function fmt(v) {
  return Number(v || 0).toLocaleString('en-US')
}
function fmtPct(v) {
  return `${Number((v * 100).toFixed(1))}%`
}
function fmtShare(v) {
  return Number(v.toFixed(2)).toString()
}
</script>

<style scoped>
.payout-name { min-width: 8rem; }
.payout-share { width: 5.5rem; text-align: right; }
.payout-tax { color: var(--sf-text-muted); }
.payout-net { color: var(--sf-accent); }
.payout-sum td { border-top: 2px solid var(--sf-border-hi); }
</style>
