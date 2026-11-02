<!--
  「新增／異動」第 2 步的物品清單（components/StockWizard.vue）：照上層的搜尋條件（query：名稱、類型、拆解材料、
  物品範圍）列出物品主檔（GET /item/，後端分頁），每一列可以勾選，表頭可以整頁全選。
  勾了哪些由上層管（selectedIds），這裡只發出 toggle(物品, 勾或不勾)；換頁、改條件都不會清掉已選的。
-->
<template>
  <SfState :loading="loading && !rows.length" :error="failed ? '讀取物品資料失敗。' : ''" :empty="!rows.length"
    empty-text="沒有符合條件的物品。" @retry="reload(offset)">
    <div class="ibp-list" :class="{ 'sf-list-loading': loading }">
      <label class="ibp-row ibp-head">
        <input type="checkbox" class="form-check-input" :checked="pageAll" :indeterminate.prop="pageSome"
          :disabled="!rows.length" aria-label="本頁全選" @change="pickPage($event.target.checked)">
        <span class="ibp-name">物品</span>
        <span class="ibp-opt">類型</span>
        <span class="ibp-opt ibp-num">尺寸</span>
        <span class="ibp-opt ibp-num">等級</span>
      </label>
      <label v-for="it in rows" :key="it._id" class="ibp-row" :class="{ 'is-picked': selectedIds.has(it._id) }">
        <input type="checkbox" class="form-check-input" :checked="selectedIds.has(it._id)"
          :aria-label="`選取 ${it.name_zh || it.name}`" @change="$emit('toggle', it, $event.target.checked)">
        <span class="ibp-name">
          <span class="fw-semibold">{{ it.name_zh || it.name }}</span>
          <span v-if="it.name_zh" class="ibp-muted ms-1">{{ it.name }}</span>
        </span>
        <span class="ibp-opt ibp-muted">{{ itemTypeLabel(it.type, it.sub_type) || '—' }}</span>
        <span class="ibp-opt ibp-num">{{ it.size ?? '—' }}</span>
        <span class="ibp-opt ibp-num">{{ it.grade ?? '—' }}</span>
      </label>
    </div>
    <SfPager class="mt-2" :total="total" :offset="offset" :limit="LIMIT" :loading="loading" @page="reload" />
  </SfState>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SfPager from '@/components/SfPager.vue'
import SfState from '@/components/SfState.vue'
import { itemTypeLabel, loadItemTypeZh } from '@/utils/itemType'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 顯示時才載入 */
  active: { type: Boolean, default: false },
  /** 搜尋條件 { q, types, dismantle, source（vehicle／personal／''） } */
  query: { type: Object, required: true },
  /** 已選的物品 _id */
  selectedIds: { type: Set, required: true },
})
const emit = defineEmits(['toggle'])

const LIMIT = 30
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const failed = ref(false)
let seq = 0

async function reload(nextOffset = 0) {
  offset.value = Math.max(0, nextOffset)
  loading.value = true
  failed.value = false
  const mine = ++seq
  const f = props.query
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset.value) })
  if (f.q?.trim()) params.set('q', f.q.trim())
  ;(f.types || []).forEach(v => params.append('type', v))
  ;(f.dismantle || []).forEach(v => params.append('dismantle', v))
  if (f.source) params.set('source', f.source)
  const res = await props.fetcher(`/item/?${params.toString()}`)
  const data = res ? await res.json().catch(() => null) : null
  if (mine !== seq) return
  loading.value = false
  if (!data?.success) {
    rows.value = []
    total.value = 0
    failed.value = true
    return
  }
  rows.value = data.data || []
  total.value = data.total || 0
  loadItemTypeZh(rows.value.map(r => r.type), rows.value.map(r => r.sub_type))
}

let timer = null
watch(() => JSON.stringify(props.query), () => {
  if (!props.active) return
  clearTimeout(timer)
  timer = setTimeout(() => reload(0), 300)
})
onBeforeUnmount(() => clearTimeout(timer))
watch(() => props.active, (on) => { if (on) reload(0) }, { immediate: true })

const pageAll = computed(() => rows.value.length > 0 && rows.value.every(r => props.selectedIds.has(r._id)))
const pageSome = computed(() => !pageAll.value && rows.value.some(r => props.selectedIds.has(r._id)))
function pickPage(on) {
  for (const it of rows.value) if (props.selectedIds.has(it._id) !== on) emit('toggle', it, on)
}
</script>

<style scoped>
.ibp-list { border: 1px solid var(--sf-border); border-radius: .5rem; overflow: hidden; }
.ibp-row {
  display: grid; grid-template-columns: 1.5rem minmax(0, 1fr) 12rem 3.5rem 3.5rem; gap: .5rem; align-items: center;
  padding: .4rem .75rem; margin: 0; border-top: 1px solid var(--sf-border); cursor: pointer; font-size: 1rem;
}
.ibp-row:first-child { border-top: 0; }
.ibp-row:hover { background: var(--sf-chip-bg); }
.ibp-row.is-picked { background: rgba(var(--sf-accent-rgb), .12); }
.ibp-head { font-weight: 600; background: var(--sf-chip-bg); cursor: default; }
.ibp-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ibp-muted { color: var(--sf-text-muted); }
.ibp-num { text-align: center; }
@media (max-width: 575.98px) {
  .ibp-row { grid-template-columns: 1.5rem minmax(0, 1fr); }
  .ibp-opt { display: none; }
  .ibp-name { white-space: normal; }
}
</style>
