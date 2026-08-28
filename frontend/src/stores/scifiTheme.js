/**
 * 玩家端（公開站）的配色設定。
 *
 * 跟後台的 stores/theme.js 是**兩套獨立系統**，刻意不共用：
 *   - 後台 theme.js 管的是 sidebar/navbar 的 --sb-* / --nb-* 與內容區背景，
 *     而且有淺色模式。
 *   - 這裡管的是 assets/scifi-theme.css 的 --sf-* 變數，只有深色（科幻 HUD
 *     風格本來就不適合淺色底）。
 *
 * 作法：把使用者選的值寫進 document.documentElement 的 inline style，
 * 覆蓋 scifi-theme.css 裡 :root 的預設值（inline style 權重永遠更高）。
 * 每位使用者存自己的 localStorage，不進伺服器。
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const LS_ACCENT = 'sc_player_accent'
const LS_BG = 'sc_player_bg'
const LS_DENSITY = 'sc_player_density'

/** 強調色。名稱走星際公民的語感，不用「藍色／綠色」這種純顏色名。 */
export const ACCENTS = [
  { id: 'bridge', name: '艦橋藍', accent: '#3ea6ff', accent2: '#ff8a3d' },
  { id: 'alert', name: '警示橘', accent: '#ff8a3d', accent2: '#3ea6ff' },
  { id: 'quantum', name: '量子綠', accent: '#34d399', accent2: '#fbbf24' },
  { id: 'ion', name: '離子紫', accent: '#a78bfa', accent2: '#22d3ee' },
  { id: 'redalert', name: '赤色警戒', accent: '#f87171', accent2: '#fbbf24' },
  { id: 'amber', name: '琥珀', accent: '#fbbf24', accent2: '#3ea6ff' },
  { id: 'ice', name: '冰藍', accent: '#22d3ee', accent2: '#a78bfa' },
]

/**
 * 深色主題共用的「表面微調」—— 用疊一層半透明白來做輸入框底、hover 底、chip 底。
 */
const DARK_SURFACE = {
  inputBg: 'rgba(255, 255, 255, .03)',
  inputBgFocus: 'rgba(255, 255, 255, .05)',
  inputBgOff: 'rgba(255, 255, 255, .015)',
  hoverBg: 'rgba(255, 255, 255, .04)',
  chipBg: 'rgba(255, 255, 255, .08)',
  headerBg: 'rgba(255, 255, 255, .02)',
  inset: 'rgba(255, 255, 255, .02)',
  shadow: 'rgba(0, 0, 0, .55)',
  textStrong: '#ffffff',
}

/**
 * 亮色主題的表面微調。
 *
 * 關鍵差異：亮底**不能**用「疊半透明白」—— 白底疊白等於沒變，輸入框、
 * hover、chip 就全部消失。所以改成疊半透明的深藍黑，並把陰影調淡
 * （亮底上的重陰影看起來很髒）。
 */
const LIGHT_SURFACE = {
  inputBg: 'rgba(16, 28, 46, .035)',
  inputBgFocus: 'rgba(16, 28, 46, .06)',
  inputBgOff: 'rgba(16, 28, 46, .07)',
  hoverBg: 'rgba(16, 28, 46, .05)',
  chipBg: 'rgba(16, 28, 46, .09)',
  headerBg: 'rgba(16, 28, 46, .03)',
  inset: 'rgba(255, 255, 255, .8)',
  shadow: 'rgba(16, 28, 46, .12)',
  textStrong: '#0b1420',
}

/**
 * 底色。每組都帶完整的文字／邊框 token —— 因為亮底必須把文字整組翻成深色，
 * 只換背景會讓 --sf-text (#dce6f2) 在白底上完全看不見。
 *
 * 所有組合的對比都在 tests 裡驗證（見下方 contrast 檢查與 README）：
 * 主要文字 ≥ 10:1、次要文字 ≥ 6:1、最弱的提示文字 ≥ 4.5:1。
 */
