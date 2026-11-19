<!--
  玩家頁「資料庫 › 勢力」：全部勢力一張表（唯讀，不用登入）。
  資料：GET /mission/factions（約 64 筆，含任務數、任務類型 mission_types、聲望種類 scopes），篩選在前端做。
  聲望種類＝勢力階級表裡的種類＋任務完成後會給這個勢力的聲望種類（例如紅風物流有立場、貨運；見 src/models/mission.py 的 ladder_scopes）。
  按「聲望」展開那個勢力的聲望階級與每一階能接的任務（components/FactionReputation.vue，傳 factionId）。
-->
<template>
  <div class="sf-split">
    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-4">
            <label class="form-label small fw-semibold mb-1" for="fdb-q">勢力名稱</label>
            <input id="fdb-q" v-model="query" type="search" class="form-control form-control-sm"
              placeholder="中英文皆可" autocomplete="off">
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label small fw-semibold mb-1" for="fdb-scope">聲望種類</label>
            <MultiSelectFilter id="fdb-scope" v-model="scopeSel" :options="scopeOptions" label="聲望種類" placeholder="全部" block searchable />
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label small fw-semibold mb-1" for="fdb-type">任務類型</label>
            <MultiSelectFilter id="fdb-type" v-model="typeSel" :options="typeOptions" label="任務類型" placeholder="全部" block searchable />
          </div>
          <div class="col-12 col-md-2">
            <label class="form-label small fw-semibold mb-1" for="fdb-has">任務</label>
            <select id="fdb-has" v-model="hasMissions" class="form-select form-select-sm">
              <option value="">全部</option>
              <option value="1">有任務</option>
              <option value="0">沒有任務</option>
            </select>
          </div>
        </div>
        <div v-if="hasFilter" class="d-flex flex-wrap align-items-center gap-2 mt-2">
          <span class="small text-muted">符合 {{ rows.length }} 個勢力</span>
          <button type="button" class="btn btn-sm btn-warning ms-auto" @click="clearFilters">清除篩選</button>
        </div>
      </div>
    </div>

    <SfState :loading="loading" :error="error" :empty="loaded && !rows.length"
      :empty-text="factions.length ? '沒有符合條件的勢力。' : '尚無勢力資料。'" @retry="load">
      <SortSelect v-if="isPhone" class="mb-2" :sort="sort" :options="SORT_OPTIONS" />
      <div :class="cardClass">
        <div class="card-body p-0">
          <div style="overflow-x: auto">
            <table class="table table-hover align-middle mb-0 sf-stack">
              <thead class="table-light">
                <tr>
                  <SortTh :sort="sort" field="name" class="ps-3">勢力</SortTh>
                  <SortTh :sort="sort" field="lawful" class="d-none d-md-table-cell">合法性</SortTh>
                  <th>聲望種類</th>
                  <th class="d-none d-lg-table-cell">任務類型</th>
                  <SortTh :sort="sort" field="mission_count" class="text-end">任務數</SortTh>
                  <SortTh :sort="sort" field="blueprint_mission_count" class="text-end d-none d-md-table-cell">有藍圖的任務</SortTh>
                  <th class="pe-3"></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="f in sort.sorted.value" :key="f._id">
                  <tr>
                    <td class="ps-3 sf-stack__title">
                      <span class="fw-semibold">{{ zhName(f) || f.name }}</span>
                      <span v-if="zhName(f)" class="small text-muted ms-1">{{ f.name }}</span>
                    </td>
                    <td class="d-none d-md-table-cell" data-label="合法性">
                      <span v-if="f.lawful === true" class="sf-chip sf-chip--ok mb-0">合法</span>
                      <span v-else-if="f.lawful === false" class="sf-chip sf-chip--warn mb-0">非法</span>
                      <template v-else>—</template>
                    </td>
                    <td data-label="聲望種類">
                      <span v-for="sc in f.scopes" :key="sc" class="sf-chip sf-chip--accent me-1 mb-1">{{ scopeLabel(sc) }}</span>
                      <span v-if="!f.scopes?.length" class="text-muted">—</span>
                    </td>
                    <td class="d-none d-lg-table-cell" data-label="任務類型">
                      <span v-for="t in f.mission_types" :key="t" class="sf-chip me-1 mb-1">{{ typeLabel(t) }}</span>
                      <span v-if="!f.mission_types?.length" class="text-muted">—</span>
                    </td>
                    <td class="text-end" data-label="任務數">{{ f.mission_count }}</td>
                    <td class="text-end d-none d-md-table-cell" data-label="有藍圖的任務">{{ f.blueprint_mission_count || 0 }}</td>
                    <td class="text-end pe-3 sf-stack__actions">
                      <button type="button" class="btn btn-sm btn-info text-nowrap" :aria-expanded="openId === f._id ? 'true' : 'false'"
                        @click="openId = openId === f._id ? '' : f._id">
                        <i class="bi me-1" :class="openId === f._id ? 'bi-chevron-up' : 'bi-chevron-down'"></i>聲望
                      </button>
                    </td>
                  </tr>
                  <tr v-if="openId === f._id" class="sf-stack__detail">
                    <td colspan="7" class="fdb-detail">
                      <div class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">{{ zhName(f) || f.name }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="openId = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <FactionReputation :fetcher="fetcher" :faction-id="f._id" :registered-uuids="registeredUuids"
                        :can-register="canRegister" @registered="$emit('registered')" />
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </SfState>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import FactionReputation from '@/components/FactionReputation.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import SfState from '@/components/SfState.vue'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'
import { loadTranslations, translate } from '@/utils/translations'

