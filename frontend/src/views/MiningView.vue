<!--
  後台的「礦物參考查詢」頁。畫面與計算都在
  components/MiningLookup.vue，這裡只負責接上後台的身分（apiFetch）
  與頁面標題/說明。玩家頁的「礦物」分頁掛的是同一個元件，但帶的是
  玩家 token —— 一份實作，兩個入口（跟 BlueprintCalculator.vue 是同一個
  做法）。
-->
<template>
  <div>
    <div class="d-flex align-items-center mb-3">
      <h5 class="mb-0 fw-bold">
        <i class="bi bi-gem me-2 text-primary"></i>礦物參考查詢
      </h5>
      <FieldHint class="ms-2" text="這是靜態的礦床成分/機率對照表（資料來源：scunpacked-data，隨遊戲改版同步更新），不是玩家實際掃描到的即時回波數值——那是遊戲端隨機生成的，無法從外部資料源取得，僅供查詢參考。中文礦物名稱為人工整理的最佳猜測，較冷門的礦物可能不是官方正式譯名。" />
    </div>

    <MiningLookup :fetcher="apiFetch" />
  </div>
</template>

<script setup>
import { apiFetch } from '@/api'
import FieldHint from '@/components/FieldHint.vue'
import MiningLookup from '@/components/MiningLookup.vue'
</script>