export const BACKGROUNDS = [
  // ── 深色 ────────────────────────────────────────────────────────
  {
    id: 'deepspace',
    name: '深空藍',
    mode: 'dark',
    vars: {
      bg1: '#0a0e17', bg2: '#0e1524', panel: '#121a2b', panel2: '#0c1220',
      text: '#dce6f2', textMuted: '#b6c4d6', textDim: '#9fb0c7',
      border: 'rgba(140, 180, 220, .22)', borderHi: 'rgba(180, 210, 240, .4)',
    },
  },
  {
    // 參照 erkul.games 的近黑底（它的 theme-color 是 #09090b）
    id: 'void',
    name: '虛空黑',
    mode: 'dark',
    vars: {
      bg1: '#09090b', bg2: '#101012', panel: '#17171a', panel2: '#0d0d0f',
      text: '#e4e4e7', textMuted: '#bfbfc6', textDim: '#a1a1aa',
      border: 'rgba(200, 200, 210, .18)', borderHi: 'rgba(220, 220, 230, .34)',
    },
  },
  {
    id: 'graphite',
    name: '石墨灰',
    mode: 'dark',
    vars: {
      bg1: '#12141a', bg2: '#181b22', panel: '#1f232c', panel2: '#15181e',
      text: '#dfe4ec', textMuted: '#bcc4d0', textDim: '#a4adbb',
      border: 'rgba(170, 185, 205, .2)', borderHi: 'rgba(200, 212, 228, .36)',
    },
  },
  {
    id: 'hangar',
    name: '機庫棕',
    mode: 'dark',
    vars: {
      bg1: '#0f0d0a', bg2: '#171310', panel: '#1e1915', panel2: '#12100c',
      text: '#eee3d6', textMuted: '#cfc0ad', textDim: '#b5a48f',
      border: 'rgba(210, 180, 140, .2)', borderHi: 'rgba(230, 205, 170, .36)',
    },
  },

  // ── 亮色 ────────────────────────────────────────────────────────
  {
    id: 'daylight',
    name: '日光白',
    mode: 'light',
    vars: {
      bg1: '#f5f7fb', bg2: '#e9eef6', panel: '#ffffff', panel2: '#f6f8fc',
      text: '#141c2a', textMuted: '#3d4a5c', textDim: '#5a6779',
      border: 'rgba(20, 45, 80, .18)', borderHi: 'rgba(20, 45, 80, .32)',
    },
  },
  {
    id: 'station',
    name: '站臺灰',
    mode: 'light',
    vars: {
      bg1: '#eceef2', bg2: '#dfe3ea', panel: '#f9fafc', panel2: '#eef1f6',
      text: '#171d26', textMuted: '#3f4a58', textDim: '#5c6675',
      border: 'rgba(25, 40, 60, .2)', borderHi: 'rgba(25, 40, 60, .34)',
    },
  },
  {
    id: 'parchment',
    name: '羊皮紙',
    mode: 'light',
    vars: {
      bg1: '#f8f4ec', bg2: '#efe7d9', panel: '#fffdf8', panel2: '#f7f2e8',
      text: '#231c12', textMuted: '#4c4132', textDim: '#6b5e4b',
      border: 'rgba(90, 70, 40, .2)', borderHi: 'rgba(90, 70, 40, .34)',
    },
  },
]

/** #rrggbb → "r, g, b"（scifi-theme.css 的 rgba() 需要這個格式） */
function hexToRgb(hex) {
  const h = String(hex).replace('#', '')
  const full = h.length === 3 ? h.split('').map(c => c + c).join('') : h
  const n = parseInt(full, 16)
  if (Number.isNaN(n) || full.length !== 6) return null
  return `${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}`
}

/**
 * 相對亮度（WCAG 公式）。用來決定強調色按鈕上的文字該用深色還是淺色。
 *
 * 這一步必須在 JS 做 —— CSS 沒辦法算亮度，而使用者可以自訂任意顏色
 * （淺黃到深紫都有可能），寫死一個文字色不可能對所有顏色都夠對比。
 */
function luminance(rgbStr) {
  const [r, g, b] = rgbStr.split(',').map(s => Number(s.trim()) / 255)
  const ch = c => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
  return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)
}

const INK_DARK = '#04121b'
const INK_LIGHT = '#f2f7ff'

// 要跟 scifi-theme.css 裡 .btn-scifi 漸層的黑色 alpha 一致
const BTN_GRADIENT_ALPHA = 0.18

