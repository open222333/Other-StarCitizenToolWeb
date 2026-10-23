<!--
  藍圖資料庫瀏覽：製造藍圖主檔 blueprint_master（唯讀）。兩個地方掛載：
    - 後台「藍圖 › 藍圖資料庫」（預設，用 apiFetch）
    - 玩家頁「藍圖 › 藍圖資料」（player 模式，傳 playerFetch；套玩家頁的深色卡片）

  資料由 tasks/scdata_sync.py 從 Star Citizen Wiki API 同步，這裡只讀不寫。
  1,600+ 筆，走後端分頁／篩選（GET /blueprint/master，類型可多選、
  missing_zh=1 只看沒有中文名稱的〔後台才有〕、has_missions=1 只看有任務會給的）。
  點一列展開配方明細（GET /blueprint/master/<uuid>）與解鎖任務
  （GET /mission/for-blueprint/<uuid>，本地任務資料庫反查；「解鎖任務」欄的數字是
  後端附的 mission_count）。

  解鎖任務的連結：後台跳到任務資料庫頁；玩家頁沒有那一頁，藍圖名稱（有任務的才是
  連結）與明細裡的任務都開 BlueprintMissionsModal。

  玩家頁「藍圖 › 登記藍圖資料」再傳 registeredUuids（我的藍圖的 blueprint_uuid）就變成可登記：
  每列前面有勾選框（批量登記，勾選跨頁保留，底部出現登記列＋共用的「取得方式」）、最後一欄
  「登記」按鈕（登記這一張）；已登記的標「已登記」且不能再勾。都走 POST /player/blueprints/bulk，
  後端也會再擋重複（Blueprint.bulk_create_for_player）。登記完 emit('registered') 讓父層重抓我的藍圖。
  原本獨立的「批量登記」元件已併進這裡（已刪除）。

  玩家頁傳 sharedFilters（{ q, types, hasMissions, hideAvailable, unregistered }）時，名稱／類型／只看需任務解鎖
  全部改用「藍圖」分頁頂端的共用搜尋卡，這裡自己的條件卡整個不顯示；hideAvailable＝不列預設可用的
  （視同已登記，後端 available=0）；unregistered＝只顯示未登記（後端 unregistered=1 依玩家 token 排除自己已登記的，
  登記完名冊一變就重抓這一頁）。

  玩家頁面顯示（後台才有的欄位與篩選）：PlayerVisibleToggle，規則見 src/models/visibility.py；
  玩家 token 呼叫 /blueprint/master 時後端本來就只回顯示的。

  中文：藍圖名稱用同步時存的 name_zh（依產出物 class 查 sc_translations，比用
  英文名稱反查準）；類型用 utils/blueprintOutputType.js；材料名稱用
  utils/translations.js 即時查。
