<!--
  玩家頁「配裝模擬」：選一艘船，依掛點分區列出每一格的配件，點「更換」從可裝的配件裡挑（種類、尺寸、
  專屬標籤都對得上才列），左邊即時算出傷害（駕駛／有人砲塔／遙控砲塔／點防禦）、飛彈、護盾、量子航程，
  以及不隨配件變動的船體、裝甲、偏轉與穿透倍率。
  資料：GET /item/loadout/ships、/item/loadout/ships/<id>、/item/loadout/items（src/models/loadout.py，
  scunpacked-data；後台「配裝」同步項目）。計算在 utils/loadoutCalc.js。
  換過的格子記在網址 ?ship=&lo=（可複製連結分享）與這台瀏覽器。
-->
<template>
  <div>
    <SfState :loading="loading" :error="error" :empty="loaded && !ships.length"
      empty-text="尚無配裝資料，請管理員在後台同步「配裝」。" @retry="loadShips">
      <div class="row g-3">
        <div class="col-12 col-xl-4">
          <div :class="[cardClass, 'sf-search', 'mb-3']">
            <div class="card-body">
              <label class="form-label small fw-semibold mb-1" for="lo-ship">船艦</label>
              <AutocompleteField id="lo-ship" v-model="shipText" :search="searchShips" :get-label="shipLabel"
                :get-meta="shipMeta" :min-chars="0" :debounce-ms="0" aria-label="選擇船艦" @select="pickShip" />
              <div v-if="fleetShips.length" class="d-flex flex-wrap gap-2 mt-2">
                <button v-for="s in fleetShips" :key="s.id" type="button" class="btn btn-sm"
                  :class="s.id === ship?.id ? 'btn-success' : 'btn-secondary'" @click="pickShip(s)">
                  <i class="bi bi-rocket-takeoff me-1"></i>{{ s.name_zh || s.name }}</button>
              </div>
              <div v-if="ship" class="d-flex flex-wrap align-items-center gap-2 mt-2">
                <span class="sf-chip" :class="{ 'sf-chip--accent': changes.length }">已更換 {{ changes.length }} 格</span>
                <button type="button" class="btn btn-sm btn-warning ms-auto" :disabled="!changes.length" @click="resetLoadout">
                  <i class="bi bi-arrow-counterclockwise me-1"></i>重設配裝</button>
                <button type="button" class="btn btn-sm btn-info" @click="copyLink">
                  <i class="bi bi-link-45deg me-1"></i>{{ copied ? '已複製' : '複製連結' }}</button>
              </div>
            </div>
          </div>

          <SfState :loading="shipLoading" :error="shipError" @retry="reloadShip">
            <template v-if="ship">
              <div :class="[cardClass, 'mb-3']">
                <div class="card-body">
                  <div class="lo-mfr">{{ ship.manufacturer_name || ship.manufacturer }}</div>
                  <h3 class="lo-title">{{ ship.name_zh || ship.name }}</h3>
                  <div v-if="ship.name_zh && ship.name_zh !== ship.name" class="lo-mfr">{{ ship.name }}</div>
                  <div class="d-flex flex-wrap gap-2 mt-2">
                    <span v-if="ship.size" class="sf-chip sf-chip--accent">S{{ ship.size }}</span>
                    <span v-if="ship.role_zh || ship.role" class="sf-chip">{{ ship.role_zh || ship.role }}</span>
                    <span v-if="ship.crew" class="sf-chip"><i class="bi bi-people me-1"></i>{{ ship.crew }} 人</span>
                    <span v-if="ship.cargo" class="sf-chip"><i class="bi bi-box-seam me-1"></i>{{ fmtNum(ship.cargo) }} SCU</span>
                  </div>
                </div>
              </div>

              <!-- 傷害 -->
              <div :class="[cardClass, 'mb-3']">
                <div class="card-body">
                  <h4 class="lo-h"><i class="bi bi-crosshair me-1"></i>傷害</h4>
                  <div class="lo-tiles">
                    <div class="lo-tile"><div class="lo-tile__v">{{ fmtNum(summary.total.alpha) }}</div><div class="lo-tile__l">單發總傷害</div></div>
                    <div class="lo-tile lo-tile--hi"><div class="lo-tile__v">{{ fmtNum(summary.total.sustained) }}</div><div class="lo-tile__l">持續 DPS</div></div>
                    <div class="lo-tile"><div class="lo-tile__v">{{ fmtNum(summary.total.dps) }}</div><div class="lo-tile__l">爆發 DPS</div></div>
                  </div>
                  <table class="table table-sm lo-table mb-0">
                    <thead><tr><th>來源</th><th class="text-end">單發</th><th class="text-end">持續</th><th class="text-end">爆發</th></tr></thead>
                    <tbody>
                      <tr v-for="g in weaponRows" :key="g.key">
                        <td>{{ g.label }}<span class="lo-muted ms-1">{{ g.count }} 門</span></td>
                        <td class="text-end">{{ fmtNum(g.alpha) }}</td>
                        <td class="text-end">{{ fmtNum(g.sustained) }}</td>
                        <td class="text-end">{{ fmtNum(g.dps) }}</td>
                      </tr>
                      <tr v-if="slavedDiff">
                        <td>駕駛可連動合計</td>
                        <td class="text-end">{{ fmtNum(summary.pilotTotal.alpha) }}</td>
                        <td class="text-end">{{ fmtNum(summary.pilotTotal.sustained) }}</td>
                        <td class="text-end">{{ fmtNum(summary.pilotTotal.dps) }}</td>
                      </tr>
                      <tr v-if="summary.missiles.count">
                        <td>飛彈與魚雷<span class="lo-muted ms-1">{{ summary.missiles.count }} 顆</span></td>
                        <td class="text-end" colspan="3">總傷害 {{ fmtNum(summary.missiles.damage) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- 防禦 -->
              <div :class="[cardClass, 'mb-3']">
                <div class="card-body">
                  <h4 class="lo-h"><i class="bi bi-shield-fill me-1"></i>防禦</h4>
                  <div class="lo-tiles">
                    <div class="lo-tile lo-tile--hi"><div class="lo-tile__v">{{ fmtNum(summary.shield.hp) }}</div><div class="lo-tile__l">護盾 HP</div></div>
                    <div class="lo-tile" :title="summary.shield.regenMax && summary.shield.regen < summary.shield.regenMax ? `開滿 ${fmtNum(summary.shield.regenMax)}` : ''">
                      <div class="lo-tile__v">{{ fmtNum(summary.shield.regen) }}</div><div class="lo-tile__l">護盾回充／秒</div></div>
                    <div class="lo-tile"><div class="lo-tile__v">{{ fmtNum(ship.hull?.hp) }}</div><div class="lo-tile__l">船體 HP</div></div>
                  </div>
                  <dl class="lo-dl">
                    <dt>護盾</dt><dd>{{ summary.shield.count }} 個運作<template v-if="summary.shield.spare">（備用 {{ summary.shield.spare }}）</template>
                      <template v-if="faceLabel"> · {{ faceLabel }}</template></dd>
                    <template v-if="summary.shield.absorption?.physical">
                      <dt>護盾吸收</dt><dd>物理 {{ pctRange(summary.shield.absorption.physical) }} · 能量 {{ pctRange(summary.shield.absorption.energy) }}</dd>
                    </template>
                    <dt>裝甲 HP</dt><dd>{{ fmtNum(ship.hull?.armor_hp) }}</dd>
                    <dt>裝甲減傷</dt><dd>{{ reduceText(ship.hull?.armor_damage) }}</dd>
                    <dt>偏轉門檻</dt><dd>{{ dmgText(ship.hull?.deflection) || '—' }}</dd>
                    <dt>穿透倍率</dt><dd>{{ penText(ship.hull?.pen_multiplier) }}</dd>
                    <template v-if="ship.cross_section?.[0]">
                      <dt>截面</dt><dd>{{ ship.cross_section.map(v => fmtNum(v)).join(' / ') }}</dd>
                    </template>
                  </dl>
                </div>
              </div>

              <!-- 量子與飛行 -->
              <div :class="[cardClass, 'mb-3']">
                <div class="card-body">
                  <h4 class="lo-h"><i class="bi bi-stars me-1"></i>量子與飛行</h4>
                  <div v-if="summary.quantum" class="lo-tiles">
                    <div class="lo-tile lo-tile--hi"><div class="lo-tile__v">{{ fmtNum((summary.quantum.speed || 0) / 1000) }}</div><div class="lo-tile__l">量子速度 km/s</div></div>
                    <div class="lo-tile"><div class="lo-tile__v">{{ fmtNum(summary.quantum.range_gm, 1) }}</div><div class="lo-tile__l">量子航程 Gm</div></div>
                    <div class="lo-tile"><div class="lo-tile__v">{{ fmtNum(summary.quantum.spool, 1) }}</div><div class="lo-tile__l">啟動秒數</div></div>
                  </div>
                  <dl class="lo-dl">
                    <template v-if="ship.flight?.scm">
                      <dt>SCM／加力</dt><dd>{{ fmtNum(ship.flight.scm) }} ／ {{ fmtNum(ship.flight.boost_forward) }} m/s</dd>
                      <dt>最高速</dt><dd>{{ fmtNum(ship.flight.max) }} m/s</dd>
                      <dt>俯仰／偏航／翻滾</dt><dd>{{ fmtNum(ship.flight.pitch) }} ／ {{ fmtNum(ship.flight.yaw) }} ／ {{ fmtNum(ship.flight.roll) }} °/s</dd>
                    </template>
                    <template v-if="ship.fuel?.hydrogen"><dt>氫燃料</dt><dd>{{ fmtNum(ship.fuel.hydrogen) }}</dd></template>
                    <template v-if="ship.fuel?.quantum"><dt>量子燃料</dt><dd>{{ fmtNum(ship.fuel.quantum) }}</dd></template>
                    <template v-if="summary.power.gen"><dt>發電</dt><dd>{{ fmtNum(summary.power.gen) }}</dd></template>
                    <template v-if="summary.cooling.gen"><dt>冷卻</dt><dd>{{ fmtNum(summary.cooling.gen) }}</dd></template>
                  </dl>
                </div>
              </div>
            </template>
            <div v-else-if="!shipLoading" :class="[cardClass, 'mb-3']">
              <div class="card-body lo-muted text-center py-4">選一艘船開始配裝</div>
            </div>
          </SfState>
        </div>

        <div class="col-12 col-xl-8">
          <LoadoutPowerCard v-if="ship && ship.power" class="mb-3" :card-class="cardClass" :list="powerList" :pips="pips"
            :summary="powerSum" :mode="powerMode" :item-label="itemLabel" @set="setPips" @mode="m => (powerMode = m)"
            @auto="autoPips(true)" @max="maxPips" />
          <div v-if="ship" class="row g-3">
            <div v-for="sec in sections" :key="sec.key" class="col-12 col-xxl-6">
              <div :class="[cardClass, 'h-100']">
                <div class="card-body">
                  <div class="d-flex align-items-center gap-2">
                    <h4 class="lo-h mb-0"><i :class="sec.icon" class="me-1"></i>{{ sec.label }}</h4>
                    <span v-if="sec.chip" class="sf-chip sf-chip--accent ms-auto">{{ sec.chip }}</span>
                  </div>
                  <LoadoutSlotGroup v-for="(g, i) in sec.groups" :key="`${g[0].id}-${i}`" :nodes="g" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </SfState>

    <SfModal id="lo-picker" v-model:open="pickerOpen" :title="pickerTitle" icon="bi bi-arrow-left-right" width="960px">
      <div class="sf-search sf-search--inline mb-2 d-flex flex-wrap gap-2 align-items-center">
        <input v-model="pickerQuery" type="search" class="form-control form-control-sm lo-q" placeholder="名稱、廠商"
          aria-label="搜尋配件">
        <button v-for="t in pickerTypes" :key="t.key" type="button" class="btn btn-sm"
          :class="pickerType === t.key ? 'btn-primary' : 'btn-secondary'" @click="pickerType = t.key">
          {{ t.label }}<span class="ms-1">{{ t.count }}</span></button>
        <button v-if="pickerNodes[0]?.item" type="button" class="btn btn-sm btn-warning ms-auto" @click="choose(null)">
          <i class="bi bi-eraser me-1"></i>卸下</button>
      </div>
      <SfState :loading="pickerLoading" :empty="!pickerLoading && !pickerRows.length" empty-text="沒有可以裝的配件。">
        <div class="table-responsive">
          <table class="table table-hover table-sm align-middle sf-stack lo-pick">
            <thead>
              <tr>
                <SortTh :sort="pickSort" field="name">名稱</SortTh>
                <SortTh :sort="pickSort" field="size">尺寸</SortTh>
                <SortTh :sort="pickSort" field="mfr" class="d-none d-md-table-cell">廠商</SortTh>
                <SortTh :sort="pickSort" field="grade" class="d-none d-md-table-cell">等級</SortTh>
                <SortTh :sort="pickSort" field="primary" class="text-end">主要數值</SortTh>
                <th class="d-none d-lg-table-cell">其他</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="it in pickSort.sorted.value" :key="it.id" :class="{ 'lo-current': it.id === pickerNodes[0]?.item }">
                <td data-label="名稱">
                  <div class="fw-semibold">{{ itemLabel(it) }}</div>
                  <div class="lo-muted small">{{ typeLabel([`${it.type}.${it.sub_type}`]) }}<template v-if="it.name_zh && it.name_zh !== it.name"> · {{ it.name }}</template></div>
                </td>
                <td data-label="尺寸">S{{ it.size }}</td>
                <td data-label="廠商" class="d-none d-md-table-cell">{{ it.manufacturer || '—' }}</td>
                <td data-label="等級" class="d-none d-md-table-cell">{{ [it.grade, classLabel(it.item_class)].filter(Boolean).join(' ') || '—' }}</td>
                <td data-label="主要數值" class="text-end text-nowrap">
                  <template v-if="primary(it)"><span class="fw-semibold">{{ primary(it).text }}</span>
                    <span class="lo-muted small ms-1">{{ primary(it).label }}</span></template>
                  <template v-else>—</template>
                </td>
                <td data-label="其他" class="d-none d-lg-table-cell small">{{ secondary(it).map(s => `${s.label} ${s.text}`).join(' · ') }}</td>
                <td class="text-end">
                  <button type="button" class="btn btn-sm btn-success text-nowrap" :disabled="it.id === pickerNodes[0]?.item"
                    @click="choose(it)"><i class="bi bi-check-lg me-1"></i>{{ it.id === pickerNodes[0]?.item ? '使用中' : '選用' }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </SfState>
    </SfModal>
  </div>
</template>

<script setup>
import { computed, provide, reactive, ref, shallowReactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AutocompleteField from '@/components/AutocompleteField.vue'
import LoadoutPowerCard from '@/components/LoadoutPowerCard.vue'
import LoadoutSlotGroup from '@/components/LoadoutSlotGroup.vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import SortTh from '@/components/SortTh.vue'
import { useTableSort } from '@/composables/useTableSort'
import { fmtNum } from '@/utils/navFormat'
import {
  SECTIONS, WEAPON_GROUPS, decodeChanges, diff, encodeChanges, equip, findNode, fits, groupNodes, itemMap,
  pathTo, sectionOf, summarize, tagsFor,
} from '@/utils/loadoutCalc'
import {
  autoAllocate, consumers, efficiency, generation, maxAllocate, powerPlantEm, powerSummary,
} from '@/utils/loadoutPower'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card' },
  fleetUuids: { type: Array, default: () => [] },
})

const STORAGE_KEY = 'sc_loadout_v1'
const route = useRoute()
const router = useRouter()

async function getJson(url) {
  const res = await props.fetcher(url)
  const body = res ? await res.json().catch(() => null) : null
  return res?.ok && body?.success ? body.data : null
}

// ── 船清單 ──
const ships = ref([])
const loading = ref(false)
const error = ref('')
const loaded = ref(false)
async function loadShips() {
  loading.value = true
  error.value = ''
  const data = await getJson('/item/loadout/ships')
  loading.value = false
  if (!data) {
    error.value = '讀取失敗。'
    return
  }
  ships.value = data
  loaded.value = true
  const saved = readSaved()
  const id = onLoadoutUrl() && route.query.ship ? String(route.query.ship) : saved.ship
  const lo = onLoadoutUrl() && route.query.ship ? String(route.query.lo || '') : saved.lo
  if (id && ships.value.some(s => s.id === id)) loadShip(id, lo)
}
watch(() => props.active, on => { if (on && !loaded.value && !loading.value) loadShips() }, { immediate: true })
// 網址是不是配裝模擬（工具箱 › 配裝模擬；舊網址 ?tab=loadout 會被玩家頁改寫成新的）
function onLoadoutUrl() {
  const q = route.query
  return q.tab === 'loadout' || (q.tab === 'toolbox' && q.sub === 'loadout')
}

const fleetSet = computed(() => new Set(props.fleetUuids))
const fleetShips = computed(() => ships.value.filter(s => fleetSet.value.has(s.id)).slice(0, 16))
const shipLabel = s => (!s ? '' : s.name_zh && s.name_zh !== s.name ? `${s.name_zh}（${s.name}）` : s.name)
const shipMeta = s => [fleetSet.value.has(s.id) ? '我的機庫' : '', s.manufacturer, s.size ? `S${s.size}` : ''].filter(Boolean).join(' · ')
const shipText = ref('')
async function searchShips(q) {
  const t = (q || '').trim().toLowerCase()
  const rows = ships.value.filter(s => !t || [s.name, s.name_zh, s.manufacturer, s.manufacturer_name, s.role_zh]
    .some(x => (x || '').toLowerCase().includes(t)))
  rows.sort((a, b) => fleetSet.value.has(b.id) - fleetSet.value.has(a.id))
  return rows.slice(0, 40)
}
function pickShip(s) {
  if (!s) return
  shipText.value = ''
  loadShip(s.id, '')
}

// ── 配件快取 ──
const itemCache = shallowReactive(new Map())
const loadedTypes = new Set()
const itemOf = id => (id ? itemCache.get(id) || null : null)
function addItems(list) {
  for (const it of list || []) itemCache.set(it.id, it)
}
async function ensureIds(ids) {
  const need = [...new Set(ids.filter(id => id && !itemCache.has(id)))]
  if (!need.length) return
  addItems(await getJson(`/item/loadout/items?ids=${encodeURIComponent(need.join(','))}`))
}
async function ensureTypes(types) {
  const need = [...new Set(types)].filter(t => t && !loadedTypes.has(t))
  if (!need.length) return
  const data = await getJson(`/item/loadout/items?types=${encodeURIComponent(need.join(','))}`)
  if (data) {
    addItems(data)
    need.forEach(t => loadedTypes.add(t))
  }
}

// ── 目前這艘船 ──
const ship = ref(null)
const slots = ref([])
const defaults = ref({})
const shipLoading = ref(false)
const shipError = ref('')
let lastRequest = { id: '', lo: '' }
async function loadShip(id, lo) {
  lastRequest = { id, lo }
  shipLoading.value = true
  shipError.value = ''
  const data = await getJson(`/item/loadout/ships/${encodeURIComponent(id)}`)
  if (lastRequest.id !== id) return
  shipLoading.value = false
  if (!data) {
    shipError.value = '讀取失敗。'
    return
  }
  addItems(Object.values(data.items || {}))
  const tree = JSON.parse(JSON.stringify(data.slots || []))
  delete data.items
  delete data.slots
  ship.value = data
  defaults.value = itemMap(tree)
  slots.value = tree
  await applyChanges(decodeChanges(lo))
}
const reloadShip = () => lastRequest.id && loadShip(lastRequest.id, lastRequest.lo)

const tagsOf = node => tagsFor(ship.value, pathTo(slots.value, node.id))
async function applyChanges(changes) {
  if (!changes.length) return
  await ensureIds(changes.map(c => c[1]))
  for (const [id, itemId] of changes) {
    const node = findNode(slots.value, id)
    if (!node || !node.editable) continue
    const it = itemOf(itemId)
    if (itemId && (!it || !fits(it, node, tagsOf(node)))) continue
    equip([node], itemId || null, itemOf, tagsOf)
  }
}
function resetLoadout() {
  if (lastRequest.id) loadShip(lastRequest.id, '')
}

const changes = computed(() => (ship.value ? diff(defaults.value, slots.value) : []))
const encoded = computed(() => encodeChanges(changes.value))

// 記在這台瀏覽器＋網址（分享用）
function readSaved() {
  try {
    const v = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    return v && typeof v === 'object' ? v : {}
  } catch {
    return {}
  }
}
watch([() => ship.value?.id, encoded], ([id, lo]) => {
  if (!id) return
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ ship: id, lo })) } catch { /* 存不了就算了 */ }
  if (props.active && onLoadoutUrl() && (route.query.ship !== id || (route.query.lo || '') !== lo)) {
    const query = { ...route.query, ship: id }
    if (lo) query.lo = lo
    else delete query.lo
    router.replace({ query })
  }
})
const copied = ref(false)
async function copyLink() {
  const url = new URL(window.location.href)
  url.search = ''
  url.searchParams.set('tab', 'toolbox')
  url.searchParams.set('sub', 'loadout')
  url.searchParams.set('ship', ship.value.id)
  if (encoded.value) url.searchParams.set('lo', encoded.value)
  try {
    await navigator.clipboard.writeText(url.toString())
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* 瀏覽器不給複製就算了 */ }
}

