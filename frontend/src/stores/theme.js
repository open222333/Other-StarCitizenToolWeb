import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const ACCENTS = [
  {
    id: 'blue', name: '藍',
    dark: { sbBg: '#1e2130', sbLink: '#9aa0b4', sbSection: '#555e7a', nbBg: '#212529' },
    accent: '#6384ff', accentRgb: '99,132,255',
  },
  {
    id: 'indigo', name: '紫',
    dark: { sbBg: '#2d1b69', sbLink: '#b3a8d9', sbSection: '#7c6ab3', nbBg: '#1e1245' },
    accent: '#a78bfa', accentRgb: '167,139,250',
  },
  {
    id: 'forest', name: '綠',
    dark: { sbBg: '#1a2e1a', sbLink: '#86a886', sbSection: '#4a6b4a', nbBg: '#15231a' },
    accent: '#4ade80', accentRgb: '74,222,128',
  },
  {
    id: 'ocean', name: '藍綠',
    dark: { sbBg: '#0f2336', sbLink: '#7fb4cc', sbSection: '#3a6a8a', nbBg: '#0a1929' },
    accent: '#38bdf8', accentRgb: '56,189,248',
  },
  {
    id: 'slate', name: '灰',
    dark: { sbBg: '#1c1c1e', sbLink: '#aeaeb2', sbSection: '#636366', nbBg: '#111111' },
    accent: '#e5e5e7', accentRgb: '229,229,231',
  },
]

export const MODES = [
  { id: 'dark',  name: '深色', icon: 'bi-moon-stars' },
  { id: 'light', name: '淺色', icon: 'bi-sun' },
  { id: 'auto',  name: '自動', icon: 'bi-circle-half' },
]

// 相容舊版 admin_theme key
function migrate() {
  const old = localStorage.getItem('admin_theme')
  if (!old) return
  const map = {
    default: ['blue', 'dark'], slate:  ['slate', 'dark'],
    indigo:  ['indigo','dark'], forest: ['forest','dark'],
    ocean:   ['ocean', 'dark'], light:  ['blue',  'light'],
  }
  const [a, m] = map[old] || ['blue', 'dark']
  if (!localStorage.getItem('admin_accent')) localStorage.setItem('admin_accent', a)
  if (!localStorage.getItem('admin_mode'))   localStorage.setItem('admin_mode',   m)
  localStorage.removeItem('admin_theme')
}

function buildVars(accentId, dark) {
  const a   = ACCENTS.find(x => x.id === accentId) || ACCENTS[0]
  const rgb = a.accentRgb
  if (dark) {
    return {
      '--sb-bg':           a.dark.sbBg,
      '--sb-link':         a.dark.sbLink,
      '--sb-hover-bg':     `rgba(${rgb},.08)`,
      '--sb-active-bg':    `rgba(${rgb},.18)`,
      '--sb-active-color': a.accent,
      '--sb-section':      a.dark.sbSection,
      '--sb-footer-bd':    'rgba(255,255,255,.07)',
      '--nb-bg':           a.dark.nbBg,
      '--nb-text':         'rgba(255,255,255,.6)',
      '--nb-brand':        '#ffffff',
      '--content-bg':      '#f5f6fa',
    }
  }
  return {
    '--sb-bg':           '#f8f9fa',
    '--sb-link':         '#495057',
    '--sb-hover-bg':     `rgba(${rgb},.07)`,
    '--sb-active-bg':    `rgba(${rgb},.13)`,
    '--sb-active-color': a.accent,
    '--sb-section':      '#adb5bd',
    '--sb-footer-bd':    'rgba(0,0,0,.1)',
    '--nb-bg':           '#ffffff',
    '--nb-text':         'rgba(0,0,0,.55)',
    '--nb-brand':        '#212529',
    '--content-bg':      '#eef0f5',
  }
}

export const useThemeStore = defineStore('theme', () => {
  migrate()

  const accentId        = ref(localStorage.getItem('admin_accent') || 'blue')
  const mode            = ref(localStorage.getItem('admin_mode')   || 'dark')
  const sysDark         = window.matchMedia('(prefers-color-scheme: dark)')
  const sysDarkMatches  = ref(sysDark.matches)

  function isDark() {
    if (mode.value === 'dark')  return true
    if (mode.value === 'light') return false
    return sysDarkMatches.value
  }

  const contentBg   = ref(localStorage.getItem('admin_content_bg') || '')
  const isCustomBg  = ref(!!localStorage.getItem('admin_content_bg'))

  function applyContentBg() {
    const bg = isCustomBg.value ? contentBg.value : null
    if (bg) document.documentElement.style.setProperty('--content-bg', bg)
  }

  function applyVars() {
    const vars = buildVars(accentId.value, isDark())
    Object.entries(vars).forEach(([k, v]) => document.documentElement.style.setProperty(k, v))
    applyContentBg()
  }

  function setContentBg(hex) {
    contentBg.value  = hex
    isCustomBg.value = true
    localStorage.setItem('admin_content_bg', hex)
    document.documentElement.style.setProperty('--content-bg', hex)
  }

  function resetContentBg() {
    contentBg.value  = ''
    isCustomBg.value = false
    localStorage.removeItem('admin_content_bg')
    applyVars()
  }

  sysDark.addEventListener('change', (e) => {
    sysDarkMatches.value = e.matches
    if (mode.value === 'auto') applyVars()
  })

  const customColor = ref(localStorage.getItem('admin_custom_color') || '#6384ff')
  const isCustom    = ref(localStorage.getItem('admin_accent') === 'custom')

  function setAccent(id) {
    accentId.value = id
    isCustom.value = false
    localStorage.setItem('admin_accent', id)
    applyVars()
  }

  function setCustomColor(hex) {
    customColor.value = hex
    isCustom.value    = true
    localStorage.setItem('admin_custom_color', hex)
    localStorage.setItem('admin_accent', 'custom')
    // 自訂模式：只替換 accent 相關的 CSS 變數
    const rgb = hex.slice(1).match(/.{2}/g).map(v => parseInt(v, 16)).join(',')
    document.documentElement.style.setProperty('--sb-hover-bg',     `rgba(${rgb},.08)`)
    document.documentElement.style.setProperty('--sb-active-bg',    `rgba(${rgb},.18)`)
    document.documentElement.style.setProperty('--sb-active-color', hex)
  }

  function setMode(m) {
    mode.value = m
    localStorage.setItem('admin_mode', m)
    applyVars()
    if (isCustom.value) setCustomColor(customColor.value)
  }

  const isLight = computed(() => !isDark())

  // 啟動時套用已儲存的設定
  applyVars()
  if (isCustom.value) setCustomColor(customColor.value)

  return {
    accentId, mode, accents: ACCENTS, modes: MODES,
    isLight, isCustom, customColor,
    contentBg, isCustomBg,
    setAccent, setMode, setCustomColor,
    setContentBg, resetContentBg,
  }
})
