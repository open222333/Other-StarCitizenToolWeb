<!--
  玩家個人頁（需要玩家登入，不是後台登入）。滿版版面，4 個主分頁：

  - 倉庫（我自己的物品，看現況也在這裡動；一頁，下面三個用按鈕展開，比照艦隊）
      · 物品庫存：目前登記了哪些物品。上方有共用搜尋卡（物品名稱／物品類型／星系／行星／地點）
      · 物品資料：瀏覽物品主檔（名稱、類型、數值、購買地點），唯讀
      · 商品購買地點：勾選多種商品，列出全部都買得到的交易終端（原本在「查詢」）
      · 新增／異動：一次增減多筆，每列各自可選「＋增加」或「－減少」
        （原本的「新增物品」「庫存異動」合併；增加一個還沒登記的物品就是新增）
      · 庫存紀錄：增加／減少的歷史。上方同樣有篩選區
  - 藍圖：自己的藍圖名冊，可增刪（一頁；「登記藍圖資料」用按鈕展開，原本的藍圖資料＋批量登記合併）。**只能從主檔選**，不接受自由輸入
    （見 src/models/blueprint.py 與 app/player/view.py 的 add_my_blueprint）。
    玩家端不顯示也不選「狀態」—— 登記的意思就是「我有這張圖」，一律送
    obtained（已取得）。後端與後台管理頁仍保留完整的 UNLOCK_STATUSES，
    管理員設過的非 obtained 狀態在「查詢 › 持有藍圖」還是會標出來。
  - 查詢持有資訊（原「查詢」；別人的東西，唯讀）
      一個區塊：一張搜尋卡（名稱、玩家、種類＋單一種類的專用條件）＋一張整合列表（物品／藍圖／船艦，不屬於那一類的欄位留空）
      · 持有物品（公會庫＋所有玩家個人庫，見 app/inventory/view.py 的 search_stock）
      · 持有藍圖：某張藍圖誰登記了
      · 持有船艦：誰有哪款船
  - 個人資料：暱稱／Discord／備註可以自己改，遊戲ID（star_citizen_id）不開放修改
    （它同時是 inventory.player / discord_bindings.handle 的鍵值，改了個人庫存會對不起來）

  Discord 有一個「公開給其他玩家」的勾選（discord_public，預設 false）。
  勾了之後別人在「查詢」的結果裡才看得到聯絡方式，用意是「找到有這張圖的人
  去問他能不能幫做」。遮蔽是在**後端**做的（見 Player.display_names_by_scid
  與 Blueprint._redact_contact），前端只判斷「有沒有拿到值」，不自己解讀旗標。

  「新增／異動」是跳出視窗（components/StockWizard.vue）：先選地點、再勾物品（數量不限）、最後設定數量送出。

  地點的搜尋一律是「星系／行星／地點」三段（utils/locationArea.js、
  components/LocationAreaFilter.vue）。

  兩張查詢表格的「持有者」都顯示成「暱稱（遊戲ID）」（見 holderLabel）。
  物品那張的 nickname 是後端 /inventory/where 補的 ——
  inventory.player 只存 RSI handle，沒有暱稱（見 Player.display_names_by_scid）。

  畫面上不放固定的使用說明（CLAUDE.md 介面文字原則；工具網站的連結描述直接顯示在卡片上）。
  會隨狀態變的訊息（「以下 3 筆都會登記到
  Area18」、「顯示 2 / 3 筆」、選中物品的綠色勾勾）留在原地常駐顯示。

  藍圖刻意獨立在頂層，不塞進倉庫：它是布林狀態的名冊（有／沒有這張圖），
  跟數量會變動的庫存物品不是同一種東西（見 src/models/blueprint.py 的開頭說明）。
  它跟「查詢 › 持有藍圖」的分界是**資料範圍**：這裡是我的、可寫入，
  查詢那邊是全部玩家的、唯讀。

  版面：.scifi-app（滿版）+ sticky 頂端工具列 + 分頁列（放不下時折行）+ 下層分頁，
  配色由 stores/scifiTheme.js 管，玩家可自行更換（ScifiThemePicker）。
  分頁狀態同步在 URL 的 ?tab= 與 ?sub=。
