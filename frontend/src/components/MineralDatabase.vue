<!--
  玩家頁「資料庫 › 礦物」：每種礦物可以在哪裡挖到（唯讀，不用登入）。

  資料跟「工具箱 › 礦物回波」（components/MiningLookup.vue）同一份 scunpacked-data：
    - GET /mining/deposits：礦床成分（parts：礦物、含量範圍 %、出現機率）
    - GET /mining/locations：各地點（星系、類型）的礦床群組（船載／地面載具／手持／採集）與各礦床的佔比
  兩份合起來：礦物 → 有哪些地點的哪一種採集方式會出現含有它的礦床。
  遊戲資料有礦床、但沒有放到任何地點的礦物（例如 Carinite）也列出來，標「遊戲資料未標出產地」（有篩選地點／方式時不列）。
  focus：只看一種礦物（跳出視窗用，例如維克洛需要的礦物），不顯示搜尋卡、第一筆直接展開。
  取得方式：要先完成特殊行動、任務、活動才挖得到的礦物，後台手動填寫（GET /mining/sources，src/models/mineral_source.py），
  列表標出來、展開「詳細」最上面顯示說明；「採集方式」篩選多一個「特殊取得」。
  展開「詳細」另外列「用在哪些藍圖」：GET /blueprint/master/by-material（名稱去掉 (Ore)／(Raw) 後綴比對）。
  「出現率」＝那一類礦床在該地點同一群組裡的佔比 × 礦床含有這種礦物的機率（遊戲資料的相對值，不是實際刷新次數）。
  打撈、殘骸、化石、戰利品箱這些群組不列。
