<!--
  後台「地點資料庫」（唯讀）。

  資料是 starmap_master（tasks/scdata_sync.py 的「地點」同步項目，從 scunpacked-data
  starmap.json 同步：星系、行星、衛星、太空站、前哨站、小行星…約 2,000 筆），
  後端分頁／篩選（GET /starmap/，類型、星系、管轄、設施可多選）。點一列展開說明、
  設施、上下層。

  中文：名稱、說明、類型、管轄、設施都是同步時從 sc_translations 比對好的 *_zh
  （見 src/sc_zh.py「星圖地點」一節），翻譯同步完會自動重新比對；「只看沒有中文」
  用來找沒對到的。預設不列沒有名稱的點（遊戲內部用的導航點），可以勾「顯示未命名」。

  屬性（has_hangar、shop_weapons…）是同步時從設施算出來的布林欄位（src/models/starmap.py
  的 FEATURES）；「可存放」預設依機庫／停機坪／對接口／商品交易／裝卸區自動判斷，
  admin／operator 可以在展開列個別改成可存放／不可存放或回到自動
  （PUT /starmap/<id>/storage，存在 can_store_override，同步不會蓋掉）。

  網址參數：?id=<uuid> 只列那一筆並展開（點「上層」「下層」會跳過去）。
-->
<template>
  <div>
    <h5 class="mb-3 fw-bold"><i class="bi bi-geo-alt me-2 text-primary"></i>地點資料庫</h5>

    <div class="card shadow-sm border-0 mb-3">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="query" type="search" class="form-control form-control-sm"
            style="max-width: 14rem" placeholder="搜尋英文或中文名稱..." @change="reload(0)">
          <MultiSelectFilter :model-value="types" label="類型" :options="typeOptions" searchable
            @update:model-value="v => { types = v; reload(0) }" />
          <MultiSelectFilter :model-value="systems" label="星系" :options="systemOptions"
            @update:model-value="v => { systems = v; reload(0) }" />
          <MultiSelectFilter :model-value="jurisdictions" label="管轄" :options="jurisdictionOptions" searchable
            @update:model-value="v => { jurisdictions = v; reload(0) }" />
          <MultiSelectFilter :model-value="amenities" label="設施" :options="amenityOptions" searchable
            @update:model-value="v => { amenities = v; reload(0) }" />
          <MultiSelectFilter :model-value="features" label="屬性" :options="featureOptions" searchable
            @update:model-value="v => { features = v; reload(0) }" />
          <select v-model="canStore" class="form-select form-select-sm w-auto" aria-label="可存放" @change="reload(0)">
            <option value="">可存放：全部</option>
            <option value="1">可存放（{{ facets.can_store?.yes ?? 0 }}）</option>
            <option value="0">不可存放（{{ facets.can_store?.no ?? 0 }}）</option>
          </select>
          <select v-model="playerVisible" class="form-select form-select-sm w-auto" aria-label="玩家頁面顯示"
            @change="reload(0)">
            <option value="">玩家頁面：全部</option>
            <option value="1">玩家頁面：顯示</option>
            <option value="0">玩家頁面：不顯示</option>
          </select>
          <div class="form-check form-check-inline mb-0 ms-1">
            <input id="sm-missing-zh" v-model="missingZh" class="form-check-input" type="checkbox" @change="reload(0)">
            <label class="form-check-label small" for="sm-missing-zh">只看沒有中文</label>
          </div>
          <div class="form-check form-check-inline mb-0">
            <input id="sm-unnamed" v-model="includeUnnamed" class="form-check-input" type="checkbox" @change="reload(0)">
            <label class="form-check-label small" for="sm-unnamed">顯示未命名</label>
          </div>
          <button v-if="hasActiveFilters" type="button" class="btn btn-sm btn-link" @click="resetFilters">
            清除全部篩選
          </button>
        </div>
      </div>
    </div>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0 small">
            <thead class="table-light">
              <tr>
                <th class="ps-3">地點（英文）</th>
                <th>中文</th>
                <th>類型</th>
                <th>星系</th>
                <th>上層</th>
                <th>管轄</th>
                <th class="text-center">可存放</th>
                <th class="text-end">設施</th>
                <th class="pe-3 text-nowrap">玩家頁面</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="9" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="9" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取地點資料失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="9" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的地點。' : '尚無地點資料' }}
                </td>
              </tr>
              <template v-else>
                <template v-for="loc in rows" :key="loc._id">
                  <tr class="row-click" role="button" tabindex="0"
                    :aria-expanded="expandedId === loc._id ? 'true' : 'false'"
                    @click="toggle(loc)" @keydown.enter="toggle(loc)">
                    <td class="ps-3">
                      <i class="bi me-1 text-muted" :class="expandedId === loc._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <span class="fw-semibold">{{ loc.name || '（未命名）' }}</span>
                    </td>
                    <td class="text-nowrap">
                      <span v-if="loc.name_zh">{{ loc.name_zh }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td class="text-nowrap">{{ zhPair(loc.type, loc.type_zh) }}</td>
                    <td class="text-nowrap">{{ loc.system_name ? (loc.system_name_zh || loc.system_name) : '—' }}</td>
                    <td>
                      <RouterLink v-if="loc.parent_uuid && loc.parent_name" :to="{ query: { id: loc.parent_uuid } }"
                        @click.stop>{{ loc.parent_name_zh || loc.parent_name }}</RouterLink>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td>{{ loc.jurisdiction ? (loc.jurisdiction_zh || loc.jurisdiction) : '—' }}</td>
                    <td class="text-center text-nowrap">
                      <i v-if="loc.can_store" class="bi bi-check-lg text-success" aria-label="可存放"></i>
                      <span v-else class="text-muted">—</span>
                      <span v-if="isOverridden(loc)" class="badge text-bg-secondary ms-1">手動</span>
                    </td>
                    <td class="text-end">
                      <span v-if="loc.amenity_count" class="badge text-bg-primary">{{ loc.amenity_count }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td class="pe-3"><PlayerVisibleToggle dataset="locations" :doc-id="loc._id" :row="loc" /></td>
                  </tr>
                  <tr v-if="expandedId === loc._id">
                    <td colspan="9" class="detail-cell ps-5 pe-3 py-3">
                      <div class="row g-3">
                        <div class="col-lg-4">
                          <div class="fw-semibold mb-1">說明</div>
                          <div v-if="loc.description_zh" class="pre-line">{{ loc.description_zh }}</div>
                          <details v-if="loc.description" :open="!loc.description_zh" class="mt-1">
                            <summary class="text-muted">英文</summary>
                            <div class="pre-line text-muted mt-1">{{ loc.description }}</div>
                          </details>
                          <div v-if="!loc.description && !loc.description_zh" class="text-muted">—</div>
                          <div v-if="loc.path?.length" class="mt-2 text-muted">
                            位置：{{ (loc.path_zh?.length ? loc.path_zh : loc.path).join(' › ') }} › {{ loc.name_zh || loc.name }}
                          </div>
                          <div class="mt-1 text-muted">{{ flags(loc) }}</div>
                        </div>
                        <div class="col-lg-3">
                          <div class="fw-semibold mb-1">可存放</div>
                          <div class="mb-1">
                            {{ loc.can_store ? '可存放' : '不可存放' }}
                            <span class="text-muted">
                              （{{ isOverridden(loc) ? `手動；自動判斷為${loc.can_store_auto ? '可存放' : '不可存放'}` : '自動判斷' }}）
                            </span>
                          </div>
                          <div v-if="canWrite" class="btn-group btn-group-sm mb-1" role="group" aria-label="設定可存放">
                            <button v-for="opt in STORAGE_OPTIONS" :key="String(opt.value)" type="button" class="btn"
                              :class="storageMode(loc) === opt.value ? 'btn-primary' : 'btn-outline-secondary'"
                              :disabled="savingStorage" @click="setStorage(loc, opt.value)">{{ opt.label }}</button>
                          </div>
                          <div v-if="storageError" class="text-danger">{{ storageError }}</div>
                          <div v-if="isOverridden(loc) && loc.can_store_updated_by" class="text-muted meta-line">
                            {{ loc.can_store_updated_by }} · {{ formatTime(loc.can_store_updated_at) }}
                          </div>
                          <div class="fw-semibold mt-2 mb-1">屬性</div>
                          <div v-if="!featureList(loc).length" class="text-muted">—</div>
                          <div v-for="f in featureList(loc)" :key="f.key">
                            {{ f.label }}<span v-if="f.sizes" class="text-muted"> {{ f.sizes }}</span>
                          </div>
                        </div>
                        <div class="col-lg-2">
                          <div class="fw-semibold mb-1">設施</div>
                          <div v-if="!loc.amenities?.length" class="text-muted">—</div>
                          <div v-for="a in loc.amenities || []" :key="a.name">{{ zhPair(a.name, a.name_zh) }}</div>
                        </div>
                        <div class="col-lg-3">
                          <div class="fw-semibold mb-1">下層地點</div>
                          <div v-if="detailLoading" class="text-muted">
                            <span class="spinner-border spinner-border-sm me-1"></span>載入中...
                          </div>
                          <div v-else-if="!children.length" class="text-muted">—</div>
                          <ul v-else class="list-unstyled mb-0 child-list">
                            <li v-for="c in children" :key="c._id">
                              <RouterLink :to="{ query: { id: c._id } }">{{ c.name_zh || c.name || '（未命名）' }}</RouterLink>
                              <span class="text-muted"> · {{ c.type_zh || c.type }}</span>
                            </li>
                          </ul>
                        </div>
                        <div class="col-12 text-muted meta-line">
                          UUID <span class="font-monospace">{{ loc._id }}</span>
                          <span v-if="loc.hierarchy_tag"> · <span class="font-monospace">{{ loc.hierarchy_tag }}</span></span>
                        </div>
                      </div>
                    </td>
                  </tr>
                </template>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </div>

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
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { starmapApi } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import PlayerVisibleToggle from '@/components/PlayerVisibleToggle.vue'
import { useAuthStore } from '@/stores/auth'
import { zhPair } from '@/utils/mission'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const canWrite = computed(() => auth.role === 'admin' || auth.role === 'operator')

const limit = 50
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)
const expandedId = ref('')
const children = ref([])
const detailLoading = ref(false)

const EMPTY_FACETS = { types: [], systems: [], jurisdictions: [], amenities: [], features: [], can_store: null }
const facets = ref({ ...EMPTY_FACETS })
const query = ref('')
const types = ref([])
const systems = ref([])
const jurisdictions = ref([])
const amenities = ref([])
const features = ref([])
const canStore = ref('')
const playerVisible = ref('')
const missingZh = ref(false)
const includeUnnamed = ref(false)
const onlyId = ref('')

const optionsOf = list => list.map(f => ({
  value: f.value, label: `${zhPair(f.value, f.label_zh)}（${f.count}）`,
}))
const typeOptions = computed(() => optionsOf(facets.value.types))
const systemOptions = computed(() => optionsOf(facets.value.systems))
const jurisdictionOptions = computed(() => optionsOf(facets.value.jurisdictions))
const amenityOptions = computed(() => optionsOf(facets.value.amenities))
const featureLabels = computed(() => Object.fromEntries(
  (facets.value.features || []).map(f => [f.value, f.label_zh || f.label])))
const featureOptions = computed(() => (facets.value.features || []).filter(f => f.count > 0).map(f => ({
  value: f.value, label: `${f.label_zh || f.label}（${f.count}）`,
})))

const hasActiveFilters = computed(() => !!query.value.trim() || types.value.length > 0
  || systems.value.length > 0 || jurisdictions.value.length > 0 || amenities.value.length > 0
  || features.value.length > 0 || !!canStore.value || !!playerVisible.value || missingZh.value || includeUnnamed.value || !!onlyId.value)

async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  const res = await starmapApi.list({
    q: query.value.trim(),
    type: types.value,
    system: systems.value,
    jurisdiction: jurisdictions.value,
    amenity: amenities.value,
    feature: features.value,
    can_store: canStore.value,
    player_visible: playerVisible.value,
    missing_zh: missingZh.value ? 1 : '',
    include_unnamed: includeUnnamed.value || onlyId.value ? 1 : '',
    id: onlyId.value,
    limit, offset: newOffset,
  })
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (body?.success) {
    rows.value = body.data || []
    total.value = body.total || 0
    if (onlyId.value && rows.value.length === 1) open(rows.value[0])
    else expandedId.value = ''
  } else {
    rows.value = []
    total.value = 0
    loadFailed.value = true
  }
  loading.value = false
}

