<!--
  玩家頁「配裝模擬」：選一艘船，依掛點分區列出每一格的配件，點「更換」從可裝的配件裡挑（種類、尺寸、
  專屬標籤都對得上才列），左邊即時算出傷害（駕駛／有人砲塔／遙控砲塔／點防禦）、飛彈、護盾、量子航程，
  以及不隨配件變動的船體、裝甲、偏轉與穿透倍率。
  資料：GET /item/loadout/ships、/item/loadout/ships/<id>、/item/loadout/items（src/models/loadout.py，
  scunpacked-data；後台「配裝」同步項目）。計算在 utils/loadoutCalc.js。
  換過的格子記在網址 ?ship=&lo=（可複製連結分享）與這台瀏覽器。
  版面：選船＋動作是側欄（寬螢幕在右邊、其餘在上方）；主欄是船名、傷害／防禦、電源、量子與飛行、各區配件。
  會員可以「只看我的機庫」，也可以把這份配裝的連結存到艦隊那艘船的配件網址（PUT /player/fleet/<id>）。
-->
<template>
  <div>
    <SfState :loading="loading" :error="error" :empty="loaded && !ships.length"
      empty-text="尚無配裝資料，請管理員在後台同步「配裝」。" @retry="loadShips">
      <div class="lo-layout">
        <!-- 側欄：選船（跟資料庫一樣：寬螢幕在右邊、其餘在上方）＋動作 -->
        <aside class="lo-side">
          <div :class="[cardClass, 'sf-search', 'lo-card']">
            <div class="card-body">
              <label class="form-label small fw-semibold mb-1" for="lo-ship">船艦</label>
              <AutocompleteField id="lo-ship" v-model="shipText" :search="searchShips" :get-label="shipLabel"
                :get-meta="shipMeta" :min-chars="0" :debounce-ms="0" aria-label="選擇船艦" @select="pickShip" />
              <div v-if="member" class="form-check form-switch mt-2 mb-0">
                <input id="lo-mine" v-model="mineOnly" class="form-check-input" type="checkbox" role="switch" :disabled="!fleetSet.size">
                <label class="form-check-label" for="lo-mine">只看我的機庫<span class="lo-muted ms-1">{{ fleetSet.size }}</span></label>
              </div>
              <!-- 跟資料庫 › 艦船一樣的條件（類型、尺寸、廠商、角色），選了之後上面的候選只列符合的船 -->
              <div class="row g-2 mt-1">
                <div class="col-6">
                  <label class="form-label small mb-1" for="lo-f-type">類型</label>
                  <MultiSelectFilter id="lo-f-type" v-model="shipF.types" :options="shipFacet.types" label="類型" placeholder="全部" block />
                </div>
                <div class="col-6">
                  <label class="form-label small mb-1" for="lo-f-size">尺寸</label>
                  <MultiSelectFilter id="lo-f-size" v-model="shipF.sizes" :options="shipFacet.sizes" label="尺寸" placeholder="全部" block />
                </div>
                <div class="col-6">
                  <label class="form-label small mb-1" for="lo-f-mfr">廠商</label>
                  <MultiSelectFilter id="lo-f-mfr" v-model="shipF.mfrs" :options="shipFacet.mfrs" label="廠商" placeholder="全部" block searchable />
                </div>
                <div class="col-6">
                  <label class="form-label small mb-1" for="lo-f-role">角色</label>
                  <MultiSelectFilter id="lo-f-role" v-model="shipF.roles" :options="shipFacet.roles" label="角色" placeholder="全部" block searchable />
                </div>
              </div>
              <div v-if="shipFiltering" class="d-flex align-items-center gap-2 mt-2">
                <span class="sf-chip">符合 {{ filteredShips.length }} 艘</span>
                <button type="button" class="btn btn-sm btn-secondary ms-auto" @click="clearShipFilters">
                  <i class="bi bi-x-lg me-1"></i>清除條件</button>
              </div>
            </div>
          </div>

          <!-- 動作 -->
          <div v-if="ship" :class="[cardClass, 'lo-card']">
            <div class="card-body">
              <div class="d-flex align-items-center mb-2">
                <h4 class="lo-h mb-0">動作</h4>
                <span class="sf-chip ms-auto" :class="{ 'sf-chip--accent': changes.length }">已更換 {{ changes.length }} 格</span>
              </div>
              <div class="lo-actions">
                <button type="button" class="btn btn-sm btn-info" @click="copyLink"><i class="bi bi-share me-1"></i>複製連結</button>
                <button type="button" class="btn btn-sm btn-warning" :disabled="!changes.length" @click="resetLoadout">
                  <i class="bi bi-arrow-counterclockwise me-1"></i>重設配裝</button>
                <button v-if="member" type="button" class="btn btn-sm btn-success lo-actions__wide" :disabled="!fleetRow || savingLink"
                  :title="fleetRow ? '' : '這艘船不在你的機庫'" @click="saveToFleet">
                  <span v-if="savingLink" class="spinner-border spinner-border-sm me-1"></span>
                  <i v-else class="bi bi-bookmark-plus me-1"></i>存到我的機庫</button>
                <button type="button" class="btn btn-sm btn-secondary lo-actions__wide" @click="foldAllSections">
                  <i class="bi me-1" :class="allFolded ? 'bi-arrows-expand' : 'bi-arrows-collapse'"></i>{{ allFolded ? '展開全部配件' : '收起全部配件' }}</button>
              </div>
              <div v-if="member && fleetRow && fleetRow.quantity > 1" class="mt-2">
                <label class="form-label small mb-1" for="lo-unit">存到哪一艘</label>
                <select id="lo-unit" v-model.number="saveUnit" class="form-select form-select-sm">
                  <option v-for="n in fleetRow.quantity" :key="n" :value="n">{{ fleetRow.unit_names?.[n - 1] || `第 ${n} 艘` }}</option>
                </select>
              </div>
            </div>
          </div>

          <!-- 購物車：可購買的配件算總價（UEX 最低購買價）；買不到的標出來（可製作的看藍圖） -->
          <div :class="[cardClass, 'lo-card']">
            <div class="card-body">
              <div class="d-flex align-items-center mb-2">
                <h4 class="lo-h mb-0"><i class="bi bi-cart3 me-2"></i>購物車</h4>
                <span v-if="cartCount" class="sf-chip ms-2">{{ cartCount }} 件</span>
                <button v-if="cartRows.length" type="button" class="btn btn-sm btn-warning ms-auto" @click="clearCart">
                  <i class="bi bi-trash me-1"></i>清空</button>
              </div>
              <button v-if="ship" type="button" class="btn btn-sm btn-primary w-100 mb-2" :disabled="!changes.length" @click="addChangesToCart">
                <i class="bi bi-cart-plus me-1"></i>換過的配件全部加入</button>
              <div v-if="!cartRows.length" class="lo-muted small">空的</div>
              <div v-for="r in cartRows" :key="r.id" class="lo-cart">
                <button type="button" class="lo-cart__name" :disabled="!r.it" @click="openInfo(r.it, r.it?.buyable ? 'buy' : 'bp')">
                  {{ r.it ? itemLabel(r.it) : '載入中…' }}</button>
                <div class="lo-cart__line">
                  <span class="lo-cart__meta">
                    <template v-if="r.price != null">{{ fmtAuec(r.price) }}</template>
                    <template v-else-if="r.it?.blueprint"><i class="bi bi-hammer me-1"></i>買不到 · 可製作</template>
                    <template v-else-if="r.it">買不到</template>
                  </span>
                  <span class="lo-cart__qty">
                    <button type="button" class="btn btn-sm btn-secondary" :aria-label="`減少 ${r.it ? itemLabel(r.it) : ''}`" @click="setCartQty(r.id, r.qty - 1)">
                      <i class="bi bi-dash"></i></button>
                    <span>{{ r.qty }}</span>
                    <button type="button" class="btn btn-sm btn-secondary" :aria-label="`增加 ${r.it ? itemLabel(r.it) : ''}`" @click="setCartQty(r.id, r.qty + 1)">
                      <i class="bi bi-plus"></i></button>
                  </span>
                  <span class="lo-cart__sub">{{ r.sub != null ? fmtAuec(r.sub) : '—' }}</span>
                </div>
              </div>
              <div v-if="cartRows.length" class="lo-cart__total">
                <span>合計<span v-if="cartMissing" class="lo-muted ms-1">（{{ cartMissing }} 種買不到，不算）</span></span>
                <b>{{ fmtAuec(cartTotal) }}</b>
              </div>
            </div>
          </div>
        </aside>

        <div class="lo-main">
          <SfState :loading="shipLoading" :error="shipError" @retry="reloadShip">
            <template v-if="ship">
              <!-- 船名 -->
              <div :class="[cardClass, 'lo-card']">
                <div class="card-body lo-hero">
                  <div class="lo-mfr">{{ ship.manufacturer_name || ship.manufacturer }}</div>
                  <h3 class="lo-title">{{ ship.name_zh || ship.name }}</h3>
                  <div v-if="ship.name_zh && ship.name_zh !== ship.name" class="lo-en">{{ ship.name }}</div>
                  <div class="lo-badges">
                    <span v-if="ship.size" class="lo-badge lo-badge--hi">S{{ ship.size }}</span>
                    <span v-if="careerLabel" class="lo-badge">{{ careerLabel }}</span>
                    <span v-if="ship.role_zh || ship.role" class="lo-badge">{{ ship.role_zh || ship.role }}</span>
                    <span v-if="ship.crew" class="lo-badge"><i class="bi bi-people me-1"></i>{{ ship.crew }} 人</span>
                    <span v-if="ship.cargo" class="lo-badge lo-badge--ok"><i class="bi bi-box-seam me-1"></i>{{ fmtNum(ship.cargo) }} SCU</span>
                    <span v-if="fleetRow" class="lo-badge lo-badge--ok"><i class="bi bi-rocket-takeoff me-1"></i>我的機庫</span>
                  </div>
                </div>
              </div>

              <div class="lo-grid">
                <!-- 傷害 -->
                <div :class="[cardClass, 'lo-card']">
                  <div class="card-body">
                    <h4 class="lo-h"><i class="bi bi-crosshair me-2"></i>傷害</h4>
                    <div class="lo-big">
                      <div class="lo-bt"><div class="lo-bt__v">{{ fmtNum(summary.total.alpha) }}</div><div class="lo-bt__l">單發總傷害</div></div>
                      <div class="lo-bt lo-bt--hi"><div class="lo-bt__v">{{ fmtNum(summary.total.sustained) }}</div><div class="lo-bt__l">持續 DPS</div></div>
                      <div class="lo-bt"><div class="lo-bt__v">{{ fmtNum(summary.total.dps) }}</div><div class="lo-bt__l">爆發 DPS</div></div>
                    </div>
                    <table class="table lo-table mb-0">
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
                      </tbody>
                    </table>
                    <div v-if="summary.missiles.count" class="lo-big lo-big--2 mt-3">
                      <div class="lo-bt"><div class="lo-bt__v">{{ fmtNum(summary.missiles.damage) }}</div><div class="lo-bt__l">飛彈總傷害</div></div>
                      <div class="lo-bt"><div class="lo-bt__v">{{ summary.missiles.count }}</div><div class="lo-bt__l">飛彈與魚雷（顆）</div></div>
                    </div>
                  </div>
                </div>

                <!-- 防禦 -->
                <div :class="[cardClass, 'lo-card']">
                  <div class="card-body">
                    <h4 class="lo-h"><i class="bi bi-shield-fill me-2"></i>防禦</h4>
                    <div class="lo-big lo-big--2">
                      <div class="lo-bt"><div class="lo-bt__v">{{ fmtNum(summary.shield.hp) }}</div><div class="lo-bt__l">護盾 HP</div></div>
                      <div class="lo-bt lo-bt--hi">
                        <div class="d-flex align-items-baseline gap-2">
                          <div class="lo-bt__v">{{ fmtNum(summary.shield.regen) }}</div>
                          <div v-if="regenPct != null" class="lo-bt__pct ms-auto">{{ fmtNum(regenPct * 100) }}%</div>
                        </div>
                        <div class="lo-bt__l">回充／秒</div>
                        <div v-if="regenPct != null" class="lo-bt__bar"><span :style="{ width: `${Math.min(100, regenPct * 100)}%` }"></span></div>
                      </div>
                    </div>
                    <div class="lo-rows">
                      <div class="lo-r"><span class="lo-r__k">護盾</span>
                        <span class="lo-r__v">{{ summary.shield.count }} 個運作<template v-if="summary.shield.spare">（備用 {{ summary.shield.spare }}）</template><template v-if="faceLabel"> · {{ faceLabel }}</template></span></div>
                      <div v-if="chipsOf(summary.shield.resistance, true).length" class="lo-r"><span class="lo-r__k">護盾抗性</span>
                        <span class="lo-chips"><span v-for="c in chipsOf(summary.shield.resistance, true)" :key="c.k" class="lo-chip">{{ c.label }} <b :class="`lo-c--${c.k}`">{{ c.text }}</b></span></span></div>
                      <div v-if="chipsOf(summary.shield.absorption, true).length" class="lo-r"><span class="lo-r__k">護盾吸收</span>
                        <span class="lo-chips"><span v-for="c in chipsOf(summary.shield.absorption, true)" :key="c.k" class="lo-chip">{{ c.label }} <b :class="`lo-c--${c.k}`">{{ c.text }}</b></span></span></div>
                      <div class="lo-r lo-r--big"><span class="lo-r__k">船體 HP</span><span class="lo-r__v">{{ fmtNum(ship.hull?.hp) }}</span></div>
                      <div class="lo-r lo-r--big"><span class="lo-r__k">裝甲 HP</span><span class="lo-r__v">{{ fmtNum(ship.hull?.armor_hp) }}</span></div>
                      <div v-if="dmgChips(ship.hull?.deflection).length" class="lo-r"><span class="lo-r__k">偏轉門檻</span>
                        <span class="lo-chips"><span v-for="c in dmgChips(ship.hull?.deflection)" :key="c.k" class="lo-chip">{{ c.label }} <b :class="`lo-c--${c.k}`">{{ c.text }}</b></span></span></div>
                      <div v-if="multChips(ship.hull?.armor_damage).length" class="lo-r"><span class="lo-r__k">裝甲減傷</span>
                        <span class="lo-chips"><span v-for="c in multChips(ship.hull?.armor_damage)" :key="c.k" class="lo-chip">{{ c.label }} <b :class="`lo-c--${c.k}`">{{ c.text }}</b></span></span></div>
                      <div class="lo-r"><span class="lo-r__k">穿透倍率</span><span class="lo-r__v lo-r__v--sm">{{ penText(ship.hull?.pen_multiplier) }}</span></div>
                      <div v-if="ship.cross_section?.[0]" class="lo-r"><span class="lo-r__k">截面</span>
                        <span class="lo-r__v lo-r__v--sm">{{ ship.cross_section.map(v => fmtNum(v)).join(' / ') }}</span></div>
                    </div>
                  </div>
                </div>
              </div>

              <LoadoutPowerCard v-if="ship && ship.power" class="lo-card" :card-class="cardClass" :list="powerList" :pips="pips"
            :summary="powerSum" :mode="powerMode" :item-label="itemLabel" @set="setPips" @mode="m => (powerMode = m)"
            @auto="autoPips(true)" @max="maxPips" />

              <!-- 量子與飛行 -->
              <div :class="[cardClass, 'lo-card']">
                <div class="card-body">
                  <h4 class="lo-h"><i class="bi bi-stars me-2"></i>量子與飛行</h4>
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

              <div class="row g-3">
            <!-- 武器區（雲台＋武器排左右兩欄）佔整列，其他區塊寬螢幕兩欄 -->
            <div v-for="sec in sections" :key="sec.key" class="col-12" :class="{ 'col-xxl-6': !WEAPON_GROUPS.includes(sec.key) }">
              <div :class="[cardClass, 'h-100']">
                <div class="card-body lo-sec">
                  <!-- 區塊標題可以整區收起（再點展開） -->
                  <button type="button" class="lo-sec__head" :aria-expanded="folded.has(sec.key) ? 'false' : 'true'"
                    @click="toggleSec(sec.key)">
                    <i class="bi lo-sec__chev" :class="folded.has(sec.key) ? 'bi-chevron-right' : 'bi-chevron-down'" aria-hidden="true"></i>
                    <span class="lo-h mb-0"><i :class="sec.icon" class="me-1"></i>{{ sec.label }}</span>
                    <span v-if="sec.chip" class="sf-chip sf-chip--accent ms-auto">{{ sec.chip }}</span>
                  </button>
                  <template v-if="!folded.has(sec.key)">
                    <LoadoutSlotGroup v-for="(g, i) in sec.groups" :key="`${g[0].id}-${i}`" :nodes="g" />
                  </template>
                </div>
              </div>
            </div>
              </div>
            </template>
            <div v-else-if="!shipLoading" :class="[cardClass, 'lo-card']">
              <div class="card-body lo-muted text-center py-4">選一艘船開始配裝</div>
            </div>
          </SfState>
        </div>
      </div>
    </SfState>

    <LoadoutItemModal v-model:open="infoOpen" :item="infoItem" :initial-tab="infoTab" :fetcher="fetcher"
      @missions="bp => missionsRef?.open(bp)" />
    <BlueprintMissionsModal ref="missionsRef" :fetcher="fetcher" />
    <LoadoutPicker v-model:open="pickerOpen" :title="pickerTitle" :items="pickerAll" :loading="pickerLoading"
      :current-id="pickerNodes[0]?.item || ''" :slot-text="pickerSlotText" @choose="choose" />
  </div>