-->
<template>
  <!-- sf-split：超寬螢幕搜尋卡放左邊、列表放右邊（跟資料庫其他子分頁一致，見 scifi-theme.css） -->
  <div class="sf-split">
    <div v-if="!focus" :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body py-3">
        <div class="row g-2 g-md-3 align-items-start">
          <div class="col-12 col-md-3">
            <label class="form-label small fw-semibold mb-1" for="mdb-q">礦物名稱</label>
            <input id="mdb-q" v-model="query" type="search" class="form-control form-control-sm"
              placeholder="中英文皆可" autocomplete="off">
          </div>
          <!-- 星系：選項少，直接列出來可複選（MultiSelectFilter 選項 ≤ 4 時自動變按鈕） -->
          <div class="col-12 col-md-5">
            <label class="form-label small fw-semibold mb-1" for="mdb-system">星系</label>
            <MultiSelectFilter id="mdb-system" v-model="system" :options="systemOptions" label="星系" placeholder="全部" block />
          </div>
          <div class="col-6 col-md-2">
            <label class="form-label small fw-semibold mb-1" for="mdb-place">地點</label>
            <select id="mdb-place" v-model="place" class="form-select form-select-sm">
              <option value="">全部</option>
              <option v-for="p in placeOptions" :key="p.key" :value="p.key">{{ p.label }}</option>
            </select>
          </div>
          <div class="col-6 col-md-2">
            <label class="form-label small fw-semibold mb-1" for="mdb-method">採集方式</label>
            <select id="mdb-method" v-model="method" class="form-select form-select-sm">
              <option value="">全部</option>
              <option v-for="m in METHODS" :key="m.key" :value="m.key">{{ m.label }}</option>
              <option :value="SOURCE_FILTER">特殊取得（行動／任務／活動）</option>
            </select>
          </div>
        </div>
        <div v-if="hasFilter" class="d-flex flex-wrap align-items-center gap-2 mt-2">
          <span class="small text-muted">符合 {{ rows.length }} 種礦物</span>
          <button type="button" class="btn btn-sm btn-warning ms-auto" @click="clearFilters">清除篩選</button>
        </div>
      </div>
    </div>

    <SfState :loading="loading" :error="error" :empty="loaded && !rows.length"
      :empty-text="minerals.length ? '沒有符合條件的礦物。' : '尚無礦物資料。'" @retry="load">
      <SortSelect v-if="isPhone" class="mb-2" :sort="sort" :options="SORT_OPTIONS" />
      <div :class="cardClass">
        <div class="card-body p-0">
          <div style="overflow-x: auto">
            <table class="table table-hover align-middle mb-0 sf-stack">
              <thead class="table-light">
                <tr>
                  <SortTh :sort="sort" field="name" class="ps-3">礦物</SortTh>
                  <th>採集方式</th>
                  <SortTh :sort="sort" field="places" class="text-end">地點數</SortTh>
                  <SortTh :sort="sort" field="content" class="text-end">最高含量</SortTh>
                  <SortTh :sort="sort" field="chance" class="text-end">最高出現率</SortTh>
                  <th class="d-none d-lg-table-cell">主要地點</th>
                  <th class="pe-3"></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="m in sort.sorted.value" :key="m.key">
                  <tr>
                    <td class="ps-3 sf-stack__title">
                      <span class="sf-name">
                        <span class="fw-semibold">{{ m.name_zh || m.name }}</span>
                        <span v-if="m.uex_code" class="sf-chip sf-chip--accent ms-1">{{ m.uex_code }}</span>
                        <span v-if="m.name_zh" class="sf-name__en">{{ m.name }}</span>
                      </span>
                    </td>
                    <td data-label="採集方式">
                      <span v-for="k in m.methods" :key="k" class="sf-chip me-1">{{ methodLabel(k) }}</span>
                      <!-- 後台補的取得方式（特殊行動、任務獎勵…） -->
                      <span v-for="k in (sources[m.key]?.methods || [])" :key="`s-${k}`" class="sf-chip sf-chip--warn me-1">{{ sourceLabel(k) }}</span>
                      <span v-if="!m.methods.length && !sources[m.key]?.methods?.length" class="small text-muted">—</span>
                    </td>
                    <td class="text-end" data-label="地點數">{{ m.places }}</td>
                    <td class="text-end text-nowrap" data-label="最高含量">{{ pct(m.content) }}</td>
                    <td class="text-end text-nowrap" data-label="最高出現率">{{ m.chance == null ? '—' : pct(m.chance * 100, 2) }}</td>
                    <td class="d-none d-lg-table-cell small" data-label="主要地點">
                      <template v-if="m.places">{{ m.top.map(o => placeLabel(o)).join('、') }}<template v-if="m.places > m.top.length"> …</template></template>
                      <span v-else-if="sources[m.key]" class="text-muted">{{ sourceSummary(sources[m.key]) }}</span>
                      <span v-else class="text-muted">遊戲資料未標出產地</span>
                    </td>
                    <td class="text-end pe-3 sf-stack__actions">
                      <button type="button" class="btn btn-sm btn-info text-nowrap" :aria-expanded="openKey === m.key ? 'true' : 'false'"
                        @click="toggle(m)">
                        <i class="bi me-1" :class="openKey === m.key ? 'bi-chevron-up' : 'bi-chevron-down'"></i>詳細
                      </button>
                    </td>
                  </tr>
                  <tr v-if="openKey === m.key" class="sf-stack__detail">
                    <td colspan="7" class="mdb-detail">
                      <div class="sf-sheet__head sf-stack__sheet-head">
                        <h3 class="sf-sheet__title">{{ m.name_zh || m.name }}</h3>
                        <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="openKey = ''"><i class="bi bi-x-lg"></i></button>
                      </div>
                      <!-- 取得方式（後台手動填寫） -->
                      <template v-if="sources[m.key]">
                        <div class="mdb-sec">取得方式</div>
                        <div class="mb-1">
                          <span v-for="k in (sources[m.key].methods || [])" :key="k" class="sf-chip sf-chip--warn me-1">{{ sourceLabel(k) }}</span>
                        </div>
                        <!-- 自動判斷：遊戲說明（翻譯包中文，沒有就英文）＋資料來源 -->
                        <template v-if="sources[m.key].auto">
                          <p v-if="sources[m.key].description_zh || sources[m.key].description_en" class="small mb-1">
                            {{ sources[m.key].description_zh || sources[m.key].description_en }}</p>
                          <p class="small text-muted mb-1">遊戲資料沒有標出產地（來源：{{ sources[m.key].source }}）</p>
                        </template>
                        <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown 先跳脫整段 HTML，只產生白名單標籤 -->
                        <div v-else-if="sources[m.key].description" class="mdb-md small" v-html="renderMarkdown(sources[m.key].description)"></div>
                        <div v-if="sources[m.key].locations?.length" class="small mb-1">
                          <span class="text-muted me-1">相關地點</span>{{ sources[m.key].locations.map(locText).join('、') }}
                        </div>
                        <a v-if="sources[m.key].source_url || sources[m.key].web_url" :href="sources[m.key].source_url || sources[m.key].web_url"
                          target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-primary"><i class="bi bi-box-arrow-up-right me-1"></i>參考資料</a>
                        <div class="mb-3"></div>
                      </template>
                      <div v-if="m.occurrences.length || !sources[m.key]" class="mdb-sec">產地</div>
                      <p v-if="!m.occurrences.length && !sources[m.key]" class="small text-muted mb-2">
                        遊戲資料沒有標出產地。
                      </p>
                      <table v-else-if="m.occurrences.length" class="table table-sm align-middle mb-0 mdb-sub">
                        <thead>
                          <tr>
                            <th>地點</th><th>星系</th><th>類型</th><th>採集方式</th><th>礦床</th>
                            <th class="text-end">含量</th><th class="text-end">出現率</th>
                          </tr>
                        </thead>
                        <tbody>
                          <tr v-for="o in m.occurrences" :key="o.key">
                            <td data-label="地點" class="fw-semibold">{{ placeLabel(o) }}</td>
                            <td data-label="星系">{{ systemLabel(o.system) }}</td>
                            <td data-label="類型">{{ typeLabel(o.type) }}</td>
                            <td data-label="採集方式">{{ methodLabel(o.method) }}</td>
                            <td data-label="礦床">{{ o.deposits.join('、') }}</td>
                            <td class="text-end text-nowrap" data-label="含量">{{ range(o.min, o.max) }}</td>
                            <td class="text-end text-nowrap" data-label="出現率">{{ pct(o.chance * 100, 2) }}</td>
                          </tr>
                        </tbody>
                      </table>

                      <!-- 用在哪些藍圖 -->
                      <div class="mdb-sec mt-3">用在哪些藍圖
                        <span v-if="bpOf(m).rows" class="small text-muted fw-normal ms-1">{{ bpOf(m).rows.length }} 張</span>
                      </div>
                      <div v-if="bpOf(m).loading" class="small text-muted"><span class="spinner-border spinner-border-sm me-1"></span>載入中…</div>
                      <div v-else-if="bpOf(m).error" class="small text-danger">{{ bpOf(m).error }}
                        <button type="button" class="btn btn-sm btn-secondary ms-2" @click="loadBlueprints(m, true)">重試</button></div>
                      <p v-else-if="bpOf(m).rows && !bpOf(m).rows.length" class="small text-muted mb-0">沒有藍圖用到這種礦物。</p>
                      <template v-else-if="bpOf(m).rows">
                        <input v-if="bpOf(m).rows.length > 8" v-model="bpQuery" type="search" class="form-control form-control-sm mb-2 mdb-bpq"
                          placeholder="篩選藍圖名稱或類型" aria-label="篩選藍圖">
                        <table class="table table-sm align-middle mb-0 mdb-sub">
                          <thead>
                            <tr><th>藍圖</th><th>類型</th><th class="text-end">用量</th><th class="ps-3">取得</th><th></th></tr>
                          </thead>
                          <tbody>
                            <tr v-for="b in bpShown(m)" :key="b._id">
                              <td data-label="藍圖" class="fw-semibold">{{ b.name_zh || b.name }}
                                <span v-if="b.name_zh" class="small text-muted fw-normal ms-1">{{ b.name }}</span></td>
                              <td data-label="類型" class="small">{{ blueprintTypeZh(b.output_type) || b.output_type_label || b.output_type || '—' }}</td>
                              <td data-label="用量" class="text-end text-nowrap">{{ useLabel(b) }}</td>
                              <td data-label="取得" class="ps-3">
                                <span v-if="b.is_available_by_default" class="sf-chip sf-chip--accent">預設可用</span>
                                <span v-else-if="b.mission_count" class="sf-chip">任務 {{ b.mission_count }} 個</span>
                                <span v-else class="small text-muted">—</span>
                              </td>
                              <td class="text-end">
                                <button type="button" class="btn btn-sm btn-info text-nowrap" :aria-label="`${b.name_zh || b.name} 藍圖詳細`"
                                  @click="openBlueprint(b, m)"><i class="bi bi-hammer me-1"></i>詳細</button>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                        <button v-if="bpFiltered(m).length > bpShown(m).length" type="button" class="btn btn-sm btn-secondary mt-2"
                          @click="bpAll = true">顯示全部 {{ bpFiltered(m).length }} 張</button>
                      </template>

                      <!-- 用在哪些任務（要運送這種礦物的任務） -->
                      <div class="mdb-sec mt-3">用在哪些任務
                        <span v-if="msOf(m).rows" class="small text-muted fw-normal ms-1">{{ msOf(m).rows.length }} 個</span>
                      </div>
                      <div v-if="msOf(m).loading" class="small text-muted"><span class="spinner-border spinner-border-sm me-1"></span>載入中…</div>
                      <div v-else-if="msOf(m).error" class="small text-danger">{{ msOf(m).error }}
                        <button type="button" class="btn btn-sm btn-secondary ms-2" @click="loadMissions(m, true)">重試</button></div>
                      <p v-else-if="msOf(m).rows && !msOf(m).rows.length" class="small text-muted mb-0">沒有任務要運送這種礦物。</p>
                      <template v-else-if="msOf(m).rows">
                        <table class="table table-sm align-middle mb-0 mdb-sub">
                          <thead><tr><th>任務</th><th class="text-end">運送量</th><th class="text-end">報酬</th><th></th></tr></thead>
                          <tbody>
                            <tr v-for="ms in msOf(m).rows.slice(0, MS_PAGE)" :key="ms._id">
                              <td data-label="任務" class="fw-semibold">{{ ms.title_zh || ms.title }}</td>
                              <td data-label="運送量" class="text-end text-nowrap">{{ fmtHaul(ms.haul) }}</td>
                              <td data-label="報酬" class="text-end text-nowrap">{{ rewardLabel(ms) }}</td>
                              <td class="text-end">
                                <button type="button" class="btn btn-sm btn-info text-nowrap" :aria-label="`${ms.title_zh || ms.title} 任務詳細`"
                                  @click="openMissions(m, [ms])"><i class="bi bi-flag me-1"></i>詳細</button>
                              </td>
                            </tr>
                          </tbody>
                        </table>
                        <button v-if="msOf(m).rows.length > MS_PAGE" type="button" class="btn btn-sm btn-secondary mt-2"
                          @click="openMissions(m, msOf(m).rows)">全部 {{ msOf(m).rows.length }} 個任務</button>
                      </template>

                      <!-- 買賣價格（UEX） -->
                      <div class="mdb-sec mt-3">買賣價格</div>
                      <MineralPrices :uex="m.uex" :fetcher="fetcher" />
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </SfState>
    <BlueprintDetailModal ref="bpDetailRef" :fetcher="fetcher" />
    <BlueprintMissionsModal ref="missionsRef" :fetcher="fetcher" />
  </div>