-->
<template>
  <!-- 換頁載入中保留舊的列（只變淡），不讓頁面瞬間變短；變短會讓瀏覽器把畫面捲到下面去 -->
  <div ref="rootEl" class="sf-scroll-anchor" :class="{ 'sf-list-loading': loading }">
    <!-- 後台搜尋卡：條件照列表欄位排（見 components/AdminSearchCard.vue）；玩家頁一律用「藍圖」分頁的共用搜尋卡 -->
    <AdminSearchCard v-if="!shared" :active="hasActiveFilters" @clear="resetFilters">
      <AdminSearchField label="藍圖（英文／中文）" :for-id="`${uid}-q`" col="col-12 col-md-6 col-xl-3">
        <input :id="`${uid}-q`" v-model="nameQuery" type="search" class="form-control form-control-sm" placeholder="輸入藍圖名稱">
      </AdminSearchField>
      <AdminSearchField label="類型" :for-id="`${uid}-type`" col="col-6 col-md-3 col-xl-2">
        <MultiSelectFilter :id="`${uid}-type`" :model-value="selectedTypes" label="類型" :options="typeOptions" searchable block placeholder="全部"
          @update:model-value="v => { selectedTypes = v; reload(0) }" />
      </AdminSearchField>
      <AdminSearchField label="預設可用" :for-id="`${uid}-available`" col="col-6 col-md-3 col-xl-2">
        <select :id="`${uid}-available`" v-model="availableSel" class="form-select form-select-sm" @change="reload(0)">
          <option value="">全部</option>
          <option value="1">是</option>
          <option value="0">否</option>
        </select>
      </AdminSearchField>
      <AdminSearchField label="解鎖任務" :for-id="`${uid}-has-missions`" col="col-6 col-md-3 col-xl-2">
        <select :id="`${uid}-has-missions`" v-model="hasMissionsOnly" class="form-select form-select-sm" @change="reload(0)">
          <option :value="false">全部</option>
          <option :value="true">需任務解鎖</option>
        </select>
      </AdminSearchField>
      <AdminSearchField v-if="!player" label="玩家頁面" :for-id="`${uid}-visible`" col="col-6 col-md-3 col-xl-2">
        <select :id="`${uid}-visible`" v-model="playerVisible" class="form-select form-select-sm" @change="reload(0)">
          <option value="">全部</option>
          <option value="1">顯示</option>
          <option value="0">不顯示</option>
        </select>
      </AdminSearchField>
      <template v-if="!player" #options>
        <div class="form-check form-check-inline mb-0">
          <input :id="`${uid}-missing-zh`" v-model="missingZhOnly" class="form-check-input" type="checkbox" @change="reload(0)">
          <label class="form-check-label small" :for="`${uid}-missing-zh`">只看沒有中文</label>
        </div>
      </template>
    </AdminSearchCard>

    <div v-if="message" :class="['alert', 'py-2', messageType]">{{ message }}</div>

    <div :class="cardClass">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <!-- 玩家頁：手機上每列變卡片（sf-stack，見 scifi-theme.css）；後台不受影響 -->
          <table class="table table-hover align-middle mb-0" :class="{ 'sf-stack': player }">
            <thead class="table-light">
              <tr>
                <th v-if="registerable" class="ps-3" style="width: 2.5rem">
                  <input class="form-check-input" type="checkbox" aria-label="全選本頁"
                    :checked="allSelectableChecked" :indeterminate.prop="someSelectableChecked && !allSelectableChecked"
                    :disabled="!selectableRows.length" @change="togglePage($event.target.checked)">
                </th>
                <SortTh :sort="sort" :field="player ? 'name_zh' : 'name'" :class="{ 'ps-3': !registerable }">{{ player ? '名稱' : '藍圖（英文）' }}</SortTh>
                <SortTh v-if="!player" :sort="sort" field="name_zh">中文</SortTh>
                <SortTh :sort="sort" field="type">類型</SortTh>
                <!-- 玩家頁在手機／平板藏次要欄位（點一列展開的配方明細看得到） -->
                <SortTh :sort="sort" field="grade" :class="{ 'd-none d-md-table-cell': player }">等級</SortTh>
                <SortTh :sort="sort" field="craft_time" :class="{ 'd-none d-lg-table-cell': player }">製作時間</SortTh>
                <SortTh :sort="sort" field="ingredients" class="text-end" :class="{ 'd-none d-md-table-cell': player }">材料數</SortTh>
                <SortTh :sort="sort" field="available" :class="{ 'd-none d-lg-table-cell': player }">預設可用</SortTh>
                <th class="text-end" :class="{ 'pe-3': player && !registerable, 'd-none d-md-table-cell': player }">解鎖任務</th>
                <th v-if="registerable" class="pe-3"></th>
                <SortTh v-if="!player" :sort="sort" field="player_visible" class="pe-3">玩家頁面</SortTh>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading && !rows.length">
                <td :colspan="colspan" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td :colspan="colspan" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取藍圖資料失敗。</span>
                  <button class="btn btn-sm ms-1" :class="player ? 'btn-primary' : 'btn-outline-secondary'" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td :colspan="colspan" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的藍圖。' : '尚無藍圖資料' }}
                </td>
              </tr>
              <template v-else>
                <template v-for="bp in rows" :key="bp._id">
                  <tr class="bp-row" :class="{ 'bp-registered': registerable && isRegistered(bp) }"
                    role="button" tabindex="0" :aria-expanded="expandedId === bp._id ? 'true' : 'false'"
                    @click="toggle(bp)" @keydown.enter.self="toggle(bp)">
                    <td v-if="registerable" class="ps-3 sf-stack__check" @click.stop>
                      <input class="form-check-input" type="checkbox" :checked="selected.has(bp._id)"
                        :disabled="isRegistered(bp)" :aria-label="`勾選 ${bp.name_zh || bp.name}`"
                        @change="toggleOne(bp._id, $event.target.checked)">
                    </td>
                    <td class="sf-stack__title" :class="{ 'ps-3': !registerable }">
                      <i class="bi me-1 small text-muted" :class="expandedId === bp._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <template v-if="player">
                        <button v-if="bp.mission_count" type="button" class="btn btn-sm btn-info py-0 px-2 text-start fw-semibold"
                          @click.stop="openMissions(bp)">{{ bp.name_zh || bp.name }}</button>
                        <span v-else class="fw-semibold">{{ bp.name_zh || bp.name }}</span>
                        <span v-if="bp.name_zh" class="small text-muted ms-1">{{ bp.name }}</span>
                      </template>
                      <template v-else>
                        <span class="fw-semibold">{{ bp.name }}</span>
                        <div class="small text-muted font-monospace ms-3">{{ bp.key }}</div>
                      </template>
                    </td>
                    <td v-if="!player">
                      <span v-if="bp.name_zh">{{ bp.name_zh }}</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td :class="{ small: !player }" data-label="類型">{{ bp.output_type ? blueprintTypeLabel(bp.output_type) : (bp.output_type_label || '—') }}</td>
                    <td :class="player ? 'd-none d-md-table-cell' : 'small'" data-label="等級">{{ bp.output_grade || '—' }}</td>
                    <td :class="player ? 'd-none d-lg-table-cell' : 'small'" data-label="製作時間">{{ bp.craft_time_label || fmtSeconds(bp.craft_time_seconds) }}</td>
                    <td class="text-end" :class="player ? 'd-none d-md-table-cell' : 'small'" data-label="材料數">{{ bp.ingredient_count ?? '—' }}</td>
                    <td :class="player ? 'd-none d-lg-table-cell' : 'small'">{{ bp.is_available_by_default ? '是' : '否' }}</td>
                    <td class="text-end" :class="{ small: !player, 'pe-3': player && !registerable, 'd-none d-md-table-cell': player }" data-label="解鎖任務">
                      <span v-if="bp.mission_count">{{ bp.mission_count }} 個</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td v-if="registerable" class="pe-3 text-end text-nowrap sf-stack__actions" @click.stop>
                      <!-- 手機上這兩顆只留圖示（文字 d-none d-sm-inline），不然會擠出表格 -->
                      <button type="button" class="btn btn-sm btn-info me-1" aria-label="品質試算"
                        :aria-expanded="qualityId === bp._id ? 'true' : 'false'" @click="qualityId = qualityId === bp._id ? '' : bp._id">
                        <i class="bi" :class="qualityId === bp._id ? 'bi-chevron-up' : 'bi-sliders'"></i><span class="d-none d-sm-inline ms-1">品質試算</span>
                      </button>
                      <span v-if="isRegistered(bp)" class="sf-tree-chip">已登記</span>
                      <button v-else type="button" class="btn btn-sm btn-success" :disabled="submitting"
                        :aria-label="`登記 ${bp.name_zh || bp.name}`" @click="register([bp._id])">
                        <i class="bi bi-plus-lg"></i><span class="d-none d-sm-inline ms-1">登記</span>
                      </button>
                    </td>
                    <td v-if="!player" class="pe-3">
                      <PlayerVisibleToggle dataset="blueprints" :doc-id="bp._id" :row="bp" />
                    </td>
                  </tr>
                  <!-- 品質試算（跟我的藍圖同一個元件），登記前就能先試算 -->
                  <tr v-if="registerable && qualityId === bp._id" class="bp-detail sf-stack__detail">
                    <td :colspan="colspan" class="px-3 py-2">
                      <!-- 手機上這一列變成底部面板（sf-stack__detail），標題列附關閉按鈕 -->
                      <div v-if="player" class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">品質試算 · {{ bp.name_zh || bp.name }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="qualityId = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <BlueprintQuality :fetcher="fetcher" :blueprint-uuid="bp._id" />
                    </td>
                  </tr>
                  <tr v-if="expandedId === bp._id" class="bp-detail sf-stack__detail">
                    <td :colspan="colspan" class="ps-5 pe-3 py-2 small">
                      <div v-if="player" class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">{{ bp.name_zh || bp.name }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="expandedId = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <div v-if="detailLoading" class="text-muted">
                        <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                      </div>
                      <div v-else-if="!detail" class="text-warning">讀取配方失敗。</div>
                      <div v-else class="row g-3">
                        <div class="col-md-4">
                          <div class="fw-semibold mb-1">材料</div>
                          <div v-if="!detail.ingredients?.length" class="text-muted">—</div>
                          <div v-for="(ing, i) in detail.ingredients || []" :key="`i${i}`">
                            {{ materialLabel(ing) }}
                            <span class="text-muted">· {{ fmtQty(ing) }}</span>
                          </div>
                        </div>
                        <div class="col-md-3">
                          <div class="fw-semibold mb-1">拆解回收</div>
                          <div v-if="!detail.dismantle_returns?.length" class="text-muted">—</div>
                          <div v-for="(ret, i) in detail.dismantle_returns || []" :key="`r${i}`">
                            {{ materialLabel(ret) }}
                            <span class="text-muted">· {{ fmtQty(ret) }}</span>
                          </div>
                        </div>
                        <div class="col-md-5">
                          <div class="fw-semibold mb-1">解鎖任務</div>
                          <div v-if="!detailMissions.length" class="text-muted">—</div>
                          <div v-for="m in detailMissions" :key="m._id">
                            <button v-if="player" type="button" class="btn btn-sm btn-info py-0 px-2 text-start" @click="openMissions(bp)">
                              {{ zhPair(m.title, m.title_zh) }}
                            </button>
                            <RouterLink v-else :to="{ path: adminPath('/missions'), query: { id: m._id } }">{{ zhPair(m.title, m.title_zh) }}</RouterLink>
                            <span class="text-muted">
                              · {{ factionLabel(m) }}
                              <template v-if="m.star_systems?.length"> · {{ m.star_systems.join('、') }}</template>
                              <template v-if="m.reward_scope"> · {{ m.reward_scope }}</template>
                              <template v-if="m.chance !== null && m.chance !== undefined"> · 機率 {{ fmtChance(m.chance) }}</template>
                            </span>
                          </div>
                        </div>
                        <div v-if="!player" class="col-12 text-muted">
                          UUID <span class="font-monospace">{{ detail._id }}</span>
                          <span v-if="detail.game_version"> · {{ detail.game_version }}</span>
                          <span v-if="detail.unlocking_missions_count"> · 解鎖任務 {{ detail.unlocking_missions_count }} 個</span>
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
        <button class="btn" :class="player ? 'btn-scifi-outline' : 'btn-outline-secondary'"
          :disabled="offset === 0 || loading" @click="goPage(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn" :class="player ? 'btn-scifi-outline' : 'btn-outline-secondary'"
          :disabled="offset + limit >= total || loading" @click="goPage(offset + limit)">下一頁</button>
      </div>
    </div>

    <!-- ── 批量登記列（有勾選才出現；勾選跨頁保留）──────────────── -->
    <!-- sf-sticky-bar：手機上固定在畫面底部 -->
    <div v-if="registerable && selected.size" :class="[cardClass, 'sf-search', 'mt-3', 'bp-submit', 'sf-sticky-bar']">
      <div class="card-body">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <span class="fw-semibold">已選 {{ selected.size }} 張</span>
          <button type="button" class="btn btn-sm btn-warning" @click="selected.clear()">清除勾選</button>
          <span class="flex-grow-1"></span>
          <input v-model="acquisitionMethod" type="text" class="form-control form-control-sm"
            style="max-width: 12rem" placeholder="取得方式（可留空）" aria-label="取得方式（套用到這批全部）">
          <button type="button" class="btn btn-sm btn-success" :disabled="submitting || selected.size > maxBulk"
            @click="register([...selected], acquisitionMethod)">
            <span v-if="submitting" class="spinner-border spinner-border-sm me-1"></span>
            登記這 {{ selected.size }} 張
          </button>
        </div>
        <div v-if="selected.size > maxBulk" class="small text-danger mt-1">
          一次最多 {{ maxBulk }} 張，請先取消一些。
        </div>
      </div>
    </div>

    <BlueprintMissionsModal v-if="player" ref="missionsRef" :fetcher="fetcher" :registered-uuids="registeredUuids" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { scrollToListTop } from '@/utils/scrollAnchor'
