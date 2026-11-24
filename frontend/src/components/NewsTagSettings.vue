<!--
  後台「新聞」頁的標籤顯示方式（後端 GET/PUT /news/admin/tag-settings，見 src/models/news.py）：
  - 分類列（main）：玩家頁新聞分類列直接顯示，可以上下調整順序
  - 更多（more）：收在玩家頁「更多」裡；外部 API 帶進來的新標籤沒設定過，一律在這裡
  - 下架（hidden）：帶這個標籤的新聞對玩家隱藏（列表、全文、篩選、搜尋都找不到），後台照常看得到
  切換就存（失敗會還原），結果用 toast。
-->
<template>
  <div class="card shadow-sm border-0 mb-3">
    <div class="card-body p-0">
      <div class="d-flex align-items-center px-3 pt-3 pb-2">
        <h6 class="fw-semibold mb-0"><i class="bi bi-tags me-2 text-primary"></i>標籤顯示</h6>
        <button type="button" class="btn btn-outline-secondary btn-sm ms-auto" :disabled="loading" @click="load">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
          <i v-else class="bi bi-arrow-clockwise me-1"></i>重新整理</button>
      </div>
      <div class="table-responsive">
        <table class="table table-hover align-middle mb-0">
          <thead class="table-light">
            <tr>
              <th class="ps-3">標籤</th>
              <th class="text-end">則數</th>
              <th class="text-center">顯示</th>
              <th class="text-center pe-3" style="width: 6rem">順序</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && !rows.length"><td colspan="4" class="text-center py-4 text-muted">
              <span class="spinner-border spinner-border-sm me-2"></span>載入中…</td></tr>
            <tr v-else-if="!rows.length"><td colspan="4" class="text-center py-4 text-muted">尚無標籤</td></tr>
            <tr v-for="r in rows" :key="r.tag" :class="{ 'nts-off': r.display === 'hidden' }">
              <td class="ps-3 fw-semibold">{{ r.tag }}</td>
              <td class="text-end">{{ r.count }}</td>
              <td class="text-center">
                <div class="btn-group btn-group-sm" role="group" :aria-label="`${r.tag} 顯示方式`">
                  <button v-for="o in OPTIONS" :key="o.key" type="button" class="btn"
                    :class="r.display === o.key ? o.on : 'btn-outline-secondary'" :aria-pressed="r.display === o.key ? 'true' : 'false'"
                    :disabled="!canWrite || busy.has(r.tag)" @click="setDisplay(r, o.key)"><i :class="o.icon" class="me-1"></i>{{ o.label }}</button>
                </div>
              </td>
              <td class="text-center pe-3 text-nowrap">
                <template v-if="r.display === 'main'">
                  <button type="button" class="btn btn-sm btn-outline-secondary me-1" :disabled="!canWrite || mainIndex(r) === 0 || moving"
                    :aria-label="`${r.tag} 往前`" @click="move(r, -1)"><i class="bi bi-arrow-up"></i></button>
                  <button type="button" class="btn btn-sm btn-outline-secondary" :disabled="!canWrite || mainIndex(r) === mains.length - 1 || moving"
                    :aria-label="`${r.tag} 往後`" @click="move(r, 1)"><i class="bi bi-arrow-down"></i></button>
                </template>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { newsApi } from '@/api'
import { toast } from '@/utils/toast'

defineProps({ canWrite: { type: Boolean, default: false } })
const emit = defineEmits(['changed'])

const OPTIONS = [
  { key: 'main', label: '分類列', icon: 'bi bi-pin-angle', on: 'btn-primary' },
  { key: 'more', label: '更多', icon: 'bi bi-three-dots', on: 'btn-info' },
  { key: 'hidden', label: '下架', icon: 'bi bi-eye-slash', on: 'btn-secondary' },
]
const LABEL = { main: '分類列', more: '更多', hidden: '下架' }
const rows = ref([])
const loading = ref(false)
const moving = ref(false)
const busy = reactive(new Set())
const mains = computed(() => rows.value.filter(r => r.display === 'main'))
const mainIndex = r => mains.value.indexOf(r)
const RANK = { main: 0, more: 1, hidden: 2 }
function resort() {
  rows.value = [...rows.value].sort((a, b) => RANK[a.display] - RANK[b.display]
    || (a.display === 'main' ? a.order - b.order : 0) || b.count - a.count || a.tag.localeCompare(b.tag))
}

async function load() {
  loading.value = true
  const res = await newsApi.tagSettings()
  const body = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!res?.ok || !body?.success) { toast(body?.message || '讀取標籤失敗', 'error'); return }
  rows.value = body.data || []
}
onMounted(load)

async function put(row, display, order) {
  busy.add(row.tag)
  const res = await newsApi.setTag({ tag: row.tag, display, ...(order != null ? { order } : {}) })
  const body = res ? await res.json().catch(() => null) : null
  busy.delete(row.tag)
  if (!res?.ok || !body?.success) { toast(body?.message || '儲存失敗', 'error'); return false }
  row.display = body.data.display
  row.order = body.data.order
  row.listed = body.data.listed
  return true
}

async function setDisplay(row, display) {
  if (row.display === display) return
  // 改成分類列：排在分類列最後
  const order = display === 'main' ? Math.max(-1, ...mains.value.map(r => r.order).filter(n => n < 999)) + 1 : null
  if (!(await put(row, display, order))) return
  resort()
  toast(`「${row.tag}」改為${LABEL[display]}`)
  emit('changed')
}

// 分類列換順序：整排重新編號（0、1、2…），只送有變的
async function move(row, d) {
  const list = [...mains.value]
  const i = list.indexOf(row)
  const j = i + d
  if (j < 0 || j >= list.length) return
  ;[list[i], list[j]] = [list[j], list[i]]
  moving.value = true
  for (const [n, r] of list.entries()) {
    if (r.order !== n && !(await put(r, 'main', n))) break
  }
  moving.value = false
  resort()
  emit('changed')
}
defineExpose({ load })
</script>

<style scoped>
.nts-off td { color: var(--bs-secondary-color); }
</style>
