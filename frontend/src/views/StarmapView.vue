<!--
  後台「地點資料庫」（遊戲資料唯讀；可存放、設施可以人工修正）。

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
  設施也可以在展開列編輯（勾選＋自訂名稱，PUT /starmap/<id>/amenities）：存成跟同步資料比較的增減
  （amenities_override），屬性、自動可存放跟著重算，重新同步後由 Starmap.apply_amenities() 套回去；
  「回到同步資料」清掉人工修正。
  「可選居住地」：預設清單 src/data/home_locations.json（英文名稱比對），admin／operator 可以在展開列
  個別改成是／不是或回到自動（PUT /starmap/<id>/home，存在 home_override，同步不會蓋掉）。

  網址參數：?id=<uuid> 只列那一筆並展開（點「上層」「下層」會跳過去）。
-->
<template>
  <div>
    <h5 class="mb-3 fw-bold"><i class="bi bi-geo-alt me-2 text-primary"></i>地點資料庫</h5>

    <!-- 搜尋卡：條件照列表欄位排（見 components/AdminSearchCard.vue）；名稱打字停 300ms 就查 -->
    <AdminSearchCard :active="hasActiveFilters" @clear="resetFilters">
      <AdminSearchField label="地點（英文／中文）" for-id="sm-q" col="col-12 col-md-6 col-xl-3">
        <input id="sm-q" v-model="query" type="search" class="form-control form-control-sm" placeholder="輸入地點名稱">
      </AdminSearchField>
      <AdminSearchField label="類型" for-id="sm-type" col="col-6 col-md-3 col-xl-3">
        <MultiSelectFilter id="sm-type" :model-value="types" label="類型" :options="typeOptions" searchable block placeholder="全部"
          @update:model-value="v => { types = v; reload(0) }" />
      </AdminSearchField>
      <AdminSearchField label="星系" for-id="sm-system">
        <MultiSelectFilter id="sm-system" :model-value="systems" label="星系" :options="systemOptions" block placeholder="全部"
          @update:model-value="v => { systems = v; reload(0) }" />
      </AdminSearchField>
      <AdminSearchField label="管轄" for-id="sm-jurisdiction">
        <MultiSelectFilter id="sm-jurisdiction" :model-value="jurisdictions" label="管轄" :options="jurisdictionOptions" searchable block placeholder="全部"
          @update:model-value="v => { jurisdictions = v; reload(0) }" />
      </AdminSearchField>
      <AdminSearchField label="設施" for-id="sm-amenity">
        <MultiSelectFilter id="sm-amenity" :model-value="amenities" label="設施" :options="amenityOptions" searchable block placeholder="全部"
          @update:model-value="v => { amenities = v; reload(0) }" />
      </AdminSearchField>
      <AdminSearchField label="屬性" for-id="sm-feature" col="col-6 col-md-3 col-xl">
        <MultiSelectFilter id="sm-feature" :model-value="features" label="屬性" :options="featureOptions" searchable block placeholder="全部"
          @update:model-value="v => { features = v; reload(0) }" />
      </AdminSearchField>
      <AdminSearchField label="可存放" for-id="sm-can-store" col="col-6 col-md-3 col-xl">
        <select id="sm-can-store" v-model="canStore" class="form-select form-select-sm" @change="reload(0)">
          <option value="">全部</option>
          <option value="1">可存放（{{ facets.can_store?.yes ?? 0 }}）</option>
          <option value="0">不可存放（{{ facets.can_store?.no ?? 0 }}）</option>
        </select>
      </AdminSearchField>
      <AdminSearchField label="居住地" for-id="sm-home" col="col-6 col-md-3 col-xl">
        <select id="sm-home" v-model="home" class="form-select form-select-sm" @change="reload(0)">
          <option value="">全部</option>
          <option value="1">可選居住地（{{ facets.home?.yes ?? 0 }}）</option>
          <option value="0">不是居住地（{{ facets.home?.no ?? 0 }}）</option>
        </select>
      </AdminSearchField>
      <AdminSearchField label="玩家頁面" for-id="sm-visible" col="col-6 col-md-3 col-xl">
        <select id="sm-visible" v-model="playerVisible" class="form-select form-select-sm" @change="reload(0)">
          <option value="">全部</option>
          <option value="1">顯示</option>
          <option value="0">不顯示</option>
        </select>
      </AdminSearchField>
      <template #options>
        <div class="form-check form-check-inline mb-0">
          <input id="sm-missing-zh" v-model="missingZh" class="form-check-input" type="checkbox" @change="reload(0)">
          <label class="form-check-label small" for="sm-missing-zh">只看沒有中文</label>
        </div>
        <div class="form-check form-check-inline mb-0">
          <input id="sm-unnamed" v-model="includeUnnamed" class="form-check-input" type="checkbox" @change="reload(0)">
          <label class="form-check-label small" for="sm-unnamed">顯示未命名</label>
        </div>
      </template>
    </AdminSearchCard>

    <div class="card shadow-sm border-0">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0 small">
            <thead class="table-light">
              <tr>
                <SortTh :sort="sort" field="name" class="ps-3">地點（英文）</SortTh>
                <SortTh :sort="sort" field="name_zh">中文</SortTh>
                <SortTh :sort="sort" field="type">類型</SortTh>
                <SortTh :sort="sort" field="system">星系</SortTh>
                <SortTh :sort="sort" field="parent">上層</SortTh>
                <SortTh :sort="sort" field="jurisdiction">管轄</SortTh>
                <SortTh :sort="sort" field="can_store" class="text-center">可存放</SortTh>
                <SortTh :sort="sort" field="is_home" class="text-center">居住地</SortTh>
                <SortTh :sort="sort" field="amenity_count" class="text-end">設施</SortTh>
                <SortTh :sort="sort" field="player_visible" class="pe-3">玩家頁面</SortTh>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td colspan="10" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td colspan="10" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取地點資料失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td colspan="10" class="text-center py-4 text-muted">
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
                    <td class="text-center text-nowrap">
                      <i v-if="loc.is_home" class="bi bi-house-fill text-primary" aria-label="可選居住地"></i>
                      <span v-else class="text-muted">—</span>
                      <span v-if="isHomeOverridden(loc)" class="badge text-bg-secondary ms-1">手動</span>
                    </td>
                    <td class="text-end">
                      <span v-if="loc.amenity_count" class="badge text-bg-primary">{{ loc.amenity_count }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td class="pe-3"><PlayerVisibleToggle dataset="locations" :doc-id="loc._id" :row="loc" /></td>
                  </tr>
                  <tr v-if="expandedId === loc._id">
                    <td colspan="10" class="detail-cell ps-5 pe-3 py-3">
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
                          <div class="fw-semibold mt-2 mb-1">可選居住地</div>
                          <div class="mb-1">
                            {{ loc.is_home ? '是' : '否' }}
                            <span class="text-muted">
                              （{{ isHomeOverridden(loc) ? `手動；預設清單為${loc.home_auto ? '是' : '否'}` : '依預設清單' }}）
                            </span>
                          </div>
                          <div v-if="canWrite" class="btn-group btn-group-sm mb-1" role="group" aria-label="設定可選居住地">
                            <button v-for="opt in HOME_OPTIONS" :key="String(opt.value)" type="button" class="btn"
                              :class="homeMode(loc) === opt.value ? 'btn-primary' : 'btn-outline-secondary'"
                              :disabled="savingHome" @click="setHome(loc, opt.value)">{{ opt.label }}</button>
                          </div>
                          <div v-if="homeError" class="text-danger">{{ homeError }}</div>
                          <div v-if="isHomeOverridden(loc) && loc.home_updated_by" class="text-muted meta-line">
                            {{ loc.home_updated_by }} · {{ formatTime(loc.home_updated_at) }}
                          </div>
                          <div class="fw-semibold mt-2 mb-1">屬性</div>
                          <div v-if="!featureList(loc).length" class="text-muted">—</div>
                          <div v-for="f in featureList(loc)" :key="f.key">
                            {{ f.label }}<span v-if="f.sizes" class="text-muted"> {{ f.sizes }}</span>
                          </div>
                        </div>
                        <div class="col-lg-3">
                          <div class="fw-semibold mb-1">
                            設施
                            <span v-if="loc.amenities_override" class="badge text-bg-secondary ms-1">手動</span>
                          </div>
                          <template v-if="amenityEditId !== loc._id">
                            <div v-if="!loc.amenities?.length" class="text-muted">—</div>
                            <div v-for="a in loc.amenities || []" :key="a.name">
                              {{ zhPair(a.name, a.name_zh) }}
                              <span v-if="loc.amenities_override?.add?.includes(a.name)" class="badge text-bg-success ms-1">手動加</span>
                            </div>
                            <div v-for="n in loc.amenities_override?.remove || []" :key="`rm-${n}`" class="text-muted">
                              <s>{{ n }}</s><span class="badge text-bg-warning ms-1">手動移除</span>
                            </div>
                            <div v-if="loc.amenities_override && loc.amenities_updated_by" class="text-muted meta-line">
                              {{ loc.amenities_updated_by }} · {{ formatTime(loc.amenities_updated_at) }}
                            </div>
                            <div v-if="canWrite" class="d-flex flex-wrap gap-1 mt-1">
                              <button type="button" class="btn btn-sm btn-outline-primary" @click="startAmenityEdit(loc)">
                                <i class="bi bi-pencil me-1"></i>編輯設施
                              </button>
                              <button v-if="loc.amenities_override" type="button" class="btn btn-sm btn-outline-secondary"
                                :disabled="savingAmenities" @click="saveAmenities(loc, null)">回到同步資料</button>
                            </div>
                          </template>
                          <template v-else>
                            <input v-model="amenityFilter" type="search" class="form-control form-control-sm mb-1"
                              placeholder="篩選設施..." aria-label="篩選設施">
                            <div class="amenity-box">
                              <label v-for="c in visibleAmenityChoices" :key="c.value" class="form-check mb-0">
                                <input class="form-check-input" type="checkbox" :checked="amenityDraft.includes(c.value)"
                                  @change="toggleAmenity(c.value, $event.target.checked)">
                                <span class="form-check-label">{{ zhPair(c.value, c.label_zh) }}</span>
                              </label>
                            </div>
                            <div class="input-group input-group-sm mt-1">
                              <input v-model="customAmenity" type="text" class="form-control" maxlength="80"
                                placeholder="其他設施（英文）" aria-label="其他設施" @keydown.enter.prevent="addCustomAmenity">
                              <button type="button" class="btn btn-outline-secondary" :disabled="!customAmenity.trim()"
                                @click="addCustomAmenity">加入</button>
                            </div>
                            <div class="small text-muted mt-1">已選 {{ amenityDraft.length }} 個</div>
                            <div class="d-flex gap-1 mt-1">
                              <button type="button" class="btn btn-sm btn-primary" :disabled="savingAmenities"
                                @click="saveAmenities(loc, amenityDraft)">儲存</button>
                              <button type="button" class="btn btn-sm btn-outline-secondary" :disabled="savingAmenities"
                                @click="amenityEditId = ''">取消</button>
                            </div>
                          </template>
                          <div v-if="amenityError" class="text-danger">{{ amenityError }}</div>
                        </div>
                        <div class="col-lg-2">
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { starmapApi } from '@/api'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import AdminSearchCard from '@/components/AdminSearchCard.vue'
import AdminSearchField from '@/components/AdminSearchField.vue'
import PlayerVisibleToggle from '@/components/PlayerVisibleToggle.vue'
import SortTh from '@/components/SortTh.vue'
import { useTableSort } from '@/composables/useTableSort'
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

const EMPTY_FACETS = { types: [], systems: [], jurisdictions: [], amenities: [], amenity_choices: [], features: [],
  can_store: null }
const facets = ref({ ...EMPTY_FACETS })
const query = ref('')
const types = ref([])
const systems = ref([])
const jurisdictions = ref([])
const amenities = ref([])
const features = ref([])
const canStore = ref('')
const home = ref('')
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
  || features.value.length > 0 || !!canStore.value || !!home.value || !!playerVisible.value || missingZh.value || includeUnnamed.value || !!onlyId.value)

