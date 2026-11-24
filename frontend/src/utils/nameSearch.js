// 前端自己篩的列表用的名稱搜尋規則，跟後端 src/models/name_search.py 同一套：
//   1. 關鍵字用空白分開，每個都要符合（順序不拘）：「gamma ll」「ll gamma」都找得到 Gamma LL
//   2. 英文只比「字首」（以空白／標點／底線分字），中文任何位置都算；關鍵字前後的標點去掉
//   3. 用上面的規則一筆都沒有，才退回「整串關鍵字在任意位置」
const CJK = /[㐀-鿿豈-﫿]/
const EDGE_PUNCT = /^[^\w㐀-鿿]+|[^\w㐀-鿿]+$/g
const NON_WORD = /[^0-9a-z㐀-鿿]+/
const MAX_TOKENS = 6

export function nameTokens(query) {
  const out = []
  for (const raw of String(query || '').toLowerCase().split(/\s+/)) {
    const t = raw.replace(EDGE_PUNCT, '')
    if (t && !out.includes(t)) out.push(t)
  }
  return out.slice(0, MAX_TOKENS)
}

const words = s => String(s || '').toLowerCase().split(NON_WORD).filter(Boolean)

/** 嚴格規則：每個關鍵字都要對到某個欄位的字首（中文任意位置） */
export function matchStrict(fields, toks) {
  const texts = fields.map(x => String(x || '').toLowerCase()).filter(Boolean)
  const ws = texts.flatMap(words)
  return toks.every(t => (CJK.test(t) ? texts.some(x => x.includes(t)) : ws.some(w => w.startsWith(t))))
}

/** 放寬規則：整串關鍵字在任一欄位的任意位置（不分大小寫） */
export function matchLoose(fields, query) {
  const q = String(query || '').trim().toLowerCase()
  return !q || fields.some(x => String(x || '').toLowerCase().includes(q))
}

/**
 * 篩選列表：fieldsOf(row) 回傳要比對的欄位陣列。沒有關鍵字原樣回傳。
 * 回傳 { rows, match }：match ''＝沒關鍵字、'strict'、'loose'（嚴格找不到才放寬）
 */
export function filterByName(list, query, fieldsOf) {
  const q = String(query || '').trim()
  if (!q) return { rows: list, match: '' }
  const toks = nameTokens(q)
  if (toks.length) {
    const rows = list.filter(r => matchStrict(fieldsOf(r), toks))
    if (rows.length) return { rows, match: 'strict' }
  }
  return { rows: list.filter(r => matchLoose(fieldsOf(r), q)), match: 'loose' }
}
