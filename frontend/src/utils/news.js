// 新聞（玩家頁「新聞」分頁 NewsBoard.vue、「艦長室」上方 NewsBanner.vue 共用）：抓資料與日期格式。
// 後端見 app/news/view.py（GET /news/、/news/tags、/news/<id>，公開）。
import { getJson } from '@/utils/getJson'

/** params：tag、q、pinned、limit、offset、sort（latest＝只依發布時間，跑馬燈用） */
export async function fetchNews(fetcher, params = {}) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== '' && v !== null && v !== undefined) sp.append(k, v)
  const r = await getJson(fetcher, `/news/?${sp.toString()}`, undefined, '讀取新聞失敗')
  if (!r.ok) return { ok: false, message: r.message }
  return { ok: true, data: r.data || [], total: r.body.total || 0 }
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
