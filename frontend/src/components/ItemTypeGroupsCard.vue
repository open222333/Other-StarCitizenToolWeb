<!--
  後台「系統設定」：物品類型分組（全站設定，GET／PUT /item/type-groups，存在 app_settings 的 item_type_groups）。
  物品類型的多選篩選（倉庫、新增／異動、物品頁）照這裡分段，可整組勾選；沒對到任何群組的類型歸「其他」。
  每組：名稱、類型（完整代碼，一個類型只能在一組）、前綴（例如 Char_Armor_，之後新增的同前綴類型自動歸進來）。
  按「儲存」才送出；「恢復預設」＝程式預設分組（src/models/app_setting.py 的 DEFAULT_ITEM_TYPE_GROUPS）。
-->
<template>
  <div class="card border-0 shadow-sm mb-3">
    <div class="card-body p-4">
      <h6 class="fw-semibold mb-1"><i class="bi bi-collection me-1"></i>物品類型分組</h6>
      <p class="text-body-secondary small mb-3">倉庫、新增／異動、物品頁的「物品類型」篩選照這裡分段，可以整組勾選。前綴（例如 Char_Armor_）會把之後新增的同前綴類型自動歸進來；沒對到的歸「其他」。</p>
      <div v-if="message && messageType === 'danger'" class="alert alert-danger py-2">{{ message }}</div>
      <div v-if="loading" class="text-muted small">載入中…</div>
      <template v-else>
        <ol class="itg list-unstyled mb-3">
          <li v-for="(g, i) in rows" :key="g.key" class="itg__row">
            <div class="d-flex flex-wrap align-items-center gap-2">
              <span class="itg__no">{{ i + 1 }}</span>
              <input v-model="g.label" type="text" maxlength="20" class="form-control form-control-sm itg__label"
                :disabled="!canWrite" :aria-label="`第 ${i + 1} 組名稱`" @input="message = ''">
              <span class="badge text-bg-secondary">{{ matchedOf(g).length }} 種</span>
              <template v-if="canWrite">
                <div class="btn-group btn-group-sm ms-auto">
                  <button type="button" class="btn btn-outline-secondary" :disabled="i === 0"
                    :aria-label="`第 ${i + 1} 組往前`" @click="move(i, i - 1)"><i class="bi bi-arrow-up"></i></button>
                  <button type="button" class="btn btn-outline-secondary" :disabled="i === rows.length - 1"
                    :aria-label="`第 ${i + 1} 組往後`" @click="move(i, i + 1)"><i class="bi bi-arrow-down"></i></button>
                </div>
                <button type="button" class="btn btn-sm btn-outline-danger" :aria-label="`刪除第 ${i + 1} 組`"
                  @click="rows.splice(i, 1); message = ''"><i class="bi bi-trash"></i></button>
              </template>
            </div>
            <div class="row g-2 mt-1">
              <div class="col-12 col-md-8">
                <label class="form-label small fw-semibold mb-1" :for="`itg-types-${g.key}`">類型</label>
                <MultiSelectFilter :id="`itg-types-${g.key}`" v-model="g.types" :options="optionsFor(g)"
                  :label="`第 ${i + 1} 組類型`" placeholder="未選" block searchable
                  :class="{ 'pe-none opacity-75': !canWrite }" @update:model-value="message = ''" />
              </div>
              <div class="col-12 col-md-4">
                <label class="form-label small fw-semibold mb-1" :for="`itg-prefix-${g.key}`">前綴</label>
                <input :id="`itg-prefix-${g.key}`" v-model="g.prefixText" type="text" class="form-control form-control-sm"
                  placeholder="Char_Armor_" :disabled="!canWrite" @input="message = ''">
              </div>
            </div>
          </li>
        </ol>
        <div v-if="others.length" class="mb-3">
          <span class="badge text-bg-secondary me-1">其他 {{ others.length }} 種</span>
          <span class="small text-body-secondary">{{ others.map(typeName).join('、') }}</span>
        </div>
        <button v-if="canWrite" type="button" class="btn btn-outline-success btn-sm mb-3" :disabled="rows.length >= MAX_GROUPS"
          @click="rows.push(newRow()); message = ''"><i class="bi bi-plus-lg me-1"></i>加群組</button>
        <SettingsSaveBar v-if="canWrite" :dirty="dirty" :saving="saving" resettable :can-reset="custom"
          reset-warning="換回程式預設的分組" @save="save(payload())" @cancel="reset" @reset="save([])" />
      </template>
    </div>
  </div>
