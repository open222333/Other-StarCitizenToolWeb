<!--
  藍圖詳細（跳出視窗）：配方（材料、用量、最低品質、製作時間、是否預設可用）與品質試算兩個分頁，
  有解鎖任務的另外點開 BlueprintMissionsModal。礦物資料庫「用在哪些藍圖」點開用，其他列表也可以共用。
  資料：GET /blueprint/master/<uuid>（配方）、品質試算見 components/BlueprintQuality.vue。
  用法：<BlueprintDetailModal ref="d" :fetcher="..." /> → d.value.open({ uuid, name, name_zh, output_type })
-->
<template>
  <SfModal id="bp-detail" v-model:open="openRef" :title="title" icon="bi bi-hammer" width="1100px">
    <div class="bpd-tabs" role="tablist">
      <button v-for="t in TABS" :key="t.key" type="button" class="bpd-tab" role="tab" :aria-selected="tab === t.key ? 'true' : 'false'"
        :class="{ active: tab === t.key }" @click="tab = t.key"><i :class="t.icon" class="me-1"></i>{{ t.label }}</button>
    </div>
    <div v-if="tab === 'recipe'">
      <SfState :loading="loading" :error="error" @retry="load">
        <template v-if="bp">
          <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
            <span v-if="typeText" class="sf-chip">{{ typeText }}</span>
            <span v-if="bp.is_available_by_default" class="sf-chip sf-chip--accent">預設可用</span>
            <span v-if="bp.craft_time_label" class="sf-chip"><i class="bi bi-clock me-1"></i>{{ bp.craft_time_label }}</span>
            <button v-if="bp.unlocking_missions_count" type="button" class="btn btn-sm btn-info ms-auto" @click="openMissions">
              <i class="bi bi-flag me-1"></i>解鎖任務 {{ bp.unlocking_missions_count }} 個</button>
          </div>
          <h4 class="bpd-h">材料</h4>
          <div v-if="!bp.ingredients?.length" class="text-muted">—</div>
          <div v-for="(ing, i) in bp.ingredients || []" :key="i" class="bpd-mat" :class="{ 'bpd-mat--hit': highlight && sameName(ing.name, highlight) }">
            <span>{{ materialLabel(ing) }}</span>
            <span class="bpd-mat__q">{{ fmtQty(ing) }}<span v-if="ing.min_quality" class="bpd-warn ms-2">最低 Q{{ ing.min_quality }}</span></span>
          </div>
        </template>
      </SfState>
    </div>
    <BlueprintQuality v-else-if="openRef && uuid" :key="uuid" :fetcher="fetcher" :blueprint-uuid="uuid" />
  </SfModal>
  <BlueprintMissionsModal ref="missionsRef" :fetcher="fetcher" />
</template>

<script setup>
import { computed, ref } from 'vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import BlueprintQuality from '@/components/BlueprintQuality.vue'
import BlueprintMissionsModal from '@/components/BlueprintMissionsModal.vue'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'
import { loadMaterialZh, materialLabel } from '@/utils/blueprintMaterial'

const props = defineProps({
  fetcher: { type: Function, required: true },
})
const TABS = [
  { key: 'recipe', label: '配方', icon: 'bi bi-list-ul' },
  { key: 'quality', label: '品質試算', icon: 'bi bi-sliders' },
]
const openRef = ref(false)
const tab = ref('recipe')
const uuid = ref('')
const brief = ref(null)
/** 從礦物點進來時，配方裡標出那個材料 */
const highlight = ref('')
const bp = ref(null)
const loading = ref(false)
const error = ref('')
const missionsRef = ref(null)
let seq = 0

const title = computed(() => {
  const b = bp.value || brief.value || {}
  return b.name_zh || b.name || '藍圖'
})
const typeText = computed(() => (bp.value?.output_type ? blueprintTypeLabel(bp.value.output_type) : ''))
const sameName = (a, b) => (a || '').toLowerCase() === (b || '').toLowerCase()

async function load() {
  if (!uuid.value) return
  const my = ++seq
  loading.value = true
  error.value = ''
  const res = await props.fetcher(`/blueprint/master/${encodeURIComponent(uuid.value)}`)
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (my !== seq) return
  loading.value = false
  if (!body?.success) { error.value = '讀取藍圖失敗。'; return }
  bp.value = body.data
  loadMaterialZh(bp.value)
}
function open(b, { material = '', initialTab = 'recipe' } = {}) {
  if (!b?.uuid) return
  uuid.value = b.uuid
  brief.value = b
  highlight.value = material
  bp.value = null
  tab.value = initialTab
  openRef.value = true
  load()
}
function openMissions() {
  const b = bp.value
  missionsRef.value?.open({ uuid: b._id || uuid.value, name: b.name, name_zh: b.name_zh, output_type: b.output_type })
}
function fmtQty(m) {
  if (m.quantity_scu != null) return `${m.quantity_scu} SCU`
  if (m.quantity != null) return `× ${m.quantity}`
  return '—'
}
defineExpose({ open, close: () => { openRef.value = false } })
</script>

<style scoped>
.bpd-tabs { display: flex; gap: .25rem; border-bottom: 1px solid var(--sf-border); margin-bottom: 1rem; overflow-x: auto; }
.bpd-tab { border: 0; background: none; padding: .5rem .9rem; font-weight: 700; color: var(--sf-text); position: relative; white-space: nowrap; }
.bpd-tab:hover { color: var(--sf-text-strong); }
.bpd-tab.active { color: var(--sf-accent-text, var(--sf-accent)); }
.bpd-tab.active::after { content: ''; position: absolute; left: .6rem; right: .6rem; bottom: -1px; height: 3px; border-radius: 3px 3px 0 0; background: var(--sf-accent); }
.bpd-h { font-size: var(--sf-fs-md); font-weight: 800; color: var(--sf-text-strong); margin-bottom: .5rem; }
.bpd-mat { display: flex; justify-content: space-between; gap: .75rem; padding: .4rem .3rem; border-bottom: 1px solid var(--sf-border); }
.bpd-mat--hit { background: rgba(var(--sf-accent-2-rgb), .12); border-radius: .3rem; }
.bpd-mat__q { font-weight: 700; color: var(--sf-text-strong); white-space: nowrap; }
.bpd-warn { color: var(--sf-accent-2); font-size: var(--sf-fs-sm); }
</style>
