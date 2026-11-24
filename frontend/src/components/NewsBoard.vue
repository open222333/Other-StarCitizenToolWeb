<!--
  玩家頁「新聞」分頁（不登入也能看）：後台或外部程式（API 金鑰，POST /news/ingest）寫入的新聞。
  雜誌式版面（配色用網站主題的 --sf-* 變數，跟著「配色」切換）：最上面「最新消息」跑馬燈；沒有搜尋／篩選時，
  置頂區 4 則大圖（官方優先、再置頂、再最新；標題、標籤疊在圖上，沒有封面用主題色漸層代替），下面是依時間新到舊的卡片。
  搜尋關鍵字、標籤篩選、發布日期（今日／昨日／上週）；一次 20 則，往下捲自動載入更舊的。後台下架的標籤，帶它的新聞不會出現。
  點一則跳出視窗看全文（components/NewsArticle.vue）。網址 ?news=<id> 直接打開那一則（分享用）。
-->
<template>
  <div class="nb">
    <!-- 最新消息跑馬燈（最新 8 則，滑鼠移上去暫停；減少動態效果時不跑，改成可以橫向捲） -->
    <div v-if="latest.length" class="nb-ticker" :class="cardClass">
      <span class="nb-ticker__label"><i class="bi bi-lightning-charge-fill me-1"></i>最新消息</span>
      <div class="nb-ticker__view">
        <div class="nb-ticker__track" :style="{ animationDuration: `${Math.max(20, latest.length * 6)}s` }">
          <button v-for="(n, i) in [...latest, ...latest]" :key="`${n._id}-${i}`" type="button" class="nb-ticker__item"
            :tabindex="i < latest.length ? 0 : -1" :aria-hidden="i >= latest.length ? 'true' : null" @click="openItem(n)">
            <span class="nb-ticker__dot" aria-hidden="true"></span>{{ n.title }}</button>
        </div>
      </div>
    </div>

    <!-- 搜尋＋分類（像新聞網站的頂端列）：圓角搜尋框；下面一排分類分頁，只放幾個主要分類，其餘收在「更多」 -->
    <div class="nb-filter">
      <div class="nb-search sf-search-pill sf-search-pill--round">
        <i class="bi bi-search sf-search-pill__icon" aria-hidden="true"></i>
        <input id="news-q" v-model.trim="query" type="search" class="sf-search-pill__input" placeholder="搜尋標題、內文和標籤"
          aria-label="搜尋新聞">
      </div>
      <nav class="nb-tabs" aria-label="分類">
        <button type="button" class="nb-tab" :class="{ active: !tag }" :aria-pressed="!tag ? 'true' : 'false'" @click="pickTag('')">全部</button>
        <span v-if="mainTags.length" class="nb-tabs__sep" aria-hidden="true"></span>
        <button v-for="t in mainTags" :key="t" type="button" class="nb-tab" :class="{ active: tag === t }"
          :aria-pressed="tag === t ? 'true' : 'false'" @click="pickTag(t)">{{ t }}</button>
        <button v-if="moreTags.length" type="button" class="nb-tab nb-tab--more" :class="{ open: showMore }" :aria-expanded="showMore ? 'true' : 'false'"
          aria-controls="news-more-tags" @click="showMore = !showMore">更多<i class="bi bi-chevron-down ms-1"></i></button>
      </nav>
      <div class="nb-dates" role="group" aria-label="發布日期">
        <button v-for="d in DATE_FILTERS" :key="d.key" type="button" class="nb-date" :class="{ active: dateKey === d.key }"
          :aria-pressed="dateKey === d.key ? 'true' : 'false'" @click="dateKey = d.key">{{ d.label }}</button>
      </div>
      <div v-if="showMore && moreTags.length" id="news-more-tags" class="nb-tags" role="group" aria-label="更多分類">
        <button v-for="t in moreTags" :key="t.tag" type="button" class="nb-tag" :style="{ '--h': tagHue(t.tag) }"
          :class="{ active: tag === t.tag }" :aria-pressed="tag === t.tag ? 'true' : 'false'" @click="pickTag(t.tag)">
          <span class="nb-tag__dot" aria-hidden="true"></span>{{ t.tag }}<span class="nb-tag__n">{{ t.count }}</span></button>
      </div>
    </div>

    <!-- 頭條：沒有搜尋／篩選時，前 4 則排成雜誌版面（左大、中兩小、右直長） -->
    <section v-if="showHero" class="nb-hero" :class="`nb-hero--${hero.length}`" aria-label="頭條">
      <button v-for="(n, i) in hero" :key="n._id" type="button" class="nb-tile" :class="`nb-tile--${i}`" @click="openItem(n)">
        <img v-if="n.cover_url && !broken.has(n._id)" :src="n.cover_url" alt="" class="nb-tile__img" loading="lazy"
          referrerpolicy="no-referrer" @error="broken.add(n._id)">
        <span v-else class="nb-tile__ph" aria-hidden="true"></span>
        <span class="nb-tile__shade" aria-hidden="true"></span>
        <span class="nb-tile__body">
          <span class="d-flex flex-wrap gap-1 mb-1">
            <span v-if="n.pinned" class="nb-badge nb-badge--pin"><i class="bi bi-pin-angle-fill me-1"></i>置頂</span>
            <span v-for="t in n.tags.slice(0, 2)" :key="t" class="nb-badge" :style="{ '--h': tagHue(t) }">{{ t }}</span>
          </span>
          <span class="nb-tile__title">{{ n.title }}</span>
          <span class="nb-meta"><i class="bi bi-clock me-1"></i>{{ fmtNewsDate(n.published_at) }}</span>
        </span>
      </button>
    </section>

    <SfState :loading="loading && !items.length" :error="error" :empty="loaded && !items.length"
      :empty-text="query || tag || dateKey ? '沒有符合的新聞。' : '目前沒有新聞。'" @retry="reload">
      <h2 v-if="showHero && rest.length" class="nb-section"><span>更多新聞</span></h2>
      <div class="nb-list">
        <button v-for="n in rest" :key="n._id" type="button" :class="[cardClass, 'nb-card']" @click="openItem(n)">
          <span class="nb-card__media">
            <img v-if="n.cover_url && !broken.has(n._id)" :src="n.cover_url" alt="" loading="lazy" referrerpolicy="no-referrer"
              @error="broken.add(n._id)">
            <span v-else class="nb-tile__ph" aria-hidden="true"></span>
            <span class="nb-card__badges">
              <span v-if="n.pinned" class="nb-badge nb-badge--pin"><i class="bi bi-pin-angle-fill me-1"></i>置頂</span>
              <span v-for="t in n.tags.slice(0, 2)" :key="t" class="nb-badge" :style="{ '--h': tagHue(t) }">{{ t }}</span>
            </span>
          </span>
          <span class="nb-card__body">
            <span class="nb-card__title">{{ n.title }}</span>
            <span v-if="n.excerpt" class="nb-card__excerpt">{{ n.excerpt }}</span>
            <span class="nb-meta nb-meta--muted"><i class="bi bi-clock me-1"></i>{{ fmtNewsDate(n.published_at) }}</span>
          </span>
        </button>
      </div>
      <!-- 捲到這裡自動載入更舊的（IntersectionObserver） -->
      <div ref="sentinel" class="nb-more" aria-hidden="true">
        <span v-if="loading && items.length" class="spinner-border spinner-border-sm"></span>
      </div>
    </SfState>

    <Teleport to="body">
      <div class="scifi-page nb-host">
        <SfModal id="news-article" v-model:open="open" :title="current?.title || '新聞'" icon="bi bi-newspaper" width="860px">
          <SfState v-if="!current?.body && articleLoading" :loading="true" />
          <NewsArticle v-else-if="current" :item="current" />
        </SfModal>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import NewsArticle from '@/components/NewsArticle.vue'
