<!--
  航線結果上方的工具列（「航線規劃」RoutePlanner、「合約分配」ContractPlanner 共用，待辦 B1）：
  顯示方式（航段表／總覽／3D 星圖）、總覽的排列方向（橫向／直向）、貨物規劃開關；右邊放各自的按鈕（default slot）。
  常數在 utils/routeRows.js（ROUTE_VIEWS、FLOW_DIRS），兩個規劃器各自記在自己的 localStorage。
  idPrefix：同一頁有好幾條（合約分配每個小隊一條）時，開關的 id 才不會重複。
-->
<template>
  <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
    <div class="btn-group btn-group-sm" role="group" aria-label="顯示方式">
      <button v-for="v in ROUTE_VIEWS" :key="v.key" type="button" class="btn btn-subtab text-nowrap"
        :class="{ active: view === v.key }" :aria-pressed="view === v.key ? 'true' : 'false'"
        @click="$emit('update:view', v.key)"><i :class="v.icon" class="me-1"></i>{{ v.label }}</button>
    </div>
    <!-- 總覽的排列方向：橫向（左右來回）／直向（上下來回） -->
    <div v-if="view === 'flow'" class="btn-group btn-group-sm" role="group" aria-label="總覽排列方向">
      <button v-for="d in FLOW_DIRS" :key="d.key" type="button" class="btn btn-subtab text-nowrap"
        :class="{ active: flowDir === d.key }" :aria-pressed="flowDir === d.key ? 'true' : 'false'"
        :title="d.title" @click="$emit('update:flowDir', d.key)"><i :class="d.icon" class="me-1"></i>{{ d.label }}</button>
    </div>
    <!-- 貨物規劃（可選）：每站設定裝卸，顯示貨艙用量與貨櫃拆法 -->
    <div class="form-check sf-check-btn mb-0 ms-md-2">
      <input :id="`${idPrefix}-cargo-plan`" :checked="cargoOn" class="form-check-input" type="checkbox"
        @change="$emit('update:cargoOn', $event.target.checked)">
      <label class="form-check-label" :for="`${idPrefix}-cargo-plan`">貨物規劃</label>
    </div>
    <slot />
  </div>
</template>

<script setup>
import { FLOW_DIRS, ROUTE_VIEWS } from '@/utils/routeRows'

defineProps({
  view: { type: String, required: true },
  flowDir: { type: String, required: true },
  cargoOn: { type: Boolean, default: false },
  idPrefix: { type: String, default: 'route' },
})
defineEmits(['update:view', 'update:flowDir', 'update:cargoOn'])
</script>
