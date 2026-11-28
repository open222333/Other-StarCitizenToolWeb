<template>
  <div class="sf-split">
    <div class="sf-toolbar">
      <!-- 查詢條件都記在網址裡，複製下來貼給隊友就是同一個查詢 -->
      <button type="button" class="btn btn-sm btn-primary" aria-label="複製查詢連結" @click="copySearchLink">
        <i class="bi bi-link-45deg me-1"></i><span class="sf-btn-text">複製連結</span>
      </button>
    </div>
    <div class="card scifi-card sf-search mb-3">
      <div class="card-body py-3">
        <div class="d-flex justify-content-between align-items-start mb-1">
          <span class="form-label small fw-semibold mb-0">搜尋條件</span>
          <button type="button" class="btn btn-sm btn-warning" @click="clearWhoFilters">清除全部</button>
        </div>
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-7">
            <label class="form-label small mb-1" for="who-name">名稱</label>
            <AutocompleteField id="who-name" v-model="whoName" :search="searchWhoNames" :get-label="whoNameLabel"
              :get-meta="whoNameMeta" aria-label="物品、藍圖或船艦名稱" placeholder="物品、藍圖或船艦名稱…" :min-chars="1"
              @select="onWhoNameSelect" />
          </div>
          <div class="col-12 col-md-5">
            <label class="form-label small mb-1" for="who-player">玩家</label>
            <AutocompleteField id="who-player" v-model="whoPlayerText" :search="searchPlayersLocal"
              :get-label="c => holderLabel(c.nickname, c.player_name, c.star_citizen_id)"
              aria-label="玩家id或暱稱" placeholder="點一下看全部玩家…" :min-chars="0" :debounce-ms="0"
              @select="c => { whoPlayerScid = c ? c.star_citizen_id : '' }" />
          </div>
          <div class="col-12">
            <span class="form-label small mb-1 d-block">種類</span>
            <!-- 全部／物品／藍圖／船艦：膠囊單選，數量標在後面 -->
            <SfChoice v-model="whoKind" required label="種類"
              :options="whoKinds.map(k => ({ value: k.key, label: k.label, count: k.count }))" />
          </div>
          <!-- 選了單一種類才出現它專用的條件（手機收進「篩選」面板） -->
          <SfFilterSheet v-if="whoKind === 'items'" :count="itemsSheetCount" title="物品篩選" @clear="clearItemsSheet">
            <div class="col-12 col-md-3">
              <label class="form-label small mb-1" for="items-type">物品類型</label>
              <MultiSelectFilter id="items-type" v-model="itemsSelectedTypes" :options="itemTypeTreeOpts"
                label="物品類型" placeholder="全部" block searchable />
            </div>
            <LocationAreaFilter :names="locations" :loc-label="locLabel" col-class="col-12 col-md-3"
              v-model:systems="itemsSelectedSystems" v-model:planets="itemsSelectedPlanets"
              v-model:locations="itemsSelectedLocations" />
          </SfFilterSheet>
          <SfFilterSheet v-if="whoKind === 'blueprints'" :count="bpHolderSheetCount" title="藍圖篩選" @clear="clearBpHolderSheet">
            <div class="col-12 col-md-6">
              <label class="form-label small mb-1" for="bp-type">藍圖類型</label>
              <MultiSelectFilter id="bp-type" v-model="bpSelectedTypes" :options="blueprintTypeOptions"
                label="藍圖類型" placeholder="全部" block searchable />
            </div>
          </SfFilterSheet>
          <SfFilterSheet v-if="whoKind === 'fleet'" :count="flSheetCount" title="船艦篩選" @clear="clearFlSheet">
            <div class="col-6 col-md-3">
              <label class="form-label small mb-1" for="fl-type">類型</label>
              <MultiSelectFilter id="fl-type" v-model="flSelectedTypes" :options="vehicleFacets.types"
                label="類型" placeholder="全部" block />
            </div>
            <div class="col-6 col-md-3">
              <label class="form-label small mb-1" for="fl-size">尺寸</label>
              <MultiSelectFilter id="fl-size" v-model="flSelectedSizes" :options="vehicleSizeOptions"
                label="尺寸" placeholder="全部" block />
            </div>
            <div class="col-12 col-md-3">
              <label class="form-label small mb-1" for="fl-mfr">廠商</label>
              <MultiSelectFilter id="fl-mfr" v-model="flSelectedMfrs" :options="manufacturerOptions"
                label="廠商" placeholder="全部" block searchable />
            </div>
            <div class="col-12 col-md-3">
              <label class="form-label small mb-1" for="fl-role">角色</label>
              <MultiSelectFilter id="fl-role" v-model="flSelectedRoles" :options="roleOptions"
                label="角色" placeholder="全部" block searchable />
            </div>
          </SfFilterSheet>
        </div>
      </div>
    </div>

    <div v-if="whoBusy && !whoShown.length" class="text-muted small">查詢中…</div>
    <div v-else-if="!whoShown.length" class="text-muted small">找不到符合條件的資料。</div>
    <div v-else>
      <div v-if="whoRows.length >= WHO_LIMIT && whoKind !== 'blueprints' && whoKind !== 'fleet'" class="sf-chip sf-chip--warn mb-2">
        物品只列出前 {{ WHO_LIMIT }} 筆，加條件可以縮小範圍</div>
      <!-- 一張表：物品／藍圖／船艦都在這裡，不屬於那一類的欄位留空；「詳細」展開持有者 -->
      <SortSelect v-if="isPhone" class="mb-2" :sort="whoSort" :options="WHO_SORT_OPTIONS" />
      <div class="card scifi-card" :class="{ 'sf-list-loading': whoBusy }">
      <div class="card-body p-0">
      <div style="overflow-x: auto">
      <table class="table table-hover align-middle mb-0 sf-stack who-table">
        <thead class="table-light">
          <tr>
            <SortTh :sort="whoSort" field="name" class="ps-3">名稱</SortTh>
            <SortTh :sort="whoSort" field="kind">種類</SortTh>
            <SortTh :sort="whoSort" field="type" class="d-none d-md-table-cell">類型</SortTh>
            <SortTh :sort="whoSort" field="size" class="d-none d-lg-table-cell">尺寸</SortTh>
            <SortTh :sort="whoSort" field="mfr" class="d-none d-lg-table-cell">廠商</SortTh>
            <SortTh :sort="whoSort" field="cargo" class="text-end d-none d-xl-table-cell">載貨</SortTh>
            <SortTh :sort="whoSort" field="holders" class="text-end">持有人數</SortTh>
            <SortTh :sort="whoSort" field="qty" class="text-end">數量</SortTh>
            <th class="pe-3"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in whoSort.sorted.value" :key="row.key">
          <tr>
            <td class="ps-3 sf-stack__title">
              <span class="fw-semibold">{{ row.name_zh || row.name }}</span>
              <i v-if="row.retired" class="bi bi-exclamation-triangle text-warning ms-1" title="這個物品已在新版本移除"></i>
              <i v-if="row.freeText" class="bi bi-pencil ms-1" title="自由輸入，沒有對應到遊戲配方"></i>
              <span v-if="row.note" class="sf-tree-chip ms-1" title="系統說明：同名變體的區別">{{ row.note }}</span>
              <span v-if="row.name_zh && row.name_zh !== row.name" class="sf-name__en">{{ row.name }}</span>
              <!-- 船艦：每位持有者每一艘的配件網址，按鈕標「玩家 · 識別名稱 · 配件碼」 -->
              <VehicleLoadoutLinks v-for="u in (row.kind === 'fleet' ? holderUnitLoadouts(row.src.holders) : [])" :key="u.key"
                :links="u.links" :prefix="u.prefix" button-class="btn-loadout" hide-label />
            </td>
            <td data-label="種類"><span class="sf-chip who-kind" :class="`who-kind--${row.kind}`">
              <i :class="WHO_KIND_ICON[row.kind]" class="me-1"></i>{{ WHO_KIND_LABEL[row.kind] }}</span></td>
            <td class="d-none d-md-table-cell" :class="{ 'who-na': !row.typeLabel }" data-label="類型">{{ row.typeLabel }}</td>
            <td class="d-none d-lg-table-cell" :class="{ 'who-na': !row.sizeLabel }" data-label="尺寸">{{ row.sizeLabel }}</td>
            <td class="d-none d-lg-table-cell" :class="{ 'who-na': !row.mfr }" data-label="廠商">{{ row.mfr }}</td>
            <td class="text-end text-nowrap d-none d-xl-table-cell" :class="{ 'who-na': !row.cargo }" data-label="載貨">{{ row.cargo ? scuLabel(row.cargo) : '' }}</td>
            <td class="text-end" data-label="持有人數">{{ row.holders }}</td>
            <td class="text-end" :class="{ 'who-na': row.qty == null }" data-label="數量">{{ row.qty ?? '' }}</td>
            <td class="text-end text-nowrap pe-3 sf-stack__actions">
              <CargoGridButton v-if="row.kind === 'fleet'" :fetcher="fetcher" :vehicle-uuid="row.src._id"
                :name="row.name_zh || row.name" button-class="me-2" />
              <button type="button" class="btn btn-sm btn-info" :aria-expanded="openTree.has(row.key) ? 'true' : 'false'"
                @click="toggleTree(row.key)">
                <i class="bi me-1" :class="openTree.has(row.key) ? 'bi-chevron-up' : 'bi-chevron-down'"></i>詳細
              </button>
            </td>
          </tr>
          <tr v-if="openTree.has(row.key)" class="sf-stack__detail">
            <td colspan="9" class="holder-detail">
              <div class="sf-sheet__head sf-stack__sheet-head">
                <h3 class="sf-sheet__title">{{ row.name_zh || row.name }}</h3>
                <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="toggleTree(row.key)"><i class="bi bi-x-lg"></i></button>
              </div>
              <!-- 物品：持有者（含公會共享庫）× 放的地點，一列一個地點 -->
              <table v-if="row.kind === 'items'" class="table align-middle mb-0 holder-sub">
                <thead><tr><th>持有者</th><th>地點</th><th class="text-end">數量</th></tr></thead>
                <tbody>
                  <template v-for="h in row.src.holders" :key="h.key">
                    <tr v-for="(place, j) in h.places" :key="j">
                      <td v-if="j === 0" :rowspan="h.places.length">
                        <span class="fw-semibold">{{ h.guild ? '公會共享庫' : holderLabel(h.row.nickname, h.row.player_name, h.row.player) }}</span>
                        <!-- 只有本人勾了公開才拿得到值，後端已經先遮蔽過 -->
                        <div v-if="!h.guild && discordLabel(h.row)" class="text-muted"><i class="bi bi-discord"></i> {{ discordLabel(h.row) }}</div>
                        <div v-if="h.places.length > 1" class="text-muted">共 {{ h.total }}</div>
                      </td>
                      <td>{{ locLabel(place.location) }}<span v-if="place.container" class="text-muted"> / {{ place.container }}</span></td>
                      <td class="text-end">{{ place.quantity }}</td>
                    </tr>
                  </template>
                </tbody>
              </table>
              <!-- 藍圖：持有者＋Discord -->
              <table v-else-if="row.kind === 'blueprints'" class="table align-middle mb-0 holder-sub">
                <thead><tr><th>持有者</th><th>Discord</th></tr></thead>
                <tbody>
                  <tr v-for="(h, i) in row.src.holders" :key="i">
                    <td class="fw-semibold">{{ holderLabel(h.nickname, h.player_name, h.star_citizen_id) }}</td>
                    <td><template v-if="discordLabel(h)"><i class="bi bi-discord"></i> {{ discordLabel(h) }}</template><span v-else class="text-muted">—</span></td>
                  </tr>
                </tbody>
              </table>
              <!-- 船艦：船艦資訊＋持有者、Discord、艘數、配件網址 -->
              <template v-else>
                <div class="mb-2">
                  <template v-if="row.src.vehicle?.cargo_capacity_scu">載貨 {{ scuLabel(row.src.vehicle.cargo_capacity_scu) }} · </template>
                  {{ vehicleTypeLabel(row.src.vehicle?.vehicle_type) }} ·
                  {{ vehicleSizeLabel(row.src.vehicle?.size_class) }} ·
                  {{ manufacturerLabel(row.src.vehicle?.manufacturer_name, row.src.vehicle?.manufacturer_code) }} ·
                  {{ vehicleRoleLabel(row.src.vehicle?.role, row.src.vehicle?.role_zh) }}
                </div>
                <div v-if="row.src.vehicle?.note" class="mb-2 vehicle-note">{{ row.src.vehicle.note }}</div>
                <table class="table align-middle mb-0 holder-sub">
                  <thead><tr><th>持有者</th><th>Discord</th><th class="text-end">艘數</th><th>配件網址</th></tr></thead>
                  <tbody>
                    <tr v-for="(h, i) in row.src.holders" :key="i">
                      <td class="fw-semibold">{{ holderLabel(h.nickname, h.player_name, h.star_citizen_id) }}</td>
                      <td><template v-if="discordLabel(h)"><i class="bi bi-discord"></i> {{ discordLabel(h) }}</template><span v-else class="text-muted">—</span></td>
                      <td class="text-end">{{ h.quantity || 1 }}</td>
                      <td>
                        <VehicleLoadoutLinks v-for="u in holderUnitLoadouts([h], false)" :key="u.key" :links="u.links"
                          :prefix="u.prefix" button-class="btn-loadout" hide-label />
                        <span v-if="!holderUnitLoadouts([h], false).length" class="text-muted">—</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </template>
            </td>
          </tr>
          </template>
        </tbody>
      </table>
      </div>
      </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import SfChoice from '@/components/SfChoice.vue'