import { fetchNews, fetchNewsFeatured, fetchNewsItem, fetchNewsTags, fmtNewsDate, tagHue } from '@/utils/news'
import { useBreakpoint } from '@/composables/useBreakpoint'
import { DATE_FILTERS, dateRange } from '@/utils/newsDate'

const props = defineProps({
  fetcher: { type: Function, required: true },
  cardClass: { type: String, default: 'card' },
  /** 第一次顯示才載入 */
  active: { type: Boolean, default: true },
})

const PAGE = 20
// 封面圖讀不到的（網址失效）就不顯示圖框
const broken = reactive(new Set())
const items = ref([])
const total = ref(0)
const tags = ref([])
const loading = ref(false)
const loaded = ref(false)
const error = ref('')
const query = ref('')
const tag = ref('')
// 發布日期：''＝不限、today、yesterday、week（utils/newsDate.js，用瀏覽器時區切日）
const dateKey = ref('')
// 分類列放後台設成「分類列」的標籤（display main，後端已依 order 排好），其他收在「更多」（外部新帶進來的標籤預設在這裡）；
// 有這個標籤的新聞才出現，後台下架的不會出現。選到「更多」裡的標籤時，它也暫時排進分類列
const showMore = ref(false)
const mainTags = computed(() => {
  const list = tags.value.filter(t => t.display === 'main').map(t => t.tag)
  if (tag.value && !list.includes(tag.value)) list.push(tag.value)
  return list
})
const moreTags = computed(() => tags.value.filter(t => t.display !== 'main'))
function pickTag(t) {
  tag.value = tag.value === t ? '' : t
  showMore.value = false
}