// ── 顯示 ──
// ── 電源分配（pips）：戰鬥／量子兩種模式各記一份，換配件時沒動到的格數保留、其餘重新自動分配 ──
const powerMode = ref('scm')
const pipsByMode = reactive({ scm: {}, quantum: {} })
const pips = computed(() => pipsByMode[powerMode.value])
const listOf = mode => (ship.value?.power ? consumers(ship.value, slots.value, itemOf, mode) : [])
const powerList = computed(() => listOf(powerMode.value))
const powerGen = computed(() => (ship.value?.power ? generation(ship.value, slots.value, defaults.value, itemOf) : 0))
const ppEm = computed(() => powerPlantEm(slots.value, itemOf))
const powerSum = computed(() => powerSummary(ship.value, powerList.value, pips.value, powerGen.value, ppEm.value))
// 耗電者的組成（哪一格裝什麼）變了才重新分配
const powerSig = computed(() => JSON.stringify([powerGen.value,
  ...listOf('scm').map(c => [c.key, c.item?.id || '', c.max])]))
let lastItems = {}
function autoPips(all = false) {
  // all＝「自動分配」按鈕：目前模式全部重分；否則（換了配件）兩個模式都只重分有變動的
  for (const mode of all ? [powerMode.value] : ['scm', 'quantum']) {
    const list = listOf(mode)
    const keep = {}
    if (!all) {
      for (const c of list) {
        const id = c.item?.id || c.key
        if (c.key in pipsByMode[mode] && lastItems[c.key] === id) keep[c.key] = pipsByMode[mode][c.key]
      }
    }
    pipsByMode[mode] = autoAllocate(list, powerGen.value, keep)
  }
  lastItems = Object.fromEntries(listOf('scm').map(c => [c.key, c.item?.id || c.key]))
}
watch(powerSig, () => autoPips(false))
function setPips(key, p) {
  pipsByMode[powerMode.value] = { ...pipsByMode[powerMode.value], [key]: p }
}
function maxPips() {
  pipsByMode[powerMode.value] = maxAllocate(powerList.value)
}
// 護盾回充依戰鬥模式分到的格數打折
const shieldEff = computed(() => {
  if (!ship.value?.power) return null
  const out = {}
  for (const c of listOf('scm')) {
    if (c.kind === 'shield') out[c.key] = efficiency(c.max, c.item.stats?.power_ranges, pipsByMode.scm[c.key] ?? c.max)
  }
  return out
})

