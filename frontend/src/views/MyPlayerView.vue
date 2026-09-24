<!--
  玩家個人頁（需要玩家登入，不是後台登入）。滿版版面，4 個主分頁：

  - 倉庫（我自己的物品，看現況也在這裡動）
      · 物品庫存：目前登記了哪些物品。上方有篩選區（物品／地點，預設全部）
      · 新增：一次登記多筆「還沒有的物品」
      · 庫存異動：對已登記的物品增減數量，每列各自可選「＋增加」或「－減少」
      · 庫存紀錄：增加／減少的歷史。上方同樣有篩選區
  - 藍圖：自己的藍圖名冊，可增刪。**只能從主檔選**，不接受自由輸入
    （見 src/models/blueprint.py 與 app/player/view.py 的 add_my_blueprint）。
    玩家端不顯示也不選「狀態」—— 登記的意思就是「我有這張圖」，一律送
    obtained（已取得）。後端與後台管理頁仍保留完整的 UNLOCK_STATUSES，
    管理員設過的非 obtained 狀態在「查詢 › 持有藍圖」還是會標出來。
  - 查詢（別人的東西，唯讀）
      · 物品庫存：一個關鍵字同時搜物品名稱／地點／玩家暱稱／玩家遊戲ID
        （公會庫＋所有玩家個人庫，見 app/inventory/view.py 的 search_stock）
      · 持有藍圖：某張藍圖誰登記了
  - 個人資料：暱稱／Discord／備註可以自己改，遊戲ID（star_citizen_id）不開放修改
    （它同時是 inventory.player / discord_bindings.handle 的鍵值，改了個人庫存會對不起來）

  Discord 有一個「公開給其他玩家」的勾選（discord_public，預設 false）。
  勾了之後別人在「查詢」的結果裡才看得到聯絡方式，用意是「找到有這張圖的人
  去問他能不能幫做」。遮蔽是在**後端**做的（見 Player.display_names_by_scid
  與 Blueprint._redact_contact），前端只判斷「有沒有拿到值」，不自己解讀旗標。

  「新增」與「庫存異動」的分界是**有沒有這個物品**，不是方向：新增是「我多了
  一個原本沒登記的東西」，庫存異動是「已經登記過的東西數量變了」。所以庫存異動
  兩個方向都能選，新增只有增加。後端沒有帶正負號的 delta API，增減分別是
  /player/inventory/add 與 /remove 兩支，逐列由 endpointFor 決定（見 submitRows）。

  兩者的**地點都是整批共用的一份，放在表單最上面**（depositLocation /
  withdrawLocation），送出後刻意不清空 —— 這兩件事實際上都是「站在某個據點前面
  一次處理完這裡的東西」，地點只需要選一次。所以 row 身上沒有地點欄位，
  submitRows 收的是一個 location 字串而不是逐列的 getter。

  兩張查詢表格的「持有者」都顯示成「暱稱（遊戲ID）」（見 holderLabel）。
  物品那張的 nickname 是後端 /inventory/where 補的 ——
  inventory.player 只存 RSI handle，沒有暱稱（見 Player.display_names_by_scid）。

  欄位的固定說明一律做成標題後面的「?」（components/FieldHint.vue），
  hover 或點一下才展開，不佔版面高度。會隨狀態變的訊息（「以下 3 筆都會登記到
  Area18」、「顯示 2 / 3 筆」、選中物品的綠色勾勾）留在原地常駐顯示。

  藍圖刻意獨立在頂層，不塞進倉庫：它是布林狀態的名冊（有／沒有這張圖），
  跟數量會變動的庫存物品不是同一種東西（見 src/models/blueprint.py 的開頭說明）。
  它跟「查詢 › 持有藍圖」的分界是**資料範圍**：這裡是我的、可寫入，
  查詢那邊是全部玩家的、唯讀。

  版面：.scifi-app（滿版）+ sticky 頂端工具列 + 橫向捲動的分頁列 + 下層分頁，
  配色由 stores/scifiTheme.js 管，玩家可自行更換（ScifiThemePicker）。
  分頁狀態同步在 URL 的 ?tab= 與 ?sub=。