</template>

<script setup>
import { filterByName } from '@/utils/nameSearch'
import { computed, reactive, ref, watch } from 'vue'
import SfState from '@/components/SfState.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import BlueprintDetailModal from '@/components/BlueprintDetailModal.vue'
import BlueprintMissionsModal from '@/components/BlueprintMissionsModal.vue'
import MineralPrices from '@/components/MineralPrices.vue'
import { rewardLabel } from '@/utils/mission'
import SortSelect from '@/components/SortSelect.vue'
import SortTh from '@/components/SortTh.vue'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'
import { blueprintTypeZh } from '@/utils/blueprintOutputType'
import { renderMarkdown } from '@/utils/markdown'
import { loadTranslations, translate } from '@/utils/translations'

const props = defineProps({
  fetcher: { type: Function, required: true },
  /** 分頁第一次變成可見才載入 */
  active: { type: Boolean, default: true },
  cardClass: { type: String, default: 'card' },
  /** 站內「到礦物頁找這個」帶進來的名稱（MyPlayerView 的 ?find=） */
  find: { type: Object, default: null },
  /** 只看這一種礦物（跳出視窗用，例如維克洛需要的礦物）：不顯示搜尋卡、載入後直接展開「詳細」 */
  focus: { type: String, default: '' },
})

