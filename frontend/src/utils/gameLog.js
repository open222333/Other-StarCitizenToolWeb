// 玩家頁「LOG 解析」：把星際公民的 Game.log 整理成中文事件與本次遊玩回顧。
//
// 移植自 Other-Game/StarCitizen/gamelog_reader/main.py（規則與輸出文字保持一致）：
//   - 哪些 log 要顯示、講成什麼中文，寫在 gameLogRules.json（原 log_rules.json，格式說明在檔內「_說明」）
//   - 「交易」這種要算金額的交給程式內建的 sayTrade
//   - 時間一律轉成台灣時間（UTC+8），用「晚上 9:05」這種說法
// 解析完全在玩家的瀏覽器裡做，Game.log 不會上傳到伺服器。

import RULES_CONFIG from './gameLogRules.json'

const TW_OFFSET_MS = 8 * 3600 * 1000
const RAW_PREVIEW_LEN = 100
const MULTILINE_MAX = 5

const TIMESTAMP = /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)Z?/
const TRADE_ACTION = /(buy|bought|purchas|sell|sold|sale)/i
const TRADE_AMOUNT = [/([\d,]+(?:\.\d+)?)\s*a?UEC\b/i, /\ba?UEC\s*[:=[]\s*([\d,]+(?:\.\d+)?)/i]
const SCU = /([\d,]+(?:\.\d+)?)\s*SCU\b/i
const LINE_PREFIX = /^<[^>]*>\s*/
const OPTIONAL_SEGMENT = /〔([^〔〕]*)〕/g
const PLACEHOLDER = /\{([^{}]+)\}/g

const escapeRe = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

// ── 小工具 ───────────────────────────────────────────────────────────

/** 取欄位值，支援 name=值、name: 值、name[值]（SC 很常用最後一種，例如 shard[...]） */
function field(line, ...names) {
  for (const name of names) {
    const m = line.match(new RegExp(`\\b${escapeRe(name)}\\s*(?:[:=]\\s*["']?|\\[)([^\\]\\s,"'}]+)`, 'i'))
    if (m) return m[1]
  }
  return null
}

function toNumber(text) {
  if (!text) return null
  const n = Number(String(text).replace(/,/g, ''))
  return Number.isFinite(n) ? n : null
}

export const fmtMoney = v => (Number.isInteger(v) ? v.toLocaleString('en-US')
  : v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
const fmtNum = v => (Number.isInteger(v) ? String(v) : String(Number(v.toPrecision(6))))

// 船廠代碼 → 名稱（跟遊戲裡頻道名稱的寫法一致，例如「Anvil Asgard」）
const MANUFACTURERS = {
  AEGS: 'Aegis', ANVL: 'Anvil', ARGO: 'Argo', BANU: 'Banu', CNOU: 'C.O.',
  CRUS: 'Crusader', DRAK: 'Drake', ESPR: 'Esperia', GAMA: 'Gatac', GRIN: 'Greycat',
  KRIG: 'Kruger', MISC: 'MISC', MRAI: 'Mirai', ORIG: 'Origin', RSI: 'RSI',
  TMBL: 'Tumbril', VNCL: 'Vanduul', XIAN: 'Aopoa', XNAA: 'Aopoa',
}

/** DRAK_Cutlass_Black_01 → Drake Cutlass Black */
export function prettyName(raw) {
  let parts = raw.split('_')
  const head = parts[0]
  if (parts.length > 1 && /[A-Z]/.test(head) && head === head.toUpperCase() && head.length <= 5) {
    const maker = MANUFACTURERS[head]
    parts = (maker ? [maker] : []).concat(parts.slice(1))
  }
  while (parts.length && /^\d+$/.test(parts[parts.length - 1])) parts = parts.slice(0, -1)
  return parts.join(' ') || raw
}

const raw = line => line.slice(0, RAW_PREVIEW_LEN)

/** 台灣時間的各欄位（when 是 Date，UTC） */
function tw(when) {
  const d = new Date(when.getTime() + TW_OFFSET_MS)
  return { y: d.getUTCFullYear(), mo: d.getUTCMonth() + 1, d: d.getUTCDate(), h: d.getUTCHours(), mi: d.getUTCMinutes() }
}

/** 2026-10-05 21:05 → 晚上 9:05 */
export function casualTime(when) {
  if (!when) return '某個時間'
  const { h, mi } = tw(when)
  const period = h < 5 ? '凌晨' : h < 11 ? '早上' : h < 13 ? '中午' : h < 18 ? '下午' : '晚上'
  return `${period} ${h % 12 || 12}:${String(mi).padStart(2, '0')}`
}

/** 10/5（台灣時間的日期） */
export function casualDate(when) {
  if (!when) return ''
  const { mo, d } = tw(when)
  return `${mo}/${d}`
}

function casualDuration(ms) {
  const total = Math.floor(ms / 60000)
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h && m) return `${h} 小時 ${m} 分鐘`
  if (h) return `${h} 小時`
  return `${Math.max(m, 1)} 分鐘`
}

export function parseTime(line) {
  const m = line.match(TIMESTAMP)
  if (!m) return null
  const [base, frac = ''] = m[1].split('.')
  const t = Date.parse(`${base}${frac ? '.' + frac.slice(0, 3).padEnd(3, '0') : ''}Z`)
  return Number.isNaN(t) ? null : new Date(t)
}

// ── 需要程式處理的事件 ───────────────────────────────────────────────

/** 商品買賣：盡量抓方向、商品、數量、金額；抓不到的不講，完全看不懂才附原文，不亂編數字 */
function sayTrade(line) {
  const action = line.match(TRADE_ACTION)
  const word = action ? action[1].toLowerCase() : ''
  const side = ['sell', 'sold', 'sale'].includes(word) ? 'sell' : word ? 'buy' : null

  const itemRaw = field(line, 'commodity_name', 'commodity', 'item', 'product', 'goods', 'resource')
  const item = itemRaw ? prettyName(itemRaw) : null

  let qty = toNumber(field(line, 'quantity', 'qty', 'count'))
  if (qty === null) {
    const s = line.match(SCU)
    qty = s ? toNumber(s[1]) : null
  }
  let money = toNumber(field(line, 'price', 'amount', 'total', 'cost', 'value'))
  if (money === null) {
    for (const p of TRADE_AMOUNT) {
      const m = line.match(p)
      if (m) { money = toNumber(m[1]); break }
    }
  }
  // shopName[SCShop_Levski_CargoOffice_Commodities] → 地點 Levski
  const shop = field(line, 'shopName')
  const shopParts = shop ? shop.split('_') : []
  const place = shopParts.length > 2 && shopParts[0].toLowerCase() === 'scshop' ? shopParts[1] : null
  const where = place ? `在 ${place} ` : ''

  const data = { side, item, qty, money }
  if (place) data.location = place

  if (!(item || qty || money)) {
    const verb = side === 'sell' ? '賣東西' : side === 'buy' ? '買東西' : '交易'
    return [`好像有一筆${verb}，但看不出細節（原文：${raw(line)}）`, data]
  }
  const goods = qty && item ? `${fmtNum(qty)} SCU 的 ${item}` : (item || `${fmtNum(qty)} SCU 的貨`)
  if (side === 'sell') return [`你${where}賣掉了 ${goods}${money ? `，入帳 ${fmtMoney(money)} aUEC 💸` : ''}`, data]
  if (side === 'buy') return [`${money ? `你${where}花了 ${fmtMoney(money)} aUEC 買了 ` : `你${where}買了 `}${goods}`, data]
  return [`一筆跟 ${goods} 有關的交易`, data]
}

const HANDLERS = { 交易: sayTrade }

// ── 規則 ────────────────────────────────────────────────────────────

function compile(spec, where) {
  if (!spec || !('正則' in spec)) return spec
  try {
    return { ...spec, _re: new RegExp(spec['正則'], 'i') }
  } catch (e) {
    throw new Error(`${where}的正則寫錯了：${spec['正則']}（${e.message}）`)
  }
}

function groupMatches(line, group) {
  if (!group) return true
  const ic = group['不分大小寫']
  const text = ic ? line.toLowerCase() : line
  for (const word of group['包含任一'] || []) {
    if (text.includes(ic ? word.toLowerCase() : word)) return true
  }
  return !!(group._re && group._re.test(line))
}

function extract(line, spec) {
  let value = spec['來源'] ? field(line, ...spec['來源']) : null
  if (value === null && spec._re) {
    const m = line.match(spec._re)
    if (m) value = m.length > 1 ? m[1] : m[0]
  }
  if (value === null || value === undefined) return spec['預設'] ?? null
  value = value.trim()
  for (const [key, name] of Object.entries(spec['對照'] || {})) {
    if (value.toLowerCase().includes(key.toLowerCase())) return name
  }
  if (spec['數字']) {
    const n = toNumber(value)
    return n !== null ? fmtNum(n) : value
  }
  if (spec['美化']) return prettyName(value)
  return value
}

function render(template, values, specs) {
  const show = (name) => {
    const spec = specs[name] || {}
    const v = values[name]
    if (v === null || v === undefined) return spec['沒抓到顯示'] || ''
    return (spec['格式'] || '{}').replace('{}', String(v))
  }
  const text = template.replace(OPTIONAL_SEGMENT, (_, seg) => {
    const names = [...seg.matchAll(PLACEHOLDER)].map(m => m[1])
    return names.every(n => values[n] !== null && values[n] !== undefined)
      ? seg.replace(PLACEHOLDER, (__, n) => show(n)) : ''
  })
  return text.replace(PLACEHOLDER, (_, n) => show(n))
}

function fillData(template, values) {
  const data = {}
  for (const [key, value] of Object.entries(template || {})) {
    const m = typeof value === 'string' ? value.match(/^\{([^{}]+)\}$/) : null
    if (!m) data[key] = value
    else if (values[m[1]] !== null && values[m[1]] !== undefined) data[key] = values[m[1]]
  }
  return data
}

class EventRule {
  constructor(o) { Object.assign(this, o) }

  matches(line) {
    if (this.exclude && groupMatches(line, this.exclude)) return false
    return this.groups.every(g => groupMatches(line, g))
  }

  /** [句子, 資料, 圖示]；沒有一句適用回 null */
  describe(line) {
    if (this.handler) {
      const d = this.handler(line)
      return d ? [...d, this.icon] : null
    }
    const values = {}
    for (const [name, spec] of Object.entries(this.fields)) values[name] = extract(line, spec)
    for (const s of this.sentences) {
      if (!groupMatches(line, s['條件'])) continue
      if ((s['需要欄位'] || []).some(n => values[n] === null || values[n] === undefined)) continue
      return [render(s['文字'], values, this.fields), fillData(s['資料'], values), s['圖示'] || this.icon]
    }
    return null
  }
}

/** 讀規則設定 → { rules, ignore, multiline }。格式有錯丟 Error（中文訊息） */
export function loadRules(config = RULES_CONFIG) {
  const rules = (config['規則'] || []).map((r, i) => {
    const name = `規則「${r['名稱'] || `第 ${i + 1} 條`}」`
    for (const k of ['分類', '圖示']) if (!r[k]) throw new Error(`${name}少了「${k}」`)
    if (!r['符合']?.length) throw new Error(`${name}沒寫「符合」條件`)
    let handler = null
    if (r['處理器']) {
      handler = HANDLERS[r['處理器']]
      if (!handler) throw new Error(`${name}的處理器「${r['處理器']}」不存在`)
    } else if (!r['句子']) throw new Error(`${name}沒寫「句子」也沒寫「處理器」`)
    return new EventRule({
      category: r['分類'],
      icon: r['圖示'],
      groups: r['符合'].map(g => compile(g, name)),
      exclude: compile(r['排除'], name),
      fields: Object.fromEntries(Object.entries(r['欄位'] || {}).map(([n, s]) => [n, compile(s, `${name}的欄位「${n}」`)])),
      sentences: (r['句子'] || []).map(s => ({ ...s, 條件: compile(s['條件'], name) })),
      handler,
    })
  })
  const multiline = (config['多行合併'] || []).map(s => [new RegExp(s['開頭']), new RegExp(s['結束'])])
  return { rules, ignore: config['略過'] || [], multiline }
}

// ── 解析器 ──────────────────────────────────────────────────────────

const sameData = (a, b) => JSON.stringify(a) === JSON.stringify(b)

export class GameLogParser {
  constructor({ rules, ignore, multiline } = loadRules()) {
    this.rules = rules
    this.ignore = ignore
    this.multiline = multiline
    this.reset()
  }

  reset() {
    this.events = []
    this.pending = null   // [已合併的文字, 結束正則, 已合併行數]
  }

  /** 同一件事 1 秒內寫好幾行（例如陣亡時每件裝備一行）只算一次；交易不合併，免得少算錢 */
  isRepeat(ev) {
    const last = this.events[this.events.length - 1]
    if (!last || ev.category === 'trade') return false
    if (last.text !== ev.text || !sameData(last.data, ev.data) || !(last.when && ev.when)) return false
    return Math.abs(ev.when - last.when) <= 1000
  }

  /** 一則訊息斷成好幾行的（例如遊戲通知），照「多行合併」接回一行；還沒接完回 null */
  joinMultiline(line) {
    if (this.pending) {
      const [text0, end, count] = this.pending
      const text = `${text0} ${line.replace(LINE_PREFIX, '')}`
      if (end.test(text) || count + 1 >= MULTILINE_MAX) {
        this.pending = null
        return text
      }
      this.pending = [text, end, count + 1]
      return null
    }
    for (const [start, end] of this.multiline) {
      if (start.test(line) && !end.test(line)) {
        this.pending = [line, end, 1]
        return null
      }
    }
    return line
  }

  /** 解析一行，認得就回事件（也會加進 this.events），不認得回 null */
  parseLine(input) {
    let line = input.trim()
    if (!line) return null
    line = this.joinMultiline(line)
    if (!line || this.ignore.some(k => line.includes(k))) return null
    for (const rule of this.rules) {
      if (!rule.matches(line)) continue
      const d = rule.describe(line)
      if (!d) continue
      const [text, data, icon] = d
      const ev = { category: rule.category, icon, when: parseTime(line), text, data }
      if (this.isRepeat(ev)) return null
      this.events.push(ev)
      return ev
    }
    return null
  }

  /** 解析整份文字；每 CHUNK 行讓出一次主執行緒，大檔不會卡住畫面 */
  async parseText(text, onProgress) {
    const lines = text.split(/\r?\n/)
    const CHUNK = 4000
    for (let i = 0; i < lines.length; i += 1) {
      this.parseLine(lines[i])
      if (i % CHUNK === CHUNK - 1) {
        onProgress?.(i / lines.length)
        await new Promise(r => setTimeout(r))
      }
    }
    onProgress?.(1)
  }
}

// ── 回顧 ────────────────────────────────────────────────────────────

/** 照時間排好，連續重複的同一句合併：[{ ev, count }] */
export function timeline(events) {
  const merged = []
  for (const ev of events) {
    const last = merged[merged.length - 1]
    if (last && last.ev.text === ev.text) last.count += 1
    else merged.push({ ev, count: 1 })
  }
  return merged
}

const uniq = arr => [...new Set(arr)]

export function summaryLines(events) {
  const lines = []
  const times = events.map(e => e.when).filter(Boolean)
  if (times.length >= 2) {
    const start = new Date(Math.min(...times))
    const end = new Date(Math.max(...times))
    lines.push(`這趟大約玩了 ${casualDuration(end - start)}（${casualTime(start)} 到 ${casualTime(end)}）。`)
  }

  const shards = uniq(events.map(e => e.data.shard).filter(Boolean))
  if (shards.length === 1) lines.push(`全程都待在 Shard「${shards[0]}」。`)
  else if (shards.length) lines.push(`換過 ${shards.length} 個 Shard：${shards.join('、')}。`)

  const places = uniq(events.map(e => e.data.location).filter(Boolean).map(prettyName))
  if (places.length) {
    lines.push(`去過 ${places.length} 個地方：${places.slice(0, 5).join('、')}${places.length > 5 ? '…等地' : ''}。`)
  }

  const trades = events.filter(e => e.category === 'trade').map(e => e.data)
  if (trades.length) {
    const buys = trades.filter(t => t.side === 'buy')
    const sells = trades.filter(t => t.side === 'sell')
    const spent = buys.reduce((n, t) => n + (t.money || 0), 0)
    const earned = sells.reduce((n, t) => n + (t.money || 0), 0)
    let s = `交易方面：買了 ${buys.length} 次、賣了 ${sells.length} 次`
    if (spent || earned) {
      const net = earned - spent
      const mood = net > 0 ? '賺了' : net < 0 ? '虧了' : '打平'
      s += `，花掉 ${fmtMoney(spent)}、收入 ${fmtMoney(earned)} aUEC，算起來${mood}${net ? ` ${fmtMoney(Math.abs(net))} aUEC` : ''}`
    }
    const unknownPrice = trades.filter(t => t.money === null || t.money === undefined).length
    if (unknownPrice) s += `（其中 ${unknownPrice} 筆看不出金額，沒算進去）`
    lines.push(s + '。')
  }

  // 同一件事常連續寫好幾行，統計前先合併
  const runs = timeline(events).map(r => r.ev)
  const spawned = runs.filter(e => e.data.vehicle === 'spawned').length
  const destroyed = runs.filter(e => e.data.vehicle === 'destroyed').length
  const ships = uniq(events.map(e => e.data.ship).filter(Boolean))
  if (spawned || destroyed || ships.length) {
    let s = spawned ? `叫了 ${spawned} 次船` : '開過船'
    if (ships.length) s += `（${ships.slice(0, 3).join('、')}）`
    s += destroyed ? `，被打爆 ${destroyed} 次。` : '，一次都沒被打爆 👍'
    lines.push(s)
  }

  const jumps = runs.filter(e => e.data.quantum === 'arrived').length
  if (jumps) lines.push(`量子航行了 ${jumps} 趟。`)

  const downs = runs.filter(e => e.data.health === 'down').length
  const deaths = runs.filter(e => e.data.health === 'dead').length
  if (downs || deaths) {
    lines.push([downs ? `倒地 ${downs} 次` : '', deaths ? `陣亡 ${deaths} 次` : ''].filter(Boolean).join('、') + '，辛苦了 🫡')
  }

  const join = runs.filter(e => e.data.party === 'join').length
  const leave = runs.filter(e => e.data.party === 'leave').length
  if (join || leave) lines.push(`小隊有 ${join} 次有人加入、${leave} 次有人離開。`)

  return lines
}

/** 分類代碼 → 中文（篩選用） */
export const CATEGORY_LABELS = {
  login: '登入／Shard', trade: '交易', health: '倒地／陣亡', combat: '擊殺', vehicle: '船艦',
  location: '地點', quantum: '量子航行', party: '小隊',
}
