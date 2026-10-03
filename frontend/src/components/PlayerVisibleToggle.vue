<!--
  「玩家頁面顯示」開關（後台各遊戲資料庫頁共用：藍圖、任務、礦床、礦物、採礦地點、
  艦船、地點）。資料欄位與規則見 src/models/visibility.py：
    player_visible（實際結果）、player_visible_auto（依名稱自動判斷）、
    player_hidden_reason（自動判斷成不顯示的原因）、player_visible_override（手動設定）。

  切換 → PUT /item/visibility/<dataset>/<id>，成功後把新的欄位寫回 row（同一個物件，
  列表會跟著更新）並 emit('updated', state)。手動設定過的顯示「手動」，按 ↺ 回到自動。
  admin／operator 才能切換，其他角色只看。
-->
<template>
  <span class="d-inline-flex align-items-center gap-1 text-nowrap" @click.stop @keydown.stop>
    <span class="form-check form-switch mb-0 d-inline-block">
      <input class="form-check-input" type="checkbox" role="switch" :checked="visible"
        :disabled="!canWrite || saving" :title="title" :aria-label="`玩家頁面顯示：${visible ? '顯示' : '不顯示'}`"
        @change="save($event.target.checked)">
    </span>
    <span v-if="overridden" class="badge text-bg-secondary" :title="title">手動</span>
    <button v-if="overridden && canWrite" type="button" class="btn btn-link btn-sm p-0 lh-1"
      :disabled="saving" title="回到自動判斷" aria-label="回到自動判斷" @click="save(null)">
      <i class="bi bi-arrow-counterclockwise"></i>
    </button>
    <span v-else-if="!overridden && !visible && row.player_hidden_reason" class="small text-muted reason"
      :title="row.player_hidden_reason">{{ row.player_hidden_reason }}</span>
    <span v-if="error" class="small text-danger">{{ error }}</span>
  </span>
</template>

<script setup>
import { computed, ref } from 'vue'
import { visibilityApi } from '@/api'
import { useAuthStore } from '@/stores/auth'

const props = defineProps({
  dataset: { type: String, required: true },
  docId: { type: String, required: true },
  row: { type: Object, required: true },
})
const emit = defineEmits(['updated'])

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')
const saving = ref(false)
const error = ref('')

const visible = computed(() => props.row.player_visible !== false)
const overridden = computed(() => props.row.player_visible_override === true
  || props.row.player_visible_override === false)
const title = computed(() => {
  if (overridden.value) {
    const auto = props.row.player_visible_auto === false ? '不顯示' : '顯示'
    return `手動設定；自動判斷為${auto}${props.row.player_hidden_reason ? `（${props.row.player_hidden_reason}）` : ''}`
  }
  return props.row.player_hidden_reason ? `自動判斷不顯示：${props.row.player_hidden_reason}` : '自動判斷'
})

async function save(value) {
  // 切回跟自動判斷一樣的值就直接當成「回到自動」，不留一筆多餘的手動設定
  const autoVisible = props.row.player_visible_auto !== false
  const target = value !== null && value === autoVisible ? null : value
  saving.value = true
  error.value = ''
  const res = await visibilityApi.set(props.dataset, props.docId, target)
  const body = res ? await res.json().catch(() => null) : null
  if (res?.ok && body?.success) {
    Object.assign(props.row, body.data)
    emit('updated', body.data)
  } else {
    error.value = body?.message || '儲存失敗'
  }
  saving.value = false
}
</script>

<style scoped>
.reason { max-width: 10rem; overflow: hidden; text-overflow: ellipsis; }
</style>