/** 地點的礦床群組 → 採集方式（其餘群組：打撈、殘骸、化石、戰利品箱不列） */
const METHODS = [
  { key: 'ship', label: '船載採礦', re: /^spaceship/i },
  { key: 'vehicle', label: '地面載具', re: /^groundvehicle/i },
  { key: 'fps', label: '手持採礦', re: /^fps/i },
  { key: 'harvest', label: '採集', re: /^(ha(r)?vestables?|plants?)$/i },
]
const methodOf = group => METHODS.find(m => m.re.test(group || ''))?.key || ''
const methodLabel = k => METHODS.find(m => m.key === k)?.label || k
const TYPE_LABEL = { planet: '行星', moon: '衛星', lagrange: '拉格朗日點', belt: '小行星帶', cluster: '小行星群',
  cave: '洞穴', special: '特殊地點' }
const typeLabel = t => (t ? TYPE_LABEL[t] || t : '—')
const SYSTEM_LABEL = { Stanton: '斯坦頓', Pyro: '派羅', Nyx: '尼克斯' }
const systemLabel = s => (s ? (SYSTEM_LABEL[s] ? `${SYSTEM_LABEL[s]}（${s}）` : s) : '—')
const placeLabel = o => (o.name_zh && o.name_zh !== o.name ? `${o.name_zh}（${o.name}）` : o.name)
// 遊戲資料裡還沒補名稱的會是 <= PLACEHOLDER =>，改用 key
const realName = s => (s && !s.includes('<=') ? s : '')
const pct = (v, digits = 0) => (v == null || !Number.isFinite(v) ? '—'
  : `${Number(v).toLocaleString('en-US', { maximumFractionDigits: digits })}%`)
