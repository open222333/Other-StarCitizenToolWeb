<!--
  艦隊統計晶片（戰術小隊編輯畫面與唯讀畫面的艦隊標題列共用）：船數、人數、各職位人數、
  空位（船的建議乘員減船上人數）、沒有駕駛的船數；有缺的用警示色。計算見 utils/squadBoard.js 的 fleetStats。
-->
<template>
  <div class="fsc">
    <span class="sf-chip">{{ st.ships }} 艘船</span>
    <span class="sf-chip">{{ st.people }} 人</span>
    <span v-for="(n, r) in st.roles" :key="r" class="sf-chip sf-chip--accent">{{ r }} {{ n }}</span>
    <span v-if="st.emptySeats" class="sf-chip sf-chip--warn">空位 {{ st.emptySeats }}</span>
    <span v-if="st.noPilot" class="sf-chip sf-chip--warn">{{ st.noPilot }} 艘缺駕駛</span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { fleetStats } from '@/utils/squadBoard'

const props = defineProps({ fleet: { type: Object, required: true } })
const st = computed(() => fleetStats(props.fleet))
</script>

<style scoped>
.fsc { display: flex; flex-wrap: wrap; gap: .25rem; }
</style>
