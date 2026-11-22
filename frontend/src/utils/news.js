// 新聞（玩家頁「新聞」分頁 NewsBoard.vue、「艦長室」上方 NewsBanner.vue 共用）：抓資料與日期格式。
// 後端見 app/news/view.py（GET /news/、/news/tags、/news/<id>，公開）。
import { getJson } from '@/utils/getJson'

/** params：tag、q、pinned、limit、offset（玩家頁一律依發布時間新到舊） */
export async function fetchNews(fetcher, params = {}) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== '' && v !== null && v !== undefined) sp.append(k, v)
  const r = await getJson(fetcher, `/news/?${sp.toString()}`, undefined, '讀取新聞失敗')
  if (!r.ok) return { ok: false, message: r.message }
  return { ok: true, data: r.data || [], total: r.body.total || 0 }
}

/** 置頂區（官方優先、再置頂、再最新，最多 4 則；後端 GET /news/featured） */
export async function fetchNewsFeatured(fetcher, limit = 4) {
  const r = await getJson(fetcher, `/news/featured?limit=${limit}`, undefined, '讀取新聞失敗')
  return r.ok ? { ok: true, data: r.data || [] } : { ok: false, message: r.message }
}

export async function fetchNewsItem(fetcher, id) {
  const r = await getJson(fetcher, `/news/${encodeURIComponent(id)}`)
  return r.ok ? r.data : null
}

export async function fetchNewsTags(fetcher) {
  const r = await getJson(fetcher, '/news/tags')
  return r.ok ? r.data || [] : []
}

/** ISO → 「2026-11-20 16:00」（瀏覽器時區） */
export function fmtNewsDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 標籤顏色：依標籤文字固定挑一個色相（同一個標籤在篩選鈕、卡片徽章上同色）。
// 色相挑過、彼此分得開；不用連續的雜湊值，避免兩個標籤顏色只差一點點。
const TAG_HUES = [205, 160, 32, 280, 345, 95, 185, 50, 255, 15, 130, 310]
export function tagHue(tag) {
  let h = 0
  for (const ch of String(tag || '')) h = (h * 31 + ch.codePointAt(0)) >>> 0
  return TAG_HUES[h % TAG_HUES.length]
}