-->
<template>
  <div class="scifi-page scifi-app">
    <!-- ══════════ 頂端工具列（捲動時固定） ══════════ -->
    <header class="scifi-topbar">
      <h1 class="scifi-topbar__title h6">
        <i class="bi bi-person-badge" style="color: var(--sf-accent)"></i>
        <span>{{ player?.nickname || '個人資料' }}</span>
      </h1>

      <span v-if="player?.star_citizen_id" class="badge text-bg-secondary d-none d-md-inline">
        {{ player.star_citizen_id }}
      </span>

      <span class="scifi-topbar__spacer"></span>

      <ScifiThemePicker />

      <button class="btn btn-scifi-outline btn-sm" aria-label="登出" title="登出" @click="logout">
        <i class="bi bi-box-arrow-right"></i>
        <span class="d-none d-sm-inline ms-1">登出</span>
      </button>
    </header>

    <!-- ══════════ 分頁列（手機上橫向捲動，不折行） ══════════ -->
    <nav class="scifi-tabs">
      <ul class="nav nav-tabs" role="tablist">
        <li class="nav-item" v-for="tab in tabs" :key="tab.key" role="presentation">
          <button
            class="nav-link"
            :class="{ active: activeTab === tab.key }"
            role="tab"
            :aria-selected="activeTab === tab.key"
            :aria-controls="`panel-${tab.key}`"
            :id="`tab-${tab.key}`"
            @click="setTab(tab.key)"
          >
            <i :class="tab.icon" class="me-1"></i>{{ tab.label }}
          </button>
        </li>
      </ul>
    </nav>

    <!-- ══════════ 下層分頁（倉庫／查詢才有） ══════════ -->
    <nav v-if="subTabsOf(activeTab).length" class="scifi-subtabs">
      <div class="btn-group btn-group-sm" role="tablist">
        <button
          v-for="sub in subTabsOf(activeTab)"
          :key="sub.key"
          class="btn btn-subtab"
          :class="{ active: activeSub === sub.key }"
          role="tab"
          :aria-selected="activeSub === sub.key"
          :aria-controls="`panel-${activeTab}-${sub.key}`"
          :id="`subtab-${activeTab}-${sub.key}`"
          @click="setSub(sub.key)"
        >{{ sub.label }}</button>
      </div>
    </nav>

    <!-- ══════════ 內容區（滿版） ══════════ -->
    <div class="scifi-body">
    <div v-if="loadingPlayer" class="text-muted small mb-3">載入中…</div>
    <div v-else-if="playerError" class="alert alert-danger">{{ playerError }}</div>

    <!-- ══════════ 倉庫 › 新增（登記還沒有的物品） ══════════ -->
    <div v-show="activeTab === 'warehouse' && activeSub === 'add'" role="tabpanel"
         id="panel-warehouse-add" aria-labelledby="subtab-warehouse-add">
      <Transition name="alert-slide">
        <div v-if="depositSuccess" class="alert alert-success py-2">{{ depositSuccess }}</div>
      </Transition>
      <Transition name="alert-slide">
        <div v-if="depositError" class="alert alert-danger py-2">{{ depositError }}</div>
      </Transition>

      <!-- 地點是整張表單共用的一份，放在最上面：一次新增通常是「剛回到某個
           據點，把身上的東西全部登記進去」，地點只需要選一次。
           送出後刻意**不清空**地點，方便繼續在同一個地點加下一批。 -->
      <div class="card scifi-card mb-3">
        <div class="card-body py-3">
          <div class="row g-2">
            <div class="col-12 col-md-6 position-relative">
              <label class="form-label small fw-semibold mb-1">地點</label>
              <FieldHint text="先選地點，下面的物品都會登記到這裡。送出後地點會保留，方便繼續在同一個地點新增。" />
              <input v-model="depositLocation.location"
                @input="filterRowLocations(depositLocation)" @focus="filterRowLocations(depositLocation)"
                @blur="closeRowLocations(depositLocation)"
                type="text" class="form-control form-control-sm" placeholder="輸入或選擇地點…" autocomplete="off">
              <ul v-if="depositLocation.locationOpen" class="list-group position-absolute w-100 shadow-sm"
                  style="z-index: 30; max-height: 220px; overflow-y: auto;">
                <li v-for="loc in depositLocation.locationResults" :key="loc"
                    class="list-group-item list-group-item-action py-1 px-2 small" style="cursor: pointer;"
                    @mousedown.prevent="pickRowLocation(depositLocation, loc)">
                  {{ locLabel(loc) }}
                </li>
                <li v-if="!depositLocation.locationResults.length"
                    class="list-group-item py-1 px-2 small text-muted">
                  沒有符合的地點，直接輸入即可新增
                </li>
              </ul>
              <div v-if="depositLocation.location.trim()" class="form-text text-success py-0">
                <i class="bi bi-geo-alt"></i> 以下 {{ depositRows.length }} 筆都會登記到
                {{ locLabel(depositLocation.location.trim()) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-for="(row, idx) in depositRows" :key="row.key" class="card scifi-card mb-2">
        <div class="card-body py-3">
          <div class="d-flex justify-content-between align-items-start mb-2">
            <span class="badge text-bg-secondary">第 {{ idx + 1 }} 筆</span>
            <button v-if="depositRows.length > 1" class="btn btn-sm btn-link text-danger p-0"
              :disabled="depositSubmitting" @click="depositRows.splice(idx, 1)">移除</button>
          </div>

          <div class="row g-2">
            <div class="col-12 col-md-9 position-relative">
              <label class="form-label small fw-semibold mb-1">物品</label>
              <input v-model="row.itemQuery" @input="searchRowItems(row)" @focus="searchRowItems(row)"
                type="text" class="form-control form-control-sm" placeholder="輸入物品名稱…" autocomplete="off">
              <ul v-if="row.itemResults.length" class="list-group position-absolute w-100 shadow-sm"
                  style="z-index: 20; max-height: 220px; overflow-y: auto;">
                <li v-for="it in row.itemResults" :key="it._id"
                    class="list-group-item list-group-item-action py-1 px-2 small" style="cursor: pointer;"
                    @click="pickRowItem(row, it)">
                  {{ it.name }}<span v-if="it.name_zh">（{{ it.name_zh }}）</span>
                  <span class="text-muted" v-if="it.type">（{{ it.type }}）</span>
                </li>
              </ul>
              <div v-if="row.selectedItem" class="form-text text-success py-0">
                <i class="bi bi-check-circle"></i> {{ row.selectedItem.name }}
                <span v-if="row.selectedItem.name_zh">（{{ row.selectedItem.name_zh }}）</span>
              </div>
            </div>

            <div class="col-6 col-md-3">
              <label class="form-label small fw-semibold mb-1">數量</label>
              <input v-model.number="row.quantity" type="number" min="1" class="form-control form-control-sm">
            </div>
          </div>

          <div v-if="row.error" class="text-danger small mt-2">{{ row.error }}</div>
        </div>
      </div>

      <div class="d-flex justify-content-between mb-4">
        <button class="btn btn-scifi-outline btn-sm" :disabled="depositSubmitting"
          @click="depositRows.push(makeRow(false))">
          <i class="bi bi-plus-lg me-1"></i>再加一筆
        </button>
        <button class="btn btn-scifi" :disabled="depositSubmitting" @click="submitDepositRows">
          <span v-if="depositSubmitting" class="spinner-border spinner-border-sm me-1"></span>
          全部新增
        </button>
      </div>
    </div>

    <!-- ══════════ 倉庫 › 庫存異動（對已登記的物品增減數量） ══════════ -->
    <div v-show="activeTab === 'warehouse' && activeSub === 'adjust'" role="tabpanel"
         id="panel-warehouse-adjust" aria-labelledby="subtab-warehouse-adjust">
      <Transition name="alert-slide">
        <div v-if="withdrawSuccess" class="alert alert-success py-2">{{ withdrawSuccess }}</div>
      </Transition>
      <Transition name="alert-slide">
        <div v-if="withdrawError" class="alert alert-danger py-2">{{ withdrawError }}</div>
      </Transition>

      <!-- 地點跟「新增」一樣是整批共用的一份，放在最上面：盤點通常是
           「站在某個據點前面，把這裡的庫存一次對完」，地點只需要選一次。
           送出後刻意不清空，方便繼續在同一個地點調下一批。 -->
      <div class="card scifi-card mb-3">
        <div class="card-body py-3">
          <div class="row g-2">
            <div class="col-12 col-md-6 position-relative">
              <label class="form-label small fw-semibold mb-1">地點</label>
              <FieldHint text="先選地點，下面的增減都會套用到這裡。送出後地點會保留，方便繼續調同一個地點的庫存。" />
              <input v-model="withdrawLocation.location"
                @input="filterRowLocations(withdrawLocation)" @focus="filterRowLocations(withdrawLocation)"
                @blur="closeRowLocations(withdrawLocation)"
                type="text" class="form-control form-control-sm" placeholder="輸入或選擇地點…" autocomplete="off">
              <ul v-if="withdrawLocation.locationOpen" class="list-group position-absolute w-100 shadow-sm"
                  style="z-index: 30; max-height: 220px; overflow-y: auto;">
                <li v-for="loc in withdrawLocation.locationResults" :key="loc"
                    class="list-group-item list-group-item-action py-1 px-2 small" style="cursor: pointer;"
                    @mousedown.prevent="pickRowLocation(withdrawLocation, loc)">
                  {{ locLabel(loc) }}
                </li>
                <li v-if="!withdrawLocation.locationResults.length"
                    class="list-group-item py-1 px-2 small text-muted">
                  沒有符合的地點，直接輸入即可新增
                </li>
              </ul>
              <div v-if="withdrawLocation.location.trim()" class="form-text text-success py-0">
                <i class="bi bi-geo-alt"></i> 以下 {{ withdrawRows.length }} 筆都會異動
                {{ locLabel(withdrawLocation.location.trim()) }} 的庫存
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-for="(row, idx) in withdrawRows" :key="row.key" class="card scifi-card mb-2">
        <div class="card-body py-3">
          <div class="d-flex justify-content-between align-items-center mb-2">
            <div class="d-flex align-items-center gap-2">
              <span class="badge text-bg-secondary">第 {{ idx + 1 }} 筆</span>
              <!-- 方向做成每列各自可選，而不是整張表單一個開關：
                   同一次送出常常是「這個 +5、那個 -2」的盤點調整 -->
              <div class="btn-group btn-group-sm" role="group" aria-label="異動方向">
                <button type="button" class="btn btn-subtab"
                  :class="{ active: row.direction === 'in' }"
                  @click="row.direction = 'in'">＋ 增加</button>
                <button type="button" class="btn btn-subtab"
                  :class="{ active: row.direction === 'out' }"
                  @click="row.direction = 'out'">－ 減少</button>
              </div>
            </div>
            <button v-if="withdrawRows.length > 1" class="btn btn-sm btn-link text-danger p-0"
              :disabled="withdrawSubmitting" @click="withdrawRows.splice(idx, 1)">移除</button>
          </div>

          <div class="row g-2">
            <div class="col-12 col-md-9 position-relative">
              <label class="form-label small fw-semibold mb-1">物品</label>
              <input v-model="row.itemQuery" @input="searchRowItems(row)" @focus="searchRowItems(row)"
                type="text" class="form-control form-control-sm" placeholder="輸入物品名稱…" autocomplete="off">
              <ul v-if="row.itemResults.length" class="list-group position-absolute w-100 shadow-sm"
                  style="z-index: 20; max-height: 220px; overflow-y: auto;">
                <li v-for="it in row.itemResults" :key="it._id"
                    class="list-group-item list-group-item-action py-1 px-2 small" style="cursor: pointer;"
                    @click="pickRowItem(row, it)">
                  {{ it.name }}<span v-if="it.name_zh">（{{ it.name_zh }}）</span>
                  <span class="text-muted" v-if="it.type">（{{ it.type }}）</span>
                </li>
              </ul>
              <div v-if="row.selectedItem" class="form-text text-success py-0">
                <i class="bi bi-check-circle"></i> {{ row.selectedItem.name }}
                <span v-if="row.selectedItem.name_zh">（{{ row.selectedItem.name_zh }}）</span>
              </div>
            </div>

            <div class="col-6 col-md-3">
              <label class="form-label small fw-semibold mb-1">數量</label>
              <input v-model.number="row.quantity" type="number" min="1" class="form-control form-control-sm">
            </div>

            <div class="col-12">
              <label class="form-label small fw-semibold mb-1">備註（選填，記錄異動原因）</label>
              <input v-model="row.note" type="text" class="form-control form-control-sm"
                :placeholder="row.direction === 'out'
                  ? '例如：分給公會、任務用掉…'
                  : '例如：打怪撿到、盤點補回…'">
            </div>
          </div>

          <div v-if="row.error" class="text-danger small mt-2">{{ row.error }}</div>
        </div>
      </div>

      <div class="d-flex justify-content-between mb-4">
        <button class="btn btn-scifi-outline btn-sm" :disabled="withdrawSubmitting"
          @click="withdrawRows.push(makeRow(true))">
          <i class="bi bi-plus-lg me-1"></i>再加一筆
        </button>
        <button class="btn btn-scifi" :disabled="withdrawSubmitting" @click="submitWithdrawRows">
          <span v-if="withdrawSubmitting" class="spinner-border spinner-border-sm me-1"></span>
          全部送出
        </button>
      </div>
    </div>

    <!-- ══════════ 查詢 › 物品庫存 ══════════ -->
    <div v-show="activeTab === 'search' && activeSub === 'items'" role="tabpanel"
         id="panel-search-items" aria-labelledby="subtab-search-items">
      <div class="card scifi-card mb-3">
        <div class="card-body py-3">
          <div class="d-flex justify-content-between align-items-start mb-1">
            <label class="form-label small fw-semibold mb-0">搜尋條件</label>
            <button type="button" class="btn btn-sm btn-outline-secondary py-0"
              @click="clearItemsFilters">清除全部</button>
          </div>
          <FieldHint text="打字選一個候選代入（不是子字串比對），5 個欄位都填的話要同時符合才會出現在結果裡。物品名稱／物品類型只能擇一——選了名稱等於已經鎖定單一物品，類型會被忽略。" />
          <div class="row g-2">
            <div class="col-12 col-md-6">
              <label class="form-label small mb-1" for="items-name">物品名稱</label>
              <AutocompleteField id="items-name" v-model="itemsNameText"
                :search="searchItemNames" :get-label="itemNameLabel"
                aria-label="物品名稱" placeholder="輸入物品名稱…" :min-chars="1"
                @select="onItemsNameSelect" />
            </div>
            <div class="col-12 col-md-6">
              <label class="form-label small mb-1" for="items-type">物品類型</label>
              <MultiSelectFilter id="items-type" v-model="itemsSelectedTypes" :options="itemTypes"
                label="物品類型" placeholder="全部" block searchable />
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label small mb-1" for="items-location">物品地點</label>
              <MultiSelectFilter id="items-location" v-model="itemsSelectedLocations" :options="locationOptions"
                label="物品地點" placeholder="全部" block searchable />
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label small mb-1" for="items-player-id">玩家id</label>
              <AutocompleteField id="items-player-id" v-model="itemsPlayerIdText"
                :search="searchPlayersLocal" :get-label="c => c.star_citizen_id"
                aria-label="玩家id" placeholder="點一下看全部玩家…" :min-chars="0" :debounce-ms="0"
                @select="onItemsPlayerIdSelect" />
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label small mb-1" for="items-player-nickname">玩家暱稱</label>
              <AutocompleteField id="items-player-nickname" v-model="itemsPlayerNicknameText"
                :search="searchPlayersLocal" :get-label="playerCandidateLabel"
                aria-label="玩家暱稱" placeholder="點一下看全部玩家…" :min-chars="0" :debounce-ms="0"
                @select="onItemsPlayerNicknameSelect" />
            </div>
          </div>
        </div>
      </div>

      <div v-if="loadingWho" class="text-muted small">查詢中…</div>
      <div v-else-if="!hasStockFilter" class="text-muted small">
        至少選擇一個篩選條件開始搜尋。
      </div>
      <div v-else-if="!whoRows.length" class="text-muted small">
        找不到符合條件的庫存。
      </div>
      <div v-else>
        <p class="small text-muted mb-2">共 {{ whoRows.length }} 筆</p>
        <div class="scifi-scroll">
        <table class="table table-sm">
          <thead>
            <tr><th>物品</th><th>持有者</th><th>地點</th><th class="text-end">數量</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in whoRows" :key="i">
              <td>
                {{ row.item_name }}<span v-if="row.item_name_zh" class="text-muted">（{{ row.item_name_zh }}）</span>
                <i v-if="row.item_retired" class="bi bi-exclamation-triangle text-warning ms-1"
                   title="這個物品已在新版本移除"></i>
              </td>
              <td>
                <span v-if="row.owner_type === 'guild'">公會共享庫</span>
                <template v-else>
                  {{ holderLabel(row.nickname, row.player_name, row.player) }}
                  <!-- 只有本人勾了公開才拿得到值，後端已經先遮蔽過 -->
                  <span v-if="discordLabel(row)" class="d-block small text-muted">
                    <i class="bi bi-discord"></i> {{ discordLabel(row) }}
                  </span>
                </template>
              </td>
              <td>{{ locLabel(row.location) }}<span v-if="row.container" class="text-muted"> / {{ row.container }}</span></td>
              <td class="text-end">{{ row.quantity }}</td>
            </tr>
          </tbody>
        </table>
        </div>
      </div>
    </div>

    <!-- ══════════ 查詢 › 持有藍圖 ══════════ -->
    <!-- 這裡查的是「誰登記了這張藍圖」，也就是別人的名冊 ——
         跟頂層的「藍圖」分頁（自己的名冊，可增刪）是不同的資料範圍。 -->
    <div v-show="activeTab === 'search' && activeSub === 'blueprints'" role="tabpanel"
         id="panel-search-blueprints" aria-labelledby="subtab-search-blueprints">
      <div class="card scifi-card mb-3">
        <div class="card-body py-3">
          <div class="d-flex justify-content-between align-items-start mb-1">
            <label class="form-label small fw-semibold mb-0">搜尋條件</label>
            <button type="button" class="btn btn-sm btn-outline-secondary py-0"
              @click="clearBpFilters">清除全部</button>
          </div>
          <FieldHint text="打字選一個候選代入。都留空則列出全部人的登記；填了的話要同時符合才會出現。" />
          <div class="row g-2">
            <div class="col-12 col-md-6">
              <label class="form-label small mb-1" for="bp-name">藍圖名稱</label>
              <AutocompleteField id="bp-name" v-model="bpNameText"
                :search="searchBlueprintNames" :get-label="blueprintNameLabel"
                aria-label="藍圖名稱" placeholder="輸入藍圖名稱…" :min-chars="1"
                @select="onBpNameSelect" />
            </div>
            <div class="col-12 col-md-6">
              <label class="form-label small mb-1" for="bp-type">藍圖類型</label>
              <MultiSelectFilter id="bp-type" v-model="bpSelectedTypes" :options="blueprintTypeOptions"
                label="藍圖類型" placeholder="全部" block searchable />
            </div>
            <div class="col-12 col-md-6">
              <label class="form-label small mb-1" for="bp-player-id">玩家id</label>
              <AutocompleteField id="bp-player-id" v-model="bpPlayerIdText"
                :search="searchPlayersLocal" :get-label="c => c.star_citizen_id"
                aria-label="玩家id" placeholder="點一下看全部玩家…" :min-chars="0" :debounce-ms="0"
                @select="onBpPlayerIdSelect" />
            </div>
            <div class="col-12 col-md-6">
              <label class="form-label small mb-1" for="bp-player-nickname">玩家暱稱</label>
              <AutocompleteField id="bp-player-nickname" v-model="bpPlayerNicknameText"
                :search="searchPlayersLocal" :get-label="playerCandidateLabel"
                aria-label="玩家暱稱" placeholder="點一下看全部玩家…" :min-chars="0" :debounce-ms="0"
                @select="onBpPlayerNicknameSelect" />
            </div>
          </div>
        </div>
      </div>

      <div v-if="loadingBpHolders" class="text-muted small">查詢中…</div>
      <div v-else-if="!bpHolders.length" class="text-muted small">
        沒有人登記符合的藍圖。
      </div>
      <div v-else class="scifi-scroll">
        <table class="table table-sm">
          <thead>
            <tr><th>藍圖</th><th>持有人數</th><th class="sf-wrap">持有者</th></tr>
          </thead>
          <tbody>
            <tr v-for="group in bpHolders" :key="group._id">
              <td>
                {{ group.name }}
                <span v-if="group.name_zh" class="text-muted">（{{ group.name_zh }}）</span>
                <i v-if="!group.blueprint_uuid" class="bi bi-pencil text-muted ms-1"
                   title="自由輸入，沒有對應到遊戲配方"></i>
              </td>
              <td>{{ group.holder_count }}</td>
              <td class="small sf-wrap">
                <span v-for="(h, i) in group.holders" :key="i" class="d-block">
                  {{ holderLabel(h.nickname, h.player_name, h.star_citizen_id) }}
                  <!-- 只有管理員設過非「已取得」的狀態才標出來，見 blueprintStatusLabel -->
                  <span v-if="blueprintStatusLabel(h.unlock_status)" class="text-muted">
                    {{ blueprintStatusLabel(h.unlock_status) }}
                  </span>
                  <!-- 只有本人勾了公開才拿得到值，後端已經先遮蔽過 -->
                  <span v-if="discordLabel(h)" class="text-muted ms-1">
                    <i class="bi bi-discord"></i> {{ discordLabel(h) }}
                  </span>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ══════════ 查詢 › 船艦搜尋：誰有哪款船 ══════════ -->
    <div v-show="activeTab === 'search' && activeSub === 'fleet'" role="tabpanel"
         id="panel-search-fleet" aria-labelledby="subtab-search-fleet">
      <div class="card scifi-card mb-3">
        <div class="card-body py-3">
          <div class="d-flex justify-content-between align-items-start mb-1">
            <label class="form-label small fw-semibold mb-0">搜尋條件</label>
            <button type="button" class="btn btn-sm btn-outline-secondary py-0"
              @click="clearFleetFilters">清除全部</button>
          </div>
          <div class="row g-2">
            <div class="col-12 col-md-4">
              <label class="form-label small mb-1" for="fl-name">船艦名稱</label>
              <AutocompleteField id="fl-name" v-model="flNameText"
                :search="searchVehicleNames" :get-label="c => vehicleNameLabel(c.name, c.name_zh)"
                aria-label="船艦名稱" placeholder="輸入船名…" :min-chars="1"
                @select="c => { flSelectedVehicleId = c ? c._id : '' }" />
            </div>
            <div class="col-6 col-md-4">
              <label class="form-label small mb-1" for="fl-type">類型</label>
              <MultiSelectFilter id="fl-type" v-model="flSelectedTypes" :options="vehicleFacets.types"
                label="類型" placeholder="全部" block />
            </div>
            <div class="col-6 col-md-4">
              <label class="form-label small mb-1" for="fl-size">尺寸</label>
              <MultiSelectFilter id="fl-size" v-model="flSelectedSizes" :options="vehicleSizeOptions"
                label="尺寸" placeholder="全部" block />
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label small mb-1" for="fl-mfr">廠商</label>
              <MultiSelectFilter id="fl-mfr" v-model="flSelectedMfrs" :options="manufacturerOptions"
                label="廠商" placeholder="全部" block searchable />
            </div>
            <div class="col-12 col-md-4">
              <label class="form-label small mb-1" for="fl-role">角色</label>
              <MultiSelectFilter id="fl-role" v-model="flSelectedRoles" :options="vehicleFacets.roles"
                label="角色" placeholder="全部" block searchable />
            </div>
            <div class="col-6 col-md-2">
              <label class="form-label small mb-1" for="fl-player-id">玩家id</label>
              <AutocompleteField id="fl-player-id" v-model="flPlayerIdText"
                :search="searchPlayersLocal" :get-label="c => c.star_citizen_id"
                aria-label="玩家id" placeholder="點一下看全部玩家…" :min-chars="0" :debounce-ms="0"
                @select="onFlPlayerIdSelect" />
            </div>
            <div class="col-6 col-md-2">
              <label class="form-label small mb-1" for="fl-player-nickname">玩家暱稱</label>
              <AutocompleteField id="fl-player-nickname" v-model="flPlayerNicknameText"
                :search="searchPlayersLocal" :get-label="playerCandidateLabel"
                aria-label="玩家暱稱" placeholder="點一下看全部玩家…" :min-chars="0" :debounce-ms="0"
                @select="onFlPlayerNicknameSelect" />
            </div>
          </div>
        </div>
      </div>

      <div v-if="loadingFleetHolders" class="text-muted small">查詢中…</div>
      <div v-else-if="!fleetHolders.length" class="text-muted small">
        沒有人登記符合條件的船／載具。
      </div>
      <div v-else class="scifi-scroll">
        <table class="table table-sm">
          <thead>
            <tr>
              <th>船艦</th><th>類型</th><th>尺寸</th><th>廠商</th><th>角色</th>
              <th>持有</th><th class="sf-wrap">持有者</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="group in fleetHolders" :key="group._id">
              <td>
                {{ group.vehicle?.name || group.name }}
                <span v-if="group.vehicle?.name_zh" class="text-muted">（{{ group.vehicle.name_zh }}）</span>
              </td>
              <td class="small">{{ vehicleTypeLabel(group.vehicle?.vehicle_type) }}</td>
              <td class="small">{{ vehicleSizeLabel(group.vehicle?.size_class) }}</td>
              <td class="small">{{ manufacturerLabel(group.vehicle?.manufacturer_name, group.vehicle?.manufacturer_code) }}</td>
              <td class="small">{{ vehicleRoleLabel(group.vehicle?.role, group.vehicle?.role_zh) }}</td>
              <td class="small text-nowrap">{{ group.holder_count }} 人 / {{ group.total_quantity }} 艘</td>
              <td class="small sf-wrap">
                <span v-for="(h, i) in group.holders" :key="i" class="d-block">
                  {{ holderLabel(h.nickname, h.player_name, h.star_citizen_id) }}
                  <span v-if="h.quantity > 1" class="text-muted">×{{ h.quantity }}</span>
                  <!-- 只有本人勾了公開才拿得到值，後端已經先遮蔽過 -->
                  <span v-if="discordLabel(h)" class="text-muted ms-1">
                    <i class="bi bi-discord"></i> {{ discordLabel(h) }}
                  </span>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ══════════ 倉庫 › 物品庫存 ══════════ -->
    <div v-show="activeTab === 'warehouse' && activeSub === 'stock'" role="tabpanel"
         id="panel-warehouse-stock" aria-labelledby="subtab-warehouse-stock">
      <InventoryFilterBar
        :rows="myInventory" :matched="filteredInventory.length" :loc-label="locLabel"
        v-model:item="stockFilter.item" v-model:location="stockFilter.location" />

      <div class="d-flex justify-content-end mb-2">
        <button class="btn btn-sm btn-link p-0" @click="loadMyInventory">重新整理</button>
      </div>
      <div v-if="loadingInventory" class="text-muted small">載入中…</div>
      <div v-else-if="!myInventory.length" class="text-muted small">目前沒有登記任何物品。</div>
      <div v-else-if="!filteredInventory.length" class="text-muted small">
        沒有符合篩選條件的物品。
      </div>
      <div v-else class="scifi-scroll">
      <table class="table table-sm">
        <thead>
          <tr><th>物品</th><th>地點</th><th class="text-end">數量</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredInventory" :key="row.item_id + row.location + (row.container || '')">
            <td>{{ row.item_name }}<span v-if="row.item_name_zh" class="text-muted">（{{ row.item_name_zh }}）</span></td>
            <td>{{ locLabel(row.location) }}<span v-if="row.container" class="text-muted"> / {{ row.container }}</span></td>
            <td class="text-end">{{ row.quantity }}</td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>

    <!-- ══════════ 倉庫 › 庫存紀錄 ══════════ -->
    <div v-show="activeTab === 'warehouse' && activeSub === 'history'" role="tabpanel"
         id="panel-warehouse-history" aria-labelledby="subtab-warehouse-history">
      <InventoryFilterBar
        :rows="history" :matched="filteredHistory.length" :loc-label="locLabel"
        v-model:item="historyFilter.item" v-model:location="historyFilter.location" />

      <div class="d-flex justify-content-end mb-2">
        <button class="btn btn-sm btn-link p-0" @click="loadHistory">重新整理</button>
      </div>
      <div v-if="loadingHistory" class="text-muted small">載入中…</div>
      <div v-else-if="!history.length" class="text-muted small">目前沒有任何紀錄。</div>
      <div v-else-if="!filteredHistory.length" class="text-muted small">
        沒有符合篩選條件的紀錄。
      </div>
      <div v-else class="scifi-scroll">
      <table class="table table-sm">
        <thead>
          <tr><th>時間</th><th>動作</th><th>物品</th><th>地點</th><th class="text-end">數量</th><th class="sf-wrap">備註</th></tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in filteredHistory" :key="i">
            <td class="small text-muted">{{ formatTs(row.ts) }}</td>
            <td>
              <span v-if="row.delta > 0" class="badge text-bg-success">增加</span>
              <span v-else class="badge text-bg-danger">減少</span>
            </td>
            <td>{{ row.item_name }}<span v-if="row.item_name_zh" class="text-muted">（{{ row.item_name_zh }}）</span></td>
            <td>{{ locLabel(row.location) }}<span v-if="row.container" class="text-muted"> / {{ row.container }}</span></td>
            <td class="text-end">{{ row.delta > 0 ? '+' : '' }}{{ row.delta }}</td>
            <td class="small text-muted sf-wrap">{{ row.note || '—' }}</td>
          </tr>
        </tbody>
      </table>
      </div>
    </div>

    <!-- ══════════ 藍圖（自己的名冊，可增刪） ══════════ -->
    <div v-show="activeTab === 'blueprints' && activeSub === 'mine'" role="tabpanel"
         id="panel-blueprints-mine" aria-labelledby="subtab-blueprints-mine">
      <Transition name="alert-slide">
        <div v-if="blueprintError" class="alert alert-danger py-2">{{ blueprintError }}</div>
      </Transition>
      <Transition name="alert-slide">
        <div v-if="blueprintSuccess" class="alert alert-success py-2">{{ blueprintSuccess }}</div>
      </Transition>

      <div class="card scifi-card mb-3">
        <div class="card-body py-3">
          <div class="row g-2">
            <div class="col-12 col-md-6 position-relative">
              <label class="form-label small fw-semibold mb-1">藍圖</label>

              <!-- 主檔還沒同步時給明確指示，而不是一個永遠搜不到東西的輸入框 -->
              <div v-if="masterCount === 0" class="alert alert-warning py-2 mb-0 small">
                <i class="bi bi-exclamation-triangle me-1"></i>
                藍圖主檔尚未同步，目前無法登記。請聯絡管理員執行遊戲資料同步。
              </div>

              <template v-else>
                <input v-model="bpQuery"
                  @input="searchBlueprintMaster" @focus="searchBlueprintMaster"
                  @blur="closeBlueprintResults"
                  type="text" class="form-control form-control-sm" autocomplete="off"
                  placeholder="搜尋藍圖名稱（中英文皆可）">
                <ul v-if="bpOpen" class="list-group position-absolute w-100 shadow-sm"
                    style="z-index: 20; max-height: 240px; overflow-y: auto;">
                  <li v-for="bp in bpResults" :key="bp._id"
                      class="list-group-item list-group-item-action py-1 px-2 small" style="cursor: pointer;"
                      @mousedown.prevent="pickBlueprintMaster(bp)">
                    {{ bp.name }}<span v-if="bp.name_zh">（{{ bp.name_zh }}）</span>
                    <span class="text-muted" v-if="bp.output_type">（{{ blueprintTypeLabel(bp.output_type) }}）</span>
                    <span class="text-muted" v-if="bp.ingredient_count"> · {{ bp.ingredient_count }} 種材料</span>
                  </li>
                  <li v-if="!bpResults.length" class="list-group-item py-1 px-2 small text-muted">
                    <template v-if="bpQuery.trim().length < 2">請至少輸入 2 個字</template>
                    <template v-else>找不到「{{ bpQuery }}」。只能登記主檔裡有的藍圖。</template>
                  </li>
                </ul>

                <div v-if="blueprintForm.blueprint_uuid" class="form-text text-success py-0">
                  <i class="bi bi-check-circle"></i> {{ blueprintForm.name }}
                  <button class="btn btn-link btn-sm p-0 ms-1" @click="clearBlueprintMaster">清除</button>
                </div>
              </template>
            </div>
            <div class="col-12 col-md-6">
              <label class="form-label small fw-semibold mb-1">備註</label>
              <input v-model="blueprintForm.notes" type="text" class="form-control form-control-sm">
            </div>
          </div>
          <div class="text-end mt-2">
            <button class="btn btn-scifi btn-sm"
              :disabled="blueprintSubmitting || !blueprintForm.blueprint_uuid"
              :title="blueprintForm.blueprint_uuid ? '' : '請先從清單選擇藍圖'"
              @click="submitBlueprint">
              <span v-if="blueprintSubmitting" class="spinner-border spinner-border-sm me-1"></span>
              登記藍圖
            </button>
          </div>
        </div>
      </div>

      <div class="d-flex justify-content-end mb-2">
        <button class="btn btn-sm btn-link p-0" @click="loadBlueprints">重新整理</button>
      </div>
      <div v-if="loadingBlueprints" class="text-muted small">載入中…</div>
      <div v-else-if="!blueprints.length" class="text-muted small">目前沒有登記任何藍圖。</div>
      <div v-else class="scifi-scroll">
      <table class="table table-sm">
        <thead>
          <tr><th>名稱</th><th>類型</th><th>製作時間</th><th>材料</th><th class="sf-wrap">備註</th><th></th></tr>
        </thead>
        <tbody>
          <template v-for="bp in blueprints" :key="bp._id">
          <tr>
            <td>
              {{ bp.name }}
              <span v-if="bp.master?.name_zh" class="text-muted">（{{ bp.master.name_zh }}）</span>
              <i v-if="!bp.blueprint_uuid" class="bi bi-pencil text-muted ms-1"
                 title="自由輸入，沒有對應到遊戲配方"></i>
            </td>
            <td class="small">{{ bp.master?.output_type ? blueprintTypeLabel(bp.master.output_type) : (bp.master?.output_type_label || '—') }}</td>
            <td class="small">{{ bp.master?.craft_time_label || '—' }}</td>
            <td class="small">
              <button v-if="bp.blueprint_uuid" class="btn btn-link btn-sm p-0"
                @click="showRecipe(bp)">{{ bp.master?.ingredient_count ?? '?' }} 種</button>
              <span v-else class="text-muted">—</span>
            </td>
            <td class="small text-muted sf-wrap">{{ bp.notes || '—' }}</td>
            <td class="text-end">
              <button class="btn btn-sm btn-link text-danger p-0" @click="removeBlueprint(bp)">刪除</button>
            </td>
          </tr>
          <tr v-if="recipeFor === bp._id">
            <!-- colspan 要跟 thead 的欄數一致（移除「狀態」欄後是 6） -->
            <td colspan="6" class="small">
              <div v-if="loadingRecipe" class="text-muted">載入配方…</div>
              <div v-else-if="recipe">
                <strong>{{ recipe.name }}</strong>
                <span v-if="recipe.craft_time_label" class="text-muted">（{{ recipe.craft_time_label }}）</span>
                <ul class="mb-1 mt-1">
                  <li v-for="(ing, i) in recipe.ingredients" :key="i">
                    {{ ing.name }} ×
                    <span v-if="ing.quantity != null">{{ ing.quantity }}</span>
                    <span v-else-if="ing.quantity_scu != null">{{ ing.quantity_scu }} SCU</span>
                    <span v-else>?</span>
                  </li>
                </ul>
                <div v-if="recipe.dismantle_returns?.length" class="text-muted">
                  拆解可回收：{{ recipe.dismantle_returns.map(r => `${r.name} ${r.quantity_scu} SCU`).join('、') }}
                </div>
              </div>
            </td>
          </tr>
          </template>
        </tbody>
      </table>
      </div>
    </div>

    <!-- ══════════ 個人資料 ══════════ -->
    <!-- ══════════ 藍圖批量登記 ══════════ -->
    <div v-show="activeTab === 'blueprints' && activeSub === 'bulk'" role="tabpanel"
         id="panel-blueprints-bulk" aria-labelledby="subtab-blueprints-bulk">
      <BlueprintBulkRegister ref="bulkRegisterRef" :fetcher="playerAuth.playerFetch"
        card-class="card scifi-card" @registered="onBulkRegistered" />
    </div>

    <!-- ══════════ 藍圖 › 試算 ══════════ -->
    <div v-show="activeTab === 'blueprints' && activeSub === 'craft'" role="tabpanel"
      id="panel-blueprints-craft" :aria-labelledby="'subtab-blueprints-craft'">
      <!-- 元件跟後台「材料試算」頁共用，差別只在帶進去的身分與庫存來源 -->
      <BlueprintCalculator :fetcher="playerAuth.playerFetch"
        :stock-loader="loadMyStock" stock-label="我的個人庫"
        card-class="card scifi-card" />
    </div>

    <!-- ══════════ 艦隊 › 我的艦隊 ══════════ -->
    <div v-show="activeTab === 'fleet' && activeSub === 'mine'" role="tabpanel"
         id="panel-fleet-mine" aria-labelledby="subtab-fleet-mine">
      <Transition name="alert-slide">
        <div v-if="fleetError" class="alert alert-danger py-2">{{ fleetError }}</div>
      </Transition>

      <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
        <span class="small text-muted">
          <template v-if="fleet.length">共 {{ fleet.length }} 款、{{ fleetShipCount }} 艘</template>
        </span>
        <button class="btn btn-sm btn-link p-0" @click="loadFleet">重新整理</button>
      </div>
      <div v-if="loadingFleet" class="text-muted small">載入中…</div>
      <div v-else-if="fleet.length" class="scifi-scroll">
        <table class="table table-sm align-middle">
          <thead>
            <tr>
              <th>載具</th><th>類型</th><th>尺寸</th><th>廠商</th><th>角色</th>
              <th style="width: 6rem">數量</th><th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in fleet" :key="row._id">
              <td>
                {{ row.name }}
                <span v-if="row.vehicle?.name_zh" class="text-muted">（{{ row.vehicle.name_zh }}）</span>
                <span v-if="row.vehicle && row.vehicle.is_current === false"
                  class="badge bg-secondary ms-1" title="目前遊戲版本的資料裡已經沒有這款">已下架</span>
              </td>
              <td class="small">{{ vehicleTypeLabel(row.vehicle?.vehicle_type) }}</td>
              <td class="small">{{ vehicleSizeLabel(row.vehicle?.size_class) }}</td>
              <td class="small">{{ manufacturerLabel(row.vehicle?.manufacturer_name, row.vehicle?.manufacturer_code) }}</td>
              <td class="small">{{ vehicleRoleLabel(row.vehicle?.role, row.vehicle?.role_zh) }}</td>
              <td>
                <input type="number" min="1" :max="fleetMaxQuantity"
                  class="form-control form-control-sm" :value="row.quantity"
                  :aria-label="`${row.name} 數量`" :disabled="savingFleetId === row._id"
                  @change="updateFleetQuantity(row, $event)">
              </td>
              <td class="text-end">
                <button class="btn btn-sm btn-link text-danger p-0" @click="removeFleet(row)">刪除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ══════════ 艦隊 › 批量登記 ══════════ -->
    <div v-show="activeTab === 'fleet' && activeSub === 'bulk'" role="tabpanel"
         id="panel-fleet-bulk" aria-labelledby="subtab-fleet-bulk">
      <FleetBulkRegister ref="fleetBulkRef" :fetcher="playerAuth.playerFetch"
        card-class="card scifi-card" @registered="loadFleet" />
    </div>

    <!-- ══════════ 礦物參考查詢 ══════════ -->
    <div v-show="activeTab === 'mining'" role="tabpanel" id="panel-mining"
      :aria-labelledby="'tab-mining'">
      <!-- 元件跟後台「礦物參考查詢」頁共用，差別只在帶進去的身分 -->
      <MiningLookup :fetcher="playerAuth.playerFetch" :active="activeTab === 'mining'"
        card-class="card scifi-card" />
    </div>

    <div v-show="activeTab === 'profile'" role="tabpanel" id="panel-profile" :aria-labelledby="'tab-profile'">
      <Transition name="alert-slide">
        <div v-if="profileError" class="alert alert-danger py-2">{{ profileError }}</div>
      </Transition>
      <Transition name="alert-slide">
        <div v-if="profileSuccess" class="alert alert-success py-2">已更新</div>
      </Transition>

      <div v-if="player" class="card scifi-card">
        <div class="card-body">
          <div class="mb-3">
            <label class="form-label small fw-semibold">遊戲ID（Star Citizen ID）</label>
            <FieldHint text="遊戲ID 不可自行更改，需要換的話請聯絡管理員。它同時是個人庫存與 Discord 綁定用的鍵值，改了會對不起來。" />
            <input :value="player.star_citizen_id" type="text" class="form-control" disabled>
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold">暱稱</label>
            <input v-model="profileForm.nickname" type="text" class="form-control">
          </div>
          <!-- Discord 兩個欄位放在同一張卡裡，公開勾選就在下面 ——
               勾選管的是這兩個欄位，分開放會看不出關聯。 -->
          <div class="card scifi-card mb-3">
            <div class="card-body py-3">
              <div class="row g-2">
                <div class="col-12 col-md-6">
                  <label class="form-label small fw-semibold mb-1">Discord 名稱</label>
                  <input v-model="profileForm.discord_name" type="text" class="form-control form-control-sm">
                </div>
                <div class="col-12 col-md-6">
                  <label class="form-label small fw-semibold mb-1">Discord ID</label>
                  <input v-model="profileForm.discord_id" type="text" class="form-control form-control-sm">
                </div>
              </div>

              <div class="form-check mt-3">
                <input class="form-check-input" type="checkbox" id="discord-public"
                  v-model="profileForm.discord_public">
                <label class="form-check-label small" for="discord-public">
                  公開給其他玩家
                  <FieldHint text="勾選後，別人在「查詢」的結果裡看到你時會一併看到你的 Discord，方便直接找你詢問。不勾就完全不顯示（預設不公開）。" />
                </label>
              </div>
              <div class="form-text py-0">
                <template v-if="profileForm.discord_public">
                  <i class="bi bi-eye text-warning"></i>
                  其他玩家查到你持有的物品或藍圖時，會看到你的 Discord。
                </template>
                <template v-else>
                  <i class="bi bi-eye-slash"></i>
                  目前不公開，只有你和管理員看得到。
                </template>
              </div>
            </div>
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold">備註</label>
            <textarea v-model="profileForm.notes" class="form-control" rows="2"></textarea>
          </div>
          <button class="btn btn-scifi" :disabled="savingProfile" @click="saveProfile">
            <span v-if="savingProfile" class="spinner-border spinner-border-sm me-1"></span>
            儲存
          </button>
        </div>
      </div>

      <div v-if="player" class="card scifi-card mt-3">
        <div class="card-body">
          <h6 class="fw-semibold mb-3"><i class="bi bi-key me-1"></i>更改密碼</h6>
          <Transition name="alert-slide">
            <div v-if="pwError" class="alert alert-danger py-2">{{ pwError }}</div>
          </Transition>
          <Transition name="alert-slide">
            <div v-if="pwSuccess" class="alert alert-success py-2">密碼已更新</div>
          </Transition>

          <div class="mb-3">
            <label class="form-label small fw-semibold">目前密碼</label>
            <input v-model="pwForm.current_password" type="password" class="form-control"
              autocomplete="current-password">
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold">新密碼</label>
            <input v-model="pwForm.new_password" type="password" class="form-control" minlength="6"
              placeholder="至少 6 個字元" autocomplete="new-password">
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold">確認新密碼</label>
            <input v-model="pwForm.confirm_password" type="password" class="form-control" minlength="6"
              placeholder="再輸入一次新密碼" autocomplete="new-password">
          </div>
          <button class="btn btn-scifi" :disabled="changingPassword" @click="changePassword">
            <span v-if="changingPassword" class="spinner-border spinner-border-sm me-1"></span>
            更改密碼
          </button>
        </div>
      </div>

      <!-- Discord 綁定碼：Discord 帳號沒辦法自己證明它屬於哪個遊戲帳號，
           所以「證明」這一步只能放在需要密碼登入的這一頁。 -->
      <div v-if="player" class="card scifi-card mt-3">
        <div class="card-body">
          <h6 class="fw-semibold mb-3"><i class="bi bi-discord me-1"></i>Discord 綁定</h6>
          <p class="small mb-3" style="color: var(--sf-text-muted)">
            按下按鈕產生一組 8 碼，10 分鐘內到 Discord 輸入
            <code>/bind</code> 完成綁定。綁定後才能用 Discord 指令操作自己的個人庫。
          </p>

          <Transition name="alert-slide">
            <div v-if="bindError" class="alert alert-danger py-2">{{ bindError }}</div>
          </Transition>

          <div v-if="bindCode" class="mb-3">
            <div class="p-3 rounded" style="background: var(--sf-panel-2, rgba(255,255,255,.06))">
              <div class="small mb-1" style="color: var(--sf-text-muted)">在 Discord 貼上這一行：</div>
              <code class="d-block" style="user-select: all; word-break: break-all">
                /bind handle:{{ player.star_citizen_id }} code:{{ bindCode }}
              </code>
            </div>
            <div class="small mt-2" style="color: var(--sf-text-muted)">
              有效期限至 {{ fmtTime(bindCodeExpiresAt) }}（過期就再產生一組）。
              這組碼等同一次性密碼，不要貼在公開頻道以外的地方給別人。
            </div>
          </div>

          <button class="btn btn-scifi" :disabled="issuingCode" @click="issueDiscordCode">
            <span v-if="issuingCode" class="spinner-border spinner-border-sm me-1"></span>
            {{ bindCode ? '重新產生綁定碼' : '產生 Discord 綁定碼' }}
          </button>
        </div>
      </div>
    </div>
  </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { usePlayerAuthStore } from '@/stores/playerAuth'
import { PLAYER_LOGIN_PATH } from '@/router'
import { useScifiThemeStore } from '@/stores/scifiTheme'
import ScifiThemePicker from '@/components/ScifiThemePicker.vue'
import InventoryFilterBar from '@/components/InventoryFilterBar.vue'
import BlueprintCalculator from '@/components/BlueprintCalculator.vue'
import MiningLookup from '@/components/MiningLookup.vue'
import BlueprintBulkRegister from '@/components/BlueprintBulkRegister.vue'
import FleetBulkRegister from '@/components/FleetBulkRegister.vue'
import FieldHint from '@/components/FieldHint.vue'
import AutocompleteField from '@/components/AutocompleteField.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'
import { manufacturerLabel, vehicleNameLabel, vehicleRoleLabel, vehicleSizeLabel, vehicleTypeLabel } from '@/utils/vehicle'
// 地點中文：跟全站一樣查資料庫的翻譯（utils/translations.js），不在前端放對照表
import { loadKnownLocations, loadTranslations, translate } from '@/utils/translations'

const router     = useRouter()
const playerAuth = usePlayerAuthStore()
const scifiTheme = useScifiThemeStore()

function locZh(en) { return translate('location', en) }
function locLabel(en) { const zh = locZh(en); return zh ? `${en}（${zh}）` : en }

/** 持有者顯示成「暱稱（遊戲ID）」。
 *
 * 暱稱是選填的，玩家也可能是舊資料／已被軟刪除而查不到名冊，所以要層層退回：
 * 暱稱 → player_name → 只剩遊戲ID 就單獨顯示它，絕不輸出「（TomLi_SC）」
 * 這種前面空一塊的字串。遊戲ID 本身缺失時（理論上不該發生）回 '—'。
 */
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

function holderLabel(nickname, playerName, scid) {
  const id = (scid || '').trim()
  const name = (nickname || '').trim() || (playerName || '').trim()
  if (!id) return name || '—'
  return name ? `${name}（${id}）` : id
}

// 主分頁。「倉庫」與「查詢」各自有下層分頁（subTabs），
// 頂層 6 個項目，手機上放不下時分頁列可以左右滑（見 scifi-theme.css 的 .scifi-tabs）。
const tabs = [
  {
    key: 'warehouse', label: '倉庫',   icon: 'bi bi-box-seam',
    subTabs: [
      { key: 'stock',      label: '物品庫存' },
      { key: 'add',        label: '新增' },
      { key: 'adjust',     label: '庫存異動' },
      { key: 'history',    label: '庫存紀錄' },
    ],
  },
  {
    key: 'blueprints', label: '藍圖',  icon: 'bi bi-diagram-3',
    subTabs: [
      { key: 'mine',   label: '我的藍圖' },
      { key: 'bulk',   label: '批量登記' },
      { key: 'craft',  label: '試算' },
    ],
  },
  {
    key: 'fleet', label: '艦隊',  icon: 'bi bi-rocket-takeoff',
    subTabs: [
      { key: 'mine', label: '我的艦隊' },
      { key: 'bulk', label: '批量登記' },
    ],
  },
  { key: 'mining',     label: '礦物',   icon: 'bi bi-gem' },
  {
    key: 'search',    label: '查詢',   icon: 'bi bi-search',
    subTabs: [
      { key: 'items',      label: '物品庫存' },
      { key: 'blueprints', label: '持有藍圖' },
      { key: 'fleet',      label: '船艦搜尋' },
    ],
  },
  { key: 'profile',   label: '個人資料', icon: 'bi bi-person-gear' },
]

/** 某個主分頁的下層分頁清單（沒有就回空陣列）。 */
function subTabsOf(key) {
  return tabs.find(t => t.key === key)?.subTabs || []
}
// 分頁狀態同步到 URL 的 ?tab= —— 這樣重新整理、手機切回瀏覽器、
// 分享連結給隊友都會停在同一個分頁，瀏覽器的返回鍵也會退回上一個分頁
// 而不是直接離開 /me。
const route = useRoute()
const validTabs = tabs.map(t => t.key)
const activeTab = ref(
  validTabs.includes(route.query.tab) ? route.query.tab : 'warehouse'
)

/** 某個主分頁的預設下層分頁（沒有下層就回 ''）。 */
function defaultSub(tabKey) {
  return subTabsOf(tabKey)[0]?.key || ''
}

function validSub(tabKey, sub) {
  return subTabsOf(tabKey).some(t => t.key === sub)
}

const activeSub = ref(
  validSub(activeTab.value, route.query.sub)
    ? route.query.sub
    : defaultSub(activeTab.value)
)

function syncUrl() {
  const query = { ...route.query, tab: activeTab.value }
  if (activeSub.value) query.sub = activeSub.value
  else delete query.sub
  // replace 而不是 push：切分頁不該在歷史紀錄裡堆一堆項目，
  // 但仍然讓「重新整理後留在同一分頁」成立。
  router.replace({ query })
}

function setTab(key) {
  if (!validTabs.includes(key)) return
  activeTab.value = key
  // 切主分頁時回到它的第一個下層分頁（沒有下層就清空）
  activeSub.value = defaultSub(key)
  syncUrl()
}

function setSub(key) {
  if (!validSub(activeTab.value, key)) return
  activeSub.value = key
  syncUrl()
}

// 某些分頁的資料是進去才載入的，刻意不在 onMounted 全部預載 ——
// 多數玩家不會用到這些分頁，沒必要每次開頁都多打幾次 API。
//
// 用具名函式而不是把邏輯寫在 watch 裡，是因為 onMounted 也要呼叫一次：
// syncUrl() 會把分頁寫進 ?tab=，所以「在藍圖分頁按重新整理」「把連結貼給隊友」
// 都會直接以該分頁開場，此時 watch 不會觸發（值沒變過），資料就永遠不會載。
// 不用 { immediate: true } 是因為 masterCount / bpHolders 宣告在下面，
// 立即執行會踩到 const 的 TDZ。
function loadForTab(tab, sub) {
  if (tab === 'search' && sub === 'items' && !itemTypes.value.length) {
    loadItemTypes()
  }
  if (tab === 'search' && sub === 'blueprints') {
    if (!blueprintOutputTypes.value.length) loadBlueprintOutputTypes()
    if (!bpHolders.value.length) loadBlueprintHolders()
  }
  // 「查詢」各分頁的玩家id／暱稱欄位都用同一份玩家名單，先載起來
  if (tab === 'search') ensureRoster()
  if (tab === 'search' && sub === 'fleet') {
    if (!vehicleFacetsLoaded) loadVehicleFacets()
    if (!fleetHolders.value.length) loadFleetHolders()
  }
  if (tab === 'fleet' && !fleetLoaded.value) loadFleet()
  // 進「藍圖」才查主檔筆數（決定要不要顯示「尚未同步」提示）
  if (tab === 'blueprints' && masterCount.value === null) {
    loadMasterCount()
  }
}

watch([activeTab, activeSub], ([tab, sub]) => loadForTab(tab, sub))

// 使用者直接改網址（或按上一頁）時，畫面要跟著走
watch(() => [route.query.tab, route.query.sub], ([tab, sub]) => {
  if (validTabs.includes(tab) && tab !== activeTab.value) {
    activeTab.value = tab
    activeSub.value = validSub(tab, sub) ? sub : defaultSub(tab)
  } else if (validSub(activeTab.value, sub) && sub !== activeSub.value) {
    activeSub.value = sub
  }
})

function formatTs(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts
  return d.toLocaleString('zh-TW', { hour12: false })
}

// ── 玩家名冊資料 ──────────────────────────────────────────────
const player        = ref(null)
const loadingPlayer  = ref(true)
const playerError    = ref('')
const profileForm    = reactive({ nickname: '', discord_name: '', discord_id: '',
                                  discord_public: false, notes: '' })
const savingProfile  = ref(false)
const profileError   = ref('')
const profileSuccess = ref(false)

// ── 更改密碼：獨立的表單／狀態，跟上面的個人資料儲存分開送出 ──────
// 這樣密碼打錯不會連帶蓋掉「暱稱／Discord 已經存好了」的成功訊息，
// 反之亦然。
const pwForm = reactive({ current_password: '', new_password: '', confirm_password: '' })
const changingPassword = ref(false)
const pwError   = ref('')
const pwSuccess = ref(false)

async function loadPlayer() {
  loadingPlayer.value = true
  const res = await playerAuth.playerFetch('/player/me')
  loadingPlayer.value = false
  if (!res) { playerError.value = '網路錯誤，請稍後再試'; return }
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) {
    player.value = data.data
    profileForm.nickname     = data.data.nickname || ''
    profileForm.discord_name = data.data.discord_name || ''
    profileForm.discord_id   = data.data.discord_id || ''
    profileForm.notes        = data.data.notes || ''
    profileForm.discord_public = !!data.data.discord_public
  } else {
    playerError.value = data?.message || '無法載入資料，請重新登入'
  }
}

async function saveProfile() {
  profileError.value = ''
  profileSuccess.value = false
  savingProfile.value = true
  try {
    const res = await playerAuth.playerFetch('/player/me', {
      method: 'PUT',
      body: JSON.stringify({ ...profileForm }),
    })
    if (!res) { profileError.value = '網路錯誤，請稍後再試'; return }
    const data = await res.json().catch(() => null)
    if (res.ok && data?.success) {
      profileSuccess.value = true
      loadPlayer()
    } else {
      profileError.value = data?.message || '更新失敗，請稍後再試'
    }
  } finally {
    savingProfile.value = false
  }
}

async function changePassword() {
  pwError.value = ''
  pwSuccess.value = false

  const current = pwForm.current_password
  const next     = pwForm.new_password
  if (!current)         { pwError.value = '請輸入目前密碼'; return }
  if (next.length < 6)  { pwError.value = '新密碼至少需要 6 個字元'; return }
  if (next !== pwForm.confirm_password) { pwError.value = '兩次輸入的新密碼不一致'; return }

  changingPassword.value = true
  try {
    const res = await playerAuth.playerFetch('/player/me/password', {
      method: 'PUT',
      body: JSON.stringify({ current_password: current, new_password: next }),
    })
    if (!res) { pwError.value = '網路錯誤，請稍後再試'; return }
    const data = await res.json().catch(() => null)
    if (res.ok && data?.success) {
      pwSuccess.value = true
      pwForm.current_password = ''
      pwForm.new_password = ''
      pwForm.confirm_password = ''
    } else {
      pwError.value = data?.message || '更改密碼失敗，請稍後再試'
    }
  } finally {
    changingPassword.value = false
  }
}

// ── 藍圖批量登記 ──────────────────────────────────────────────
const bulkRegisterRef = ref(null)

/** 批量登記完成後，把「我的藍圖」那一頁的清單也更新（否則要手動重新整理）。 */
async function onBulkRegistered() {
  await loadBlueprints()
}

// ── 藍圖材料試算的庫存來源 ────────────────────────────────────
//
// 個人庫的清單一次就撈得完（後端 limit 200，一般玩家遠低於此），
// 所以不像後台那頁需要逐材料查詢。回傳原始庫存列，換算交給
// utils/craftCalc.js 的 stockToHaveMap（同一份邏輯兩邊共用）。
async function loadMyStock() {
  const res = await playerAuth.playerFetch('/player/inventory')
  const data = res ? await res.json().catch(() => null) : null
  return data?.success ? (data.data || []) : []
}

// ── Discord 綁定碼 ────────────────────────────────────────────
// 碼只在這一次回應裡出現（後端不會再回傳它，玩家名冊 API 也一律把它濾掉），
// 所以存在元件狀態就好，不要寫進 localStorage。
const bindCode          = ref('')
const bindCodeExpiresAt = ref('')
const issuingCode       = ref(false)
const bindError         = ref('')

function fmtTime(value) {
  if (!value) return '—'
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleTimeString('zh-TW')
}

async function issueDiscordCode() {
  bindError.value = ''
  issuingCode.value = true
  try {
    const res = await playerAuth.playerFetch('/player/me/discord-code', { method: 'POST' })
    if (!res) { bindError.value = '網路錯誤，請稍後再試'; return }
    const data = await res.json().catch(() => null)
    if (res.ok && data?.success) {
      bindCode.value = data.code
      bindCodeExpiresAt.value = data.expires_at
    } else {
      bindError.value = data?.message
        || (res.status === 429 ? '產生太頻繁，請稍等一分鐘再試' : '產生綁定碼失敗')
    }
  } finally {
    issuingCode.value = false
  }
}

function logout() {
  playerAuth.clearAuth()
  router.push(PLAYER_LOGIN_PATH)
}

// ── 地點清單（給新增物品的地點下拉選單用） ─────────────────────
// 來源有兩個：資料庫裡已經用過的地點（/inventory/locations），加上
// 遊戲已知的地點名稱（翻譯表裡的星系／星球／降落點…，即使還沒有人登記過庫存也能選）。
const locations = ref([])
async function loadLocations() {
  const [res, known] = await Promise.all([
    playerAuth.playerFetch('/inventory/locations'),
    loadKnownLocations(),
  ])
  const data = res ? await res.json().catch(() => null) : null
  const used = (res?.ok && data?.success) ? (data.data || []) : []
  locations.value = [...new Set([...used, ...known])].sort()
}

// ── 「查詢」頁分頁篩選欄位要用的類型清單（各自進分頁時才載，見 loadForTab）──
const itemTypes = ref([])
async function loadItemTypes() {
  const res = await playerAuth.playerFetch('/item/types')
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) itemTypes.value = data.data || []
}

