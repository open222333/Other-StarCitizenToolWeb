<!--
  「倉庫」分頁的共用搜尋卡（物品名稱／物品類型／星系／行星／地點）。倉庫分頁頂端只有這一張，
  同一組條件同時篩「物品庫存」、展開的「庫存紀錄」，名稱＋類型也帶給展開的「物品資料」
  （後端查物品主檔，見 ItemDataBrowser.vue）；「只看買得到」只給物品資料用，展開時才顯示。

  物品庫存、庫存紀錄是純前端篩選：兩份清單都整包載在記憶體裡（個人庫存最多幾百筆、
  紀錄上限 200 筆），改條件就即時反應。名稱比對英文＋中文（含即符合），類型比對 item_type。

  地點選項＝rows（兩份清單合起來）出現過的地點＋父層給的 knownLocations（地點資料庫裡可存放的地點），
  所以庫存還是空的時候星系／行星／地點也有選項；
  物品類型選項由父層給（物品主檔的全部類型，物品資料也要用）。
-->
<template>
  <div class="card scifi-card sf-search mb-2">
    <div class="card-body py-2">
      <div class="row g-2 align-items-end">
        <div class="col-12 col-md-6 col-lg-3">
          <label class="form-label small fw-semibold mb-1" for="wh-q">物品名稱</label>
          <input id="wh-q" type="search" class="form-control form-control-sm" placeholder="輸入物品名稱…"
            autocomplete="off" :value="q" @input="$emit('update:q', $event.target.value)">
        </div>
        <div class="col-12 col-md-6 col-lg-3">
          <label class="form-label small fw-semibold mb-1" for="wh-type">物品類型</label>
          <MultiSelectFilter id="wh-type" :model-value="types" :options="typeOptions" label="物品類型"
            placeholder="全部" block searchable @update:model-value="$emit('update:types', $event)" />
        </div>

        <LocationAreaFilter :names="locationNames" :loc-label="locLabel" col-class="col-12 col-sm-4 col-lg-2"
          :systems="systems" :planets="planets" :locations="locations"
          @update:systems="$emit('update:systems', $event)"
          @update:planets="$emit('update:planets', $event)"
          @update:locations="$emit('update:locations', $event)" />
      </div>

      <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
        <div v-if="showBuyable" class="form-check mb-0 me-2">
          <input id="wh-buyable" class="form-check-input" type="checkbox" :checked="buyable"
            @change="$emit('update:buyable', $event.target.checked)">
          <label class="form-check-label" for="wh-buyable">只看買得到</label>
        </div>
        <span v-if="active" class="form-text py-0 my-0">
          <template v-for="(c, i) in counts" :key="c.label">
            <template v-if="i"> · </template>{{ c.label }} {{ c.matched }} / {{ c.total }} 筆
          </template>
        </span>
        <button class="btn btn-sm btn-warning ms-auto" :disabled="!active" @click="clear">清除</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import LocationAreaFilter from '@/components/LocationAreaFilter.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'

const props = defineProps({
  // 用來產生地點選項的資料列（物品庫存＋庫存紀錄合起來）
  rows:      { type: Array,  required: true },
  // 其他已知地點（名稱字串陣列，地點資料庫的可存放地點），併進地點選項
  knownLocations: { type: Array, default: () => [] },
  q:         { type: String, default: '' },
  types:     { type: Array,  default: () => [] },
  // 物品類型的選項（字串陣列）
  typeOptions: { type: Array, default: () => [] },
  // 星系／行星／地點：多選，空陣列 = 全部（比對規則見 utils/locationArea.js 的 matchArea）
  systems:   { type: Array, default: () => [] },
  planets:   { type: Array, default: () => [] },
  locations: { type: Array, default: () => [] },
  // 各清單篩選後剩幾筆：[{ label, matched, total }]，由父層算好傳進來（父層才知道完整的篩選規則）
  counts:    { type: Array,  default: () => [] },
  // 地點的顯示文字（英文＋中文對照），由父層的 locLabel 提供
  locLabel:  { type: Function, default: (v) => v },
  // 「只看買得到」：只有物品資料用得到（UEX 有購買地點），物品資料展開時才顯示
  buyable:     { type: Boolean, default: false },
  showBuyable: { type: Boolean, default: false },
})

const emit = defineEmits(['update:q', 'update:types', 'update:systems', 'update:planets', 'update:locations',
  'update:buyable'])

const active = computed(() => !!(props.q.trim() || props.types.length || props.systems.length
  || props.planets.length || props.locations.length || (props.showBuyable && props.buyable)))

const locationNames = computed(() =>
  [...new Set([...props.rows.map(r => r.location), ...props.knownLocations].filter(Boolean))])

function clear() {
  emit('update:q', '')
  emit('update:types', [])
  emit('update:systems', [])
  emit('update:planets', [])
  emit('update:locations', [])
  emit('update:buyable', false)
}
</script>