const range = (min, max) => (min == null || max == null ? '—' : min === max ? `${min}%` : `${min}–${max}%`)

// ── 資料 ──
const deposits = ref([])
const locations = ref([])
const loading = ref(false)
const loaded = ref(false)
const error = ref('')
async function load() {
  loading.value = true
  error.value = ''
  const [d, l] = await Promise.all(['/mining/deposits', '/mining/locations'].map(async url => {
    const res = await props.fetcher(url)
    const body = res ? await res.json().catch(() => null) : null
    return res?.ok && body?.success ? body.data || [] : null
  }))
  loading.value = false
  if (!d || !l) {
    error.value = '讀取失敗。'
    return
  }
  deposits.value = d
  locations.value = l
  loaded.value = true
  loadSources()
}

// ── 取得方式（後台手動填寫；讀不到不影響其他內容）──
const SOURCE_FILTER = '__source'
const sources = ref({})
const sourceLabels = ref({})
const sourceLabel = k => sourceLabels.value[k] || k
/** 主要地點欄的摘要：自動判斷只有「需特殊取得」；手填的寫「需特殊行動、洞穴取得」 */
function sourceSummary(src) {
  const ms = (src.methods || []).filter(k => k !== 'unplaced').map(sourceLabel)
  return ms.length ? `需${ms.join('、')}取得` : '需特殊取得'
}
const locText = en => { const zh = translate('location', en); return zh && zh !== en ? `${zh}（${en}）` : en }
async function loadSources() {
  const res = await props.fetcher('/mining/sources')
  const body = res ? await res.json().catch(() => null) : null
  if (!res?.ok || !body?.success) return
  // 後台手填的為主；沒填的用自動判斷（Wiki API 標成可開採、但遊戲資料沒標產地，例如 Carinite）
  sources.value = Object.fromEntries([...(body.auto || []).map(x => [x.key, { ...x, auto: true }]),
    ...(body.data || []).map(x => [x.key, x])])
  sourceLabels.value = body.methods_label || {}
  loadTranslations('location', (body.data || []).flatMap(x => x.locations || []))
}
watch(() => props.active, on => { if (on && !loaded.value && !loading.value) load() }, { immediate: true })

