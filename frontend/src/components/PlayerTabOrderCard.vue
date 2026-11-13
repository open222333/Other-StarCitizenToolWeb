<!--
  後台「系統設定」：玩家頁分頁的排列順序與開放狀態（全站設定，GET／PUT /player/settings/tab-order，
  存在 app_settings 的 player_tab_order、player_tab_access）。
  拖拉或用上下箭頭排；每個分頁選「開放／預設不顯示／不開放」：
    開放＝照常顯示（玩家可以在「個人資料」自己勾掉）；預設不顯示＝玩家要在「個人資料」自己打開；不開放＝玩家看不到也打不開。
  有下層分頁（子功能）的分頁（我的、資料庫、航線、工具箱）可以展開，子功能一樣能排順序、設定開放或不開放
  （存成「主分頁.下層分頁」，例如 items.missions，見 utils/playerTabs.js 的 subKey／orderSubTabs）；
  子功能全部不開放時，整個分頁在玩家頁也不顯示。
  按「儲存」才送出；「恢復預設」＝程式預設順序、全部開放。「個人資料」一定開放。
  玩家自己的勾選另外存在各自帳號上（players.hidden_tabs／shown_tabs）。
-->
<template>
  <div class="card border-0 shadow-sm mb-3">
    <div class="card-body p-4">
      <h6 class="fw-semibold mb-1"><i class="bi bi-arrow-down-up me-1"></i>玩家頁分頁順序與開放</h6>
      <p class="text-body-secondary small mb-3">拖拉或用箭頭排順序。開放＝照常顯示（玩家可自己藏）；預設不顯示＝玩家要在「個人資料」自己打開；不開放＝玩家看不到。有子功能的分頁按「子功能」展開，子功能可以排順序、設成不開放。</p>
      <div v-if="message && messageType === 'danger'" class="alert alert-danger py-2">{{ message }}</div>
      <div v-if="loading" class="text-muted small">載入中…</div>
      <template v-else>
        <div v-if="hasSubs" class="d-flex gap-2 mb-2">
          <button type="button" class="btn btn-sm btn-outline-secondary" @click="expandAll(true)">
            <i class="bi bi-arrows-expand me-1"></i>全部展開</button>
          <button type="button" class="btn btn-sm btn-outline-secondary" @click="expandAll(false)">
            <i class="bi bi-arrows-collapse me-1"></i>全部收合</button>
        </div>
        <ol class="tab-order list-unstyled mb-3">
          <li v-for="(tab, i) in rows" :key="tab.key" class="tab-order__item">
            <div class="tab-order__row"
              :class="{ 'is-dragging': dragIndex === i, 'is-over': overIndex === i && dragIndex !== i }"
              :draggable="canWrite" @dragstart="onDragStart(i, $event)" @dragover.prevent="overIndex = i"
              @dragleave="overIndex === i && (overIndex = -1)" @drop.prevent="onDrop(i)" @dragend="dragIndex = overIndex = -1">
              <i v-if="canWrite" class="bi bi-grip-vertical tab-order__grip" aria-hidden="true"></i>
              <span class="tab-order__no">{{ i + 1 }}</span>
              <i :class="tab.icon" class="tab-order__icon"></i>
              <span class="flex-grow-1" :class="{ 'text-body-secondary text-decoration-line-through': tabOff(tab) }">
                {{ tab.label }}
                <span v-if="tab.member" class="badge text-bg-light border ms-1">會員</span>
              </span>
              <button v-if="tab.subTabs" type="button" class="btn btn-sm btn-link tab-order__toggle text-nowrap"
                :aria-expanded="!!expanded[tab.key]" :aria-controls="`tab-order-subs-${tab.key}`" @click="expanded[tab.key] = !expanded[tab.key]">
                <i class="bi me-1" :class="expanded[tab.key] ? 'bi-chevron-up' : 'bi-chevron-down'"></i>子功能 {{ openSubCount(tab) }}／{{ tab.subTabs.length }}
              </button>
              <select v-model="access[tab.key]" class="form-select form-select-sm tab-order__access"
                :disabled="!canWrite || tab.key === 'profile'" :aria-label="`${tab.label} 開放狀態`" @change="message = ''">
                <option v-for="o in ACCESS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
              <div v-if="canWrite" class="btn-group btn-group-sm">
                <button type="button" class="btn btn-outline-secondary" :disabled="i === 0"
                  :aria-label="`${tab.label} 往前`" @click="move(i, i - 1)"><i class="bi bi-arrow-up"></i></button>
                <button type="button" class="btn btn-outline-secondary" :disabled="i === rows.length - 1"
                  :aria-label="`${tab.label} 往後`" @click="move(i, i + 1)"><i class="bi bi-arrow-down"></i></button>
              </div>
            </div>
            <!-- 子功能（下層分頁）：順序＋開放／不開放 -->
            <ol v-if="tab.subTabs && expanded[tab.key]" :id="`tab-order-subs-${tab.key}`" class="tab-order__subs list-unstyled">
              <li v-for="(sub, j) in subRows[tab.key]" :key="sub.key" class="tab-order__sub">
                <span class="tab-order__no">{{ j + 1 }}</span>
                <span class="flex-grow-1" :class="{ 'text-body-secondary text-decoration-line-through': subOff(tab, sub) }">
                  {{ sub.label }}
                  <span v-if="sub.member" class="badge text-bg-light border ms-1">會員</span>
                </span>
                <select v-model="access[subKey(tab.key, sub.key)]" class="form-select form-select-sm tab-order__access"
                  :disabled="!canWrite" :aria-label="`${tab.label} › ${sub.label} 開放狀態`" @change="message = ''">
                  <option v-for="o in SUB_ACCESS_OPTIONS" :key="o.value" :value="o.value">{{ o.label }}</option>
                </select>
                <div v-if="canWrite" class="btn-group btn-group-sm">
                  <button type="button" class="btn btn-outline-secondary" :disabled="j === 0"
                    :aria-label="`${sub.label} 往前`" @click="moveSub(tab.key, j, j - 1)"><i class="bi bi-arrow-up"></i></button>
                  <button type="button" class="btn btn-outline-secondary" :disabled="j === subRows[tab.key].length - 1"
                    :aria-label="`${sub.label} 往後`" @click="moveSub(tab.key, j, j + 1)"><i class="bi bi-arrow-down"></i></button>
                </div>
              </li>
              <li v-if="!openSubCount(tab)" class="small text-danger px-2 pt-1">
                <i class="bi bi-exclamation-triangle-fill me-1"></i>子功能全部不開放，玩家頁不會顯示這個分頁</li>
            </ol>
          </li>
        </ol>
        <SettingsSaveBar v-if="canWrite" :dirty="dirty" :saving="saving" resettable :can-reset="!isDefault"
          reset-warning="順序換回預設、全部開放" @save="save(orderPayload(), accessPayload())" @cancel="reset" @reset="save([], {})" />
      </template>
    </div>
  </div>
