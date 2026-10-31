<!--
  後台「資料庫檢視」（唯讀）：遊戲資料、同步資料與系統紀錄的資料表，依類別列出，點一個看它的全部欄位、可以加條件篩選
  （見 src/models/data_browser.py 的 CATALOG、components/DataCollectionTable.vue）。
  網址 ?c=<資料表> 直接打開那一個。
-->
<template>
  <div>
    <h5 class="mb-3 fw-bold"><i class="bi bi-database me-2 text-primary"></i>資料庫檢視</h5>
    <div class="row g-3">
      <div class="col-12 col-lg-3">
        <div class="card shadow-sm border-0">
          <div class="card-body p-2">
            <div v-if="loading" class="text-muted small p-2">載入中...</div>
            <div v-else-if="failed" class="text-warning small p-2">讀取失敗。</div>
            <template v-for="cat in catalog" v-else :key="cat.category">
              <div class="small fw-semibold text-muted px-2 pt-2 pb-1">{{ cat.category }}</div>
              <div class="list-group list-group-flush mb-1">
                <button v-for="c in cat.collections" :key="c.name" type="button"
                  class="list-group-item list-group-item-action d-flex justify-content-between align-items-center py-1 px-2 small"
                  :class="{ active: current === c.name }" @click="pick(c.name)">
                  <span>
                    {{ c.label }}
                    <span class="d-block font-monospace dbv-name">{{ c.name }}</span>
                  </span>
                  <span class="badge rounded-pill" :class="current === c.name ? 'text-bg-light' : 'text-bg-secondary'">{{ fmt(c.count) }}</span>
                </button>
              </div>
            </template>
          </div>
        </div>
      </div>
      <div class="col-12 col-lg-9">
        <DataCollectionTable v-if="current" :collection="current" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { dataApi } from '@/api'
import DataCollectionTable from '@/components/DataCollectionTable.vue'

const route = useRoute()
const router = useRouter()
const catalog = ref([])
const loading = ref(true)
const failed = ref(false)
const current = ref('')

function pick(name) {
  current.value = name
  router.replace({ query: { c: name } })
}
function fmt(n) {
  return Number(n || 0).toLocaleString('en-US')
}

onMounted(async () => {
  const res = await dataApi.collections()
  const body = res?.ok ? await res.json().catch(() => null) : null
  loading.value = false
  if (!body?.success) { failed.value = true; return }
  catalog.value = body.data || []
  const names = catalog.value.flatMap(c => c.collections.map(x => x.name))
  current.value = names.includes(route.query.c) ? route.query.c : (names[0] || '')
})
</script>

<style scoped>
.dbv-name { font-size: .7rem; opacity: .7; }
</style>