const blueprintOutputTypes = ref([])
async function loadBlueprintOutputTypes() {
  const res = await playerAuth.playerFetch('/blueprint/master/types')
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) blueprintOutputTypes.value = data.data || []
}

// ── 新增／庫存異動（多筆，共用同一套 row 結構） ──────────────────
//
// 「新增」= 登記還沒有的物品，一律是增加，所以沒有 direction。
// 「庫存異動」= 對已登記的物品調整數量，每列各自可選增加或減少
//   （direction 只有 withNote 的那組會用到，見 submitRows 的 endpointFor）。
let rowKeySeq = 0
function makeRow(withNote = false) {
  return {
    key: ++rowKeySeq,
    itemQuery: '', itemResults: [], selectedItem: null,
    quantity: 1,
    // row 不帶地點欄位：新增與庫存異動的地點都是整批共用的一份
    // （depositLocation / withdrawLocation），放在表單最上面。
    note: withNote ? '' : undefined,
    // 預設「減少」：庫存異動是從原本的「取出」演化來的，
    // 多數情境還是扣庫存，增加的情境有專門的「新增」分頁。
    direction: withNote ? 'out' : 'in',
    error: '',
  }
}
const depositRows       = reactive([makeRow(false)])
const depositSubmitting = ref(false)
const depositSuccess    = ref('')
const depositError      = ref('')

