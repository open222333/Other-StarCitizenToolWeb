<!--
  後台的「藍圖材料試算」頁。畫面與計算都在
  components/BlueprintCalculator.vue，這裡只負責接上後台的身分（apiFetch）
  與庫存來源（公會共享庫）。玩家頁掛的是同一個元件，但帶的是玩家 token
  與個人庫 —— 一份實作，兩個入口。
-->
<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold">
        <i class="bi bi-calculator me-2 text-primary"></i>藍圖材料試算
      </h5>
    </div>

    <p class="small text-muted">
      選一張藍圖後填入現有材料數量，會算出最多可以做幾個、卡在哪一種材料，
      以及做到目標數量還缺多少。「從公會共享庫帶入」會把公會庫現有的量填進去。
    </p>

    <BlueprintCalculator :fetcher="apiFetch" :stock-loader="loadGuildStock"
      stock-label="公會共享庫" />
  </div>
</template>

<script setup>
import { apiFetch } from '@/api'
import BlueprintCalculator from '@/components/BlueprintCalculator.vue'

/**
 * 讀公會共享庫裡這些材料的現有量。
 *
 * 刻意「每個材料一次查詢」而不是「撈整個庫存再比對」：庫存列表有
 * limit 上限（200），公會庫大起來之後整撈會漏掉東西，而漏掉會靜默地
 * 算出偏低的可做數量 —— 那比慢幾百毫秒糟糕得多。材料種類通常不到 10，
 * 而且是並行送出的。
 */
async function loadGuildStock(rows) {
  const targets = rows.filter(row => row.itemUuid)
  if (!targets.length) return []

  const responses = await Promise.all(targets.map(row =>
    apiFetch(`/inventory/?owner_type=guild&item_id=${encodeURIComponent(row.itemUuid)}&limit=200`)))

  const stockRows = []
  for (let i = 0; i < targets.length; i++) {
    const res = responses[i]
    if (!res) continue
    const data = await res.json().catch(() => null)
    if (!data?.success) continue
    // 只收「這次查的那個材料」的列。後端本來就會按 item_id 過濾，這裡再擋一次
    // 是因為漏掉的後果是**靜默高估**：同一批列被多次累加，畫面會說可以做
    // 更多個，而使用者要到實際製造時才發現材料不夠。
    stockRows.push(...(data.data || []).filter(stock => stock.item_id === targets[i].itemUuid))
  }
  return stockRows
}
</script>