</template>

<script setup>
import { computed, provide, reactive, ref, shallowReactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AutocompleteField from '@/components/AutocompleteField.vue'
import LoadoutPowerCard from '@/components/LoadoutPowerCard.vue'
import LoadoutSlotGroup from '@/components/LoadoutSlotGroup.vue'
import SfState from '@/components/SfState.vue'
import LoadoutPicker from '@/components/LoadoutPicker.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import LoadoutItemModal from '@/components/LoadoutItemModal.vue'
import BlueprintMissionsModal from '@/components/BlueprintMissionsModal.vue'
import { LOCKED_QUALITY, applyQuality, avgQuality, decodeQualities, encodeQualities, isDefault as isDefaultQuality, qualitiesOf } from '@/utils/loadoutCraft'
import { clampQuality } from '@/utils/craftQuality'
import { fmtAuec } from '@/utils/uexCommodity'
import { manufacturerLabel, vehicleRoleLabel, vehicleSizeLabel } from '@/utils/vehicle'
import { fmtNum } from '@/utils/navFormat'
import { DMG_LABEL, TRACK_LABEL, classLabel, loadLoadoutZh, typeLabel } from '@/utils/loadoutLabels'
import {
  SECTIONS, WEAPON_GROUPS, decodeChanges, diff, encodeChanges, equip, findNode, fits, groupNodes, itemMap,
  pathTo, sectionOf, summarize, tagsFor, walk,
} from '@/utils/loadoutCalc'
import { copyText } from '@/utils/clipboard'
import { toast } from '@/utils/toast'
import {
  autoAllocate, consumerLoad, consumers, generation, maxAllocate, powerPlantEm, setWithinGen, powerSummary, shieldShares,
} from '@/utils/loadoutPower'

const props = defineProps({
  fetcher: { type: Function, required: true },
  active: { type: Boolean, default: false },
  cardClass: { type: String, default: 'card' },
  fleetUuids: { type: Array, default: () => [] },
  /** 我的艦隊（GET /player/fleet 的列）：「存到我的機庫」用 */
  fleet: { type: Array, default: () => [] },
  /** 有登入（「只看我的機庫」「存到我的機庫」只有會員能用） */
  member: { type: Boolean, default: false },
})
const emit = defineEmits(['fleet-changed'])

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
  const fromUrl = onLoadoutUrl() && route.query.ship
  const id = fromUrl ? String(route.query.ship) : saved.ship
  const lo = fromUrl ? String(route.query.lo || '') : saved.lo
  const lq = fromUrl ? String(route.query.lq || '') : saved.lq
  if (id && ships.value.some(s => s.id === id)) loadShip(id, lo, lq)
}
watch(() => props.active, on => { if (on && !loaded.value && !loading.value) loadShips() }, { immediate: true })
// 網址是不是配裝模擬（工具箱 › 配裝模擬；舊網址 ?tab=loadout 會被玩家頁改寫成新的）
function onLoadoutUrl() {
  const q = route.query
  return q.tab === 'loadout' || (q.tab === 'toolbox' && q.sub === 'loadout')
}