/**
 * 查詢持有資訊（從 views/MyPlayerView.vue 拆出來，待辦 3-6）：別人的東西，唯讀。
 * 一張搜尋卡（共同條件：名稱、玩家；種類；選了單一種類才出現它專用的條件），
 * 一張整合列表（物品／藍圖／船艦混在一起，不屬於那一類的欄位留空），「詳細」展開持有者。
 * 查詢條件記在網址（?tab=search&q=…&p=…，鍵名見 SEARCH_URL_KEYS），重新整理或貼給隊友都是同一個查詢。
 * 選項資料（物品類型樹、藍圖類型、船艦 facets、地點）由 MyPlayerView 載入後傳進來，跟倉庫、艦隊共用。
 */
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AutocompleteField from '@/components/AutocompleteField.vue'
import CargoGridButton from '@/components/CargoGridButton.vue'
import LocationAreaFilter from '@/components/LocationAreaFilter.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import SfFilterSheet from '@/components/SfFilterSheet.vue'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import VehicleLoadoutLinks from '@/components/VehicleLoadoutLinks.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'
import { copyText } from '@/utils/clipboard'
import { itemTypeLabel, loadItemTypeZh } from '@/utils/itemType'
import { nameLabel, searchBlueprintNames, searchItemNames, searchVehicleNames } from '@/utils/nameLookup'
import { SEARCH_URL_KEYS } from '@/utils/playerTabs'
import { loadTranslations } from '@/utils/translations'
import { groupRoleOptions, manufacturerLabel, scuLabel, vehicleRoleLabel, vehicleSizeLabel, vehicleTypeLabel } from '@/utils/vehicle'