const summary = computed(() => summarize(ship.value, slots.value, itemOf, shieldEff.value))
const GROUP_LABEL = { pilot: '駕駛武器', manned: '有人砲塔', remote: '遙控砲塔', pdc: '點防禦' }
const weaponRows = computed(() => WEAPON_GROUPS.map(k => ({ key: k, label: GROUP_LABEL[k], ...summary.value.weapons[k] }))
  .filter(g => g.count))
const slavedDiff = computed(() => Math.round(summary.value.pilotTotal.dps) !== Math.round(summary.value.weapons.pilot.dps))

const sections = computed(() => {
  const by = new Map()
  for (const root of slots.value) {
    const key = sectionOf(root, itemOf)
    if (!by.has(key)) by.set(key, [])
    by.get(key).push(root)
  }
  const s = summary.value
  const chips = {
    pilot: s.weapons.pilot.count && `持續 ${fmtNum(s.weapons.pilot.sustained)} DPS`,
    manned: s.weapons.manned.count && `持續 ${fmtNum(s.weapons.manned.sustained)} DPS`,
    remote: s.weapons.remote.count && `持續 ${fmtNum(s.weapons.remote.sustained)} DPS`,
    pdc: s.weapons.pdc.count && `持續 ${fmtNum(s.weapons.pdc.sustained)} DPS`,
    missile: s.missiles.count && `${s.missiles.count} 顆 · ${fmtNum(s.missiles.damage)}`,
    shield: s.shield.hp && `${fmtNum(s.shield.hp)} HP`,
    power: s.power.gen && `發電 ${fmtNum(s.power.gen)}`,
    cooler: s.cooling.gen && `冷卻 ${fmtNum(s.cooling.gen)}`,
    quantum: s.quantum?.range_gm && `${fmtNum(s.quantum.range_gm, 1)} Gm`,
  }
  return SECTIONS.filter(sec => by.has(sec.key))
    .map(sec => ({ ...sec, groups: groupNodes(by.get(sec.key), itemOf), chip: chips[sec.key] || '' }))
})

