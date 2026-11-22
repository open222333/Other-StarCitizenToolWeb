<!--
  玩家頁「新聞」分頁（不登入也能看）：後台或外部程式（API 金鑰，POST /news/ingest）寫入的新聞。
  雜誌式版面（配色用網站主題的 --sf-* 變數，跟著「配色」切換）：最上面「最新消息」跑馬燈；沒有搜尋／篩選時，
  前 4 則（置頂在前）是頭條大圖（標題、標籤疊在圖上，沒有封面用主題色漸層代替），其餘是下面的卡片。
  搜尋關鍵字、標籤篩選；一次 20 則，「載入更多」接著讀。
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

    <!-- 頭條：沒有搜尋／篩選時，前 4 則排成雜誌版面（左大、中兩小、右直長） -->
    <section v-if="showHero" class="nb-hero" :class="`nb-hero--${hero.length}`" aria-label="頭條">
      <button v-for="(n, i) in hero" :key="n._id" type="button" class="nb-tile" :class="`nb-tile--${i}`" @click="openItem(n)">
        <img v-if="n.cover_url && !broken.has(n._id)" :src="n.cover_url" alt="" class="nb-tile__img" loading="lazy"
          referrerpolicy="no-referrer" @error="broken.add(n._id)">
        <span v-else class="nb-tile__ph" aria-hidden="true"><i class="bi bi-newspaper"></i></span>
        <span class="nb-tile__shade" aria-hidden="true"></span>
        <span class="nb-tile__body">
          <span class="d-flex flex-wrap gap-1 mb-1">
            <span v-if="n.pinned" class="nb-badge nb-badge--pin"><i class="bi bi-pin-angle-fill me-1"></i>置頂</span>
            <span v-for="t in n.tags.slice(0, 2)" :key="t" class="nb-badge">{{ t }}</span>
          </span>
          <span class="nb-tile__title">{{ n.title }}</span>
          <span class="nb-meta"><i class="bi bi-clock me-1"></i>{{ fmtNewsDate(n.published_at) }}</span>
        </span>
      </button>
    </section>

    <div :class="[cardClass, 'sf-search', 'mb-3']">
      <div class="card-body py-3">
        <div class="row g-2 align-items-end">
          <div class="col-12 col-md-5">
            <label class="form-label small mb-1" for="news-q">搜尋</label>
            <input id="news-q" v-model.trim="query" type="search" class="form-control form-control-sm" placeholder="標題、內文、標籤…">
          </div>
          <div class="col-12 col-md-7">
            <span class="form-label small mb-1 d-block" id="news-tags-label">分類</span>
            <div class="d-flex flex-wrap gap-1" role="group" aria-labelledby="news-tags-label">
              <button type="button" class="btn btn-sm btn-subtab" :class="{ active: !tag }" :aria-pressed="!tag ? 'true' : 'false'"
                @click="tag = ''">全部</button>
              <button v-for="t in tags" :key="t.tag" type="button" class="btn btn-sm btn-subtab"
                :class="{ active: tag === t.tag }" :aria-pressed="tag === t.tag ? 'true' : 'false'" @click="tag = tag === t.tag ? '' : t.tag">
                {{ t.tag }}<span class="ms-1 nb-count">{{ t.count }}</span></button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <SfState :loading="loading && !items.length" :error="error" :empty="loaded && !items.length"
      :empty-text="query || tag ? '沒有符合的新聞。' : '目前沒有新聞。'" @retry="reload">
      <h2 v-if="showHero && rest.length" class="nb-section"><span>更多新聞</span></h2>
      <div class="nb-list">
        <button v-for="n in rest" :key="n._id" type="button" :class="[cardClass, 'nb-card']" @click="openItem(n)">
          <span class="nb-card__media">
            <img v-if="n.cover_url && !broken.has(n._id)" :src="n.cover_url" alt="" loading="lazy" referrerpolicy="no-referrer"
              @error="broken.add(n._id)">
            <span v-else class="nb-tile__ph" aria-hidden="true"><i class="bi bi-newspaper"></i></span>
            <span class="nb-card__badges">
              <span v-if="n.pinned" class="nb-badge nb-badge--pin"><i class="bi bi-pin-angle-fill me-1"></i>置頂</span>
              <span v-for="t in n.tags.slice(0, 2)" :key="t" class="nb-badge">{{ t }}</span>
            </span>
          </span>
          <span class="nb-card__body">
            <span class="nb-card__title">{{ n.title }}</span>
            <span v-if="n.excerpt" class="nb-card__excerpt">{{ n.excerpt }}</span>
            <span class="nb-meta nb-meta--muted"><i class="bi bi-clock me-1"></i>{{ fmtNewsDate(n.published_at) }}</span>
          </span>
        </button>
      </div>
      <div v-if="items.length < total" class="text-center mt-3">
        <button type="button" class="btn btn-sm btn-primary" :disabled="loading" @click="loadMore">
          <span v-if="loading" class="spinner-border spinner-border-sm me-1"></span>載入更多（{{ items.length }} / {{ total }}）</button>
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
import { computed, onMounted, reactive, ref, watch } from 'vue'
import SfModal from '@/components/SfModal.vue'
import SfState from '@/components/SfState.vue'
import NewsArticle from '@/components/NewsArticle.vue'
import { fetchNews, fetchNewsItem, fetchNewsTags, fmtNewsDate } from '@/utils/news'
import { useBreakpoint } from '@/composables/useBreakpoint'

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

