<!--
  礦物參考查詢（唯讀）——掛在玩家頁 MyPlayerView 的「礦物」分頁（用 playerFetch）。
  後台的「礦物」頁是另一個東西（views/MiningView.vue：直接看礦物資料庫與中文
  對照），不用這個元件。取資料一律走 `fetcher` prop，不直接碰 api/index.js 的 miningApi。

  資料來源是 scunpacked-data（StarCitizenWiki 維護的解包資料集），由
  tasks/scdata_sync.py 定期同步，兩種東西都在裡面：

  - 礦床成分（parts）：某種礦床可能含哪些礦物、比例區間（%）、出現機率——
    右側「礦物訊號參考」用這個。
  - 單顆訊號值（signature）：船艦感測器掃到單顆這種礦床時回傳的雷達截面
    基準值（RS）。一叢礦石是這個值的整數倍（遊戲內一叢最多 10 顆），
    例如單顆 3000、掃到 3 顆一叢畫面上就會顯示 9000——左側「回波」就是
    拿玩家輸入的掃描值去反查「單顆值 × 1~10 顆」有沒有對得上。
    少數 FPS 徒手採礦專用的項目沒有這個值（船艦掃描器用不到），
    比對時會被排除。

  兩者都是**靜態**的遊戲設定值，隨改版由 scdata sync 更新，跟玩家實際
  掃描當下看到的畫面應該一致（除非該版本剛好還沒同步到）。

  礦物、礦床、地點的中文名稱都來自 src/sc_zh.py（社群翻譯包 + 少數標準地質/
  天文學術語），查不到就顯示英文名，不會讓畫面掛掉——詳見該檔案的檔頭說明。

  資料量小（目前約 270 個礦床、60 個地點群組），後端 /mining/deposits、
  /mining/locations 都是一次回全部、不分頁，左右兩側的比對/搜尋都在前端做。

  ⚠️ 右側刻意不顯示市場價格：這套系統目前沒有礦物/商品的 UEX 價格資料
  （需要設定 UEX_API_TOKEN 才能同步，且目前也還沒有對應的同步流程），
  硬做一個假數字出來會誤導玩家，所以只顯示訊號值。

  ⚠️ 同一種礦物在不同礦床/尺寸下，單顆基準訊號值常常不一樣（例如
  Hephaestanite 實際同時有 4000/4180/4210/4255/4700 好幾種）。這裡**不**
  合成單一「代表值」——訊號值本質上是「礦床尺寸/稀有度」的屬性，不是
  「礦物」的屬性，常見礦物幾乎都會被最常見的礦床尺寸吃到同一個基準值，
  選代表值等於沒有鑑別度（實測過，踩過這個坑）。改成老實列出每一筆
  真實礦床各自的資料，點開一列才展開那一列**自己的** 1~10 倍格子，
  不是綜合出來的數字。