/** 第一次顯示過了沒（之前條件變了也不查） */
let loaded = false

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 目前顯示中（第一次顯示時才載資料；網址只在顯示中改） */
  active: { type: Boolean, default: false },
  locations: { type: Array, default: () => [] },
  locLabel: { type: Function, required: true },
  itemTypeTreeOpts: { type: Array, default: () => [] },
  blueprintTypeOptions: { type: Array, default: () => [] },
  vehicleFacets: { type: Object, default: () => ({ size_classes: [], types: [], manufacturers: [], roles: [] }) },
  vehicleSizeOptions: { type: Array, default: () => [] },
  manufacturerOptions: { type: Array, default: () => [] },
})

// 角色選項依大類分組（utils/vehicleRole.js）
const roleOptions = computed(() => groupRoleOptions(props.vehicleFacets.roles))

const route = useRoute()
const router = useRouter()
const { isPhone } = useBreakpoint()

/** 持有者顯示成「暱稱（遊戲ID）」。
 *
 * 暱稱是選填的，玩家也可能是舊資料／已被軟刪除而查不到名冊，所以要層層退回：
 * 暱稱 → player_name → 只剩遊戲ID 就單獨顯示它，絕不輸出「（TomLi_SC）」
 * 這種前面空一塊的字串。遊戲ID 本身缺失時（理論上不該發生）回 '—'。
 */
