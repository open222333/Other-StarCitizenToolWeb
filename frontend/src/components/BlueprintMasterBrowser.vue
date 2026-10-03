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

  玩家頁面顯示（後台才有的欄位與篩選）：PlayerVisibleToggle，規則見 src/models/visibility.py；
  玩家 token 呼叫 /blueprint/master 時後端本來就只回顯示的。

  中文：藍圖名稱用同步時存的 name_zh（依產出物 class 查 sc_translations，比用
  英文名稱反查準）；類型用 utils/blueprintOutputType.js；材料名稱用
  utils/translations.js 即時查。
-->
<template>
  <div>
    <div :class="[cardClass, 'mb-3']">
      <div class="card-body py-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <input v-model="nameQuery" type="search" class="form-control form-control-sm"
            style="max-width: 14rem" placeholder="搜尋英文或中文名稱..." :aria-label="'搜尋藍圖名稱'"
            @change="reload(0)">
          <MultiSelectFilter :model-value="selectedTypes" label="類型" :options="typeOptions" searchable
            @update:model-value="v => { selectedTypes = v; reload(0) }" />
          <div class="form-check form-check-inline mb-0 ms-1">
            <input :id="`${uid}-available`" v-model="availableOnly" class="form-check-input" type="checkbox"
              @change="reload(0)">
            <label class="form-check-label small" :for="`${uid}-available`">只看預設可用</label>
          </div>
          <div v-if="!player" class="form-check form-check-inline mb-0">
            <input :id="`${uid}-missing-zh`" v-model="missingZhOnly" class="form-check-input" type="checkbox"
              @change="reload(0)">
            <label class="form-check-label small" :for="`${uid}-missing-zh`">只看沒有中文</label>
          </div>
          <div class="form-check form-check-inline mb-0">
            <input :id="`${uid}-has-missions`" v-model="hasMissionsOnly" class="form-check-input" type="checkbox"
              @change="reload(0)">
            <label class="form-check-label small" :for="`${uid}-has-missions`">只看需任務解鎖</label>
          </div>
          <select v-if="!player" v-model="playerVisible" class="form-select form-select-sm w-auto"
            aria-label="玩家頁面顯示" @change="reload(0)">
            <option value="">玩家頁面：全部</option>
            <option value="1">玩家頁面：顯示</option>
            <option value="0">玩家頁面：不顯示</option>
          </select>
          <button v-if="hasActiveFilters" type="button" class="btn btn-sm btn-link" @click="resetFilters">
            清除全部篩選
          </button>
        </div>
      </div>
    </div>

    <div :class="cardClass">
      <div class="card-body p-0">
        <div style="overflow-x:auto">
          <table class="table table-hover align-middle mb-0" :class="{ 'table-sm': player }">
            <thead :class="{ 'table-light': !player }">
              <tr>
                <th class="ps-3">{{ player ? '名稱' : '藍圖（英文）' }}</th>
                <th v-if="!player">中文</th>
                <th>類型</th>
                <th>等級</th>
                <th>製作時間</th>
                <th class="text-end">材料數</th>
                <th>預設可用</th>
                <th class="text-end" :class="{ 'pe-3': player }">解鎖任務</th>
                <th v-if="!player" class="pe-3">玩家頁面</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="loading">
                <td :colspan="colspan" class="text-center py-4 text-muted">
                  <span class="spinner-border spinner-border-sm me-2"></span>載入中...
                </td>
              </tr>
              <tr v-else-if="loadFailed">
                <td :colspan="colspan" class="text-center py-4">
                  <span class="text-warning"><i class="bi bi-exclamation-triangle me-1"></i>讀取藍圖資料失敗。</span>
                  <button class="btn btn-sm btn-link p-0 ms-1" @click="reload(offset)">重試</button>
                </td>
              </tr>
              <tr v-else-if="!rows.length">
                <td :colspan="colspan" class="text-center py-4 text-muted">
                  {{ hasActiveFilters ? '沒有符合篩選條件的藍圖。' : '尚無藍圖資料' }}
                </td>
              </tr>
              <template v-else>
                <template v-for="bp in rows" :key="bp._id">
                  <tr class="bp-row" role="button" tabindex="0" :aria-expanded="expandedId === bp._id ? 'true' : 'false'"
                    @click="toggle(bp)" @keydown.enter.self="toggle(bp)">
                    <td class="ps-3">
                      <i class="bi me-1 small text-muted" :class="expandedId === bp._id ? 'bi-chevron-down' : 'bi-chevron-right'"></i>
                      <template v-if="player">
                        <button v-if="bp.mission_count" type="button" class="bp-link fw-semibold"
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
                    <td class="small">{{ bp.output_type ? blueprintTypeLabel(bp.output_type) : (bp.output_type_label || '—') }}</td>
                    <td class="small">{{ bp.output_grade || '—' }}</td>
                    <td class="small">{{ bp.craft_time_label || fmtSeconds(bp.craft_time_seconds) }}</td>
                    <td class="small text-end">{{ bp.ingredient_count ?? '—' }}</td>
                    <td class="small">{{ bp.is_available_by_default ? '是' : '否' }}</td>
                    <td class="small text-end" :class="{ 'pe-3': player }">
                      <span v-if="bp.mission_count">{{ bp.mission_count }} 個</span>
                      <span v-else class="text-muted">—</span>
                    </td>
                    <td v-if="!player" class="pe-3">
                      <PlayerVisibleToggle dataset="blueprints" :doc-id="bp._id" :row="bp" />
                    </td>
                  </tr>
                  <tr v-if="expandedId === bp._id" class="bp-detail">
                    <td :colspan="colspan" class="ps-5 pe-3 py-2 small">
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
                            <button v-if="player" type="button" class="bp-link" @click="openMissions(bp)">
                              {{ zhPair(m.title, m.title_zh) }}
                            </button>
                            <RouterLink v-else :to="{ path: '/missions', query: { id: m._id } }">{{ zhPair(m.title, m.title_zh) }}</RouterLink>
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
          :disabled="offset === 0 || loading" @click="reload(Math.max(0, offset - limit))">上一頁</button>
        <button class="btn" :class="player ? 'btn-scifi-outline' : 'btn-outline-secondary'"
          :disabled="offset + limit >= total || loading" @click="reload(offset + limit)">下一頁</button>
      </div>
    </div>

    <BlueprintMissionsModal v-if="player" ref="missionsRef" :fetcher="fetcher" />
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { apiFetch } from '@/api'
import BlueprintMissionsModal from '@/components/BlueprintMissionsModal.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import PlayerVisibleToggle from '@/components/PlayerVisibleToggle.vue'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'
import { loadTranslations, translate } from '@/utils/translations'
import { factionLabel, fmtChance, zhPair } from '@/utils/mission'