// 「新增」共用的地點。刻意做成跟 row 一樣的形狀（location /
// locationResults / locationOpen），這樣 filterRowLocations、
// closeRowLocations、pickRowLocation 三個 helper 可以原封不動重用。
const depositLocation = reactive({ location: '', locationResults: [], locationOpen: false })

// 一填了地點就把「請先選地點」的錯誤收掉。不收的話畫面上會同時出現
// 紅色的「請先在最上面輸入或選擇地點」跟它下面綠色的「以下 3 筆都會登記到
// Area18」，互相矛盾。
watch(() => depositLocation.location, (v) => {
  if (v.trim()) depositError.value = ''
})

const withdrawRows       = reactive([makeRow(true)])
const withdrawSubmitting = ref(false)
const withdrawSuccess    = ref('')
const withdrawError      = ref('')

// 「庫存異動」共用的地點，跟 depositLocation 同樣的形狀與理由
const withdrawLocation = reactive({ location: '', locationResults: [], locationOpen: false })

watch(() => withdrawLocation.location, (v) => {
  if (v.trim()) withdrawError.value = ''
})

const searchTimers = new Map()

function searchRowItems(row) {
  row.selectedItem = null
  clearTimeout(searchTimers.get(row.key))
  const q = row.itemQuery.trim()
  if (!q) { row.itemResults = []; return }
  searchTimers.set(row.key, setTimeout(async () => {
    const res = await playerAuth.playerFetch(`/item/search?q=${encodeURIComponent(q)}`)
    if (!res) return
    const data = await res.json().catch(() => null)
    row.itemResults = (res.ok && data?.success) ? (data.data || []) : []
  }, 300))
}

