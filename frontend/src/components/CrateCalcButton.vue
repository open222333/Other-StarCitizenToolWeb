<!--
  「貨櫃試算」按鈕＋跳出視窗（航線規劃結果用）：內容就是工具箱的 components/CrateCalculator.vue，
  總量預設帶 total（例如選的船貨艙容量），打開後可以自己改。
  視窗 Teleport 到 body（可以疊在航線結果視窗上面），外面包 .scifi-page 才吃得到玩家頁主題；Esc 只關最上層（useSheet）。
-->
<template>
  <button type="button" class="btn btn-sm btn-info" :class="buttonClass" aria-haspopup="dialog" @click="open = true">
    <i class="bi bi-box-seam me-1"></i>貨櫃試算</button>
  <Teleport to="body">
    <div class="scifi-page ccb-host">
      <SfModal :id="uid" v-model:open="open" title="貨櫃試算" icon="bi bi-box-seam" width="1100px">
        <CrateCalculator v-if="mounted" :id="`${uid}-calc`" :initial="total" card-class="card scifi-card" />
      </SfModal>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, watch } from 'vue'
import SfModal from '@/components/SfModal.vue'
import CrateCalculator from '@/components/CrateCalculator.vue'

defineProps({
  /** 預設總量（SCU） */
  total: { type: Number, default: 0 },
  buttonClass: { type: String, default: '' },
})

const uid = `ccb-${Math.random().toString(36).slice(2, 8)}`
const open = ref(false)
// 第一次打開才掛內容
const mounted = ref(false)
watch(open, v => { if (v) mounted.value = true })
</script>

<style scoped>
.ccb-host { display: contents; }
</style>
