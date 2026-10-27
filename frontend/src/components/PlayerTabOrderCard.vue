<!--
  後台「系統設定」：玩家頁分頁的排列順序（全站設定，GET／PUT /player/settings/tab-order）。
  拖拉或用上下箭頭排，按「儲存」才送出；「恢復預設」＝存空清單（照 utils/playerTabs.js 的順序）。
  玩家自己在「個人資料」勾掉的分頁另外存在各自帳號上，跟這個順序無關。
-->
<template>
  <div class="card border-0 shadow-sm mb-3">
    <div class="card-body p-4">
      <h6 class="fw-semibold mb-3"><i class="bi bi-arrow-down-up me-1"></i>玩家頁分頁順序</h6>
      <div v-if="message" class="alert py-2" :class="messageType === 'danger' ? 'alert-danger' : 'alert-success'">{{ message }}</div>
      <div v-if="loading" class="text-muted small">載入中…</div>
      <template v-else>
        <ol class="tab-order list-unstyled mb-3">
          <li v-for="(tab, i) in rows" :key="tab.key" class="tab-order__row"
            :class="{ 'is-dragging': dragIndex === i, 'is-over': overIndex === i && dragIndex !== i }"
            :draggable="canWrite" @dragstart="onDragStart(i, $event)" @dragover.prevent="overIndex = i"
            @dragleave="overIndex === i && (overIndex = -1)" @drop.prevent="onDrop(i)" @dragend="dragIndex = overIndex = -1">
            <i v-if="canWrite" class="bi bi-grip-vertical tab-order__grip" aria-hidden="true"></i>
            <span class="tab-order__no">{{ i + 1 }}</span>
            <i :class="tab.icon" class="tab-order__icon"></i>
            <span class="flex-grow-1">{{ tab.label }}</span>
            <template v-if="canWrite">
              <button type="button" class="btn btn-sm btn-info" :disabled="i === 0"
                :aria-label="`${tab.label} 往前`" @click="move(i, i - 1)"><i class="bi bi-arrow-up"></i></button>
              <button type="button" class="btn btn-sm btn-info" :disabled="i === rows.length - 1"
                :aria-label="`${tab.label} 往後`" @click="move(i, i + 1)"><i class="bi bi-arrow-down"></i></button>
            </template>
          </li>
        </ol>
        <div v-if="canWrite" class="d-flex flex-wrap gap-2">
          <button type="button" class="btn btn-primary btn-sm" :disabled="saving || !dirty" @click="save(rows.map(t => t.key))">
            <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>儲存
          </button>
          <button type="button" class="btn btn-secondary btn-sm" :disabled="saving || !dirty" @click="reset">取消變更</button>
          <button type="button" class="btn btn-warning btn-sm ms-auto" :disabled="saving || isDefault" @click="save([])">恢復預設</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { apiFetch } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { PLAYER_TABS, orderTabs } from '@/utils/playerTabs'

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')

const saved = ref([])       // 伺服器上的順序（空＝預設）
const rows = ref([...PLAYER_TABS])
const loading = ref(true)
const saving = ref(false)
const message = ref('')
const messageType = ref('success')
const dragIndex = ref(-1)
const overIndex = ref(-1)

const savedKeys = computed(() => orderTabs(PLAYER_TABS, saved.value).map(t => t.key).join(','))
const dirty = computed(() => rows.value.map(t => t.key).join(',') !== savedKeys.value)
const isDefault = computed(() => !dirty.value && savedKeys.value === PLAYER_TABS.map(t => t.key).join(','))

async function readJson(res) {
  return res ? res.json().catch(() => null) : null
}

async function load() {
  loading.value = true
  const res = await apiFetch('/player/settings/tab-order')
  const data = await readJson(res)
  loading.value = false
  if (!res?.ok || !data?.success) {
    messageType.value = 'danger'
    message.value = data?.message || '讀取失敗。'
    return
  }
  saved.value = data.data.tab_order || []
  reset()
}

function reset() {
  rows.value = orderTabs(PLAYER_TABS, saved.value)
}

function move(from, to) {
  if (to < 0 || to >= rows.value.length || from === to) return
  const list = [...rows.value]
  const [item] = list.splice(from, 1)
  list.splice(to, 0, item)
  rows.value = list
  message.value = ''
}

function onDragStart(i, event) {
  dragIndex.value = i
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', String(i))
}

function onDrop(i) {
  if (dragIndex.value >= 0) move(dragIndex.value, i)
  dragIndex.value = overIndex.value = -1
}

async function save(keys) {
  saving.value = true
  message.value = ''
  const res = await apiFetch('/player/settings/tab-order', { method: 'PUT', body: JSON.stringify({ tab_order: keys }) })
  const data = await readJson(res)
  saving.value = false
  if (!res?.ok || !data?.success) {
    messageType.value = 'danger'
    message.value = data?.message || '儲存失敗。'
    return
  }
  saved.value = data.data.tab_order || []
  reset()
  messageType.value = 'success'
  message.value = keys.length ? '已儲存。' : '已恢復預設順序。'
}

onMounted(load)
</script>

<style scoped>
.tab-order { display: flex; flex-direction: column; gap: .35rem; max-width: 32rem; }
.tab-order__row {
  display: flex; align-items: center; gap: .6rem;
  padding: .45rem .6rem; border: 1px solid var(--bs-border-color); border-radius: .5rem;
  background: var(--bs-body-bg);
}
.tab-order__row[draggable="true"] { cursor: grab; }
.tab-order__row.is-dragging { opacity: .45; }
.tab-order__row.is-over { border-color: var(--bs-primary); box-shadow: 0 0 0 2px rgba(var(--bs-primary-rgb), .25); }
.tab-order__grip { color: var(--bs-secondary-color); }
.tab-order__no { min-width: 1.5rem; text-align: right; color: var(--bs-secondary-color); }
.tab-order__icon { width: 1.25rem; text-align: center; }
</style>
