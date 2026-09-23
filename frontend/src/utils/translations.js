// 遊戲文字翻譯（前端端）—— 跟後端同一個來源：資料庫 sc_translations，
// 透過公開的 GET /item/translations 查（見 app/item/view.py 的 lookup_translations）。
// 前端不再放任何翻譯對照表；要中文化的新地方，後端 src/sc_zh.py 加一個 domain，
// 這裡用 translate(domain, 英文) 取。
//
// 快取是整個 SPA 共用的 reactive 物件：查到之前 translate() 回 ''（畫面先顯示英文），
// 查回來後自動重新渲染。查不到的也記成 ''，不會重複查。
import { reactive } from 'vue'

const DOMAINS = ['location', 'item', 'vehicle', 'vehicle_role',
  'mining_resource', 'mining_deposit', 'blueprint_type']

const cache = reactive(Object.fromEntries(DOMAINS.map(d => [d, {}])))
const inflight = Object.fromEntries(DOMAINS.map(d => [d, new Set()]))
const loadedDomains = new Set()

// 跟後端 MAX_TRANSLATION_TEXTS 一致，一次請求最多幾段
const BATCH = 100

export function translate(domain, text) {
  if (!text) return ''
  return cache[domain]?.[text] || ''
}

/** 查一批英文的翻譯（已經查過或正在查的會跳過）。 */
export async function loadTranslations(domain, texts) {
  const table = cache[domain]
  if (!table) return
  const want = [...new Set((texts || []).map(t => (t || '').trim()).filter(Boolean))]
    .filter(t => !(t in table) && !inflight[domain].has(t))
  if (!want.length) return
  want.forEach(t => inflight[domain].add(t))
  try {
    for (let i = 0; i < want.length; i += BATCH) {
      const chunk = want.slice(i, i + BATCH)
      const params = new URLSearchParams({ domain })
      chunk.forEach(t => params.append('text', t))
      const data = await fetchJson(`/item/translations?${params.toString()}`)
      for (const t of chunk) table[t] = data?.[t] || ''
    }
  } finally {
    want.forEach(t => inflight[domain].delete(t))
  }
}

/** 遊戲已知的地點名稱（英文，已排序），順便把它們的翻譯放進快取。
 *  給地點下拉選單列出還沒有人登記過庫存的地點用。 */
let knownLocationsPromise = null
export function loadKnownLocations() {
  if (!knownLocationsPromise) {
    knownLocationsPromise = fetchJson('/item/translations?domain=location').then((data) => {
      if (!data) { knownLocationsPromise = null; return [] }
      for (const [en, zh] of Object.entries(data)) cache.location[en] = zh || ''
      return Object.keys(data).sort()
    })
  }
  return knownLocationsPromise
}

/** 一次載入整個小型 domain（目前只有 blueprint_type）。 */
export async function loadTranslationDomain(domain) {
  if (!cache[domain] || loadedDomains.has(domain)) return
  loadedDomains.add(domain)
  const data = await fetchJson(`/item/translations?domain=${encodeURIComponent(domain)}`)
  if (data) Object.assign(cache[domain], data)
  else loadedDomains.delete(domain)   // 失敗就下次再試
}

async function fetchJson(url) {
  try {
    const res = await fetch(url)
    if (!res.ok) return null
    const body = await res.json().catch(() => null)
    return body?.success ? (body.data || {}) : null
  } catch {
    return null
  }
}