const fleetSet = computed(() => new Set(props.fleetUuids))
// 只看我的機庫（登入才有；開關）
const mineOnly = ref(false)
const shipLabel = s => (!s ? '' : s.name_zh && s.name_zh !== s.name ? `${s.name_zh}（${s.name}）` : s.name)
const shipMeta = s => [fleetSet.value.has(s.id) ? '我的機庫' : '', s.manufacturer, s.size ? `S${s.size}` : ''].filter(Boolean).join(' · ')
const shipText = ref('')
// 選船的篩選條件（跟資料庫 › 艦船一樣：類型、尺寸、廠商、角色；同一欄多選取聯集，欄位之間 AND）
const shipF = reactive({ types: [], sizes: [], mfrs: [], roles: [] })
const shipTypeOf = s => (s.is_spaceship === false ? 'ground' : 'space')
const SHIP_TYPE_LABEL = { space: '太空船', ground: '地面載具' }
const shipFacet = computed(() => {
  const types = new Set(); const sizes = new Set(); const mfrs = new Map(); const roles = new Map()
  for (const s of ships.value) {
    types.add(shipTypeOf(s))
    if (s.size != null) sizes.add(s.size)
    if (s.manufacturer && !mfrs.has(s.manufacturer)) mfrs.set(s.manufacturer, manufacturerLabel(s.manufacturer_name, s.manufacturer))
    if (s.role && !roles.has(s.role)) roles.set(s.role, vehicleRoleLabel(s.role, s.role_zh))
  }
  const byLabel = (a, b) => a.label.localeCompare(b.label, 'zh-Hant')
  return {
    types: [...types].map(v => ({ value: v, label: SHIP_TYPE_LABEL[v] })),
    sizes: [...sizes].sort((a, b) => a - b).map(n => ({ value: String(n), label: vehicleSizeLabel(n) })),
    mfrs: [...mfrs].map(([value, label]) => ({ value, label })).sort(byLabel),
    roles: [...roles].map(([value, label]) => ({ value, label })).sort(byLabel),
  }
})
const shipFiltering = computed(() => mineOnly.value || Object.values(shipF).some(v => v.length))
const filteredShips = computed(() => ships.value.filter(s =>
  (!mineOnly.value || fleetSet.value.has(s.id))
  && (!shipF.types.length || shipF.types.includes(shipTypeOf(s)))
  && (!shipF.sizes.length || shipF.sizes.includes(String(s.size)))
  && (!shipF.mfrs.length || shipF.mfrs.includes(s.manufacturer))
  && (!shipF.roles.length || shipF.roles.includes(s.role))))
