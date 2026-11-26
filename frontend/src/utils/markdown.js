// 新聞內文的 Markdown → HTML（NewsArticle.vue 用 v-html 顯示）。
//
// ⚠️ 安全：內文可能來自外部程式（API 金鑰寫入），一律先把整段 HTML 跳脫，再把認得的 Markdown 換成標籤；
// 連結、圖片只接受 http/https（javascript: 之類的直接當文字），連結一律另開分頁加 noopener。
// 支援：段落、換行、# 標題、- / 1. 清單、> 引言、``` 程式碼區塊、`行內程式碼`、**粗體**、*斜體*、~~刪除線~~、
// [文字](網址)、![說明](圖片網址)、裸網址自動變連結、--- 分隔線、表格（GFM：| a | b | 下一行 |---|:---:|，可對齊）。不支援 HTML。

const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
const safeUrl = u => (/^https?:\/\/[^\s"'<>]+$/i.test(u) ? u : '')

const emph = t => t
  .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/__([^_]+)__/g, '<strong>$1</strong>')
  .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>').replace(/(^|[\s(])_([^_\s][^_]*)_/g, '$1<em>$2</em>')
  .replace(/~~([^~]+)~~/g, '<del>$1</del>')

function inline(text) {
  // 已經做好的標籤（行內程式碼、圖片、連結、裸網址）先換成佔位符，最後才放回：
  // 後面的步驟（裸網址轉連結、粗斜體）就碰不到標籤的屬性。以前圖片 alt 裡的裸網址會被換成 <a href="…">，
  // 引號把 alt 提前關掉、網址後段變成屬性（例如 onerror），見 markdown.test.mjs。
  const slots = []
  const hold = html => { slots.push(html); return `\u0000${slots.length - 1}\u0000` }
  let t = text.replace(/`([^`]+)`/g, (_, c) => hold(`<code>${c}</code>`))
  t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, url) => {
    const u = safeUrl(url)
    return u ? hold(`<img src="${u}" alt="${alt}" loading="lazy">`) : m
  })
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, url) => {
    const u = safeUrl(url)
    // 連結文字只做粗斜體，不再轉網址
    return u ? hold(`<a href="${u}" target="_blank" rel="noopener noreferrer">${emph(label)}</a>`) : m
  })
  t = t.replace(/(^|[\s(（])(https?:\/\/[^\s<>"')）\u0000]+)/g, (_, pre, url) =>
    `${pre}${hold(`<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`)}`)
  t = emph(t)
  return t.replace(/\u0000(\d+)\u0000/g, (_, i) => slots[Number(i)])
}

// 表格：一列拆成格子（前後的 | 可有可無，\| 是字面上的 |）
const cells = line => line.trim().replace(/^\|/, '').replace(/(^|[^\\])\|$/, '$1').split(/(?<!\\)\|/)
  .map(c => c.trim().replace(/\\\|/g, '|'))
// 分隔列：每格是 -（可前後加 : 表示對齊）；要有 | 或 :，才不會跟 --- 分隔線搞混
const isTableSep = line => /^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$/.test(line) && /[|:]/.test(line)
const ALIGN = { left: ' style="text-align:left"', center: ' style="text-align:center"', right: ' style="text-align:right"' }
function alignOf(sep) {
  const c = sep.trim()
  if (c.startsWith(':') && c.endsWith(':')) return ALIGN.center
  if (c.endsWith(':')) return ALIGN.right
  if (c.startsWith(':')) return ALIGN.left
  return ''
}

export function renderMarkdown(src) {
  const lines = esc(String(src || '').replace(/\r\n?/g, '\n')).split('\n')
  const out = []
  let para = []
  let list = null // { tag, items }
  let quote = []
  const flushPara = () => { if (para.length) { out.push(`<p>${para.map(inline).join('<br>')}</p>`); para = [] } }
  const flushList = () => { if (list) { out.push(`<${list.tag}>${list.items.map(i => `<li>${inline(i)}</li>`).join('')}</${list.tag}>`); list = null } }
  const flushQuote = () => { if (quote.length) { out.push(`<blockquote>${quote.map(inline).join('<br>')}</blockquote>`); quote = [] } }
  const flushAll = () => { flushPara(); flushList(); flushQuote() }
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    if (/^```/.test(line.trim())) {
      flushAll()
      const code = []
      i += 1
      while (i < lines.length && !/^```/.test(lines[i].trim())) { code.push(lines[i]); i += 1 }
      out.push(`<pre><code>${code.join('\n')}</code></pre>`)
      continue
    }
    if (!line.trim()) { flushAll(); continue }
    // 表格：這一行有 |、下一行是 |---|---| 分隔列
    if (line.includes('|') && i + 1 < lines.length && isTableSep(lines[i + 1])) {
      flushAll()
      const head = cells(line)
      const aligns = cells(lines[i + 1]).map(alignOf)
      const cols = head.length
      const row = (cs, tag) => `<tr>${Array.from({ length: cols }, (_, k) => `<${tag}${aligns[k] || ''}>${inline(cs[k] ?? '')}</${tag}>`).join('')}</tr>`
      const body = []
      i += 2
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) { body.push(row(cells(lines[i]), 'td')); i += 1 }
      i -= 1
      out.push(`<table><thead>${row(head, 'th')}</thead><tbody>${body.join('')}</tbody></table>`)
      continue
    }
    let m = line.match(/^(#{1,6})\s+(.*)$/)
    if (m) { flushAll(); const lv = Math.min(6, m[1].length + 2); out.push(`<h${lv}>${inline(m[2])}</h${lv}>`); continue }
    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { flushAll(); out.push('<hr>'); continue }
    m = line.match(/^&gt;\s?(.*)$/)
    if (m) { flushPara(); flushList(); quote.push(m[1]); continue }
    m = line.match(/^\s*[-*+]\s+(.*)$/)
    if (m) { flushPara(); flushQuote(); if (!list || list.tag !== 'ul') { flushList(); list = { tag: 'ul', items: [] } } list.items.push(m[1]); continue }
    m = line.match(/^\s*\d+[.)]\s+(.*)$/)
    if (m) { flushPara(); flushQuote(); if (!list || list.tag !== 'ol') { flushList(); list = { tag: 'ol', items: [] } } list.items.push(m[1]); continue }
    flushList(); flushQuote()
    para.push(line)
  }
  flushAll()
  return out.join('\n')
}