/** 兩色的 WCAG 對比比值。 */
function contrast(rgbA, rgbB) {
  const la = luminance(rgbA)
  const lb = luminance(rgbB)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

/** 把 "r, g, b" 疊上 alpha 的黑色（對應 btn-scifi 的漸層暗端）。 */
function darken(rgbStr, alpha) {
  return rgbStr
    .split(',')
    .map(s => Math.round(Number(s.trim()) * (1 - alpha)))
    .join(', ')
}

/**
 * 在該底色上對比最好的文字色。
 *
 * 不用「亮度過某個門檻就換色」那種寫法 —— 門檻附近的顏色會挑錯。
 * （踩過一次：#3ea6ff 亮度 0.357，用 0.36 當門檻就會挑到淺色字，
 *   結果只有 2.41:1。）
 * 改成兩個候選都算過，取「最差情況比較好」的那個；按鈕有漸層，
 * 所以亮端與暗端都要納入比較。
 */
/** "r, g, b" → #rrggbb */
function rgbToHex(rgbStr) {
  const parts = rgbStr.split(',').map(s => Math.max(0, Math.min(255, Math.round(Number(s.trim())))))
  return '#' + parts.map(n => n.toString(16).padStart(2, '0')).join('')
}

/**
 * 把顏色往深或往淺調，直到疊在 bg 上達到 target 對比。
 *
 * 為什麼需要：強調色除了當按鈕底色，也直接當**文字色**用（連結、
 * 作用中分頁）。深底上亮藍很好讀，但同一個 #3ea6ff 放在白底上只有
 * 2.3:1，亮綠 #34d399 更只有 1.6:1 —— 亮底模式如果直接沿用強調色，
 * 所有連結都會變成幾乎看不見的淺色字。
 *
 * 回傳一個「保有原色相、但對比夠」的版本；調到極限仍不夠就回極值。
 */
function readableOn(rgbStr, bgHex, target = 4.5) {
  const bgRgb = hexToRgb(bgHex)
  if (!bgRgb) return rgbToHex(rgbStr)

  if (contrast(rgbStr, bgRgb) >= target) return rgbToHex(rgbStr)

  // 背景亮 → 把強調色壓暗；背景暗 → 把強調色提亮
  const bgIsLight = luminance(bgRgb) > 0.5
  const channels = rgbStr.split(',').map(s => Number(s.trim()))

  for (let step = 1; step <= 20; step++) {
    const f = step / 20
    const next = channels
      .map(c => (bgIsLight ? c * (1 - f) : c + (255 - c) * f))
      .map(c => Math.round(c))
      .join(', ')
    if (contrast(next, bgRgb) >= target) return rgbToHex(next)
  }
  return bgIsLight ? '#000000' : '#ffffff'
}

function inkFor(rgbStr) {
  const dark = darken(rgbStr, BTN_GRADIENT_ALPHA)
  // ⚠️ contrast()/luminance() 吃的是 "r, g, b" 字串，不是 hex ——
  //    直接把 INK_DARK 這種 hex 丟進去會算出 NaN，然後永遠選到同一色。
  const inkDarkRgb = hexToRgb(INK_DARK)
  const inkLightRgb = hexToRgb(INK_LIGHT)

  const scoreDark = Math.min(contrast(inkDarkRgb, rgbStr), contrast(inkDarkRgb, dark))
  const scoreLight = Math.min(contrast(inkLightRgb, rgbStr), contrast(inkLightRgb, dark))
  return scoreDark >= scoreLight ? INK_DARK : INK_LIGHT
}


function readLS(key, fallback) {
  try {
    return localStorage.getItem(key) ?? fallback
  } catch {
    // 私密瀏覽 / 封鎖網站資料時 localStorage 存取本身就會丟例外
    return fallback
  }
}

function writeLS(key, value) {
  try {
    localStorage.setItem(key, value)
  } catch { /* 存不進去就算了，配色不是關鍵資料 */ }
}

export const useScifiThemeStore = defineStore('scifiTheme', () => {
  // accentId 可以是預設 id，也可以是 '#rrggbb'（自訂色）
  const accentId = ref(readLS(LS_ACCENT, 'bridge'))
  const bgId = ref(readLS(LS_BG, 'deepspace'))
  const density = ref(readLS(LS_DENSITY, 'comfortable'))   // comfortable | compact

  const isCustomAccent = computed(() => accentId.value.startsWith('#'))

  const currentAccent = computed(() => {
    if (isCustomAccent.value) {
      // 自訂色只給 accent，accent2 沿用預設橘，避免使用者要選兩個顏色
      return { id: accentId.value, name: '自訂', accent: accentId.value, accent2: '#ff8a3d' }
    }
    return ACCENTS.find(a => a.id === accentId.value) || ACCENTS[0]
  })

  const currentBg = computed(
    () => BACKGROUNDS.find(b => b.id === bgId.value) || BACKGROUNDS[0]
  )

  function apply() {
    const root = document.documentElement
    if (!root) return

    const a = currentAccent.value
    const accentRgb = hexToRgb(a.accent)
    const accent2Rgb = hexToRgb(a.accent2)

    // 顏色格式不合法就不要寫進去，免得整個主題壞掉
    if (accentRgb) {
      root.style.setProperty('--sf-accent', a.accent)
      root.style.setProperty('--sf-accent-rgb', accentRgb)
      // btn-scifi 的文字色隨強調色亮度切換，自訂任意顏色也不會變成看不見
      root.style.setProperty('--sf-accent-ink', inkFor(accentRgb))
    }
    if (accent2Rgb) {
      root.style.setProperty('--sf-accent-2', a.accent2)
      root.style.setProperty('--sf-accent-2-rgb', accent2Rgb)
      root.style.setProperty('--sf-accent-2-ink', inkFor(accent2Rgb))
    }

    const bg = currentBg.value
    const v = bg.vars
    root.style.setProperty('--sf-bg-1', v.bg1)
    root.style.setProperty('--sf-bg-2', v.bg2)
    root.style.setProperty('--sf-panel', v.panel)
    root.style.setProperty('--sf-panel-2', v.panel2)
    // 亮底必須把文字整組翻成深色 —— 只換背景的話 --sf-text (#dce6f2)
    // 在白底上是完全看不見的
    root.style.setProperty('--sf-text', v.text)
    root.style.setProperty('--sf-text-muted', v.textMuted)
    root.style.setProperty('--sf-text-dim', v.textDim)
    root.style.setProperty('--sf-border', v.border)
    root.style.setProperty('--sf-border-hi', v.borderHi)

    // 表面微調：亮底不能用「疊半透明白」（白疊白等於沒變），
    // 要改成疊半透明深色，陰影也要調淡
    const surface = bg.mode === 'light' ? LIGHT_SURFACE : DARK_SURFACE
    root.style.setProperty('--sf-input-bg', surface.inputBg)
    root.style.setProperty('--sf-input-bg-focus', surface.inputBgFocus)
    root.style.setProperty('--sf-input-bg-off', surface.inputBgOff)
    root.style.setProperty('--sf-hover-bg', surface.hoverBg)
    root.style.setProperty('--sf-chip-bg', surface.chipBg)
    root.style.setProperty('--sf-header-bg', surface.headerBg)
    root.style.setProperty('--sf-inset', surface.inset)
    root.style.setProperty('--sf-shadow', surface.shadow)
    root.style.setProperty('--sf-text-strong', surface.textStrong)

    // 頂端工具列的半透明底色要跟著底色走
    root.style.setProperty('--sf-topbar-rgb', hexToRgb(v.bg1) || '10, 14, 23')

    // 強調色當「文字」用時（連結、作用中分頁）要保證對比 —— 見 readableOn()
    if (accentRgb) {
      root.style.setProperty('--sf-accent-text', readableOn(accentRgb, v.panel))
    }
    if (accent2Rgb) {
      root.style.setProperty('--sf-accent-2-text', readableOn(accent2Rgb, v.panel))
      root.style.setProperty('--sf-accent-2-ink', readableOn(accent2Rgb, v.panel))
    }

    // 狀態色（成功/危險/警示）在亮底上要用「深一階」的版本，
    // 淺底配亮綠亮紅會低於 AA。實際值在 CSS 的 [data-sf-mode] 區塊。
    root.setAttribute('data-sf-mode', bg.mode || 'dark')
    root.setAttribute('data-sf-density', density.value)
  }

  function setAccent(id) {
    accentId.value = id
    writeLS(LS_ACCENT, id)
    apply()
  }

  function setCustomAccent(hex) {
    if (!hexToRgb(hex)) return
    setAccent(hex)
  }

  function setBg(id) {
    bgId.value = id
    writeLS(LS_BG, id)
    apply()
  }

  function setDensity(value) {
    density.value = value === 'compact' ? 'compact' : 'comfortable'
    writeLS(LS_DENSITY, density.value)
    apply()
  }

  function reset() {
    accentId.value = 'bridge'
    bgId.value = 'deepspace'
    density.value = 'comfortable'
    writeLS(LS_ACCENT, 'bridge')
    writeLS(LS_BG, 'deepspace')
    writeLS(LS_DENSITY, 'comfortable')
    apply()
  }

  return {
    accentId, bgId, density,
    isCustomAccent, currentAccent, currentBg,
    accents: ACCENTS, backgrounds: BACKGROUNDS,
    apply, setAccent, setCustomAccent, setBg, setDensity, reset,
  }
})
