<!--
  物品／藍圖／艦船列上的「維克洛」按鈕＋跳出視窗：這個東西有出現在維克洛交易裡（獎勵或需求，
  utils/wikelo.js 的共用索引）才出現按鈕；按了用 GET /mission/wikelo/by-item 列出
  「可以跟維克洛換到」與「要交給維克洛」的交易（每筆一個區塊：標題＋WikeloTradePanel，跟資料庫 › 維克洛的視窗同一份）。
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
          <!-- 兩段：換得到它的、要交它的；每筆交易一個區塊（標題＋WikeloTradePanel：需要的物品表、獎勵、前置條件），標出就是它的那一行 -->
          <section v-for="g in groups" :key="g.key" class="wkb-group">
            <h4 class="wkb-h">{{ g.label }}<span class="wkb-count">{{ g.rows.length }}</span></h4>
            <article v-for="t in g.rows" :key="t._id" class="wkb-trade">
              <h5 class="wkb-title">
                {{ t.title_zh || t.title }}
                <span v-if="t.title_zh" class="sf-name__en">{{ t.title }}</span>
              </h5>
              <WikeloTradePanel :trade="t" :highlight="uuids" />
            </article>
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
import WikeloTradePanel from '@/components/WikeloTradePanel.vue'
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
const groups = computed(() => [
  { key: 'reward', label: '可以跟維克洛換到', rows: data.value.reward },
  { key: 'requirement', label: '要交給維克洛', rows: data.value.requirement },
].filter(g => g.rows.length))

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
.wkb-group + .wkb-group { margin-top: 1.5rem; }
.wkb-h {
  display: flex; align-items: center; gap: .5rem; margin: 0 0 .75rem;
  font-size: var(--sf-fs-base); font-weight: 700; color: rgb(var(--sf-accent-rgb));
}
.wkb-count {
  font-size: var(--sf-fs-xs); font-weight: 700; padding: .05rem .5rem; border-radius: 999px;
  background: rgba(var(--sf-accent-rgb), .18); color: var(--sf-text-strong);
}
.wkb-trade { padding: .75rem; border: 1px solid var(--sf-border); border-radius: .5rem; background: var(--sf-inset); }
.wkb-trade + .wkb-trade { margin-top: .75rem; }
.wkb-title { margin: 0 0 .6rem; font-size: var(--sf-fs-md); font-weight: 700; color: var(--sf-text-strong); }
.wkb-title .sf-name__en { display: block; font-size: var(--sf-fs-sm); font-weight: 400; }
</style>
