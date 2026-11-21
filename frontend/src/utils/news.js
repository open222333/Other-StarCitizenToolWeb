// 新聞（玩家頁「新聞」分頁 NewsBoard.vue、「艦長室」上方 NewsBanner.vue 共用）：抓資料與日期格式。
// 後端見 app/news/view.py（GET /news/、/news/tags、/news/<id>，公開）。

export async function fetchNews(fetcher, params = {}) {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== '' && v !== null && v !== undefined) sp.append(k, v)
  const res = await fetcher(`/news/?${sp.toString()}`)
  const body = res ? await res.json().catch(() => null) : null
  if (!res?.ok || !body?.success) return { ok: false, message: body?.message || '讀取新聞失敗' }
  return { ok: true, data: body.data || [], total: body.total || 0 }
}

export async function fetchNewsItem(fetcher, id) {
  const res = await fetcher(`/news/${encodeURIComponent(id)}`)
  const body = res ? await res.json().catch(() => null) : null
  return res?.ok && body?.success ? body.data : null
}

export async function fetchNewsTags(fetcher) {
  const res = await fetcher('/news/tags')
  const body = res ? await res.json().catch(() => null) : null
  return res?.ok && body?.success ? body.data || [] : []
}

/** ISO → 「2026-11-20 16:00」（瀏覽器時區） */
export function fmtNewsDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const p = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
