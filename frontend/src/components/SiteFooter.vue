<!--
  說明頁最下方的「資料來源與使用條款」：本站用到的每個外部資料來源、它的授權／使用條款連結，
  以及本站的使用範圍（非官方、非商業粉絲工具）。新增同步來源時這裡也要加一列（後端來源清單見 src/scdata.py 的 PROVIDERS）。

  只列有公開 API／公開授權的來源；每列的「條款」連結就是可以這樣使用的依據。
-->
<template>
  <footer class="site-footer" aria-label="資料來源與使用條款">
    <div class="site-footer__head">
      <span class="site-footer__title">資料來源與使用條款</span>
      <span class="site-footer__note">本站為玩家自製的非官方、非商業粉絲工具，與 Cloud Imperium Games／Roberts Space Industries 無關。</span>
    </div>
    <ul class="site-footer__list">
      <li v-for="s in SOURCES" :key="s.name">
        <span class="site-footer__name">{{ s.name }}</span>
        <span class="site-footer__use">{{ s.use }}</span>
        <!-- 玩家頁不用文字連結：開外部網址用有底色的按鈕樣式（CLAUDE.md 介面文字原則） -->
        <span class="site-footer__terms">
          <a v-for="t in s.terms" :key="t.url" :href="t.url" target="_blank" rel="noopener noreferrer"
            class="btn btn-sm btn-primary"><i class="bi bi-box-arrow-up-right me-1"></i>{{ t.label }}</a>
        </span>
      </li>
    </ul>
    <p class="site-footer__legal">
      Star Citizen®、Squadron 42®、Roberts Space Industries® 及相關名稱、圖像為 Cloud Imperium Rights LLC／Cloud Imperium Rights Ltd. 所有，
      依 RSI 粉絲政策於非商業用途下使用。遊戲數值來自社群解包與玩家回報，可能與遊戲內不同。
    </p>
  </footer>
</template>

<script setup>
// 每個來源：名稱、本站拿來做什麼、使用依據（授權／條款）
const SOURCES = [
  { name: 'Star Citizen（RSI 官方）', url: 'https://robertsspaceindustries.com', use: '遊戲名稱、商標；船艦官網售價、商店上架、借用船清單（公開頁面）',
    terms: [{ label: 'Fankit 與粉絲 FAQ', url: 'https://support.robertsspaceindustries.com/hc/en-us/articles/360006895793-Star-Citizen-Fankit-and-Fandom-FAQ' },
      { label: '服務條款', url: 'https://robertsspaceindustries.com/en/tos' }] },
  { name: 'Star Citizen Wiki API', url: 'https://api.star-citizen.wiki', use: '物品、艦船、藍圖、任務、勢力、商品（含礦物取得方式判斷）',
    terms: [{ label: '使用說明（須標註來源、不得商用）', url: 'https://api.star-citizen.wiki/developers' }] },
  { name: 'scunpacked-data（Star Citizen Wiki）', url: 'https://github.com/StarCitizenWiki/scunpacked-data', use: '礦床、採礦地點、星圖、配裝、藍圖品質、英文原文',
    terms: [{ label: 'GitHub 公開儲存庫', url: 'https://github.com/StarCitizenWiki/scunpacked-data' },
      { label: 'Fankit 與粉絲 FAQ', url: 'https://support.robertsspaceindustries.com/hc/en-us/articles/360006895793-Star-Citizen-Fankit-and-Fandom-FAQ' }] },
  { name: 'UEX Corp API', url: 'https://uexcorp.space', use: '遊戲內買賣價、租船價、精煉資料（玩家回報）',
    terms: [{ label: 'API 文件（允許任何專案使用）', url: 'https://uexcorp.space/api/documentation' },
      { label: '條款', url: 'https://uexcorp.space/about/terms' }] },
  { name: '星際公民繁體中文化語言包', url: 'https://github.com/cosmo-chang-1701/sc-translation-pack', use: '遊戲文字繁體中文翻譯',
    terms: [{ label: 'CC BY-NC-SA 4.0', url: 'https://github.com/cosmo-chang-1701/sc-translation-pack/blob/main/LICENSE' }] },
  { name: 'sc-cargo.space', url: 'https://github.com/sccargospace/sc-cargo.space', use: '船艦貨艙網格',
    terms: [{ label: 'MIT License', url: 'https://github.com/sccargospace/sc-cargo.space/blob/main/LICENSE' }] },
  { name: 'Open Hangar', url: 'https://openhangar.space', use: 'RSI 商店上架歷史（2021-11 起）',
    terms: [{ label: 'CC BY 4.0', url: 'https://creativecommons.org/licenses/by/4.0/' }] },
]
</script>

<style scoped>
.site-footer {
  margin-top: 2.5rem; padding: 1rem 0 .5rem; border-top: 1px solid var(--sf-border);
  color: var(--sf-text-muted); font-size: var(--sf-fs-sm); line-height: var(--sf-lh-body);
}
.site-footer__head { display: flex; flex-wrap: wrap; align-items: baseline; gap: .25rem .75rem; margin-bottom: .5rem; }
.site-footer__title { font-weight: 700; color: var(--sf-text); }
.site-footer__list { list-style: none; padding: 0; margin: 0 0 .75rem; display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 22rem), 1fr)); gap: .75rem 1.25rem; }
.site-footer__list li { display: flex; flex-direction: column; gap: .15rem; }
.site-footer__name { font-weight: 600; color: var(--sf-text); }
.site-footer__terms { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .1rem; }
.site-footer__legal { margin: 0; font-size: var(--sf-fs-xs); }
</style>
