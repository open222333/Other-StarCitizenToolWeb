<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold">
        <i class="bi bi-journal-text me-2 text-primary"></i>操作紀錄
      </h5>
      <button class="btn btn-outline-secondary btn-sm" :disabled="loading" @click="reload(offset)">
        <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
        <i v-else class="bi bi-arrow-clockwise me-1"></i>重新整理
      </button>
    </div>

    <!-- 搜尋卡：條件照列表欄位排（見 components/AdminSearchCard.vue） -->
    <AdminSearchCard :active="hasActiveFilters" @clear="resetFilters">
      <AdminSearchField label="時間" :for-id="sinceId" col="col-12 col-md-6 col-xl-4">
        <div class="input-group input-group-sm">
          <input :id="sinceId" v-model="since" type="datetime-local" class="form-control" aria-label="時間（從）"
            @change="reload(0)">
          <span class="input-group-text">到</span>
          <input :id="untilId" v-model="until" type="datetime-local" class="form-control" aria-label="時間（到）"
            @change="reload(0)">
        </div>
      </AdminSearchField>
      <AdminSearchField label="操作者" for-id="log-username" col="col-6 col-md-3 col-xl-3">
        <MultiSelectFilter id="log-username" :model-value="selectedUsernames" label="操作者" :options="usernameOptions" block placeholder="全部"
          @update:model-value="onUsernamesChange" />
      </AdminSearchField>
      <AdminSearchField label="動作" for-id="log-action" col="col-6 col-md-3 col-xl-3">
        <MultiSelectFilter id="log-action" :model-value="selectedActions" label="動作" :options="actionOptions" block placeholder="全部"
          @update:model-value="onActionsChange" />
      </AdminSearchField>
      <AdminSearchField label="結果" for-id="log-result" col="col-6 col-md-3 col-xl">
        <MultiSelectFilter id="log-result" :model-value="selectedResults" label="結果" :options="resultOptions" block placeholder="全部"
          @update:model-value="onResultsChange" />
      </AdminSearchField>
    </AdminSearchCard>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3 sortable-th" role="button" tabindex="0"
                  @click="toggleSort" @keydown.enter="toggleSort">
                  時間
                  <i class="bi ms-1" :class="sortDir === 'asc' ? 'bi-sort-up' : 'bi-sort-down'"></i>
                </th>
                <th>操作者</th>
                <th>動作</th>
                <th>詳細</th>
                <th>IP 來源</th>
                <th class="pe-3">結果</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="6" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="6" class="text-center py-4">
                  <span class="text-warning">
                    <i class="bi bi-exclamation-triangle me-1"></i>讀取紀錄失敗。
                  </span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!logs.length">
                <td colspan="6" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的紀錄。' : '尚無紀錄' }}
                </td>
              </tr>
              <tr v-for="l in logs" :key="l._id" v-else>
                <td class="ps-3 text-muted small">{{ fmtDate(l.created_at) }}</td>
                <td class="fw-semibold">{{ l.username }}</td>
                <td>{{ l.action }}</td>
                <td class="text-muted small">{{ l.detail || '—' }}</td>
                <td class="small font-monospace text-nowrap">{{ l.ip || '—' }}</td>
                <td class="pe-3">
                  <span :class="`badge bg-${l.success ? 'success' : 'danger'}`">
                    {{ l.success ? '成功' : '失敗' }}
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- ── 分頁 ────────────────────────────────────────────── -->
    <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mt-2">
      <div class="small text-muted">
        共 {{ total }} 筆<span v-if="total"> · 第 {{ offset + 1 }}–{{ Math.min(offset + limit, total) }} 筆</span>
      </div>
      <div class="btn-group btn-group-sm">
        <button class="btn btn-outline-secondary" :disabled="offset === 0 || loading"
          @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn btn-outline-secondary" :disabled="offset + limit >= total || loading"
          @click="reload(offset + limit)">下一頁</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { logApi } from '@/api'
import AdminSearchCard from '@/components/AdminSearchCard.vue'
import AdminSearchField from '@/components/AdminSearchField.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'

const logs       = ref([])
const total       = ref(0)
const limit       = 50
const offset      = ref(0)
const loading     = ref(false)
const loadFailed  = ref(false)

const usernameOptions = ref([])
const actionOptions   = ref([])
const resultOptions   = [{ value: '1', label: '成功' }, { value: '0', label: '失敗' }]

const selectedUsernames = ref([])
const selectedActions   = ref([])
const selectedResults   = ref([])
const since = ref('')
const until = ref('')
const sortDir = ref('desc')

const sinceId = 'log-since'
const untilId = 'log-until'

const hasActiveFilters = computed(() => !!(
  selectedUsernames.value.length || selectedActions.value.length ||
  selectedResults.value.length || since.value || until.value))

const fmtDate = (d) => d ? new Date(d).toLocaleString('zh-TW') : '—'

// datetime-local 給的是「使用者瀏覽器當地時間、沒有時區資訊」的字串，直接送給
// 後端會被誤判成 UTC（見 app/log/view.py 的 _parse_dt）。用 Date 物件轉一次
// toISOString() 才會正確換算成 UTC，篩出來的區間才會跟使用者看到的時鐘對得上。
function toUtcIso(localValue) {
  if (!localValue) return ''
  const d = new Date(localValue)
  return isNaN(d) ? '' : d.toISOString()
}

function toggleSort() {
  sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  reload(0)
}

// 這三個都是「選項變了就重新查」，不用 v-model + watch —— 用明確的
// change handler 一次做完「更新選取狀態」跟「重新查詢」兩件事，
// 不用擔心 v-model 跟額外監聽器混用時事件有沒有真的兩邊都觸發到。
function onUsernamesChange(values) {
  selectedUsernames.value = values
  reload(0)
}
function onActionsChange(values) {
  selectedActions.value = values
  reload(0)
}
function onResultsChange(values) {
  selectedResults.value = values
  reload(0)
}

function resetFilters() {
  selectedUsernames.value = []
  selectedActions.value = []
  selectedResults.value = []
  since.value = ''
  until.value = ''
  reload(0)
}

async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  const res = await logApi.list({
    username: selectedUsernames.value,
    action:   selectedActions.value,
    success:  selectedResults.value,
    since:    toUtcIso(since.value),
    until:    toUtcIso(until.value),
    sort_dir: sortDir.value,
    limit, offset: newOffset,
  })
  if (res && res.ok) {
    const body = await res.json()
    logs.value = body.data || []
    total.value = body.total || 0
  } else {
    logs.value = []
    loadFailed.value = true
  }
  loading.value = false
}

async function loadFilterOptions() {
  const [uRes, aRes] = await Promise.all([logApi.usernames(), logApi.actions()])
  if (uRes && uRes.ok) usernameOptions.value = (await uRes.json()).data || []
  if (aRes && aRes.ok) actionOptions.value = (await aRes.json()).data || []
}

onMounted(() => {
  loadFilterOptions()
  reload(0)
})
</script>

<style scoped>
.sortable-th { cursor: pointer; user-select: none; }
.sortable-th:hover { color: var(--bs-primary); }
</style>
