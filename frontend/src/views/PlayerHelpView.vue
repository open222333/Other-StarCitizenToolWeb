<!--
  玩家頁使用說明（公開頁面，/player/help）：每個分頁能做什麼、怎麼用，附畫面截圖。玩家登入頁有連結進來。
  只說明玩家頁面（不含後台）。分頁有增減時，這裡跟著 utils/playerTabs.js 一起改。
  截圖放在 public/help/（webp，寬 1120），畫面改版時重拍對應的那張；截圖裡的資料都是示範資料。
-->
<template>
  <div class="scifi-page help-page">
    <div class="help-wrap">
      <header class="help-head">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <h1 class="help-title"><i class="bi bi-book me-2" style="color: var(--sf-accent)"></i>玩家頁使用說明</h1>
          <RouterLink :to="playerAuth.isLoggedIn ? PLAYER_HOME : PLAYER_LOGIN_PATH" class="btn btn-sm btn-primary ms-auto">
            <i class="bi me-1" :class="playerAuth.isLoggedIn ? 'bi-house' : 'bi-box-arrow-in-right'"></i>
            {{ playerAuth.isLoggedIn ? '回到玩家頁' : '前往登入' }}
          </RouterLink>
        </div>
        <nav class="help-toc" aria-label="目錄">
          <a v-for="s in sections" :key="s.id" :href="`#${s.id}`" class="help-toc__item" @click.prevent="jump(s.id)">
            <i :class="s.icon" class="me-1"></i>{{ s.title }}</a>
        </nav>
      </header>

      <section v-for="s in sections" :id="s.id" :key="s.id" class="card scifi-card help-card">
        <div class="card-body">
          <h2 class="help-h2"><i :class="s.icon" class="me-2"></i>{{ s.title }}</h2>
          <p v-if="s.intro" class="help-intro">{{ s.intro }}</p>
          <div v-for="(b, i) in s.blocks" :key="i" class="help-block">
            <h3 v-if="b.title" class="help-h3">{{ b.title }}</h3>
            <ul class="help-list">
              <li v-for="(t, j) in b.items" :key="j">{{ t }}</li>
            </ul>
            <figure v-for="f in b.figs || []" :key="f.src" class="help-fig" :style="f.w ? { maxWidth: f.w } : null">
              <a :href="imgUrl(f.src)" target="_blank" rel="noopener">
                <img :src="imgUrl(f.src)" :alt="f.alt" loading="lazy" decoding="async">
              </a>
              <figcaption>{{ f.alt }}</figcaption>
            </figure>
          </div>
        </div>
      </section>

      <div class="text-center my-4">
        <button type="button" class="btn btn-sm btn-info" @click="jump('top')"><i class="bi bi-arrow-up me-1"></i>回到最上面</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { usePlayerAuthStore } from '@/stores/playerAuth'
import { PLAYER_HOME, PLAYER_LOGIN_PATH } from '@/router'

const playerAuth = usePlayerAuthStore()
// 截圖在 public/help/（玩家站與後台的 base 不同，用 BASE_URL 組）
const imgUrl = name => `${import.meta.env.BASE_URL}help/${name}.webp`

