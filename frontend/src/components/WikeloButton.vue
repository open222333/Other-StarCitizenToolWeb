<!--
  物品／藍圖／艦船列上的「維克洛」按鈕＋跳出視窗：這個東西有出現在維克洛交易裡（獎勵或需求，
  utils/wikelo.js 的共用索引）才出現按鈕；按了用 GET /mission/wikelo/by-item 列出
  「可以跟維克洛換到」與「要交給維克洛」的交易（WikeloTradeCard）。
  uuids＝物品 uuid（藍圖給產物的 uuid）；names＝獎勵名稱（艦船用，獎勵的 uuid 不一定是載具主檔的）。
-->
<template>
  <button v-if="hit" type="button" class="btn btn-sm btn-info" :class="buttonClass"
    :aria-label="`${name} 的維克洛交易`" aria-haspopup="dialog" @click.stop="openModal">維克洛</button>
  <Teleport v-if="hit && mounted" to="body">
    <div class="scifi-page wkb-host">
      <SfModal :id="uid" v-model:open="open" :title="`${name} · 維克洛交易`" width="1100px">
        <SfState v-if="loading" loading />
        <SfState v-else-if="error" :error="error" @retry="load" />
        <template v-else>
          <section v-if="data.reward.length" class="mb-3">
            <h4 class="wkb-h">可以跟維克洛換到（{{ data.reward.length }}）</h4>
            <div class="wkb-grid">
              <WikeloTradeCard v-for="t in data.reward" :key="t._id" :trade="t" :highlight="uuids" />
            </div>
          </section>
          <section v-if="data.requirement.length">
            <h4 class="wkb-h">要交給維克洛（{{ data.requirement.length }}）</h4>
            <div class="wkb-grid">
              <WikeloTradeCard v-for="t in data.requirement" :key="t._id" :trade="t" :highlight="uuids" />
            </div>
          </section>
          <SfState v-if="!data.reward.length && !data.requirement.length" empty empty-text="沒有相關的維克洛交易" />
        </template>
      </SfModal>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import WikeloTradeCard from '@/components/WikeloTradeCard.vue'
import { getJson } from '@/utils/getJson'
import { loadWikeloIndex, wikeloHit } from '@/utils/wikelo'

const props = defineProps({
  uuids: { type: Array, default: () => [] },
  names: { type: Array, default: () => [] },
  name: { type: String, default: '' },
  buttonClass: { type: String, default: '' },
})

const uid = `wkb-${Math.random().toString(36).slice(2, 8)}`
const hit = computed(() => wikeloHit(props.uuids, props.names))
const mounted = ref(false)
const open = ref(false)
const loading = ref(false)
const error = ref('')
const data = ref({ reward: [], requirement: [] })
let loaded = false

onMounted(() => { loadWikeloIndex() })

async function load() {
  loading.value = true
  error.value = ''
  const sp = new URLSearchParams()
  props.uuids.filter(Boolean).forEach(u => sp.append('uuid', u))
  props.names.filter(Boolean).forEach(n => sp.append('name', n))
  const res = await getJson(fetch, `/mission/wikelo/by-item?${sp}`, undefined, '讀取維克洛交易失敗')
  loading.value = false
  if (!res.ok) { error.value = res.message; return }
  data.value = { reward: res.data.reward || [], requirement: res.data.requirement || [] }
  loaded = true
}

async function openModal() {
  if (!mounted.value) { mounted.value = true; await nextTick() }
  open.value = true
  if (!loaded) load()
}
</script>

<style scoped>
.wkb-host { display: contents; }
.wkb-h { font-size: var(--sf-fs-base); font-weight: 700; margin: 0 0 .5rem; color: rgb(var(--sf-accent-rgb)); }
.wkb-grid { display: grid; gap: .75rem; grid-template-columns: 1fr; }
@media (min-width: 992px) { .wkb-grid { grid-template-columns: 1fr 1fr; } }
</style>