import { apiFetch } from '@/api'
import BlueprintMissionsModal from '@/components/BlueprintMissionsModal.vue'
import BlueprintQuality from '@/components/BlueprintQuality.vue'
import AdminSearchCard from '@/components/AdminSearchCard.vue'
import AdminSearchField from '@/components/AdminSearchField.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import SortTh from '@/components/SortTh.vue'
import { useTableSort } from '@/composables/useTableSort'
import { adminPath } from '@/router'
import PlayerVisibleToggle from '@/components/PlayerVisibleToggle.vue'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'
import { factionLabel, fmtChance, zhPair } from '@/utils/mission'
import { loadMaterialZh, materialLabel } from '@/utils/blueprintMaterial'

const props = defineProps({
  /** 帶身分的 fetch（後台 apiFetch、玩家頁 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, default: apiFetch },
  /** 玩家頁模式：名稱合併成一欄、有任務的名稱可點開看解鎖任務、沒有後台專用的篩選 */
  player: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card shadow-sm border-0' },
  /** 玩家頁分頁用 v-show 一直掛著，第一次變成可見才載入（跟 MiningLookup 一樣） */
  active: { type: Boolean, default: true },
  /** 玩家頁「藍圖」分頁的共用搜尋卡 { q, types, available, hasMissions }；null＝用這裡自己的條件卡（後台） */
  sharedFilters: { type: Object, default: null },
  /** 玩家頁「登記藍圖資料」：我的藍圖已登記的 blueprint_uuid；null＝不能登記（後台／純瀏覽） */
  registeredUuids: { type: Array, default: null },
})
const emit = defineEmits(['registered'])