</template>

<script setup>
import SettingsSaveBar from '@/components/SettingsSaveBar.vue'
import { toast } from '@/utils/toast'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import { useAuthStore } from '@/stores/auth'
import { PLAYER_TABS, normalizeTabAccess, orderSubTabs, orderTabs, subKey } from '@/utils/playerTabs'

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')

const saved = ref([])       // 伺服器上的順序（空＝預設）
const rows = ref([...PLAYER_TABS])
const ACCESS_OPTIONS = [
  { value: 'open', label: '開放' },
  { value: 'hidden', label: '預設不顯示' },
  { value: 'closed', label: '不開放' },
]
// 子功能只有開放／不開放（「預設不顯示」要玩家在個人資料自己打開，那裡只列主分頁）
const SUB_ACCESS_OPTIONS = ACCESS_OPTIONS.filter(o => o.value !== 'hidden')
const TABS_WITH_SUBS = PLAYER_TABS.filter(t => t.subTabs?.length)
const hasSubs = TABS_WITH_SUBS.length > 0
// 全部的設定代號：主分頁＋「主分頁.下層分頁」
const ALL_KEYS = [...PLAYER_TABS.map(t => t.key), ...TABS_WITH_SUBS.flatMap(t => t.subTabs.map(s => subKey(t.key, s.key)))]
const savedAccess = ref({})   // 伺服器上的開放狀態（只有不是開放的）
const access = reactive(Object.fromEntries(ALL_KEYS.map(k => [k, 'open'])))
const accessKey = obj => ALL_KEYS.map(k => `${k}:${obj[k] || 'open'}`).join(',')
const subRows = reactive(Object.fromEntries(TABS_WITH_SUBS.map(t => [t.key, [...t.subTabs]])))
const expanded = reactive({})
const expandAll = on => TABS_WITH_SUBS.forEach(t => { expanded[t.key] = on })
const openSubCount = tab => (tab.subTabs || []).filter(s => access[subKey(tab.key, s.key)] !== 'closed').length
const subOff = (tab, sub) => access[subKey(tab.key, sub.key)] === 'closed'
const tabOff = tab => access[tab.key] === 'closed' || (tab.subTabs?.length > 0 && !openSubCount(tab))