const TYPE_LABEL = {
  WeaponGun: '武器', Turret: '砲塔／雲台', TurretBase: '砲塔', MissileLauncher: '飛彈架', Missile: '飛彈',
  BombLauncher: '炸彈架', Bomb: '炸彈', Shield: '護盾', PowerPlant: '發電機', Cooler: '冷卻器', QuantumDrive: '量子引擎',
  JumpDrive: '跳躍引擎', Radar: '雷達', WeaponDefensive: '反制發射器', WeaponMining: '採礦雷射', SalvageHead: '打撈頭',
  TractorBeam: '牽引光束', MiningModifier: '採礦模組',
}
const SUB_LABEL = { Torpedo: '魚雷', Rocket: '火箭', GunTurret: '雲台', MannedTurret: '有人砲塔', PDCTurret: '點防禦砲塔',
  BallTurret: '球形砲塔', TopTurret: '上方遙控砲塔', BottomTurret: '下方遙控砲塔', NoseMounted: '機鼻砲座',
  CanardTurret: '鴨翼砲塔', MissileTurret: '飛彈砲塔', CountermeasureLauncher: '' }
function typeLabel(types) {
  const out = []
  for (const t of types || []) {
    const [b, s] = String(t).split('.')
    const label = SUB_LABEL[s] || TYPE_LABEL[b] || b
    if (label && !out.includes(label)) out.push(label)
  }
  return out.join('／')
}
const CLASS_LABEL = { Military: '軍用', Civilian: '民用', Industrial: '工業', Stealth: '隱形', Competition: '競賽' }
const classLabel = c => (c ? CLASS_LABEL[c] || c : '')
const itemLabel = it => it.name_zh || it.name
const FACE_LABEL = { Quadrant: '四面護盾', Bubble: '單面護盾', FrontBack: '前後護盾' }
const faceLabel = computed(() => FACE_LABEL[ship.value?.shield_face] || ship.value?.shield_face || '')