function pickRowItem(row, it) {
  row.selectedItem = it
  row.itemQuery = it.name
  row.itemResults = []
}

function filterRowLocations(row) {
  const q = row.location.trim().toLowerCase()
  // 同時比對英文（loc 本身）跟中文對照（locZh），方便直接打中文搜尋地點
  row.locationResults = q
    ? locations.value.filter(loc =>
        loc.toLowerCase().includes(q) || locZh(loc).includes(row.location.trim())
      ).slice(0, 20)
    : locations.value.slice(0, 20)
  row.locationOpen = true
}

function closeRowLocations(row) {
  // 延遲關閉，讓點擊選項的 click/mousedown 先觸發（不然 blur 會比 click 早跑，選不到）
  setTimeout(() => { row.locationOpen = false }, 150)
}

function pickRowLocation(row, loc) {
  row.location = loc
  row.locationResults = []
  row.locationOpen = false
}

// endpointFor 是 function 而不是固定字串：庫存異動同一次送出可能有幾列增加、
// 幾列減少，端點要逐列決定（後端沒有「帶正負號的 delta」這種 API，
// 增減是 /player/inventory/add 與 /remove 兩支，見 app/player/view.py）。
async function submitRows(rows, {
  endpointFor, verbFor, location, resultRef, submittingRef, withNote, makeNextRow,
}) {
  resultRef.value = ''
  // 地點是整批共用的一份，兩個呼叫端都已經在表單層級擋掉空值
  // （才不會在每一列都印一次同樣的訊息）。這裡只是不信任呼叫端的保險。
  if (!location) return
  let ok = 0
  const successNames = []

  // 先拍快照再驗證與送出。
  //
  // 不拍快照的話 `for...of` 迭代的是 reactive 陣列本身，而迭代器每次 next()
  // 都重讀 length —— 使用者在某一列還在 await 時按「再加一筆」，那個從未經過
  // 驗證的空白列會被同一個迴圈掃到，`row.selectedItem._id` 對 null 取屬性丟出
  // TypeError。而 Vue 3 的 callWithAsyncErrorHandling 會把它 .catch() 掉降級成
  // console.error，所以畫面上**完全沒有徵兆**：前幾筆其實已經寫進後端了，
  // 但成功訊息沒出現、列也沒被清掉，使用者幾乎一定會再按一次造成重複入庫。
  // （下面的按鈕也一併 disabled，這裡的快照是第二道防線。）
  const batch = [...rows]

  for (const row of batch) {
    row.error = ''
    if (!row.selectedItem) { row.error = '請先從搜尋結果選擇物品'; continue }
    if (!row.quantity || row.quantity <= 0) { row.error = '數量必須大於 0'; continue }
  }
  if (batch.some(r => r.error)) return

  submittingRef.value = true
  try {
    for (const row of batch) {
      const body = {
        item: row.selectedItem._id,
        quantity: row.quantity,
        location,
      }
      if (withNote) body.note = (row.note || '').trim()

      const res = await playerAuth.playerFetch(endpointFor(row), {
        method: 'POST',
        body: JSON.stringify(body),
      })
      if (!res) { row.error = '網路錯誤，請稍後再試'; continue }
      const data = await res.json().catch(() => null)
      if (res.ok && data?.success) {
        ok += 1
        const d = data.data.delta
        successNames.push(
          `${data.data.item_name} ${d > 0 ? '+' : '-'}${Math.abs(d)} @ ${data.data.location}`)
      } else {
        row.error = data?.message || `${verbFor(row)}失敗`
      }
    }
  } finally {
    submittingRef.value = false
  }

  if (ok) {
    resultRef.value = `已處理 ${ok} 筆：${successNames.join('；')}`
    // 只清掉「這一批裡送成功的」，失敗的留著讓玩家修正。
    //
    // 判斷條件必須同時看「有沒有在 batch 裡」和「有沒有 error」：只看 error 的話，
    // 送出期間才被加進來、根本沒被處理過的空白列（error 也是空的）會被當成
    // 成功而清掉，使用者剛打的東西就這樣消失。
    const done = new Set(batch.filter(r => !r.error))
    for (let i = rows.length - 1; i >= 0; i--) {
      if (done.has(rows[i])) rows.splice(i, 1)
    }
    if (!rows.length) rows.push(makeNextRow())
    loadMyInventory()
    loadLocations()
    loadHistory()
  }
}