-->
<template>
  <div class="mining-echo">
    <div class="row g-3 g-lg-4">
      <!-- ══ 左：回波（輸入掃描訊號值 → 反查礦床＋顆數）══ -->
      <div class="col-12 col-lg-6">
        <div class="mining-echo__label">
          <span>回波</span>
        </div>
        <div class="mining-echo__search mb-3">
          <i class="bi bi-search"></i>
          <input v-model="resonanceInput" type="number" min="0" step="1"
            placeholder="輸入掃描到的訊號值（RS）" aria-label="輸入掃描到的訊號值">
          <button type="button" class="btn btn-sm btn-warning mining-echo__clear"
            :disabled="resonanceInput === ''" @click="resonanceInput = ''">
            <i class="bi bi-x-lg me-1"></i>清除
          </button>
        </div>

        <div v-if="loadingDeposits" class="mining-echo__panel text-center py-4">
          <span class="spinner-border spinner-border-sm me-2"></span>載入中...
        </div>
        <div v-else-if="resonanceInput === ''" class="mining-echo__panel mining-echo__panel--empty text-center py-4">
          請輸入船艦感測器掃描到的訊號值
        </div>
        <div v-else-if="!signatureMatches.length" class="mining-echo__panel mining-echo__panel--empty text-center py-4">
          沒有礦床的「單顆訊號值 × 顆數」對得上 {{ resonanceInput }}
        </div>
        <template v-else>
          <div class="mining-echo__panel mining-echo__panel--result">
            <span class="mining-echo__pill">
              <i class="bi bi-check-lg"></i>MATCH ACQUIRED
            </span>
            <h3 class="mining-echo__title">{{ depositLabel(bestMatch) }}</h3>

            <div class="mining-echo__stats">
              <div class="mining-echo__stat">
                <div class="mining-echo__stat-label">CLUSTER SIZE</div>
                <div class="mining-echo__stat-value">{{ bestMatch.rock_count }} <small>RCKS</small></div>
              </div>
              <div class="mining-echo__stat mining-echo__stat--accent">
                <div class="mining-echo__stat-label">TARGET RS</div>
                <div class="mining-echo__stat-value">{{ fmtInt(bestMatch.expected) }} <small>SIG</small></div>
              </div>
              <div class="mining-echo__stat">
                <div class="mining-echo__stat-label">BASE RS</div>
                <div class="mining-echo__stat-value mining-echo__stat-value--ok">{{ fmtInt(bestMatch.signature) }} <small>× {{ bestMatch.rock_count }}</small></div>
              </div>
            </div>

            <!-- 可能礦物：每種一行 -->
            <div class="mining-echo__hint mb-0">
              <div>可能礦物：</div>
              <div v-for="(p, i) in bestMatch.parts || []" :key="i" class="mining-echo__part">{{ partLine(p) }}</div>
              <div v-if="!bestMatch.parts?.length">—</div>
            </div>
          </div>

          <button v-if="signatureMatches.length > 1" type="button"
            class="mining-echo__diagnostics-toggle" @click="showDiagnostics = !showDiagnostics">
            RUN FULL DIAGNOSTICS（還有 {{ signatureMatches.length - 1 }} 筆吻合）
            <i class="bi" :class="showDiagnostics ? 'bi-chevron-up' : 'bi-chevron-down'"></i>
          </button>

          <div v-show="showDiagnostics" class="mining-echo__panel mining-echo__panel--table mt-2">
            <div style="overflow-x:auto">
              <table class="table table-hover align-middle mb-0 mining-echo__table">
                <thead>
                  <tr>
                    <SortTh :sort="matchSort" field="deposit" class="ps-3">礦床</SortTh>
                    <SortTh :sort="matchSort" field="tier">Tier</SortTh>
                    <SortTh :sort="matchSort" field="rock_count">顆數</SortTh>
                    <SortTh :sort="matchSort" field="expected">對應訊號值</SortTh>
                    <SortTh :sort="matchSort" field="signature">單顆訊號值</SortTh>
                    <SortTh :sort="matchSort" field="parts" class="pe-3">可能礦物</SortTh>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(m, idx) in matchSort.sorted.value" :key="idx">
                    <td class="ps-3 fw-semibold">{{ depositLabel(m) }}</td>
                    <td>
                      <span v-if="m.tier" class="mining-echo__tag">{{ m.tier }}</span>
                      <span v-else>—</span>
                    </td>
                    <td>{{ m.rock_count }} 顆</td>
                    <td>{{ fmtInt(m.expected) }}</td>
                    <td>{{ fmtInt(m.signature) }}</td>
                    <td class="pe-3">
                      <div v-for="(p, i) in m.parts || []" :key="i" class="text-nowrap">{{ partLine(p) }}</div>
                      <span v-if="!m.parts?.length">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>

      </div>

      <!-- ══ 右：礦物訊號參考（輸入名稱 → 列出每一筆真實礦床各自的數字）══ -->
      <div class="col-12 col-lg-6">
        <div class="mining-echo__label">
          <span>礦物訊號參考</span>
        </div>
        <!-- 跟「查詢 › 持有藍圖」的名稱欄位同一套互動：打部分文字 → 下拉列出可能的礦物 →
             點選或用方向鍵＋Enter 選定，下面才顯示那一種礦物（純打字不會顯示結果） -->
        <div class="mining-echo__search mb-3">
          <i class="bi bi-search"></i>
          <input :value="mineralQuery" type="text" placeholder="輸入礦物名稱或 UEX 縮寫…"
            role="combobox" aria-autocomplete="list" aria-label="礦物名稱"
            :aria-expanded="showMineralSuggest ? 'true' : 'false'" :aria-controls="mineralListId"
            :aria-activedescendant="mineralHighlight >= 0 ? `${mineralListId}-${mineralHighlight}` : undefined"
            autocomplete="off"
            @input="onMineralInput($event.target.value)" @focus="showMineralSuggest = !!mineralQuery.trim()"
            @keydown="onMineralKeydown" @blur="onMineralBlur">
          <button type="button" class="btn btn-sm btn-warning mining-echo__clear"
            :disabled="!mineralQuery && !selectedMineralKey" @mousedown.prevent="clearMineral">
            <i class="bi bi-x-lg me-1"></i>清除
          </button>
          <ul v-if="showMineralSuggest" :id="mineralListId" role="listbox" class="mining-echo__suggest">
            <li v-if="!mineralSuggestions.length" class="mining-echo__suggest-hint">沒有符合的礦物</li>
            <li v-for="(g, i) in mineralSuggestions" v-else :id="`${mineralListId}-${i}`" :key="g.resource_key"
              role="option" :aria-selected="i === mineralHighlight"
              class="mining-echo__suggest-item" :class="{ 'is-active': i === mineralHighlight }"
              @mousedown.prevent="pickMineral(g)" @mousemove="mineralHighlight = i">
              {{ mineralLabel(g) }}<span v-if="g.uex?.code" class="mining-echo__suggest-code">{{ g.uex.code }}</span>
            </li>
          </ul>
        </div>

        <!-- 勾選後每張礦物卡片多列「包含這種礦物的礦床」（只列機率 100% 的；含量、單顆訊號值） -->
        <div class="form-check mb-3">
          <input :id="`${mineralListId}-containing`" v-model="showContaining" class="form-check-input" type="checkbox">
          <label class="form-check-label" :for="`${mineralListId}-containing`">顯示包含此礦物的礦床</label>
        </div>
        <!-- 名稱有「小行星」「礦床」的（Asteroid／Deposit）預設不列，勾了才列 -->
        <div v-if="showContaining" class="form-check mb-3 ms-4">
          <input :id="`${mineralListId}-generic`" v-model="showGenericDeposits" class="form-check-input" type="checkbox">
          <label class="form-check-label" :for="`${mineralListId}-generic`">包含小行星、礦床</label>
        </div>

        <div v-if="loadingDeposits" class="mining-echo__panel text-center py-4">
          <span class="spinner-border spinner-border-sm me-2"></span>載入中...
        </div>
        <!-- 沒有選定也沒有釘選時只顯示提示（跟左側「回波」同樣的空狀態樣式） -->
        <div v-else-if="!displayGroups.length" class="mining-echo__panel mining-echo__panel--empty text-center py-4">
          請輸入礦物名稱
        </div>
        <div v-else class="mining-echo__mineral-list">
          <!-- 釘選的礦物常駐顯示（存在這台瀏覽器），後面接目前選定、還沒釘選的那一種 -->
          <div v-for="g in displayGroups" :key="g.resource_key" class="mining-echo__panel mb-2"
            :class="{ 'mining-echo__panel--pinned': isPinned(g) }">
            <div class="d-flex align-items-start gap-2 mb-1">
            <h3 class="mining-echo__title mb-0 flex-grow-1" style="font-size: 1.05rem">
              <i v-if="isPinned(g)" class="bi bi-pin-angle-fill me-1 mining-echo__pin-icon" aria-label="已釘選"></i>
              {{ mineralLabel(g) }}
              <!-- UEX 商品縮寫（交易／價格網站用的代碼，例如 QUAN） -->
              <span v-if="g.uex?.code" class="mining-echo__tag mining-echo__tag--info ms-1" :title="`UEX：${g.uex.name || ''}`">{{ g.uex.code }}</span>
              <span v-if="ownSignatures(g)[0]?.tier" class="mining-echo__tag ms-1">{{ ownSignatures(g)[0].tier }}</span>
            </h3>
            <button type="button" class="btn btn-sm text-nowrap" :class="isPinned(g) ? 'btn-warning' : 'btn-success'"
              :aria-pressed="isPinned(g) ? 'true' : 'false'" @click="togglePin(g)">
              <i class="bi me-1" :class="isPinned(g) ? 'bi-pin-angle-fill' : 'bi-pin-angle'"></i>{{ isPinned(g) ? '取消釘選' : '釘選' }}
            </button>
            </div>
            <p v-if="locationsFor(g).length" class="mining-echo__hint mb-2">
              可能出現地點：
              <span v-for="loc in locationsFor(g)" :key="loc.system + '/' + loc.location_name"
                class="mining-echo__tag mining-echo__tag--info me-1" :title="loc.system">
                {{ locationLabel(loc) }}
              </span>
            </p>
            <template v-if="ownSignatures(g).length">
              <div class="mining-echo__hint mb-1">一叢礦石可能有 1～10 顆，掃描器讀到的整叢訊號值＝單顆 × 顆數：</div>
              <div v-for="own in ownSignatures(g)" :key="own.signature" class="mb-2">
                <!-- 極少數礦物（Carinite、Janalite）自己的礦床有兩種單顆值，才另外標出來 -->
                <div v-if="ownSignatures(g).length > 1" class="mining-echo__hint mb-1">
                  單顆 {{ fmtInt(own.signature) }}
                </div>
                <div class="mining-echo__grid">
                  <div v-for="step in signatureSteps(own.signature)" :key="step.n" class="mining-echo__cell">
                    <div class="mining-echo__cell-mult">{{ step.n }}X</div>
                    <div class="mining-echo__cell-label">SIGNATURE</div>
                    <div class="mining-echo__cell-value">{{ fmtInt(step.value) }}</div>
                  </div>
                </div>
              </div>
            </template>
            <p v-else class="mining-echo__hint mb-0">
              資料裡沒有這種礦物單獨成礦的紀錄（只以其他礦床的成分出現），沒有它自己的訊號值可以參考。
            </p>
            <!-- 精煉產量加成（UEX）：每個精煉站對這種礦物的 %，預設加成高的在前、先列 5 筆 -->
            <div v-if="refineryFor(g).length" class="mt-2">
              <div class="d-flex align-items-center gap-2 mb-1">
                <span class="mining-echo__hint">精煉產量加成（{{ refineryFor(g).length }} 個精煉站）：</span>
                <button v-if="refineryFor(g).length > REFINERY_PREVIEW" type="button" class="btn btn-sm btn-info py-0 ms-auto"
                  @click="toggleRefinery(g)">{{ refineryOpen[g.resource_key] ? '收起' : '顯示全部' }}</button>
              </div>
              <div style="overflow-x:auto">
                <table class="table table-sm align-middle mb-0 mining-echo__table">
                  <thead>
                    <tr>
                      <SortTh :sort="refinerySort" field="terminal" class="ps-2">精煉站</SortTh>
                      <SortTh :sort="refinerySort" field="system">星系</SortTh>
                      <SortTh :sort="refinerySort" field="value" class="pe-2 text-end">產量加成</SortTh>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="y in refineryRows(g)" :key="y.terminal + y.commodity">
                      <td class="ps-2">{{ y.terminal }}<span v-if="y.place && y.place !== y.terminal" class="mining-echo__hint ms-1">{{ y.place }}</span></td>
                      <td>{{ y.system || '—' }}</td>
                      <td class="pe-2 text-end fw-bold" :class="y.value > 0 ? 'mining-echo__good' : y.value < 0 ? 'mining-echo__bad' : ''">{{ fmtYield(y.value) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <!-- 精煉方式：玩家回報的精煉紀錄（UEX refineries_audits，最新遊戲版本）依方式彙整 -->
            <div v-if="methodsFor(g).length" class="mt-2">
              <div class="mining-echo__hint mb-1">
                精煉方式（玩家回報<template v-if="refineryVersion">，{{ refineryVersion }}</template>）：
              </div>
              <div style="overflow-x:auto">
                <table class="table table-sm align-middle mb-0 mining-echo__table">
                  <thead>
                    <tr>
                      <SortTh :sort="methodSort" field="method" class="ps-2">方式</SortTh>
                      <SortTh :sort="methodSort" field="yield_pct" class="text-end">產出率</SortTh>
                      <SortTh :sort="methodSort" field="cost_per_scu" class="text-end">成本／SCU</SortTh>
                      <SortTh :sort="methodSort" field="minutes_per_scu" class="text-end">時間／SCU</SortTh>
                      <SortTh :sort="methodSort" field="samples" class="pe-2 text-end">紀錄數</SortTh>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="m in methodSort.sortList(methodsFor(g))" :key="m.method">
                      <td class="ps-2">{{ m.method }}</td>
                      <td class="text-end fw-bold">{{ m.yield_pct !== null ? `${m.yield_pct}%` : '—' }}</td>
                      <td class="text-end">{{ m.cost_per_scu !== null ? `${Number(m.cost_per_scu.toFixed(1)).toLocaleString('en-US')} aUEC` : '—' }}</td>
                      <td class="text-end">{{ fmtMinutes(m.minutes_per_scu) }}</td>
                      <td class="pe-2 text-end">{{ m.samples }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <!-- 精煉試算（這張卡片的礦物）：原礦量 × 方式產出率 ×（1＋站點加成）；成本／時間用每 SCU 的平均 -->
            <div v-for="rv in [refineView(g)]" v-show="rv.methods.length" :key="rv.base" class="mining-echo__refine mt-3">
              <div class="mining-echo__hint fw-semibold mb-2">精煉試算</div>
              <div class="row g-2 align-items-end">
                <div class="col-12 col-sm-6">
                  <label class="mining-echo__hint mb-1 d-block" :for="`${mineralListId}-${rv.base}-rf-station`">精煉站</label>
                  <select :id="`${mineralListId}-${rv.base}-rf-station`" :value="rv.station" class="form-select form-select-sm"
                    @change="setRefine(rv.base, { station: $event.target.value })">
                    <option value="">不指定（加成 0%）</option>
                    <option v-for="y in rv.stations" :key="y.terminal" :value="y.terminal">{{ y.terminal }}（{{ fmtYield(y.value) }}）</option>
                  </select>
                </div>
                <div class="col-12 col-sm-6">
                  <label class="mining-echo__hint mb-1 d-block" :for="`${mineralListId}-${rv.base}-rf-method`">精煉方式</label>
                  <select :id="`${mineralListId}-${rv.base}-rf-method`" :value="rv.method" class="form-select form-select-sm"
                    @change="setRefine(rv.base, { method: $event.target.value })">
                    <option v-for="m in rv.methods" :key="m.method" :value="m.method">{{ m.method }}（{{ m.yield_pct }}%）</option>
                  </select>
                </div>
                <div class="col-12">
                  <label class="mining-echo__hint mb-1 d-block" :for="`${mineralListId}-${rv.base}-rf-qty`">原礦量</label>
                  <div class="d-flex align-items-center gap-2">
                    <input :value="rv.qty" type="range" class="flex-grow-1 mining-echo__range" min="1" :max="REFINE_SLIDER_MAX" step="1"
                      :style="{ '--me-fill': `${Math.min(rv.qty, REFINE_SLIDER_MAX) / REFINE_SLIDER_MAX * 100}%` }"
                      aria-label="原礦量（拉條）" @input="setRefine(rv.base, { qty: Number($event.target.value) })">
                    <input :id="`${mineralListId}-${rv.base}-rf-qty`" :value="rv.qty" type="number" class="form-control form-control-sm mining-echo__qty"
                      min="0" :max="REFINE_QTY_MAX" step="any"
                      @change="setRefine(rv.base, { qty: clampRefineQty($event.target.value) }); $event.target.value = refineView(g).qty">
                    <span class="mining-echo__hint">SCU</span>
                  </div>
                </div>
              </div>

              <div v-if="rv.result" class="mining-echo__stats mt-3">
                <div class="mining-echo__stat mining-echo__stat--accent">
                  <div class="mining-echo__stat-label">預估產出</div>
                  <div class="mining-echo__stat-value">{{ fmtScu(rv.result.output) }} <small>SCU</small></div>
                </div>
                <div class="mining-echo__stat">
                  <div class="mining-echo__stat-label">預估成本</div>
                  <div class="mining-echo__stat-value">{{ rv.result.cost !== null ? fmtInt(rv.result.cost) : '—' }} <small v-if="rv.result.cost !== null">aUEC</small></div>
                </div>
                <div class="mining-echo__stat">
                  <div class="mining-echo__stat-label">預估時間</div>
                  <div class="mining-echo__stat-value">{{ fmtDuration(rv.result.minutes) }}</div>
                </div>
              </div>

              <!-- 所有「站點 × 方式」組合，預設產出多的在前（點欄位名稱排序），先列 10 筆；點一列就套用 -->
              <div v-if="rv.combos.length" class="mt-3">
                <div class="d-flex align-items-center gap-2 mb-1">
                  <span class="mining-echo__hint">站點 × 方式組合（{{ rv.combos.length }}）：</span>
                  <button v-if="rv.combos.length > COMBO_PREVIEW" type="button" class="btn btn-sm btn-info py-0 ms-auto"
                    @click="setRefine(rv.base, { open: !rv.open })">{{ rv.open ? '收起' : '顯示全部' }}</button>
                </div>
                <div style="overflow-x:auto">
                  <table class="table table-sm align-middle mb-0 mining-echo__table">
                    <thead>
                      <tr>
                        <SortTh :sort="comboSort" field="station" class="ps-2">精煉站</SortTh>
                        <SortTh :sort="comboSort" field="method">方式</SortTh>
                        <SortTh :sort="comboSort" field="output" class="text-end">產出</SortTh>
                        <SortTh :sort="comboSort" field="cost" class="text-end">成本</SortTh>
                        <SortTh :sort="comboSort" field="minutes" class="pe-2 text-end">時間</SortTh>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="c in rv.comboRows" :key="c.station + '|' + c.method"
                        :class="{ 'mining-echo__row--picked': c.station === rv.station && c.method === rv.method }"
                        role="button" @click="setRefine(rv.base, { station: c.station, method: c.method })">
                        <td class="ps-2">{{ c.station || '不指定' }}<span v-if="c.bonus" class="ms-1" :class="c.bonus > 0 ? 'mining-echo__good' : 'mining-echo__bad'">{{ fmtYield(c.bonus) }}</span></td>
                        <td>{{ c.method }}</td>
                        <td class="text-end fw-bold">{{ fmtScu(c.output) }} SCU</td>
                        <td class="text-end">{{ c.cost !== null ? `${fmtInt(c.cost)} aUEC` : '—' }}</td>
                        <td class="pe-2 text-end">{{ fmtDuration(c.minutes) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <p class="mining-echo__footnote mt-2 mb-0">
                產出率、成本、時間是玩家回報紀錄的平均<template v-if="refineryVersion">（{{ refineryVersion }}）</template>，站點加成來自 UEX，實際結果會有落差。
              </p>
            </div>
            <!-- 包含這種礦物的礦床（勾選「顯示包含此礦物的礦床」才列） -->
            <div v-if="showContaining" class="mt-2">
              <div class="mining-echo__hint mb-1">包含這種礦物的礦床（機率 100%，{{ containingDeposits(g).length }}）：</div>
              <div v-if="!containingDeposits(g).length" class="mining-echo__hint">—</div>
              <div v-else style="overflow-x:auto">
                <table class="table table-sm align-middle mb-0 mining-echo__table">
                  <thead>
                    <tr>
                      <SortTh :sort="containSort" field="deposit" class="ps-2">礦床</SortTh>
                      <SortTh :sort="containSort" field="tier">Tier</SortTh>
                      <SortTh :sort="containSort" field="range">含量</SortTh>
                      <SortTh :sort="containSort" field="signature" class="pe-2 text-end">單顆訊號值</SortTh>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="d in containSort.sortList(containingDeposits(g))" :key="d.key">
                      <td class="ps-2">{{ depositLabel(d) }}</td>
                      <td><span v-if="d.tier" class="mining-echo__tag">{{ d.tier }}</span><span v-else>—</span></td>
                      <td class="text-nowrap">{{ fmtRange(d.min_percentage, d.max_percentage) }}</td>
                      <td class="pe-2 text-end">{{ fmtInt(d.signature) }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, reactive, watch } from 'vue'
import SortTh from '@/components/SortTh.vue'
import { useTableSort } from '@/composables/useTableSort'
import { mineralBaseName, ownSignatures as mineralOwnSignatures } from '@/utils/miningSignature'

const props = defineProps({
  /** 帶身分的 fetch（後台用 apiFetch、玩家頁用 playerFetch），回傳 Response 或 null */
  fetcher: { type: Function, required: true },
  /**
   * 是否為目前可見的分頁。玩家頁的分頁全部用 v-show（切分頁不重新掛載，
   * 保留使用者輸入到一半的內容），代表這個元件在玩家一進頁面時就已經
   * 掛載了——如果 onMounted 就無條件打兩支 API，等於每個玩家每次開
   * 個人頁都會抓一份礦物參考表，即使他根本沒點進「礦物」分頁。
   * 所以資料改成「第一次變成可見時才載入」，之後切走再切回來不重載。
   * 預設值 true（獨立頁面掛載時一進頁就載入）。
   */
  active: { type: Boolean, default: true },
})

// ── 資料載入（第一次 active 變 true 時才載入一次）───────────────────
const deposits = ref([])
// 精煉站產量加成（UEX）：[{base, commodity, terminal, place, system, value}]，base＝去掉 (Ore)／(Raw) 的小寫名稱
const refineryYields = ref([])
// 精煉方式（玩家回報紀錄彙整）：[{base, commodity, method, samples, yield_pct, cost_per_scu, minutes_per_scu}]
const refineryMethodRows = ref([])
const refineryVersion = ref('')
const locations = ref([])
const loadingDeposits = ref(false)
let loaded = false

async function loadData() {
  if (loaded) return
  loaded = true
  loadingDeposits.value = true
  try {
    const [depRes, locRes, yieldRes, methodRes] = await Promise.all([
      props.fetcher('/mining/deposits'),
      props.fetcher('/mining/locations'),
      props.fetcher('/mining/refinery-yields'),
      props.fetcher('/mining/refinery-methods'),
    ])
    const methodData = methodRes ? await methodRes.json().catch(() => null) : null
    refineryMethodRows.value = methodData?.success ? (methodData.data?.rows || []) : []
    refineryVersion.value = methodData?.success ? (methodData.data?.version || '') : ''
    const yieldData = yieldRes ? await yieldRes.json().catch(() => null) : null
    refineryYields.value = yieldData?.success ? (yieldData.data || []) : []
    const depData = depRes ? await depRes.json().catch(() => null) : null
    deposits.value = depData?.success ? (depData.data || []) : []
    const locData = locRes ? await locRes.json().catch(() => null) : null
    locations.value = locData?.success ? (locData.data || []) : []
  } finally {
    loadingDeposits.value = false
  }
}

watch(() => props.active, (v) => { if (v) loadData() }, { immediate: true })

// ── 共用：把所有礦床的成分攤平成一份清單，帶著所屬礦床脈絡 ──────────
const flatParts = computed(() => {
  const rows = []
  for (const d of deposits.value) {
    for (const p of (d.parts || [])) {
      rows.push({
        deposit_id: d._id, deposit_name: d.deposit_name, deposit_name_zh: d.deposit_name_zh,
        tier: d.tier, signature: d.signature,
        resource_key: p.resource_key, resource_name: p.resource_name,
        resource_name_zh: p.resource_name_zh, uex: p.uex,
        min_percentage: p.min_percentage, max_percentage: p.max_percentage,
        probability: p.probability,
      })
    }
  }
  return rows
})

function mineralLabel(p) {
  if (p.resource_name_zh) return `${p.resource_name_zh}（${p.resource_name || p.resource_key}）`
  return p.resource_name || p.resource_key
}

// 「其他可能」表格（第一筆是最佳結果，另外顯示）
const otherMatches = computed(() => signatureMatches.value.slice(1))
const matchSort = useTableSort(otherMatches, { accessors: {
  deposit: m => depositLabel(m), parts: m => partsSummary(m.parts),
} })

function depositLabel(d) {
  if (d.deposit_name_zh) return `${d.deposit_name_zh}（${d.deposit_name}）`
  return d.deposit_name
}

function locationLabel(loc) {
  if (loc.location_name_zh) return `${loc.location_name_zh}（${loc.location_name}）`
  return loc.location_name
}

function fmtRange(min, max) {
  if (min === null || min === undefined || max === null || max === undefined) return '—'
  return `${min}–${max}%`
}

function fmtInt(v) {
  if (v === null || v === undefined) return '—'
  return Math.round(v).toLocaleString('en-US')
}

/** 可能礦物的一行：「中文（English）10–30%」 */
function partLine(p) {
  return `${mineralLabel(p)} ${fmtRange(p.min_percentage, p.max_percentage)}`
}

function partsSummary(parts) {
  if (!parts || !parts.length) return '—'
  return parts.map(p => {
    const label = mineralLabel(p)
    const range = fmtRange(p.min_percentage, p.max_percentage)
    return `${label} ${range}`
  }).join('、')
}

// ── 左：回波 —— 輸入船艦掃描訊號值 → 反查「單顆基準值 × 1~10 顆」───────
//
// 遊戲內一叢礦石最多 10 顆，掃描器回傳的整叢訊號值（RS）是「單顆基準值 × 顆數」
// 的整數倍（例如鐵礦單顆 4,270，兩顆 8,540）——確定性的算式，不是有 ± 誤差的範圍，
// 所以只列「剛好等於」的組合（只容許 0.5 以內的小數捨入）。
const SIGNATURE_ROUNDING = 0.5

const resonanceInput = ref('')

// 使用者改輸入值時，先前展開的完整診斷區塊沒必要留著（結果已經不一樣了）。
const showDiagnostics = ref(false)
watch(resonanceInput, () => { showDiagnostics.value = false })

const signatureMatches = computed(() => {
  const v = parseFloat(resonanceInput.value)
  if (!v || Number.isNaN(v) || v <= 0) return []

  const seen = new Set()
  const matches = []
  for (const d of deposits.value) {
    const sig = d.signature
    if (!sig || sig <= 0) continue
    // 同一種礦床在資料集裡常常有好幾個變體（一般/大顆/小顆模型），
    // 成分與單顆訊號值完全一樣——用「礦床名稱＋Tier＋顆數」去重，
    // 不然畫面會出現好幾筆一模一樣的結果。
    const dedupeKey = `${d.deposit_name}__${d.tier}`
    for (let n = 1; n <= 10; n++) {
      const expected = sig * n
      if (Math.abs(v - expected) > SIGNATURE_ROUNDING) continue
      const key = `${dedupeKey}__${n}`
      if (seen.has(key)) continue
      seen.add(key)
      matches.push({
        deposit_name: d.deposit_name, deposit_name_zh: d.deposit_name_zh,
        tier: d.tier, rock_count: n, signature: sig,
        expected, parts: d.parts,
      })
    }
  }
  // 都是剛好吻合；顆數少的在前（一叢 2 顆比 8 顆常見），同顆數照礦床名稱
  matches.sort((a, b) => a.rock_count - b.rock_count
    || (a.deposit_name || '').localeCompare(b.deposit_name || ''))
  return matches
})

// 排序後的第一筆（顆數最少的吻合）放主結果卡。
const bestMatch = computed(() => signatureMatches.value[0] || null)

// ── 右：礦物訊號參考 —— 輸入名稱（中/英皆可）→ 依礦物分組列出礦床明細 ─
//
// 刻意不合成單一「代表值」：訊號值本質上是「礦床尺寸/稀有度」的屬性，
// 不是「礦物」的屬性，常見礦物在最常見的礦床尺寸下幾乎都收斂到同一個
// 基準值，選代表值等於沒有鑑別度（實測踩過這個坑）。所以這裡老實列出
// 「這種礦物」底下每一筆真實存在的礦床，各自的 tier／比例／機率／
// 單顆訊號值都是資料庫裡真實的那一筆，一個都沒有被合併或統計過。
const mineralQuery = ref('')

const mineralGroups = computed(() => {
  const byKey = new Map()
  for (const p of flatParts.value) {
    if (!byKey.has(p.resource_key)) {
      byKey.set(p.resource_key, {
        resource_key: p.resource_key, resource_name: p.resource_name,
        resource_name_zh: p.resource_name_zh, uex: p.uex, deposits: [],
      })
    }
    byKey.get(p.resource_key).deposits.push(p)
  }
  return Array.from(byKey.values())
    // 資料集裡還沒補名字的佔位項目（"<= PLACEHOLDER =>"）不列出
    .filter(g => !(g.resource_name || '').includes('PLACEHOLDER'))
    .sort((a, b) => mineralLabel(a).localeCompare(mineralLabel(b), 'zh-Hant'))
})

// 名稱欄位的候選：子字串「包含」比對（中文、英文、resource key、UEX 縮寫），最多列 20 筆。
// 開頭就對上的排前面，比較接近輸入的意思（打「Ti」先出 Titanium 而不是 Hephaestanite）。
const MINERAL_SUGGEST_MAX = 20
const mineralListId = `mining-mineral-${Math.random().toString(36).slice(2, 8)}`
const selectedMineralKey = ref('')
const showMineralSuggest = ref(false)
const mineralHighlight = ref(-1)

const mineralSuggestions = computed(() => {
  const raw = mineralQuery.value.trim()
  if (!raw) return []
  const q = raw.toLowerCase()
  const fields = g => [(g.resource_name || '').toLowerCase(), g.resource_name_zh || '',
    (g.resource_key || '').toLowerCase(), (g.uex?.code || '').toLowerCase()]
  return mineralGroups.value
    .filter(g => fields(g).some(f => f.includes(q) || f.includes(raw)))
    .map(g => ({ g, starts: fields(g).some(f => f.startsWith(q) || f.startsWith(raw)) }))
    .sort((a, b) => Number(b.starts) - Number(a.starts))
    .slice(0, MINERAL_SUGGEST_MAX)
    .map(x => x.g)
})

// 下面只顯示選定的那一種礦物；純打字（還沒選）不顯示結果
const filteredMineralGroups = computed(() =>
  mineralGroups.value.filter(g => g.resource_key === selectedMineralKey.value))

// ── 釘選：好幾種礦物常駐顯示（存在這台瀏覽器的 localStorage；讀寫失敗就只在這次有效）──
const PIN_KEY = 'sc_mining_pinned_minerals'
const CONTAINING_KEY = 'sc_mining_show_containing'
const PIN_MAX = 20
function readStore(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    return raw === null ? fallback : JSON.parse(raw)
  } catch { return fallback }
}
function writeStore(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)) } catch { /* 私密視窗等情況存不了，忽略 */ }
}
const storedPins = readStore(PIN_KEY, [])
const pinnedKeys = ref(Array.isArray(storedPins) ? storedPins.filter(k => typeof k === 'string').slice(0, PIN_MAX) : [])
watch(pinnedKeys, v => writeStore(PIN_KEY, v), { deep: true })
const showContaining = ref(readStore(CONTAINING_KEY, false) === true)
watch(showContaining, v => writeStore(CONTAINING_KEY, v))
const GENERIC_KEY = 'sc_mining_show_generic_deposits'
const showGenericDeposits = ref(readStore(GENERIC_KEY, false) === true)
watch(showGenericDeposits, v => writeStore(GENERIC_KEY, v))
// 名稱有「小行星」「礦床」的礦床（英文 Asteroid／Deposit）：預設不列在「包含這種礦物的礦床」
const GENERIC_DEPOSIT_RE = /小行星|礦床|asteroid|deposit/i
function isGenericDeposit(d) {
  return GENERIC_DEPOSIT_RE.test(`${d.deposit_name_zh || ''} ${d.deposit_name || ''}`)
}

function isPinned(g) { return pinnedKeys.value.includes(g.resource_key) }
function togglePin(g) {
  if (isPinned(g)) pinnedKeys.value = pinnedKeys.value.filter(k => k !== g.resource_key)
  else pinnedKeys.value = [...pinnedKeys.value, g.resource_key].slice(-PIN_MAX)
}
// 釘選的（照釘選順序）＋目前選定但還沒釘選的
const displayGroups = computed(() => {
  const byKey = new Map(mineralGroups.value.map(g => [g.resource_key, g]))
  const out = pinnedKeys.value.map(k => byKey.get(k)).filter(Boolean)
  for (const g of filteredMineralGroups.value) if (!isPinned(g)) out.push(g)
  return out
})

// ── 精煉產量加成：用礦物英文名去掉 (Ore)／(Raw)／Raw 前綴後對 UEX 商品名稱（後端 base 欄位同規則）──
const REFINERY_PREVIEW = 5
const refineryOpen = reactive({})
const refineryByBase = computed(() => {
  const map = new Map()
  for (const y of refineryYields.value) {
    if (!map.has(y.base)) map.set(y.base, [])
    map.get(y.base).push(y)
  }
  return map
})
function refineryFor(group) {
  return refineryByBase.value.get(mineralBaseName(group.resource_name)) || []
}
const refinerySort = useTableSort(null, { key: 'value', dir: 'desc' })
function refineryRows(group) {
  const rows = refinerySort.sortList(refineryFor(group))
  return refineryOpen[group.resource_key] ? rows : rows.slice(0, REFINERY_PREVIEW)
}
function toggleRefinery(group) {
  refineryOpen[group.resource_key] = !refineryOpen[group.resource_key]
}
const methodByBase = computed(() => {
  const map = new Map()
  for (const m of refineryMethodRows.value) {
    if (!map.has(m.base)) map.set(m.base, [])
    map.get(m.base).push(m)
  }
  return map
})
function methodsFor(group) {
  return methodByBase.value.get(mineralBaseName(group.resource_name)) || []
}
const methodSort = useTableSort(null, { key: 'yield_pct', dir: 'desc' })

// ── 精煉試算（每張礦物卡片各自一組）：選精煉站、方式，輸入原礦量 ──────────────
//    產出 = 原礦量 × 方式產出率 ×（1 + 站點加成）；成本、時間 = 原礦量 × 每 SCU 平均（站點不影響）
//    沒選過就用「產出率最高的方式」＋「加成最高的站」；選過的存在 refineState[base]
const REFINE_SLIDER_MAX = 1000
const REFINE_QTY_MAX = 100000
const COMBO_PREVIEW = 10
const REFINE_DEFAULT_QTY = 100
const refineState = reactive({})
function setRefine(base, patch) {
  refineState[base] = { ...(refineState[base] || {}), ...patch }
}
const comboSort = useTableSort(null, { key: 'output', dir: 'desc' })

function calcRefine(qty, method, bonus) {
  return {
    output: qty * (method.yield_pct / 100) * (1 + (bonus || 0) / 100),
    cost: method.cost_per_scu !== null ? qty * method.cost_per_scu : null,
    minutes: method.minutes_per_scu !== null ? qty * method.minutes_per_scu : null,
  }
}
function refineView(group) {
  const base = mineralBaseName(group.resource_name)
  const st = refineState[base] || {}
  const methods = methodsFor(group).filter(m => m.yield_pct !== null).slice().sort((a, b) => b.yield_pct - a.yield_pct)
  const stations = refineryFor(group).slice().sort((a, b) => b.value - a.value)
  const method = methods.some(m => m.method === st.method) ? st.method : (methods[0]?.method || '')
  const station = st.station === '' || stations.some(y => y.terminal === st.station) ? st.station : (stations[0]?.terminal || '')
  const qty = st.qty ?? REFINE_DEFAULT_QTY
  const picked = methods.find(m => m.method === method)
  const result = picked ? calcRefine(qty, picked, stations.find(y => y.terminal === station)?.value) : null
  const combos = []
  for (const s of (stations.length ? stations : [{ terminal: '', value: 0 }])) {
    for (const m of methods) combos.push({ station: s.terminal, bonus: s.value, method: m.method, ...calcRefine(qty, m, s.value) })
  }
  const sortedCombos = comboSort.sortList(combos)
  const open = !!st.open
  return { base, methods, stations, method, station, qty, result, combos, open,
    comboRows: open ? sortedCombos : sortedCombos.slice(0, COMBO_PREVIEW) }
}

function clampRefineQty(value) {
  const v = Number(value)
  if (Number.isNaN(v) || v < 0) return 0
  return Math.min(REFINE_QTY_MAX, v)
}
function fmtScu(v) {
  if (v === null || v === undefined) return '—'
  return Number(v.toFixed(2)).toLocaleString('en-US')
}
function fmtDuration(minutes) {
  if (minutes === null || minutes === undefined) return '—'
  if (minutes < 1) return `${Math.round(minutes * 60)} 秒`
  if (minutes < 60) return `${Math.round(minutes)} 分`
  const h = Math.floor(minutes / 60)
  return `${h} 時 ${Math.round(minutes - h * 60)} 分`
}
function fmtMinutes(m) {
  if (m === null || m === undefined) return '—'
  return m < 1 ? `${Math.round(m * 60)} 秒` : `${Number(m.toFixed(1))} 分`
}

function fmtYield(v) {
  if (v === null || v === undefined) return '—'
  return `${v > 0 ? '+' : ''}${Number(v.toFixed(1))}%`
}

// ── 包含這種礦物的礦床：只列機率 100%（這種礦床一定含有這種礦物）的那幾筆，
//    同名同 Tier 同數字的變體去重 ──
function containingDeposits(group) {
  const seen = new Set()
  const rows = []
  for (const d of group.deposits) {
    if (!(d.probability >= 1)) continue
    if (!showGenericDeposits.value && isGenericDeposit(d)) continue
    const key = [d.deposit_name, d.tier, d.signature, d.min_percentage, d.max_percentage, d.probability].join('|')
    if (seen.has(key)) continue
    seen.add(key)
    rows.push({ ...d, key })
  }
  return rows.sort((a, b) => (b.max_percentage || 0) - (a.max_percentage || 0)
    || depositLabel(a).localeCompare(depositLabel(b), 'zh-Hant'))
}
const containSort = useTableSort(null, { accessors: {
  deposit: d => depositLabel(d), range: d => d.max_percentage,
} })


function onMineralInput(value) {
  mineralQuery.value = value
  selectedMineralKey.value = ''   // 文字改了就撤銷上一次的選定
  mineralHighlight.value = -1
  showMineralSuggest.value = !!value.trim()
}

function pickMineral(g) {
  if (!g) return
  mineralQuery.value = mineralLabel(g)
  selectedMineralKey.value = g.resource_key
  showMineralSuggest.value = false
}

function clearMineral() {
  mineralQuery.value = ''
  selectedMineralKey.value = ''
  showMineralSuggest.value = false
}

function onMineralKeydown(event) {
  if (event.key === 'Escape') { showMineralSuggest.value = false; return }
  const list = mineralSuggestions.value
  if (!showMineralSuggest.value || !list.length) return
  if (event.key === 'ArrowDown') {
    event.preventDefault()
    mineralHighlight.value = (mineralHighlight.value + 1) % list.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    mineralHighlight.value = mineralHighlight.value <= 0 ? list.length - 1 : mineralHighlight.value - 1
  } else if (event.key === 'Enter') {
    event.preventDefault()
    pickMineral(list[mineralHighlight.value >= 0 ? mineralHighlight.value : 0])
  }
}

function onMineralBlur() {
  // 延遲關閉，讓候選的 mousedown 先選定（跟 AutocompleteField.vue 同樣的理由）
  setTimeout(() => { showMineralSuggest.value = false }, 120)
}

// 每種礦物「自己那個礦床」的單顆訊號值 —— 礦床名稱跟礦物名稱相同的那一筆
// （例如「Hephaestanite (R)」礦床，成分 100% 是 Hephaestanite），也就是
// 掃描器掃到一顆純的這種礦石時讀到的值。其他礦床（Shale／Gneiss／小行星…）
// 的訊號值是那個礦床本身的屬性，跟「查的是哪種礦物」無關，列出來只會讓
// 畫面變成一長串幾乎都是 4000 的數字，所以不顯示。
//
// 同名礦床常有好幾筆（成分比例區間不同的變體），但單顆訊號值相同，依值去重；
// 真的有兩種值的（Carinite、Janalite：3000／4000）兩組都列。
// 名稱寫法不一致的（Stileron (Ore) ↔ Stileron、Raw Ouratite ↔ Ouratite）
// 由 utils/miningSignature.js 處理，後台礦物資料庫頁共用同一份。
function ownSignatures(group) {
  return mineralOwnSignatures(group.resource_name, group.deposits)
}

/** 單顆訊號值 × 1~10 顆（整叢掃描值），用的是礦物自己礦床的真實值，不是合成的。 */
function signatureSteps(signature) {
  return Array.from({ length: 10 }, (_, i) => ({ n: i + 1, value: signature * (i + 1) }))
}

function locationsFor(group) {
  const depositIds = new Set(group.deposits.map(d => d.deposit_id))
  const seen = new Set()
  const result = []
  for (const loc of locations.value) {
    if (!loc.location_name) continue
    let hit = false
    for (const g of (loc.groups || [])) {
      for (const dep of (g.deposits || [])) {
        if (depositIds.has(dep.resource_uuid)) { hit = true; break }
      }
      if (hit) break
    }
    if (!hit) continue
    const key = `${loc.system}/${loc.location_name}`
    if (seen.has(key)) continue
    seen.add(key)
    result.push({ system: loc.system, location_name: loc.location_name, location_name_zh: loc.location_name_zh })
  }
  return result.sort((a, b) => (a.system || '').localeCompare(b.system || '') || a.location_name.localeCompare(b.location_name))
}
</script>

<style scoped>
/* 「終端機」風格的卡片：版面自成一體，但顏色跟著網站主題（--sf-*）。 */
.mining-echo {
  /* 顏色一律取網站主題（assets/scifi-theme.css 的 --sf-*），換強調色、切亮底會跟著變 */
  --me-bg: var(--sf-bg-2);
  --me-panel: var(--sf-panel);
  --me-border: rgba(var(--sf-accent-rgb), .35);
  --me-border-hi: rgba(var(--sf-accent-rgb), .7);
  --me-accent: var(--sf-accent);
  --me-text: var(--sf-text);
  --me-text-dim: var(--sf-text-muted);
  font-variant-numeric: tabular-nums;
}

.mining-echo__label {
  display: flex;
  align-items: center;
  gap: .5rem;
  font-size: .78rem;
  font-weight: 700;
  letter-spacing: .12em;
  color: var(--me-accent);
  margin-bottom: .6rem;
}
.mining-echo__label::before,
.mining-echo__label::after {
  content: '';
  flex: 1 1 auto;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--me-border-hi), transparent);
}

