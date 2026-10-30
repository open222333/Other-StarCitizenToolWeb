<!--
  航線結果的 3D 星圖（canvas 自己畫，不靠 3D 函式庫）：一次顯示一個星系，
  畫恆星／行星／衛星／跳躍點（POST /starmap/nav/route 回傳的 map），以及這個方案的航線、
  經過的 OM 點、各站點（編號跟航段表一樣，0＝起點；要補燃料的站點換成警示色）。

  畫面：固定的深空背景（星點、星雲）、黃道面座標網、行星軌道、天體依恆星方向打光、
  站點／天體到黃道面的垂直投影線、航線發光並有流動的光點（系統設定「減少動態效果」時不動）。
  操作：左鍵／單指拖曳旋轉（放開有慣性）、右鍵／Shift＋拖曳／雙指拖曳平移、滾輪／雙指縮放（往游標方向）、
  點一下選取、點兩下飛過去；右上角按鈕：拉近、拉遠、俯視、全覽、全螢幕。
  座標是公尺（星系座標系，z 朝上），距離跨度很大，天體太小時畫成固定大小的點。
-->
<template>
  <div class="rm3d">
    <div v-if="systemKeys.length > 1" class="btn-group btn-group-sm mb-2" role="group" aria-label="星系">
      <button v-for="k in systemKeys" :key="k" type="button" class="btn btn-subtab"
        :class="{ active: system === k }" :aria-pressed="system === k ? 'true' : 'false'"
        @click="system = k">{{ systemLabel(k) }}</button>
    </div>
    <div ref="wrapEl" class="rm3d__wrap" :class="{ 'is-full': fullscreen }">
      <canvas ref="canvasEl" class="rm3d__canvas" tabindex="0" aria-label="3D 星圖"
        @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp"
        @pointercancel="onPointerUp" @pointerleave="onPointerLeave" @wheel.prevent="onWheel"
        @dblclick="onDblClick" @contextmenu.prevent @keydown="onKey"></canvas>

      <div class="rm3d__system">{{ systemLabel(system) }}</div>

      <div class="rm3d__tools" role="toolbar" aria-label="星圖操作">
        <button type="button" class="btn btn-sm btn-info" aria-label="拉近" @click="zoomBy(1 / 1.6)"><i class="bi bi-plus-lg"></i></button>
        <button type="button" class="btn btn-sm btn-info" aria-label="拉遠" @click="zoomBy(1.6)"><i class="bi bi-dash-lg"></i></button>
        <button type="button" class="btn btn-sm btn-info" :aria-pressed="topView ? 'true' : 'false'" aria-label="俯視"
          @click="toggleTopView"><i class="bi" :class="topView ? 'bi-badge-3d' : 'bi-grid-3x3'"></i></button>
        <button type="button" class="btn btn-sm btn-info" aria-label="全覽" @click="fit(true)"><i class="bi bi-bullseye"></i></button>
        <button type="button" class="btn btn-sm btn-info" :aria-label="fullscreen ? '離開全螢幕' : '全螢幕'"
          @click="toggleFullscreen"><i class="bi" :class="fullscreen ? 'bi-fullscreen-exit' : 'bi-arrows-fullscreen'"></i></button>
      </div>

      <div v-if="hover && !dragging" class="rm3d__tip" :style="tipStyle(hover)">
        <div class="fw-semibold">{{ hover.title }}</div>
        <div v-if="hover.sub" class="rm3d__tip-sub">{{ hover.sub }}</div>
      </div>

      <div v-if="selected" class="rm3d__info">
        <div class="d-flex align-items-start gap-2">
          <div class="flex-grow-1 min-w-0">
            <div class="fw-semibold rm3d__info-title">{{ selected.title }}</div>
            <div v-if="selected.sub" class="rm3d__tip-sub">{{ selected.sub }}</div>
          </div>
          <button type="button" class="btn btn-sm btn-info" aria-label="移過去" @click="flyTo(selected)">
            <i class="bi bi-crosshair"></i></button>
          <button type="button" class="btn btn-sm btn-secondary" aria-label="取消選取" @click="selected = null">
            <i class="bi bi-x-lg"></i></button>
        </div>
      </div>

      <div class="rm3d__scale">{{ scaleLabel }}</div>
    </div>
    <div class="d-flex flex-wrap gap-1 mt-2">
      <button v-for="s in stopsInSystem" :key="s.index" type="button" class="sf-chip rm3d__stop"
        :class="{ 'sf-chip--warn': s.refuel, 'sf-chip--accent': !s.refuel }" @click="flyToStop(s)">
        {{ s.index }} {{ s.label }}<i v-if="s.refuel" class="bi bi-fuel-pump ms-1"></i>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  plan: { type: Object, required: true },       // 一個方案（start, legs[].steps[], refuel_stops）
  map: { type: Object, default: () => ({}) },   // {system_key: {name, name_zh, bodies}}
})

const FOV = Math.PI / 3                 // 60 度
const STATION_VIEW = 6e6                // 點站點時鏡頭距離（6,000 km）
const MIN_DIST = 2e4
const MAX_DIST = 5e12
const PITCH_MIN = 0.02
const PITCH_MAX = Math.PI / 2 - 0.001

const canvasEl = ref(null)
const wrapEl = ref(null)
const hover = ref(null)
const selected = ref(null)
const dragging = ref(false)
const topView = ref(false)
const fullscreen = ref(false)
const scaleLabel = ref('')

const nameOf = n => (n?.name_zh && n.name_zh !== n.name ? `${n.name_zh}（${n.name}）` : (n?.name || ''))
const shortName = n => n?.name_zh || n?.name || ''