const DMG_LABEL = { physical: '物理', energy: '能量', distortion: '扭曲', thermal: '熱能', biochemical: '生化', stun: '暈眩' }
const dmgText = d => Object.entries(d || {}).filter(([, v]) => v).map(([k, v]) => `${DMG_LABEL[k] || k} ${fmtNum(v, 1)}`).join(' · ')
const pct = v => `${fmtNum(v * 100)}%`
const pctRange = r => (!r ? '—' : r[0] === r[1] ? pct(r[1]) : `${pct(r[0])}–${pct(r[1])}`)
function reduceText(m) {
  const parts = ['physical', 'energy', 'distortion'].filter(k => m?.[k] != null && m[k] !== 1)
    .map(k => `${DMG_LABEL[k]} ${m[k] < 1 ? '-' : '+'}${fmtNum(Math.abs(1 - m[k]) * 100)}%`)
  return parts.join(' · ') || '—'
}
const penText = p => [p?.fuse != null && `保險絲 ×${p.fuse}`, p?.components != null && `內部配件 ×${p.components}`]
  .filter(Boolean).join(' · ') || '—'

/** 配件的主要數值（列表右邊大字、更換清單的排序） */
function primary(it) {
  const s = it?.stats || {}
  switch (it?.type) {
    case 'WeaponGun': return { value: s.sustained, text: fmtNum(s.sustained), label: '持續 DPS' }
    case 'Missile': case 'Bomb': return { value: s.damage_total, text: fmtNum(s.damage_total), label: '傷害' }
    case 'Shield': return { value: s.hp, text: fmtNum(s.hp), label: '護盾 HP' }
    case 'PowerPlant': return { value: s.power_gen, text: fmtNum(s.power_gen), label: '發電' }
    case 'Cooler': return { value: s.coolant_gen, text: fmtNum(s.coolant_gen), label: '冷卻' }
    case 'QuantumDrive': return { value: s.speed, text: fmtNum((s.speed || 0) / 1000), label: 'km/s' }
    case 'MissileLauncher': case 'BombLauncher':
      return s.count ? { value: s.count, text: `${s.count}×S${s.missile_size}`, label: '飛彈' } : null
    case 'WeaponDefensive': return s.ammo ? { value: s.ammo, text: fmtNum(s.ammo), label: '發數' } : null
    case 'WeaponMining': return { value: s.mining_power, text: fmtNum(s.mining_power), label: '採礦功率' }
    case 'Radar': return s.sensitivity?.em != null ? { value: s.sensitivity.em, text: pct(s.sensitivity.em), label: 'EM 靈敏度' } : null
    case 'Turret': {
      const n = (it.ports || []).length
      return n ? { value: n, text: `${n} 槽`, label: [...new Set(it.ports.map(p => `S${p.max}`))].join('／') } : null
    }
    default: return null
  }
}
/** 配件的其他數值（列表下方一行、更換清單的「其他」） */
function secondary(it) {
  const s = it?.stats || {}
  const out = []
  const add = (label, v, text) => { if (v != null && v !== '' && !Number.isNaN(v)) out.push({ label, text: text ?? String(v) }) }
  switch (it?.type) {
    case 'WeaponGun':
      add('單發', s.alpha, fmtNum(s.alpha, 1))
      add('爆發', s.dps, fmtNum(s.dps))
      add('射速', s.rpm, `${fmtNum(s.rpm)}/分`)
      add('射程', s.range, `${fmtNum(s.range)} m`)
      add('彈速', s.speed, `${fmtNum(s.speed)} m/s`)
      add('穿透', s.pen_distance, `${fmtNum(s.pen_distance, 2)} m`)
      add('類型', dmgText(s.damage) || null, Object.keys(s.damage || {}).map(k => DMG_LABEL[k] || k).join('／'))
      break
    case 'Missile': case 'Bomb':
      add('追蹤', s.tracking, { Electromagnetic: '電磁', Infrared: '紅外線', CrossSection: '截面' }[s.tracking] || s.tracking)
      add('鎖定', s.lock_time, `${fmtNum(s.lock_time, 1)} 秒`)
      add('速度', s.speed, `${fmtNum(s.speed)} m/s`)
      add('鎖定距離', s.lock_range?.[1], `${fmtNum((s.lock_range?.[1] || 0) / 1000, 1)} km`)
      break
    case 'Shield':
      add('回充', s.regen, `${fmtNum(s.regen)}/秒`)
      add('受擊延遲', s.damaged_delay, `${fmtNum(s.damaged_delay, 1)} 秒`)
      add('物理吸收', s.absorption?.physical, pctRange(s.absorption?.physical))
      break
    case 'QuantumDrive':
      add('啟動', s.spool, `${fmtNum(s.spool, 1)} 秒`)
      add('冷卻', s.cooldown, `${fmtNum(s.cooldown, 1)} 秒`)
      add('每 Gm 油耗', s.fuel_req, fmtNum(s.fuel_req * 1000, 2))
      break
    case 'Radar':
      add('IR', s.sensitivity?.ir, pct(s.sensitivity?.ir || 0))
      add('CS', s.sensitivity?.cs, pct(s.sensitivity?.cs || 0))
      break
    case 'Turret':
      add('偏航', s.yaw, `${fmtNum(s.yaw)}°/s`)
      add('俯仰', s.pitch, `${fmtNum(s.pitch)}°/s`)
      break
    case 'WeaponMining':
      add('最佳距離', s.optimal_range, `${fmtNum(s.optimal_range)} m`)
      add('模組槽', s.module_slots)
      break
    case 'WeaponDefensive':
      add('類型', s.cm_type, { Flare: '熱焰彈', Chaff: '干擾絲', Noise: '噪訊', Decoy: '誘餌' }[s.cm_type] || s.cm_type)
      break
  }
  if (s.power_use?.[1]) add('耗電', s.power_use[1], fmtNum(s.power_use[1], 1))
  if (s.em) add('EM', s.em, fmtNum(s.em))
  if (s.ir) add('IR 訊號', s.ir, fmtNum(s.ir))
  return out
}