-->
<template>
  <div class="scifi-page scifi-app has-bottom-nav">
    <!-- ══════════ 跳出視窗（v-show 一直掛著；登記藍圖／船艦資料的搜尋卡用 Teleport defer 移進來）══════════ -->
    <!-- 定居點（頂端名字右邊的按鈕）：從可選居住地（/starmap/home-locations）選一個，下面是「全部物品轉移到定居點」 -->
    <SfModal id="home" v-model:open="homeOpen" title="定居點" icon="bi bi-house">
      <div v-if="homeMessage" :class="['alert', 'py-2', homeMessageType]">{{ homeMessage }}</div>
      <div class="card scifi-card">
        <div class="card-body py-3">
          <div class="row g-2 align-items-end">
            <div class="col-12 col-md-6">
              <label class="form-label small fw-semibold mb-1" for="home-select">定居點</label>
              <select id="home-select" v-model="homeDraft" class="form-select form-select-sm">
                <option value="">未設定</option>
                <optgroup v-for="g in homeGroups" :key="g.system" :label="g.system_zh ? `${g.system}（${g.system_zh}）` : g.system">
                  <option v-for="h in g.items" :key="h.name" :value="h.name">{{ homeOptionLabel(h) }}</option>
                </optgroup>
              </select>
            </div>
            <div class="col-12 col-md-6 d-flex gap-2">
              <button type="button" class="btn btn-sm btn-primary" :disabled="savingHome || homeDraft === (homeLocation || '')"
                @click="saveHome(homeDraft)">儲存</button>
              <button v-if="homeLocation" type="button" class="btn btn-sm btn-warning" :disabled="savingHome"
                @click="saveHome('')">清除定居點</button>
            </div>
          </div>
        </div>
      </div>
      <div v-if="homeLocation" class="card scifi-card mt-2">
        <div class="card-body py-3">
          <h4 class="sf-drawer__title mb-2"><i class="bi bi-box-arrow-in-down me-1"></i>全部物品轉移到定居點</h4>
          <div v-if="moveAllMessage" :class="['alert', 'py-2', moveAllMessageType]">{{ moveAllMessage }}</div>
          <div v-if="!moveAllPending.length" class="text-muted">所有物品都已經在 {{ locLabel(homeLocation) }}。</div>
          <template v-else>
            <div class="mb-2">
              將 {{ moveAllPending.length }} 筆、共 {{ moveAllUnits }} 件物品（來自 {{ moveAllSources }} 個地點）移到
              <span class="fw-semibold">{{ locLabel(homeLocation) }}</span>。
            </div>
            <button type="button" class="btn btn-sm btn-primary" :disabled="movingAll" @click="moveAllHome">
              <span v-if="movingAll" class="spinner-border spinner-border-sm me-1"></span>確定轉移
            </button>
          </template>
        </div>
      </div>
    </SfModal>
    <!-- 藍圖 › 登記藍圖資料：遊戲藍圖資料庫，點一列看配方與解鎖任務；每列「登記」，或勾選多張一次登記。
         上方是藍圖分頁的共用搜尋卡（開視窗時用 Teleport 移進來），舊網址 ?tab=blueprints&sub=data|bulk 一進來就打開 -->
    <SfModal id="bp-data" v-model:open="bpDataOpen" title="登記藍圖資料" icon="bi bi-journal-text" width="1440px">
      <div id="bp-modal-filters"></div>
      <BlueprintMasterBrowser player :fetcher="playerAuth.playerFetch" card-class="card scifi-card"
        :active="activeTab === 'blueprints' && bpDataOpen" :shared-filters="bpFilters"
        :registered-uuids="myBlueprintUuids" @registered="onBulkRegistered" />
    </SfModal>
    <!-- 任務 › 勢力聲望：勢力的聲望階級與每一階解鎖的任務（見 components/FactionReputation.vue） -->
    <SfModal id="faction-rep" v-model:open="factionRepOpen" title="勢力聲望" icon="bi bi-award" width="1100px">
      <FactionReputation :fetcher="playerAuth.playerFetch" :active="activeTab === 'missions' && factionRepOpen"
        :registered-uuids="myBlueprintUuids" @registered="onBulkRegistered" />
    </SfModal>
    <!-- 艦隊 › 編輯：數量（多艘同款）、每一艘的識別名稱與配件網址 -->
    <SfModal id="fleet-edit" v-model:open="fleetEditOpen" :title="fleetEditRow ? `編輯 ${fleetEditRow.vehicle?.name_zh || fleetEditRow.name}` : '編輯'"
      icon="bi bi-pencil-square" width="960px">
      <div v-if="fleetError" class="alert alert-danger py-2">{{ fleetError }}</div>
      <template v-for="row in (fleetEditRow ? [fleetEditRow] : [])" :key="row._id">
      <!-- 數量：－／＋ 一次加減 1，也可以直接輸入數字 -->
      <div class="d-flex flex-wrap align-items-center gap-2 mb-2">
        <label class="mb-0" :for="`fleet-qty-${row._id}`">數量</label>
        <div class="input-group input-group-sm myfleet-qty">
          <button type="button" class="btn btn-secondary" aria-label="減少 1 艘"
            :disabled="savingFleetId === row._id || row.quantity <= 1"
            @click="setFleetQuantity(row, row.quantity - 1)"><i class="bi bi-dash-lg"></i></button>
          <input :id="`fleet-qty-${row._id}`" type="number" min="1" :max="fleetMaxQuantity"
            class="form-control text-center" :value="row.quantity"
            :disabled="savingFleetId === row._id" @change="updateFleetQuantity(row, $event)">
          <button type="button" class="btn btn-success" aria-label="增加 1 艘"
            :disabled="savingFleetId === row._id || row.quantity >= fleetMaxQuantity"
            @click="setFleetQuantity(row, row.quantity + 1)"><i class="bi bi-plus-lg"></i></button>
        </div>
      </div>
      <!-- 每一艘一列：識別名稱公開在「查詢持有資訊」（玩家 · 識別名稱 · 配件碼），後台列表不放；
           配件網址設在每一艘上（「設置配件網址」），一樣公開給其他玩家 -->
      <template v-for="n in row.quantity" :key="n">
      <div class="sf-tree-leaf">
        <span class="sf-tree-title text-nowrap">第 {{ n }} 艘</span>
        <input :id="`unit-name-${row._id}-${n}`" type="text" class="form-control form-control-sm" style="max-width: 18rem"
          maxlength="50" placeholder="識別名稱" :value="row.unit_names?.[n - 1] || ''"
          :aria-label="`${row.vehicle?.name_zh || row.name} 第 ${n} 艘的識別名稱`"
          :disabled="savingFleetId === row._id" @keydown.enter="saveUnitName(row, n - 1, $event)">
        <!-- 輸入後按這個（或 Enter）才存 -->
        <button type="button" class="btn btn-sm btn-primary text-nowrap" :disabled="savingFleetId === row._id"
          @click="saveUnitNameFromInput(row, n)">設置識別名稱</button>
        <VehicleLoadoutLinks v-if="loadoutEditId !== `${row._id}:${n}` && row.unit_loadouts?.[n - 1]?.length"
          :links="row.unit_loadouts[n - 1]" button-class="btn-loadout" hide-label />
        <span class="ms-auto"></span>
        <!-- 設置按鈕放最右、用綠色，跟左邊已設好的網址按鈕（主題色）區分 -->
        <button type="button" class="btn btn-sm btn-success text-nowrap"
          :aria-expanded="loadoutEditId === `${row._id}:${n}` ? 'true' : 'false'"
          @click="toggleLoadoutEdit(row, n)">
          <i class="bi me-1" :class="loadoutEditId === `${row._id}:${n}` ? 'bi-x-lg' : 'bi-gear'"></i>設置配件網址
        </button>
        <!-- 好幾艘時可以只刪這一艘（只剩 1 艘時用船名右邊的刪除） -->
        <template v-if="row.quantity > 1 && confirmDeleteKey === `unit:${row._id}:${n}`">
          <span class="text-nowrap">確定刪除第 {{ n }} 艘？</span>
          <button type="button" class="btn btn-sm btn-danger text-nowrap" :aria-label="`確定刪除第 ${n} 艘`"
            :disabled="savingFleetId === row._id || deletingKey === `unit:${row._id}:${n}`" @click="removeFleetUnit(row, n)">
            <span v-if="deletingKey === `unit:${row._id}:${n}`" class="spinner-border spinner-border-sm me-1"></span>刪除
          </button>
          <button type="button" class="btn btn-sm btn-secondary text-nowrap"
            :disabled="deletingKey === `unit:${row._id}:${n}`" @click="confirmDeleteKey = ''">取消</button>
        </template>
        <button v-else-if="row.quantity > 1" type="button" class="btn btn-sm btn-danger text-nowrap"
          :aria-label="`刪除第 ${n} 艘`" :disabled="savingFleetId === row._id"
          @click="confirmDeleteKey = `unit:${row._id}:${n}`">
          <i class="bi bi-trash"></i>
        </button>
      </div>
      <div v-if="loadoutEditId === `${row._id}:${n}`" class="sf-tree-leaf d-block">
        <div class="mb-1">第 {{ n }} 艘的配件網址</div>
        <div v-for="(link, i) in loadoutDraft" :key="i" class="d-flex flex-wrap gap-2 mb-1">
          <input v-model="link.label" type="text" class="form-control form-control-sm loadout-label-input"
            placeholder="標籤（選填）" maxlength="50" :aria-label="`第 ${i + 1} 條標籤`">
          <input v-model="link.url" type="text" class="form-control form-control-sm loadout-url-input"
            placeholder="abcd1234 或 https://erkul.games/s/abcd1234" :aria-label="`第 ${i + 1} 條配件網址`">
          <!-- 預設公開（查詢持有資訊看得到）；關掉就只有自己看得到 -->
          <div class="form-check form-switch mb-0 align-self-center text-nowrap">
            <input :id="`loadout-public-${i}`" v-model="link.public" class="form-check-input" type="checkbox" role="switch">
            <label class="form-check-label" :for="`loadout-public-${i}`">公開</label>
          </div>
          <button type="button" class="btn btn-sm btn-danger" :aria-label="`移除第 ${i + 1} 條`"
            @click="loadoutDraft.splice(i, 1)"><i class="bi bi-x-lg"></i></button>
        </div>
        <div class="d-flex flex-wrap align-items-center gap-2 mt-1">
          <button v-if="loadoutDraft.length < 10" type="button" class="btn btn-sm btn-success"
            @click="loadoutDraft.push({ label: '', url: '', public: true })"><i class="bi bi-plus-lg me-1"></i>新增</button>
          <button type="button" class="btn btn-sm btn-primary" :disabled="savingFleetId === row._id"
            @click="saveLoadouts(row, n)">儲存</button>
          <button type="button" class="btn btn-sm btn-secondary" @click="loadoutEditId = ''">取消</button>
        </div>
      </div>
      </template>
      </template>
    </SfModal>
    <!-- 艦隊 › JSON 匯入：HangarXPLOR 匯出的機庫船單（見 components/FleetImport.vue）；每次打開都是新的匯入 -->
    <SfModal id="fleet-import" v-model:open="fleetImportOpen" title="JSON 匯入" icon="bi bi-filetype-json" width="960px">
      <FleetImport v-if="fleetImportOpen" :fetcher="playerAuth.playerFetch" card-class="card scifi-card" @imported="onFleetImported" />
    </SfModal>
    <!-- 艦隊 › 登記船艦資料：載具主檔＋官網價／遊戲內購買價／租船價，在這裡登記（單艘或勾選批量，
         components/VehicleDataBrowser.vue）；上方是艦隊分頁的共用搜尋卡（Teleport 移進來）；舊網址 ?tab=fleet&sub=data|bulk 直接打開 -->
    <SfModal id="fleet-data" v-model:open="fleetDataOpen" title="登記船艦資料" icon="bi bi-info-circle" width="1440px">
      <div id="fleet-modal-filters"></div>
      <VehicleDataBrowser :fetcher="playerAuth.playerFetch" :filters="fleetFilters"
        :registered-uuids="fleetVehicleUuids" :active="activeTab === 'fleet' && fleetDataOpen"
        @registered="loadFleet" />
    </SfModal>

    <!-- ══════════ 頂端工具列（捲動時固定） ══════════ -->
    <header class="scifi-topbar">
      <!-- 三欄：左邊空白、中間玩家名稱（置中）、右邊配色與登出 -->
      <span class="scifi-topbar__side" aria-hidden="true"></span>

      <div class="scifi-topbar__center">
        <h1 class="scifi-topbar__title">
          <i class="bi bi-person-badge"></i>
          <span>{{ player?.nickname || '個人資料' }}</span>
        </h1>
        <span v-if="player?.star_citizen_id" class="scifi-topbar__id d-none d-sm-inline">
          {{ player.star_citizen_id }}
        </span>
        <!-- 定居點：設定／清除＋全部物品轉移到定居點，都在跳出的視窗裡 -->
        <button v-if="player" type="button" class="btn btn-sm btn-success scifi-topbar__home" aria-haspopup="dialog"
          :aria-label="homeLocation ? `定居點：${locLabel(homeLocation)}` : '設置定居點'" @click="toggleHome">
          <i class="bi bi-house"></i>
          <span class="d-none d-md-inline ms-1">{{ homeLocation ? locLabel(homeLocation) : '設置定居點' }}</span>
        </button>
      </div>

      <div class="scifi-topbar__side scifi-topbar__actions">
        <ScifiThemePicker />
        <button class="btn btn-danger btn-sm" aria-label="登出" title="登出" @click="logout">
          <i class="bi bi-box-arrow-right"></i>
          <span class="d-none d-sm-inline ms-1">登出</span>
        </button>
      </div>
    </header>

    <!-- ══════════ 分頁列（放不下時折到下一列；手機改成底部導覽；「個人資料」可以選要顯示哪些分頁） ══════════ -->
    <nav class="scifi-tabs">
      <ul class="nav nav-tabs" role="tablist">
        <li class="nav-item" v-for="tab in visibleTabs" :key="tab.key" role="presentation">
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
      <div class="btn-group" role="tablist">
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
    <div class="scifi-body sf-split">
    <SfState v-if="loadingPlayer || playerError" class="mb-3" :loading="loadingPlayer" :error="playerError" @retry="loadPlayer" />
    <!-- ══════════ 倉庫 › 工具列：展開區塊的開關＋重新整理放最上面，開關不用捲到列表那邊 ══════════ -->
    <div v-show="activeTab === 'warehouse'" class="sf-toolbar">
      <button aria-label="新增／異動" class="btn btn-sm btn-success" @click="stockWizardRef?.openNew()">
        <i class="bi bi-plus-slash-minus me-1"></i><span class="sf-btn-text">新增／異動</span>
      </button>
      <button :aria-label="historyOpen ? '收起紀錄' : '庫存紀錄'" class="btn btn-sm" :class="historyOpen ? 'btn-secondary' : 'btn-info'"
        :aria-expanded="historyOpen ? 'true' : 'false'" @click="historyOpen = !historyOpen">
        <i class="bi me-1" :class="historyOpen ? 'bi-x-lg' : 'bi-clock-history'"></i><span class="sf-btn-text">{{ historyOpen ? '收起紀錄' : '庫存紀錄' }}</span>
      </button>
      <button class="btn btn-sm btn-primary" @click="refreshWarehouse" aria-label="重新整理"><i class="bi bi-arrow-clockwise me-1"></i><span class="sf-btn-text">重新整理</span></button>
    </div>
    <!-- 倉庫 › 共用篩選：只有這一張，同時篩「物品庫存」跟展開的「庫存紀錄」 -->
    <InventoryFilterBar v-show="activeTab === 'warehouse'"
      :rows="warehouseFilterRows" :known-locations="locations" :counts="warehouseFilterCounts" :loc-label="locLabel"
      :type-options="itemTypeOptions" v-model:q="stockFilter.q" v-model:types="stockFilter.types"
      v-model:dismantle="stockFilter.dismantle" :dismantle-options="dismantleOptions"
      v-model:systems="stockFilter.systems"
      v-model:planets="stockFilter.planets" v-model:locations="stockFilter.locations" />


    <!-- ══════════ 物品 › 物品資料：瀏覽物品主檔（唯讀），自己的搜尋卡（不含地點） ══════════ -->
    <div v-show="activeTab === 'items' && activeSub === 'data'" id="panel-items-data" class="sf-split">
      <div class="sf-toolbar">
        <button class="btn btn-sm btn-primary" aria-label="重新整理" @click="itemDataRef?.refresh()">
          <i class="bi bi-arrow-clockwise me-1"></i><span class="sf-btn-text">重新整理</span></button>
      </div>
      <InventoryFilterBar :rows="[]" :show-locations="false" show-buyable :type-options="itemTypeOptions"
        v-model:q="itemDataFilter.q" v-model:types="itemDataFilter.types" v-model:buyable="itemDataFilter.buyable"
        v-model:dismantlable="itemDataFilter.dismantlable" v-model:dismantle="itemDataFilter.dismantle"
        :dismantle-options="dismantleOptions" />
      <ItemDataBrowser ref="itemDataRef" :fetcher="playerAuth.playerFetch" :filters="itemDataFilters"
        :active="activeTab === 'items' && activeSub === 'data'" />
    </div>

    <!-- ══════════ 物品 › 商品購買地點：勾選多種商品，列出全部都買得到的交易終端（UEX 價格表）══════════ -->
    <div v-show="activeTab === 'items' && activeSub === 'commodities'" id="panel-items-commodities">
      <CommodityBuyFinder :fetcher="playerAuth.playerFetch" card-class="card scifi-card"
        :active="activeTab === 'items' && activeSub === 'commodities'" />
    </div>

    <!-- ══════════ 查詢持有資訊：一個區塊——一張搜尋卡（共同條件＋種類，選了單一種類才出現它專用的條件），
         一張整合的列表（物品／藍圖／船艦混在一起，不屬於那一類的欄位留空）══════════ -->
    <div v-show="activeTab === 'search'" class="sf-split">
      <div class="sf-toolbar">
        <!-- 查詢條件都記在網址裡，複製下來貼給隊友就是同一個查詢 -->
        <button type="button" class="btn btn-sm btn-primary" aria-label="複製查詢連結" @click="copySearchLink">
          <i class="bi me-1" :class="linkCopied ? 'bi-check-lg' : 'bi-link-45deg'"></i><span class="sf-btn-text">{{ linkCopied ? '已複製' : '複製連結' }}</span>
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
              <div class="btn-group btn-group-sm flex-wrap" role="group" aria-label="種類">
                <button v-for="k in whoKinds" :key="k.key" type="button" class="btn btn-subtab"
                  :class="{ active: whoKind === k.key }" :aria-pressed="whoKind === k.key ? 'true' : 'false'"
                  @click="whoKind = k.key"><i v-if="k.icon" :class="k.icon" class="me-1"></i>{{ k.label }}
                  <span class="who-count">{{ k.count }}</span></button>
              </div>
            </div>
            <!-- 選了單一種類才出現它專用的條件（手機收進「篩選」面板） -->
            <SfFilterSheet v-if="whoKind === 'items'" :count="itemsSheetCount" title="物品篩選" @clear="clearItemsSheet">
              <div class="col-12 col-md-3">
                <label class="form-label small mb-1" for="items-type">物品類型</label>
                <MultiSelectFilter id="items-type" v-model="itemsSelectedTypes" :options="itemTypeOptions"
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
                <MultiSelectFilter id="fl-role" v-model="flSelectedRoles" :options="vehicleFacets.roles"
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
                <span v-if="row.name_zh && row.name_zh !== row.name" class="small text-muted ms-1">{{ row.name }}</span>
                <i v-if="row.retired" class="bi bi-exclamation-triangle text-warning ms-1" title="這個物品已在新版本移除"></i>
                <i v-if="row.freeText" class="bi bi-pencil ms-1" title="自由輸入，沒有對應到遊戲配方"></i>
                <span v-if="row.note" class="sf-tree-chip ms-1" title="系統說明：同名變體的區別">{{ row.note }}</span>
                <!-- 船艦：每位持有者每一艘的配件網址，按鈕標「玩家 · 識別名稱 · 配件碼」 -->
                <VehicleLoadoutLinks v-for="u in (row.kind === 'fleet' ? holderUnitLoadouts(row.src.holders) : [])" :key="u.key"
                  :links="u.links" :prefix="u.prefix" button-class="btn-loadout" hide-label />
              </td>
              <td data-label="種類"><span class="sf-chip" :class="`who-kind--${row.kind}`">{{ WHO_KIND_LABEL[row.kind] }}</span></td>
              <td class="d-none d-md-table-cell" :class="{ 'who-na': !row.typeLabel }" data-label="類型">{{ row.typeLabel }}</td>
              <td class="d-none d-lg-table-cell" :class="{ 'who-na': !row.sizeLabel }" data-label="尺寸">{{ row.sizeLabel }}</td>
              <td class="d-none d-lg-table-cell" :class="{ 'who-na': !row.mfr }" data-label="廠商">{{ row.mfr }}</td>
              <td class="text-end text-nowrap d-none d-xl-table-cell" :class="{ 'who-na': !row.cargo }" data-label="載貨">{{ row.cargo ? scuLabel(row.cargo) : '' }}</td>
              <td class="text-end" data-label="持有人數">{{ row.holders }}</td>
              <td class="text-end" :class="{ 'who-na': row.qty == null }" data-label="數量">{{ row.qty ?? '' }}</td>
              <td class="text-end text-nowrap pe-3 sf-stack__actions">
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

    <!-- ══════════ 倉庫 › 庫存紀錄（原本的獨立分頁，改成物品庫存上方按「庫存紀錄」展開；
         舊網址 ?tab=warehouse&sub=history 直接展開）══════════ -->
    <div v-show="activeTab === 'warehouse' && historyOpen" class="sf-drawer">
      <h3 class="sf-drawer__title"><i class="bi bi-clock-history me-1"></i>庫存紀錄</h3>
      <SfState :loading="loadingHistory" :empty="!filteredHistory.length"
        :empty-text="history.length ? '沒有符合篩選條件的紀錄。' : '目前沒有任何紀錄。'">
      <div class="card scifi-card">
      <div class="card-body p-0">
      <div style="overflow-x: auto">
      <table class="table table-hover align-middle mb-0 sf-stack history-stack">
        <thead class="table-light">
          <tr>
            <SortTh :sort="historySort" field="ts" class="ps-3">時間</SortTh>
            <SortTh :sort="historySort" field="action">動作</SortTh>
            <SortTh :sort="historySort" field="item">物品</SortTh>
            <SortTh :sort="historySort" field="location">地點</SortTh>
            <SortTh :sort="historySort" field="delta" class="text-end">數量</SortTh>
            <SortTh :sort="historySort" field="note" class="sf-wrap pe-3">備註</SortTh>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, i) in historySort.sorted.value" :key="i">
            <td class="ps-3 text-muted text-nowrap" data-label="時間">{{ formatTs(row.ts) }}</td>
            <td data-label="動作">
              <span v-if="row.delta > 0" class="badge text-bg-success">增加</span>
              <span v-else class="badge text-bg-danger">減少</span>
            </td>
            <td class="sf-stack__title">
              <span class="fw-semibold">{{ row.item_name_zh || row.item_name }}</span>
              <span v-if="row.item_name_zh" class="small text-muted ms-1">{{ row.item_name }}</span>
            </td>
            <td data-label="地點">{{ locLabel(row.location) }}<span v-if="row.container" class="text-muted"> / {{ row.container }}</span></td>
            <td class="text-end" data-label="數量">{{ row.delta > 0 ? '+' : '' }}{{ row.delta }}</td>
            <td class="text-muted sf-wrap pe-3" data-label="備註">{{ row.note || '—' }}</td>
          </tr>
        </tbody>
      </table>
      </div>
      </div>
      </div>
      </SfState>
    </div>

    <!-- ══════════ 倉庫 › 物品庫存 ══════════ -->
    <!-- 有展開工具時隱藏列表（工具一次只開一個，見 exclusiveDrawers） -->
    <div v-show="activeTab === 'warehouse' && !warehouseDrawerOpen" role="tabpanel"
         id="panel-warehouse" :aria-labelledby="'tab-warehouse'">
      <SfState :loading="loadingInventory" :empty="!filteredInventory.length"
        :empty-text="myInventory.length ? '沒有符合篩選條件的物品。' : '目前沒有登記任何物品。'">
      <SortSelect v-if="isPhone" class="mb-2" :sort="inventorySort" :options="INVENTORY_SORT_OPTIONS" />
      <div class="card scifi-card">
      <div class="card-body p-0">
      <div style="overflow-x: auto">
      <!-- sf-stack：手機上每一列變成一張卡片（td 的 data-label 是卡片裡的欄位名稱） -->
      <table class="table table-hover align-middle mb-0 sf-stack">
        <thead class="table-light">
          <tr>
            <SortTh :sort="inventorySort" field="item" class="ps-3">物品</SortTh>
            <SortTh :sort="inventorySort" field="location">地點</SortTh>
            <SortTh :sort="inventorySort" field="quantity" class="text-end">數量</SortTh>
            <th class="pe-3"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in inventorySort.sorted.value" :key="row.item_id + row.location + (row.container || '')">
            <td class="ps-3 sf-stack__title">
              <span class="fw-semibold">{{ row.item_name_zh || row.item_name }}</span>
              <span v-if="row.item_name_zh" class="small text-muted ms-1">{{ row.item_name }}</span>
              <div v-if="stockFilter.dismantle.length" class="small text-muted">
                拆解回收：{{ dismantleHits(dismantleMap[row.item_id], stockFilter.dismantle).join('、') || '—' }}
              </div>
            </td>
            <td data-label="地點">{{ locLabel(row.location) }}<span v-if="row.container" class="text-muted"> / {{ row.container }}</span></td>
            <td class="text-end" data-label="數量">{{ row.quantity }}</td>
            <td class="text-end pe-3 sf-stack__actions">
              <button type="button" class="btn btn-sm btn-info" @click="stockWizardRef?.openAdjust(row)">異動</button>
            </td>
          </tr>
        </tbody>
      </table>
      </div>
      </div>
      </div>
      </SfState>
    </div>

    <!-- ══════════ 藍圖 › 工具列（同倉庫：開關＋重新整理放最上面）══════════ -->
    <div v-show="activeTab === 'blueprints'" class="sf-toolbar">
      <button aria-label="登記藍圖資料" aria-haspopup="dialog" class="btn btn-sm btn-success" @click="bpDataOpen = true">
        <i class="bi bi-journal-text me-1"></i><span class="sf-btn-text">登記藍圖資料</span>
      </button>
      <button class="btn btn-sm btn-primary" @click="loadBlueprints" aria-label="重新整理"><i class="bi bi-arrow-clockwise me-1"></i><span class="sf-btn-text">重新整理</span></button>
    </div>
    <!-- 藍圖 › 共用搜尋：同一組名稱／類型／需任務解鎖同時篩「我的藍圖」「登記藍圖資料」；
         展開登記藍圖資料時多一個「只顯示未登記」（預設勾選）。
         預設可用的藍圖視同已登記，兩邊都不列（不需要勾選）。
         名稱打字就即時篩（子字串），同時跳出主檔的候選，點一個就代入名稱 -->
    <Teleport defer to="#bp-modal-filters" :disabled="!bpDataOpen">
    <div v-show="activeTab === 'blueprints'" class="card scifi-card sf-search mb-3">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col col-md-7">
            <label class="form-label small fw-semibold mb-1" for="bp-filter-q">藍圖名稱</label>
            <AutocompleteField id="bp-filter-q" v-model="bpFilterQuery" :search="searchBlueprintNames"
              :get-label="blueprintNameLabel" :get-meta="blueprintNameMeta"
              aria-label="藍圖名稱" placeholder="輸入藍圖名稱（中英文皆可）" :min-chars="1" />
          </div>
          <!-- 手機：類型與勾選收進「篩選」底部面板 -->
          <SfFilterSheet :count="bpSheetCount" @clear="clearBpFilter">
            <div class="col-12 col-md-5">
              <label class="form-label small fw-semibold mb-1" for="bp-filter-type">類型</label>
              <MultiSelectFilter id="bp-filter-type" v-model="myBpTypes" :options="blueprintTypeOptions"
                label="類型" placeholder="全部" block searchable />
            </div>

            <template #more>
              <div class="form-check mt-3">
                <input id="bp-filter-missions-m" v-model="bpHasMissionsOnly" class="form-check-input" type="checkbox">
                <label class="form-check-label" for="bp-filter-missions-m">只看需任務解鎖</label>
              </div>
              <div v-if="bpDataOpen" class="form-check mt-2">
                <input id="bp-filter-unregistered-m" v-model="bpUnregisteredOnly" class="form-check-input" type="checkbox">
                <label class="form-check-label" for="bp-filter-unregistered-m">只顯示未登記</label>
              </div>
            </template>
          </SfFilterSheet>
        </div>
        <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
          <div v-if="!isPhone" class="form-check form-check-inline mb-0">
            <input id="bp-filter-missions" v-model="bpHasMissionsOnly" class="form-check-input" type="checkbox">
            <label class="form-check-label" for="bp-filter-missions">只看需任務解鎖</label>
          </div>
          <div v-if="bpDataOpen && !isPhone" class="form-check form-check-inline mb-0">
            <input id="bp-filter-unregistered" v-model="bpUnregisteredOnly" class="form-check-input" type="checkbox">
            <label class="form-check-label" for="bp-filter-unregistered">只顯示未登記</label>
          </div>
          <span v-if="bpFilterActive" class="small text-muted">我的藍圖 符合 {{ filteredBlueprints.length }} / {{ visibleBlueprints.length }} 張</span>
          <button v-if="bpFilterActive && !isPhone" type="button" class="btn btn-sm btn-warning ms-auto" @click="clearBpFilter">清除篩選</button>
        </div>
      </div>
    </div>
    </Teleport>

    <!-- ══════════ 藍圖（自己的名冊，可增刪） ══════════ -->
    <div v-show="activeTab === 'blueprints'" role="tabpanel"
         id="panel-blueprints" :aria-labelledby="'tab-blueprints'">
      <Transition name="alert-slide">
        <div v-if="blueprintError" class="alert alert-danger py-2">{{ blueprintError }}</div>
      </Transition>
      <Transition name="alert-slide">
        <div v-if="blueprintSuccess" class="alert alert-success py-2">{{ blueprintSuccess }}</div>
      </Transition>

      <!-- 列表外觀：卡片＋一般字級的 hover 表格；手機上每列變卡片（sf-stack） -->
      <SfState :loading="loadingBlueprints" :empty="!filteredBlueprints.length"
        :empty-text="visibleBlueprints.length ? '沒有符合篩選條件的藍圖。' : '目前沒有登記任何藍圖。'">
      <SortSelect v-if="isPhone" class="mb-2" :sort="myBpSort" :options="MY_BP_SORT_OPTIONS" />
      <div class="card scifi-card">
      <div class="card-body p-0">
      <div style="overflow-x: auto">
      <table class="table table-hover align-middle mb-0 sf-stack">
        <thead class="table-light">
          <tr>
            <SortTh :sort="myBpSort" field="name" class="ps-3">名稱</SortTh>
            <SortTh :sort="myBpSort" field="type">類型</SortTh>
            <SortTh :sort="myBpSort" field="craft_time" class="d-none d-lg-table-cell">製作時間</SortTh>
            <SortTh :sort="myBpSort" field="ingredients">材料</SortTh>
            <SortTh :sort="myBpSort" field="notes" class="sf-wrap d-none d-md-table-cell">備註</SortTh>
            <th class="pe-3"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="bp in myBpSort.sorted.value" :key="bp._id">
          <tr>
            <td class="ps-3 sf-stack__title">
              <button v-if="bp.blueprint_uuid && bp.master?.mission_count" type="button" class="btn btn-sm btn-info px-2 text-start fw-semibold"
                @click="openBpMissions({ uuid: bp.blueprint_uuid, name: bp.name, name_zh: bp.master.name_zh, output_type: bp.master.output_type })">
                {{ bp.master?.name_zh || bp.name }}
              </button>
              <span v-else class="fw-semibold">{{ bp.master?.name_zh || bp.name }}</span>
              <span v-if="bp.master?.name_zh" class="small text-muted ms-1">{{ bp.name }}</span>
              <i v-if="!bp.blueprint_uuid" class="bi bi-pencil text-muted ms-1"
                 title="自由輸入，沒有對應到遊戲配方"></i>
              <!-- 手機藏了備註欄，改顯示在名稱下面 -->
              <div v-if="bp.notes" class="small text-muted d-md-none">{{ bp.notes }}</div>
            </td>
            <td data-label="類型">{{ bp.master?.output_type ? blueprintTypeLabel(bp.master.output_type) : (bp.master?.output_type_label || '—') }}</td>
            <td class="d-none d-lg-table-cell" data-label="製作時間">{{ bp.master?.craft_time_label || '—' }}</td>
            <td data-label="材料">
              <button v-if="bp.blueprint_uuid" class="btn btn-sm btn-info"
                @click="showRecipe(bp)">{{ bp.master?.ingredient_count ?? '?' }} 種</button>
              <span v-else class="text-muted">—</span>
            </td>
            <td class="text-muted sf-wrap d-none d-md-table-cell">{{ bp.notes || '—' }}</td>
            <td class="text-end text-nowrap pe-3 sf-stack__actions">
              <button v-if="bp.blueprint_uuid" class="btn btn-sm btn-info me-2"
                :aria-expanded="qualityFor === bp._id ? 'true' : 'false'"
                @click="qualityFor = qualityFor === bp._id ? null : bp._id">
                <i class="bi me-1" :class="qualityFor === bp._id ? 'bi-chevron-up' : 'bi-sliders'"></i>品質試算
              </button>
              <!-- 刪除先確認（同一格換成「確定刪除？ 刪除／取消」），送出中停用 -->
              <template v-if="confirmDeleteKey === `bp:${bp._id}`">
                <span class="me-2">確定刪除？</span>
                <button class="btn btn-sm btn-danger me-2" :disabled="deletingKey === `bp:${bp._id}`"
                  :aria-label="`確定刪除 ${bp.master?.name_zh || bp.name}`" @click="removeBlueprint(bp)">
                  <span v-if="deletingKey === `bp:${bp._id}`" class="spinner-border spinner-border-sm me-1"></span>刪除
                </button>
                <button class="btn btn-sm btn-secondary" :disabled="deletingKey === `bp:${bp._id}`" @click="confirmDeleteKey = ''">取消</button>
              </template>
              <button v-else class="btn btn-sm btn-danger" @click="confirmDeleteKey = `bp:${bp._id}`">刪除</button>
            </td>
          </tr>
          <tr v-if="qualityFor === bp._id" class="sf-stack__detail">
            <td colspan="6">
              <!-- 手機上這一列變成底部面板，標題列附關閉按鈕 -->
              <div class="sf-sheet__head sf-stack__sheet-head">
                <h3 class="sf-sheet__title">品質試算 · {{ bp.master?.name_zh || bp.name }}</h3>
                <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="qualityFor = null"><i class="bi bi-x-lg"></i></button>
              </div>
              <!-- 品質試算：拖拉每個部位的材料品質，看各屬性加成（見 components/BlueprintQuality.vue） -->
              <BlueprintQuality :fetcher="playerAuth.playerFetch" :blueprint-uuid="bp.blueprint_uuid" />
            </td>
          </tr>
          <tr v-if="recipeFor === bp._id" class="sf-stack__detail">
            <!-- colspan 要跟 thead 的欄數一致（移除「狀態」欄後是 6） -->
            <td colspan="6">
              <div class="sf-sheet__head sf-stack__sheet-head">
                <h3 class="sf-sheet__title">材料 · {{ bp.master?.name_zh || bp.name }}</h3>
                <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="recipeFor = null"><i class="bi bi-x-lg"></i></button>
              </div>
              <!-- 材料試算：輸入要做幾個，列出每種材料需要多少（附 sc-datahub 對應頁面） -->
              <BlueprintCalculator :fetcher="playerAuth.playerFetch"
                :blueprint="{ _id: bp.blueprint_uuid, name: bp.name, name_zh: bp.master?.name_zh }"
                card-class="card scifi-card" />
            </td>
          </tr>
          </template>
        </tbody>
      </table>
      </div>
      </div>
      </div>
      </SfState>
    </div>

    <!-- ══════════ 任務（唯讀任務資料庫；藍圖欄標出自己已登記幾張，見 components/MissionBrowser.vue）══════════ -->
    <div v-show="activeTab === 'missions'" class="sf-toolbar">
      <button aria-label="勢力聲望" aria-haspopup="dialog" class="btn btn-sm btn-success" @click="factionRepOpen = true">
        <i class="bi bi-award me-1"></i><span class="sf-btn-text">勢力聲望</span>
      </button>
      <button class="btn btn-sm btn-primary" aria-label="重新整理" @click="missionBrowserRef?.reload()"><i class="bi bi-arrow-clockwise me-1"></i><span class="sf-btn-text">重新整理</span></button>
    </div>
    <!-- 任務 › 共用搜尋：名稱即時篩；類型／星系／勢力／合法性手機收進「篩選」面板 -->
    <div v-show="activeTab === 'missions'" class="card scifi-card sf-search mb-3">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-4">
            <label class="form-label small fw-semibold mb-1" for="ms-filter-q">任務名稱</label>
            <input id="ms-filter-q" v-model="msFilter.q" type="search" class="form-control" placeholder="輸入任務名稱（中英文皆可）">
          </div>
          <SfFilterSheet :count="msSheetCount" @clear="clearMsFilter">
            <div class="col-6 col-md-2">
              <label class="form-label small fw-semibold mb-1" for="ms-filter-scope">類型</label>
              <MultiSelectFilter id="ms-filter-scope" v-model="msFilter.scopes" :options="msScopeOptions"
                label="類型" placeholder="全部" block searchable />
            </div>
            <div class="col-6 col-md-2">
              <label class="form-label small fw-semibold mb-1" for="ms-filter-system">星系</label>
              <MultiSelectFilter id="ms-filter-system" v-model="msFilter.systems" :options="msSystemOptions"
                label="星系" placeholder="全部" block />
            </div>
            <div class="col-6 col-md-2">
              <label class="form-label small fw-semibold mb-1" for="ms-filter-faction">勢力</label>
              <MultiSelectFilter id="ms-filter-faction" v-model="msFilter.factions" :options="msFactionOptions"
                label="勢力" placeholder="全部" block searchable />
            </div>
            <div class="col-6 col-md-2">
              <label class="form-label small fw-semibold mb-1" for="ms-filter-legal">合法性</label>
              <MultiSelectFilter id="ms-filter-legal" v-model="msFilter.legality" :options="MS_LEGALITY_OPTIONS"
                label="合法性" placeholder="全部" block />
            </div>

            <template #more>
              <div class="form-check mt-3">
                <input id="ms-filter-bp-m" v-model="msFilter.hasBlueprints" class="form-check-input" type="checkbox">
                <label class="form-check-label" for="ms-filter-bp-m">只看有藍圖</label>
              </div>
              <div class="form-check mt-2">
                <input id="ms-filter-reward-m" v-model="msFilter.hasReward" class="form-check-input" type="checkbox">
                <label class="form-check-label" for="ms-filter-reward-m">只看固定報酬</label>
              </div>
            </template>
          </SfFilterSheet>
        </div>
        <div class="d-flex flex-wrap align-items-center gap-2 mt-2">
          <div v-if="!isPhone" class="form-check form-check-inline mb-0">
            <input id="ms-filter-bp" v-model="msFilter.hasBlueprints" class="form-check-input" type="checkbox">
            <label class="form-check-label" for="ms-filter-bp">只看有藍圖</label>
          </div>
          <div v-if="!isPhone" class="form-check form-check-inline mb-0">
            <input id="ms-filter-reward" v-model="msFilter.hasReward" class="form-check-input" type="checkbox">
            <label class="form-check-label" for="ms-filter-reward">只看固定報酬</label>
          </div>
          <button v-if="msFilterActive && !isPhone" type="button" class="btn btn-sm btn-warning ms-auto" @click="clearMsFilter">清除篩選</button>
        </div>
      </div>
    </div>
    <div v-show="activeTab === 'missions'" role="tabpanel" id="panel-missions" :aria-labelledby="'tab-missions'">
      <MissionBrowser ref="missionBrowserRef" :fetcher="playerAuth.playerFetch" :active="activeTab === 'missions'"
        :filters="msFilter" :registered-uuids="myBlueprintUuids" @registered="onBulkRegistered" />
    </div>

    <!-- ══════════ 個人資料 ══════════ -->
    <!-- ══════════ 艦隊（我的艦隊＋登記船艦資料／JSON 匯入） ══════════ -->
    <div v-show="activeTab === 'fleet'" role="tabpanel" id="panel-fleet" :aria-labelledby="'tab-fleet'" class="sf-split">
      <Transition name="alert-slide">
        <div v-if="fleetError" class="alert alert-danger py-2">{{ fleetError }}</div>
      </Transition>

      <!-- 工具列（同倉庫：開關＋重新整理放最上面） -->
      <div class="sf-toolbar">
        <button aria-label="登記船艦資料" aria-haspopup="dialog" class="btn btn-sm btn-success" @click="fleetDataOpen = true">
          <i class="bi bi-info-circle me-1"></i><span class="sf-btn-text">登記船艦資料</span>
        </button>
        <button aria-label="JSON 匯入" aria-haspopup="dialog" class="btn btn-sm btn-success" @click="fleetImportOpen = true">
          <i class="bi bi-filetype-json me-1"></i><span class="sf-btn-text">JSON 匯入</span>
        </button>
        <button class="btn btn-sm btn-primary" @click="loadFleet" aria-label="重新整理"><i class="bi bi-arrow-clockwise me-1"></i><span class="sf-btn-text">重新整理</span></button>
      </div>

      <!-- 共用搜尋：同一組條件同時篩「我的艦隊」跟「登記船艦資料」（開視窗時用 Teleport 移進視窗） -->
      <Teleport defer to="#fleet-modal-filters" :disabled="!fleetDataOpen">
      <div class="card scifi-card sf-search mb-3">
        <div class="card-body py-3">
          <div class="row g-2 align-items-end">
            <div class="col col-md-6">
              <label class="form-label small mb-1" for="myfleet-q">名稱關鍵字</label>
              <input id="myfleet-q" v-model="myFleetQuery" type="search" class="form-control form-control-sm"
                placeholder="搜尋船艦名稱（中英文皆可）" autocomplete="off">
            </div>
            <!-- 手機：名稱以外的條件收進「篩選」底部面板 -->
            <SfFilterSheet :count="fleetSheetCount" @clear="clearMyFleetFilters">
              <div class="col-12 col-md-6">
                <label class="form-label small mb-1" for="myfleet-acquire">取得方式</label>
                <MultiSelectFilter id="myfleet-acquire" v-model="myFleetAcquire" :options="VEHICLE_ACQUIRE_OPTIONS"
                  label="取得方式" placeholder="全部" block />
              </div>
              <div class="col-6 col-md-3">
                <label class="form-label small mb-1" for="myfleet-type">類型</label>
                <MultiSelectFilter id="myfleet-type" v-model="myFleetTypes" :options="myFleetTypeOptions"
                  label="類型" placeholder="全部" block />
              </div>
              <div class="col-6 col-md-3">
                <label class="form-label small mb-1" for="myfleet-size">尺寸</label>
                <MultiSelectFilter id="myfleet-size" v-model="myFleetSizes" :options="myFleetSizeOptions"
                  label="尺寸" placeholder="全部" block />
              </div>
              <div class="col-6 col-md-3">
                <label class="form-label small mb-1" for="myfleet-mfr">廠商</label>
                <MultiSelectFilter id="myfleet-mfr" v-model="myFleetMfrs" :options="myFleetMfrOptions"
                  label="廠商" placeholder="全部" block searchable />
              </div>
              <div class="col-6 col-md-3">
                <label class="form-label small mb-1" for="myfleet-role">角色</label>
                <MultiSelectFilter id="myfleet-role" v-model="myFleetRoles" :options="myFleetRoleOptions"
                  label="角色" placeholder="全部" block searchable />
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label small mb-1" for="myfleet-price-min">價格</label>
                <div class="input-group input-group-sm">
                  <select v-model="myFleetRange.priceCurrency" class="form-select form-select-sm fleet-range-currency" aria-label="價格幣別">
                    <option value="usd">美金</option>
                    <option value="auec">遊戲幣</option>
                    <option value="rent">租用</option>
                  </select>
                  <input id="myfleet-price-min" v-model.lazy="myFleetRange.priceMin" type="number" min="0" class="form-control"
                    placeholder="最低" aria-label="最低價格">
                  <span class="input-group-text">–</span>
                  <input v-model.lazy="myFleetRange.priceMax" type="number" min="0" class="form-control"
                    placeholder="最高" aria-label="最高價格">
                </div>
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label small mb-1" for="myfleet-scu-min">貨物量</label>
                <div class="input-group input-group-sm">
                  <input id="myfleet-scu-min" v-model.lazy="myFleetRange.scuMin" type="number" min="0" class="form-control"
                    placeholder="最少" aria-label="最少貨物量">
                  <span class="input-group-text">–</span>
                  <input v-model.lazy="myFleetRange.scuMax" type="number" min="0" class="form-control"
                    placeholder="最多" aria-label="最多貨物量">
                  <span class="input-group-text">SCU</span>
                </div>
              </div>
            </SfFilterSheet>
          </div>
          <div v-if="fleet.length || myFleetHasFilter" class="d-flex flex-wrap align-items-center gap-2 mt-2">
            <span v-if="fleet.length" class="small text-muted">
              <template v-if="myFleetHasFilter">符合 {{ filteredFleet.length }} 款、{{ filteredFleetShipCount }} 艘、{{ scuLabel(fleetScuOf(filteredFleet)) }} · </template>
              共 {{ fleet.length }} 款、{{ fleetShipCount }} 艘、載貨 {{ scuLabel(fleetScuOf(fleet)) }}
            </span>
            <button v-if="myFleetHasFilter && !isPhone" type="button" class="btn btn-sm btn-warning ms-auto" @click="clearMyFleetFilters">清除篩選</button>
          </div>
        </div>
      </div>

      </Teleport>

      <div>
      <div v-if="loadingFleet" class="text-muted small">載入中…</div>
      <div v-else-if="fleetLoaded && !fleet.length" class="text-muted small">還沒有登記任何船／載具。</div>
      <div v-else-if="fleet.length && !filteredFleet.length" class="text-muted small">沒有符合篩選條件的船／載具。</div>
      <!-- 列表外觀跟倉庫、藍圖一致：卡片＋hover 表格＋表頭排序；「詳細」展開船艦資訊、數量與每一艘的識別名稱／配件網址 -->
      <template v-else-if="fleet.length">
      <SortSelect v-if="isPhone" class="mb-2" :sort="myFleetSort" :options="MY_FLEET_SORT_OPTIONS" />
      <div class="card scifi-card">
      <div class="card-body p-0">
      <div style="overflow-x: auto">
      <table class="table table-hover align-middle mb-0 sf-stack">
        <thead class="table-light">
          <tr>
            <SortTh :sort="myFleetSort" field="name" class="ps-3">船艦</SortTh>
            <SortTh :sort="myFleetSort" field="type" class="d-none d-md-table-cell">類型</SortTh>
            <SortTh :sort="myFleetSort" field="size" class="d-none d-lg-table-cell">尺寸</SortTh>
            <SortTh :sort="myFleetSort" field="manufacturer" class="d-none d-lg-table-cell">廠商</SortTh>
            <SortTh :sort="myFleetSort" field="role" class="d-none d-lg-table-cell">角色</SortTh>
            <SortTh :sort="myFleetSort" field="cargo" class="text-end">載貨</SortTh>
            <SortTh :sort="myFleetSort" field="usd" class="text-end">美金</SortTh>
            <SortTh :sort="myFleetSort" field="auec" class="text-end">遊戲幣</SortTh>
            <SortTh :sort="myFleetSort" field="rent" class="text-end d-none d-xl-table-cell">租用</SortTh>
            <SortTh :sort="myFleetSort" field="ratio" class="text-end d-none d-xxl-table-cell">aUEC／美金</SortTh>
            <SortTh :sort="myFleetSort" field="quantity" class="text-end">數量</SortTh>
            <th class="pe-3"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in myFleetSort.sorted.value" :key="row._id">
          <tr>
            <td class="ps-3 sf-stack__title">
              <span class="fw-semibold">{{ row.vehicle?.name_zh || row.name }}</span>
              <span v-if="row.vehicle?.name_zh" class="small text-muted ms-1">{{ row.name }}</span>
              <span v-if="row.vehicle?.system_note" class="sf-tree-chip ms-1" title="系統說明：同名變體的區別">{{ row.vehicle.system_note }}</span>
              <span v-if="row.vehicle && row.vehicle.is_current === false"
                class="sf-tree-chip ms-1" title="目前遊戲版本的資料裡已經沒有這款">已下架</span>
              <!-- 配件網址直接列在船名下面（好幾艘時按鈕前面標是哪一艘） -->
              <VehicleLoadoutLinks v-for="u in fleetUnitLoadouts(row)" :key="u.n" :links="u.links" :prefix="u.prefix"
                button-class="btn-loadout" hide-label />
            </td>
            <!-- 手機／平板藏次要欄位（「詳細」裡都看得到）；尺寸 ≥992、租用 ≥1200、aUEC／美金 ≥1400 才顯示，平板與一般筆電不用橫向捲 -->
            <td class="d-none d-md-table-cell" data-label="類型">{{ vehicleTypeLabel(row.vehicle?.vehicle_type) || '—' }}</td>
            <td class="d-none d-lg-table-cell" data-label="尺寸">{{ vehicleSizeLabel(row.vehicle?.size_class) || '—' }}</td>
            <td class="d-none d-lg-table-cell" data-label="廠商">{{ manufacturerLabel(row.vehicle?.manufacturer_name, row.vehicle?.manufacturer_code) || '—' }}</td>
            <td class="d-none d-lg-table-cell" data-label="角色">{{ vehicleRoleLabel(row.vehicle?.role, row.vehicle?.role_zh) || '—' }}</td>
            <td class="text-end text-nowrap" data-label="載貨">{{ scuLabel(row.vehicle?.cargo_capacity_scu) }}</td>
            <td class="text-end text-nowrap" data-label="美金">{{ fmtUsd(row.vehicle?.msrp) }}</td>
            <td class="text-end text-nowrap" data-label="遊戲幣">{{ fmtAuec(row.vehicle?.uex_price?.buy_min) }}</td>
            <td class="text-end text-nowrap d-none d-xl-table-cell" data-label="租用">{{ fmtAuec(row.vehicle?.uex_price?.rent_min) }}</td>
            <td class="text-end text-nowrap d-none d-xxl-table-cell" data-label="aUEC／美金">{{ fmtAuecPerUsd(auecPerUsd(row.vehicle)) }}</td>
            <td class="text-end" data-label="數量">{{ row.quantity }}</td>
            <td class="text-end text-nowrap pe-3 sf-stack__actions">
              <button type="button" class="btn btn-sm btn-info me-2"
                :aria-label="`編輯 ${row.vehicle?.name_zh || row.name}`" @click="openFleetEdit(row)">
                <i class="bi bi-pencil-square me-1"></i>編輯
              </button>
              <button type="button" class="btn btn-sm btn-info me-2"
                :aria-expanded="openMyFleet.has(row._id) ? 'true' : 'false'" @click="toggleMyFleet(row._id)">
                <i class="bi me-1" :class="openMyFleet.has(row._id) ? 'bi-chevron-up' : 'bi-chevron-down'"></i>詳細
              </button>
              <template v-if="confirmDeleteKey === `fleet:${row._id}`">
                <span class="me-2">確定刪除全部 {{ row.quantity }} 艘？</span>
                <button type="button" class="btn btn-sm btn-danger me-2" :disabled="deletingKey === `fleet:${row._id}`"
                  :aria-label="`確定刪除 ${row.vehicle?.name_zh || row.name}（全部 ${row.quantity} 艘）`" @click="removeFleet(row)">
                  <span v-if="deletingKey === `fleet:${row._id}`" class="spinner-border spinner-border-sm me-1"></span>刪除
                </button>
                <button type="button" class="btn btn-sm btn-secondary" :disabled="deletingKey === `fleet:${row._id}`"
                  @click="confirmDeleteKey = ''">取消</button>
              </template>
              <button v-else type="button" class="btn btn-sm btn-danger"
                :aria-label="`刪除 ${row.vehicle?.name_zh || row.name}（全部 ${row.quantity} 艘）`"
                @click="confirmDeleteKey = `fleet:${row._id}`">刪除</button>
            </td>
          </tr>
          <tr v-if="openMyFleet.has(row._id)" class="sf-stack__detail">
            <!-- colspan 要跟 thead 的欄數一致（12）；手機上這一列變成底部面板。數量、識別名稱、配件網址改在「編輯」視窗 -->
            <td colspan="12" class="myfleet-detail">
                <div class="sf-sheet__head sf-stack__sheet-head">
                  <h3 class="sf-sheet__title">{{ row.vehicle?.name_zh || row.name }}</h3>
                  <button type="button" class="btn btn-sm btn-secondary" aria-label="關閉" @click="toggleMyFleet(row._id)"><i class="bi bi-x-lg"></i></button>
                </div>
                <!-- 船艦資訊：欄位名稱＋值的格子，比一長串「·」好讀 -->
                <div class="myfleet-info">
                  <div v-for="f in fleetInfoFields(row.vehicle)" :key="f.label" class="myfleet-info__item">
                    <span class="myfleet-info__label">{{ f.label }}</span>
                    <span class="myfleet-info__value">{{ f.value }}</span>
                  </div>
                </div>
                <div v-if="row.vehicle?.note" class="sf-tree-info vehicle-note">{{ row.vehicle.note }}</div>
            </td>
          </tr>
          </template>
        </tbody>
      </table>
      </div>
      </div>
      </div>
      </template>
      </div>
    </div>

    <!-- ══════════ 礦物參考查詢 ══════════ -->
    <div v-show="activeTab === 'mining'" role="tabpanel" id="panel-mining"
      :aria-labelledby="'tab-mining'">
      <!-- 元件跟後台「礦物參考查詢」頁共用，差別只在帶進去的身分 -->
      <MiningLookup :fetcher="playerAuth.playerFetch" :active="activeTab === 'mining'"
        card-class="card scifi-card" />
    </div>

    <!-- ══════════ 航線規劃／合約分配（見 components/RoutePlanner.vue、ContractPlanner.vue、src/models/nav.py、haul.py）══════════ -->
    <div v-show="activeTab === 'route' && activeSub === 'plan'" role="tabpanel" id="panel-route-plan"
      aria-labelledby="subtab-route-plan">
      <RoutePlanner :fetcher="playerAuth.playerFetch" :active="activeTab === 'route' && activeSub === 'plan'"
        :fleet-uuids="fleetVehicleUuids" card-class="card scifi-card" />
    </div>
    <div v-show="activeTab === 'route' && activeSub === 'contracts'" role="tabpanel" id="panel-route-contracts"
      aria-labelledby="subtab-route-contracts">
      <ContractPlanner :fetcher="playerAuth.playerFetch" :active="activeTab === 'route' && activeSub === 'contracts'"
        :fleet-uuids="fleetVehicleUuids" card-class="card scifi-card" />
    </div>

    <!-- ══════════ 貨艙網格（見 components/CargoLoader.vue）══════════ -->
    <div v-show="activeTab === 'cargo'" role="tabpanel" id="panel-cargo" :aria-labelledby="'tab-cargo'">
      <CargoLoader :fetcher="playerAuth.playerFetch" :active="activeTab === 'cargo'"
        :fleet-uuids="fleetVehicleUuids" card-class="card scifi-card" />
    </div>

    <!-- ══════════ LOG 解析（Game.log 在瀏覽器裡解析，不上傳；見 components/GameLogReader.vue）══════════ -->
    <div v-show="activeTab === 'gamelog'" role="tabpanel" id="panel-gamelog" :aria-labelledby="'tab-gamelog'">
      <GameLogReader card-class="card scifi-card" :player-name="playerAuth.starCitizenId" />
    </div>

    <!-- ══════════ 酬勞分配（總金額依人數／成數分，扣稅前後；純前端，見 components/PayoutCalculator.vue）══════════ -->
    <div v-show="activeTab === 'payout'" role="tabpanel" id="panel-payout" :aria-labelledby="'tab-payout'">
      <PayoutCalculator card-class="card scifi-card" />
    </div>

    <!-- ══════════ 中文轉碼（遊戲聊天用的 中文 ↔ @代碼，見 components/ChatCodeTranslator.vue）══════════ -->
    <div v-show="activeTab === 'chatcode'" role="tabpanel" id="panel-chatcode" :aria-labelledby="'tab-chatcode'">
      <ChatCodeTranslator :fetcher="playerAuth.playerFetch" :active="activeTab === 'chatcode'"
        card-class="card scifi-card" />
    </div>

    <!-- ══════════ 工具網站（後台維護的外部連結） ══════════ -->
    <div v-show="activeTab === 'tools'" role="tabpanel" id="panel-tools" :aria-labelledby="'tab-tools'">
      <SfState :loading="loadingToolLinks && !toolLinks.length" :error="toolLinksError" :empty="!toolLinks.length"
        empty-text="目前沒有工具網站。" @retry="loadToolLinks">
      <div class="sf-split">
        <!-- 搜尋卡：關鍵字（名稱、網址、說明、標籤）＋標籤快速篩選（按鈕，可多選，上面有數量） -->
        <div class="card scifi-card sf-search mb-3">
          <div class="card-body py-3">
            <div class="row g-2 align-items-end">
              <div class="col-12 col-md-6 col-xl-4">
                <label class="form-label small mb-1" for="tool-q">搜尋</label>
                <input id="tool-q" v-model="toolQuery" type="search" class="form-control form-control-sm"
                  placeholder="名稱、網址、說明、標籤…" aria-label="搜尋工具網站">
              </div>
              <div class="col-12">
                <span class="form-label small mb-1 d-block">標籤</span>
                <div class="d-flex flex-wrap gap-2">
                  <button type="button" class="btn btn-sm btn-subtab" :class="{ active: !toolSelectedTags.length }"
                    :aria-pressed="!toolSelectedTags.length ? 'true' : 'false'" @click="toolSelectedTags = []">
                    全部<span class="tool-count">{{ toolLinks.length }}</span></button>
                  <button v-for="t in toolTagCounts" :key="t.tag" type="button" class="btn btn-sm btn-subtab"
                    :class="{ active: toolSelectedTags.includes(t.tag) }"
                    :aria-pressed="toolSelectedTags.includes(t.tag) ? 'true' : 'false'" @click="toggleToolTag(t.tag)">
                    {{ t.tag }}<span class="tool-count">{{ t.count }}</span></button>
                </div>
              </div>
            </div>
            <div v-if="toolQuery || toolSelectedTags.length" class="d-flex justify-content-end mt-2">
              <button type="button" class="btn btn-sm btn-warning" @click="toolQuery = ''; toolSelectedTags = []">清除全部</button>
            </div>
          </div>
        </div>

        <div>
          <div v-if="!toolLinkGroups.length" class="text-muted">沒有符合的工具網站。</div>
          <!-- 依標籤分組（後台設定的順序，沒有標籤的排最後）；一個網址有好幾個標籤就出現在每一組，分組標題按了可以收起來 -->
          <section v-for="group in toolLinkGroups" :key="group.name" class="tool-group">
            <button type="button" class="tool-group__head" :aria-expanded="collapsedToolGroups.has(group.name) ? 'false' : 'true'"
              @click="toggleToolGroup(group.name)">
              <i class="bi" :class="collapsedToolGroups.has(group.name) ? 'bi-chevron-right' : 'bi-chevron-down'"></i>
              <span>{{ group.name || '未分類' }}</span>
              <span class="sf-chip">{{ group.links.length }}</span>
            </button>
            <div v-if="!collapsedToolGroups.has(group.name)" class="row g-3">
              <div v-for="link in group.links" :key="link._id" class="col-12 col-md-6 col-xl-4 col-xxl-3">
                <div class="card scifi-card h-100 tool-card">
                  <div class="card-body d-flex flex-column gap-2">
                    <div class="d-flex align-items-start gap-2">
                      <span class="tool-card__icon" aria-hidden="true">{{ toolInitial(link) }}</span>
                      <div class="flex-grow-1 min-w-0">
                        <div class="tool-card__title">{{ link.title }}</div>
                        <div class="tool-card__host">{{ toolHost(link.url) }}</div>
                      </div>
                      <a :href="link.url" target="_blank" rel="noopener noreferrer" class="btn btn-sm btn-primary text-nowrap"
                        :aria-label="`開啟 ${link.title}`"><i class="bi bi-box-arrow-up-right me-1"></i>開啟</a>
                    </div>
                    <p v-if="link.description" class="tool-card__desc mb-0">{{ link.description }}</p>
                    <div v-if="link.tags?.length" class="d-flex flex-wrap gap-1 mt-auto">
                      <button v-for="t in link.tags" :key="t" type="button" class="sf-chip tool-card__tag"
                        :class="{ 'sf-chip--accent': toolSelectedTags.includes(t) }" @click="toggleToolTag(t)">{{ t }}</button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
      </SfState>
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
            <label class="form-label small fw-semibold" for="profile-scid">遊戲ID（Star Citizen ID）</label>
            <input id="profile-scid" :value="player.star_citizen_id" type="text" class="form-control" disabled>
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="profile-nickname">暱稱</label>
            <input id="profile-nickname" v-model="profileForm.nickname" type="text" class="form-control">
          </div>
          <!-- Discord 兩個欄位放在同一張卡裡，公開勾選就在下面 ——
               勾選管的是這兩個欄位，分開放會看不出關聯。 -->
          <div class="card scifi-card mb-3">
            <div class="card-body py-3">
              <div class="row g-2">
                <div class="col-12 col-md-6">
                  <label class="form-label small fw-semibold mb-1" for="profile-discord-name">Discord 名稱</label>
                  <input id="profile-discord-name" v-model="profileForm.discord_name" type="text" class="form-control form-control-sm">
                </div>
                <div class="col-12 col-md-6">
                  <label class="form-label small fw-semibold mb-1" for="profile-discord-id">Discord ID</label>
                  <input id="profile-discord-id" v-model="profileForm.discord_id" type="text" class="form-control form-control-sm">
                </div>
              </div>

              <div class="form-check mt-3">
                <input class="form-check-input" type="checkbox" id="discord-public"
                  v-model="profileForm.discord_public">
                <label class="form-check-label small" for="discord-public">
                  公開給其他玩家
                </label>
              </div>
            </div>
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="profile-notes">備註</label>
            <textarea id="profile-notes" v-model="profileForm.notes" class="form-control" rows="2"></textarea>
          </div>
          <button class="btn btn-primary" :disabled="savingProfile" @click="saveProfile">
            <span v-if="savingProfile" class="spinner-border spinner-border-sm me-1"></span>
            儲存
          </button>
        </div>
      </div>

      <!-- 顯示的分頁：勾掉的分頁不出現在分頁列（手機底部列／更多），存在帳號上，換裝置也一樣 -->
      <div v-if="player" class="card scifi-card mt-3">
        <div class="card-body">
          <h3 class="sf-drawer__title"><i class="bi bi-ui-checks-grid me-1"></i>顯示的分頁</h3>
          <div class="tab-prefs">
            <div v-for="tab in orderedTabs" :key="tab.key" class="form-check mb-0">
              <input :id="`tab-show-${tab.key}`" class="form-check-input" type="checkbox"
                :checked="isTabShown(tab.key)"
                :disabled="tab.key === 'profile' || savingTabs" @change="toggleTab(tab.key, $event.target.checked)">
              <label class="form-check-label" :for="`tab-show-${tab.key}`">
                <i :class="tab.icon" class="me-1"></i>{{ tab.label }}
              </label>
            </div>
          </div>
          <div v-if="tabsError" class="sf-bad mt-2">{{ tabsError }}</div>
        </div>
      </div>

      <!-- 更改密碼：只在「個人資料」分頁才放進 DOM，並包成自己的 <form>（附隱藏的帳號欄位）。
           否則瀏覽器會把自動填入的「目前密碼」跟其他分頁的搜尋欄位湊成一組帳密，
           打完搜尋字、切分頁（網址改變）時就跳出「要儲存密碼嗎」。 -->
      <div v-if="player && activeTab === 'profile'" class="card scifi-card mt-3">
        <form class="card-body" autocomplete="on" @submit.prevent="changePassword">
          <input type="text" name="username" autocomplete="username" :value="player.star_citizen_id"
            readonly hidden aria-hidden="true" tabindex="-1">
          <h3 class="sf-drawer__title"><i class="bi bi-key me-1"></i>更改密碼</h3>
          <Transition name="alert-slide">
            <div v-if="pwError" class="alert alert-danger py-2">{{ pwError }}</div>
          </Transition>
          <Transition name="alert-slide">
            <div v-if="pwSuccess" class="alert alert-success py-2">密碼已更新</div>
          </Transition>

          <div class="mb-3">
            <label class="form-label small fw-semibold" for="pw-current">目前密碼</label>
            <input id="pw-current" v-model="pwForm.current_password" type="password" class="form-control"
              autocomplete="current-password">
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="pw-new">新密碼</label>
            <input id="pw-new" v-model="pwForm.new_password" type="password" class="form-control" minlength="6"
              placeholder="至少 6 個字元" autocomplete="new-password">
          </div>
          <div class="mb-3">
            <label class="form-label small fw-semibold" for="pw-confirm">確認新密碼</label>
            <input id="pw-confirm" v-model="pwForm.confirm_password" type="password" class="form-control" minlength="6"
              placeholder="再輸入一次新密碼" autocomplete="new-password">
          </div>
          <button type="submit" class="btn btn-primary" :disabled="changingPassword">
            <span v-if="changingPassword" class="spinner-border spinner-border-sm me-1"></span>
            更改密碼
          </button>
        </form>
      </div>

      <!-- Discord 綁定碼：Discord 帳號沒辦法自己證明它屬於哪個遊戲帳號，
           所以「證明」這一步只能放在需要密碼登入的這一頁。 -->
      <div v-if="player" class="card scifi-card mt-3">
        <div class="card-body">
          <h3 class="sf-drawer__title"><i class="bi bi-discord me-1"></i>Discord 綁定</h3>

          <Transition name="alert-slide">
            <div v-if="bindError" class="alert alert-danger py-2">{{ bindError }}</div>
          </Transition>

          <div v-if="bindCode" class="mb-3">
            <div class="p-3 rounded" style="background: var(--sf-panel-2, rgba(255,255,255,.06))">
              <code class="d-block" style="user-select: all; word-break: break-all">
                /bind handle:{{ player.star_citizen_id }} code:{{ bindCode }}
              </code>
            </div>
            <div class="small mt-2" style="color: var(--sf-text-muted)">
              有效期限至 {{ fmtTime(bindCodeExpiresAt) }}
            </div>
          </div>

          <button class="btn btn-primary" :disabled="issuingCode" @click="issueDiscordCode">
            <span v-if="issuingCode" class="spinner-border spinner-border-sm me-1"></span>
            {{ bindCode ? '重新產生綁定碼' : '產生 Discord 綁定碼' }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- 倉庫 › 新增／異動（跳出視窗：地點 → 物品 → 數量） -->
  <StockWizard ref="stockWizardRef" :fetcher="playerAuth.playerFetch" :locations="locations" :loc-label="locLabel"
    :loc-zh="locZh" :home-location="homeLocation" :history="history" :type-options="itemTypeOptions"
    :dismantle-options="dismantleOptions" @done="onStockDone" />
  <BlueprintMissionsModal ref="bpMissionsRef" :fetcher="playerAuth.playerFetch" :registered-uuids="myBlueprintUuids" />

  <!-- ══════════ 手機底部導覽列（上方分頁列在手機上藏起來）：常用的四個＋「更多」 ══════════ -->
  <nav v-if="isPhone" class="sf-bottom-nav" aria-label="主分頁">
    <button v-for="tab in bottomTabs" :key="tab.key" type="button" class="sf-bottom-nav__item"
      :class="{ active: activeTab === tab.key }" :aria-current="activeTab === tab.key ? 'page' : null"
      @click="setTab(tab.key); moreOpen = false">
      <i :class="tab.icon"></i>{{ tab.short || tab.label }}
    </button>
    <button type="button" class="sf-bottom-nav__item" :class="{ active: moreOpen || moreTabActive }"
      :aria-expanded="moreOpen ? 'true' : 'false'" @click="moreOpen = !moreOpen">
      <i class="bi bi-three-dots"></i>更多
    </button>
  </nav>
  <template v-if="isPhone && moreOpen">
    <div class="sf-sheet-backdrop" @click="moreOpen = false"></div>
    <div ref="moreSheetEl" class="sf-sheet sf-more-list" role="dialog" aria-modal="true" tabindex="-1" aria-label="更多分頁"
      style="bottom: calc(64px + env(safe-area-inset-bottom))">
      <div class="sf-sheet__grip"></div>
      <button v-for="tab in moreTabs" :key="tab.key" type="button" :class="{ active: activeTab === tab.key }"
        @click="setTab(tab.key); moreOpen = false">
        <i :class="tab.icon"></i>{{ tab.label }}<i class="bi bi-chevron-right"></i>
      </button>
    </div>
  </template>
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
import SortTh from '@/components/SortTh.vue'
import SortSelect from '@/components/SortSelect.vue'
import SfFilterSheet from '@/components/SfFilterSheet.vue'
import SfState from '@/components/SfState.vue'
import { useSheet } from '@/composables/useSheet'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { useTableSort } from '@/composables/useTableSort'
import LocationAreaFilter from '@/components/LocationAreaFilter.vue'
import { loadLocationAreas, matchArea } from '@/utils/locationArea'
import BlueprintCalculator from '@/components/BlueprintCalculator.vue'
import BlueprintQuality from '@/components/BlueprintQuality.vue'
import MiningLookup from '@/components/MiningLookup.vue'
import CommodityBuyFinder from '@/components/CommodityBuyFinder.vue'
import ItemDataBrowser from '@/components/ItemDataBrowser.vue'
import StockWizard from '@/components/StockWizard.vue'
import SfModal from '@/components/SfModal.vue'
import { itemTypeLabel, itemTypeOption, loadItemTypeZh } from '@/utils/itemType'
import VehicleDataBrowser from '@/components/VehicleDataBrowser.vue'
import { auecPerUsd, fmtAuec, fmtAuecPerUsd, fmtUsd, vehicleInRanges, VEHICLE_ACQUIRE_OPTIONS } from '@/utils/uexCommodity'
import GameLogReader from '@/components/GameLogReader.vue'
import PayoutCalculator from '@/components/PayoutCalculator.vue'
import RoutePlanner from '@/components/RoutePlanner.vue'
import ContractPlanner from '@/components/ContractPlanner.vue'
import CargoLoader from '@/components/CargoLoader.vue'
import { PLAYER_TABS, orderTabs } from '@/utils/playerTabs'
import ChatCodeTranslator from '@/components/ChatCodeTranslator.vue'
import BlueprintMissionsModal from '@/components/BlueprintMissionsModal.vue'
import MissionBrowser from '@/components/MissionBrowser.vue'
import FactionReputation from '@/components/FactionReputation.vue'
import BlueprintMasterBrowser from '@/components/BlueprintMasterBrowser.vue'
import FleetImport from '@/components/FleetImport.vue'
import VehicleLoadoutLinks from '@/components/VehicleLoadoutLinks.vue'
import AutocompleteField from '@/components/AutocompleteField.vue'
import MultiSelectFilter from '@/components/MultiSelectFilter.vue'
import { blueprintTypeLabel } from '@/utils/blueprintOutputType'
import { dismantleHits, materialLabel } from '@/utils/blueprintMaterial'
import { manufacturerLabel, vehicleNameLabel, vehicleRoleLabel, vehicleSizeLabel, vehicleTypeLabel } from '@/utils/vehicle'
// 地點中文：跟全站一樣查資料庫的翻譯（utils/translations.js），不在前端放對照表
import { loadKnownLocations, loadStorageLocations, loadTranslations, translate } from '@/utils/translations'

const router     = useRouter()
const playerAuth = usePlayerAuthStore()

// 點藍圖名稱看解鎖任務（「我的藍圖」「查詢 › 持有藍圖」共用一個彈窗）
const bpMissionsRef = ref(null)
function openBpMissions(bp) {
  bpMissionsRef.value?.open(bp)
}
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

// 主分頁。目前都沒有下層分頁（subTabs，保留機制備用），
// 頂層 6 個項目，手機上放不下時分頁列可以左右滑（見 scifi-theme.css 的 .scifi-tabs）。
const tabs = PLAYER_TABS
// 後台設定的分頁順序（/player/me 的 tab_order）
const TAB_ORDER_CACHE = 'sc_player_tab_order'
const tabOrder = ref((() => {
  try {
    const v = JSON.parse(localStorage.getItem(TAB_ORDER_CACHE) || '[]')
    return Array.isArray(v) ? v : []
  } catch {
    return []
  }
})())
// 後台設定的開放狀態（/player/me 的 tab_access：{分頁: hidden（預設不顯示）／closed（不開放）}，沒列到的＝開放）
const TAB_ACCESS_CACHE = 'sc_player_tab_access'
const tabAccess = ref((() => {
  try {
    const v = JSON.parse(localStorage.getItem(TAB_ACCESS_CACHE) || '{}')
    return v && typeof v === 'object' && !Array.isArray(v) ? v : {}
  } catch {
    return {}
  }
})())
// 不開放的分頁整個拿掉（分頁列、更多、個人資料的勾選都不出現）
const orderedTabs = computed(() => orderTabs(tabs, tabOrder.value).filter(t => tabAccess.value[t.key] !== 'closed'))

// 手機／平板（方案見專案文件「星際公民工具-玩家頁手機平板UI方案」）：
// 手機上方分頁列換成底部導覽列，常用四個直接放，其餘收進「更多」
const { isPhone } = useBreakpoint()
const BOTTOM_TAB_KEYS = ['warehouse', 'blueprints', 'fleet', 'search']
const BOTTOM_COUNT = 4

// ── 顯示的分頁（個人資料可勾選；存在帳號上 hidden_tabs／shown_tabs，這台瀏覽器另存一份避免載入時閃一下）──
// 一般分頁：勾掉的記在 hidden_tabs；後台設成「預設不顯示」的分頁：玩家自己打開的記在 shown_tabs
const tabsCacheKey = () => `sc_player_hidden_tabs:${playerAuth.starCitizenId || ''}`
function readTabsCache() {
  try {
    const v = JSON.parse(localStorage.getItem(tabsCacheKey()) || '[]')
    return Array.isArray(v) ? v.filter(k => typeof k === 'string') : []
  } catch {
    return []
  }
}
const hiddenTabs = ref(readTabsCache())
const shownCacheKey = () => `sc_player_shown_tabs:${playerAuth.starCitizenId || ''}`
const shownTabs = ref((() => {
  try {
    const v = JSON.parse(localStorage.getItem(shownCacheKey()) || '[]')
    return Array.isArray(v) ? v.filter(k => typeof k === 'string') : []
  } catch {
    return []
  }
})())
function applyShownTabs(keys) {
  shownTabs.value = (keys || []).filter(k => typeof k === 'string')
  try { localStorage.setItem(shownCacheKey(), JSON.stringify(shownTabs.value)) } catch { /* 存不了就算了 */ }
}
/** 這個分頁現在要不要顯示（個人資料一定顯示） */
function isTabShown(key) {
  if (key === 'profile') return true
  if (tabAccess.value[key] === 'hidden') return shownTabs.value.includes(key)
  return !hiddenTabs.value.includes(key)
}
const savingTabs = ref(false)
const tabsError = ref('')
function applyHiddenTabs(keys) {
  hiddenTabs.value = (keys || []).filter(k => k !== 'profile')
  try { localStorage.setItem(tabsCacheKey(), JSON.stringify(hiddenTabs.value)) } catch { /* 存不了就算了 */ }
}
// 被隱藏的分頁如果正好是目前這頁（例如從舊連結進來），還是照常顯示
const visibleTabs = computed(() => orderedTabs.value.filter(t => t.key === activeTab.value || isTabShown(t.key)))
const bottomTabs = computed(() => {
  const shown = visibleTabs.value.filter(t => t.key !== 'profile')
  const first = shown.filter(t => BOTTOM_TAB_KEYS.includes(t.key))   // 照後台排的順序
  const rest = shown.filter(t => !BOTTOM_TAB_KEYS.includes(t.key))
  return [...first, ...rest].slice(0, BOTTOM_COUNT)
})
const moreTabs = computed(() => visibleTabs.value.filter(t => !bottomTabs.value.includes(t)))

async function toggleTab(key, show) {
  if (key === 'profile') return
  const before = { hidden: hiddenTabs.value, shown: shownTabs.value }
  let hidden = before.hidden
  let shown = before.shown
  if (tabAccess.value[key] === 'hidden') shown = show ? [...shown.filter(k => k !== key), key] : shown.filter(k => k !== key)
  else hidden = show ? hidden.filter(k => k !== key) : [...hidden.filter(k => k !== key), key]
  tabsError.value = ''
  applyHiddenTabs(hidden)
  applyShownTabs(shown)
  savingTabs.value = true
  const res = await playerAuth.playerFetch('/player/me/tabs', {
    method: 'PUT', body: JSON.stringify({ hidden_tabs: hidden, shown_tabs: shown }),
  })
  savingTabs.value = false
  const data = res ? await res.json().catch(() => null) : null
  if (!res?.ok || !data?.success) {
    applyHiddenTabs(before.hidden)
    applyShownTabs(before.shown)
    tabsError.value = data?.message || '儲存失敗。'
  }
}

const moreOpen = ref(false)
// 「更多」底部面板：Esc 關閉、開啟時焦點移進面板、關閉後回到「更多」按鈕
const moreSheetEl = ref(null)
useSheet(moreOpen, moreSheetEl)

// 刪除確認（藍圖／整款船艦／單一艘共用）：confirmDeleteKey＝正在問「確定刪除？」的那一列，
// deletingKey＝送出中的那一列（按鈕停用＋轉圈）。key：bp:<id>、fleet:<id>、unit:<id>:<第幾艘>
const confirmDeleteKey = ref('')
const deletingKey = ref('')
const moreTabActive = computed(() => !bottomTabs.value.some(t => t.key === activeTab.value))
// 手機的排序下拉選項（表頭在手機上看不到）
const INVENTORY_SORT_OPTIONS = [{ field: 'item', label: '物品' }, { field: 'location', label: '地點' }, { field: 'quantity', label: '數量' }]
const MY_BP_SORT_OPTIONS = [{ field: 'name', label: '名稱' }, { field: 'type', label: '類型' },
  { field: 'craft_time', label: '製作時間' }, { field: 'ingredients', label: '材料' }]
const MY_FLEET_SORT_OPTIONS = [{ field: 'name', label: '船艦' }, { field: 'type', label: '類型' }, { field: 'size', label: '尺寸' },
  { field: 'manufacturer', label: '廠商' }, { field: 'role', label: '角色' }, { field: 'cargo', label: '載貨' }, { field: 'usd', label: '美金' }, { field: 'auec', label: '遊戲幣' }, { field: 'rent', label: '租用' }, { field: 'ratio', label: 'aUEC／美金' }, { field: 'quantity', label: '數量' }]

/** 某個主分頁的下層分頁清單（沒有就回空陣列）。 */
function subTabsOf(key) {
  return tabs.find(t => t.key === key)?.subTabs || []
}
// 分頁狀態同步到 URL 的 ?tab= —— 這樣重新整理、手機切回瀏覽器、
// 分享連結給隊友都會停在同一個分頁，瀏覽器的返回鍵也會退回上一個分頁
// 而不是直接離開 /me。
const route = useRoute()
const validTabs = tabs.map(t => t.key)
// 舊網址：商品購買地點（?tab=search|warehouse&sub=commodities、?tab=commodities）、
// 物品資料（?tab=warehouse&sub=items、?tab=itemdata）改到「物品」分頁的兩個下層分頁
const legacySub = (['search', 'warehouse'].includes(route.query.tab) && route.query.sub === 'commodities')
  || route.query.tab === 'commodities' ? 'commodities'
  : (route.query.tab === 'warehouse' && route.query.sub === 'items') || route.query.tab === 'itemdata' ? 'data' : ''
const legacyCommodities = !!legacySub
const activeTab = ref(legacySub ? 'items' : (validTabs.includes(route.query.tab) ? route.query.tab : 'warehouse'))

/** 某個主分頁的預設下層分頁（沒有下層就回 ''）。 */
function defaultSub(tabKey) {
  return subTabsOf(tabKey)[0]?.key || ''
}

function validSub(tabKey, sub) {
  return subTabsOf(tabKey).some(t => t.key === sub)
}

// 倉庫 › 新增／異動：跳出視窗（components/StockWizard.vue）。舊網址 ?tab=warehouse&sub=add|adjust 一進來就打開
const openStockOnMount = activeTab.value === 'warehouse' && ['add', 'adjust'].includes(route.query.sub)
const stockWizardRef = ref(null)
function onStockDone() {
  loadMyInventory()
  loadLocations()
  loadHistory()
}
// 艦隊的「登記船艦資料」（?tab=fleet&sub=data 直接展開；原本的批量登記已併進來，舊網址 sub=bulk 也展開它）
const fleetDataOpen = ref(activeTab.value === 'fleet' && ['data', 'bulk'].includes(route.query.sub))
// 倉庫的庫存紀錄同理（舊網址 ?sub=history 直接展開）
const historyOpen = ref(activeTab.value === 'warehouse' && route.query.sub === 'history')
// 藍圖的「登記藍圖資料」（原本的藍圖資料＋批量登記合併；舊網址 sub=data|bulk 都展開它）
const bpDataOpen = ref(activeTab.value === 'blueprints' && ['data', 'bulk'].includes(route.query.sub))
const fleetImportOpen = ref(false)

const activeSub = ref(legacySub || (
  validSub(activeTab.value, route.query.sub)
    ? route.query.sub
    : defaultSub(activeTab.value)
))

// 「查詢持有資訊」記在網址上的條件（對應見下面 SEARCH_URL_STR／SEARCH_URL_ARR）。
// 寫成常數放在這裡：syncUrl 可能在 setup 早期就被呼叫，那時下面的對照表還沒宣告
const SEARCH_URL_KEYS = ['k', 'q', 'pk', 'pid', 'pn', 'p', 'i_t', 'i_sys', 'i_pl', 'i_loc',
  'b_t', 'f_t', 'f_s', 'f_m', 'f_r']

function syncUrl() {
  const query = { ...route.query, tab: activeTab.value }
  if (activeSub.value) query.sub = activeSub.value
  else delete query.sub
  // 「查詢持有資訊」的條件只留在那個分頁的網址上
  if (activeTab.value !== 'search') SEARCH_URL_KEYS.forEach(k => delete query[k])
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

// 目前的分頁被後台設成「不開放」（例如舊連結、或剛載入到最新設定）：換到第一個看得到的分頁
watch([activeTab, tabAccess], () => {
  if (tabAccess.value[activeTab.value] !== 'closed') return
  const next = orderedTabs.value.find(t => isTabShown(t.key)) || orderedTabs.value[0]
  if (next) setTab(next.key)
}, { immediate: true })

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
// 不用 { immediate: true } 是因為 bpHolders 等宣告在下面，
// 立即執行會踩到 const 的 TDZ。
function loadForTab(tab) {
  // 「查詢」：點開哪一區才載入那一區的資料（見 loadSearchSections）
  if (tab === 'search') loadSearchSections()
  if ((tab === 'fleet' || tab === 'route' || tab === 'cargo') && !fleetLoaded.value) loadFleet()
  if (tab === 'tools') loadToolLinks()
  // 倉庫、物品資料搜尋卡的「物品類型」選項（物品主檔的全部類型）
  if ((tab === 'warehouse' || tab === 'items') && !itemTypes.value.length) loadItemTypes()
  // 共用搜尋卡的類型選項（主檔全部類型）、艦隊共用搜尋卡的類型／尺寸／廠商／角色選項
  if (tab === 'blueprints' && !blueprintOutputTypes.value.length) loadBlueprintOutputTypes()
  // 倉庫、物品資料搜尋卡的「拆解材料」選項
  if ((tab === 'warehouse' || tab === 'items') && !dismantleMaterials.value.length) loadDismantleMaterials()
  if (tab === 'fleet' && !vehicleFacetsLoaded) loadVehicleFacets()
}

watch([activeTab, activeSub], ([tab, sub]) => loadForTab(tab, sub))

// 「查詢持有資訊」三部分一起載入（第一次進來才載；之後條件改了由各自的 watch 重查）
let whoSectionsLoaded = false
function loadSearchSections() {
  ensureRoster()
  if (!itemTypes.value.length) loadItemTypes()
  if (!blueprintOutputTypes.value.length) loadBlueprintOutputTypes()
  if (!vehicleFacetsLoaded) loadVehicleFacets()
  if (whoSectionsLoaded) return
  whoSectionsLoaded = true
  if (!whoLoaded) runStockSearch()
  loadBlueprintHolders()
  loadFleetHolders()
}

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
  playerError.value = ''
  const res = await playerAuth.playerFetch('/player/me')
  loadingPlayer.value = false
  if (!res) { playerError.value = '網路錯誤，請稍後再試'; return }
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) {
    player.value = data.data
    applyHiddenTabs(data.data.hidden_tabs)
    applyShownTabs(data.data.shown_tabs)
    tabAccess.value = data.data.tab_access && typeof data.data.tab_access === 'object' ? data.data.tab_access : {}
    try { localStorage.setItem(TAB_ACCESS_CACHE, JSON.stringify(tabAccess.value)) } catch { /* 存不了就算了 */ }
    tabOrder.value = Array.isArray(data.data.tab_order) ? data.data.tab_order : []
    try { localStorage.setItem(TAB_ORDER_CACHE, JSON.stringify(tabOrder.value)) } catch { /* 存不了就算了 */ }
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
// 我的藍圖已登記的主檔 uuid（登記藍圖資料標「已登記」、不能再勾）
const myBlueprintUuids = computed(() => blueprints.value.map(bp => bp.blueprint_uuid).filter(Boolean))

/** 批量登記完成後，把「我的藍圖」那一頁的清單也更新（否則要手動重新整理）。 */
async function onBulkRegistered() {
  await loadBlueprints()
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

// 登出（或登入過期、refresh 失敗被 playerFetch 清掉登入狀態）→ 直接整頁換到登入頁。
// 不用 router.push：登入頁是延遲載入的 chunk，載入慢或部署後舊 chunk 已經不在時
// 畫面會停在原地；整頁換掉也順便把上一位玩家留在記憶體裡的資料清乾淨。
function goLogin() {
  window.location.replace(router.resolve(PLAYER_LOGIN_PATH).href)
}

function logout() {
  playerAuth.clearAuth()
  goLogin()
}

watch(() => playerAuth.isLoggedIn, (loggedIn) => { if (!loggedIn) goLogin() })

// ── 地點清單（給新增物品的地點下拉選單用） ─────────────────────
// 來源有兩個：資料庫裡已經用過的地點（/inventory/locations，排前面），加上
// 地點資料庫裡「可存放」的地點（/starmap/storage-locations，即使還沒有人登記過庫存
// 也能選）。地點資料還沒同步時退回翻譯表裡的遊戲地點名稱。
const locations = ref([])
async function loadLocations() {
  const [res, storage] = await Promise.all([
    playerAuth.playerFetch('/inventory/locations'),
    loadStorageLocations(),
    loadLocationAreas(),
  ])
  const known = storage.length ? storage : await loadKnownLocations()
  const data = res ? await res.json().catch(() => null) : null
  const used = (res?.ok && data?.success) ? (data.data || []) : []
  const seen = new Set(used.map(loc => loc.toLowerCase()))
  locations.value = [...[...used].sort(), ...known.filter(loc => !seen.has(loc.toLowerCase()))]
}

// ── 「查詢」頁分頁篩選欄位要用的類型清單（各自進分頁時才載，見 loadForTab）──
const itemTypes = ref([])
async function loadItemTypes() {
  const res = await playerAuth.playerFetch('/item/types')
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) {
    itemTypes.value = data.data || []
    loadItemTypeZh(itemTypes.value)
  }
}
// 物品類型選項：中文（代碼），依中文排序（倉庫共用搜尋卡、查詢持有資訊 › 持有物品）
const itemTypeOptions = computed(() => itemTypes.value.map(itemTypeOption)
  .sort((a, b) => a.label.localeCompare(b.label, 'zh-Hant')))

const blueprintOutputTypes = ref([])
async function loadBlueprintOutputTypes() {
  const res = await playerAuth.playerFetch('/blueprint/master/types')
  if (!res) return
  const data = await res.json().catch(() => null)
  if (res.ok && data?.success) blueprintOutputTypes.value = data.data || []
}

// ── 篩選區（倉庫分頁頂端共用一張：同一組條件同時篩物品庫存與庫存紀錄）──────
// 庫存紀錄已經併成同一頁的展開區塊，上下兩份清單看同一個物品／地點才直覺。
// '' = 全部。用 item_id 比對而不是名稱，見 InventoryFilterBar 的說明。
// 地點是「星系／行星／地點」三段多選（utils/locationArea.js 的 matchArea）。
// 物品名稱比對英文＋中文（含即符合）、物品類型比對 item_type；名稱＋類型也帶給「物品資料」。
// buyable（只看買得到）只給物品資料用
const stockFilter   = reactive({ q: '', types: [], systems: [], planets: [], locations: [], buyable: false, dismantlable: false, dismantle: [] })
// 物品資料分頁自己的搜尋條件（名稱、類型、只看買得到、只看可拆解、拆解材料）
const itemDataFilter = reactive({ q: '', types: [], buyable: false, dismantlable: false, dismantle: [] })
const itemDataFilters = computed(() => ({
  q: itemDataFilter.q.trim(), types: itemDataFilter.types, buyable: itemDataFilter.buyable,
  dismantlable: itemDataFilter.dismantlable, dismantle: itemDataFilter.dismantle }))

// 拆解材料：拆解後會回收所選材料的物品 {物品 uuid: [符合的拆解回收]}（後端從藍圖的拆解回收反查）。
// 物品庫存、庫存紀錄在前端篩，物品資料把條件帶去後端
const dismantleMap = ref({})
let dismantleSeq = 0
watch(() => [...stockFilter.dismantle], async (names) => {
  const mine = ++dismantleSeq
  if (!names.length) { dismantleMap.value = {}; return }
  const qs = names.map(n => `material=${encodeURIComponent(n)}`).join('&')
  const res = await playerAuth.playerFetch(`/blueprint/master/dismantle-items?${qs}`)
  const data = res?.ok ? await res.json().catch(() => null) : null
  if (mine === dismantleSeq) dismantleMap.value = data?.success ? (data.data || {}) : {}
})

function applyFilter(rows, f) {
  const q = f.q.trim().toLowerCase()
  return rows.filter(r =>
    (!q || [r.item_name, r.item_name_zh].some(t => (t || '').toLowerCase().includes(q)))
    && (!f.types.length || f.types.includes(r.item_type))
    && (!f.dismantle?.length || !!dismantleMap.value[r.item_id])
    && matchArea(r.location, f))
}

// ── 我的個人庫 ────────────────────────────────────────────────
const myInventory      = ref([])
const loadingInventory = ref(false)
const filteredInventory = computed(() => applyFilter(myInventory.value, stockFilter))
const itemNameOf = r => r.item_name_zh || r.item_name
const inventorySort = useTableSort(filteredInventory, { accessors: {
  item: itemNameOf, location: r => locLabel(r.location) + (r.container ? ` / ${r.container}` : ''),
} })

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
const filteredHistory = computed(() => applyFilter(history.value, stockFilter))
const historySort = useTableSort(filteredHistory, { accessors: {
  ts: r => new Date(r.ts).getTime(), action: r => (r.delta > 0 ? 1 : 0), item: itemNameOf,
  location: r => locLabel(r.location) + (r.container ? ` / ${r.container}` : ''),
} })
// 共用篩選的選項涵蓋兩份清單；紀錄區塊收起時只顯示庫存的筆數
const warehouseFilterRows = computed(() => [...myInventory.value, ...history.value])
const warehouseFilterCounts = computed(() => [
  { label: '物品庫存', matched: filteredInventory.value.length, total: myInventory.value.length },
  ...(historyOpen.value
    ? [{ label: '庫存紀錄', matched: filteredHistory.value.length, total: history.value.length }]
    : []),
])

// 倉庫工具列的「重新整理」：庫存一定重抓，紀錄有展開才一起重抓
function refreshWarehouse() {
  loadMyInventory()
  if (historyOpen.value) loadHistory()
}
const itemDataRef = ref(null)

// ── 定居點（玩家自己設定，只能選可選居住地）＋全部物品轉移到定居點 ────────
const homeOpen = ref(false)
const homeLocations = ref([])
const homeDraft = ref('')
const savingHome = ref(false)
const homeMessage = ref('')
const homeMessageType = ref('alert-success')
const homeLocation = computed(() => player.value?.home_location || '')

async function loadHomeLocations() {
  if (homeLocations.value.length) return
  const res = await playerAuth.playerFetch('/starmap/home-locations')
  const data = res ? await res.json().catch(() => null) : null
  if (res?.ok && data?.success) homeLocations.value = data.data || []
}
function toggleHome() {
  homeOpen.value = !homeOpen.value
  if (homeOpen.value) {
    homeDraft.value = homeLocation.value
    homeMessage.value = ''
    loadHomeLocations()
  }
}
const homeGroups = computed(() => {
  const groups = new Map()
  for (const h of homeLocations.value) {
    const key = h.system || ''
    if (!groups.has(key)) groups.set(key, { system: key, system_zh: h.system_zh, items: [] })
    groups.get(key).items.push(h)
  }
  return [...groups.values()]
})
function homeOptionLabel(h) {
  const where = h.planet || h.parent
  const name = h.name_zh && h.name_zh !== h.name ? `${h.name}（${h.name_zh}）` : locLabel(h.name)
  return `${name}${where && where !== h.system ? ` — ${h.planet_zh || h.parent_zh || where}` : ''}`
}
async function saveHome(name) {
  savingHome.value = true
  homeMessage.value = ''
  const res = await playerAuth.playerFetch('/player/me/home', {
    method: 'PUT', body: JSON.stringify({ home_location: name || null }),
  })
  const data = res ? await res.json().catch(() => null) : null
  savingHome.value = false
  if (!(res?.ok && data?.success)) {
    homeMessageType.value = 'alert-danger'
    homeMessage.value = data?.message || '儲存失敗'
    return
  }
  player.value = { ...player.value, home_location: data.data.home_location }
  homeDraft.value = data.data.home_location || ''
  homeMessageType.value = 'alert-success'
  homeMessage.value = data.data.home_location ? `定居點已設為 ${locLabel(data.data.home_location)}` : '已清除定居點'
}

const movingAll = ref(false)
const moveAllMessage = ref('')
const moveAllMessageType = ref('alert-success')
/** 會被移動的庫存（已經在定居點、沒放容器的不動；跟後端 Inventory.move_all 同一個規則） */
const moveAllPending = computed(() => myInventory.value.filter(r =>
  r.quantity > 0 && !(r.location === homeLocation.value && !r.container)))
const moveAllUnits = computed(() => moveAllPending.value.reduce((n, r) => n + (r.quantity || 0), 0))
const moveAllSources = computed(() => new Set(moveAllPending.value.map(r => `${r.location}|${r.container || ''}`)).size)
watch(homeOpen, (v) => { if (v) moveAllMessage.value = '' })

async function moveAllHome() {
  movingAll.value = true
  moveAllMessage.value = ''
  const res = await playerAuth.playerFetch('/player/inventory/move-all-home', { method: 'POST' })
  const data = res ? await res.json().catch(() => null) : null
  movingAll.value = false
  if (!(res?.ok && data?.success)) {
    moveAllMessageType.value = 'alert-danger'
    moveAllMessage.value = data?.message || '轉移失敗，請稍後再試'
    return
  }
  const d = data.data
  moveAllMessageType.value = d.failed?.length ? 'alert-warning' : 'alert-success'
  moveAllMessage.value = `已轉移 ${d.moved} 筆、共 ${d.units} 件到 ${locLabel(d.home_location)}`
    + (d.failed?.length ? `；${d.failed.length} 筆失敗：${d.failed.map(f => f.message).join('；')}` : '')
  loadMyInventory()
  loadHistory()
  loadLocations()
}

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

// 「藍圖」分頁頂端的共用搜尋（名稱關鍵字＋類型可多選、取聯集）：
// 「我的藍圖」整份已載入，直接在前端篩；「登記藍圖資料」把同一組條件帶去後端查主檔。
// 類型選項用主檔的全部類型（/blueprint/master/types），三區才會一致。
const bpFilterQuery = ref('')
const myBpTypes = ref([])
const dismantleMaterials = ref([])
const dismantleOptions = computed(() => dismantleMaterials.value.map(name => ({
  value: name, label: materialLabel({ name, resource_type_uuid: 'x' }),
})))
async function loadDismantleMaterials() {
  const res = await playerAuth.playerFetch('/blueprint/master/dismantle-materials')
  const data = res?.ok ? await res.json().catch(() => null) : null
  if (!data?.success) return
  dismantleMaterials.value = data.data || []
  loadTranslations('mining_resource', dismantleMaterials.value)
  loadTranslations('item', dismantleMaterials.value)
}
// 「只看需任務解鎖」預設勾選。預設可用的藍圖每個人本來就有，視同已登記：
// 我的藍圖、登記藍圖資料都不列（登記藍圖資料傳 hideAvailable，後端 available=0）
const bpHasMissionsOnly = ref(true)
// 「只顯示未登記」只作用在展開的「登記藍圖資料」，預設勾選（自己已登記的不用再看到）
const bpUnregisteredOnly = ref(true)
const bpFilters = computed(() => ({
  q: bpFilterQuery.value.trim(), types: myBpTypes.value,
  hasMissions: bpHasMissionsOnly.value, hideAvailable: true, unregistered: bpUnregisteredOnly.value,
}))
// 手機「篩選」按鈕上的數字：收進面板的條件有幾個在作用
const bpSheetCount = computed(() => myBpTypes.value.length + (bpHasMissionsOnly.value ? 1 : 0)
  + (bpDataOpen.value && bpUnregisteredOnly.value ? 1 : 0))
const bpFilterActive = computed(() => !!(bpFilters.value.q || myBpTypes.value.length || bpHasMissionsOnly.value))
function clearBpFilter() {
  bpFilterQuery.value = ''
  myBpTypes.value = []
  bpHasMissionsOnly.value = false
}
// ── 任務分頁：共用搜尋卡（條件直接傳給 MissionBrowser）；「只看有藍圖」預設勾選 ──
const missionBrowserRef = ref(null)
// 任務 › 勢力聲望（?tab=missions&sub=reputation 直接展開）
const factionRepOpen = ref(activeTab.value === 'missions' && route.query.sub === 'reputation')
const MS_LEGALITY_OPTIONS = [{ value: 'legal', label: '合法' }, { value: 'illegal', label: '違法' }]
const msFilter = reactive({ q: '', scopes: [], systems: [], factions: [], legality: [], hasBlueprints: true, hasReward: false })
const msFacets = ref({ reward_scopes: [], star_systems: [], factions: [] })
const msFactionOptions = computed(() => msFacets.value.factions.map(f => ({
  value: f.uuid, label: f.name_zh ? `${f.name_zh}（${f.name}）` : f.name,
})))
// 類型、星系選項：中文（英文），中文從翻譯資料庫查（見 utils/translations.js）
const zhOption = (domain, en) => { const zh = translate(domain, en); return { value: en, label: zh ? `${zh}（${en}）` : en } }
const msScopeOptions = computed(() => msFacets.value.reward_scopes.map(s => zhOption('mission_type', s)))
const msSystemOptions = computed(() => msFacets.value.star_systems.map(s => zhOption('location', s)))
const msSheetCount = computed(() => msFilter.scopes.length + msFilter.systems.length + msFilter.factions.length
  + msFilter.legality.length + (msFilter.hasBlueprints ? 1 : 0) + (msFilter.hasReward ? 1 : 0))
const msFilterActive = computed(() => !!msFilter.q.trim() || msSheetCount.value > 0)
function clearMsFilter() {
  Object.assign(msFilter, { q: '', scopes: [], systems: [], factions: [], legality: [], hasBlueprints: false, hasReward: false })
}
let msFacetsLoaded = false
watch(activeTab, async (tab) => {
  if (tab !== 'missions' || msFacetsLoaded) return
  msFacetsLoaded = true
  const res = await playerAuth.playerFetch('/mission/facets')
  const body = res?.ok ? await res.json().catch(() => null) : null
  if (body?.success) {
    msFacets.value = { reward_scopes: [], star_systems: [], factions: [], ...body.data }
    loadTranslations('mission_type', msFacets.value.reward_scopes)
    loadTranslations('location', msFacets.value.star_systems)
  } else msFacetsLoaded = false
}, { immediate: true })
// 我的藍圖：預設可用的不列
const visibleBlueprints = computed(() => blueprints.value.filter(bp => !bp.master?.is_available_by_default))
// 藍圖名稱的候選用「查詢持有資訊」同一支 searchBlueprintNames（主檔，中英文都比對）；候選右邊顯示英文名與類型
function blueprintNameMeta(bp) {
  const parts = [bp.name_zh && bp.name !== bp.name_zh ? bp.name : '', bp.output_type ? blueprintTypeLabel(bp.output_type) : '']
  return parts.filter(Boolean).join(' · ')
}
const filteredBlueprints = computed(() => {
  const { q: rawQ, types, hasMissions } = bpFilters.value
  const q = rawQ.toLowerCase()
  if (!q && !types.length && !hasMissions) return visibleBlueprints.value
  return visibleBlueprints.value.filter(bp => {
    if (types.length && !types.includes(bp.master?.output_type)) return false
    if (hasMissions && !bp.master?.mission_count) return false
    if (!q) return true
    return [bp.name, bp.master?.name, bp.master?.name_zh]
      .some(t => (t || '').toLowerCase().includes(q))
  })
})
const myBpSort = useTableSort(filteredBlueprints, { accessors: {
  name: bp => bp.master?.name_zh || bp.name,
  type: bp => (bp.master?.output_type ? blueprintTypeLabel(bp.master.output_type) : bp.master?.output_type_label),
  craft_time: bp => bp.master?.craft_time_seconds,
  ingredients: bp => bp.master?.ingredient_count,
} })
// 刪除藍圖的結果訊息（登記一律走「登記藍圖資料」，原本這裡的單張登記表單已拿掉）
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

// ── 展開某張藍圖的完整配方（點「N 種」材料時才抓，不預載）──────────
const recipeFor     = ref(null)
// 品質試算展開的是哪一列（跟材料展開各自獨立）
const qualityFor    = ref(null)

function showRecipe(bp) {
  // 再點一次收起來；配方與試算由 BlueprintCalculator 自己載入
  recipeFor.value = recipeFor.value === bp._id ? null : bp._id
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
const blueprintTypeOptions = computed(() =>
  blueprintOutputTypes.value.map(t => ({ value: t, label: blueprintTypeLabel(t) })))

let bpHolderSeq = 0
async function loadBlueprintHolders() {
  const seq = ++bpHolderSeq
  clearTree('b|')
  loadingBpHolders.value = true
  const params = new URLSearchParams({ limit: '100' })
  if (bpSelectedName.value || bpNameQuery.value) params.set('q', bpSelectedName.value || bpNameQuery.value)
  bpSelectedTypes.value.forEach(t => params.append('output_type', t))
  if (bpPlayerScid.value) params.set('player_id', bpPlayerScid.value)
  const res = await playerAuth.playerFetch(`/blueprint/holders?${params.toString()}`)
  if (seq !== bpHolderSeq) return   // 已經有更新的查詢在跑了
  loadingBpHolders.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  bpHolders.value = (res.ok && data?.success) ? (data.data || []) : []
}

watch([bpSelectedName, bpNameQuery, bpSelectedTypes, bpPlayerScid], loadBlueprintHolders)

async function searchBlueprintNames(q) {
  const res = await playerAuth.playerFetch(`/blueprint/master/search?q=${encodeURIComponent(q)}&limit=20`)
  if (!res) return []
  const data = await res.json().catch(() => null)
  return (res.ok && data?.success) ? (data.data || []) : []
}
function blueprintNameLabel(c) { return c.name_zh || c.name }





async function removeBlueprint(bp) {
  const key = `bp:${bp._id}`
  if (deletingKey.value) return
  deletingKey.value = key
  blueprintError.value = ''
  const res = await playerAuth.playerFetch(`/player/blueprints/${bp._id}`, { method: 'DELETE' })
  const data = res ? await res.json().catch(() => null) : null
  deletingKey.value = ''
  if (res?.ok && data?.success) {
    if (confirmDeleteKey.value === key) confirmDeleteKey.value = ''
    await loadBlueprints()
  } else {
    blueprintError.value = data?.message || '刪除失敗，請稍後再試'
  }
}

// 查詢 › 持有藍圖：手機「篩選」面板裡的條件（名稱以外）
const bpHolderSheetCount = computed(() => bpSelectedTypes.value.length)
function clearBpHolderSheet() {
  bpSelectedTypes.value = []
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
let whoLoaded = false
async function runStockSearch() {
  whoLoaded = true
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
  const res = await playerAuth.playerFetch(`/inventory/search?${params.toString()}`)
  if (seq !== whoSeq) return          // 已經有更新的搜尋在跑了
  loadingWho.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  whoRows.value = (res.ok && data?.success) ? (data.data || []) : []
  loadItemTypeZh(whoRows.value.map(r => r.item_type).filter(Boolean), whoRows.value.map(r => r.item_sub_type).filter(Boolean))
}

watch([itemsSelectedItemId, itemsNameQuery, itemsSelectedTypes, itemsSelectedSystems, itemsSelectedPlanets,
  itemsSelectedLocations, itemsPlayerScid], runStockSearch)


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


// 查詢 › 持有物品：手機「篩選」面板裡的條件（名稱以外）
const itemsSheetCount = computed(() => itemsSelectedTypes.value.length + itemsSelectedSystems.value.length
  + itemsSelectedPlanets.value.length + itemsSelectedLocations.value.length)
function clearItemsSheet() {
  itemsSelectedTypes.value = []
  itemsSelectedSystems.value = []
  itemsSelectedPlanets.value = []
  itemsSelectedLocations.value = []
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

// ── 工具網站 ────────────────────────────────────────────────
// 每次進分頁都重抓（清單很小），後台剛改完玩家這邊切回來就看得到
const toolLinks        = ref([])
const toolTags         = ref([])   // 標籤順序（後端一起回傳）
const toolQuery        = ref('')
const toolSelectedTags = ref([])
const toolTagOptions = computed(() => toolTags.value.map(t => ({ value: t, label: t })))
// 先篩選再依標籤分組，預設全部展開
const toolLinkGroups = computed(() => {
  const q = toolQuery.value.trim().toLowerCase()
  const picked = toolSelectedTags.value
  const matches = link => !q || [link.title, link.url, link.description, ...(link.tags || [])]
    .some(v => (v || '').toLowerCase().includes(q))
  const groups = new Map(toolTags.value.map(t => [t, { name: t, links: [] }]))
  const untagged = { name: '', links: [] }
  for (const link of toolLinks.value) {
    if (!matches(link)) continue
    const tags = link.tags || []
    if (!tags.length) {
      if (!picked.length) untagged.links.push(link)
      continue
    }
    for (const tag of tags) {
      if (picked.length && !picked.includes(tag)) continue
      if (!groups.has(tag)) groups.set(tag, { name: tag, links: [] })
      groups.get(tag).links.push(link)
    }
  }
  return [...groups.values(), untagged].filter(g => g.links.length)
})
// 標籤快速篩選按鈕上的數量（後台設定的順序）
const toolTagCounts = computed(() => toolTags.value
  .map(tag => ({ tag, count: toolLinks.value.filter(l => (l.tags || []).includes(tag)).length }))
  .filter(t => t.count))
function toggleToolTag(tag) {
  const i = toolSelectedTags.value.indexOf(tag)
  toolSelectedTags.value = i >= 0 ? toolSelectedTags.value.filter(t => t !== tag) : [...toolSelectedTags.value, tag]
}
function toolHost(url) {
  try { return new URL(url).hostname.replace(/^www\./, '') } catch { return url }
}
// 卡片左上角的字母圖示（不去抓外站的 favicon）
const toolInitial = link => ((link.title || toolHost(link.url) || '?').trim()[0] || '?').toUpperCase()
const collapsedToolGroups = reactive(new Set())
function toggleToolGroup(name) {
  if (collapsedToolGroups.has(name)) collapsedToolGroups.delete(name)
  else collapsedToolGroups.add(name)
}
const loadingToolLinks = ref(false)
const toolLinksError   = ref('')

async function loadToolLinks() {
  loadingToolLinks.value = true
  const res = await playerAuth.playerFetch('/player/tool-links')
  const data = res ? await res.json().catch(() => null) : null
  loadingToolLinks.value = false
  if (res?.ok && data?.success) {
    toolLinks.value = data.data || []
    toolTags.value = data.tags || []
    toolLinksError.value = ''
  } else if (!toolLinks.value.length) {
    toolLinksError.value = data?.message || '讀取工具網站失敗'
  }
}

// ── 艦隊 › 我的艦隊 ──────────────────────────────────────────
const fleet            = ref([])
const loadingFleet     = ref(false)
const fleetLoaded      = ref(false)
const fleetError       = ref('')
const fleetMaxQuantity = ref(99)
const savingFleetId    = ref('')
// 已經在我的艦隊裡的載具（登記船艦資料標「已登記」、不能再勾）
const fleetVehicleUuids = computed(() => fleet.value.map(r => r.vehicle_uuid).filter(Boolean))
const fleetShipCount   = computed(() => fleet.value.reduce((n, r) => n + (r.quantity || 0), 0))

// 「艦隊」分頁頂端的共用搜尋（同一欄位取聯集、欄位之間 AND）：
// 「我的艦隊」整份已載入，直接在前端篩；「批量登記」把同一組條件帶去後端查載具主檔。
// 選項＝載具主檔的 facets（批量登記查得到的）再補上自己艦隊裡有、但主檔已下架的值。
// 尺寸統一用字串比對（facets 跟後端 size_class 參數都是字串）。
const myFleetQuery = ref('')
// 取得方式：只看可用遊戲幣購買／可租船（UEX 價格 vehicle.uex_price，多選取聯集）
const myFleetAcquire = ref([])
const myFleetTypes = ref([])
const myFleetSizes = ref([])
const myFleetMfrs  = ref([])
const myFleetRoles = ref([])
// 價格（美金或遊戲幣）、貨物量（SCU）範圍；空字串＝不限
const myFleetRange = reactive({ priceCurrency: 'usd', priceMin: '', priceMax: '', scuMin: '', scuMax: '' })
const fleetRangeCount = computed(() => ((myFleetRange.priceMin !== '' || myFleetRange.priceMax !== '') ? 1 : 0)
  + ((myFleetRange.scuMin !== '' || myFleetRange.scuMax !== '') ? 1 : 0))
const fleetSheetCount = computed(() => myFleetAcquire.value.length + myFleetTypes.value.length
  + myFleetSizes.value.length + myFleetMfrs.value.length + myFleetRoles.value.length + fleetRangeCount.value)
const myFleetHasFilter = computed(() => !!(myFleetQuery.value.trim() || myFleetAcquire.value.length
  || myFleetTypes.value.length
  || myFleetSizes.value.length || myFleetMfrs.value.length || myFleetRoles.value.length || fleetRangeCount.value))
const fleetFilters = computed(() => ({
  q: myFleetQuery.value.trim(), types: myFleetTypes.value, sizes: myFleetSizes.value,
  manufacturers: myFleetMfrs.value, roles: myFleetRoles.value, acquire: myFleetAcquire.value,
  ...myFleetRange,
}))

function fleetOptions(pick, label, sortKey = o => o.label, base = []) {
  const seen = new Map(base.map(o => [o.value, o]))
  for (const row of fleet.value) {
    const v = row.vehicle
    if (!v) continue
    const value = pick(v)
    if (value === null || value === undefined || value === '' || seen.has(value)) continue
    seen.set(value, { value, label: label(v) })
  }
  return [...seen.values()].sort((a, b) => {
    const x = sortKey(a), y = sortKey(b)
    return typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), 'zh-Hant')
  })
}
const TYPE_ORDER = ['ship', 'ground', 'gravlev']
const myFleetTypeOptions = computed(() => fleetOptions(
  v => v.vehicle_type, v => vehicleTypeLabel(v.vehicle_type), o => TYPE_ORDER.indexOf(o.value),
  vehicleFacets.value.types))
const myFleetSizeOptions = computed(() => fleetOptions(
  v => (v.size_class === null || v.size_class === undefined ? '' : String(v.size_class)),
  v => vehicleSizeLabel(v.size_class), o => Number(o.value), vehicleSizeOptions.value))
const myFleetMfrOptions = computed(() => fleetOptions(
  v => v.manufacturer_code, v => manufacturerLabel(v.manufacturer_name, v.manufacturer_code),
  undefined, manufacturerOptions.value))
const myFleetRoleOptions = computed(() => fleetOptions(
  v => v.role, v => vehicleRoleLabel(v.role, v.role_zh), undefined, vehicleFacets.value.roles))

const filteredFleet = computed(() => {
  if (!myFleetHasFilter.value) return fleet.value
  const match = (selected, value) => !selected.length || selected.includes(value)
  const q = myFleetQuery.value.trim().toLowerCase()
  return fleet.value.filter(row => {
    const v = row.vehicle || {}
    if (q && ![row.name, v.name, v.name_zh, ...(row.unit_names || [])]
      .some(t => (t || '').toLowerCase().includes(q))) return false
    if (myFleetAcquire.value.length && !myFleetAcquire.value.some(a =>
      (a === 'buy' && v.uex_price?.buy_min) || (a === 'rent' && v.uex_price?.rent_min))) return false
    if (!vehicleInRanges(v, myFleetRange)) return false
    return match(myFleetTypes.value, v.vehicle_type)
      && match(myFleetSizes.value, v.size_class === null || v.size_class === undefined ? '' : String(v.size_class))
      && match(myFleetMfrs.value, v.manufacturer_code)
      && match(myFleetRoles.value, v.role)
  })
})
const myFleetSort = useTableSort(filteredFleet, { accessors: {
  name: r => r.vehicle?.name_zh || r.name,
  type: r => vehicleTypeLabel(r.vehicle?.vehicle_type) || null, size: r => r.vehicle?.size_class,
  manufacturer: r => manufacturerLabel(r.vehicle?.manufacturer_name, r.vehicle?.manufacturer_code) || null,
  role: r => vehicleRoleLabel(r.vehicle?.role, r.vehicle?.role_zh) || null,
  loadouts: r => r.loadout_links?.length || 0,
  cargo: r => r.vehicle?.cargo_capacity_scu || 0,
  usd: r => r.vehicle?.msrp || null,
  auec: r => r.vehicle?.uex_price?.buy_min || null,
  rent: r => r.vehicle?.uex_price?.rent_min || null,
  ratio: r => auecPerUsd(r.vehicle),
} })
const filteredFleetShipCount = computed(() =>
  filteredFleet.value.reduce((n, r) => n + (r.quantity || 0), 0))
// 載貨量合計（每款的貨艙 × 艘數）
const fleetScuOf = rows => rows.reduce((n, r) => n + (r.vehicle?.cargo_capacity_scu || 0) * (r.quantity || 0), 0)

function clearMyFleetFilters() {
  myFleetQuery.value = ''
  myFleetAcquire.value = []
  myFleetTypes.value = []
  myFleetSizes.value = []
  myFleetMfrs.value = []
  myFleetRoles.value = []
  Object.assign(myFleetRange, { priceMin: '', priceMax: '', scuMin: '', scuMax: '' })
}

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
  await setFleetQuantity(row, qty, input)
}

/** 改數量（－／＋ 按鈕或輸入框）；改少時多出來那幾艘的區別名稱／配件網址後端會一起截掉 */
async function setFleetQuantity(row, qty, input = null) {
  if (qty < 1 || qty > fleetMaxQuantity.value || qty === row.quantity) return
  savingFleetId.value = row._id
  const res = await playerAuth.playerFetch(`/player/fleet/${row._id}`, {
    method: 'PUT', body: JSON.stringify({ quantity: qty }),
  })
  savingFleetId.value = ''
  const data = res ? await res.json().catch(() => null) : null
  if (res?.ok && data?.success) {
    row.quantity = qty
    if (row.unit_names?.length > qty) row.unit_names = row.unit_names.slice(0, qty)   // 後端也一起截掉
    if (row.unit_loadouts?.length > qty) await loadFleet()   // 配件網址合併要重算，直接重抓
  } else {
    if (input) input.value = row.quantity
    showFleetError(data?.message || '更新數量失敗，請稍後再試')
  }
}

/** 好幾艘時刪掉其中一艘（後面的往前補） */
async function removeFleetUnit(row, n) {
  const key = `unit:${row._id}:${n}`
  if (deletingKey.value) return
  deletingKey.value = key
  savingFleetId.value = row._id
  const res = await playerAuth.playerFetch(`/player/fleet/${row._id}/units/${n}`, { method: 'DELETE' })
  savingFleetId.value = ''
  deletingKey.value = ''
  const data = res ? await res.json().catch(() => null) : null
  if (res?.ok && data?.success) {
    loadoutEditId.value = ''
    if (confirmDeleteKey.value === key) confirmDeleteKey.value = ''
    await loadFleet()
  } else {
    showFleetError(data?.message || '刪除失敗，請稍後再試')
  }
}

/** 展開後的船艦資訊格子 */
/** 貨艙容量（SCU），沒有貨艙顯示 — */
function scuLabel(scu) {
  return scu ? `${Math.round(scu).toLocaleString('en-US')} SCU` : '—'
}

function fleetInfoFields(v) {
  if (!v) return []
  const p = v.uex_price || {}
  return [
    { label: '類型', value: vehicleTypeLabel(v.vehicle_type) || '—' },
    { label: '尺寸', value: vehicleSizeLabel(v.size_class) || '—' },
    { label: '廠商', value: manufacturerLabel(v.manufacturer_name, v.manufacturer_code) || '—' },
    { label: '角色', value: vehicleRoleLabel(v.role, v.role_zh) || '—' },
    { label: '載貨', value: scuLabel(v.cargo_capacity_scu) },
    { label: '官網售價', value: fmtUsd(v.msrp) },
    { label: '遊戲內購買', value: p.buy_min ? `${fmtAuec(p.buy_min)} 起` : '—' },
    { label: 'aUEC／美金', value: fmtAuecPerUsd(auecPerUsd(v)) },
    { label: '租船', value: p.rent_min ? `${fmtAuec(p.rent_min)} 起` : '—' },
  ]
}

// ── 我的艦隊：列上直接顯示每一艘的配件網址；「編輯」跳出視窗設數量、每艘識別名稱與配件網址 ──
/** 列上要顯示的配件網址：每艘一組，好幾艘時按鈕前面標「識別名稱」或「第 n 艘」（舊資料只有 loadout_links 的算第 1 艘） */
function fleetUnitLoadouts(row) {
  const units = row.unit_loadouts?.length ? row.unit_loadouts : (row.loadout_links?.length ? [row.loadout_links] : [])
  return units.map((links, i) => ({
    n: i + 1, links: links || [],
    prefix: row.quantity > 1 ? (row.unit_names?.[i] || `第 ${i + 1} 艘`) : '',
  })).filter(u => u.links.length)
}
/** 查詢持有資訊：持有者每一艘的配件網址，按鈕前面標「玩家 · 識別名稱（沒填就第 n 艘）」；
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
const fleetEditId = ref('')
const fleetEditRow = computed(() => fleet.value.find(r => r._id === fleetEditId.value) || null)
const fleetEditOpen = computed({
  get: () => !!fleetEditRow.value,
  set: (v) => { if (!v) { fleetEditId.value = ''; loadoutEditId.value = '' } },
})
function openFleetEdit(row) {
  loadoutEditId.value = ''
  confirmDeleteKey.value = ''
  fleetEditId.value = row._id
}

// 「詳細」展開的列（船艦資訊）
const openMyFleet = reactive(new Set())
function toggleMyFleet(id) {
  if (openMyFleet.has(id)) openMyFleet.delete(id)
  else openMyFleet.add(id)
}

function saveUnitNameFromInput(row, n) {
  const input = document.getElementById(`unit-name-${row._id}-${n}`)
  if (input) saveUnitName(row, n - 1, { target: input })
}

async function saveUnitName(row, index, event) {
  const input = event.target
  const value = input.value.trim()
  const names = Array.from({ length: row.quantity }, (_, i) => row.unit_names?.[i] || '')
  if (names[index] === value) { input.value = value; return }
  names[index] = value
  savingFleetId.value = row._id
  const res = await playerAuth.playerFetch(`/player/fleet/${row._id}`, {
    method: 'PUT', body: JSON.stringify({ unit_names: names }),
  })
  savingFleetId.value = ''
  const data = res ? await res.json().catch(() => null) : null
  if (res?.ok && data?.success) {
    while (names.length && !names[names.length - 1]) names.pop()
    row.unit_names = names
  } else {
    input.value = row.unit_names?.[index] || ''
    showFleetError(data?.message || '儲存區別名稱失敗，請稍後再試')
  }
}

// ── 我的艦隊：配件網址（設在每一艘上，公開給其他玩家，見 src/models/fleet.py 的 unit_loadouts）──
// loadoutEditId＝「登記 id:第幾艘」
const loadoutEditId = ref('')
const loadoutDraft = ref([])

function toggleLoadoutEdit(row, n) {
  const key = `${row._id}:${n}`
  if (loadoutEditId.value === key) {
    loadoutEditId.value = ''
    return
  }
  loadoutEditId.value = key
  loadoutDraft.value = (row.unit_loadouts?.[n - 1] || []).map(l => ({ label: l.label || '', url: l.url, public: !l.private }))
  if (!loadoutDraft.value.length) loadoutDraft.value.push({ label: '', url: '', public: true })
}

async function saveLoadouts(row, n) {
  // 整列都空白的直接略過
  const links = loadoutDraft.value
    .map(l => ({ label: (l.label || '').trim(), url: (l.url || '').trim(), private: l.public === false }))
    .filter(l => l.url || l.label)
  savingFleetId.value = row._id
  const res = await playerAuth.playerFetch(`/player/fleet/${row._id}`, {
    method: 'PUT', body: JSON.stringify({ unit_loadout: { unit: n, links } }),
  })
  savingFleetId.value = ''
  const data = res ? await res.json().catch(() => null) : null
  if (res?.ok && data?.success) {
    loadoutEditId.value = ''
    await loadFleet()
  } else {
    showFleetError(data?.message || '儲存配件網址失敗，請稍後再試')
  }
}

async function onFleetImported() {
  await loadFleet()   // 登記船艦資料的「已登記」標記跟著 fleetVehicleUuids 更新
}

async function removeFleet(row) {
  const key = `fleet:${row._id}`
  if (deletingKey.value) return
  deletingKey.value = key
  const res = await playerAuth.playerFetch(`/player/fleet/${row._id}`, { method: 'DELETE' })
  const data = res ? await res.json().catch(() => null) : null
  deletingKey.value = ''
  if (res?.ok && data?.success) {
    if (confirmDeleteKey.value === key) confirmDeleteKey.value = ''
    await loadFleet()   // 登記船艦資料的「已登記」標記跟著解除
  } else {
    showFleetError(data?.message || '刪除失敗，請稍後再試')
  }
}

// ── 查詢 › 持有船艦：誰有哪款船 ──────────────────────────────
// 整合列表「詳細」展開的列：key 前綴 i|（物品）、b|（藍圖）、f|（船艦），各自重新查詢時清掉自己那一類
const openTree = reactive(new Set())
function toggleTree(key) {
  if (openTree.has(key)) openTree.delete(key)
  else openTree.add(key)
}
function clearTree(prefix) {
  for (const key of [...openTree]) if (key.startsWith(prefix)) openTree.delete(key)
}
//
// 船艦名稱／類型／尺寸／廠商／角色／玩家id／玩家暱稱，AND 語意，打
// /player/fleet/holders。跟「持有藍圖」一樣：都沒選定時列出全部人的艦隊；
// 船艦名稱打字就當關鍵字篩（q），選定了就用那一款（vehicle_id）。
const fleetHolders        = ref([])
const loadingFleetHolders = ref(false)
const vehicleFacets       = ref({ size_classes: [], types: [], manufacturers: [], roles: [] })
let vehicleFacetsLoaded = false

// 類型／尺寸／廠商／角色可多選（同一欄位內取聯集，欄位之間 AND）
const flSelectedTypes      = ref([])
const flSelectedSizes      = ref([])
const flSelectedMfrs       = ref([])
const flSelectedRoles      = ref([])
const vehicleSizeOptions = computed(() =>
  vehicleFacets.value.size_classes.map(n => ({ value: String(n), label: vehicleSizeLabel(n) })))
const manufacturerOptions = computed(() =>
  vehicleFacets.value.manufacturers.map(m => ({ value: m.value, label: manufacturerLabel(m.label, m.value) })))

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
  const res = await playerAuth.playerFetch(`/player/fleet/holders?${params.toString()}`)
  if (seq !== fleetHolderSeq) return   // 已經有更新的查詢在跑了
  loadingFleetHolders.value = false
  if (!res) return
  const data = await res.json().catch(() => null)
  fleetHolders.value = (res.ok && data?.success) ? (data.data || []) : []
}

watch([flSelectedVehicleId, flNameQuery, flSelectedTypes, flSelectedSizes, flSelectedMfrs, flSelectedRoles, flPlayerScid],
  loadFleetHolders)

async function searchVehicleNames(q) {
  const res = await playerAuth.playerFetch(`/item/vehicles?q=${encodeURIComponent(q)}&limit=20`)
  if (!res) return []
  const data = await res.json().catch(() => null)
  return (res.ok && data?.success) ? (data.data || []) : []
}



// 查詢 › 持有船艦：手機「篩選」面板裡的條件（名稱以外）
const flSheetCount = computed(() => flSelectedTypes.value.length + flSelectedSizes.value.length
  + flSelectedMfrs.value.length + flSelectedRoles.value.length)
function clearFlSheet() {
  flSelectedTypes.value = []
  flSelectedSizes.value = []
  flSelectedMfrs.value = []
  flSelectedRoles.value = []
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

// ── 查詢持有資訊：共同「名稱」欄的候選（物品／藍圖／船艦一起列，標出是哪一類）──
const WHO_KINDS = { item: '物品', bp: '藍圖', vehicle: '船艦' }
async function searchWhoNames(q) {
  const [items, bps, vehicles] = await Promise.all([searchItemNames(q), searchBlueprintNames(q), searchVehicleNames(q)])
  return [
    ...items.slice(0, 8).map(c => ({ kind: 'item', c })),
    ...bps.slice(0, 8).map(c => ({ kind: 'bp', c })),
    ...vehicles.slice(0, 8).map(c => ({ kind: 'vehicle', c })),
  ]
}
function whoNameLabel(x) {
  if (x.kind === 'item') return itemNameLabel(x.c)
  if (x.kind === 'bp') return blueprintNameLabel(x.c)
  return x.c.name_zh || x.c.name
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
    if (activeTab.value !== 'search') return
    const query = { ...route.query }
    SEARCH_URL_KEYS.forEach(k => delete query[k])
    router.replace({ query: { ...query, ...searchUrlQuery() } })
  }, 300)
}, { deep: true })

const linkCopied = ref(false)
async function copySearchLink() {
  try {
    await navigator.clipboard.writeText(window.location.href)
    linkCopied.value = true
    setTimeout(() => { linkCopied.value = false }, 2000)
  } catch { /* 瀏覽器不給複製就算了 */ }
}