// ── 這個方案經過的星系（依序）──────────────────────────────
const systemKeys = computed(() => {
  const keys = []
  const add = k => { if (k && !keys.includes(k)) keys.push(k) }
  add(props.plan.start?.system_key)
  for (const leg of props.plan.legs || []) {
    for (const s of leg.steps || []) { add(s.from?.system_key); add(s.to?.system_key) }
    add(leg.to?.system_key)
  }
  return keys
})
const system = ref('')
watch(systemKeys, keys => { if (!keys.includes(system.value)) system.value = keys[0] || '' }, { immediate: true })

function systemLabel(k) {
  const m = props.map?.[k]
  return m ? nameOf(m) : k
}

// ── 這個星系裡要畫的東西 ────────────────────────────────────
const bodies = computed(() => props.map?.[system.value]?.bodies || [])
const star = computed(() => bodies.value.find(b => b.type === 'Star') || null)

const segments = computed(() => {
  const out = []
  for (const leg of props.plan.legs || []) {
    for (const s of leg.steps || []) {
      if (s.kind !== 'qt' || s.from?.system_key !== system.value || s.to?.system_key !== system.value) continue
      if (s.from?.p && s.to?.p) out.push([s.from.p, s.to.p])
    }
  }
  return out
})

const waypoints = computed(() => {
  // 航線中途經過的 OM 點、跳躍點（不是站點的）
  const out = []
  const seen = new Set()
  for (const leg of props.plan.legs || []) {
    for (const s of leg.steps || []) {
      for (const n of [s.from, s.to]) {
        if (!n?.p || n.system_key !== system.value || seen.has(n.id)) continue
        if (n.synthetic || n.jump || n.type === 'JumpPoint') {
          seen.add(n.id)
          out.push({ id: n.id, p: n.p, kind: n.synthetic ? 'om' : 'jump', node: n })
        }
      }
    }
  }
  return out
})

const stopsInSystem = computed(() => {
  const refuel = new Set(props.plan.refuel_stops || [])
  const all = [props.plan.start, ...(props.plan.legs || []).map(l => l.to)]
  const out = []
  all.forEach((n, i) => {
    if (n?.p && n.system_key === system.value) {
      out.push({ index: i, p: n.p, node: n, label: shortName(n), refuel: refuel.has(i) })
    }
  })
  return out
})

// ── 鏡頭 ────────────────────────────────────────────────────
const cam = { target: [0, 0, 0], yaw: 0.6, pitch: 0.95, dist: 1e11 }
let size = { w: 600, h: 400, dpr: 1 }
let lastPitch = 0.95

function focal() {
  return (size.h / 2) / Math.tan(FOV / 2)
}

/** 世界座標（相對 target）→ 鏡頭座標：x 右、y 往螢幕裡、z 上 */
function toCam(vx, vy, vz) {
  const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw)
  const x1 = vx * cy - vy * sy
  const y1 = vx * sy + vy * cy
  const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch)
  return [x1, y1 * cp - vz * sp, y1 * sp + vz * cp]
}

/** 鏡頭座標 → 世界座標的位移 */
function fromCam(x1, y2, z2) {
  const cp = Math.cos(cam.pitch), sp = Math.sin(cam.pitch)
  const y1 = y2 * cp + z2 * sp
  const vz = -y2 * sp + z2 * cp
  const cy = Math.cos(cam.yaw), sy = Math.sin(cam.yaw)
  return [x1 * cy + y1 * sy, -x1 * sy + y1 * cy, vz]
}

function project(p) {
  const [x, y, z] = toCam(p[0] - cam.target[0], p[1] - cam.target[1], p[2] - cam.target[2])
  const depth = cam.dist + y
  if (depth <= cam.dist * 0.02) return null
  const s = focal() / depth
  return { x: size.w / 2 + x * s, y: size.h / 2 - z * s, depth, scale: s }
}

/** 螢幕上一點在「過 target、垂直視線」那個平面上的世界座標 */
function screenToWorld(sx, sy) {
  const s = focal() / cam.dist
  const d = fromCam((sx - size.w / 2) / s, 0, -(sy - size.h / 2) / s)
  return [cam.target[0] + d[0], cam.target[1] + d[1], cam.target[2] + d[2]]
}

function clampDist(d) {
  return Math.min(MAX_DIST, Math.max(MIN_DIST, d))
}

function routePoints() {
  return [...segments.value.flat(), ...stopsInSystem.value.map(s => s.p)]
}

function fit(animate = false) {
  // 以航線（站點、航段）為範圍；遠方的跳躍點、外圍衛星不硬塞進畫面
  const route = routePoints()
  const pts = route.length ? route : bodies.value.map(b => b.p)
  if (!pts.length) return
  const c = [0, 1, 2].map(i => {
    const vals = pts.map(p => p[i])
    return (Math.min(...vals) + Math.max(...vals)) / 2
  })
  let r = 0
  for (const p of pts) r = Math.max(r, Math.hypot(p[0] - c[0], p[1] - c[1], p[2] - c[2]))
  // 窄螢幕（手機直放）時寬度才是限制；右邊扣掉按鈕那一欄，內容往左挪半欄
  const TOOLS = 52
  const halfTan = Math.min(Math.tan(FOV / 2), ((size.w - TOOLS) / 2) / focal())
  const dist = clampDist(Math.max(MIN_DIST * 50, (r / halfTan) * 1.12))
  const shift = fromCam((TOOLS / 2) * dist / focal(), 0, 0)
  moveTo({ target: c.map((v, i) => v + shift[i]), dist }, animate)
}

// 站點附近有星體（地表站點、軌道太空站）時，鏡頭拉遠到看得到整顆星體
function viewDistFor(p) {
  let best = null
  for (const b of bodies.value) {
    if (!b.radius || b.type === 'JumpPoint') continue
    const d = Math.hypot(p[0] - b.p[0], p[1] - b.p[1], p[2] - b.p[2])
    if (d < b.radius * 4 && (!best || d < best.d)) best = { d, r: b.radius }
  }
  return best ? Math.max(STATION_VIEW, best.r * 5) : STATION_VIEW
}