// 倉庫 › 新增：一律是增加，沒有方向可選；地點是整批共用的一份
function submitDepositRows() {
  depositError.value = ''
  const loc = depositLocation.location.trim()
  if (!loc) {
    depositError.value = '請先在最上面輸入或選擇地點。'
    return
  }
  return submitRows(depositRows, {
    endpointFor: () => '/player/inventory/add',
    verbFor:     () => '新增',
    location:    loc,
    // 刻意不清掉 depositLocation，方便在同一個地點繼續加下一批
    makeNextRow: () => makeRow(false),
    resultRef: depositSuccess, submittingRef: depositSubmitting, withNote: false,
  })
}

// 倉庫 › 庫存異動：地點整批共用，方向逐列各自選
function submitWithdrawRows() {
  withdrawError.value = ''
  const loc = withdrawLocation.location.trim()
  if (!loc) {
    withdrawError.value = '請先在最上面輸入或選擇地點。'
    return
  }
  return submitRows(withdrawRows, {
    endpointFor: (row) => row.direction === 'in'
      ? '/player/inventory/add'
      : '/player/inventory/remove',
    verbFor:     (row) => row.direction === 'in' ? '增加' : '減少',
    location:    loc,
    // 同樣不清掉 withdrawLocation，方便繼續調同一個地點的下一批
    makeNextRow: () => makeRow(true),
    resultRef: withdrawSuccess, submittingRef: withdrawSubmitting, withNote: true,
  })
}