let uidSeq = 0
const uid = `bp-master-${props.player ? 'p' : 'a'}${++uidSeq}`

const limit = 50
const rows = ref([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const loadFailed = ref(false)

const types = ref([])
const nameQuery = ref('')
// 上一次查詢用的名稱（名稱的延遲查詢用來判斷要不要再查）
let lastName = ''
const selectedTypes = ref([])
// 預設可用：'' 不篩、'1' 只看預設可用、'0' 不列預設可用
const availableSel = ref('')
const missingZhOnly = ref(false)
// 玩家頁「登記藍圖資料」預設只看需任務解鎖的（預設可用的不用特地登記）
const hasMissionsOnly = ref(props.player && props.registeredUuids !== null)
const playerVisible = ref('')

const shared = computed(() => props.sharedFilters !== null)
const effectiveQuery = computed(() => (shared.value ? (props.sharedFilters.q || '') : nameQuery.value).trim())
const effectiveTypes = computed(() => (shared.value ? (props.sharedFilters.types || []) : selectedTypes.value))
// '1' 只看預設可用、'0' 不列預設可用、'' 不篩
const effectiveAvailable = computed(() => {
  if (!shared.value) return availableSel.value
  if (props.sharedFilters.hideAvailable) return '0'
  return props.sharedFilters.available ? '1' : ''
})
const effectiveHasMissions = computed(() => (shared.value ? !!props.sharedFilters.hasMissions : hasMissionsOnly.value))

const registerable = computed(() => props.player && props.registeredUuids !== null)
/** 正在品質試算的藍圖（登記藍圖資料） */
const qualityId = ref('')
const colspan = computed(() => (props.player ? 7 + (registerable.value ? 2 : 0) : 9))

// ── 登記（玩家頁「登記藍圖資料」）────────────────────────────
// 跟後端的 MAX_BULK_BLUEPRINTS 一致
const maxBulk = 200
const registeredSet = computed(() => new Set(props.registeredUuids || []))
const isRegistered = bp => registeredSet.value.has(bp._id)
/** 勾選中的 uuid，跨頁保留 */
const selected = reactive(new Set())
const acquisitionMethod = ref('')
const submitting = ref(false)
const message = ref('')
const messageType = ref('alert-success')
const selectableRows = computed(() => rows.value.filter(bp => !isRegistered(bp)))
const allSelectableChecked = computed(() =>
  selectableRows.value.length > 0 && selectableRows.value.every(bp => selected.has(bp._id)))
const someSelectableChecked = computed(() => selectableRows.value.some(bp => selected.has(bp._id)))

function toggleOne(id, checked) {
  if (checked) selected.add(id)
  else selected.delete(id)
}

function togglePage(checked) {
  for (const bp of selectableRows.value) {
    if (checked) selected.add(bp._id)
    else selected.delete(bp._id)
  }
}

// 別處（單張登記、我的藍圖刪除）改了名冊，已登記的就不該還勾著
watch(registeredSet, (set) => {
  for (const id of [...selected]) if (set.has(id)) selected.delete(id)
  // 「只顯示未登記」時剛登記的要從清單消失；這一頁被登記光了就退回上一頁
  if (loaded && shared.value && props.sharedFilters.unregistered) {
    const left = rows.value.filter(bp => !set.has(bp._id)).length
    reload(!left && offset.value > 0 ? Math.max(0, offset.value - limit) : offset.value)
  }
})

let flashTimer = null
function flash(text, type = 'alert-success') {
  message.value = text
  messageType.value = type
  clearTimeout(flashTimer)
  flashTimer = setTimeout(() => { message.value = '' }, 6000)
}

async function register(uuids, method = '') {
  if (!uuids.length || submitting.value) return
  submitting.value = true
  try {
    const res = await props.fetcher('/player/blueprints/bulk', {
      method: 'POST',
      body: JSON.stringify({ blueprint_uuids: uuids, acquisition_method: (method || '').trim() }),
    })
    if (!res) { flash('網路錯誤，請稍後再試', 'alert-warning'); return }
    const data = await res.json().catch(() => null)
    if (!res.ok || !data?.success) {
      flash(data?.message || '登記失敗，請稍後再試', 'alert-warning')
      return
    }
    // 誠實回報：跳過與查不到的也要講，不然使用者會以為全部都登記進去了
    const parts = [`新增 ${data.added} 張`]
    if (data.skipped) parts.push(`跳過 ${data.skipped} 張（已登記過）`)
    if (data.not_found) parts.push(`${data.not_found} 張在主檔查不到`)
    flash(parts.join('，'), data.added ? 'alert-success' : 'alert-warning')
    uuids.forEach(id => selected.delete(id))
    emit('registered', data)
  } finally {
    submitting.value = false
  }
}
const typeOptions = computed(() => types.value.map(t => ({ value: t, label: blueprintTypeLabel(t) })))

// 共用搜尋卡（玩家頁）時條件卡不顯示；空結果訊息用共用條件判斷
const hasActiveFilters = computed(() => (shared.value
  ? !!(effectiveQuery.value || effectiveTypes.value.length || effectiveHasMissions.value)
  : (!!nameQuery.value.trim() || selectedTypes.value.length > 0 || !!availableSel.value || missingZhOnly.value
    || hasMissionsOnly.value || !!playerVisible.value)))

const expandedId = ref('')
const detail = ref(null)
const detailMissions = ref([])
const detailLoading = ref(false)
const missionsRef = ref(null)

async function getJson(path) {
  const res = await props.fetcher(path)
  return res?.ok ? await res.json().catch(() => null) : null
}

function query(params) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) v.forEach(x => sp.append(k, x))
    else if (v !== '' && v !== null && v !== undefined) sp.append(k, v)
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

// 點表頭排序（後端，見 src/models/item.py 的 BlueprintMaster.list_all）
const sort = useTableSort(null, { onChange: () => reload(0) })

async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  expandedId.value = ''
  if (!shared.value) lastName = effectiveQuery.value
  const body = await getJson(`/blueprint/master${query({
    q: effectiveQuery.value,
    output_type: effectiveTypes.value,
    available: effectiveAvailable.value,
    missing_zh: missingZhOnly.value ? 1 : '',
    has_missions: effectiveHasMissions.value ? 1 : '',
    player_visible: props.player ? '' : playerVisible.value,
    unregistered: shared.value && props.sharedFilters.unregistered ? 1 : '',
    ...sort.params.value,
    limit, offset: newOffset,
  })}`)
  if (body?.success) {
    rows.value = body.data || []
    total.value = body.total || 0
  } else {
    rows.value = []
    total.value = 0
    loadFailed.value = true
  }
  loading.value = false
}