function flyTo(item) {
  if (item?.p) moveTo({ target: item.p, dist: item.dist || viewDistFor(item.p) }, true)
}

function flyToStop(s) {
  selected.value = stopInfo(s)
  flyTo({ p: s.p, dist: viewDistFor(s.p) })
}

function zoomBy(f) {
  moveTo({ dist: clampDist(cam.dist * f) }, true)
}

function toggleTopView() {
  topView.value = !topView.value
  if (topView.value) lastPitch = cam.pitch
  moveTo({ pitch: topView.value ? PITCH_MAX : (lastPitch < PITCH_MAX - 0.05 ? lastPitch : 0.95) }, true)
}

let anim = null
function moveTo(to, animate) {
  inertia = null
  const from = { target: [...cam.target], dist: cam.dist, pitch: cam.pitch, yaw: cam.yaw }
  const goal = { target: to.target || from.target, dist: to.dist || from.dist,
    pitch: to.pitch ?? from.pitch, yaw: to.yaw ?? from.yaw }
  if (!animate || reducedMotion) {
    Object.assign(cam, { target: [...goal.target], dist: goal.dist, pitch: goal.pitch, yaw: goal.yaw })
    anim = null
    requestDraw()
    return
  }
  anim = { from, goal, t0: performance.now(), ms: 600 }
  requestDraw()
}

function stepAnim(now) {
  if (!anim) return
  const k = Math.min(1, (now - anim.t0) / anim.ms)
  const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2
  const { from, goal } = anim
  cam.target = from.target.map((v, i) => v + (goal.target[i] - v) * e)
  cam.dist = Math.exp(Math.log(from.dist) + (Math.log(goal.dist) - Math.log(from.dist)) * e)
  cam.pitch = from.pitch + (goal.pitch - from.pitch) * e
  cam.yaw = from.yaw + (goal.yaw - from.yaw) * e
  if (k >= 1) anim = null
}

// ── 背景星空（只跟著旋轉，不跟著平移縮放）─────────────────────
const SKY = (() => {
  let seed = 7
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
  const stars = []
  for (let i = 0; i < 700; i++) {
    const u = rnd() * 2 - 1, t = rnd() * Math.PI * 2
    const r = Math.sqrt(1 - u * u)
    const warm = rnd()
    stars.push({ d: [r * Math.cos(t), r * Math.sin(t), u], m: Math.pow(rnd(), 3),
      c: warm < 0.15 ? '255,214,170' : warm < 0.3 ? '170,200,255' : '235,240,255' })
  }
  const nebulae = [
    { d: [0.6, 0.5, 0.3], r: 0.55, c: '90,60,170' },
    { d: [-0.7, 0.2, -0.2], r: 0.45, c: '30,110,160' },
    { d: [0.1, -0.8, 0.4], r: 0.4, c: '150,60,110' },
  ]
  return { stars, nebulae }
})()

function projectDir(d) {
  const [x, y, z] = toCam(d[0], d[1], d[2])
  if (y <= 0.05) return null
  const s = focal() / y
  return { x: size.w / 2 + x * s, y: size.h / 2 - z * s, s }
}

// ── 顏色 ────────────────────────────────────────────────────
let colors = {}
function readColors() {
  const el = canvasEl.value
  if (!el) return
  const cs = getComputedStyle(el)
  const v = name => cs.getPropertyValue(name).trim()
  const rgbVar = name => v(name).replace(/\s+/g, '')
  colors = {
    accent: v('--sf-accent') || '#38bdf8',
    accentRgb: rgbVar('--sf-accent-rgb') || '56,189,248',
    warnRgb: rgbVar('--bs-warning-rgb') || '245,158,11',
  }
}

// 行星配色：依名稱固定挑一組（岩石、冰、氣態、沙漠…）
const PLANET_PALETTE = [
  ['#c9a27a', '#6b4a2f'], ['#7fb3d5', '#1f4e79'], ['#d8c69a', '#7a6233'], ['#9fd3c7', '#2f6b5f'],
  ['#c98f6b', '#5e2f1d'], ['#b9b7d6', '#4b4777'], ['#e0b97a', '#8a5a1c'], ['#8fb27a', '#3c5a2b'],
]
function paletteFor(b) {
  if (b.type === 'Moon') return ['#c8c8c8', '#4a4a4a']
  let h = 0
  for (const ch of b.name || '') h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return PLANET_PALETTE[h % PLANET_PALETTE.length]
}

// ── 畫 ──────────────────────────────────────────────────────
let hits = []
let raf = null
let needsDraw = true
let dashT = 0
let inertia = null
let lastFrame = 0
let visible = true
const reducedMotion = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

function requestDraw() {
  needsDraw = true
}

function loop(now) {
  raf = requestAnimationFrame(loop)
  if (!visible) return
  const dt = Math.min(0.05, (now - (lastFrame || now)) / 1000)
  lastFrame = now
  if (anim) { stepAnim(now); needsDraw = true }
  if (inertia) {
    cam.yaw += inertia.vy * dt
    cam.pitch = Math.max(PITCH_MIN, Math.min(PITCH_MAX, cam.pitch + inertia.vp * dt))
    const k = Math.pow(0.02, dt)
    inertia.vy *= k
    inertia.vp *= k
    if (Math.abs(inertia.vy) + Math.abs(inertia.vp) < 0.02) inertia = null
    needsDraw = true
  }
  if (!reducedMotion && segments.value.length) {
    dashT = (dashT + dt * 0.35) % 1
    needsDraw = true
  }
  if (needsDraw) {
    needsDraw = false
    render()
  }
}

