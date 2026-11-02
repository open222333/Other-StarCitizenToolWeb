<!--
  後台「系統設定」：玩家頁分頁的排列順序與開放狀態（全站設定，GET／PUT /player/settings/tab-order，
  存在 app_settings 的 player_tab_order、player_tab_access）。
  拖拉或用上下箭頭排；每個分頁選「開放／預設不顯示／不開放」：
    開放＝照常顯示（玩家可以在「個人資料」自己勾掉）；預設不顯示＝玩家要在「個人資料」自己打開；不開放＝玩家看不到也打不開。
  按「儲存」才送出；「恢復預設」＝程式預設順序、全部開放。「個人資料」一定開放。
  玩家自己的勾選另外存在各自帳號上（players.hidden_tabs／shown_tabs）。
-->
<template>
  <div class="card border-0 shadow-sm mb-3">
    <div class="card-body p-4">
      <h6 class="fw-semibold mb-3"><i class="bi bi-arrow-down-up me-1"></i>玩家頁分頁順序與開放</h6>
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
            <span class="flex-grow-1" :class="{ 'text-body-secondary text-decoration-line-through': access[tab.key] === 'closed' }">{{ tab.label }}</span>
            <select v-model="access[tab.key]" class="form-select form-select-sm tab-order__access"
              :disabled="!canWrite || tab.key === 'profile'" :aria-label="`${tab.label} 開放狀態`" @change="message = ''">
              <option v-for="o in ACCESS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
            <template v-if="canWrite">
              <button type="button" class="btn btn-sm btn-info" :disabled="i === 0"
                :aria-label="`${tab.label} 往前`" @click="move(i, i - 1)"><i class="bi bi-arrow-up"></i></button>
              <button type="button" class="btn btn-sm btn-info" :disabled="i === rows.length - 1"
                :aria-label="`${tab.label} 往後`" @click="move(i, i + 1)"><i class="bi bi-arrow-down"></i></button>
            </template>
          </li>
        </ol>
        <div v-if="canWrite" class="d-flex flex-wrap gap-2">
          <button type="button" class="btn btn-primary btn-sm" :disabled="saving || !dirty" @click="save(rows.map(t => t.key), access)">
            <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>儲存
          </button>
          <button type="button" class="btn btn-secondary btn-sm" :disabled="saving || !dirty" @click="reset">取消變更</button>
          <button type="button" class="btn btn-warning btn-sm ms-auto" :disabled="saving || isDefault" @click="save([], {})">恢復預設</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { apiFetch } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { PLAYER_TABS, orderTabs } from '@/utils/playerTabs'

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')

const saved = ref([])       // 伺服器上的順序（空＝預設）
const rows = ref([...PLAYER_TABS])
const ACCESS_OPTIONS = [
  { value: 'open', label: '開放' },
  { value: 'hidden', label: '預設不顯示' },
  { value: 'closed', label: '不開放' },
]
const savedAccess = ref({})   // 伺服器上的開放狀態（只有不是開放的）
const access = reactive(Object.fromEntries(PLAYER_TABS.map(t => [t.key, 'open'])))
const accessKey = obj => PLAYER_TABS.map(t => `${t.key}:${obj[t.key] || 'open'}`).join(',')
const loading = ref(true)
const saving = ref(false)
const message = ref('')
const messageType = ref('success')
const dragIndex = ref(-1)
const overIndex = ref(-1)

const savedKeys = computed(() => orderTabs(PLAYER_TABS, saved.value).map(t => t.key).join(','))
const dirty = computed(() => rows.value.map(t => t.key).join(',') !== savedKeys.value
  || accessKey(access) !== accessKey(savedAccess.value))
const isDefault = computed(() => !dirty.value && savedKeys.value === PLAYER_TABS.map(t => t.key).join(',')
  && !Object.keys(savedAccess.value).length)

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
  savedAccess.value = data.data.tab_access || {}
  reset()
}

function reset() {
  rows.value = orderTabs(PLAYER_TABS, saved.value)
  for (const t of PLAYER_TABS) access[t.key] = savedAccess.value[t.key] || 'open'
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

async function save(keys, accessMap) {
  saving.value = true
  message.value = ''
  const res = await apiFetch('/player/settings/tab-order', { method: 'PUT', body: JSON.stringify({ tab_order: keys, tab_access: { ...accessMap } }) })
  const data = await readJson(res)
  saving.value = false
  if (!res?.ok || !data?.success) {
    messageType.value = 'danger'
    message.value = data?.message || '儲存失敗。'
    return
  }
  saved.value = data.data.tab_order || []
  savedAccess.value = data.data.tab_access || {}
  reset()
  messageType.value = 'success'
  message.value = keys.length || Object.keys(accessMap).length ? '已儲存。' : '已恢復預設（順序、全部開放）。'
}

onMounted(load)
</script>

<style scoped>
.tab-order { display: flex; flex-direction: column; gap: .35rem; max-width: 40rem; }
.tab-order__access { width: 8.5rem; flex: 0 0 auto; }
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