function holderLabel(nickname, playerName, scid) {
  const id = (scid || '').trim()
  const name = (nickname || '').trim() || (playerName || '').trim()
  if (!id) return name || '—'
  return name ? `${name}（${id}）` : id
}

/** 持有者的 Discord 聯絡方式，沒公開就回 ''。
 *
 * 後端已經按 discord_public 遮蔽過（見 src/models/player.py 的
 * display_names_by_scid 與 src/models/blueprint.py 的 _redact_contact），
 * 所以這裡拿到值就代表本人同意公開，前端不用再判斷旗標 —— 也刻意不接收
 * discord_public，避免哪天前端自己解讀旗標卻跟後端規則不一致。
 *
 * 兩個欄位都有時只顯示名稱：ID 是一串數字，人看了也不會拿去找人。
 */
function discordLabel(row) {
  const name = (row?.discord_name || '').trim()
  const id   = (row?.discord_id || '').trim()
  return name || id
}

/** 持有者每一艘的配件網址，按鈕前面標「玩家 · 識別名稱（沒填就第 n 艘）」；
 *  withPlayer＝false 時不標玩家（詳細裡的持有者表已經有玩家欄）。舊資料只有 loadout_links 的算第 1 艘 */
function holderUnitLoadouts(holders, withPlayer = true) {
  const out = []
  for (const h of holders || []) {
    const units = h.unit_loadouts?.length ? h.unit_loadouts : (h.loadout_links?.length ? [h.loadout_links] : [])
    const player = (h.nickname || h.player_name || h.star_citizen_id || '').trim()
    units.forEach((links, i) => {
      if (!links?.length) return
      const unit = (h.unit_names?.[i] || '').trim() || ((h.quantity || 1) > 1 ? `第 ${i + 1} 艘` : '')
      out.push({ key: `${h.star_citizen_id}|${i}`, links,
        prefix: [withPlayer ? player : '', unit].filter(Boolean).join(' · ') })
    })
  }
  return out
}

// 整合列表「詳細」展開的列：key 前綴 i|（物品）、b|（藍圖）、f|（船艦），各自重新查詢時清掉自己那一類
const openTree = reactive(new Set())
function toggleTree(key) {
  if (openTree.has(key)) openTree.delete(key)
  else openTree.add(key)
}
function clearTree(prefix) {
  for (const key of [...openTree]) if (key.startsWith(prefix)) openTree.delete(key)
}

// ── 查詢持有資訊的共同條件（名稱、玩家），三部分（物品／藍圖／船艦）都套用 ──
// 名稱：打字就當關鍵字篩（停手 350ms 再查，三部分都用同一個關鍵字）；從候選清單選定了某個東西，
// 它那一類改用精確值（物品 item_id、藍圖英文名、船 vehicle_id），另外兩類仍用欄位上的文字當關鍵字。
const whoName = ref('')
const whoPick = ref(null)          // { kind: 'item'|'bp'|'vehicle', id, name }
const whoNameQuery = ref('')
let whoNameTimer = null
watch(whoName, (v) => {
  clearTimeout(whoNameTimer)
  whoNameTimer = setTimeout(() => { whoNameQuery.value = (v || '').trim() }, 350)
})
// 玩家：id 或暱稱都能找，選定才算數
const whoPlayerText = ref('')
const whoPlayerScid = ref('')
const itemsSelectedItemId = computed(() => (whoPick.value?.kind === 'item' ? whoPick.value.id : null))
const itemsNameQuery = computed(() => (itemsSelectedItemId.value ? '' : whoNameQuery.value))
const bpSelectedName = computed(() => (whoPick.value?.kind === 'bp' ? whoPick.value.name : ''))
const bpNameQuery = computed(() => (bpSelectedName.value ? '' : whoNameQuery.value))
const flSelectedVehicleId = computed(() => (whoPick.value?.kind === 'vehicle' ? whoPick.value.id : ''))
const flNameQuery = computed(() => (flSelectedVehicleId.value ? '' : whoNameQuery.value))
const itemsPlayerScid = whoPlayerScid
const bpPlayerScid = whoPlayerScid
const flPlayerScid = whoPlayerScid

// ── 查詢 › 持有藍圖：誰登記了這張藍圖 ──────────────────────────
// 這是藍圖版的 /inventory/where —— 查的是別人的名冊，不是自己的。
//
// 欄位（藍圖名稱／藍圖類型／玩家id／玩家暱稱，AND 語意，見
// Blueprint.find_holders 的說明）：名稱、玩家是上方共同條件（見 whoName／whoPick），藍圖類型是這部分自己的。
// 沒有任何條件時列出全部（三部分都一樣）。
const bpHolders        = ref([])
const loadingBpHolders = ref(false)