// ── 更換視窗 ──
const pickerOpen = ref(false)
const pickerNodes = ref([])
const pickerQuery = ref('')
const pickerType = ref('')
const pickerLoading = ref(false)
async function openPicker(nodes) {
  pickerNodes.value = nodes
  pickerQuery.value = ''
  pickerType.value = ''
  pickerOpen.value = true
  pickerLoading.value = true
  await ensureTypes((nodes[0].types || []).map(t => String(t).split('.')[0]))
  pickerLoading.value = false
}
const pickerTitle = computed(() => {
  const n = pickerNodes.value[0]
  if (!n) return '更換配件'
  const size = n.min === n.max ? `S${n.min}` : `S${n.min}–S${n.max}`
  return `更換${typeLabel(n.types)}（${size}${pickerNodes.value.length > 1 ? `，${pickerNodes.value.length} 格一起換` : ''}）`
})
const pickerAll = computed(() => {
  const node = pickerNodes.value[0]
  if (!node || !pickerOpen.value) return []
  const tags = tagsOf(node)
  return [...itemCache.values()].filter(it => fits(it, node, tags))
})
const pickerTypes = computed(() => {
  const counts = new Map()
  for (const it of pickerAll.value) counts.set(it.type, (counts.get(it.type) || 0) + 1)
  if (counts.size < 2) return []
  return [{ key: '', label: '全部', count: pickerAll.value.length },
    ...[...counts].map(([k, c]) => ({ key: k, label: TYPE_LABEL[k] || k, count: c }))]
})
const pickerRows = computed(() => {
  const q = pickerQuery.value.trim().toLowerCase()
  return pickerAll.value.filter(it => (!pickerType.value || it.type === pickerType.value)
    && (!q || [it.name, it.name_zh, it.manufacturer, it.manufacturer_name, it.class_name].some(x => (x || '').toLowerCase().includes(q))))
})
const pickSort = useTableSort(pickerRows, {
  key: 'primary', dir: 'desc',
  accessors: { name: it => itemLabel(it), size: it => it.size, mfr: it => it.manufacturer, grade: it => it.grade,
    primary: it => primary(it)?.value ?? null },
})
async function choose(it) {
  if (it) await ensureIds([it.id, ...(it.ports || []).map(p => p.default)])
  equip(pickerNodes.value, it?.id || null, itemOf, tagsOf)
  pickerOpen.value = false
}