// ── 工具列的展開區塊：同一個分頁一次只開一個，開了一個就收起其他的 ──
function exclusiveDrawers(refs) {
  refs.forEach((r, i) => watch(r, on => {
    if (on) refs.forEach((o, j) => { if (j !== i && o.value) o.value = false })
  }))
}
const warehouseDrawers = [historyOpen]
exclusiveDrawers(warehouseDrawers)
applySearchQuery(route.query)
exclusiveDrawers([fleetDataOpen, fleetImportOpen])
const warehouseDrawerOpen = computed(() => warehouseDrawers.some(r => r.value))

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
  if (legacyCommodities) syncUrl()   // 舊網址改寫成新的分頁
  if (openStockOnMount) stockWizardRef.value?.openNew()
})

onBeforeUnmount(() => {
  stickyObserver?.disconnect()
})
</script>

<style scoped>
.stock-paste-raw { font-size: 1rem; color: var(--sf-text-muted); }
/* 工具網站分組（列的樣式在 scifi-theme.css 的 .sf-tree-*） */
.holder-ship { margin-bottom: .4rem; }
.myfleet-info {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
  gap: .3rem 1rem; margin-bottom: .6rem;
}
.myfleet-info__item { display: flex; gap: .5rem; font-size: 1rem; min-width: 0; }
.myfleet-info__label { color: var(--sf-text-muted); white-space: nowrap; }
.myfleet-info__value { color: var(--sf-text-strong); font-weight: 600; }
.myfleet-qty { width: 9.5rem; }
.myfleet-detail { background: var(--sf-panel-2); }
/* 查詢持有資訊的「詳細」：持有者小表（底色跟我的艦隊的詳細一樣） */
.holder-detail { background: var(--sf-panel-2); }
/* 查詢持有資訊的整合列表：種類按鈕上的數量、種類膠囊 */
.who-count { margin-left: .35rem; opacity: .75; }
/* 手機卡片：不屬於那一類的欄位（空的）整格不顯示，免得只剩標籤 */
@media (max-width: 767.98px) {
  .scifi-page table.sf-stack.who-table tr:not(.sf-stack__detail) > td.who-na[data-label] { display: none !important; }
}
.holder-sub { --bs-table-bg: transparent; }
.holder-sub > :not(caption) > * > * { padding: .4rem .6rem; }
.holder-sub td[rowspan] { vertical-align: top; }

