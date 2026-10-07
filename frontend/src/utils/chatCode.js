// 玩家頁「中文轉碼」：遊戲聊天用的 中文 ↔ @xxx 代碼互轉。
//
// 移植自 Other-Game/StarCitizen/tctp_translator/main.py（邏輯保持一致）：
//   - 字典是社群 chsc-tw 的 textinput.txt，一行一組「代碼=中文字」（代碼本身不含 @），
//     由後端 GET /player/chat-code/dictionary 提供（伺服器快取，見 src/models/chat_code.py）
//   - 輸入有中文 → 逐字轉成 @代碼，前面加「[zh] 」；ASCII 原樣保留；字典沒有的字原樣保留並列出
//   - 輸入有 @xxx → 每個 @ 後面用「最長的代碼優先」比對換回中文；對不到的 @xxx 原樣保留並列出
//   - 輸入開頭的 [zh]／[en] 之類語言前綴、首尾引號會先拿掉

/** 解析字典原文 → { keyToChar, charToKeys, keyLengths, entries } */
export function parseDictionary(text) {
  const keyToChar = new Map()
  const charToKeys = new Map()
  for (const raw of (text || '').replace(/^﻿/, '').split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith('#') || line.startsWith(';')) continue
    const idx = line.indexOf('=')
    if (idx < 0) continue
    const key = line.slice(0, idx).trim().replace(/^@+/, '')
    const value = line.slice(idx + 1).trim()
    if (!key || !value) continue
    keyToChar.set(key, value)
    if (!charToKeys.has(value)) charToKeys.set(value, [])
    charToKeys.get(value).push(key)
  }
  const keyLengths = [...new Set([...keyToChar.keys()].map(k => k.length))].sort((a, b) => b - a)
  return { keyToChar, charToKeys, keyLengths, entries: keyToChar.size }
}

export function cleanInput(text) {
  return (text || '').trim()
    .replace(/^\[[A-Za-z]{2,5}\]\s*/, '')
    .replace(/^["']+|["']+$/g, '')
    .trim()
}

const CHINESE = /[㐀-䶿一-鿿]/
const CODE = /@[A-Za-z0-9]+/

/** 'chinese' | 'code' | 'empty' | 'unknown' */
export function detectType(text) {
  const cleaned = cleanInput(text)
  if (!cleaned) return 'empty'
  if (CHINESE.test(cleaned)) return 'chinese'
  if (CODE.test(cleaned)) return 'code'
  return 'unknown'
}

// 用 Array.from 逐「字」走，才不會把罕用字（surrogate pair）拆成兩半
export function chineseToCode(text, dict) {
  const out = []
  const unknown = []
  for (const ch of Array.from(text)) {
    const keys = dict.charToKeys.get(ch)
    if (keys) out.push('@' + keys[0])
    else {
      out.push(ch)
      // ASCII（英數、空白、半形標點）原樣保留，不算找不到
      if (ch.charCodeAt(0) > 0x7f && !unknown.includes(ch)) unknown.push(ch)
    }
  }
  return { result: out.join(''), unknown }
}

export function codeToChinese(text, dict) {
  const src = cleanInput(text)
  const out = []
  const unknown = []
  let i = 0
  while (i < src.length) {
    if (src[i] !== '@') {
      out.push(src[i])
      i += 1
      continue
    }
    let found = false
    for (const len of dict.keyLengths) {
      const candidate = src.slice(i + 1, i + 1 + len)
      if (candidate.length === len && dict.keyToChar.has(candidate)) {
        out.push(dict.keyToChar.get(candidate))
        i += 1 + len
        found = true
        break
      }
    }
    if (found) continue
    const m = src.slice(i).match(/^@[A-Za-z0-9]+/)
    if (m) {
      out.push(m[0])
      if (!unknown.includes(m[0])) unknown.push(m[0])
      i += m[0].length
    } else {
      out.push('@')
      i += 1
    }
  }
  return { result: out.join(''), unknown }
}

/**
 * 轉換 → { type, output, unknown }（type 是 empty／unknown 時 output 為空）
 * mode：'auto'（依內容判斷）／'chinese'（強制中文 → 代碼）／'code'（強制代碼 → 中文）
 */
export function autoTranslate(text, dict, mode = 'auto') {
  if (!cleanInput(text)) return { type: 'empty', output: '', unknown: [] }
  const type = mode === 'chinese' || mode === 'code' ? mode : detectType(text)
  if (type === 'chinese') {
    const { result, unknown } = chineseToCode(cleanInput(text), dict)
    return { type, output: '[zh] ' + result, unknown }
  }
  if (type === 'code') {
    const { result, unknown } = codeToChinese(text, dict)
    return { type, output: result, unknown }
  }
  return { type, output: '', unknown: [] }
}
