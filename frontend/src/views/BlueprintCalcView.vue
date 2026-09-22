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
const STOCK_CONCURRENCY = 6

async function loadGuildStock(rows) {
  // 同一個 item_uuid 只查一次：配方裡同一種材料可能出現兩筆
  // （craftCalc 會把需求合併），查兩次會讓同一批庫存被累加兩遍 → 靜默高估。
  const targets = [...new Map(
    rows.filter(row => row.itemUuid).map(row => [row.itemUuid, row]),
  ).values()]
  if (!targets.length) return { rows: [], failed: 0 }

  const stockRows = []
  let failed = 0

  // 分批送出而不是一次 Promise.all：材料多的配方（上限 200 種）會一次開出
  // 200 個請求，把瀏覽器的連線數與後端都打滿。
  for (let i = 0; i < targets.length; i += STOCK_CONCURRENCY) {
    const batch = targets.slice(i, i + STOCK_CONCURRENCY)
    const responses = await Promise.all(batch.map(row =>
      apiFetch(`/inventory/?owner_type=guild&item_id=${encodeURIComponent(row.itemUuid)}&limit=200`)))

    for (let j = 0; j < batch.length; j++) {
      const res = responses[j]
      const data = res ? await res.json().catch(() => null) : null
      // ⚠️ 讀失敗一定要算進 failed 並回報給呼叫端。
      //    靜默跳過的話那個材料的數量會留空 → 視為 0 → 「最多可做 0 個」
      //    並把它標成瓶頸，而畫面仍顯示資料可靠 —— 使用者無從得知是讀取失敗。
      if (!data?.success) { failed += 1; continue }
      // 只收「這次查的那個材料」的列（後端本來就會過濾，這裡再擋一次）
      stockRows.push(...(data.data || [])
        .filter(stock => stock.item_id === batch[j].itemUuid))
    }
  }
  return { rows: stockRows, failed }
}
</script>