// 序號擋掉過期回應：快速改關鍵字時，舊請求晚回來不會蓋掉新的結果
let loadSeq = 0
async function load(offset = 0) {
  const seq = ++loadSeq
  const filtered = !!(query.value || tag.value || dateKey.value)
  loading.value = true
  const r = await fetchNews(props.fetcher, { q: query.value, tag: tag.value, ...dateRange(dateKey.value), limit: PAGE, offset })
  if (seq !== loadSeq) return
  loading.value = false
  loaded.value = true
  if (!r.ok) { error.value = r.message; return }
  error.value = ''
  items.value = offset ? [...items.value, ...r.data] : r.data
  total.value = r.total
  if (!offset && !filtered) latest.value = r.data.slice(0, 8)   // 跑馬燈：沒篩選的第一頁就是最新的，不用另外查
}
const reload = () => load(0)
// 置頂區：沒有搜尋／篩選時顯示，後端挑好（官方優先、再置頂、再最新，見 src/models/news.py featured()）；
// 下面的列表一律新到舊，已經在置頂區的不重複列。寬螢幕 4 則（右邊直長那格）、平板以下 3 則
const featured = ref([])
const latest = ref([])   // 跑馬燈：最新 8 則（load() 第一頁沒篩選時順便填）
const showHero = computed(() => !query.value && !tag.value && !dateKey.value && featured.value.length > 0)
const { isWide: wide } = useBreakpoint()   // 監聽器卸載時由 composable 移除
const hero = computed(() => (showHero.value ? featured.value.slice(0, wide.value ? 4 : 3) : []))
const rest = computed(() => {
  if (!showHero.value) return items.value
  const ids = new Set(hero.value.map(n => n._id))
  return items.value.filter(n => !ids.has(n._id))
})
async function loadFeatured() {
  const r = await fetchNewsFeatured(props.fetcher)
  if (r.ok) featured.value = r.data
}
let timer = null
watch([query, tag, dateKey], () => { clearTimeout(timer); timer = setTimeout(reload, 250) })

// ── 往下捲自動載入更舊的 ──
// 底部哨兵進到畫面（提前 600px）就載下一頁；載完哨兵還在畫面裡（一頁不夠填滿）就再載
const sentinel = ref(null)
const hasMore = computed(() => items.value.length < total.value)
function sentinelInView() {
  const el = sentinel.value
  if (!el || !el.offsetParent) return false        // 分頁沒顯示時 offsetParent 是 null
  return el.getBoundingClientRect().top < window.innerHeight + 600
}
async function loadMore() {
  if (loading.value || error.value || !hasMore.value) return
  await load(items.value.length)
  if (sentinelInView()) loadMore()
}
let observer = null
watch(sentinel, (el) => {
  observer?.disconnect()
  if (!el || typeof IntersectionObserver === 'undefined') return
  observer = new IntersectionObserver((entries) => { if (entries.some(e => e.isIntersecting)) loadMore() },
    { rootMargin: '0px 0px 600px 0px' })
  observer.observe(el)
})
onBeforeUnmount(() => observer?.disconnect())