/** 礦物 → 出現的地方（同一個地點、同一種採集方式合成一筆：含量取最大範圍、出現率取最高） */
const minerals = computed(() => {
  const depById = new Map(deposits.value.map(d => [d._id, d]))
  const byKey = new Map()
  for (const loc of locations.value) {
    for (const g of loc.groups || []) {
      const method = methodOf(g.group_name)
      if (!method) continue
      for (const dref of g.deposits || []) {
        const dep = depById.get(dref.resource_uuid)
        if (!dep) continue
        for (const p of dep.parts || []) {
          const key = p.resource_key || p.resource_name
          if (!key) continue
          let m = byKey.get(key)
          if (!m) {
            m = { key, name: realName(p.resource_name) || key.replace(/_/g, ' '), name_zh: p.resource_name_zh || '', uex_code: p.uex?.code || '', uex: p.uex || null,
              occ: new Map() }
            byKey.set(key, m)
          }
          const okey = `${loc.system}|${loc.location_name}|${method}`
          const chance = (dref.relative_probability ?? 0) * (p.probability ?? 1)
          let o = m.occ.get(okey)
          if (!o) {
            o = { key: okey, system: loc.system, name: loc.location_name, name_zh: loc.location_name_zh, type: loc.location_type,
              method, deposits: [], min: p.min_percentage, max: p.max_percentage, chance: 0 }
            m.occ.set(okey, o)
          }
          const depName = dep.deposit_name_zh || dep.deposit_name
          if (depName && !o.deposits.includes(depName)) o.deposits.push(depName)
          if (p.min_percentage != null && (o.min == null || p.min_percentage < o.min)) o.min = p.min_percentage
          if (p.max_percentage != null && (o.max == null || p.max_percentage > o.max)) o.max = p.max_percentage
          o.chance = Math.max(o.chance, chance)
        }
      }
    }
  }
  // 有礦床、但沒放到任何地點的礦物（Carinite 等）：一樣列出來，產地空白
  for (const dep of deposits.value) {
    for (const p of dep.parts || []) {
      const key = p.resource_key || p.resource_name
      if (!key || byKey.has(key) || !realName(p.resource_name)) continue
      byKey.set(key, { key, name: p.resource_name, name_zh: p.resource_name_zh || '', uex_code: p.uex?.code || '', uex: p.uex || null, occ: new Map() })
    }
  }
  return [...byKey.values()].map(m => ({ ...m, all: [...m.occ.values()] }))
})

// ── 篩選 ──
const query = ref('')
watch(() => props.find, (v) => { if (v?.q) query.value = v.q }, { immediate: true })
// 星系可複選（空陣列＝全部）
const system = ref([])
const place = ref('')
const method = ref('')
const systems = computed(() => [...new Set(locations.value.map(l => l.system).filter(Boolean))].sort())
const systemOptions = computed(() => systems.value.map(s => ({ value: s, label: systemLabel(s) })))
const inSystem = s => !system.value.length || system.value.includes(s)
const placeOptions = computed(() => {
  const seen = new Map()
  for (const l of locations.value) {
    if (!l.location_name || !inSystem(l.system)) continue
    const key = `${l.system}|${l.location_name}`
    if (!seen.has(key)) seen.set(key, { key, label: placeLabel({ name: l.location_name, name_zh: l.location_name_zh }), system: l.system })
  }
  return [...seen.values()].sort((a, b) => a.system.localeCompare(b.system) || a.label.localeCompare(b.label))
})
watch(system, () => { if (place.value && !placeOptions.value.some(p => p.key === place.value)) place.value = '' })
const hasFilter = computed(() => !!(query.value.trim() || system.value.length || place.value || method.value))
function clearFilters() {
  query.value = ''
  system.value = []
  place.value = ''
  method.value = ''
}

const rows = computed(() => {
  const out = []
  for (const m of filterByName(minerals.value, query.value, x => [x.name, x.name_zh, x.key, x.uex_code]).rows) {
    // 「特殊取得」：只看後台補了取得方式的礦物（產地照常列）
    const bySource = method.value === SOURCE_FILTER
    if (bySource && !sources.value[m.key]) continue
    const occ = m.all.filter(o => inSystem(o.system)
      && (!place.value || `${o.system}|${o.name}` === place.value)
      && (!method.value || bySource || o.method === method.value))
    // 沒有產地資料的：只在沒篩地點／方式時列（「特殊取得」篩選時也列）
    if (!occ.length && (m.all.length || system.value.length || place.value || (method.value && !bySource))) continue
    occ.sort((a, b) => b.chance - a.chance || (b.max ?? 0) - (a.max ?? 0))
    const placeKeys = new Set(occ.map(o => `${o.system}|${o.name}`))
    const top = []
    for (const o of occ) {
      if (top.length >= 3) break
      if (!top.some(x => x.system === o.system && x.name === o.name)) top.push(o)
    }
    out.push({
      key: m.key, name: m.name, name_zh: m.name_zh, uex_code: m.uex_code, uex: m.uex, occurrences: occ, top,
      methods: METHODS.map(x => x.key).filter(k => occ.some(o => o.method === k)),
      places: placeKeys.size,
      content: occ.length ? Math.max(...occ.map(o => o.max ?? 0)) : null,
      chance: occ.length ? Math.max(...occ.map(o => o.chance)) : null,
    })
  }
  return out
})

