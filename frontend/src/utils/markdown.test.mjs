import assert from 'node:assert/strict'
import { renderMarkdown as md } from './markdown.js'

assert.equal(md('**粗** 與 *斜*'), '<p><strong>粗</strong> 與 <em>斜</em></p>')
assert.equal(md('# 標題'), '<h3>標題</h3>')
assert.equal(md('- a\n- b'), '<ul><li>a</li><li>b</li></ul>')
assert.equal(md('1. a\n2. b'), '<ol><li>a</li><li>b</li></ol>')
assert.equal(md('一行\n兩行'), '<p>一行<br>兩行</p>')
assert.match(md('[RSI](https://robertsspaceindustries.com)'), /<a href="https:\/\/robertsspaceindustries.com" target="_blank" rel="noopener noreferrer">RSI<\/a>/)
// 安全：HTML 被跳脫、javascript: 連結不做成連結
assert.equal(md('<script>alert(1)</script>'), '<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>')
assert.ok(!md('[x](javascript:alert(1))').includes('<a '))
assert.ok(!md('![x](javascript:alert(1))').includes('<img'))
assert.ok(!md('<img src=x onerror=alert(1)>').includes('<img'))
assert.equal(md('`<b>`'), '<p><code>&lt;b&gt;</code></p>')
assert.match(md('看 https://example.com 這裡'), /<a href="https:\/\/example.com"/)
assert.equal(md('```\n<a>\n```'), '<pre><code>&lt;a&gt;</code></pre>')
assert.equal(md('> 引言'), '<blockquote>引言</blockquote>')
// 安全：圖片說明／連結文字裡的裸網址不能再被轉成標籤（以前會把 alt 提前關掉、多出 onerror 屬性）
const evil = md('![a https://x/onerror=alert(1)](https://example.com/none.png)')
assert.ok(!/onerror\s*=/.test(evil.replace(/alt="[^"]*"/g, '')), evil)
assert.equal((evil.match(/<img /g) || []).length, 1)
assert.match(evil, /^<p><img src="https:\/\/example.com\/none.png" alt="a https:\/\/x\/onerror=alert\(1\)" loading="lazy"><\/p>$/)
assert.ok(!md('[看 https://x.com/"onclick=1](https://example.com)').includes('onclick=1"'))
assert.match(md('[**粗**](https://example.com)'), /<a [^>]+><strong>粗<\/strong><\/a>/)
console.log('markdown ok')
