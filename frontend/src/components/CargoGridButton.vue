<!--
  艦船資料列上的「貨艙網格」按鈕＋跳出視窗（我的艦隊、登記船艦資料、查詢持有資訊的船艦列用）：
  有貨物網格資料（sc-cargo.space，GET /starmap/nav/cargo-grids，utils/navBase.js 共用一份）的船才出現按鈕，
  按了跳出視窗用 3D 檢視（components/CargoView3D.vue）看網格；可以切「空網格／自動裝滿」，有非官方版面時也能切換。
-->
<template>
  <button v-if="grid" type="button" class="btn btn-sm btn-info" :class="buttonClass"
    :aria-label="`${name} 的貨艙網格`" aria-haspopup="dialog" @click="open = true">
    <i class="bi bi-boxes me-1"></i>網格</button>
  <Teleport v-if="grid" to="body">
    <div class="scifi-page cgb-host">
      <SfModal :id="uid" v-model:open="open" :title="`${name} 貨艙網格`" icon="bi bi-boxes" width="1100px">
        <template v-if="open">
          <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
            <div class="btn-group btn-group-sm" role="group" aria-label="顯示">
              <button type="button" class="btn btn-subtab" :class="{ active: !filled }" :aria-pressed="!filled ? 'true' : 'false'"
                @click="filled = false">空網格</button>
              <button type="button" class="btn btn-subtab" :class="{ active: filled }" :aria-pressed="filled ? 'true' : 'false'"
                @click="filled = true">自動裝滿</button>
            </div>
            <div v-if="grid.unofficial" class="btn-group btn-group-sm" role="group" aria-label="版面">
              <button type="button" class="btn btn-subtab" :class="{ active: layout === 'official' }" @click="layout = 'official'">官方</button>
              <button type="button" class="btn btn-subtab" :class="{ active: layout === 'unofficial' }" @click="layout = 'unofficial'">非官方</button>
            </div>
            <span class="sf-chip sf-chip--accent mb-0">容量 {{ fmtNum(capacity) }} SCU</span>
            <span v-if="filled && fillText" class="sf-chip mb-0">{{ fillText }}</span>
          </div>
          <CargoView3D :ships="viewShips" />
        </template>
      </SfModal>
    </div>
  </Teleport>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import SfModal from '@/components/SfModal.vue'
import CargoView3D from '@/components/CargoView3D.vue'
import { gridByVehicle, useNavBase } from '@/utils/navBase'
import { SIZES, autoFill, gridCapacity } from '@/utils/cargoPack'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 載具主檔 uuid */
  vehicleUuid: { type: String, default: '' },
  name: { type: String, default: '' },
  buttonClass: { type: String, default: '' },
})

const uid = `cgb-${Math.random().toString(36).slice(2, 8)}`
const open = ref(false)
const filled = ref(true)
const layout = ref('official')
const grid = computed(() => (props.vehicleUuid ? gridByVehicle.value.get(props.vehicleUuid) : null) || null)
const grids = computed(() => grid.value?.[layout.value]?.grids || grid.value?.official?.grids || [])
const capacity = computed(() => gridCapacity(grids.value))
const fill = computed(() => (filled.value ? autoFill(grids.value) : null))
const fillText = computed(() => SIZES.filter(s => fill.value?.counts?.[s]).reverse()
  .map(s => `${s} SCU × ${fill.value.counts[s]}`).join('、'))
const fmtNum = v => (v == null ? '—' : Math.round(v).toLocaleString('en-US'))
const viewShips = computed(() => [{
  id: `${props.vehicleUuid}-${layout.value}`, label: props.name, grids: grids.value, boxes: fill.value?.boxes || [],
}])

// 網格資料整站共用一份，第一個按鈕掛上來時載入
onMounted(() => { useNavBase(props.fetcher).loadCargoGrids() })
</script>

<style scoped>
/* 視窗 Teleport 到 body，外面包一層 .scifi-page 才吃得到玩家頁的主題樣式；本身不佔版面 */
.cgb-host { display: contents; }
</style>
