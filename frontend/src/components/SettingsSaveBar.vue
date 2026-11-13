<!--
  後台「系統設定」各卡片共用的儲存列：左邊「儲存」「取消變更」＋狀態（有未儲存的變更／已儲存），右邊「恢復預設」。
  恢復預設會覆蓋全站設定，所以按下去先在原地問一次（不用跳視窗），再按「確定恢復」才送出。
  用法：<SettingsSaveBar :dirty :saving :can-reset @save @cancel @reset />（沒有恢復預設就不傳 can-reset、不聽 reset）
-->
<template>
  <div class="ssb d-flex flex-wrap align-items-center gap-2">
    <button type="button" class="btn btn-primary btn-sm" :disabled="saving || !dirty" @click="emit('save')">
      <span v-if="saving" class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>
      <i v-else class="bi bi-check-lg me-1" aria-hidden="true"></i>儲存</button>
    <button type="button" class="btn btn-outline-secondary btn-sm" :disabled="saving || !dirty" @click="emit('cancel')">取消變更</button>
    <span class="ssb__state small" :class="dirty ? 'ssb__state--dirty' : 'text-body-secondary'" aria-live="polite">
      <template v-if="dirty"><i class="bi bi-circle-fill me-1" aria-hidden="true"></i>有未儲存的變更</template>
      <template v-else-if="savedText">{{ savedText }}</template>
    </span>
    <template v-if="resettable">
      <span v-if="confirming" class="ms-auto d-inline-flex flex-wrap align-items-center gap-2">
        <span class="small text-danger"><i class="bi bi-exclamation-triangle-fill me-1" aria-hidden="true"></i>{{ resetWarning }}</span>
        <button type="button" class="btn btn-warning btn-sm" :disabled="saving" @click="confirming = false; emit('reset')">確定恢復</button>
        <button type="button" class="btn btn-outline-secondary btn-sm" @click="confirming = false">取消</button>
      </span>
      <button v-else type="button" class="btn btn-outline-warning btn-sm ms-auto" :disabled="saving || !canReset"
        @click="confirming = true"><i class="bi bi-arrow-counterclockwise me-1" aria-hidden="true"></i>恢復預設</button>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  dirty: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  // 有「恢復預設」按鈕
  resettable: { type: Boolean, default: false },
  // 目前不是預設值（是預設就不能按）
  canReset: { type: Boolean, default: false },
  resetWarning: { type: String, default: '會換回程式預設，目前的設定會被覆蓋' },
  // 沒有變更時顯示的文字，例如「上次更新：…」
  savedText: { type: String, default: '' },
})
const emit = defineEmits(['save', 'cancel', 'reset'])
const confirming = ref(false)
</script>

<style scoped>
.ssb { padding-top: .75rem; border-top: 1px solid var(--bs-border-color); }
.ssb__state--dirty { color: var(--bs-warning-text-emphasis, #997404); font-weight: 600; }
.ssb__state--dirty .bi { font-size: .55rem; vertical-align: middle; }
</style>