// 「藍圖類型」可多選（取聯集）
const bpSelectedTypes   = ref([])

let bpHolderSeq = 0
async function loadBlueprintHolders() {
  const seq = ++bpHolderSeq
  clearTree('b|')
  loadingBpHolders.value = true
  const params = new URLSearchParams({ limit: '100' })
  if (bpSelectedName.value || bpNameQuery.value) params.set('q', bpSelectedName.value || bpNameQuery.value)
  bpSelectedTypes.value.forEach(t => params.append('output_type', t))
  if (bpPlayerScid.value) params.set('player_id', bpPlayerScid.value)
  const res = await props.fetcher(`/blueprint/holders?${params.toString()}`)
  if (seq !== bpHolderSeq) return   // 已經有更新的查詢在跑了
  loadingBpHolders.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  bpHolders.value = (res.ok && data?.success) ? (data.data || []) : []
}

watch([bpSelectedName, bpNameQuery, bpSelectedTypes, bpPlayerScid], () => { if (loaded) loadBlueprintHolders() })






// 查詢 › 持有藍圖：手機「篩選」面板裡的條件（名稱以外）
const bpHolderSheetCount = computed(() => bpSelectedTypes.value.length)
function clearBpHolderSheet() {
  if (bpSelectedTypes.value.length) bpSelectedTypes.value = []
}

// ── 查詢 › 持有物品（原「物品庫存」）：物品名稱／類型／地點／玩家id／玩家暱稱，AND 篩選 ──
//
// 舊版是一個關鍵字同時比對物品／玩家／地點取聯集（OR）。現在拆成 5 個各自
// autocomplete 選定的欄位，AND 語意（同時符合才顯示）——打 /inventory/search
// 帶 item_id / item_type / location / player_id，見 app/inventory/view.py
// 的 search_stock() 跟 Inventory.search_filtered()。
//
// 物品名稱／物品類型互斥：兩個都是在篩「item_id 要是哪些」，選了名稱等於
// 精準指定單一物品，這時類型篩選只會被後端忽略（search_filtered 的
// item_id 優先於 item_type），留著只會誤導「怎麼篩了兩個結果卻沒變」，
// 所以選其中一個時自動清空另一個。
const whoRows    = ref([])
// 物品庫存查詢結果整理成 物品 → 持有者 → 地點（後端回的是一列一個「誰、哪個物品、放哪裡」）
const whoTree = computed(() => {
  const items = new Map()
  for (const r of whoRows.value) {
    const itemKey = r.item_id || r.item_name
    if (!items.has(itemKey)) {
      items.set(itemKey, { key: itemKey, name: r.item_name, name_zh: r.item_name_zh,
        retired: r.item_retired, type: r.item_type, sub_type: r.item_sub_type, size: r.item_size,
        total: 0, holders: new Map() })
    }
    const item = items.get(itemKey)
    item.total += r.quantity || 0
    const guild = r.owner_type === 'guild'
    const holderKey = guild ? 'guild' : `p:${r.player || ''}`
    if (!item.holders.has(holderKey)) item.holders.set(holderKey, { key: holderKey, guild, row: r, total: 0, places: [] })
    const holder = item.holders.get(holderKey)
    holder.total += r.quantity || 0
    holder.places.push({ location: r.location, container: r.container, quantity: r.quantity })
  }
  return [...items.values()].map(item => ({ ...item, holders: [...item.holders.values()] }))
})
const loadingWho = ref(false)

// 「物品類型」「物品地點」可多選（同一欄位內取聯集，欄位之間 AND）
const itemsSelectedTypes     = ref([])
// 地點是「星系／行星／地點」三段（後端 /inventory/search 的 star_system／planet／location）
const itemsSelectedSystems   = ref([])
const itemsSelectedPlanets   = ref([])
const itemsSelectedLocations = ref([])


const hasStockFilter = computed(() => !!(
  itemsSelectedItemId.value || itemsNameQuery.value || itemsSelectedTypes.value.length ||
  itemsSelectedSystems.value.length || itemsSelectedPlanets.value.length ||
  itemsSelectedLocations.value.length || itemsPlayerScid.value
))

// 每次搜尋遞增。慢的舊請求回來時若序號已過期就丟掉。
let whoSeq = 0

// 沒選任何條件時列出全部（all=1，最多 WHO_LIMIT 筆）
const WHO_LIMIT = 300
async function runStockSearch() {
  const seq = ++whoSeq
  clearTree('i|')
  loadingWho.value = true
  const params = new URLSearchParams({ limit: String(WHO_LIMIT) })
  if (!hasStockFilter.value) params.set('all', '1')
  if (itemsSelectedItemId.value) params.set('item_id', itemsSelectedItemId.value)
  else {
    itemsSelectedTypes.value.forEach(t => params.append('item_type', t))
    if (itemsNameQuery.value) params.set('name', itemsNameQuery.value)
  }
  itemsSelectedSystems.value.forEach(sys => params.append('star_system', sys))
  itemsSelectedPlanets.value.forEach(p => params.append('planet', p))
  itemsSelectedLocations.value.forEach(loc => params.append('location', loc))
  if (itemsPlayerScid.value) params.set('player_id', itemsPlayerScid.value)
  const res = await props.fetcher(`/inventory/search?${params.toString()}`)
  if (seq !== whoSeq) return          // 已經有更新的搜尋在跑了
  loadingWho.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  whoRows.value = (res.ok && data?.success) ? (data.data || []) : []
  loadItemTypeZh(whoRows.value.map(r => r.item_type).filter(Boolean), whoRows.value.map(r => r.item_sub_type).filter(Boolean))
}

