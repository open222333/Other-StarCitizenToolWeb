# 🚀 Star Citizen Tools

## 玩家、藍圖與戰利品管理網站

> 用途：建立一個專門服務 Star Citizen 玩家／團隊的資料管理網站，用來記錄玩家 ID、藍圖、戰利品、武器、裝備以及取得來源。

---

## 目錄

- [1. 專案目標與定位](#1-專案目標與定位)
- [2. 資訊架構（導覽）](#2-資訊架構導覽)
- [3. 首頁 Dashboard](#3-首頁-dashboard)
- [4. 玩家管理](#4-玩家管理)
- [5. 藍圖 Blueprint 管理](#5-藍圖-blueprint-管理)
- [6. 戰利品 Loot 管理](#6-戰利品-loot-管理)
- [7. 任務資料](#7-任務資料)
- [8. 地點資料](#8-地點資料)
- [9. 收藏庫與重複物品](#9-收藏庫與重複物品)
- [10. 標籤 Tags](#10-標籤-tags)
- [11. 資料可信度與來源](#11-資料可信度與來源)
- [12. 搜尋與篩選](#12-搜尋與篩選)
- [13. 物品圖片與詳細頁](#13-物品圖片與詳細頁)
- [14. 快速操作](#14-快速操作)
- [15. 資料庫設計](#15-資料庫設計)
- [16. UI／UX 設計](#16-uiux-設計)
- [17. 前端技術架構（Vue 3）](#17-前端技術架構vue-3)
- [18. 權限與資料安全](#18-權限與資料安全)
- [19. 擴充規劃](#19-擴充規劃)
- [20. 開發階段（MVP）](#20-開發階段mvp)
- [21. 核心資料關聯範例](#21-核心資料關聯範例)
- [22. 開發原則](#22-開發原則)

---

## 1. 專案目標與定位

建立一個簡潔、快速、適合桌面與手機使用的 Star Citizen 玩家工具網站。這不是單純的 Star Citizen Wiki，而是：

> **「Star Citizen 玩家個人／團隊收藏與戰利品資料庫」**

核心價值鏈：

```text
我有誰？
↓
我有哪些 Blueprint？
↓
我有哪些 Loot？
↓
這個 Loot 誰拿到？
↓
在哪裡拿到？
↓
怎麼拿到？
↓
現在誰持有？
↓
還缺哪些？
```

網站主要功能：

1. 玩家 ID 管理
2. 藍圖 Blueprint 管理
3. 戰利品 Loot 管理
4. 武器與裝備收藏管理
5. 戰利品取得紀錄
6. 玩家與物品關聯
7. 搜尋與篩選
8. 統計資料
9. 未來支援 Discord／公會使用

網站介面以「Star Citizen / 科幻軍事終端」風格為主。

---

## 2. 資訊架構（導覽）

網站左側或上方建立主要導覽：

- 🏠 首頁
- 👤 玩家
- 📘 藍圖
- 🎒 戰利品
- 🔫 武器
- 🛡️ 裝備
- 📦 收藏庫
- 📊 統計
- ⚙️ 設定

---

## 3. 首頁 Dashboard

首頁顯示整體資料摘要。

### 統計卡片

- 玩家數量
- 藍圖數量
- 戰利品數量
- 武器數量
- 裝備數量
- 最近取得物品
- 最近新增玩家

範例版面：

```text
┌─────────────────────────────────────┐
│ STAR CITIZEN TOOLS                  │
│                                     │
│ 👤 玩家       24                     │
│ 📘 藍圖       18                     │
│ 🎒 戰利品     137                    │
│ 🔫 武器       42                     │
│ 🛡️ 裝備       65                     │
└─────────────────────────────────────┘
```

### 快速新增

首頁提供以下捷徑以減少操作步驟：

```text
+ 新增玩家
+ 新增 Loot
+ 新增 Blueprint
+ 新增任務
```

---

## 4. 玩家管理

### 4.1 玩家資料欄位

```text
玩家名稱
Star Citizen ID
暱稱
Discord ID
玩家備註
加入日期
最後更新日期
```

> Star Citizen ID 是主要識別資料，必須與 Discord 名稱／ID 分開儲存；Discord ID 不可直接取代 Star Citizen ID。

範例：

```text
玩家名稱：ChengEn
Star Citizen ID：XXXXXXXX
Discord：@player
備註：主要負責戰鬥任務
```

### 4.2 玩家詳細頁

點擊玩家後進入玩家詳細頁，顯示：

**基本資料**

- 玩家名稱
- Star Citizen ID
- Discord
- 備註

**玩家收藏統計**

- 📘 藍圖
- 🎒 戰利品
- 🔫 武器
- 🛡️ 裝備

**玩家取得紀錄**（時間軸）

```text
2026/08/18
Onyx Facility
Yormandi Eyes
取得者：ChengEn

------------------

2026/08/17
Onyx Facility
XDL Rangefinder
取得者：ChengEn
```

### 4.3 玩家自助註冊

提供一個不需要登入的公開頁面（`/register`），讓玩家自己登記，不用等管理員手動新增。只收兩個欄位：

```text
暱稱（nickname）
遊戲ID（star_citizen_id）
```

`star_citizen_id` 必須唯一，後端需在建立前檢查重複，重複時回傳衝突錯誤（建議 HTTP 409），前端顯示「這個遊戲ID已經被註冊過了」。

其餘玩家欄位（Discord 名稱／ID、備註）不開放自助填寫，留給管理員之後在後台補齊（見[第 4.1 節](#41-玩家資料欄位)的 `PlayerFormModal`），避免公開表單被亂填。

---

## 5. 藍圖 Blueprint 管理

### 5.1 藍圖資料欄位

```text
Blueprint 名稱
英文名稱
類型
所屬物品
取得方式
取得地點
取得任務
取得玩家
取得日期
是否已解鎖
備註
```

### 5.2 Blueprint 狀態

- 🔒 未取得
- 📘 已取得
- ✅ 已解鎖
- ❓ 未確認
- ⚠️ 已過時

### 5.3 Blueprint 取得方式分類

- 任務
- NPC 掉落
- 寶箱
- 探索
- 活動
- 商店
- 聲望獎勵
- 特殊事件
- 玩家取得
- 未知

---

## 6. 戰利品 Loot 管理

戰利品是網站的核心功能之一。

### 6.1 Loot 資料欄位

```text
物品名稱
英文名稱
物品類型
稀有度
取得地點
取得方式
取得任務
取得玩家
取得日期
數量
目前持有人
物品狀態
備註
```

### 6.2 Loot 類型

**武器**：手槍、步槍、SMG、Shotgun、Sniper、重武器、近戰武器

**裝備**：頭盔、防彈衣、背包、防護服、醫療裝備、工具

**特殊物品**：任務物品、稀有物品、特殊裝備、掃描器、Rangefinder、特殊道具

**其他**：彈藥、消耗品、材料、未分類

### 6.3 Loot 稀有度

```text
Common
Uncommon
Rare
Very Rare
Epic
Legendary
Unknown
```

網站可以使用不同視覺標示稀有度。

### 6.4 Loot 狀態

- 📦 庫存中
- 🎒 玩家持有
- 🔫 已裝備
- 🤝 已轉交
- 💰 已出售
- 💀 已遺失
- 🗑️ 已消耗
- ❓ 未確認

### 6.5 取得紀錄

每個物品必須能記錄來源，範例：

```text
物品：Yormandi Eyes
取得地點：Onyx Facility
取得方式：Boss 掉落
取得玩家：ChengEn
取得日期：2026/08/18
目前持有人：ChengEn
狀態：庫存中
```

### 6.6 團隊戰利品與分配

如果多人一起進行任務，可以記錄整團的取得與分配結果：

```text
任務：Onyx Facility
日期：2026/08/18

參與玩家：
ChengEn
Player02
Player03
Player04

戰利品：
Yormandi Eyes → ChengEn
XDL Rangefinder → Player02
特殊武器 → Player03
其他 Loot → 團隊倉庫
```

每一筆 Loot 的分配資訊包含：

```text
取得者
分配給
目前持有人
分配日期
備註
```

分配方式支援：

- 個人取得
- 指定玩家
- 團隊倉庫
- 待分配
- 未確認

---

## 7. 任務資料

Loot 與 Blueprint 皆可關聯任務。

任務欄位：

```text
任務名稱
任務類型
任務提供者
地點
聲望
任務報酬
相關 Loot
```

範例：

```text
任務：Jorrit Dossier

Loot：
Yormandi Eyes
實驗樣本
其他特殊物品
```

---

## 8. 地點資料

建立 Star Citizen 地點資料，支援星系 → 行星 → 地點 → 設施 → 房間的階層關聯。

```text
Stanton
├── ArcCorp
├── Hurston
├── MicroTech
├── Crusader
└── Onyx Facility
```

Loot 可關聯到任一層級：

```text
Stanton
└── Onyx Facility
    └── Site B
        └── Boss Room
```

---

## 9. 收藏庫與重複物品

### 9.1 我的收藏庫

可以查看：

```text
📘 Blueprint
🎒 Loot
🔫 Weapons
🛡️ Equipment
```

並提供統計：

```text
總數
已收集
未收集
重複物品
已轉交
已遺失
```

### 9.2 重複物品

相同物品以數量記錄，而不是建立多筆完全相同的資料：

```text
P8-AR
數量：5

持有人：
ChengEn × 2
Player02 × 1
團隊倉庫 × 2
```

---

## 10. 標籤 Tags

所有物品可以加入標籤，支援多標籤搜尋。

範例：

```text
#稀有
#Boss掉落
#Onyx
#JorritDossier
#特殊裝備
#不可購買
#任務物品
```

---

## 11. 資料可信度與來源

### 11.1 未確認資料標記

對尚未確認的資料加入狀態標記：

- ❓ 未確認
- ⚠️ 可能過時
- ✅ 已確認

範例：

```text
取得方式：❓ 未確認
來源：玩家回報
最後確認：2026/08/18
```

這個功能非常重要，避免玩家把過時資訊當成官方資料。

### 11.2 資料來源類型

每筆資料可以記錄來源類型：

```text
官方
玩家測試
Discord
Reddit
Spectrum
Wiki
未知
```

並提供：

```text
來源 URL
最後確認日期
資料備註
```

---

## 12. 搜尋與篩選

### 12.1 全域搜尋

網站必須提供全域搜尋，涵蓋：

```text
玩家名稱
Star Citizen ID
Blueprint
武器
裝備
Loot
地點
任務
取得方式
```

範例：輸入 `Yormandi` 可以找到

```text
Yormandi Eyes
類型：特殊裝備
來源：Onyx Facility
取得玩家：ChengEn
日期：2026/08/18
```

### 12.2 篩選

Loot 頁面提供篩選：

```text
類型
稀有度
取得地點
取得方式
取得玩家
目前持有人
狀態
日期
```

範例組合：

```text
地點：Onyx Facility
+
類型：特殊物品
+
狀態：庫存中
```

只顯示符合條件的物品。

---

## 13. 物品圖片與詳細頁

每個物品可以加入圖片：

```text
圖片 URL
圖片
縮圖
```

如果未提供圖片，使用預設 Star Citizen 風格圖示。

物品詳細頁範例：

```text
┌─────────────────────────────────┐
│ YORMANDI EYES                   │
│                                 │
│ [ ITEM IMAGE ]                  │
│                                 │
│ 類型：特殊物品                  │
│ 稀有度：Legendary               │
│                                 │
│ 取得地點：Onyx Facility         │
│ 取得方式：Boss 掉落             │
│                                 │
│ 取得者：ChengEn                 │
│ 日期：2026/08/18                │
│                                 │
│ 狀態：庫存中                    │
└─────────────────────────────────┘
```

---

## 14. 快速操作

### 14.1 新增 Loot 表單流程

```text
物品名稱
↓
類型
↓
取得地點
↓
取得方式
↓
取得玩家
↓
目前持有人
↓
狀態
↓
備註
↓
儲存
```

---

## 15. 資料庫設計

建議至少建立以下資料表，欄位規劃如下（各表皆應包含建立／修改時間，詳見[開發原則](#22-開發原則)）：

### 15.1 players

```text
id
player_name
star_citizen_id     ← 唯一，玩家自助註冊（第 4.3 節）與後台新增共用
nickname
discord_name
discord_id
notes
created_at
updated_at
```

> `nickname` 欄位原本在第 4.1 節就有列出，但先前整理資料表時漏加，這裡補上並跟前端表單同步。

### 15.2 items

```text
id
name
name_en
category
subcategory
rarity
image_url
description
status
created_at
updated_at
```

### 15.3 blueprints

```text
id
item_id
acquisition_method
acquisition_location
mission_id
player_id
acquired_at
unlock_status
source_id
notes
```

### 15.4 loot_records

```text
id
item_id
quantity
location_id
mission_id
obtained_by
current_owner
acquisition_method
obtained_at
status
notes
```

### 15.5 locations

```text
id
system
planet
location_name
facility
room
description
```

### 15.6 missions

```text
id
name
type
provider
location_id
reputation
reward
description
```

### 15.7 其餘資料表

以下資料表對應本文件對應章節的功能，欄位可依實作細節調整：

- `tags`：標籤主檔（見[第 10 節](#10-標籤-tags)）
- `item_tags`：物品與標籤的多對多關聯
- `loot_distribution`：戰利品分配紀錄（見[第 6.6 節](#66-團隊戰利品與分配)）
- `sources`：資料來源紀錄（見[第 11.2 節](#112-資料來源類型)）

---

## 16. UI／UX 設計

### 16.1 整體風格

```text
Star Citizen
Military / Industrial
Dark UI
Sci-Fi Terminal
```

介面不要過度花俏，重點是：

- 快速搜尋
- 快速新增
- 快速查看
- 清楚分類
- 適合大量資料

### 16.2 顏色概念

```text
背景：深灰 / 黑色
主要文字：白色
次要文字：灰色
資訊：藍色
成功：綠色
警告：黃色
錯誤：紅色
```

不要大量使用霓虹效果。

### 16.3 Mobile

手機版必須支援，手機畫面優先顯示：

```text
搜尋
玩家
Loot
Blueprint
新增
```

卡片式顯示物品。

---

## 17. 前端技術架構（Vue 3）

沿用專案現有 `frontend/` 的技術棧與慣例（見 `frontend/package.json`、`frontend/src/`），新功能不另起爐灶。

### 17.1 技術棧

```text
Vue 3（<script setup> 風格）
Vite
Pinia            — 狀態管理
vue-router 4     — 路由（history 模式）
Bootstrap 5 + bootstrap-icons — UI 元件與圖示
原生 fetch 封裝  — 不引入 axios，比照現有 src/api/index.js 的 apiFetch()
```

> ⚠️ 待確認：目前 `frontend/` 是掛在 `/admin/` base path 下的後台管理介面（使用者／模板／操作紀錄），跟這份規格描述的「玩家／藍圖／戰利品」主功能面向的是不同受眾。建議二擇一並在動工前定案：
> 1. 在同一個 Vue 專案內，於根路徑（`/`）新增這組頁面，`/admin/` 維持現有後台不動；或
> 2. 另開一個獨立的 Vue 專案／子目錄（例如 `frontend-app/`），與 `frontend/`（後台）分開建置、分開部署。

### 17.2 專案結構（比照現有慣例）

```text
frontend/src/
├── api/                 # 依資料網域拆分，比照 userApi / logApi 的寫法
│   ├── index.js          # apiFetch() 共用封裝（JWT + 401 自動 refresh）
│   ├── player.js          # playerApi
│   ├── item.js             # itemApi（含 weapon／equipment 共用）
│   ├── blueprint.js        # blueprintApi
│   ├── loot.js              # lootApi + lootDistributionApi
│   ├── mission.js           # missionApi
│   ├── location.js          # locationApi
│   └── tag.js                # tagApi
├── stores/
│   ├── auth.js            # 既有
│   ├── theme.js            # 既有
│   ├── player.js            # 玩家清單／目前選取玩家
│   ├── loot.js               # Loot 清單、篩選條件、分頁狀態
│   └── ui.js                  # 全域搜尋關鍵字、行動版側欄開關
├── layouts/
│   └── DashboardLayout.vue   # 既有，導覽項目擴充見 17.3
├── views/
│   ├── DashboardView.vue      # 首頁統計卡片
│   ├── PlayerListView.vue
│   ├── PlayerDetailView.vue
│   ├── BlueprintListView.vue
│   ├── LootListView.vue
│   ├── LootDetailView.vue
│   ├── CollectionView.vue      # 收藏庫
│   └── StatsView.vue
└── components/
    ├── ConfirmModal.vue        # 既有，刪除／soft delete 確認共用
    ├── ItemCard.vue             # 戰利品／藍圖卡片（含稀有度視覺標示）
    ├── PlayerFormModal.vue
    ├── LootFormModal.vue
    ├── FilterBar.vue             # 12.2 篩選條件列
    ├── SearchBox.vue              # 12.1 全域搜尋
    ├── StatusBadge.vue             # Loot／Blueprint 狀態徽章（含 ❓/⚠️/✅）
    └── RarityTag.vue                # 稀有度標籤
```

### 17.3 路由規劃

延續 `router/index.js` 現有的 `meta.requiresAuth` / `meta.requiresAdmin` guard 模式：

```text
/                     → DashboardView（首頁 Dashboard）
/players              → PlayerListView
/players/:id          → PlayerDetailView
/blueprints           → BlueprintListView
/loot                 → LootListView（含篩選、支援 query string 深連結）
/loot/:id             → LootDetailView
/collection           → CollectionView
/stats                → StatsView
```

第一階段（P0，見[第 20 節](#20-開發階段mvp)）先做到 `/players`、`/players/:id`、`/loot`、`/loot/:id`、`/blueprints`；`/collection`、`/stats` 排入 P1。

若採 17.1 的方案一（同專案根路徑新增），需注意 `router/index.js` 目前用 `createWebHistory('/admin/')`，新頁面須改成不綁 base path 的根路由設定，或拆成兩個 router 實例分掛在不同 base path。

### 17.4 Pinia Store 與 API 對應

比照 `stores/auth.js` 的寫法，每個資料網域一個 store，內部呼叫對應的 `xxxApi`：

```text
store              呼叫的 API 模組       對應資料表（第 15 節）
──────────────────────────────────────────────────────
usePlayerStore      playerApi            players
useItemStore        itemApi              items
useBlueprintStore   blueprintApi         blueprints
useLootStore        lootApi              loot_records, loot_distribution
useMissionStore     missionApi           missions
useLocationStore    locationApi          locations
useTagStore         tagApi               tags, item_tags
```

`lootApi` 的方法命名比照現有 `userApi` 慣例（`list` / `create` / `update` / `remove`），另外加上：

```text
lootApi.distribute(id, data)   // 6.6 戰利品分配
lootApi.search(query)          // 12.1 全域搜尋
lootApi.filter(params)         // 12.2 篩選
```

### 17.5 元件拆分原則

- 列表頁一律採「列表 + 篩選列（FilterBar）+ 新增/編輯 Modal」的組合，Modal 沿用 `UserModal.vue` / `TemplateModal.vue` 的結構（表單 + 驗證 + 呼叫對應 `xxxApi`）。
- 刪除一律走 `ConfirmModal.vue`，且後端對應 17.1 提到的 Soft Delete（[第 18.2 節](#182-資料刪除)）。
- 稀有度（`RarityTag.vue`）與狀態（`StatusBadge.vue`）獨立成共用元件，因為 Loot、Blueprint、收藏庫、詳細頁都會重複用到（對應第 5.2、6.4、11.1 節的標記）。

### 17.6 響應式（RWD）

沿用 Bootstrap 5 的 grid／breakpoint，行動版比照[第 16.3 節](#163-mobile)只優先顯示搜尋、玩家、Loot、Blueprint、新增五項；`DashboardLayout.vue` 的側邊導覽在行動版收合為抽屜（off-canvas），複用 Bootstrap 內建 Offcanvas 元件即可，不需額外套件。

---

## 18. 權限與資料安全

### 18.1 權限模式

第一階段可以先使用單一管理者模式。未來可以增加角色：

**Admin**：新增、修改、刪除、管理玩家、管理資料

**Member**：查看、新增 Loot、新增取得紀錄

**Viewer**：只能查看

### 18.2 資料刪除

重要資料不要直接永久刪除，建議使用 Soft Delete（例如加上 `deleted_at` 欄位），避免誤刪玩家、Blueprint 或 Loot。

---

## 19. 擴充規劃

### 19.1 Discord 整合預留

網站設計時預留 Discord 整合，未來可以做到：

```text
Discord 玩家
↓
Star Citizen ID
↓
網站玩家資料
↓
Loot / Blueprint
```

以及斜線指令：

```text
/loot add
/loot search
/player
/blueprint
```

### 19.2 資料匯入／匯出

未來支援：

```text
JSON
CSV
Excel
```

可以備份整個資料庫。

### 19.3 其他未來擴充

網站架構必須預留以下功能：

```text
Discord Bot
玩家登入
團隊／公會
共享倉庫
戰利品分配
任務資料庫
船艦資料庫
武器資料庫
裝備資料庫
商店價格
聲望追蹤
任務追蹤
地圖
位置標記
活動管理
```

---

## 20. 開發階段（MVP）

第一版不要一次做太大，優先完成：

### P0

- 玩家管理
- Star Citizen ID
- Loot 管理
- Blueprint 管理
- 搜尋
- 篩選
- Loot 取得者
- Loot 持有人
- 取得地點
- 狀態

### P1

- 任務
- 地點
- 標籤
- 圖片
- 統計
- CSV 匯出

### P2

- Discord
- 登入
- 團隊
- 權限
- Discord Bot

---

## 21. 核心資料關聯範例

核心關聯：

```text
玩家
 ↓
取得 Loot
 ↓
Loot
 ↓
取得地點
 ↓
任務
 ↓
Blueprint
```

範例：

```text
ChengEn
   │
   ├── 取得
   │
   ▼
Yormandi Eyes
   │
   ├── Onyx Facility
   │
   ├── Boss 掉落
   │
   └── Jorrit Dossier
```

---

## 22. 開發原則

1. 不要把 Star Citizen 官方資料硬編碼在前端。
2. 所有物品都應該可以新增、修改。
3. Loot 與 Blueprint 必須可以記錄來源。
4. 玩家 ID 與 Discord ID 分開。
5. 所有資料都要有建立／修改時間。
6. 允許標記「未確認」與「已過時」。
7. 搜尋速度優先。
8. 手機與桌面都要能使用。
9. 資料庫結構必須方便未來增加船艦、任務、武器。
10. 第一階段以實用性為主，不要過度設計。