let started = false
async function start() {
  if (started || !props.active) return
  started = true
  await Promise.all([fetchNewsTags(props.fetcher).then(t => { tags.value = t }), reload(), loadFeatured()])
  // 分享連結 ?news=<id>：直接打開那一則
  const id = new URLSearchParams(window.location.search).get('news')
  if (id) openItem({ _id: id })
}
watch(() => props.active, start)
onMounted(start)

const open = ref(false)
// 從分享連結（?news=<id>）打開的：關掉視窗時把 news 從網址拿掉，重新整理不會再跳出來
const route = useRoute()
const router = useRouter()
watch(open, (v) => {
  if (v || !route.query.news) return
  const query = { ...route.query }
  delete query.news
  router.replace({ query })
})
const current = ref(null)
const articleLoading = ref(false)
async function openItem(n) {
  current.value = n
  open.value = true
  articleLoading.value = true
  const full = await fetchNewsItem(props.fetcher, n._id)
  articleLoading.value = false
  if (full && current.value?._id === n._id) current.value = full
}
defineExpose({ openItem })
</script>

<style scoped>
.nb-host { display: contents; }
.nb-more { display: flex; justify-content: center; min-height: 2.5rem; padding-top: 1rem; color: var(--sf-text-muted); }

/* ── 搜尋＋分類：圓角搜尋框＋底線分頁（像新聞網站頂端列）；「更多」展開其餘標籤（每個標籤的色點見 utils/news.js tagHue） ── */
.nb-filter { margin-bottom: 1rem; }
.nb-search { max-width: 46rem; margin: 0 auto .5rem; }
.nb-tabs { display: flex; align-items: stretch; justify-content: center; gap: .25rem; border-bottom: 1px solid var(--sf-border);
  overflow-x: auto; scrollbar-width: none; }
.nb-tabs::-webkit-scrollbar { display: none; }
.nb-tabs__sep { width: 1px; margin: .55rem .5rem; background: var(--sf-border); flex: 0 0 auto; }
.nb-tab {
  position: relative; flex: 0 0 auto; padding: .6rem 1rem .7rem; background: none; border: 0; border-radius: .4rem .4rem 0 0;
  font-size: var(--sf-fs-base); font-weight: 600; color: var(--sf-text); white-space: nowrap; transition: color .15s, background-color .15s;
}
.nb-tab:hover { color: var(--sf-text-strong); background: var(--sf-hover-bg); }
.nb-tab:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: -2px; }
.nb-tab.active { color: var(--sf-accent-text, var(--sf-accent)); }
.nb-tab.active::after { content: ''; position: absolute; left: .75rem; right: .75rem; bottom: 0; height: 3px;
  border-radius: 3px 3px 0 0; background: var(--sf-accent); }
.nb-tab--more .bi { font-size: .8em; transition: transform .15s; display: inline-block; }
.nb-tab--more.open { color: var(--sf-text-strong); }
.nb-tab--more.open .bi { transform: rotate(180deg); }
.nb-dates { display: flex; justify-content: center; flex-wrap: wrap; gap: .3rem; padding-top: .6rem; }
.nb-date { border: 1px solid var(--sf-border); background: var(--sf-chip-bg); color: var(--sf-text); border-radius: 999px;
  padding: .15rem .8rem; font-size: var(--sf-fs-sm); font-weight: 600; }
.nb-date:hover { color: var(--sf-text-strong); border-color: var(--sf-accent); }
.nb-date.active { background: rgba(var(--sf-accent-rgb), .28); border-color: var(--sf-accent); color: var(--sf-text-strong); }
.nb-tags { display: flex; flex-wrap: wrap; justify-content: center; gap: .4rem; padding: .75rem 0 .25rem; }
.nb-tag {
  --h: 210;
  display: inline-flex; align-items: center; gap: .35rem; padding: .28rem .7rem; border-radius: 999px;
  font-size: var(--sf-fs-sm); font-weight: 600; line-height: 1.3; white-space: nowrap;
  color: var(--sf-text); background: var(--sf-chip-bg); border: 1px solid var(--sf-border);
  transition: background-color .15s, border-color .15s, color .15s;
}
/* 顏色只用在色點；滑過、選中才帶一點該標籤的色調 */
.nb-tag:hover { color: var(--sf-text-strong); border-color: hsla(var(--h), 55%, 60%, .7); }
.nb-tag:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: 2px; }
.nb-tag.active { color: var(--sf-text-strong); background: hsla(var(--h), 45%, 50%, .2); border-color: hsla(var(--h), 55%, 60%, .8); }
.nb-tag__dot { width: .5rem; height: .5rem; border-radius: 50%; background: hsl(var(--h), 55%, 58%); flex: 0 0 auto; }
.nb-tag__n { font-size: var(--sf-fs-xs); font-weight: 600; color: var(--sf-text-muted); }
.nb-tag.active .nb-tag__n { color: var(--sf-text); }
:root[data-sf-mode='light'] .nb-tag.active { background: hsla(var(--h), 45%, 50%, .14); }