function resetFilters() {
  nameQuery.value = ''
  selectedTypes.value = []
  availableSel.value = ''
  missingZhOnly.value = false
  hasMissionsOnly.value = false
  playerVisible.value = ''
  reload(0)
}

async function loadTypes() {
  const body = await getJson('/blueprint/master/types')
  if (body?.success) types.value = body.data || []
}

async function toggle(bp) {
  if (expandedId.value === bp._id) {
    expandedId.value = ''
    return
  }
  expandedId.value = bp._id
  detail.value = null
  detailMissions.value = []
  detailLoading.value = true
  const [body, mbody] = await Promise.all([
    getJson(`/blueprint/master/${encodeURIComponent(bp._id)}`),
    bp.mission_count ? getJson(`/mission/for-blueprint/${encodeURIComponent(bp._id)}`) : Promise.resolve(null),
  ])
  if (expandedId.value !== bp._id) return   // 載入途中已經點了別列
  detail.value = body?.success ? body.data : null
  detailMissions.value = mbody?.success ? (mbody.data || []) : []
  detailLoading.value = false
  if (detail.value) loadMaterialZh(detail.value)
}

function openMissions(bp) {
  missionsRef.value?.open({ uuid: bp._id, name: bp.name, name_zh: bp.name_zh, output_type: bp.output_type })
}

