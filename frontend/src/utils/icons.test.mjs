// 圖示子集有沒有涵蓋程式碼用到的圖示（npm run icons 產生，見 frontend/scripts/subset-icons.py）：node src/utils/icons.test.mjs
import assert from 'node:assert/strict'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const src = join(dirname(fileURLToPath(import.meta.url)), '..')
const all = JSON.parse(readFileSync(join(src, '../node_modules/bootstrap-icons/font/bootstrap-icons.json'), 'utf8'))
const css = readFileSync(join(src, 'assets/icons/bootstrap-icons-subset.css'), 'utf8')
const have = new Set([...css.matchAll(/\.bi-([a-z0-9-]+)::before/g)].map(m => m[1]))
const used = new Set()
function scan(dir) {
  for (const f of readdirSync(dir)) {
    const p = join(dir, f)
    if (statSync(p).isDirectory()) { if (!p.endsWith('assets/icons')) scan(p); continue }
    if (!/\.(vue|js|mjs)$/.test(f)) continue
    for (const m of readFileSync(p, 'utf8').matchAll(/\bbi-([a-z0-9]+(?:-[a-z0-9]+)*)/g)) if (m[1] in all) used.add(m[1])
  }
}
scan(src)
const missing = [...used].filter(n => !have.has(n))
assert.deepEqual(missing, [], `圖示子集少了 ${missing.join(', ')}：請跑 npm run icons`)
console.log(`icons ok（${used.size} 個）`)