function resetFilters() {
  query.value = ''
  types.value = []
  systems.value = []
  jurisdictions.value = []
  amenities.value = []
  features.value = []
  canStore.value = ''
  playerVisible.value = ''
  missingZh.value = false
  includeUnnamed.value = false
  if (onlyId.value) {
    onlyId.value = ''
    router.replace({ query: {} })
  }
  reload(0)
}

async function open(loc) {
  expandedId.value = loc._id
  storageError.value = ''
  children.value = []
  detailLoading.value = true
  const res = await starmapApi.get(loc._id)
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (expandedId.value !== loc._id) return
  children.value = body?.success ? (body.data.children || []) : []
  detailLoading.value = false
}

function toggle(loc) {
  if (expandedId.value === loc._id) expandedId.value = ''
  else open(loc)
}

// ── 可存放／屬性 ──
const STORAGE_OPTIONS = [
  { value: null, label: '自動' }, { value: true, label: '可存放' }, { value: false, label: '不可存放' },
]
const savingStorage = ref(false)
const storageError = ref('')

const isOverridden = loc => loc.can_store_override === true || loc.can_store_override === false
const storageMode = loc => (isOverridden(loc) ? loc.can_store_override : null)

async function setStorage(loc, value) {
  if (storageMode(loc) === value) return
  savingStorage.value = true
  storageError.value = ''
  const res = await starmapApi.setStorage(loc._id, value)
  const body = res ? await res.json().catch(() => null) : null
  if (res?.ok && body?.success) {
    const i = rows.value.findIndex(r => r._id === loc._id)
    if (i >= 0) rows.value[i] = { ...rows.value[i], ...body.data }
    loadFacets()
  } else {
    storageError.value = body?.message || '儲存失敗'
  }
  savingStorage.value = false
}