</template>

<script setup>
import SettingsSaveBar from '@/components/SettingsSaveBar.vue'
import { toast } from '@/utils/toast'
import { computed, onMounted, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import { useAuthStore } from '@/stores/auth'
import { itemTypeZh, loadItemTypeZh, matchesGroup, setItemTypeGroups } from '@/utils/itemType'

// 跟後端 src/models/app_setting.py 一致
const MAX_GROUPS = 30

const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')

let keySeq = 0
const splitPrefixes = text => [...new Set((text || '').split(/[\s,，、]+/).map(t => t.trim()).filter(Boolean))]
const newRow = (g = {}) => ({ key: ++keySeq, label: g.label || '', types: [...(g.types || [])],
  prefixText: (g.prefixes || []).join(', ') })
const plainGroup = r => ({ label: r.label.trim(), types: [...r.types], prefixes: splitPrefixes(r.prefixText) })

const saved = ref([])
const custom = ref(false)
const rows = ref([])
const allTypes = ref([])
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

const typeName = (code) => {
  const zh = itemTypeZh(code)
  return zh && zh !== code ? `${zh}（${code}）` : code
}
const payload = () => rows.value.map(plainGroup)
const dirty = computed(() => JSON.stringify(payload()) !== JSON.stringify(saved.value))
const emit = defineEmits(['dirty'])
watch(dirty, v => emit('dirty', v))

// 選項：還沒被別組選走的類型（一個類型只能在一組）；不帶 group，選單不分段
function optionsFor(g) {
  const taken = new Set(rows.value.filter(r => r !== g).flatMap(r => r.types))
  return allTypes.value.filter(t => !taken.has(t) || g.types.includes(t)).map(t => ({ value: t, label: typeName(t) }))
}
// 這組實際涵蓋的類型（照前端判斷：排前面的群組優先）
const owners = computed(() => {
  const groups = rows.value.map(plainGroup)
  const map = new Map()
  for (const t of allTypes.value) {
    const i = groups.findIndex(g => matchesGroup(g, t))
    if (i >= 0) map.set(t, i)
  }
  return map
})
const matchedOf = g => allTypes.value.filter(t => owners.value.get(t) === rows.value.indexOf(g))
const others = computed(() => allTypes.value.filter(t => !owners.value.has(t)))

async function readJson(res) {
  return res ? res.json().catch(() => null) : null
}

function applyData(data) {
  saved.value = (data.groups || []).map(g => ({ label: g.label, types: [...(g.types || [])], prefixes: [...(g.prefixes || [])] }))
  custom.value = !!data.custom
  setItemTypeGroups(saved.value)
  reset()
}

async function load() {
  loading.value = true
  const [res, typesRes] = await Promise.all([apiFetch('/item/type-groups'), apiFetch('/item/types')])
  const data = await readJson(res)
  const types = await readJson(typesRes)
  loading.value = false
  if (!res?.ok || !data?.success) {
    messageType.value = 'danger'
    message.value = data?.message || '讀取失敗。'
    return
  }
  allTypes.value = (types?.data || []).filter(t => typeof t === 'string').sort()
  loadItemTypeZh(allTypes.value)
  applyData(data.data)
}

function reset() {
  rows.value = saved.value.map(newRow)
}

function move(from, to) {
  if (to < 0 || to >= rows.value.length || from === to) return
  const list = [...rows.value]
  const [item] = list.splice(from, 1)
  list.splice(to, 0, item)
  rows.value = list
  message.value = ''
}

async function save(groups) {
  saving.value = true
  message.value = ''
  const res = await apiFetch('/item/type-groups', { method: 'PUT', body: JSON.stringify({ groups }) })
  const data = await readJson(res)
  saving.value = false
  if (!res?.ok || !data?.success) {
    messageType.value = 'danger'
    message.value = data?.message || '儲存失敗。'
    return
  }
  applyData(data.data)
  messageType.value = 'success'
  message.value = groups.length ? '已儲存。' : '已恢復預設分組。'
}

onMounted(load)
</script>

<style scoped>
.itg { display: flex; flex-direction: column; gap: .5rem; max-width: 48rem; }
.itg__row { padding: .6rem .75rem; border: 1px solid var(--bs-border-color); border-radius: .5rem; background: var(--bs-body-bg); }
.itg__no { min-width: 1.5rem; text-align: right; color: var(--bs-secondary-color); }
.itg__label { max-width: 14rem; }
</style>