function jump(id) {
  if (id === 'top') {
    window.scrollTo({ top: 0, behavior: 'smooth' })
    return
  }
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

const sections = [
  {
    id: 'start', title: '開始使用', icon: 'bi bi-rocket-takeoff',
    blocks: [
      { figs: [{ src: 'login', alt: '登入頁', w: '22rem' }, { src: 'mobile', alt: '手機：底部分頁列與「更多」', w: '34rem' }], items: [
        '用遊戲ID（Star Citizen ID）註冊帳號，之後用遊戲ID＋密碼登入；勾「記住我」可以 30 天不用重新登入。',
        '上方是分頁列，放不下時可以左右滑；手機上分頁列移到畫面底部，常用的四個直接放，其餘在「更多」裡。',
        '右上角「配色」可以換強調色與背景（深色、淺色），只存在這台瀏覽器。',
        '「個人資料 › 顯示的分頁」可以把用不到的分頁藏起來。',
        '多數表單（航線、合約、貨艙、酬勞…）會記在這台瀏覽器，下次打開還在；換電腦或清除瀏覽器資料就不會留著。',
      ] },
      { title: '定居點', figs: [{ src: 'home', alt: '名字右邊的定居點按鈕與視窗' }], items: [
        '最上方名字右邊的按鈕顯示目前的定居點，點一下跳出視窗，可以設定或清除（從可選的居住地挑一個）。',
        '同一個視窗下方是「全部物品轉移到定居點」：列出會移動幾筆、幾件，按「確定轉移」才送出。',
      ] },
    ],
  },
  {
    id: 'warehouse', title: '倉庫', icon: 'bi bi-box-seam',
    intro: '記錄自己的物品放在哪裡、有多少。上方的按鈕可以展開新增／異動、庫存紀錄，搜尋卡的條件同時套用到列表。',
    blocks: [
      { title: '物品庫存', figs: [{ src: 'warehouse', alt: '物品庫存' }], items: [
        '列出你登記的物品、地點、數量；可以依物品名稱、類型、地點篩選與排序。',
      ] },
      { title: '新增／異動', figs: [{ src: 'stock_step1', alt: '第 1 步：地點' }, { src: 'warehouse_pick', alt: '第 2 步：勾選物品' }, { src: 'warehouse_paste', alt: '貼上清單比對物品' }, { src: 'warehouse_stock', alt: '第 3 步：設定數量' }], items: [
        '按「新增／異動」跳出視窗，分三步：地點 → 物品 → 數量；上方的步驟可以直接點回去改。',
        '1. 地點：用星系、行星縮小範圍，選或輸入地點。會自動帶上次送出用的地點（第一次用定居點），已經有地點時直接從第 2 步開始。',
        '2. 物品：搜尋條件跟倉庫一樣（名稱、類型、拆解材料）。物品類型預設只開量子引擎、護盾、雷達、艦炮、冷卻器、發電機六種飛船組件，需要其他類型（例如飛彈、頭盔）就在「物品類型」自己加勾，會記在這台瀏覽器；全部取消就回到預設。清單逐個勾或整頁全選，換頁、改條件都不會清掉已選的，數量不限。',
        '「最近登記」（只列開啟的類型）點一下就勾選；「貼上清單」只比對開啟的類型，每行一個物品，數量寫在前或後都可以（例如 Atlas x2、Bulwark 3、2 Hunter），比對後「加入已選」。',
        '3. 數量：每一項選「＋ 增加」或「－ 減少」、數量（預設 1）、備註，也可以一次全部改成增加或減少，最後「全部送出」。失敗的會留在清單上顯示原因；全部成功就回到第 2 步，同一個地點繼續登記。',
        '庫存列表每一列的「異動」：直接帶好地點和物品（預設減少），停在第 3 步。',
        'Discord 機器人也能登記：/add 入庫、/remove 出庫、/move 換位置。',
      ] },
      { title: '庫存紀錄', figs: [{ src: 'warehouse_history', alt: '庫存紀錄' }], items: [
        '每次增加、減少的歷史紀錄（時間、物品、地點、數量、備註）。',
      ] },
    ],
  },
  {
    id: 'blueprints', title: '藍圖', icon: 'bi bi-diagram-3',
    intro: '你自己的藍圖名冊（可以新增、刪除）。',
    blocks: [
      { title: '我的藍圖', figs: [{ src: 'blueprints', alt: '展開材料' }, { src: 'blueprints_quality', alt: '品質試算' }], items: [
        '列出已登記的藍圖：名稱、類型、製作時間、材料；可以篩選與排序。',
        '每一列可以展開「材料」：輸入要做幾個，算出每種材料總共需要多少。',
        '也可以展開「品質試算」：調整每個部位放的材料品質（0–1000），即時看成品各屬性的倍率。',
      ] },
      { title: '登記藍圖資料', items: [
        '按「登記藍圖資料」跳出視窗，搜尋藍圖資料庫（中英文都可以），把有的藍圖登記進名冊。',
        '可以「只顯示未登記」、「只看需任務解鎖」的藍圖。',
      ] },
    ],
  },
  {
    id: 'missions', title: '任務', icon: 'bi bi-flag',
    blocks: [
      { title: '任務資料庫', figs: [{ src: 'missions', alt: '展開任務看獎勵藍圖' }], items: [
        '依名稱、類型、星系、勢力、合法性篩選任務；列出報酬、聲望異動、冷卻時間。',
        '藍圖欄顯示這個任務會給的藍圖中，你已登記幾張／共幾張；點一列看說明、條件、每個獎勵池的藍圖與掉落機率。',
      ] },
      { title: '勢力聲望', items: [
        '按「勢力聲望」跳出視窗，選一個勢力，列出它的聲望階級與門檻分數，以及每個階級才能接的任務。',
      ] },
    ],
  },
  {
    id: 'fleet', title: '艦隊', icon: 'bi bi-rocket-takeoff',
    blocks: [
      { title: '我的艦隊', figs: [{ src: 'fleet', alt: '我的艦隊' }], items: [
        '列出你登記的船／載具：類型、尺寸、廠商、角色、貨物量、美金與遊戲幣價格、租用價格。',
        '配件網址（例如 erkul 的配裝連結）直接顯示在船名下面，按了開新頁；同款有好幾艘時，按鈕前面會標是哪一艘。',
        '按「編輯」跳出視窗，設定數量（同款好幾艘）、每一艘的識別名稱與配件網址，也可以只刪其中一艘；「詳細」看船艦資訊。',
        '「航線」與「貨艙網格」會把機庫裡的船排在最前面。',
      ] },
      { title: '登記船艦資料', items: [
        '按「登記船艦資料」跳出視窗，瀏覽艦船資料庫，依名稱、類型、尺寸、廠商、價格、貨物量、取得方式篩選，把船加進艦隊。',
      ] },
      { title: 'JSON 匯入', items: [
        '按工具列的「JSON 匯入」開跳出視窗，選用瀏覽器擴充功能 HangarXPLOR 在 RSI 機庫頁匯出的 JSON，一次匯入整個機庫。',
      ] },
    ],
  },
  {
    id: 'mining', title: '礦物', icon: 'bi bi-gem',
    blocks: [
      { figs: [{ src: 'mining', alt: '回波比對與礦物訊號參考' }], items: [
        '回波比對：輸入掃描器上看到的訊號值，反查可能是哪種礦床、一叢幾顆。',
        '礦物訊號參考：每種礦床可能含哪些礦物、比例與出現機率。',
        '礦物卡片附售價（精煉品／原礦）與精煉資料（各精煉站的產量加成、容量、精煉方式）。',
      ] },
    ],
  },
  {
    id: 'route', title: '航線', icon: 'bi bi-signpost-split',
    intro: '量子航行路線規劃，分「航線規劃」和「合約分配」兩個子分頁。',
    blocks: [
      { title: '航線規劃', figs: [{ src: 'route_form', alt: '選船、起始油量、起點與途經站點' }, { src: 'route_fill', alt: '按「依星系填入」展開，選星系填入站點' }, { src: 'route_result', alt: '航段表' }, { src: 'route_map', alt: '3D 星圖' }], items: [
        '選船（可以篩選貨艙大小、只看我的機庫）與量子引擎；選好船會顯示速度、油耗、油箱，以及 8／16／32 SCU 貨櫃最多裝幾個。',
        '設定起始油量（百分比或油量，空白＝滿油）、起點、途經站點、終點（最後一站／回到起點／指定地點），可以自動排序。',
        '「途經站點」按「依星系填入」可以選星系一次填入站點（填入後收起）：勾太空站、主城、地面站（地面站要先選行星），已在清單上的不重複加。',
        '每個站點前面的開關決定要不要加入這次規劃（最多 40 個），關掉的保留在清單上；「全部開啟／全部關閉／清空站點」一次處理。',
        '自動排序在 11 個站以內算出最佳順序，更多站時用近似排序（接近最佳）。',
        '勾「定期回指定站」並設定每幾站、哪個站，排序時會把回指定站算進去，航段表會多出「回指定站」那一段。',
        '每個站點旁邊的尺標數字是起點到該站的直線距離（不同星系顯示「跨星系」）。',
        '結果預設在跳出視窗裡顯示（關掉「結果用跳出視窗」就接在表單下面）；關掉視窗後可以按「查看航線」再打開。',
        '結果有「最快」「最省油」「最順路」三種方案，可以切換航段表或 3D 星圖。',
        '3D 星圖上站點右下角的綠色箱子徽章＝有外部貨運（外掛貨櫃能裝卸），滑鼠移上去或點站點也會顯示有無外部貨運。',
        '3D 星圖右上角的尺標按鈕可以切換顯示起點到各站的直線距離（黃色虛線）。',
        '航段表每一站列出經過的 OM 點與跳躍點、距離、時間、油量、剩油；油不夠時在出發前那一站提示「需補充燃料」。',
        '站點會標特大機庫、外部貨運、對接口等特性。',
      ] },
      { title: '飛行中使用航段表', figs: [{ src: 'route_visited', alt: '標記已去過，下一站自動往下移' }, { src: 'route_finish', alt: '完成：結束或終點設為起點' }], items: [
        '點站號圓鈕標記「已去過」，再點一次取消；第一個還沒去的站會標「下一站」。',
        '最左邊的上下按鈕（或拖拉整列）可以調整順序，會重新計算。',
        '「中途插入站點」：選一個要加的站，按「重新規劃未完成的行程」，從最後一個已去過的站出發，把剩下的重新排好。',
        '跑完這趟在結果底部的「完成」列選「結束」（清掉這次的結果）或「終點設為起點」（這趟的最後一站變成新起點、終點清空，途經站點保留，可以直接排下一趟）。',
      ] },
      { title: '合約分配', figs: [{ src: 'contracts_form', alt: '小隊與合約' }, { src: 'contracts_result', alt: '分配結果與各隊航段表' }], items: [
        '設定小隊數（最多 6 隊），每隊各自選船、起點；勾「我的小隊」的才會套用「只看我的機庫」。',
        '加入合約（最多 10 份），每份填幾項貨物：商品（可以從商品資料庫選）、取貨點、送貨點與 SCU。',
        '送貨點要填 SCU；取貨點不知道各拿多少可以留空：不會猜數量，這些取貨點由同一隊一趟全部去完（貨艙預留剩下的全部量）再送，結果顯示「數量未知」。',
        '取貨點、送貨點很多時按「依星系填入」：選星系（地面站要再選行星）、勾站點類型，一次填進該項貨物（各最多 30 個）。',
        '所有貨物都送到同一批地點時勾「共同送貨點」：上方設定送貨點（也能依星系填入），各項貨物只填要送到各點的 SCU，留空的點就是這項貨物不送那裡。',
        '按「分析分配」，得到「最快完成」「總時間最少」「總油量最少」「站點平均」四種方案：哪一趟貨給哪一隊，以及各隊的航段表與 3D 星圖。',
        '「站點平均」是每個站點（取貨、送貨都算）只給一隊去，各隊航程盡量一樣；同一筆貨的取、送站點一定同一隊，有貨物相連的站點會綁在一起分；站點太集中（例如同一個倉庫取貨）分不開時，會改成讓取貨站（或送貨站）由多隊共用，結果上會標示。',
        '同名商品分屬不同合約時會提醒取貨時分開放、送貨時分開繳交；外掛貨櫃船（Hull 系列）只會派到有外部貨運的站。',
        '各隊的航段表一樣可以標已去過、調整順序、中途插入重新規劃。',
      ] },
    ],
  },
  {
    id: 'items', title: '物品', icon: 'bi bi-database',
    intro: '分「物品資料」和「商品購買地點」兩個子分頁。',
    blocks: [
      { title: '物品資料', figs: [{ src: 'warehouse_items', alt: '物品資料' }], items: [
        '瀏覽遊戲物品資料庫（含飛船組件），點整列看詳細數值與購買地點。',
        '可以依名稱、類型篩選，只看買得到的、只看可拆解的，或依拆解後會得到的材料找物品。',
      ] },
      { title: '商品購買地點', figs: [{ src: 'warehouse_commodities', alt: '勾選兩種商品，列出都買得到的終端' }], items: [
        '勾選好幾種商品，列出「全部都買得到」的交易終端，可以再依星系、行星、地點縮小範圍；價格來自 UEX 玩家回報。',
      ] },
    ],
  },
  {
    id: 'cargo', title: '貨艙網格', icon: 'bi bi-boxes',
    blocks: [
      { figs: [{ src: 'cargo', alt: '自動裝滿後的貨艙' }], items: [
        '加入幾艘船（或按「加入機庫的船」），每艘填 1～32 SCU 各種貨櫃的數量，按「裝載」擺進船的貨艙網格；放不下的會列出來。',
        '「自動裝滿」用最大的貨櫃把貨艙塞滿並填好數量。',
        '右邊 3D 檢視：拖拉旋轉、滾輪或兩指縮放，右上角可以切俯視或重設視角；貨櫃依大小上色。',
        '貨艙網格資料來自 sc-cargo.space。',
      ] },
    ],
  },
  {
    id: 'search', title: '查詢持有資訊', icon: 'bi bi-search',
    blocks: [
      { figs: [{ src: 'search', alt: '物品、藍圖、船艦整合在一張表' }], items: [
        '查公會裡誰有某個物品（數量、地點）、誰登記了某張藍圖、誰有哪款船。',
        '一張搜尋卡＋一張列表：物品、藍圖、船艦都列在同一張表，不屬於那一類的欄位是空的（例如藍圖沒有數量）。',
        '名稱直接打字就會篩，也可以從清單選定某個物品／藍圖／船；選了玩家就是看他有什麼。',
        '「種類」按鈕上有各類的數量；選了物品／藍圖／船艦其中一種，會多出那一種專用的條件（類型、地點、尺寸、廠商等）。',
        '不選條件時列出全部；點表頭排序；按「詳細」看持有者（物品會列出放在哪裡）。',
        '船艦的配件網址直接列在船名下面，按鈕標「玩家 · 識別名稱 · 配件碼」（沒填識別名稱、又有好幾艘時標第幾艘）。',
        '查詢條件會記在網址上，按「複製連結」貼給隊友，對方打開就是同一個查詢。',
      ] },
    ],
  },
  {
    id: 'gamelog', title: 'LOG 解析', icon: 'bi bi-journal-code',
    blocks: [
      { items: [
        '選你電腦上的 Game.log（遊戲安裝資料夾裡），整理成中文事件時間軸與這次遊玩的回顧。',
        '檔案只在瀏覽器裡解析，不會上傳到伺服器。',
        'Chrome／Edge 可以用「選擇並監看」持續讀取新的紀錄；遊戲裝在系統資料夾時瀏覽器會擋，請改用一般的「選擇 Game.log」。',
      ] },
    ],
  },
  {
    id: 'payout', title: '酬勞分配', icon: 'bi bi-cash-coin',
    blocks: [
      { figs: [{ src: 'payout', alt: '酬勞分配' }], items: [
        '輸入總金額、成員與稅率，每個人可以調成數（預設平均分），列出每個人的稅前、稅、稅後金額。',
      ] },
    ],
  },
  {
    id: 'chatcode', title: '中文轉碼', icon: 'bi bi-translate',
    blocks: [
      { figs: [{ src: 'chatcode', alt: '中文轉成代碼' }], items: [
        '遊戲聊天打不了中文：輸入中文會轉成「[zh] @代碼」，複製到遊戲裡；收到 @代碼 也能轉回中文。',
        '下半部可以查遊戲文字代碼（localization key）對應的中文。',
      ] },
    ],
  },
  {
    id: 'tools', title: '工具網站', icon: 'bi bi-link-45deg',
    blocks: [
      { figs: [{ src: 'tools', alt: '工具網站' }], items: ['公會整理的外部工具網站連結，依標籤分組，每張卡片有網址與說明，按「開啟」開新頁。', '可以搜尋名稱、網址、說明、標籤；上面的標籤按鈕（或卡片上的標籤）按了就只看那幾類，可以多選。'] },
    ],
  },
  {
    id: 'profile', title: '個人資料', icon: 'bi bi-person-gear',
    blocks: [
      { figs: [{ src: 'profile', alt: '個人資料' }], items: [
        '修改暱稱、查看 Discord 綁定、更改密碼。',
        '「顯示的分頁」：勾選要顯示哪些分頁；有些分頁預設不顯示，需要時在這裡打開。',
      ] },
    ],
  },
]
</script>

<style scoped>
.help-page { min-height: 100vh; padding: 1rem; }
.help-wrap { max-width: 56rem; margin: 0 auto; }
.help-head { margin-bottom: 1rem; }
.help-title { font-size: 1.6rem; font-weight: 700; margin: 0; color: var(--sf-text-strong, var(--sf-text)); }
.help-toc { display: flex; flex-wrap: wrap; gap: .4rem; margin-top: .9rem; }
.help-toc__item {
  display: inline-flex; align-items: center; padding: .3rem .75rem; border-radius: 999px;
  border: 1px solid var(--sf-border-hi); background: var(--sf-chip-bg); color: var(--sf-text);
  font-size: 1rem; text-decoration: none;
}
.help-toc__item:hover { border-color: var(--sf-accent); color: var(--sf-accent-text, var(--sf-accent)); }
.help-card { margin-bottom: 1rem; scroll-margin-top: 1rem; }
.help-h2 { font-size: 1.3rem; font-weight: 700; margin-bottom: .5rem; color: var(--sf-accent-text, var(--sf-accent)); }
.help-h3 { font-size: 1.05rem; font-weight: 700; margin: .75rem 0 .35rem; color: var(--sf-text-strong, var(--sf-text)); }
.help-intro { color: var(--sf-text-muted); font-size: 1rem; margin-bottom: .25rem; }
.help-list { margin: 0; padding-left: 1.25rem; font-size: 1rem; line-height: 1.7; color: var(--sf-text); }
.help-list li + li { margin-top: .2rem; }
.help-fig { margin: .75rem 0 .25rem; }
.help-fig a { display: block; }
.help-fig img {
  display: block; width: 100%; height: auto; border-radius: .5rem;
  border: 1px solid var(--sf-border-hi); background: var(--sf-chip-bg);
}
.help-fig figcaption { margin-top: .35rem; font-size: 1rem; color: var(--sf-text-muted); text-align: center; }
</style>