watch([itemsSelectedItemId, itemsNameQuery, itemsSelectedTypes, itemsSelectedSystems, itemsSelectedPlanets,
  itemsSelectedLocations, itemsPlayerScid], () => { if (loaded) runStockSearch() })





// ── 玩家名單（「查詢」各分頁的玩家id／玩家暱稱欄位共用）──────────────
//
// 一進「查詢」就把全公會玩家名單載一次（/player/search 不帶 q＝列出全部），
// 欄位一 focus 就列出全部玩家，打字時在前端逐字篩選——名單只有幾十～
// 幾百人，比每打一個字就打一次 API 順暢，也不會有「打太快結果跳動」的問題。
const playerRoster = ref([])
let rosterLoading = null

function ensureRoster() {
  if (playerRoster.value.length) return Promise.resolve()
  if (!rosterLoading) {
    rosterLoading = (async () => {
      const res = await props.fetcher('/player/search?limit=1000')
      const data = res ? await res.json().catch(() => null) : null
      if (res?.ok && data?.success) playerRoster.value = data.data || []
    })().finally(() => { rosterLoading = null })
  }
  return rosterLoading
}

async function searchPlayersLocal(q) {
  await ensureRoster()
  const query = (q || '').trim().toLowerCase()
  if (!query) return playerRoster.value
  return playerRoster.value.filter(p =>
    [p.star_citizen_id, p.nickname, p.player_name]
      .some(v => (v || '').toLowerCase().includes(query)))
}


// 查詢 › 持有物品：手機「篩選」面板裡的條件（名稱以外）
const itemsSheetCount = computed(() => itemsSelectedTypes.value.length + itemsSelectedSystems.value.length
  + itemsSelectedPlanets.value.length + itemsSelectedLocations.value.length)
function clearItemsSheet() {
  if (itemsSelectedTypes.value.length) itemsSelectedTypes.value = []
  if (itemsSelectedSystems.value.length) itemsSelectedSystems.value = []
  if (itemsSelectedPlanets.value.length) itemsSelectedPlanets.value = []
  if (itemsSelectedLocations.value.length) itemsSelectedLocations.value = []
}

// ── 查詢 › 持有船艦：誰有哪款船 ──────────────────────────────
//
// 船艦名稱／類型／尺寸／廠商／角色／玩家id／玩家暱稱，AND 語意，打
// /player/fleet/holders。跟「持有藍圖」一樣：都沒選定時列出全部人的艦隊；
// 船艦名稱打字就當關鍵字篩（q），選定了就用那一款（vehicle_id）。
const fleetHolders        = ref([])
const loadingFleetHolders = ref(false)

// 類型／尺寸／廠商／角色可多選（同一欄位內取聯集，欄位之間 AND）
const flSelectedTypes      = ref([])
const flSelectedSizes      = ref([])
const flSelectedMfrs       = ref([])
const flSelectedRoles      = ref([])


let fleetHolderSeq = 0
async function loadFleetHolders() {
  const seq = ++fleetHolderSeq
  clearTree('f|')
  loadingFleetHolders.value = true
  const params = new URLSearchParams({ limit: '100' })
  if (flSelectedVehicleId.value) params.set('vehicle_id', flSelectedVehicleId.value)
  else if (flNameQuery.value) params.set('q', flNameQuery.value)
  flSelectedTypes.value.forEach(v => params.append('type', v))
  flSelectedSizes.value.forEach(v => params.append('size_class', v))
  flSelectedMfrs.value.forEach(v => params.append('manufacturer_code', v))
  flSelectedRoles.value.forEach(v => params.append('role', v))
  if (flPlayerScid.value) params.set('player_id', flPlayerScid.value)
  const res = await props.fetcher(`/player/fleet/holders?${params.toString()}`)
  if (seq !== fleetHolderSeq) return   // 已經有更新的查詢在跑了
  loadingFleetHolders.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  fleetHolders.value = (res.ok && data?.success) ? (data.data || []) : []
}

watch([flSelectedVehicleId, flNameQuery, flSelectedTypes, flSelectedSizes, flSelectedMfrs, flSelectedRoles, flPlayerScid],
  () => { if (loaded) loadFleetHolders() })




// 查詢 › 持有船艦：手機「篩選」面板裡的條件（名稱以外）
const flSheetCount = computed(() => flSelectedTypes.value.length + flSelectedSizes.value.length
  + flSelectedMfrs.value.length + flSelectedRoles.value.length)
function clearFlSheet() {
  if (flSelectedTypes.value.length) flSelectedTypes.value = []
  if (flSelectedSizes.value.length) flSelectedSizes.value = []
  if (flSelectedMfrs.value.length) flSelectedMfrs.value = []
  if (flSelectedRoles.value.length) flSelectedRoles.value = []
}