// 點表頭排序（後端，見 src/models/starmap.py 的 SORT_FIELDS）
const sort = useTableSort(null, { onChange: () => reload(0) })

async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  loadedQuery = query.value.trim()
  const res = await starmapApi.list({
    q: loadedQuery,
    type: types.value,
    system: systems.value,
    jurisdiction: jurisdictions.value,
    amenity: amenities.value,
    feature: features.value,
    can_store: canStore.value,
    home: home.value,
    player_visible: playerVisible.value,
    missing_zh: missingZh.value ? 1 : '',
    include_unnamed: includeUnnamed.value || onlyId.value ? 1 : '',
    id: onlyId.value,
    ...sort.params.value,
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
  home.value = ''
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
  homeError.value = ''
  amenityEditId.value = ''
  amenityError.value = ''
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

// ── 設施（人工修正）──
const amenityEditId = ref('')
const amenityDraft = ref([])
const amenityFilter = ref('')
const customAmenity = ref('')
const savingAmenities = ref(false)
const amenityError = ref('')
/** 可勾的設施：資料裡出現過的＋屬性對應的（facets.amenity_choices）＋這筆目前有的（含自訂） */
const amenityChoices = computed(() => {
  const out = new Map((facets.value.amenity_choices || []).map(c => [c.value, c]))
  for (const n of amenityDraft.value) if (!out.has(n)) out.set(n, { value: n, label_zh: null })
  return [...out.values()].sort((a, b) => a.value.toLowerCase().localeCompare(b.value.toLowerCase()))
})
const visibleAmenityChoices = computed(() => {
  const q = amenityFilter.value.trim().toLowerCase()
  return q ? amenityChoices.value.filter(c => `${c.value} ${c.label_zh || ''}`.toLowerCase().includes(q))
    : amenityChoices.value
})

function startAmenityEdit(loc) {
  amenityEditId.value = loc._id
  amenityDraft.value = (loc.amenities || []).map(a => a.name)
  amenityFilter.value = ''
  customAmenity.value = ''
  amenityError.value = ''
}
function toggleAmenity(name, checked) {
  amenityDraft.value = checked ? [...new Set([...amenityDraft.value, name])] : amenityDraft.value.filter(n => n !== name)
}
function addCustomAmenity() {
  const name = customAmenity.value.trim()
  if (name) toggleAmenity(name, true)
  customAmenity.value = ''
}
async function saveAmenities(loc, names) {
  savingAmenities.value = true
  amenityError.value = ''
  const res = await starmapApi.setAmenities(loc._id, names)
  const body = res ? await res.json().catch(() => null) : null
  if (res?.ok && body?.success) {
    const i = rows.value.findIndex(r => r._id === loc._id)
    if (i >= 0) rows.value[i] = { ...rows.value[i], ...body.data }
    amenityEditId.value = ''
    loadFacets()
  } else {
    amenityError.value = body?.message || '儲存失敗'
  }
  savingAmenities.value = false
}

// ── 可選居住地 ──
const HOME_OPTIONS = [
  { value: null, label: '自動' }, { value: true, label: '是居住地' }, { value: false, label: '不是居住地' },
]
const savingHome = ref(false)
const homeError = ref('')
const isHomeOverridden = loc => loc.home_override === true || loc.home_override === false
const homeMode = loc => (isHomeOverridden(loc) ? loc.home_override : null)

async function setHome(loc, value) {
  if (homeMode(loc) === value) return
  savingHome.value = true
  homeError.value = ''
  const res = await starmapApi.setHome(loc._id, value)
  const body = res ? await res.json().catch(() => null) : null
  if (res?.ok && body?.success) {
    const i = rows.value.findIndex(r => r._id === loc._id)
    if (i >= 0) rows.value[i] = { ...rows.value[i], ...body.data }
    loadFacets()
  } else {
    homeError.value = body?.message || '儲存失敗'
  }
  savingHome.value = false
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

// 名稱打字停 300ms 就查；跟上次查的一樣（例如按了清除篩選已經查過）就不重查
let loadedQuery = ''
let queryTimer = null
watch(query, () => {
  clearTimeout(queryTimer)
  queryTimer = setTimeout(() => { if (query.value.trim() !== loadedQuery) reload(0) }, 300)
})
onBeforeUnmount(() => clearTimeout(queryTimer))

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
.amenity-box { max-height: 14rem; overflow-y: auto; padding: .25rem .4rem; border: 1px solid var(--bs-border-color);
  border-radius: .25rem; background: var(--bs-body-bg); }
details > summary { cursor: pointer; }
</style>