// 要存的順序：主分頁，加上順序跟程式預設不同的子功能（「主分頁.下層分頁」整串）
function orderPayload() {
  const out = rows.value.map(t => t.key)
  for (const t of TABS_WITH_SUBS) {
    const keys = subRows[t.key].map(x => x.key)
    if (keys.join(',') !== t.subTabs.map(x => x.key).join(',')) out.push(...keys.map(k => subKey(t.key, k)))
  }
  return out
}
// 要存的開放狀態：只送不是開放的（子功能的「預設不顯示」不存在，選單裡也沒有）
function accessPayload() {
  return Object.fromEntries(ALL_KEYS.filter(k => access[k] && access[k] !== 'open').map(k => [k, access[k]]))
}
// 伺服器上的順序換成跟 orderPayload() 同樣的格式，方便比對有沒有改過
function canonicalOrder(order) {
  const out = orderTabs(PLAYER_TABS, order).map(t => t.key)
  for (const t of TABS_WITH_SUBS) {
    const keys = orderSubTabs(t, order).map(x => x.key)
    if (keys.join(',') !== t.subTabs.map(x => x.key).join(',')) out.push(...keys.map(k => subKey(t.key, k)))
  }
  return out.join(',')
}
const loading = ref(true)
const saving = ref(false)
const message = ref('')
const messageType = ref('success')
// 錯誤留在卡片裡（要修的地方）；成功改用全站的 toast（utils/toast.js），不把卡片內容往下推
watch([message, messageType], ([m, t]) => {
  if (m && t !== 'danger') {
    toast(m, t)
    message.value = ''
  }
})
const dragIndex = ref(-1)
const overIndex = ref(-1)

const savedKeys = computed(() => canonicalOrder(saved.value))
const dirty = computed(() => orderPayload().join(',') !== savedKeys.value
  || accessKey(access) !== accessKey(savedAccess.value))
const emit = defineEmits(['dirty'])
watch(dirty, v => emit('dirty', v))
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
  // 舊的分頁（倉庫、藍圖、艦隊、任務）已經併進「我的」「資料庫」，換成新的分頁
  savedAccess.value = normalizeTabAccess(data.data.tab_access)
  reset()
}

function reset() {
  rows.value = orderTabs(PLAYER_TABS, saved.value)
  for (const t of TABS_WITH_SUBS) subRows[t.key] = orderSubTabs(t, saved.value)
  for (const k of ALL_KEYS) {
    const v = savedAccess.value[k] || 'open'
    // 子功能沒有「預設不顯示」
    access[k] = k.includes('.') && v === 'hidden' ? 'open' : v
  }
  // 有子功能被改過（排序或不開放）的分頁預設展開，一眼看得到
  for (const t of TABS_WITH_SUBS) {
    if (expanded[t.key] === undefined) {
      expanded[t.key] = t.subTabs.some(x => access[subKey(t.key, x.key)] !== 'open')
        || subRows[t.key].map(x => x.key).join(',') !== t.subTabs.map(x => x.key).join(',')
    }
  }
}

function moveSub(tabKey, from, to) {
  const list = subRows[tabKey]
  if (to < 0 || to >= list.length || from === to) return
  list.splice(to, 0, list.splice(from, 1)[0])
  message.value = ''
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
  savedAccess.value = normalizeTabAccess(data.data.tab_access)
  reset()
  messageType.value = 'success'
  message.value = keys.length || Object.keys(accessMap).length ? '已儲存。' : '已恢復預設（順序、全部開放）。'
}

onMounted(load)
</script>

<style scoped>
.tab-order { display: flex; flex-direction: column; gap: .35rem; max-width: 44rem; }
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
.tab-order__toggle { padding-inline: .25rem; text-decoration: none; }
.tab-order__subs { display: flex; flex-direction: column; gap: .25rem; margin: .3rem 0 .2rem 2.6rem; }
.tab-order__sub {
  display: flex; align-items: center; gap: .6rem; padding: .3rem .6rem;
  border: 1px dashed var(--bs-border-color); border-radius: .4rem; background: var(--bs-tertiary-bg);
}
</style>