// ── 篩選區（倉庫 › 物品庫存／庫存紀錄 各自一份狀態）────────────────
//
// 兩份刻意分開：在庫存頁篩「Laranite @ Area18」之後切到紀錄頁，
// 通常是想看全部歷史，不是延續同一組條件。共用一份會很煩。
// '' = 全部。用 item_id 比對而不是名稱，見 InventoryFilterBar 的說明。
const stockFilter   = reactive({ item: '', location: '' })
const historyFilter = reactive({ item: '', location: '' })

function applyFilter(rows, f) {
  return rows.filter(r =>
    (!f.item     || r.item_id  === f.item) &&
    (!f.location || r.location === f.location)
  )
}

// ── 我的個人庫 ────────────────────────────────────────────────
const myInventory      = ref([])
const loadingInventory = ref(false)
const filteredInventory = computed(() => applyFilter(myInventory.value, stockFilter))

async function loadMyInventory() {
  loadingInventory.value = true
  const res = await playerAuth.playerFetch('/player/inventory')
  loadingInventory.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) myInventory.value = data.data || []
}

// ── 庫存紀錄（增加／減少歷史） ────────────────────────────────
const history        = ref([])
const loadingHistory  = ref(false)
const filteredHistory = computed(() => applyFilter(history.value, historyFilter))

async function loadHistory() {
  loadingHistory.value = true
  const res = await playerAuth.playerFetch('/player/inventory/history?limit=100')
  loadingHistory.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) history.value = data.data || []
}

// ── 藍圖（規格書第 5 節，跟 inventory 分開的獨立名冊） ────────────
// 玩家自助只填藍圖與備註。「狀態」不開放給玩家選 —— 登記的意思本來就是
// 「我有這張圖」，所以一律送 obtained（已取得）。「取得方式」「取得地點」
// 同理：欄位還留在後端模型跟後台管理頁（BlueprintFormModal.vue），
// 管理員仍可設定其他狀態，玩家端只是不顯示、也不送。
const PLAYER_BLUEPRINT_STATUS = 'obtained'

const blueprints           = ref([])
const loadingBlueprints    = ref(false)
// blueprint_uuid 對應遊戲藍圖主檔（blueprint_master）。
// 有值＝從自動完成選的，名稱以主檔為準；空值＝自由輸入。
const blueprintForm        = reactive({ name: '', notes: '', blueprint_uuid: '' })
const blueprintSubmitting  = ref(false)
const blueprintError       = ref('')
const blueprintSuccess     = ref('')

// 標籤留著：管理員從後台設過其他狀態的紀錄，在「查詢 › 持有藍圖」還是要看得懂。
const BLUEPRINT_STATUS_LABELS = {
  locked: '🔒 未取得', obtained: '📘 已取得', unlocked: '✅ 已解鎖',
  unconfirmed: '❓ 未確認', outdated: '⚠️ 已過時',
}
/** 只在狀態不是預設的 obtained 時回標籤，否則回 ''。
 *
 * 玩家登記的一律是 obtained，每一列都印「📘 已取得」等於整欄同一個值，
 * 是純噪音；但管理員設過的 locked／outdated 仍然值得標出來。 */
function blueprintStatusLabel(v) {
  if (!v || v === PLAYER_BLUEPRINT_STATUS) return ''
  return BLUEPRINT_STATUS_LABELS[v] || v
}

async function loadBlueprints() {
  loadingBlueprints.value = true
  const res = await playerAuth.playerFetch('/player/blueprints')
  loadingBlueprints.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) blueprints.value = data.data || []
}

async function submitBlueprint() {
  blueprintError.value = ''
  blueprintSuccess.value = ''
  if (!blueprintForm.blueprint_uuid) {
    blueprintError.value = '請先從清單中選擇藍圖'
    return
  }
  const name = blueprintForm.name.trim()

  blueprintSubmitting.value = true
  try {
    const res = await playerAuth.playerFetch('/player/blueprints', {
      method: 'POST',
      body: JSON.stringify({
        // blueprint_uuid 是後端唯一認的欄位（見 app/player/view.py 的
        // add_my_blueprint）—— 名稱一律以主檔為準，不看這裡傳什麼，
        // 但還是一起送出方便看 network log 對照。
        blueprint_uuid: blueprintForm.blueprint_uuid,
        name,
        // 玩家端不開放選狀態，一律「已取得」
        unlock_status: PLAYER_BLUEPRINT_STATUS,
        notes: blueprintForm.notes,
      }),
    })
    if (!res) { blueprintError.value = '網路錯誤，請稍後再試'; return }
    const data = await res.json().catch(() => null)
    if (res.ok && data?.success) {
      blueprintSuccess.value = `已登記「${name}」`
      // 一併清掉 blueprint_uuid 與搜尋框，否則登記成功後綠色勾勾還留著、
      // 「登記藍圖」按鈕仍可按，會重複送出同一張圖。
      clearBlueprintMaster()
      blueprintForm.notes = ''
      loadBlueprints()
    } else {
      blueprintError.value = data?.message || '登記失敗，請稍後再試'
    }
  } finally {
    blueprintSubmitting.value = false
  }
}

// ── 藍圖選擇器（blueprint_master，1,600+ 筆遊戲配方）─────────────────
//
// 這裡刻意**只能從主檔選**，不接受自由輸入。原因是同一張藍圖若每個人
// 自己打字，就會出現「Omnisky III」「omnisky 3」好幾種寫法，
// 「誰有這張圖」（查詢 › 持有藍圖）就分不成同一組。
//
// 因此搜尋框的文字（bpQuery）跟實際要送出的值（blueprintForm.name /
// blueprint_uuid）是**分開的兩份狀態** —— 使用者在搜尋框打的字不會直接
// 變成登記的名稱，只有點選清單項目才會寫進 form。
const bpQuery      = ref('')
const bpResults    = ref([])
const bpOpen       = ref(false)
let bpSearchTimer  = null

// 主檔筆數。0 表示還沒同步過 —— 這時候給明確提示，
// 而不是一個永遠搜不到東西的輸入框。null = 還沒查。
const masterCount = ref(null)

async function loadMasterCount() {
  const res = await playerAuth.playerFetch('/blueprint/master?limit=1')
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) masterCount.value = data.total ?? 0
}

function searchBlueprintMaster() {
  const q = bpQuery.value.trim()
  bpOpen.value = true

  clearTimeout(bpSearchTimer)
  if (q.length < 2) { bpResults.value = []; return }

  bpSearchTimer = setTimeout(async () => {
    const res = await playerAuth.playerFetch(
      `/blueprint/master/search?q=${encodeURIComponent(q)}&limit=20`)
    if (!res) return
    const data = await res.json().catch(() => null)
    bpResults.value = (res.ok && data?.success) ? (data.data || []) : []
  }, 300)
}

function closeBlueprintResults() {
  // 延遲關閉，否則 blur 會搶在清單項目的 mousedown 之前把清單收掉
  setTimeout(() => { bpOpen.value = false }, 150)
}

function pickBlueprintMaster(bp) {
  blueprintForm.name = bp.name
  blueprintForm.blueprint_uuid = bp._id
  bpQuery.value = bp.name
  bpResults.value = []
  bpOpen.value = false
}

function clearBlueprintMaster() {
  blueprintForm.blueprint_uuid = ''
  blueprintForm.name = ''
  bpQuery.value = ''
  bpResults.value = []
}

// ── 展開某張藍圖的完整配方（點「N 種」材料時才抓，不預載）──────────
const recipeFor     = ref(null)
const recipe        = ref(null)
const loadingRecipe = ref(false)

async function showRecipe(bp) {
  // 再點一次收起來
  if (recipeFor.value === bp._id) {
    recipeFor.value = null
    recipe.value = null
    return
  }
  recipeFor.value = bp._id
  recipe.value = null
  loadingRecipe.value = true

  const res = await playerAuth.playerFetch(`/blueprint/master/${bp.blueprint_uuid}`)
  loadingRecipe.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) recipe.value = data.data
}

// ── 查詢 › 持有藍圖：誰登記了這張藍圖 ──────────────────────────
// 這是藍圖版的 /inventory/where —— 查的是別人的名冊，不是自己的。
//
// 5 個欄位（藍圖名稱／藍圖類型／玩家id／玩家暱稱，AND 語意，見
// Blueprint.find_holders 的說明）都是「選定才算數」的 autocomplete——
// 純打字不會觸發查詢，只有從候選清單選一個才會。沒有任何欄位選定時預設
// 瀏覽全部（維持舊版單一輸入框留空＝列出全部的行為），不像物品庫存要求
// 至少一個篩選條件。
const bpHolders        = ref([])
const loadingBpHolders = ref(false)

const bpNameText        = ref('')
const bpSelectedName    = ref('')   // 送給 /blueprint/holders 的 q——用主檔的
                                     // 英文 name，因為玩家登記時一律存主檔
                                     // name（見 app/player/view.py 的
                                     // add_my_blueprint），用它比對最準確
// 「藍圖類型」可多選（取聯集）
const bpSelectedTypes   = ref([])
const blueprintTypeOptions = computed(() =>
  blueprintOutputTypes.value.map(t => ({ value: t, label: blueprintTypeLabel(t) })))
const bpPlayerIdText       = ref('')
const bpPlayerNicknameText = ref('')
const bpPlayerScid         = ref('')

let bpHolderSeq = 0
async function loadBlueprintHolders() {
  const seq = ++bpHolderSeq
  loadingBpHolders.value = true
  const params = new URLSearchParams({ limit: '100' })
  if (bpSelectedName.value) params.set('q', bpSelectedName.value)
  bpSelectedTypes.value.forEach(t => params.append('output_type', t))
  if (bpPlayerScid.value) params.set('player_id', bpPlayerScid.value)
  const res = await playerAuth.playerFetch(`/blueprint/holders?${params.toString()}`)
  if (seq !== bpHolderSeq) return   // 已經有更新的查詢在跑了
  loadingBpHolders.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  bpHolders.value = (res.ok && data?.success) ? (data.data || []) : []
}

watch([bpSelectedName, bpSelectedTypes, bpPlayerScid], loadBlueprintHolders)

async function searchBlueprintNames(q) {
  const res = await playerAuth.playerFetch(`/blueprint/master/search?q=${encodeURIComponent(q)}&limit=20`)
  if (!res) return []
  const data = await res.json().catch(() => null)
  return (res.ok && data?.success) ? (data.data || []) : []
}
function blueprintNameLabel(c) { return c.name_zh || c.name }


function onBpNameSelect(c) { bpSelectedName.value = c ? c.name : '' }

// 玩家id／玩家暱稱兩個欄位共用同一個 bpPlayerScid（實際送出的篩選值）——
// 兩個欄位各自都能選，選定其中一個會同步另一個欄位的顯示文字，避免
// 「id 選了甲、暱稱又獨立選了乙」這種矛盾組合永遠查不到東西。任一欄位
// 重新打字（尚未選定新候選）會讓兩邊的選定都失效，見 AutocompleteField
// 的 @select(null) 語意。
function onBpPlayerIdSelect(c) {
  if (c) {
    bpPlayerScid.value = c.star_citizen_id
    bpPlayerNicknameText.value = c.nickname || c.player_name || ''
  } else {
    bpPlayerScid.value = ''
    bpPlayerNicknameText.value = ''
  }
}
function onBpPlayerNicknameSelect(c) {
  if (c) {
    bpPlayerScid.value = c.star_citizen_id
    bpPlayerIdText.value = c.star_citizen_id
  } else {
    bpPlayerScid.value = ''
    bpPlayerIdText.value = ''
  }
}

function clearBpFilters() {
  bpNameText.value = ''
  bpSelectedName.value = ''
  bpSelectedTypes.value = []
  bpPlayerIdText.value = ''
  bpPlayerNicknameText.value = ''
  bpPlayerScid.value = ''
}

async function removeBlueprint(bp) {
  const res = await playerAuth.playerFetch(`/player/blueprints/${bp._id}`, { method: 'DELETE' })
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) loadBlueprints()
}

// ── 查詢 › 物品庫存：物品名稱／類型／地點／玩家id／玩家暱稱，AND 篩選 ──
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
const loadingWho = ref(false)