// ── 查詢持有資訊：共同「名稱」欄的候選（物品／藍圖／船艦一起列，標出是哪一類）──
const WHO_KINDS = { item: '物品', bp: '藍圖', vehicle: '船艦' }
async function searchWhoNames(q) {
  const [items, bps, vehicles] = await Promise.all([searchItemNames(props.fetcher, q), searchBlueprintNames(props.fetcher, q), searchVehicleNames(props.fetcher, q)])
  return [
    ...items.slice(0, 8).map(c => ({ kind: 'item', c })),
    ...bps.slice(0, 8).map(c => ({ kind: 'bp', c })),
    ...vehicles.slice(0, 8).map(c => ({ kind: 'vehicle', c })),
  ]
}
function whoNameLabel(x) {
  return nameLabel(x.c)
}
function whoNameMeta(x) {
  const en = x.c.name_zh && x.c.name !== x.c.name_zh ? x.c.name : ''
  return [WHO_KINDS[x.kind], en].filter(Boolean).join(' · ')
}
function onWhoNameSelect(x) {
  // 打字中（還沒選定）會先送 null：回到關鍵字模式
  whoPick.value = x ? { kind: x.kind, id: x.c._id, name: x.c.name } : null
}
function clearWhoFilters() {
  whoName.value = ''
  whoPick.value = null
  whoPlayerText.value = ''
  whoPlayerScid.value = ''
  whoKind.value = ''
  clearItemsSheet()
  clearBpHolderSheet()
  clearFlSheet()
}
// ── 整合列表：物品／藍圖／船艦整理成同一種列，不屬於那一類的欄位留空（null／''）──
const WHO_KIND_LABEL = { items: '物品', blueprints: '藍圖', fleet: '船艦' }
const WHO_KIND_ICON = { items: 'bi bi-box-seam', blueprints: 'bi bi-diagram-3', fleet: 'bi bi-rocket-takeoff' }
const WHO_KIND_ORDER = { items: 0, blueprints: 1, fleet: 2 }
// 種類：'' ＝全部；選了單一種類才出現它專用的條件，換種類時清掉其他種類的專用條件
const whoKind = ref('')
watch(whoKind, (k) => {
  if (k !== 'items') clearItemsSheet()
  if (k !== 'blueprints') clearBpHolderSheet()
  if (k !== 'fleet') clearFlSheet()
})
const whoAll = computed(() => [
  ...whoTree.value.map(i => ({
    kind: 'items', key: `i|${i.key}`, name: i.name, name_zh: i.name_zh, retired: i.retired,
    typeLabel: itemTypeLabel(i.type, i.sub_type) || '', sizeLabel: i.size != null ? `S${i.size}` : '', sizeSort: i.size ?? null,
    mfr: '', cargo: null, holders: i.holders.length, qty: i.total, src: i,
  })),
  ...bpHolders.value.map(g => ({
    kind: 'blueprints', key: `b|${g._id}`, name: g.name, name_zh: g.name_zh, freeText: !g.blueprint_uuid,
    typeLabel: g.output_type ? blueprintTypeLabel(g.output_type) : '', sizeLabel: '', sizeSort: null,
    mfr: '', cargo: null, holders: g.holder_count, qty: null, src: g,
  })),
  ...fleetHolders.value.map(g => ({
    kind: 'fleet', key: `f|${g._id}`, name: g.vehicle?.name || g.name, name_zh: g.vehicle?.name_zh, note: g.vehicle?.system_note,
    typeLabel: vehicleTypeLabel(g.vehicle?.vehicle_type) || '', sizeLabel: vehicleSizeLabel(g.vehicle?.size_class) || '',
    sizeSort: g.vehicle?.size_class ?? null,
    mfr: manufacturerLabel(g.vehicle?.manufacturer_name, g.vehicle?.manufacturer_code) || '',
    cargo: g.vehicle?.cargo_capacity_scu || null, holders: g.holder_count, qty: g.total_quantity, src: g,
  })),
])
const whoShown = computed(() => (whoKind.value ? whoAll.value.filter(r => r.kind === whoKind.value) : whoAll.value))
const whoBusy = computed(() => loadingWho.value || loadingBpHolders.value || loadingFleetHolders.value)
// 種類按鈕上的數量
const whoKinds = computed(() => {
  const n = k => (whoAll.value.filter(r => r.kind === k).length)
  return [
    { key: '', label: '全部', count: whoAll.value.length },
    { key: 'items', label: '物品', icon: 'bi bi-box-seam', count: loadingWho.value ? '…' : n('items') },
    { key: 'blueprints', label: '藍圖', icon: 'bi bi-diagram-3', count: loadingBpHolders.value ? '…' : n('blueprints') },
    { key: 'fleet', label: '船艦', icon: 'bi bi-rocket-takeoff', count: loadingFleetHolders.value ? '…' : n('fleet') },
  ]
})
// 空值（不屬於那一類）一律排最後，見 useTableSort
const whoSort = useTableSort(whoShown, { accessors: {
  name: r => r.name_zh || r.name, kind: r => WHO_KIND_ORDER[r.kind], type: r => r.typeLabel || null,
  size: r => r.sizeSort, mfr: r => r.mfr || null, cargo: r => r.cargo, holders: r => r.holders, qty: r => r.qty,
} })
// 手機的排序下拉（表頭在手機上看不到）
const WHO_SORT_OPTIONS = [{ field: 'name', label: '名稱' }, { field: 'kind', label: '種類' }, { field: 'type', label: '類型' },
  { field: 'size', label: '尺寸' }, { field: 'mfr', label: '廠商' }, { field: 'cargo', label: '載貨' },
  { field: 'holders', label: '持有人數' }, { field: 'qty', label: '數量' }]