function label(ctx, text, x, y, opts, placed) {
  ctx.font = opts.font
  const w = ctx.measureText(text).width
  // 右邊超出（或碰到右上角按鈕欄）時改放到標記左邊
  if (opts.leftOf != null && x + w + 6 > size.w - 52) x = Math.max(6, opts.leftOf - w - 6)
  const h = opts.h || 18
  const rect = { x: x - 4, y: y - h / 2, w: w + 8, h }
  if (placed.some(r => rect.x < r.x + r.w && rect.x + rect.w > r.x && rect.y < r.y + r.h && rect.y + rect.h > r.y)) {
    return false
  }
  placed.push(rect)
  if (opts.pill) {
    ctx.fillStyle = opts.pill
    roundRect(ctx, rect.x, rect.y, rect.w, rect.h, 5)
    ctx.fill()
  }
  ctx.fillStyle = opts.color
  ctx.fillText(text, x, y + 0.5)
  return true
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

function render() {
  const el = canvasEl.value
  if (!el) return
  const ctx = el.getContext('2d')
  ctx.setTransform(size.dpr, 0, 0, size.dpr, 0, 0)
  const { w, h } = size
  hits = []
  const placed = []

  // 深空背景
  const bg = ctx.createRadialGradient(w * 0.5, h * 0.45, 0, w * 0.5, h * 0.5, Math.max(w, h) * 0.75)
  bg.addColorStop(0, '#0b1426')
  bg.addColorStop(1, '#03060d')
  ctx.fillStyle = bg
  ctx.fillRect(0, 0, w, h)
  for (const n of SKY.nebulae) {
    const q = projectDir(n.d)
    if (!q) continue
    const r = n.r * focal()
    const g = ctx.createRadialGradient(q.x, q.y, 0, q.x, q.y, r)
    g.addColorStop(0, `rgba(${n.c},0.16)`)
    g.addColorStop(1, `rgba(${n.c},0)`)
    ctx.fillStyle = g
    ctx.fillRect(q.x - r, q.y - r, r * 2, r * 2)
  }
  for (const s of SKY.stars) {
    const q = projectDir(s.d)
    if (!q || q.x < 0 || q.y < 0 || q.x > w || q.y > h) continue
    const a = 0.25 + s.m * 0.75
    ctx.fillStyle = `rgba(${s.c},${a})`
    const r = 0.4 + s.m * 1.3
    ctx.fillRect(q.x - r / 2, q.y - r / 2, r, r)
  }

  ctx.textBaseline = 'middle'
  ctx.lineCap = 'round'
  const sun = star.value

  // 黃道面座標網（以恆星為中心的同心圓＋放射線），越遠越淡
  if (sun) {
    let maxR = 0
    for (const b of bodies.value) {
      if (b.type === 'Planet' || b.type === 'JumpPoint') maxR = Math.max(maxR, Math.hypot(b.p[0] - sun.p[0], b.p[1] - sun.p[1]))
    }
    const stepR = niceStep(maxR / 5)
    ctx.lineWidth = 1
    for (let r = stepR; r <= maxR * 1.15; r += stepR) ringPath(ctx, sun.p, r, 'rgba(120,160,220,0.07)')
    for (let i = 0; i < 12; i++) {
      const a = (i / 12) * Math.PI * 2
      const q1 = project(sun.p)
      const q2 = project([sun.p[0] + maxR * 1.15 * Math.cos(a), sun.p[1] + maxR * 1.15 * Math.sin(a), sun.p[2]])
      if (!q1 || !q2) continue
      ctx.strokeStyle = 'rgba(120,160,220,0.05)'
      ctx.beginPath()
      ctx.moveTo(q1.x, q1.y)
      ctx.lineTo(q2.x, q2.y)
      ctx.stroke()
    }
    // 行星軌道
    for (const b of bodies.value) {
      if (b.type !== 'Planet') continue
      const r = Math.hypot(b.p[0] - sun.p[0], b.p[1] - sun.p[1])
      ringPath(ctx, sun.p, r, 'rgba(160,190,240,0.22)')
    }
  }

  // 站點、航線端點先投影（後面用來讓標籤）
  const stopClusters = []
  for (const s of stopsInSystem.value) {
    const q = project(s.p)
    if (!q) continue
    const near = stopClusters.find(c => Math.hypot(c.q.x - q.x, c.q.y - q.y) < 16)
    if (near) {
      near.items.push(s)
      near.refuel = near.refuel || s.refuel
    } else {
      stopClusters.push({ q, p: s.p, items: [s], refuel: s.refuel })
    }
  }
  // 站點標籤優先放（避免被天體名稱擠掉）
  ctx.font = '600 13px system-ui, sans-serif'
  for (const c of stopClusters) {
    const tag = c.items.map(x => x.index).join('、')
    const names = [...new Set(c.items.map(x => x.label))].join('／')
    c.labelText = `${tag}  ${names}`
    c.labelOk = label(ctx, c.labelText, c.q.x + 15, c.q.y - 14,
      { font: '600 13px system-ui, sans-serif', color: '#ffffff', pill: 'rgba(5,10,20,0.72)', h: 20, leftOf: c.q.x - 9 }, placed)
  }

  // 垂直投影線（天體、站點到黃道面）
  if (sun && !topView.value) {
    ctx.setLineDash([2, 4])
    ctx.lineWidth = 1
    const drop = (p, color) => {
      const q1 = project(p), q2 = project([p[0], p[1], sun.p[2]])
      if (!q1 || !q2 || Math.hypot(q1.x - q2.x, q1.y - q2.y) < 3) return
      ctx.strokeStyle = color
      ctx.beginPath()
      ctx.moveTo(q1.x, q1.y)
      ctx.lineTo(q2.x, q2.y)
      ctx.stroke()
      ctx.fillStyle = color
      ctx.fillRect(q2.x - 1.5, q2.y - 1.5, 3, 3)
    }
    for (const b of bodies.value) if (b.type !== 'Star') drop(b.p, 'rgba(160,190,240,0.25)')
    for (const c of stopClusters) drop(c.p, `rgba(${colors.accentRgb},0.45)`)
    ctx.setLineDash([])
  }

  // 天體：遠的先畫
  const projected = bodies.value.map(b => ({ b, q: project(b.p) })).filter(x => x.q)
  projected.sort((a, b) => b.q.depth - a.q.depth)
  const sunQ = sun ? project(sun.p) : null
  for (const { b, q } of projected) {
    if (b.type === 'JumpPoint') {
      drawJumpPoint(ctx, q)
      label(ctx, shortName(b), q.x + 10, q.y, { font: '12px system-ui, sans-serif', color: '#d8b4fe', leftOf: q.x - 10 }, placed)
      hits.push(bodyHit(b, q, 9))
      continue
    }
    const minR = b.type === 'Star' ? 6 : b.type === 'Planet' ? 4 : 2.5
    const r = Math.max(minR, (b.radius || 0) * q.scale)
    if (q.x < -r * 3 - 60 || q.x > w + r * 3 + 60 || q.y < -r * 3 - 60 || q.y > h + r * 3 + 60) continue
    if (b.type === 'Star') drawStar(ctx, q, r)
    else drawBody(ctx, b, q, r, sunQ)
    const tooSmall = b.type === 'Moon' && r < 4 && cam.dist > 3e9
    if (!tooSmall) {
      const font = b.type === 'Moon' ? '12px system-ui, sans-serif' : '600 13px system-ui, sans-serif'
      label(ctx, shortName(b), q.x + r + 6, q.y, { font, color: b.type === 'Moon' ? '#a8b3c7' : '#dbe6ff', leftOf: q.x - r - 6 }, placed)
    }
    hits.push(bodyHit(b, q, Math.max(r, 9)))
  }

  // 航線：發光底線＋實線＋流動光點
  const rgb = colors.accentRgb
  for (const [a, b] of segments.value) {
    const qa = project(a), qb = project(b)
    if (!qa || !qb) continue
    ctx.strokeStyle = `rgba(${rgb},0.18)`
    ctx.lineWidth = 7
    line(ctx, qa, qb)
    ctx.strokeStyle = `rgba(${rgb},0.95)`
    ctx.lineWidth = 2
    line(ctx, qa, qb)
    const len = Math.hypot(qb.x - qa.x, qb.y - qa.y)
    if (len > 30) {
      const n = Math.max(1, Math.round(len / 90))
      for (let i = 0; i < n; i++) {
        const t = ((i + dashT) / n) % 1
        const x = qa.x + (qb.x - qa.x) * t, y = qa.y + (qb.y - qa.y) * t
        const g = ctx.createRadialGradient(x, y, 0, x, y, 6)
        g.addColorStop(0, 'rgba(255,255,255,0.95)')
        g.addColorStop(0.4, `rgba(${rgb},0.8)`)
        g.addColorStop(1, `rgba(${rgb},0)`)
        ctx.fillStyle = g
        ctx.fillRect(x - 6, y - 6, 12, 12)
      }
      // 方向箭頭
      const ang = Math.atan2(qb.y - qa.y, qb.x - qa.x)
      const mx = qa.x + (qb.x - qa.x) * 0.55, my = qa.y + (qb.y - qa.y) * 0.55
      ctx.fillStyle = `rgba(${rgb},1)`
      ctx.beginPath()
      ctx.moveTo(mx + Math.cos(ang) * 8, my + Math.sin(ang) * 8)
      ctx.lineTo(mx + Math.cos(ang + 2.6) * 7, my + Math.sin(ang + 2.6) * 7)
      ctx.lineTo(mx + Math.cos(ang - 2.6) * 7, my + Math.sin(ang - 2.6) * 7)
      ctx.closePath()
      ctx.fill()
    }
  }

  // 中途的 OM 點、跳躍點
  for (const wpt of waypoints.value) {
    const q = project(wpt.p)
    if (!q) continue
    if (wpt.kind === 'jump') drawJumpPoint(ctx, q)
    else {
      ctx.save()
      ctx.translate(q.x, q.y)
      ctx.rotate(Math.PI / 4)
      ctx.fillStyle = '#0b1222'
      ctx.strokeStyle = `rgba(${rgb},0.9)`
      ctx.lineWidth = 1.5
      ctx.fillRect(-4, -4, 8, 8)
      ctx.strokeRect(-4, -4, 8, 8)
      ctx.restore()
    }
    hits.push({ x: q.x, y: q.y, r: 9, title: nameOf(wpt.node), sub: wpt.kind === 'jump' ? '跳躍點' : '軌道標記（OM）',
      p: wpt.p, dist: viewDistFor(wpt.p), key: `w:${wpt.id}` })
  }

  // 站點
  const sel = selected.value?.key
  for (const c of stopClusters) {
    const { q } = c
    const col = c.refuel ? colors.warnRgb : rgb
    const isSel = sel === `s:${c.items.map(x => x.index).join(',')}`
    const halo = ctx.createRadialGradient(q.x, q.y, 0, q.x, q.y, 22)
    halo.addColorStop(0, `rgba(${col},0.45)`)
    halo.addColorStop(1, `rgba(${col},0)`)
    ctx.fillStyle = halo
    ctx.fillRect(q.x - 22, q.y - 22, 44, 44)
    ctx.beginPath()
    ctx.arc(q.x, q.y, 10, 0, Math.PI * 2)
    ctx.fillStyle = '#07101f'
    ctx.fill()
    ctx.lineWidth = isSel ? 3 : 2
    ctx.strokeStyle = `rgba(${col},1)`
    ctx.stroke()
    const indexes = c.items.map(x => x.index)
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 11px system-ui, sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(indexes.length > 1 ? `${indexes[0]}+` : String(indexes[0]), q.x, q.y + 0.5)
    ctx.textAlign = 'left'
    const subs = c.items.map(x => [x.node.path_zh?.slice(1).join(' › '), x.refuel ? '需補充燃料' : ''].filter(Boolean).join(' · '))
    hits.push({ x: q.x, y: q.y, r: 12, key: `s:${indexes.join(',')}`,
      title: c.items.map(x => `${x.index} ${nameOf(x.node)}`).join('、'),
      sub: [...new Set(subs)].filter(Boolean).join('；'), p: c.p, dist: viewDistFor(c.p) })
  }

  // 選取的天體外圈
  if (sel && !sel.startsWith('s:')) {
    const hit = hits.find(x => x.key === sel)
    if (hit) {
      ctx.strokeStyle = 'rgba(255,255,255,0.9)'
      ctx.lineWidth = 1.5
      ctx.setLineDash([4, 3])
      ctx.beginPath()
      ctx.arc(hit.x, hit.y, hit.r + 5, 0, Math.PI * 2)
      ctx.stroke()
      ctx.setLineDash([])
    }
  }

  scaleLabel.value = scaleText()
}

function bodyHit(b, q, r) {
  const typeZh = { Star: '恆星', Planet: '行星', Moon: '衛星', JumpPoint: '跳躍點' }[b.type] || b.type
  return { x: q.x, y: q.y, r, title: nameOf(b), sub: typeZh, p: b.p,
    dist: b.type === 'Star' ? Math.max(STATION_VIEW, (b.radius || 0) * 30) : Math.max(STATION_VIEW, (b.radius || 0) * 6),
    key: `b:${b.id}` }
}

function line(ctx, a, b) {
  ctx.beginPath()
  ctx.moveTo(a.x, a.y)
  ctx.lineTo(b.x, b.y)
  ctx.stroke()
}

function ringPath(ctx, c, r, color) {
  ctx.strokeStyle = color
  ctx.beginPath()
  let started = false
  for (let i = 0; i <= 128; i++) {
    const a = (i / 128) * Math.PI * 2
    const q = project([c[0] + r * Math.cos(a), c[1] + r * Math.sin(a), c[2]])
    if (!q) { started = false; continue }
    if (!started) { ctx.moveTo(q.x, q.y); started = true } else ctx.lineTo(q.x, q.y)
  }
  ctx.stroke()
}

function niceStep(v) {
  if (!v) return 1e9
  const p = Math.pow(10, Math.floor(Math.log10(v)))
  const n = v / p
  return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * p
}

function drawStar(ctx, q, r) {
  const glow = Math.max(r * 6, 46)
  const g = ctx.createRadialGradient(q.x, q.y, 0, q.x, q.y, glow)
  g.addColorStop(0, 'rgba(255,240,200,0.95)')
  g.addColorStop(0.08, 'rgba(255,214,120,0.7)')
  g.addColorStop(0.3, 'rgba(255,170,60,0.18)')
  g.addColorStop(1, 'rgba(255,150,40,0)')
  ctx.fillStyle = g
  ctx.fillRect(q.x - glow, q.y - glow, glow * 2, glow * 2)
  ctx.beginPath()
  ctx.arc(q.x, q.y, r, 0, Math.PI * 2)
  ctx.fillStyle = '#fff6dc'
  ctx.fill()
}

function drawBody(ctx, b, q, r, sunQ) {
  const [light, dark] = paletteFor(b)
  // 光源方向：恆星在畫面上的方向（恆星在鏡頭後面時就從左上打光）
  let lx = -0.6, ly = -0.6
  if (sunQ) {
    const dx = sunQ.x - q.x, dy = sunQ.y - q.y
    const d = Math.hypot(dx, dy)
    if (d > 1) { lx = dx / d; ly = dy / d }
  }
  if (r > 3) {
    // 大氣光暈
    const atm = ctx.createRadialGradient(q.x, q.y, r * 0.9, q.x, q.y, r * 1.35)
    atm.addColorStop(0, `${light}55`)
    atm.addColorStop(1, `${light}00`)
    ctx.fillStyle = atm
    ctx.beginPath()
    ctx.arc(q.x, q.y, r * 1.35, 0, Math.PI * 2)
    ctx.fill()
  }
  const g = ctx.createRadialGradient(q.x + lx * r * 0.45, q.y + ly * r * 0.45, r * 0.05, q.x, q.y, r * 1.05)
  g.addColorStop(0, '#ffffff')
  g.addColorStop(0.12, light)
  g.addColorStop(0.75, dark)
  g.addColorStop(1, '#05070c')
  ctx.beginPath()
  ctx.arc(q.x, q.y, r, 0, Math.PI * 2)
  ctx.fillStyle = r > 2.5 ? g : light
  ctx.fill()
}

function drawJumpPoint(ctx, q) {
  const g = ctx.createRadialGradient(q.x, q.y, 0, q.x, q.y, 14)
  g.addColorStop(0, 'rgba(216,180,254,0.9)')
  g.addColorStop(0.4, 'rgba(168,85,247,0.35)')
  g.addColorStop(1, 'rgba(168,85,247,0)')
  ctx.fillStyle = g
  ctx.fillRect(q.x - 14, q.y - 14, 28, 28)
  ctx.strokeStyle = 'rgba(233,213,255,0.95)'
  ctx.lineWidth = 1.5
  ctx.beginPath()
  ctx.ellipse(q.x, q.y, 7, 4, -0.5, 0, Math.PI * 2)
  ctx.stroke()
}

function scaleText() {
  // 畫面寬度大約代表多遠
  const span = (size.w / focal()) * cam.dist
  if (span >= 1e9) return `畫面寬 ≈ ${(span / 1e9).toLocaleString('en-US', { maximumFractionDigits: 1 })} Gm`
  return `畫面寬 ≈ ${Math.round(span / 1000).toLocaleString('en-US')} km`
}

function stopInfo(s) {
  return { key: `s:${s.index}`, title: `${s.index} ${nameOf(s.node)}`, p: s.p, dist: viewDistFor(s.p),
    sub: [s.node.path_zh?.slice(1).join(' › '), s.refuel ? '需補充燃料' : ''].filter(Boolean).join(' · ') }
}

function tipStyle(t) {
  const x = Math.min(t.x + 14, size.w - 230)
  const y = Math.min(t.y + 14, size.h - 60)
  return { left: `${Math.max(4, x)}px`, top: `${Math.max(4, y)}px` }
}

// ── 操作 ────────────────────────────────────────────────────
const pointers = new Map()
let mode = ''               // rotate / pan
let moved = 0
let pinch = null
let lastMove = null

function onPointerDown(e) {
  canvasEl.value?.focus({ preventScroll: true })
  canvasEl.value?.setPointerCapture?.(e.pointerId)
  pointers.set(e.pointerId, { x: e.offsetX, y: e.offsetY })
  inertia = null
  anim = null
  moved = 0
  lastMove = null
  mode = e.button === 2 || e.shiftKey ? 'pan' : 'rotate'
  if (pointers.size === 2) {
    const [a, b] = [...pointers.values()]
    pinch = { d: Math.hypot(a.x - b.x, a.y - b.y), dist: cam.dist, cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 }
  }
}

function onPointerMove(e) {
  const prev = pointers.get(e.pointerId)
  if (!prev) {
    updateHover(e.offsetX, e.offsetY)
    return
  }
  const cur = { x: e.offsetX, y: e.offsetY }
  pointers.set(e.pointerId, cur)
  dragging.value = true
  if (pointers.size === 2 && pinch) {
    const [a, b] = [...pointers.values()]
    const d = Math.hypot(a.x - b.x, a.y - b.y)
    if (d > 0) cam.dist = clampDist(pinch.dist * (pinch.d / d))
    const cx = (a.x + b.x) / 2, cy = (a.y + b.y) / 2
    pan(cx - pinch.cx, cy - pinch.cy)
    pinch.cx = cx
    pinch.cy = cy
    moved += 10
    requestDraw()
    return
  }
  const dx = cur.x - prev.x, dy = cur.y - prev.y
  moved += Math.abs(dx) + Math.abs(dy)
  if (mode === 'pan') pan(dx, dy)
  else {
    cam.yaw += dx * 0.006
    cam.pitch = Math.max(PITCH_MIN, Math.min(PITCH_MAX, cam.pitch - dy * 0.006))
    if (topView.value && cam.pitch < PITCH_MAX - 0.05) topView.value = false
    const now = performance.now()
    if (lastMove) {
      const dt = Math.max(1, now - lastMove.t) / 1000
      lastMove = { t: now, vy: (dx * 0.006) / dt, vp: (-dy * 0.006) / dt }
    } else lastMove = { t: now, vy: 0, vp: 0 }
  }
  hover.value = null
  requestDraw()
}

function pan(dx, dy) {
  const s = focal() / cam.dist
  const d = fromCam(-dx / s, 0, dy / s)
  cam.target = [cam.target[0] + d[0], cam.target[1] + d[1], cam.target[2] + d[2]]
}

function onPointerUp(e) {
  const had = pointers.get(e.pointerId)
  pointers.delete(e.pointerId)
  if (pointers.size < 2) pinch = null
  if (pointers.size === 0) {
    dragging.value = false
    if (had && moved < 4) {
      const hit = hitAt(e.offsetX, e.offsetY)
      selected.value = hit ? { key: hit.key, title: hit.title, sub: hit.sub, p: hit.p, dist: hit.dist } : null
      requestDraw()
    } else if (mode === 'rotate' && lastMove && performance.now() - lastMove.t < 80 && !reducedMotion) {
      inertia = { vy: lastMove.vy, vp: lastMove.vp }
    }
  }
}

function onDblClick(e) {
  const hit = hitAt(e.offsetX, e.offsetY)
  if (hit) {
    selected.value = { key: hit.key, title: hit.title, sub: hit.sub, p: hit.p, dist: hit.dist }
    flyTo(hit)
  } else {
    // 空白處點兩下：往那裡拉近
    moveTo({ target: screenToWorld(e.offsetX, e.offsetY), dist: clampDist(cam.dist / 2.5) }, true)
  }
}

function onPointerLeave() {
  if (!pointers.size) hover.value = null
}

function onWheel(e) {
  // 往游標方向縮放：游標底下那一點縮放後還在游標底下
  const before = screenToWorld(e.offsetX, e.offsetY)
  const f = Math.exp(Math.max(-1, Math.min(1, e.deltaY * 0.0015)))
  const next = clampDist(cam.dist * f)
  const k = 1 - next / cam.dist
  cam.target = cam.target.map((v, i) => v + (before[i] - v) * k)
  cam.dist = next
  anim = null
  requestDraw()
}

function onKey(e) {
  const rot = { ArrowLeft: [-0.12, 0], ArrowRight: [0.12, 0], ArrowUp: [0, 0.08], ArrowDown: [0, -0.08] }
  if (rot[e.key]) {
    e.preventDefault()
    cam.yaw += rot[e.key][0]
    cam.pitch = Math.max(PITCH_MIN, Math.min(PITCH_MAX, cam.pitch + rot[e.key][1]))
    requestDraw()
  } else if (e.key === '+' || e.key === '=') {
    zoomBy(1 / 1.6)
  } else if (e.key === '-' || e.key === '_') {
    zoomBy(1.6)
  } else if (e.key === 'f' || e.key === 'F' || e.key === 'Home') {
    fit(true)
  } else if (e.key === 't' || e.key === 'T') {
    toggleTopView()
  } else if (e.key === 'Escape') {
    selected.value = null
    requestDraw()
  }
}

function hitAt(x, y) {
  let best = null
  for (let i = hits.length - 1; i >= 0; i--) {   // 後畫的（站點）優先
    const hh = hits[i]
    const d = Math.hypot(hh.x - x, hh.y - y)
    if (d <= hh.r && (!best || d < best.d)) best = { ...hh, d }
  }
  return best
}

function updateHover(x, y) {
  const hh = hitAt(x, y)
  hover.value = hh ? { x, y, title: hh.title, sub: hh.sub } : null
  if (canvasEl.value) canvasEl.value.style.cursor = hh ? 'pointer' : 'grab'
}

// ── 全螢幕 ──────────────────────────────────────────────────
function toggleFullscreen() {
  const el = wrapEl.value
  if (!el) return
  if (document.fullscreenElement) document.exitFullscreen?.()
  else if (el.requestFullscreen) el.requestFullscreen().catch(() => { fullscreen.value = !fullscreen.value })
  else fullscreen.value = !fullscreen.value   // 不支援全螢幕 API（例如 iPhone Safari）時改成鋪滿視窗
}
function onFullscreenChange() {
  fullscreen.value = document.fullscreenElement === wrapEl.value
  nextTick(resize)
}

// ── 尺寸、可見度 ────────────────────────────────────────────
let ro = null
let io = null
function resize() {
  const wrap = wrapEl.value, el = canvasEl.value
  if (!wrap || !el) return
  const w = wrap.clientWidth
  const h = wrap.clientHeight
  if (!w || !h) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  size = { w, h, dpr }
  el.width = Math.round(w * dpr)
  el.height = Math.round(h * dpr)
  el.style.width = `${w}px`
  el.style.height = `${h}px`
  requestDraw()
}

function onVisibility() {
  visible = document.visibilityState !== 'hidden' && inView
  lastFrame = 0
}
let inView = true

onMounted(() => {
  readColors()
  resize()
  fit()
  if (typeof ResizeObserver !== 'undefined' && wrapEl.value) {
    ro = new ResizeObserver(resize)
    ro.observe(wrapEl.value)
  }
  if (typeof IntersectionObserver !== 'undefined' && wrapEl.value) {
    io = new IntersectionObserver(([entry]) => { inView = entry.isIntersecting; onVisibility() })
    io.observe(wrapEl.value)
  }
  document.addEventListener('visibilitychange', onVisibility)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  raf = requestAnimationFrame(loop)
})
onBeforeUnmount(() => {
  ro?.disconnect()
  io?.disconnect()
  document.removeEventListener('visibilitychange', onVisibility)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  if (raf) cancelAnimationFrame(raf)
})

watch(fullscreen, () => nextTick(resize))
watch([() => props.plan, system], () => nextTick(() => {
  readColors()
  selected.value = null
  topView.value = false
  fit()
}))
</script>

<style scoped>
.rm3d__wrap {
  position: relative; height: 520px; user-select: none; -webkit-user-select: none;
  border: 1px solid var(--sf-border); border-radius: .6rem; overflow: hidden; background: #03060d;
}
.rm3d__wrap.is-full { position: fixed; inset: 0; z-index: 2000; height: auto; border-radius: 0; border: 0; }
.rm3d__wrap:fullscreen { height: 100%; border-radius: 0; border: 0; }
@media (max-width: 767.98px) { .rm3d__wrap { height: 380px; } }
.rm3d__canvas { display: block; touch-action: none; cursor: grab; outline: none; }
.rm3d__canvas:active { cursor: grabbing; }
.rm3d__canvas:focus-visible { box-shadow: inset 0 0 0 2px var(--sf-accent); }
.rm3d__system {
  position: absolute; left: .75rem; top: .6rem; pointer-events: none;
  font-weight: 700; font-size: 1.05rem; letter-spacing: .08em; text-transform: uppercase;
  color: #dbe6ff; text-shadow: 0 0 10px rgba(var(--sf-accent-rgb), .6);
}
.rm3d__tools { position: absolute; right: .6rem; top: .6rem; display: flex; flex-direction: column; gap: .3rem; }
.rm3d__tools .btn { width: 2.2rem; height: 2.2rem; padding: 0; display: inline-flex; align-items: center; justify-content: center; }
.rm3d__tip, .rm3d__info {
  position: absolute; max-width: 18rem; padding: .35rem .55rem;
  background: rgba(5, 10, 20, .88); border: 1px solid rgba(var(--sf-accent-rgb), .45); border-radius: .4rem;
  font-size: .9rem; color: #e6edf9; backdrop-filter: blur(4px);
}
.rm3d__tip { pointer-events: none; white-space: nowrap; }
.rm3d__info { left: .6rem; bottom: .6rem; right: 3.4rem; max-width: 24rem; }
.rm3d__info-title { overflow-wrap: anywhere; }
.rm3d__tip-sub { color: #9fb0cc; font-size: .85rem; }
.rm3d__scale {
  position: absolute; right: .7rem; bottom: .5rem; pointer-events: none;
  font-size: .8rem; color: #8fa3c4; text-shadow: 0 0 4px #000;
}
.rm3d__stop { cursor: pointer; border: 0; user-select: none; }
</style>
