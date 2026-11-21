// 新聞內文的 Markdown → HTML（NewsArticle.vue 用 v-html 顯示）。
//
// ⚠️ 安全：內文可能來自外部程式（API 金鑰寫入），一律先把整段 HTML 跳脫，再把認得的 Markdown 換成標籤；
// 連結、圖片只接受 http/https（javascript: 之類的直接當文字），連結一律另開分頁加 noopener。
// 支援：段落、換行、# 標題、- / 1. 清單、> 引言、``` 程式碼區塊、`行內程式碼`、**粗體**、*斜體*、~~刪除線~~、
// [文字](網址)、![說明](圖片網址)、裸網址自動變連結、--- 分隔線。不支援 HTML、表格。

const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
const safeUrl = u => (/^https?:\/\/[^\s"'<>]+$/i.test(u) ? u : '')

function inline(text) {
  // 先把行內程式碼抽出來，裡面不再處理其他標記
  const codes = []
  let t = text.replace(/`([^`]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000` })
  t = t.replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (m, alt, url) => {
    const u = safeUrl(url)
    return u ? `<img src="${u}" alt="${alt}" loading="lazy">` : m
  })
  t = t.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, url) => {
    const u = safeUrl(url)
    return u ? `<a href="${u}" target="_blank" rel="noopener noreferrer">${label}</a>` : m
  })
  // 裸網址（不在已經做好的標籤屬性裡）
  t = t.replace(/(^|[\s(（])(https?:\/\/[^\s<>"')）]+)/g, (_, pre, url) =>
    `${pre}<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`)
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>').replace(/__([^_]+)__/g, '<strong>$1</strong>')
  t = t.replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>').replace(/(^|[\s(])_([^_\s][^_]*)_/g, '$1<em>$2</em>')
  t = t.replace(/~~([^~]+)~~/g, '<del>$1</del>')
  return t.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codes[Number(i)]}</code>`)
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