function clearShipFilters() {
  mineOnly.value = false
  for (const k of Object.keys(shipF)) shipF[k] = []
}
async function searchShips(q) {
  const t = (q || '').trim().toLowerCase()
  const rows = filteredShips.value.filter(s => !t || [s.name, s.name_zh, s.manufacturer, s.manufacturer_name, s.role_zh]
    .some(x => (x || '').toLowerCase().includes(t)))
  rows.sort((a, b) => fleetSet.value.has(b.id) - fleetSet.value.has(a.id))
  return rows.slice(0, 80)
}
function pickShip(s) {
  if (!s) return
  shipText.value = ''
  loadShip(s.id, '', '')
}

// ── 配件快取 ──
const itemCache = shallowReactive(new Map())
const loadedTypes = new Set()
// 調過品質的配件用套上品質的複本（utils/loadoutCraft.js）；其餘是原本的資料（Q500）
const baseOf = id => (id ? itemCache.get(id) || null : null)
const itemOf = id => (id ? crafted.value.get(id) || itemCache.get(id) || null : null)
function addItems(list) {
  loadLoadoutZh(list || [])
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

// ── 製作品質：{配件 id: {部位: 品質}}，只有可製作的配件（有 blueprint）能調 ──
const qualities = reactive({})
// 單格武器關電（槽位 id）：不耗電、不算傷害；換船時清掉
const weaponOff = reactive(new Set())
const qCache = shallowReactive(new Map())       // 藍圖 uuid → 品質資料的部位（slots）
const qPending = new Map()
function qualityData(uuid) {
  if (!uuid) return Promise.resolve(null)
  if (qCache.has(uuid)) return Promise.resolve(qCache.get(uuid))
  if (!qPending.has(uuid)) {
    qPending.set(uuid, getJson(`/blueprint/master/${encodeURIComponent(uuid)}/quality`).then((d) => {
      qPending.delete(uuid)
      if (d?.slots) qCache.set(uuid, d.slots)
      return d?.slots || null
    }))
  }
  return qPending.get(uuid)
}
const qualityOf = id => (id && qualities[id]) || null
function setQuality(id, q) {
  if (isDefaultQuality(q)) delete qualities[id]
  else qualities[id] = q
}
const crafted = computed(() => {
  const out = new Map()
  for (const [id, q] of Object.entries(qualities)) {
    const it = itemCache.get(id)
    const slotsQ = it?.blueprint ? qCache.get(it.blueprint) : null
    if (slotsQ && !isDefaultQuality(q)) out.set(id, applyQuality(it, slotsQ, q).item)
  }
  return out
})
/** 列表上顯示的品質：可製作＝平均品質（還沒載品質資料就看設定的值）；不可製作＝Q500 */
function avgOf(it) {
  if (!it?.blueprint) return LOCKED_QUALITY
  const slotsQ = qCache.get(it.blueprint)
  if (slotsQ) return avgQuality(slotsQ, qualities[it.id])
  const vals = Object.values(qualities[it.id] || {})
  return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : LOCKED_QUALITY
}
/** 槽位左側品質把手：每個部位各加減 delta（夾在 Q0～Q1000）；還沒載品質資料就先載 */
async function nudgeQuality(it, delta) {
  if (!it?.blueprint) return
  const slotsQ = await qualityData(it.blueprint)
  if (!slotsQ) { toast('讀取品質資料失敗。', 'danger'); return }
  const cur = qualitiesOf(slotsQ, qualities[it.id])
  setQuality(it.id, Object.fromEntries(Object.entries(cur).map(([k, v]) => [k, clampQuality(v + delta)])))
}
async function applyQualities(map) {
  for (const k of Object.keys(qualities)) delete qualities[k]
  for (const [id, q] of Object.entries(map || {})) {
    const it = itemCache.get(id)
    if (!it?.blueprint) continue
    qualities[id] = q
    qualityData(it.blueprint)
  }
}
const encodedQ = computed(() => encodeQualities(qualities))

// ── 配件詳細（購買地點／藍圖／品質）跳出視窗 ──
const infoOpen = ref(false)
const infoItem = ref(null)
const infoTab = ref('buy')
function openInfo(it, tab = 'buy') {
  if (!it) return
  infoItem.value = baseOf(it.id) || it
  infoTab.value = tab
  infoOpen.value = true
}
const missionsRef = ref(null)

// ── 購物車：{配件 id: 數量}，記在這台瀏覽器 ──
const CART_KEY = 'sc_loadout_cart_v1'
const cart = reactive((() => {
  try {
    const v = JSON.parse(localStorage.getItem(CART_KEY) || '{}')
    return v && typeof v === 'object' && !Array.isArray(v) ? v : {}
  } catch {
    return {}
  }
})())
watch(cart, (v) => { try { localStorage.setItem(CART_KEY, JSON.stringify(v)) } catch { /* 存不了就算了 */ } }, { deep: true })
function addCart(it, n = 1) {
  if (!it?.id) return
  cart[it.id] = Math.min(99, (cart[it.id] || 0) + n)
  toast(`已加入購物車：${itemLabel(it)}${n > 1 ? ` × ${n}` : ''}`)
}
function setCartQty(id, n) {
  const v = Math.max(0, Math.min(99, Math.round(Number(n) || 0)))
  if (v) cart[id] = v
  else delete cart[id]
}
function clearCart() {
  for (const k of Object.keys(cart)) delete cart[k]
}
// 購物車的配件資料：不在快取裡的（例如換了船）補載
watch(() => Object.keys(cart).join(','), (ids) => { if (ids) ensureIds(ids.split(',')) }, { immediate: true })
const cartRows = computed(() => Object.entries(cart).map(([id, qty]) => {
  const it = baseOf(id)
  return { id, qty, it, price: it?.price ?? null, sub: it?.price != null ? it.price * qty : null }
}))
const cartTotal = computed(() => cartRows.value.reduce((a, r) => a + (r.sub || 0), 0))
const cartMissing = computed(() => cartRows.value.filter(r => r.it && r.price == null).length)
const cartCount = computed(() => cartRows.value.reduce((a, r) => a + r.qty, 0))
/** 把換過的配件（跟預設不一樣的）全部加進購物車：同一個配件換了幾格就幾個 */
function addChangesToCart() {
  const counts = {}
  for (const [, itemId] of changes.value) if (itemId) counts[itemId] = (counts[itemId] || 0) + 1
  const ids = Object.keys(counts)
  if (!ids.length) { toast('沒有換過的配件', 'info'); return }
  for (const id of ids) cart[id] = Math.min(99, (cart[id] || 0) + counts[id])
  toast(`已加入 ${ids.length} 種配件`)
}

// ── 目前這艘船 ──
const ship = ref(null)
const slots = ref([])
const defaults = ref({})
const shipLoading = ref(false)
const shipError = ref('')
let lastRequest = { id: '', lo: '', lq: '' }
async function loadShip(id, lo, lq = '') {
  lastRequest = { id, lo, lq }
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
  weaponOff.clear()
  // 掛點可裝類型的中文（「更換武器」「砲塔／雲台」）
  const nodeTypes = []
  walk(tree, n => { nodeTypes.push(...(n.types || [])) })
  loadLoadoutZh([], nodeTypes)
  defaults.value = itemMap(tree)
  slots.value = tree
  await applyChanges(decodeChanges(lo))
  const qmap = decodeQualities(lq)
  await ensureIds(Object.keys(qmap))
  await applyQualities(qmap)
}
const reloadShip = () => lastRequest.id && loadShip(lastRequest.id, lastRequest.lo, lastRequest.lq)

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
  if (lastRequest.id) loadShip(lastRequest.id, '', '')
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
watch([() => ship.value?.id, encoded, encodedQ], ([id, lo, lq]) => {
  if (!id || shipLoading.value) return
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ ship: id, lo, lq })) } catch { /* 存不了就算了 */ }
  if (props.active && onLoadoutUrl() && (route.query.ship !== id || (route.query.lo || '') !== lo || (route.query.lq || '') !== lq)) {
    const query = { ...route.query, ship: id }
    if (lo) query.lo = lo
    else delete query.lo
    if (lq) query.lq = lq
    else delete query.lq
    router.replace({ query })
  }
})
function shareUrl() {
  const url = new URL(window.location.href)
  url.search = ''
  url.hash = ''
  url.searchParams.set('tab', 'toolbox')
  url.searchParams.set('sub', 'loadout')
  url.searchParams.set('ship', ship.value.id)
  if (encoded.value) url.searchParams.set('lo', encoded.value)
  if (encodedQ.value) url.searchParams.set('lq', encodedQ.value)
  return url.toString()
}
async function copyLink() {
  await copyText(shareUrl(), { okText: '已複製連結' })
}