defineEmits(['registered'])
const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 分頁第一次變成可見才載入 */
  active: { type: Boolean, default: true },
  cardClass: { type: String, default: 'card' },
  /** 我的藍圖的 blueprint_uuid（展開的任務細節用） */
  registeredUuids: { type: Array, default: null },
  canRegister: { type: Boolean, default: false },
})

const zhName = f => f.name_zh || translate('faction', f.name) || ''
/** 聲望種類、任務類型的名稱都用任務類型那份遊戲翻譯（例如 Hauling → 貨運） */
const typeLabel = t => translate('mission_type', t) || t
const scopeLabel = typeLabel

// ── 資料 ──
const factions = ref([])
const loading = ref(false)
const loaded = ref(false)
const error = ref('')
async function load() {
  loading.value = true
  error.value = ''
  const res = await props.fetcher('/mission/factions')
  const body = res ? await res.json().catch(() => null) : null
  loading.value = false
  if (!res?.ok || !body?.success) {
    error.value = '讀取失敗。'
    return
  }
  factions.value = body.data || []
  loaded.value = true
  loadTranslations('faction', factions.value.map(f => f.name))
  loadTranslations('mission_type', factions.value.flatMap(f => [...(f.scopes || []), ...(f.mission_types || [])]))
}
watch(() => props.active, on => { if (on && !loaded.value && !loading.value) load() }, { immediate: true })

// ── 篩選 ──
const query = ref('')
const scopeSel = ref([])
const typeSel = ref([])
const hasMissions = ref('1')
const optionsOf = key => [...new Set(factions.value.flatMap(f => f[key] || []))]
  .map(v => ({ value: v, label: typeLabel(v) })).sort((a, b) => a.label.localeCompare(b.label, 'zh-Hant'))
const scopeOptions = computed(() => optionsOf('scopes'))
const typeOptions = computed(() => optionsOf('mission_types'))
const hasFilter = computed(() => !!(query.value.trim() || scopeSel.value.length || typeSel.value.length || hasMissions.value))
function clearFilters() {
  query.value = ''
  scopeSel.value = []
  typeSel.value = []
  hasMissions.value = ''
}
const rows = computed(() => {
  const q = query.value.trim().toLowerCase()
  return factions.value.filter(f => (!q || [f.name, f.name_zh, translate('faction', f.name)].some(x => (x || '').toLowerCase().includes(q)))
    && (!scopeSel.value.length || scopeSel.value.some(s => (f.scopes || []).includes(s)))
    && (!typeSel.value.length || typeSel.value.some(t => (f.mission_types || []).includes(t)))
    && (!hasMissions.value || (hasMissions.value === '1' ? f.mission_count > 0 : !f.mission_count)))
})

// ── 排序、展開 ──
const SORT_OPTIONS = [{ field: 'name', label: '勢力' }, { field: 'mission_count', label: '任務數' },
  { field: 'blueprint_mission_count', label: '有藍圖的任務' }]
const sort = useTableSort(rows, { key: 'name', accessors: { name: f => zhName(f) || f.name, lawful: f => (f.lawful === true ? 0 : f.lawful === false ? 1 : 2) } })
const openId = ref('')
const { isPhone } = useBreakpoint()
</script>

<style scoped>
.fdb-detail { background: var(--sf-chip-bg); padding: .75rem 1rem !important; }
</style>