/* ── 跑馬燈 ── */
.nb-ticker { display: flex; flex-direction: row; align-items: stretch; overflow: hidden; margin-bottom: .9rem; padding: 0 !important; }
.nb-ticker__label {
  flex: 0 0 auto; display: inline-flex; align-items: center; padding: .45rem .9rem; font-weight: 700; font-size: var(--sf-fs-sm);
  color: var(--sf-accent-2-ink, #0b1020); background: var(--sf-accent-2); white-space: nowrap;
}
.nb-ticker__view { flex: 1 1 auto; min-width: 0; overflow: hidden; display: flex; align-items: center;
  mask-image: linear-gradient(90deg, transparent, #000 2rem, #000 calc(100% - 2rem), transparent); }
.nb-ticker__track { display: inline-flex; gap: 2rem; white-space: nowrap; padding-left: 1rem; animation: nb-marquee linear infinite; }
.nb-ticker:hover .nb-ticker__track, .nb-ticker:focus-within .nb-ticker__track { animation-play-state: paused; }
@keyframes nb-marquee { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@media (prefers-reduced-motion: reduce) {
  .nb-ticker__track { animation: none; }
  .nb-ticker__view { overflow-x: auto; }
}
.nb-ticker__item { background: none; border: 0; padding: .45rem 0; color: var(--sf-text); font-size: var(--sf-fs-sm); font-weight: 600; }
.nb-ticker__item:hover { color: var(--sf-accent-text, var(--sf-accent)); }
.nb-ticker__dot { display: inline-block; width: .4rem; height: .4rem; border-radius: 50%; background: var(--sf-accent-2); margin-right: .55rem; vertical-align: middle; }

/* ── 頭條 ── */
.nb-hero { display: grid; gap: .9rem; margin-bottom: 1rem;
  grid-template-columns: 2fr 1fr 1fr; grid-template-rows: 13rem 13rem; }
.nb-tile--0 { grid-column: 1; grid-row: 1 / span 2; }
.nb-tile--1 { grid-column: 2; grid-row: 1; }
.nb-tile--2 { grid-column: 2; grid-row: 2; }
.nb-tile--3 { grid-column: 3; grid-row: 1 / span 2; }
.nb-hero--1 { grid-template-columns: 1fr; grid-template-rows: 22rem; }
.nb-hero--2 { grid-template-columns: 2fr 1fr; }
.nb-hero--2 .nb-tile--1 { grid-row: 1 / span 2; }
.nb-hero--3 { grid-template-columns: 2fr 1fr; }
.nb-tile {
  position: relative; display: block; overflow: hidden; border-radius: .6rem; padding: 0; text-align: left;
  border: 1px solid var(--sf-border); background: rgba(var(--sf-panel-rgb, 18, 26, 43), .5); color: #fff; min-height: 0;
}
.nb-tile__img, .nb-tile__ph { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transition: transform .5s ease; }
.nb-tile__ph {
  display: flex; align-items: center; justify-content: center; font-size: 3rem; color: rgba(255, 255, 255, .18);
  background:
    radial-gradient(ellipse 80% 70% at 20% 10%, rgba(var(--sf-accent-rgb), .45), transparent 60%),
    radial-gradient(ellipse 70% 60% at 90% 90%, rgba(var(--sf-accent-2-rgb), .35), transparent 60%),
    rgba(var(--sf-panel-rgb, 18, 26, 43), .45);
}
.nb-tile:hover .nb-tile__img, .nb-tile:hover .nb-tile__ph, .nb-card:hover .nb-card__media img { transform: scale(1.05); }
.nb-tile:focus-visible, .nb-card:focus-visible { outline: 2px solid var(--sf-accent); outline-offset: 2px; }
.nb-tile__shade { position: absolute; inset: 0; background: linear-gradient(180deg, transparent 35%, rgba(4, 8, 18, .88) 100%); }
.nb-tile__body { position: absolute; left: 0; right: 0; bottom: 0; padding: .9rem 1rem; display: flex; flex-direction: column; }
.nb-tile__title { font-weight: 800; font-size: var(--sf-fs-md); line-height: 1.35; text-shadow: 0 1px 3px rgba(0, 0, 0, .6);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.nb-tile--0 .nb-tile__title { font-size: var(--sf-fs-xl); }
.nb-badge {
  display: inline-flex; align-items: center; padding: .1rem .5rem; border-radius: .25rem; font-size: var(--sf-fs-xs); font-weight: 700;
  color: var(--sf-accent-2-ink, #0b1020); background: var(--sf-accent-2);
}
.nb-badge[style] { color: #fff; background: rgba(4, 8, 18, .62); box-shadow: inset 3px 0 0 hsl(var(--h), 55%, 58%); padding-left: .55rem; }
.nb-badge--pin { background: var(--sf-accent); }
.nb-meta { display: inline-flex; align-items: center; margin-top: .35rem; font-size: var(--sf-fs-xs); color: rgba(255, 255, 255, .85); }
.nb-meta--muted { color: var(--sf-text-muted); }

/* ── 更多新聞 ── */
.nb-section { display: flex; align-items: center; gap: .75rem; font-size: var(--sf-fs-md); font-weight: 800; margin: .25rem 0 .75rem;
  color: var(--sf-text-strong); }
.nb-section span { padding-left: .6rem; border-left: 4px solid var(--sf-accent-2); }
.nb-section::after { content: ''; flex: 1; border-bottom: 1px solid var(--sf-border); }
.nb-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 17rem), 1fr)); gap: .9rem; }
.nb-card { display: flex; flex-direction: column; padding: 0 !important; overflow: hidden; text-align: left; color: inherit; width: 100%; }
.nb-card:hover { border-color: var(--sf-accent) !important; }
.nb-card__media { position: relative; display: block; height: 9.5rem; overflow: hidden; }
.nb-card__media img { width: 100%; height: 100%; object-fit: cover; transition: transform .5s ease; }
.nb-card__badges { position: absolute; left: .6rem; bottom: .6rem; display: flex; flex-wrap: wrap; gap: .25rem; }
.nb-card__body { display: flex; flex-direction: column; padding: .7rem .85rem .85rem; flex: 1 1 auto; }
.nb-card__title { font-weight: 700; font-size: var(--sf-fs-base); line-height: 1.4; color: var(--sf-text-strong);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.nb-card__excerpt { color: var(--sf-text-muted); font-size: var(--sf-fs-sm); margin-top: .3rem;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.nb-card .nb-meta { margin-top: auto; padding-top: .45rem; }

/* 平板：頭條兩欄（大圖一排、其餘並排）；手機：大圖＋其餘兩兩一排 */
@media (max-width: 991.98px) {
  .nb-hero, .nb-hero--2, .nb-hero--3 { grid-template-columns: 1fr 1fr; grid-template-rows: 16rem 11rem; }
  .nb-hero .nb-tile--0 { grid-column: 1 / span 2; grid-row: 1; }
  .nb-hero .nb-tile--1 { grid-column: 1; grid-row: 2; }
  .nb-hero .nb-tile--2 { grid-column: 2; grid-row: 2; }
  .nb-hero--2 .nb-tile--1 { grid-column: 1 / span 2; }
  .nb-hero--1 { grid-template-rows: 16rem; }
  .nb-tile--0 .nb-tile__title { font-size: var(--sf-fs-lg); }
}
@media (max-width: 575.98px) {
  .nb-tabs { justify-content: flex-start; }
  .nb-tab { padding: .5rem .75rem .6rem; }
  .nb-hero, .nb-hero--2, .nb-hero--3 { grid-template-rows: 13rem 9.5rem; gap: .6rem; }
  .nb-tile__title { font-size: var(--sf-fs-sm); }
}
</style>
