<!--
  後台「新聞」頁的標籤上架／下架（後端 GET/PUT /news/admin/tag-settings，見 src/models/news.py）：
  下架＝帶這個標籤的新聞對玩家隱藏（列表、全文、篩選、搜尋都找不到），後台照常看得到。
  切換就存（失敗會還原），結果用 toast。
-->
<template>
  <div class="card shadow-sm border-0 mb-3">
    <div class="card-body p-0">
      <div class="d-flex align-items-center px-3 pt-3 pb-2">
        <h6 class="fw-semibold mb-0"><i class="bi bi-tags me-2 text-primary"></i>標籤上架</h6>
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
              <th class="text-center pe-3" style="width: 7rem">上架</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading && !rows.length"><td colspan="3" class="text-center py-4 text-muted">
              <span class="spinner-border spinner-border-sm me-2"></span>載入中…</td></tr>
            <tr v-else-if="!rows.length"><td colspan="3" class="text-center py-4 text-muted">尚無標籤</td></tr>
            <tr v-for="r in rows" :key="r.tag" :class="{ 'nts-off': !r.listed }">
              <td class="ps-3 fw-semibold">
                {{ r.tag }}
                <span v-if="!r.listed" class="badge text-bg-secondary ms-1"><i class="bi bi-eye-slash me-1"></i>已下架</span>
              </td>
              <td class="text-end">{{ r.count }}</td>
              <td class="text-center pe-3">
                <div class="form-check form-switch d-inline-block mb-0">
                  <input class="form-check-input" type="checkbox" role="switch" :checked="r.listed"
                    :disabled="!canWrite || busy.has(r.tag)" :aria-label="`${r.tag} 上架`" @change="save(r, $event.target)">
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { newsApi } from '@/api'
import { toast } from '@/utils/toast'

defineProps({ canWrite: { type: Boolean, default: false } })
const emit = defineEmits(['changed'])

const rows = ref([])
const loading = ref(false)
const busy = reactive(new Set())

async function load() {
  loading.value = true
  const res = await newsApi.tagSettings()
  const body = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!res?.ok || !body?.success) { toast(body?.message || '讀取標籤失敗', 'error'); return }
  rows.value = body.data || []
}
onMounted(load)

async function save(row, input) {
  const listed = input.checked
  busy.add(row.tag)
  const res = await newsApi.setTag({ tag: row.tag, listed })
  const body = res ? await res.json().catch(() => null) : null
  busy.delete(row.tag)
  if (!res?.ok || !body?.success) {
    toast(body?.message || '儲存失敗', 'error')
    input.checked = !listed          // 資料沒改，Vue 不會重畫，自己還原
    return
  }
  row.listed = body.data.listed
  toast(`「${row.tag}」已${row.listed ? '上架' : '下架'}`)
  emit('changed')
}
defineExpose({ load })
</script>

<style scoped>
.nts-off td { color: var(--bs-secondary-color); }
</style>