const props = defineProps({
  /** 帶身分的 fetch（後台 apiFetch、玩家頁 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, default: apiFetch },
  /** 玩家頁模式：名稱合併成一欄、有任務的名稱可點開看解鎖任務、沒有後台專用的篩選 */
  player: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card shadow-sm border-0' },
  /** 玩家頁分頁用 v-show 一直掛著，第一次變成可見才載入（跟 MiningLookup 一樣） */
  active: { type: Boolean, default: true },
})

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
const selectedTypes = ref([])
const availableOnly = ref(false)
const missingZhOnly = ref(false)
const hasMissionsOnly = ref(false)
const playerVisible = ref('')

const colspan = computed(() => (props.player ? 7 : 9))
const typeOptions = computed(() => types.value.map(t => ({ value: t, label: blueprintTypeLabel(t) })))

const hasActiveFilters = computed(() =>
  !!nameQuery.value.trim() || selectedTypes.value.length > 0 || availableOnly.value || missingZhOnly.value
  || hasMissionsOnly.value || !!playerVisible.value)

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

async function reload(newOffset = 0) {
  offset.value = newOffset
  loading.value = true
  loadFailed.value = false
  expandedId.value = ''
  const body = await getJson(`/blueprint/master${query({
    q: nameQuery.value.trim(),
    output_type: selectedTypes.value,
    available: availableOnly.value ? 1 : '',
    missing_zh: missingZhOnly.value ? 1 : '',
    has_missions: hasMissionsOnly.value ? 1 : '',
    player_visible: props.player ? '' : playerVisible.value,
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
  availableOnly.value = false
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
  if (detail.value) {
    const mats = [...(detail.value.ingredients || []), ...(detail.value.dismantle_returns || [])]
    const names = mats.map(m => m.name).filter(Boolean)
    loadTranslations('item', mats.filter(m => !isResource(m)).map(m => m.name))
    loadTranslations('mining_resource', names)
  }
}

function openMissions(bp) {
  missionsRef.value?.open({ uuid: bp._id, name: bp.name, name_zh: bp.name_zh, output_type: bp.output_type })
}

function isResource(m) {
  return m.kind === 'resource' || (!m.kind && !!m.resource_type_uuid)
}

function materialLabel(m) {
  const name = m.name || '—'
  const zh = (isResource(m) ? translate('mining_resource', name) : '') || translate('item', name)
  return zh ? `${zh}（${name}）` : name
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
  loadTypes()
  reload(0)
}, { immediate: true })
</script>

<style scoped>
.bp-row { cursor: pointer; }
.bp-detail > td { background: var(--bs-tertiary-bg); }
/* 玩家頁：可以點開看解鎖任務的藍圖名稱（跟 MyPlayerView／BlueprintBulkRegister 同一個樣式） */
.bp-link {
  padding: 0; border: 0; background: none; text-align: left; font: inherit;
  color: var(--sf-accent-text, var(--sf-accent));
  border-bottom: 1px dashed currentColor; cursor: pointer;
}
.bp-link:hover { color: var(--sf-accent-2-text, var(--sf-accent-2)); }
</style>
