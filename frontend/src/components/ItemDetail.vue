<!--
  物品的詳細資料（後台「物品」、玩家頁「倉庫 › 物品資料」展開時用）：
  基本欄位（列表那筆就有）＋遊戲內說明與說明裡列出的數值（GET /item/<uuid>?with_stats=1，
  item_master.raw.description_data 原樣，見 src/models/item_stats.py 的 describe）＋
  購買／收購地點（ItemPriceDetail）。掛上去才查。
-->
<template>
  <div :class="player ? 'idt--player' : 'idt--admin'">
    <div class="idt-grid">
      <div v-for="f in fields" :key="f.label" class="idt-field">
        <span class="idt-field__label">{{ f.label }}</span>
        <span class="idt-field__value">{{ f.value }}</span>
      </div>
    </div>

    <div v-if="loading" class="small mb-2" :class="player ? 'sf-tree-info' : 'text-muted'">載入中…</div>
    <template v-else>
      <div v-if="detail.stats?.length" class="idt-grid">
        <div v-for="(s, i) in detail.stats" :key="i" class="idt-field">
          <span class="idt-field__label">{{ s.name }}</span>
          <span class="idt-field__value">{{ s.value }}</span>
        </div>
      </div>
      <div v-if="detail.description" class="idt-desc" :class="player ? 'sf-tree-info' : 'small text-muted'">
        {{ detail.description }}
      </div>
    </template>

    <ItemPriceDetail :item-uuid="item._id" :fetcher="fetcher" :player="player" :buy-only="buyOnly" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '@/api'
import ItemPriceDetail from '@/components/ItemPriceDetail.vue'
import { itemTypeLabel } from '@/utils/itemType'

const props = defineProps({
  /** 列表的那一筆（GET /item/ 回來的） */
  item: { type: Object, required: true },
  fetcher: { type: Function, default: apiFetch },
  player: { type: Boolean, default: false },
  /** 只顯示購買地點（玩家頁） */
  buyOnly: { type: Boolean, default: false },
})

const detail = ref({})
const loading = ref(false)

function fmtNum(v, digits = 2) {
  if (v === null || v === undefined || v === '') return '—'
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: digits })
}
const yesNo = v => (v === true ? '是' : v === false ? '否' : '—')

const fields = computed(() => {
  const it = props.item
  return [
    { label: '類型', value: itemTypeLabel(it.type, it.sub_type) || '—' },
    { label: '分類', value: it.classification || '—' },
    { label: '尺寸', value: it.size ?? '—' },
    { label: '等級', value: it.grade ?? '—' },
    { label: '製造商', value: it.manufacturer_name || it.manufacturer_code || '—' },
    { label: '體積', value: it.volume_scu ? `${fmtNum(it.volume_scu, 6)} SCU` : '—' },
    { label: '重量', value: it.mass ? `${fmtNum(it.mass)} kg` : '—' },
    { label: '可製造', value: yesNo(it.is_craftable) },
    { label: '可拾取', value: yesNo(it.is_lootable) },
    { label: '內部名稱', value: it.class_name || '—' },
  ]
})

onMounted(async () => {
  loading.value = true
  const res = await props.fetcher(`/item/${encodeURIComponent(props.item._id)}?with_stats=1`)
  const body = res?.ok ? await res.json().catch(() => null) : null
  loading.value = false
  if (body?.success) detail.value = body.data || {}
})
</script>

<style scoped>
.idt-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
  gap: .35rem .75rem;
  margin-bottom: .6rem;
}
.idt-field { display: flex; gap: .5rem; }
.idt-field__label { white-space: nowrap; }
.idt-field__value { font-weight: 600; word-break: break-word; }
.idt--player .idt-field__label { color: var(--sf-text-muted); }
.idt--player .idt-field__value { color: var(--sf-text-strong); }
.idt--admin .idt-field { font-size: .875rem; }
.idt--admin .idt-field__label { color: var(--bs-secondary-color); }
.idt--admin .idt-field__value { color: var(--bs-body-color); }
.idt-desc { white-space: pre-line; margin-bottom: .6rem; }
</style>