// ── 排序、展開 ──
const SORT_OPTIONS = [{ field: 'name', label: '礦物' }, { field: 'places', label: '地點數' },
  { field: 'content', label: '最高含量' }, { field: 'chance', label: '最高出現率' }]
const sort = useTableSort(rows, { key: 'name', accessors: { name: m => m.name_zh || m.name } })
const openKey = ref('')
function toggle(m) {
  openKey.value = openKey.value === m.key ? '' : m.key
  bpQuery.value = ''
  bpAll.value = false
  if (openKey.value) { loadBlueprints(m); loadMissions(m) }
}
// 只看一種礦物（focus）：名稱帶進搜尋，第一筆自動展開
watch(() => props.focus, (v) => { if (v) { query.value = v; openKey.value = '' } }, { immediate: true })
watch(rows, (list) => {
  if (props.focus && !openKey.value && list.length) toggle(list[0])
})

// ── 用在哪些藍圖（展開時才抓，抓過的記著） ──
const bpCache = reactive({})
const bpQuery = ref('')
const bpAll = ref(false)
const BP_PAGE = 15
const bpOf = m => bpCache[m.key] || {}
async function loadBlueprints(m, force = false) {
  if (!force && bpCache[m.key] && !bpCache[m.key].error) return
  bpCache[m.key] = { loading: true }
  const res = await props.fetcher(`/blueprint/master/by-material?material=${encodeURIComponent(m.name)}`)
  const body = res ? await res.json().catch(() => null) : null
  bpCache[m.key] = res?.ok && body?.success ? { rows: body.data || [] } : { error: '藍圖讀取失敗。' }
}
function bpFiltered(m) {
  const rows = bpOf(m).rows || []
  return filterByName(rows, bpQuery.value, b => [b.name, b.name_zh, b.output_type, blueprintTypeZh(b.output_type)]).rows
}
const bpShown = m => (bpAll.value ? bpFiltered(m) : bpFiltered(m).slice(0, BP_PAGE))
function useLabel(b) {
  return (b.hits || []).map(h => (h.quantity_scu != null ? `${h.quantity_scu} SCU` : h.quantity != null ? `${h.quantity} 個` : '—'))
    .join('、') || '—'
}
// ── 用在哪些任務：要運送這種礦物的任務（GET /mission/by-commodity），展開時才抓 ──
const msCache = reactive({})
const msOf = m => msCache[m.key] || {}
const MS_PAGE = 8
async function loadMissions(m, force = false) {
  if (!force && msCache[m.key] && !msCache[m.key].error) return
  msCache[m.key] = { loading: true }
  const res = await props.fetcher(`/mission/by-commodity?name=${encodeURIComponent(m.name)}`)
  const body = res ? await res.json().catch(() => null) : null
  msCache[m.key] = res?.ok && body?.success ? { rows: body.data || [] } : { error: '任務讀取失敗。' }
}
const missionsRef = ref(null)
function openMissions(m, rows) {
  missionsRef.value?.showMissions({ title: m.name_zh || m.name, subtitle: m.name_zh ? m.name : '', heading: '運送這種礦物的任務', missions: rows })
}
const fmtHaul = h => (!h ? '—' : `× ${h.min_amount === h.max_amount || h.max_amount == null ? fmtInt(h.min_amount) : `${fmtInt(h.min_amount)}–${fmtInt(h.max_amount)}`}`)
const fmtInt = v => (v == null ? '?' : Number(v).toLocaleString('en-US'))
// ── 藍圖詳細（配方、品質試算、解鎖任務） ──
const bpDetailRef = ref(null)
const openBlueprint = (b, m) => bpDetailRef.value?.open({ uuid: b._id, name: b.name, name_zh: b.name_zh, output_type: b.output_type }, { material: m.name })
const { isPhone } = useBreakpoint()
</script>

<style scoped>
.mdb-detail { background: var(--sf-chip-bg); }
.mdb-sub { --bs-table-bg: transparent; font-size: var(--sf-fs-base); }
.mdb-sub th { font-size: var(--sf-fs-xs); color: var(--sf-text-muted); font-weight: 600; }
.mdb-md :deep(p) { margin-bottom: .4rem; }
.mdb-sec { font-weight: 700; font-size: var(--sf-fs-sm); color: var(--sf-accent-text, var(--sf-accent)); margin-bottom: .35rem; }
.mdb-bpq { max-width: 20rem; }
</style>
