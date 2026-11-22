<!--
  藍圖「品質試算」跳出視窗（資料庫 › 藍圖、艦長室 › 藍圖共用；內容是 components/BlueprintQuality.vue）。
  用法：<BlueprintQualityModal ref="q" :fetcher="..." /> → q.value.open({ uuid, name })
-->
<template>
  <SfModal id="bp-quality" v-model:open="openRef" :title="`品質試算 · ${name}`" icon="bi bi-sliders" width="1100px">
    <BlueprintQuality v-if="openRef && uuid" :key="uuid" :fetcher="fetcher" :blueprint-uuid="uuid" />
  </SfModal>
</template>

<script setup>
import { ref } from 'vue'
import SfModal from '@/components/SfModal.vue'
import BlueprintQuality from '@/components/BlueprintQuality.vue'

defineProps({
  /** 帶身分的 fetch（玩家頁 playerFetch） */
  fetcher: { type: Function, required: true },
})
const openRef = ref(false)
const uuid = ref('')
const name = ref('')
function open(bp) {
  if (!bp?.uuid) return
  uuid.value = bp.uuid
  name.value = bp.name || ''
  openRef.value = true
}
defineExpose({ open, close: () => { openRef.value = false } })
</script>
