<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-3">
      <h5 class="mb-0 fw-bold">
        <i class="bi bi-journal-text me-2 text-primary"></i>操作紀錄
      </h5>
      <button class="btn btn-outline-secondary btn-sm" :disabled="loading" @click="loadLogs">
        <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>
        <i v-else class="bi bi-arrow-clockwise me-1"></i>重新整理
      </button>
    </div>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th class="ps-3">時間</th>
                <th>操作者</th>
                <th>動作</th>
                <th>詳細</th>
                <th class="pe-3">結果</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="5" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="!logs.length">
                <td colspan="5" class="text-center py-4 text-muted">尚無紀錄</td>
              </tr>
              <tr v-for="l in logs" :key="l._id" v-else>
                <td class="ps-3 text-muted small">{{ fmtDate(l.created_at) }}</td>
                <td class="fw-semibold">{{ l.username }}</td>
                <td>{{ l.action }}</td>
                <td class="text-muted small">{{ l.detail || '—' }}</td>
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { logApi } from '@/api'

const logs    = ref([])
const loading = ref(false)
const fmtDate = (d) => d ? new Date(d).toLocaleString('zh-TW') : '—'

async function loadLogs() {
  loading.value = true
  const res = await logApi.list()
  if (res) { const d = await res.json(); logs.value = d.data || [] }
  loading.value = false
}

onMounted(loadLogs)
</script>