/* 後台手寫的艦船說明（換行照原樣顯示） */
.vehicle-note { white-space: pre-line; }

.tool-link { min-width: 0; }
/* 工具網站：分組標題、卡片 */
.tool-count { margin-left: .4rem; opacity: .7; }
.tool-group { margin-bottom: 1.5rem; }
.tool-group__head {
  display: flex; align-items: center; gap: .5rem; width: 100%; margin-bottom: .6rem; padding: .35rem 0;
  background: none; border: 0; border-bottom: 1px solid var(--sf-border);
  color: var(--sf-text-strong); font-size: 1.1rem; font-weight: 700; text-align: left;
}
.tool-card { transition: border-color .15s, transform .15s; }
.tool-card:hover { border-color: var(--sf-accent); transform: translateY(-1px); }
.tool-card__icon {
  flex: 0 0 2.4rem; height: 2.4rem; display: inline-flex; align-items: center; justify-content: center;
  border-radius: .5rem; font-weight: 700; font-size: 1.1rem;
  color: var(--sf-accent); background: rgba(var(--sf-accent-rgb), .14); border: 1px solid rgba(var(--sf-accent-rgb), .35);
}
.tool-card__title { font-weight: 700; font-size: 1.05rem; color: var(--sf-text-strong); overflow-wrap: anywhere; }
.tool-card__host { font-size: .9rem; color: var(--sf-text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tool-card__desc { font-size: .95rem; color: var(--sf-text); }
.tool-card__tag { cursor: pointer; font: inherit; font-size: .9rem; }
.min-w-0 { min-width: 0; }
/* 配件網址編輯列：窄螢幕折行，網址欄可以縮（不撐破 390px） */
.loadout-label-input { flex: 1 1 8rem; max-width: 10rem; min-width: 0; width: auto; }
.loadout-url-input { flex: 1 1 12rem; min-width: 0; width: auto; }
/* 庫存紀錄在手機卡片裡：物品名稱當標題排最前面 */
.history-stack :deep(td.sf-stack__title) { order: -1; }
.my-bp-filter { min-width: 14rem; }
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
.nav-tabs .nav-link { cursor: pointer; }
.fleet-range-currency { flex: 0 0 6.5rem; }
.tab-prefs { display: grid; grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr)); gap: .5rem 1rem; }
</style>