async function load(offset = 0) {
  loading.value = true
  const r = await fetchNews(props.fetcher, { q: query.value, tag: tag.value, limit: PAGE, offset })
  loading.value = false
  loaded.value = true
  if (!r.ok) { error.value = r.message; return }
  error.value = ''
  items.value = offset ? [...items.value, ...r.data] : r.data
  total.value = r.total
}
const reload = () => load(0)
// 頭條：沒有搜尋／篩選時前 4 則；跑馬燈：依時間最新 8 則（不管置頂）
const showHero = computed(() => !query.value && !tag.value && items.value.length > 0)
// 寬螢幕 4 則（右邊直長那格）、平板以下 3 則，多的接到下面的卡片
const { isWide: wide } = useBreakpoint()   // 監聽器卸載時由 composable 移除
const hero = computed(() => (showHero.value ? items.value.slice(0, wide.value ? 4 : 3) : []))
const rest = computed(() => (showHero.value ? items.value.slice(hero.value.length) : items.value))
const latest = ref([])
async function loadLatest() {
  // 後端 sort=latest 只依發布時間排，不用再抓 30 則在前端排
  const r = await fetchNews(props.fetcher, { limit: 8, sort: 'latest' })
  if (r.ok) latest.value = r.data
}
const loadMore = () => load(items.value.length)
let timer = null
watch([query, tag], () => { clearTimeout(timer); timer = setTimeout(reload, 250) })

let started = false
async function start() {
  if (started || !props.active) return
  started = true
  tags.value = await fetchNewsTags(props.fetcher)
  await Promise.all([reload(), loadLatest()])
  // 分享連結 ?news=<id>：直接打開那一則
  const id = new URLSearchParams(window.location.search).get('news')
  if (id) openItem({ _id: id })
}
watch(() => props.active, start)
onMounted(start)

const open = ref(false)
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
.nb-count { opacity: .7; font-size: .85em; }

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
  border: 1px solid var(--sf-border); background: var(--sf-panel); color: #fff; min-height: 0;
}
.nb-tile__img, .nb-tile__ph { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transition: transform .5s ease; }
.nb-tile__ph {
  display: flex; align-items: center; justify-content: center; font-size: 3rem; color: rgba(255, 255, 255, .18);
  background:
    radial-gradient(ellipse 80% 70% at 20% 10%, rgba(var(--sf-accent-rgb), .45), transparent 60%),
    radial-gradient(ellipse 70% 60% at 90% 90%, rgba(var(--sf-accent-2-rgb), .35), transparent 60%),
    var(--sf-panel);
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
  .nb-hero, .nb-hero--2, .nb-hero--3 { grid-template-rows: 13rem 9.5rem; gap: .6rem; }
  .nb-tile__title { font-size: var(--sf-fs-sm); }
}
</style>