function fmtQty(m) {
  if (m.quantity_scu !== null && m.quantity_scu !== undefined) return `${m.quantity_scu} SCU`
  if (m.quantity !== null && m.quantity !== undefined) return `× ${m.quantity}`
  return '—'
}

function fmtSeconds(sec) {
  if (!sec && sec !== 0) return '—'
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return m ? (s ? `${m} 分 ${s} 秒` : `${m} 分`) : `${s} 秒`
}

let loaded = false
watch(() => props.active, (v) => {
  if (!v || loaded) return
  loaded = true
  if (!shared.value) loadTypes()
  reload(0)
}, { immediate: true })

// 共用搜尋卡每打一個字就會換一次，等停手 300ms 再查；還沒展開過（未載入）就先不查
let sharedTimer = null
watch(() => props.sharedFilters, () => {
  if (!loaded) return
  clearTimeout(sharedTimer)
  sharedTimer = setTimeout(() => reload(0), 300)
}, { deep: true })
// 後台搜尋卡的名稱：打字停 300ms 就查（比照玩家頁的共用搜尋卡）
let nameTimer = null
watch(nameQuery, () => {
  if (!loaded || shared.value) return
  clearTimeout(nameTimer)
  if (nameQuery.value.trim() === lastName) return   // 清除篩選時已經重查過
  nameTimer = setTimeout(() => reload(0), 300)
})
onBeforeUnmount(() => { clearTimeout(sharedTimer); clearTimeout(flashTimer); clearTimeout(nameTimer) })

// 上一頁／下一頁：載入後把列表頂端捲回畫面（不然會停在最下方的分頁按鈕，見 utils/scrollAnchor.js）
const rootEl = ref(null)
async function goPage(newOffset) {
  await reload(newOffset)
  scrollToListTop(rootEl.value)
}
</script>

<style scoped>
.bp-row { cursor: pointer; }
.bp-detail > td { background: var(--bs-tertiary-bg); }
.bp-registered > td { opacity: .6; }
.bp-submit { position: sticky; bottom: .5rem; z-index: 10; }
</style>