.mining-echo__search {
  position: relative;
  display: flex;
  align-items: center;
  gap: .5rem;
  background: var(--me-panel);
  border: 1px solid var(--me-border);
  border-radius: .4rem;
  padding: .55rem .75rem;
  color: var(--me-text);
}
.mining-echo__search > i:first-child { color: var(--me-accent); }
.mining-echo__search input {
  flex: 1 1 auto;
  min-width: 0;
  background: transparent;
  border: 0;
  color: var(--me-text);
  font-weight: 600;
  outline: none;
}
.mining-echo__search input::placeholder { color: var(--me-text-dim); }
.mining-echo__chevron { color: var(--me-text-dim); }
/* 搜尋框右側的「清除」按鈕（btn-warning，配色由 scifi-theme.css 統一） */
.mining-echo__clear {
  flex: 0 0 auto;
  white-space: nowrap;
  font-size: 1rem;
}

.mining-echo__suggest {
  position: absolute;
  z-index: 30;
  top: calc(100% + .25rem);
  left: 0;
  right: 0;
  max-height: 16rem;
  overflow-y: auto;
  margin: 0;
  padding: .3rem;
  list-style: none;
  background: var(--me-panel);
  border: 1px solid var(--me-border);
  border-radius: .4rem;
  box-shadow: 0 .5rem 1.2rem var(--sf-shadow);
}
.mining-echo__suggest-item {
  padding: .4rem .6rem;
  border-radius: .3rem;
  cursor: pointer;
  color: var(--me-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mining-echo__suggest-item:hover,
.mining-echo__suggest-item.is-active { background: rgba(var(--sf-accent-rgb), .12); }
.mining-echo__suggest-code { margin-left: .5rem; color: var(--me-accent); font-family: var(--bs-font-monospace); font-size: .9em; }
.mining-echo__suggest-hint {
  padding: .4rem .6rem;
  color: var(--me-text-dim);
  font-size: .85em;
}

.mining-echo__panel {
  background: var(--me-panel);
  border: 1px solid var(--me-border);
  border-radius: .5rem;
  color: var(--me-text);
  padding: 1.1rem 1.25rem;
}
.mining-echo__panel--empty { color: var(--me-text-dim); }
.mining-echo__refine { border-top: 1px dashed var(--me-border); padding-top: 0.75rem; }
.mining-echo__panel--result { border-color: var(--me-border-hi); }
.mining-echo__panel--table { padding: 0; }
.mining-echo__panel--table table { color: var(--me-text); }

.mining-echo__pill {
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .08em;
  color: var(--me-accent);
  background: rgba(var(--sf-accent-rgb), .12);
  border: 1px solid var(--me-border);
  border-radius: .3rem;
  padding: .25rem .55rem;
  margin-bottom: .75rem;
}
.mining-echo__pill--muted {
  color: var(--me-text-dim);
  background: var(--sf-hover-bg);
}

.mining-echo__title {
  font-weight: 800;
  letter-spacing: .02em;
  margin-bottom: 1rem;
  word-break: break-word;
}

.mining-echo__stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .6rem;
  margin-bottom: .75rem;
}
.mining-echo__stat {
  background: var(--sf-inset);
  border: 1px solid var(--me-border);
  border-radius: .4rem;
  padding: .6rem .5rem;
  text-align: center;
}
.mining-echo__stat--accent { border-color: var(--me-border-hi); }
.mining-echo__stat-label {
  font-size: .68rem;
  letter-spacing: .08em;
  color: var(--me-text-dim);
  margin-bottom: .2rem;
}
.mining-echo__stat-value {
  font-size: 1.35rem;
  font-weight: 800;
}
.mining-echo__stat-value small { font-size: .6em; font-weight: 600; opacity: .75; }
.mining-echo__stat-value--ok { color: rgb(var(--bs-success-rgb)); }

.mining-echo__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .5rem;
  margin-bottom: .75rem;
}
@media (min-width: 400px) {
  .mining-echo__grid { grid-template-columns: repeat(5, minmax(0, 1fr)); }
}
.mining-echo__cell {
  background: var(--sf-inset);
  border: 1px solid var(--me-border);
  border-radius: .4rem;
  padding: .5rem .4rem;
  text-align: center;
}
.mining-echo__cell-mult {
  position: absolute;
  font-size: .65rem;
  font-weight: 700;
  color: var(--me-text-dim);
}
.mining-echo__cell { position: relative; }
.mining-echo__cell-mult { top: .3rem; right: .4rem; }
.mining-echo__cell-label {
  font-size: .6rem;
  letter-spacing: .06em;
  color: var(--me-text-dim);
  margin-top: .6rem;
}
.mining-echo__cell-value {
  font-size: 1.05rem;
  font-weight: 800;
}