// ── 查詢條件記在網址（?tab=search&q=…&p=…），重新整理或貼給隊友都是同一個查詢 ──
// q：名稱欄文字；pk／pid／pn：選定的候選（類別、id、英文名）；p：玩家遊戲ID；其餘是三部分各自的多選條件
const SEARCH_URL_ARR = {
  i_t: itemsSelectedTypes, i_sys: itemsSelectedSystems, i_pl: itemsSelectedPlanets, i_loc: itemsSelectedLocations,
  b_t: bpSelectedTypes,
  f_t: flSelectedTypes, f_s: flSelectedSizes, f_m: flSelectedMfrs, f_r: flSelectedRoles,
}
const asArray = v => (v == null ? [] : Array.isArray(v) ? v : [v]).filter(Boolean).map(String)

function applySearchQuery(q) {
  if (q.tab !== 'search') return
  if (WHO_KIND_LABEL[q.k]) whoKind.value = q.k
  for (const [k, r] of Object.entries(SEARCH_URL_ARR)) if (q[k] != null) r.value = asArray(q[k])
  if (typeof q.q === 'string') {
    whoName.value = q.q
    whoNameQuery.value = q.q.trim()
  }
  if (WHO_KINDS[q.pk] && typeof q.pid === 'string') whoPick.value = { kind: q.pk, id: q.pid, name: q.pn || '' }
  if (typeof q.p === 'string' && q.p) {
    whoPlayerScid.value = q.p
    whoPlayerText.value = q.p
    // 名單載入後換成「暱稱（id）」
    ensureRoster().then(() => {
      const r = playerRoster.value.find(x => x.star_citizen_id === q.p)
      if (r && whoPlayerScid.value === q.p) whoPlayerText.value = holderLabel(r.nickname, r.player_name, q.p)
    })
  }
}

function searchUrlQuery() {
  const out = {}
  if (whoKind.value) out.k = whoKind.value
  if (whoName.value.trim()) out.q = whoName.value.trim()
  if (whoPick.value) {
    out.pk = whoPick.value.kind
    out.pid = String(whoPick.value.id)
    if (whoPick.value.name) out.pn = whoPick.value.name
  }
  if (whoPlayerScid.value) out.p = whoPlayerScid.value
  for (const [k, r] of Object.entries(SEARCH_URL_ARR)) if (r.value.length) out[k] = [...r.value]
  return out
}
let searchUrlTimer = null
watch([whoKind, whoName, whoPick, whoPlayerScid, ...Object.values(SEARCH_URL_ARR)], () => {
  clearTimeout(searchUrlTimer)
  searchUrlTimer = setTimeout(() => {
    if (!props.active) return
    const query = { ...route.query }
    SEARCH_URL_KEYS.forEach(k => delete query[k])
    router.replace({ query: { ...query, ...searchUrlQuery() } })
  }, 300)
}, { deep: true })

const copySearchLink = () => copyText(window.location.href, { okText: '已複製連結' })


// 第一次顯示時三部分一起載入；之後條件改了由各自的 watch 重查（loaded 之前不查）。
// 等 nextTick：網址帶進來的條件（applySearchQuery）觸發的 watch 先跑完，才不會同一組條件查兩次
watch(() => props.active, (on) => {
  if (!on || loaded) return
  nextTick(() => {
    if (loaded) return
    loaded = true
    ensureRoster()
    runStockSearch()
    loadBlueprintHolders()
    loadFleetHolders()
  })
}, { immediate: true })

// 查詢結果裡的地點查一次翻譯（查過的有快取）
watch(whoRows, rows => loadTranslations('location', rows.map(r => r.location)))

applySearchQuery(route.query)
</script>

<style scoped>
/* 「詳細」：持有者小表（底色跟我的艦隊的詳細一樣） */
.holder-detail { background: var(--sf-panel-2); }
/* 整合列表：種類膠囊 */
/* 種類三種顏色，跟著網站配色：物品＝主強調色、船艦＝次要強調色（跟配件網址按鈕同色）、藍圖＝綠色（亮底模式 Bootstrap 自動換深） */
.who-kind--items { --who-kind: var(--sf-accent-rgb); }
.who-kind--fleet { --who-kind: var(--sf-accent-2-rgb); }
.who-kind--blueprints { --who-kind: var(--bs-success-rgb); }
.scifi-page .sf-chip.who-kind { white-space: nowrap;
  color: var(--sf-text-strong); font-weight: 600;
  background: rgba(var(--who-kind), .2); border-color: rgba(var(--who-kind), .75);
}
.who-kind .bi { color: rgb(var(--who-kind)); }
/* 手機卡片：不屬於那一類的欄位（空的）整格不顯示，免得只剩標籤 */
@media (max-width: 767.98px) {
  .scifi-page table.sf-stack.who-table tr:not(.sf-stack__detail) > td.who-na[data-label] { display: none !important; }
}
.holder-sub { --bs-table-bg: transparent; }
.holder-sub > :not(caption) > * > * { padding: .4rem .6rem; }
.holder-sub td[rowspan] { vertical-align: top; }
/* 後台手寫的艦船說明（換行照原樣顯示） */
.vehicle-note { white-space: pre-line; }
</style>