// ── 存到我的機庫：把這份配裝的連結加到艦隊那艘船的配件網址（PUT /player/fleet/<id> 的 unit_loadout） ──
const fleetRow = computed(() => (ship.value ? props.fleet.find(r => r.vehicle_uuid === ship.value.id) || null : null))
const saveUnit = ref(1)
watch(fleetRow, () => { saveUnit.value = 1 })
const savingLink = ref(false)
async function saveToFleet() {
  const row = fleetRow.value
  if (!row || savingLink.value) return
  const unit = Math.min(Math.max(1, saveUnit.value || 1), row.quantity || 1)
  const current = row.unit_loadouts?.length ? row.unit_loadouts[unit - 1] || [] : (unit === 1 ? row.loadout_links || [] : [])
  const url = shareUrl()
  if (current.some(l => l.url === url)) { toast('這份配裝已經存過了', 'info'); return }
  const links = [...current.map(l => ({ label: l.label || '', url: l.url, private: !!l.private })),
    { label: `配裝模擬${changes.value.length ? `（改 ${changes.value.length} 格）` : '（預設）'}`, url }]
  savingLink.value = true
  const res = await props.fetcher(`/player/fleet/${encodeURIComponent(row._id)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ unit_loadout: { unit, links } }) })
  const body = res ? await res.json().catch(() => null) : null
  savingLink.value = false
  if (!res?.ok || !body?.success) { toast(body?.message || '存檔失敗', 'error'); return }
  toast('已存到我的機庫（艦隊的配件網址）')
  emit('fleet-changed')
}

// ── 顯示 ──
// ── 電源分配（pips）：戰鬥／量子兩種模式各記一份，換配件時沒動到的格數保留、其餘重新自動分配 ──
const powerMode = ref('scm')
const pipsByMode = reactive({ scm: {}, quantum: {} })
const pips = computed(() => pipsByMode[powerMode.value])
const listOf = mode => (ship.value?.power ? consumers(ship.value, slots.value, itemOf, mode, weaponOff) : [])
const powerList = computed(() => listOf(powerMode.value))
const powerGen = computed(() => (ship.value?.power ? generation(ship.value, slots.value, defaults.value, itemOf) : 0))
const ppEm = computed(() => powerPlantEm(slots.value, itemOf))
const powerSum = computed(() => powerSummary(ship.value, powerList.value, pips.value, powerGen.value, ppEm.value))
// 耗電者的組成（哪一格裝什麼）變了才重新分配；合成的護盾看裡面每一個產生器
const itemSig = c => (c.items ? c.items.map(i => i?.id || '').join('+') : c.item?.id || c.key)
const powerSig = computed(() => JSON.stringify([powerGen.value,
  ...listOf('scm').map(c => [c.key, itemSig(c), c.max, c.draw])]))
let lastItems = {}
function autoPips(all = false) {
  // all＝「自動分配」按鈕：目前模式全部重分；否則（換了配件）兩個模式都只重分有變動的
  for (const mode of all ? [powerMode.value] : ['scm', 'quantum']) {
    const list = listOf(mode)
    const keep = {}
    if (!all) {
      for (const c of list) {
        const id = itemSig(c)
        if (c.key in pipsByMode[mode] && lastItems[c.key] === id) keep[c.key] = pipsByMode[mode][c.key]
      }
    }
    pipsByMode[mode] = autoAllocate(list, powerGen.value, keep)
  }
  lastItems = Object.fromEntries(listOf('scm').map(c => [c.key, itemSig(c)]))
}
watch(powerSig, () => autoPips(false))
// 手動調格數、全部開滿都不會超出發電量（見 utils/loadoutPower.js 的 setWithinGen／maxAllocate）
function setPips(key, p) {
  pipsByMode[powerMode.value] = setWithinGen(powerList.value, pipsByMode[powerMode.value], key, p, powerGen.value)
}
function maxPips() {
  pipsByMode[powerMode.value] = maxAllocate(powerList.value, powerGen.value)
}
// 護盾回充依戰鬥模式分到的格數打折
const shieldEff = computed(() => {
  if (!ship.value?.power) return null
  const out = {}
  for (const c of listOf('scm')) {
    // 護盾是合成的一欄：每個產生器依分到的格數各自打折
    if (c.kind === 'shield') for (const part of shieldShares(c, pipsByMode.scm[c.key] ?? c.max)) out[part.key] = part.eff
  }
  return out
})

const summary = computed(() => summarize(ship.value, slots.value, itemOf, shieldEff.value, weaponOff))
// 武器效率：武器電源池分到的格數 ÷ 武器耗電加總（遊戲電源畫面的武器欄；沒有電源資料的船當 100%）
const weaponEff = computed(() => {
  const c = powerList.value.find(x => x.kind === 'weapons')
  if (!c) return ship.value?.power ? 0 : 1
  return consumerLoad(c, pips.value[c.key] ?? c.max).eff
})
// 武器卡的彈速、射程長條：用這艘船目前裝的武器裡最大的當滿格
const weaponScale = computed(() => {
  let speed = 0
  let range = 0
  walk(slots.value, (n) => {
    const it = itemOf(n.item)
    if (it?.type !== 'WeaponGun') return
    speed = Math.max(speed, it.stats?.speed || 0)
    range = Math.max(range, it.stats?.range || 0)
  })
  return { speed, range }
})
const isWeaponOff = nodes => nodes.every(n => weaponOff.has(n.id))
function toggleWeaponPower(nodes) {
  const off = !isWeaponOff(nodes)
  for (const n of nodes) {
    if (off) weaponOff.add(n.id)
    else weaponOff.delete(n.id)
  }
}
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

const itemLabel = it => it.name_zh || it.name
const FACE_LABEL = { Quadrant: '四面護盾', Bubble: '單面護盾', FrontBack: '前後護盾' }
const faceLabel = computed(() => FACE_LABEL[ship.value?.shield_face] || ship.value?.shield_face || '')

const dmgText = d => Object.entries(d || {}).filter(([, v]) => v).map(([k, v]) => `${DMG_LABEL[k] || k} ${fmtNum(v, 1)}`).join(' · ')
const pct = v => `${fmtNum(v * 100)}%`
const pctRange = r => (!r ? '—' : r[0] === r[1] ? pct(r[1]) : `${pct(r[0])}–${pct(r[1])}`)
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
      // 實彈：連續開火幾秒過熱、過熱後幾秒恢復；能量：電容滿電可連續開火幾秒、幾秒充滿
      add('過熱', s.overheat_s, `${fmtNum(s.overheat_s, 1)} 秒開火 · ${fmtNum(s.overheat_fix_s ?? 0, 1)} 秒恢復`)
      add('電容', s.cap_fire_s, `${fmtNum(s.cap_fire_s, 1)} 秒開火${s.cap_recharge_s != null ? ` · ${fmtNum(s.cap_recharge_s, 1)} 秒充滿` : ''}`)
      add('射速', s.rpm, `${fmtNum(s.rpm)}/分`)
      add('射程', s.range, `${fmtNum(s.range)} m`)
      add('彈速', s.speed, `${fmtNum(s.speed)} m/s`)
      add('穿透', s.pen_distance, `${fmtNum(s.pen_distance, 2)} m`)
      add('類型', dmgText(s.damage) || null, Object.keys(s.damage || {}).map(k => DMG_LABEL[k] || k).join('／'))
      break
    case 'Missile': case 'Bomb':
      add('追蹤', s.tracking, TRACK_LABEL[s.tracking] || s.tracking)
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
// 區塊整區收起（記在這次瀏覽）
const folded = reactive(new Set())
function toggleSec(key) {
  if (folded.has(key)) folded.delete(key)
  else folded.add(key)
}
const allFolded = computed(() => sections.value.length > 0 && sections.value.every(sec => folded.has(sec.key)))
function foldAllSections() {
  const fold = !allFolded.value
  for (const sec of sections.value) {
    if (fold) folded.add(sec.key)
    else folded.delete(sec.key)
  }
}

// ── 顯示用 ──
const CAREER_LABEL = { Combat: '戰鬥', Transporter: '運輸', Exploration: '探索', Industrial: '工業', Support: '支援',
  Competition: '競速', 'Multi-Role': '多用途', Ground: '地面' }
const careerLabel = computed(() => (ship.value?.career ? CAREER_LABEL[ship.value.career] || ship.value.career : ''))
// 護盾回充：依戰鬥模式分到的電力打折後佔開滿的比例
const regenPct = computed(() => (summary.value.shield.regenMax ? summary.value.shield.regen / summary.value.shield.regenMax : null))
const CHIP_KEYS = ['physical', 'energy', 'distortion']
/** 抗性／吸收：{physical: [最小, 最大] 或數字} → 晶片（取最大值） */
function chipsOf(m) {
  if (!m) return []
  return CHIP_KEYS.filter(k => m[k] != null).map(k => {
    const v = Array.isArray(m[k]) ? m[k][1] : m[k]
    return { k, label: DMG_LABEL[k], text: `${fmtNum(v * 100)}%` }
  })
}
/** 偏轉門檻：{physical: 傷害值} */
const dmgChips = d => CHIP_KEYS.filter(k => d?.[k]).map(k => ({ k, label: DMG_LABEL[k], text: fmtNum(d[k]) }))
/** 裝甲減傷：受到的傷害倍率 → 減少的百分比 */
const multChips = m => CHIP_KEYS.filter(k => m?.[k] != null && m[k] !== 1)
  .map(k => ({ k, label: DMG_LABEL[k], text: `${m[k] < 1 ? '-' : '+'}${fmtNum(Math.abs(1 - m[k]) * 100)}%` }))

const pickerOpen = ref(false)
const pickerNodes = ref([])
const pickerLoading = ref(false)
async function openPicker(nodes) {
  pickerNodes.value = nodes
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
const pickerSlotText = computed(() => {
  const n = pickerNodes.value[0]
  if (!n) return ''
  return n.min === n.max ? `S${n.min}` : `S${n.min}–S${n.max}`
})
const pickerAll = computed(() => {
  const node = pickerNodes.value[0]
  if (!node || !pickerOpen.value) return []
  const tags = tagsOf(node)
  return [...itemCache.values()].filter(it => fits(it, node, tags))
})
async function choose(it) {
  if (it) await ensureIds([it.id, ...(it.ports || []).map(p => p.default)])
  equip(pickerNodes.value, it?.id || null, itemOf, tagsOf)
  pickerOpen.value = false
}

provide('loadout', { itemOf, open: openPicker, primary, secondary, itemLabel, typeLabel, classLabel,
  openInfo, addCart, qualityData, qualityOf, setQuality, avgOf, nudgeQuality,
  weaponEff: () => weaponEff.value, weaponScale: () => weaponScale.value, isWeaponOff, toggleWeaponPower })
</script>

<style scoped>
/* ── 版面：側欄（選船＋動作）寬螢幕在右邊、其餘在上方（跟資料庫的搜尋卡一樣） ── */
.lo-layout { display: flex; flex-direction: column; gap: 1rem; }
.lo-side, .lo-main { display: flex; flex-direction: column; gap: 1rem; min-width: 0; }
.lo-card { margin: 0; }
@media (min-width: 1400px) {
  .lo-layout { display: grid; grid-template-columns: minmax(0, 1fr) 22rem; align-items: start; }
  .lo-side { grid-column: 2; grid-row: 1; position: sticky; top: calc(var(--sf-topbar-h, 52px) + var(--sf-tabs-h, 42px) + .75rem); }
  .lo-main { grid-column: 1; grid-row: 1; }
}
@media (min-width: 768px) and (max-width: 1399.98px) {
  /* 上方：選船跟動作並排 */
  .lo-side { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); align-items: start; }
}
.lo-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 24rem), 1fr)); gap: 1rem; }

/* ── 船名 ── */
.lo-hero { padding: 1.25rem 1.5rem; }
.lo-title { font-size: clamp(1.8rem, 3.2vw, 2.6rem); font-weight: 800; margin: .1rem 0 0; line-height: 1.1; color: var(--sf-text-strong); }
.lo-en { color: var(--sf-text-muted); font-size: var(--sf-fs-base); margin-top: .2rem; }
.lo-badges { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: .8rem; }
.lo-badge { display: inline-flex; align-items: center; padding: .25rem .65rem; border-radius: .4rem; font-weight: 700;
  font-size: var(--sf-fs-sm); color: var(--sf-text-strong); background: rgba(var(--sf-accent-2-rgb), .18);
  border: 1px solid rgba(var(--sf-accent-2-rgb), .45); }
.lo-badge--hi { color: var(--sf-accent-2-ink, #0b1020); background: var(--sf-accent-2); border-color: var(--sf-accent-2); }
.lo-badge--ok { background: rgba(var(--bs-success-rgb), .15); border-color: rgba(var(--bs-success-rgb), .45); color: rgb(var(--bs-success-rgb)); }

/* ── 大數字方塊 ── */
.lo-big { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .6rem; margin-bottom: 1rem; }
.lo-big--2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.lo-bt { padding: .8rem .9rem; border-radius: .6rem; background: var(--sf-chip-bg); border: 1px solid var(--sf-border); min-width: 0; }
.lo-bt--hi { border-color: rgba(var(--sf-accent-2-rgb), .7); background: rgba(var(--sf-accent-2-rgb), .1); }
.lo-bt__v { font-size: clamp(1.35rem, 2.2vw, 1.9rem); font-weight: 800; line-height: 1.1; color: var(--sf-text-strong);
  font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.lo-bt--hi .lo-bt__v { color: var(--sf-accent-2); }
.lo-bt__l { margin-top: .3rem; font-size: var(--sf-fs-xs); font-weight: 600; letter-spacing: .1em; color: var(--sf-text-muted); }
.lo-bt__pct { font-weight: 700; color: var(--sf-accent-2); font-size: var(--sf-fs-sm); }
.lo-bt__bar { height: .3rem; margin-top: .35rem; border-radius: 1rem; background: var(--sf-hover-bg); overflow: hidden; }
.lo-bt__bar span { display: block; height: 100%; background: var(--sf-accent-2); border-radius: 1rem; }

/* ── 防禦的列：左標籤、右值或晶片 ── */
.lo-rows { display: flex; flex-direction: column; }
.lo-r { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .3rem .75rem;
  padding: .45rem 0; border-bottom: 1px solid var(--sf-border); }
.lo-r:last-child { border-bottom: 0; }
.lo-r__k { color: var(--sf-text); font-size: var(--sf-fs-base); }
.lo-r__v { font-weight: 700; color: var(--sf-text-strong); font-variant-numeric: tabular-nums; text-align: right; }
.lo-r--big .lo-r__v { font-size: var(--sf-fs-lg); font-weight: 800; }
.lo-r__v--sm { font-weight: 600; font-size: var(--sf-fs-sm); }
.lo-chips { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .35rem; }
.lo-chip { padding: .15rem .6rem; border-radius: 999px; font-size: var(--sf-fs-sm); color: var(--sf-text);
  background: var(--sf-chip-bg); border: 1px solid var(--sf-border); white-space: nowrap; }
.lo-chip b { font-weight: 800; }
.lo-c--physical { color: #c9b28a; }
.lo-c--energy { color: var(--sf-accent-2); }
.lo-c--distortion { color: #b79cff; }
:root[data-sf-mode='light'] .lo-c--physical { color: #7a5c1e; }
:root[data-sf-mode='light'] .lo-c--distortion { color: #5b3dbf; }

/* ── 動作 ── */
.lo-actions { display: grid; grid-template-columns: 1fr 1fr; gap: .5rem; }
.lo-actions__wide { grid-column: 1 / -1; }

/* ── 購物車 ── */
.lo-cart { padding: .5rem 0; border-bottom: 1px solid var(--sf-border); }
.lo-cart__name { display: block; width: 100%; padding: 0; border: 0; background: none; text-align: left; font-weight: 700;
  color: var(--sf-text-strong); overflow-wrap: anywhere; }
.lo-cart__line { display: flex; align-items: center; gap: .5rem; margin-top: .25rem; }
.lo-cart__line .lo-cart__meta { flex: 1 1 auto; min-width: 0; }
.lo-cart__name:hover:not(:disabled) { color: var(--sf-accent); }
.lo-cart__meta { font-size: var(--sf-fs-xs); color: var(--sf-text-muted); }
.lo-cart__qty { display: flex; align-items: center; gap: .3rem; flex: none; }
.lo-cart__qty .btn { padding: .05rem .35rem; }
.lo-cart__qty span { min-width: 1.4rem; text-align: center; font-weight: 700; }
.lo-cart__sub { flex: none; min-width: 6.5rem; text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }
.lo-cart__total { display: flex; justify-content: space-between; align-items: baseline; gap: .5rem; padding-top: .6rem; }
.lo-cart__total b { font-size: var(--sf-fs-lg); color: var(--sf-accent-2); }
.min-w-0 { min-width: 0; }


.lo-mfr { color: var(--sf-text-muted); }
.lo-muted { color: var(--sf-text-muted); }
.lo-h { font-size: var(--sf-fs-lg); font-weight: 800; margin-bottom: .85rem; color: var(--sf-text-strong); }
.lo-tiles { display: grid; grid-template-columns: repeat(3, 1fr); gap: .5rem; margin-bottom: .6rem; }
.lo-tile { padding: .5rem .6rem; border: 1px solid var(--sf-border); border-radius: .4rem; background: var(--sf-chip-bg); }
.lo-tile--hi { border-color: rgba(var(--sf-accent-rgb), .8); background: rgba(var(--sf-accent-rgb), .15); }
.lo-tile__v { font-size: 1.35rem; font-weight: 700; color: var(--sf-text-strong); line-height: 1.1; }
.lo-tile--hi .lo-tile__v { color: var(--sf-accent); }
.lo-tile__l { font-size: .8rem; color: var(--sf-text-muted); }
.lo-table { --bs-table-bg: transparent; }
.lo-table th { font-size: var(--sf-fs-xs); color: var(--sf-text-muted); font-weight: 700; letter-spacing: .08em; }
.lo-table td { font-size: var(--sf-fs-base); padding-top: .55rem; padding-bottom: .55rem; }
.lo-table td.text-end { font-weight: 700; color: var(--sf-text-strong); font-variant-numeric: tabular-nums; }
.lo-sec { container: lo-sec / inline-size; }
.lo-sec__head { display: flex; align-items: center; gap: .5rem; width: 100%; padding: 0; border: 0; background: none;
  text-align: left; color: inherit; }
.lo-sec__head:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: 2px; border-radius: .3rem; }
.lo-sec__chev { color: var(--sf-text-muted); font-size: var(--sf-fs-sm); }
.lo-sec__head:hover .lo-sec__chev { color: var(--sf-text-strong); }
.lo-dl { display: grid; grid-template-columns: auto 1fr; gap: .25rem .8rem; margin: 0; }
.lo-dl dt { font-weight: 500; color: var(--sf-text-muted); }
.lo-dl dd { margin: 0; text-align: right; color: var(--sf-text-strong); }
@media (max-width: 575.98px) {
  .lo-tile__v { font-size: 1.1rem; }
}
</style>