provide('loadout', { itemOf, open: openPicker, primary, secondary, itemLabel, typeLabel, classLabel })
</script>

<style scoped>
.lo-title { font-size: 1.5rem; font-weight: 700; margin: 0; color: var(--sf-text-strong); }
.lo-mfr { color: var(--sf-text-muted); }
.lo-muted { color: var(--sf-text-muted); }
.lo-h { font-size: 1.05rem; font-weight: 700; margin-bottom: .6rem; color: var(--sf-text-strong); }
.lo-tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; margin-bottom: .6rem; }
.lo-tile { padding: .5rem .6rem; border: 1px solid var(--sf-border); border-radius: .4rem; background: var(--sf-chip-bg); }
.lo-tile--hi { border-color: rgba(var(--sf-accent-rgb), .8); background: rgba(var(--sf-accent-rgb), .15); }
.lo-tile__v { font-size: 1.35rem; font-weight: 700; color: var(--sf-text-strong); line-height: 1.1; }
.lo-tile--hi .lo-tile__v { color: var(--sf-accent); }
.lo-tile__l { font-size: .8rem; color: var(--sf-text-muted); }
.lo-table { --bs-table-bg: transparent; }
.lo-table th { font-size: .8rem; color: var(--sf-text-muted); font-weight: 600; }
.lo-dl { display: grid; grid-template-columns: auto 1fr; gap: .25rem .8rem; margin: 0; }
.lo-dl dt { font-weight: 500; color: var(--sf-text-muted); }
.lo-dl dd { margin: 0; text-align: right; color: var(--sf-text-strong); }
.lo-q { max-width: 16rem; }
.lo-current td { background: rgba(var(--sf-accent-rgb), .12) !important; }
@media (max-width: 575.98px) {
  .lo-tile__v { font-size: 1.1rem; }
}
</style>