const itemsNameText       = ref('')
const itemsSelectedItemId = ref(null)
// 「物品類型」「物品地點」可多選（同一欄位內取聯集，欄位之間 AND）
const itemsSelectedTypes     = ref([])
const itemsSelectedLocations = ref([])
const locationOptions = computed(() =>
  locations.value.map(loc => ({ value: loc, label: locLabel(loc) })))
const itemsPlayerIdText       = ref('')
const itemsPlayerNicknameText = ref('')
const itemsPlayerScid         = ref('')

const hasStockFilter = computed(() => !!(
  itemsSelectedItemId.value || itemsSelectedTypes.value.length ||
  itemsSelectedLocations.value.length || itemsPlayerScid.value
))

// 每次搜尋遞增。慢的舊請求回來時若序號已過期就丟掉。
let whoSeq = 0

async function runStockSearch() {
  if (!hasStockFilter.value) {
    whoRows.value = []
    loadingWho.value = false
    return
  }
  const seq = ++whoSeq
  loadingWho.value = true
  const params = new URLSearchParams({ limit: '200' })
  if (itemsSelectedItemId.value) params.set('item_id', itemsSelectedItemId.value)
  else itemsSelectedTypes.value.forEach(t => params.append('item_type', t))
  itemsSelectedLocations.value.forEach(loc => params.append('location', loc))
  if (itemsPlayerScid.value) params.set('player_id', itemsPlayerScid.value)
  const res = await playerAuth.playerFetch(`/inventory/search?${params.toString()}`)
  if (seq !== whoSeq) return          // 已經有更新的搜尋在跑了
  loadingWho.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  whoRows.value = (res.ok && data?.success) ? (data.data || []) : []
}

watch([itemsSelectedItemId, itemsSelectedTypes, itemsSelectedLocations, itemsPlayerScid], runStockSearch)

// 物品名稱／物品類型互斥（見上面的說明）：勾了類型就清掉已選的物品名稱
watch(itemsSelectedTypes, (types) => {
  if (types.length && itemsSelectedItemId.value) {
    itemsNameText.value = ''
    itemsSelectedItemId.value = null
  }
})

async function searchItemNames(q) {
  const res = await playerAuth.playerFetch(`/item/search?q=${encodeURIComponent(q)}&limit=20`)
  if (!res) return []
  const data = await res.json().catch(() => null)
  return (res.ok && data?.success) ? (data.data || []) : []
}
function itemNameLabel(c) { return c.name_zh || c.name }



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
      const res = await playerAuth.playerFetch('/player/search?limit=1000')
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
function playerCandidateLabel(c) { return c.nickname || c.player_name || c.star_citizen_id }

function onItemsNameSelect(c) {
  if (c) {
    itemsSelectedItemId.value = c._id
    itemsSelectedTypes.value = []
  } else {
    itemsSelectedItemId.value = null
  }
}

// 玩家id／玩家暱稱共用同一個 itemsPlayerScid，理由跟「持有藍圖」分頁的
// onBpPlayerIdSelect/onBpPlayerNicknameSelect 一樣（見那邊的說明）。
function onItemsPlayerIdSelect(c) {
  if (c) {
    itemsPlayerScid.value = c.star_citizen_id
    itemsPlayerNicknameText.value = c.nickname || c.player_name || ''
  } else {
    itemsPlayerScid.value = ''
    itemsPlayerNicknameText.value = ''
  }
}
function onItemsPlayerNicknameSelect(c) {
  if (c) {
    itemsPlayerScid.value = c.star_citizen_id
    itemsPlayerIdText.value = c.star_citizen_id
  } else {
    itemsPlayerScid.value = ''
    itemsPlayerIdText.value = ''
  }
}

function clearItemsFilters() {
  itemsNameText.value = ''
  itemsSelectedItemId.value = null
  itemsSelectedTypes.value = []
  itemsSelectedLocations.value = []
  itemsPlayerIdText.value = ''
  itemsPlayerNicknameText.value = ''
  itemsPlayerScid.value = ''
}

// sticky 分頁列的 top 偏移必須等於上方固定元素的實際高度：
//   主分頁列 top = 工具列高度
//   下層分頁 top = 工具列 + 主分頁列高度
// 兩者在窄螢幕都會變（工具列會折行），所以不能寫死 —— 用 ResizeObserver 量。
let stickyObserver = null

function trackStickyHeights() {
  if (typeof ResizeObserver === 'undefined') return
  const bar = document.querySelector('.scifi-topbar')
  const tabsEl = document.querySelector('.scifi-tabs')
  if (!bar) return

  const sync = () => {
    const root = document.documentElement
    root.style.setProperty(
      '--sf-topbar-h', `${Math.round(bar.getBoundingClientRect().height)}px`)
    if (tabsEl) {
      root.style.setProperty(
        '--sf-tabs-h', `${Math.round(tabsEl.getBoundingClientRect().height)}px`)
    }
  }
  sync()
  stickyObserver = new ResizeObserver(sync)
  stickyObserver.observe(bar)
  if (tabsEl) stickyObserver.observe(tabsEl)
}

// ── 艦隊 › 我的艦隊 ──────────────────────────────────────────
const fleet            = ref([])
const loadingFleet     = ref(false)
const fleetLoaded      = ref(false)
const fleetError       = ref('')
const fleetMaxQuantity = ref(99)
const savingFleetId    = ref('')
const fleetBulkRef     = ref(null)
const fleetShipCount   = computed(() => fleet.value.reduce((n, r) => n + (r.quantity || 0), 0))

function showFleetError(text) {
  fleetError.value = text
  setTimeout(() => { if (fleetError.value === text) fleetError.value = '' }, 6000)
}

async function loadFleet() {
  loadingFleet.value = true
  const res = await playerAuth.playerFetch('/player/fleet')
  loadingFleet.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) {
    fleet.value = data.data || []
    fleetMaxQuantity.value = data.max_quantity || 99
    fleetLoaded.value = true
  } else {
    showFleetError(data?.message || '讀取艦隊失敗，請稍後再試')
  }
}

async function updateFleetQuantity(row, event) {
  const input = event.target
  const qty = Math.trunc(Number(input.value))
  if (!Number.isFinite(qty) || qty < 1 || qty > fleetMaxQuantity.value) {
    input.value = row.quantity   // 不合法就還原，不送出
    showFleetError(`數量要介於 1 到 ${fleetMaxQuantity.value} 之間。`)
    return
  }
  if (qty === row.quantity) return
  savingFleetId.value = row._id
  const res = await playerAuth.playerFetch(`/player/fleet/${row._id}`, {
    method: 'PUT', body: JSON.stringify({ quantity: qty }),
  })
  savingFleetId.value = ''
  const data = res ? await res.json().catch(() => null) : null
  if (res?.ok && data?.success) {
    row.quantity = qty
  } else {
    input.value = row.quantity
    showFleetError(data?.message || '更新數量失敗，請稍後再試')
  }
}

async function removeFleet(row) {
  const res = await playerAuth.playerFetch(`/player/fleet/${row._id}`, { method: 'DELETE' })
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) {
    await loadFleet()
    fleetBulkRef.value?.refresh()   // 批量登記頁的「已登記」標記也要跟著解除
  } else {
    showFleetError(data?.message || '刪除失敗，請稍後再試')
  }
}

// ── 查詢 › 船艦搜尋：誰有哪款船 ──────────────────────────────
//
// 船艦名稱／類型／尺寸／廠商／角色／玩家id／玩家暱稱，AND 語意，打
// /player/fleet/holders。跟「持有藍圖」一樣：都沒選定時列出全部人的艦隊，
// 欄位要從候選清單選定才算數（純打字不觸發查詢）。
const fleetHolders        = ref([])
const loadingFleetHolders = ref(false)
const vehicleFacets       = ref({ size_classes: [], types: [], manufacturers: [], roles: [] })
let vehicleFacetsLoaded = false

const flNameText           = ref('')
const flSelectedVehicleId  = ref('')
// 類型／尺寸／廠商／角色可多選（同一欄位內取聯集，欄位之間 AND）
const flSelectedTypes      = ref([])
const flSelectedSizes      = ref([])
const flSelectedMfrs       = ref([])
const flSelectedRoles      = ref([])
const vehicleSizeOptions = computed(() =>
  vehicleFacets.value.size_classes.map(n => ({ value: String(n), label: vehicleSizeLabel(n) })))
const manufacturerOptions = computed(() =>
  vehicleFacets.value.manufacturers.map(m => ({ value: m.value, label: manufacturerLabel(m.label, m.value) })))
const flPlayerIdText       = ref('')
const flPlayerNicknameText = ref('')
const flPlayerScid         = ref('')

async function loadVehicleFacets() {
  vehicleFacetsLoaded = true
  const res = await playerAuth.playerFetch('/item/vehicles/facets')
  const data = res ? await res.json().catch(() => null) : null
  if (res?.ok && data?.success) vehicleFacets.value = { ...vehicleFacets.value, ...(data.data || {}) }
  else vehicleFacetsLoaded = false   // 下次進來再試
}

let fleetHolderSeq = 0
async function loadFleetHolders() {
  const seq = ++fleetHolderSeq
  loadingFleetHolders.value = true
  const params = new URLSearchParams({ limit: '100' })
  if (flSelectedVehicleId.value) params.set('vehicle_id', flSelectedVehicleId.value)
  flSelectedTypes.value.forEach(v => params.append('type', v))
  flSelectedSizes.value.forEach(v => params.append('size_class', v))
  flSelectedMfrs.value.forEach(v => params.append('manufacturer_code', v))
  flSelectedRoles.value.forEach(v => params.append('role', v))
  if (flPlayerScid.value) params.set('player_id', flPlayerScid.value)
  const res = await playerAuth.playerFetch(`/player/fleet/holders?${params.toString()}`)
  if (seq !== fleetHolderSeq) return   // 已經有更新的查詢在跑了
  loadingFleetHolders.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  fleetHolders.value = (res.ok && data?.success) ? (data.data || []) : []
}

watch([flSelectedVehicleId, flSelectedTypes, flSelectedSizes, flSelectedMfrs, flSelectedRoles, flPlayerScid],
  loadFleetHolders)

async function searchVehicleNames(q) {
  const res = await playerAuth.playerFetch(`/item/vehicles?q=${encodeURIComponent(q)}&limit=20`)
  if (!res) return []
  const data = await res.json().catch(() => null)
  return (res.ok && data?.success) ? (data.data || []) : []
}


// 玩家id／玩家暱稱共用 flPlayerScid，理由同「持有藍圖」的 onBpPlayerIdSelect
function onFlPlayerIdSelect(c) {
  flPlayerScid.value = c ? c.star_citizen_id : ''
  flPlayerNicknameText.value = c ? (c.nickname || c.player_name || '') : ''
}
function onFlPlayerNicknameSelect(c) {
  flPlayerScid.value = c ? c.star_citizen_id : ''
  flPlayerIdText.value = c ? c.star_citizen_id : ''
}

function clearFleetFilters() {
  flNameText.value = '';  flSelectedVehicleId.value = ''
  flSelectedTypes.value = []
  flSelectedSizes.value = []
  flSelectedMfrs.value = []
  flSelectedRoles.value = []
  flPlayerIdText.value = ''; flPlayerNicknameText.value = ''; flPlayerScid.value = ''
}

// 畫面上會出現的地點都查一次翻譯（地點清單、個人庫存、異動紀錄、查詢結果）；
// 查過的有快取，不會重複打 API
watch([locations, myInventory, history, whoRows], () => {
  loadTranslations('location', [
    ...locations.value,
    ...myInventory.value.map(r => r.location),
    ...history.value.map(r => r.location),
    ...whoRows.value.map(r => r.location),
  ])
})

onMounted(() => {
  scifiTheme.apply()      // 套用這位玩家自己存的配色（localStorage）
  trackStickyHeights()
  loadPlayer()
  loadLocations()
  loadMyInventory()
  loadHistory()
  loadBlueprints()
  // 直接以 ?tab=blueprints / ?tab=search&sub=blueprints 開場時補載
  loadForTab(activeTab.value, activeSub.value)
})

onBeforeUnmount(() => {
  stickyObserver?.disconnect()
})
</script>

<style scoped>
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
.nav-tabs .nav-link { cursor: pointer; }
</style>
