<!--
  資料庫 › 維克洛：維克洛（Wikelo Emporium）的全部交易（GET /mission/wikelo，同步項目「維克洛」），
  每筆一張卡（WikeloTradeCard）：獎勵、要交的物品與數量、維克洛聲望、前置條件。
  搜尋：交易名稱、獎勵或需求物品名稱（中英文），在前端過濾（全部不到一百筆）。
-->
<template>
  <div>
    <div class="card scifi-card sf-search mb-3">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-6">
            <label class="form-label small fw-semibold mb-1" for="wk-q">搜尋</label>
            <input id="wk-q" v-model="query" type="search" class="form-control" placeholder="交易、獎勵或需要的物品（中英文）" autocomplete="off">
          </div>
          <div class="col-12 col-md-6">
            <span class="form-label small fw-semibold mb-1 d-block">獎勵</span>
            <div class="sf-pills">
              <button v-for="k in KINDS" :key="k.key" type="button" class="sf-pill" :class="{ active: kinds.includes(k.key) }"
                :aria-pressed="kinds.includes(k.key) ? 'true' : 'false'" @click="toggleKind(k.key)">{{ k.label }}</button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <SfState v-if="loading" loading />
    <SfState v-else-if="error" :error="error" @retry="load" />
    <SfState v-else-if="!shown.length" empty :empty-text="rows.length ? '沒有符合條件的交易' : '尚無維克洛交易資料'" />
    <template v-else>
      <p class="small text-muted mb-2">共 {{ shown.length }} 筆</p>
      <div class="wk-grid">
        <WikeloTradeCard v-for="t in shown" :key="t._id" :trade="t" />
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import SfState from '@/components/SfState.vue'
import WikeloTradeCard from '@/components/WikeloTradeCard.vue'
import { getJson } from '@/utils/getJson'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: true },
})

// 獎勵種類：依獎勵物品的主檔種類（type）分；載具主檔沒有 type 的歸「艦船」
const KINDS = [
  { key: 'ship', label: '艦船' },
  { key: 'weapon', label: '武器' },
  { key: 'armor', label: '護甲' },
  { key: 'other', label: '其他' },
]
function rewardKind(r) {
  const t = r.type || ''
  if (!t || /vehicle|ship/i.test(t)) return /favor|scrip/i.test(r.name || '') ? 'other' : 'ship'
  if (/^Weapon/i.test(t)) return 'weapon'
  if (/^Char_Armor|Suit/i.test(t)) return 'armor'
  return 'other'
}

const rows = ref([])
const loading = ref(false)
const error = ref('')
const query = ref('')
const kinds = ref([])
const toggleKind = k => { kinds.value = kinds.value.includes(k) ? kinds.value.filter(x => x !== k) : [...kinds.value, k] }

async function load() {
  loading.value = true
  error.value = ''
  const res = await getJson(props.fetcher, '/mission/wikelo', undefined, '讀取維克洛交易失敗')
  loading.value = false
  if (!res.ok) { error.value = res.message; return }
  rows.value = res.data || []
}
let loaded = false
watch(() => props.active, v => { if (v && !loaded) { loaded = true; load() } }, { immediate: true })

const shown = computed(() => {
  const q = query.value.trim().toLowerCase()
  return rows.value.filter((t) => {
    if (kinds.value.length && !(t.rewards || []).some(r => kinds.value.includes(rewardKind(r)))) return false
    if (!q) return true
    const texts = [t.title, t.title_zh, ...[...(t.rewards || []), ...(t.requirements || [])].flatMap(r => [r.name, r.name_zh])]
    return texts.some(s => (s || '').toLowerCase().includes(q))
  })
})
</script>

<style scoped>
.wk-grid { display: grid; gap: .75rem; grid-template-columns: 1fr; }
@media (min-width: 992px) { .wk-grid { grid-template-columns: 1fr 1fr; } }
@media (min-width: 1600px) { .wk-grid { grid-template-columns: 1fr 1fr 1fr; } }
</style>