.mining-echo__hint { color: var(--me-text-dim); font-size: .85rem; }
.mining-echo__footnote {
  color: var(--me-text-dim);
  font-size: .78rem;
  opacity: .85;
  margin-top: .6rem;
}

.mining-echo__diagnostics-toggle {
  width: 100%;
  background: var(--me-panel);
  border: 1px dashed var(--me-border);
  border-radius: .4rem;
  color: var(--me-text-dim);
  font-size: .78rem;
  letter-spacing: .04em;
  padding: .5rem .75rem;
  margin-top: .6rem;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: .4rem;
}
.mining-echo__diagnostics-toggle:hover { color: var(--me-text); border-color: var(--me-border-hi); }

.mining-echo__tag {
  display: inline-block;
  font-size: .72rem;
  background: var(--sf-chip-bg);
  border: 1px solid var(--me-border);
  border-radius: .25rem;
  padding: .05rem .4rem;
}
.mining-echo__tag--info { color: var(--me-accent); }

.mining-echo__table thead th {
  color: var(--me-text-dim);
  font-size: .72rem;
  letter-spacing: .05em;
  border-bottom-color: var(--me-border);
  background: transparent;
}
.mining-echo__table tbody td {
  border-color: var(--me-border);
  font-size: .85rem;
}
.mining-echo__table tbody tr:hover { background: rgba(var(--sf-accent-rgb), .06); }
.mining-echo__part { padding-left: .75rem; }
.mining-echo__panel--pinned { border-color: var(--me-border-hi); }
.mining-echo__pin-icon { color: var(--me-accent); }
.mining-echo__good { color: var(--bs-success) !important; }
.mining-echo__bad { color: var(--bs-danger) !important; }
.mining-echo__qty { width: 7rem; }
.mining-echo__row--picked td { background: rgba(var(--sf-accent-rgb), .12); }
.mining-echo__table tbody tr[role="button"] { cursor: pointer; }
.mining-echo__range {
  -webkit-appearance: none; appearance: none; height: .45rem; border-radius: 999px; cursor: pointer;
  background: linear-gradient(to right, var(--me-accent) var(--me-fill, 10%), var(--me-border) var(--me-fill, 10%));
}
.mining-echo__range::-webkit-slider-thumb {
  -webkit-appearance: none; width: 1.1rem; height: 1.1rem; border-radius: 50%;
  background: var(--me-accent); border: 2px solid var(--sf-text-strong);
}
.mining-echo__range::-moz-range-thumb {
  width: 1.1rem; height: 1.1rem; border-radius: 50%; background: var(--me-accent); border: 2px solid var(--sf-text-strong);
}
</style>