const SIZE_FIELDS = { has_hangar: 'hangar_sizes', has_landing_pad: 'landing_pad_sizes' }

function featureList(loc) {
  return (facets.value.features || []).filter(f => loc[f.value] === true).map(f => ({
    key: f.value,
    label: featureLabels.value[f.value] || f.value,
    sizes: (loc[SIZE_FIELDS[f.value]] || []).join('、'),
  }))
}

function formatTime(value) {
  if (!value) return ''
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString('zh-TW', { hour12: false })
}

const RESPAWN_LABELS = { Hospital: '醫院（重生點）', Prison: '監獄', PrisonExit: '監獄出口',
  CriminalLocation: '罪犯據點', CriminalHospital: '罪犯醫院', Other: '其他重生點' }

function flags(loc) {
  const parts = []
  parts.push(loc.quantum_travel ? '可量子躍遷' : '不可量子躍遷')
  if (loc.respawn_type) parts.push(RESPAWN_LABELS[loc.respawn_type] || loc.respawn_type)
  if (loc.is_prison) parts.push('監獄轄區')
  if (loc.hide_in_starmap) parts.push('星圖上隱藏')
  if (loc.classification) parts.push(`分類 ${loc.classification}`)
  return parts.join(' · ')
}

async function loadFacets() {
  const res = await starmapApi.facets()
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (body?.success) facets.value = { ...EMPTY_FACETS, ...body.data }
}

watch(() => route.query.id, (id) => {
  onlyId.value = typeof id === 'string' ? id : ''
  reload(0)
})

onMounted(() => {
  onlyId.value = typeof route.query.id === 'string' ? route.query.id : ''
  loadFacets()
  reload(0)
})
</script>

<style scoped>
.row-click { cursor: pointer; }
.detail-cell { background: var(--bs-tertiary-bg); }
.meta-line { font-size: .75rem; }
.pre-line { white-space: pre-line; }
.child-list { max-height: 16rem; overflow-y: auto; }
details > summary { cursor: pointer; }
</style>
