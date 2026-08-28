<!--
  庫存清單的篩選區（物品／地點），倉庫的「物品庫存」與「庫存紀錄」共用。

  刻意做成純前端篩選：兩份清單都已經整包載在記憶體裡（個人庫存最多幾百筆、
  紀錄上限 200 筆），改選項就即時反應，不用再打一次 API。哪天資料量大到
  需要伺服器端分頁，這裡的 v-model 介面不用變，只要把 rows 換成後端結果。

  選項是從 rows 自己推導出來的 —— 只列出「這份清單裡真的出現過」的物品與
  地點，不是把整個物品主檔（1 萬多筆）塞進下拉選單。所以選了絕不會是空結果。
-->
<template>
  <div class="card scifi-card mb-2">
    <div class="card-body py-2">
      <div class="row g-2 align-items-end">
        <div class="col-12 col-md-5">
          <label class="form-label small fw-semibold mb-1">物品</label>
          <select class="form-select form-select-sm"
                  :value="item" @change="$emit('update:item', $event.target.value)">
            <option value="">全部（{{ itemOptions.length }} 種）</option>
            <option v-for="o in itemOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>

        <div class="col-12 col-md-5">
          <label class="form-label small fw-semibold mb-1">地點</label>
          <select class="form-select form-select-sm"
                  :value="location" @change="$emit('update:location', $event.target.value)">
            <option value="">全部（{{ locationOptions.length }} 個）</option>
            <option v-for="o in locationOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </div>

        <div class="col-12 col-md-2 d-flex gap-2">
          <button class="btn btn-sm btn-scifi-outline flex-grow-1"
                  :disabled="!item && !location" @click="clear">清除</button>
        </div>
      </div>

      <div v-if="item || location" class="form-text py-0 mt-1">
        顯示 {{ matched }} / {{ rows.length }} 筆
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  // 要篩選的原始資料（個人庫存列 或 庫存紀錄列）
  rows:     { type: Array,  required: true },
  item:     { type: String, default: '' },   // '' = 全部
  location: { type: String, default: '' },
  // 篩選後剩幾筆，由父層算好傳進來（父層才知道完整的篩選規則）
  matched:  { type: Number, default: 0 },
  // 地點的顯示文字（英文＋中文對照），由父層的 locLabel 提供
  locLabel: { type: Function, default: (v) => v },
})

const emit = defineEmits(['update:item', 'update:location'])

/** 去重＋排序，回傳 { value, label } 陣列。 */
function options(keyField, labelFor) {
  const seen = new Map()
  for (const r of props.rows) {
    const v = r[keyField]
    if (!v || seen.has(v)) continue
    seen.set(v, labelFor(r))
  }
  return [...seen.entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, 'zh-Hant'))
}

// 用 item_id 而不是 item_name 當 value：名稱可能重複（不同 uuid 同名），
// 用 id 才不會一選就把別的物品也篩進來。
const itemOptions = computed(() => options('item_id', (r) =>
  r.item_name_zh ? `${r.item_name}（${r.item_name_zh}）` : (r.item_name || r.item_id)
))

const locationOptions = computed(() => options('location', (r) => props.locLabel(r.location)))

function clear() {
  emit('update:item', '')
  emit('update:location', '')
}
</script>
