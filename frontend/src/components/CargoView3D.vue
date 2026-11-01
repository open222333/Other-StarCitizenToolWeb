<!--
  貨艙網格的 3D 檢視（components/CargoLoader.vue 用）：每艘船的貨物網格（地板＋外框）和擺好的貨櫃，
  幾艘船並排。canvas 2D 自己做透視投影：拖拉旋轉、滾輪／兩指縮放；貨櫃依大小上色，頂面標 SCU。
  ships：[{ id, label, grids: [{x, y, z, width, height, length}], boxes: [{size, x, y, z, w, h, l}] }]
-->
<template>
  <div ref="wrap" class="cv3d">
    <canvas ref="canvas" class="cv3d__canvas" @pointerdown="onDown" @pointermove="onMove" @pointerup="onUp"
      @pointercancel="onUp" @wheel.prevent="onWheel" @dblclick="resetView"></canvas>
    <div class="cv3d__tools">
      <button type="button" class="btn btn-sm btn-info" aria-label="俯視" @click="topView"><i class="bi bi-arrow-down-square"></i></button>
      <button type="button" class="btn btn-sm btn-info" aria-label="重設視角" @click="resetView"><i class="bi bi-arrows-fullscreen"></i></button>
    </div>
    <div class="cv3d__legend">
      <span v-for="s in SIZES" :key="s" class="cv3d__key"><i :style="{ background: COLORS[s] }"></i>{{ s }}</span>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { SIZES } from '@/utils/cargoPack'

const props = defineProps({
  ships: { type: Array, default: () => [] },
})

// 貨櫃顏色（依 SCU 大小）
const COLORS = { 1: '#8fa3b8', 2: '#d88cb0', 4: '#7fc69a', 8: '#e3b65c', 16: '#6fa8e6', 24: '#ad94e0', 32: '#c3cbd6' }
const GAP = 6

const wrap = ref(null)
const canvas = ref(null)
const cam = { yaw: -0.7, pitch: 0.62, dist: 60, target: [0, 0, 0] }
let scene = { ships: [], center: [0, 0, 0], radius: 10 }
let size = { w: 300, h: 300 }

const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
const norm = (a) => { const n = Math.hypot(...a) || 1; return [a[0] / n, a[1] / n, a[2] / n] }

// 並排：每艘船往 x 方向接在前一艘後面
function buildScene() {
  let offset = 0
  const ships = props.ships.map((s) => {
    const grids = s.grids || []
    const minX = Math.min(...grids.map(g => g.x), 0)
    const maxX = Math.max(...grids.map(g => g.x + g.width), 1)
    const minZ = Math.min(...grids.map(g => g.z), 0)
    const maxZ = Math.max(...grids.map(g => g.z + g.length), 1)
    const dx = offset - minX
    offset += maxX - minX + GAP
    return { ...s, dx, minZ, maxZ, cx: dx + (minX + maxX) / 2 }
  })
  const maxZ = Math.max(1, ...ships.map(s => s.maxZ))
  const minZ = Math.min(0, ...ships.map(s => s.minZ))
  const width = Math.max(1, offset - GAP)
  scene = { ships, center: [width / 2, 2, (minZ + maxZ) / 2], radius: Math.max(8, Math.hypot(width, maxZ - minZ) / 2) }
}

function resetView() {
  cam.yaw = -0.7
  cam.pitch = 0.62
  cam.target = [...scene.center]
  cam.dist = fitDist()
  draw()
}
// 整個場景放得進畫面的距離（直立的畫面寬度比較窄，要退遠一點）
const fitDist = () => scene.radius * (size.w < size.h ? 2.4 : 1.8)
function topView() {
  cam.pitch = 1.45
  cam.yaw = 0
  draw()
}

function camera() {
  const cp = Math.cos(cam.pitch)
  const eye = [cam.target[0] + cam.dist * cp * Math.sin(cam.yaw), cam.target[1] + cam.dist * Math.sin(cam.pitch),
    cam.target[2] + cam.dist * cp * Math.cos(cam.yaw)]
  const f = norm(sub(cam.target, eye))
  const r = norm(cross(f, [0, 1, 0]))
  const u = cross(r, f)
  return { eye, f, r, u, focal: Math.min(size.w, size.h) * 1.1 }
}

function project(c, p) {
  const v = sub(p, c.eye)
  const z = dot(v, c.f)
  if (z < 0.1) return null
  return [size.w / 2 + dot(v, c.r) * c.focal / z, size.h / 2 - dot(v, c.u) * c.focal / z]
}

function cssVar(name, fallback) {
  const v = getComputedStyle(wrap.value || document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

function shade(hex, k) {
  const n = parseInt(hex.slice(1), 16)
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(v => Math.max(0, Math.min(255, Math.round(v * k))))
  return `rgb(${c[0]}, ${c[1]}, ${c[2]})`
}

// 一個長方體的六個面：[頂點, 法向量, 亮度]
function cuboidFaces(x, y, z, w, h, l) {
  const X = x + w, Y = y + h, Z = z + l
  return [
    [[[x, Y, z], [X, Y, z], [X, Y, Z], [x, Y, Z]], [0, 1, 0], 1.08],
    [[[x, y, z], [x, y, Z], [X, y, Z], [X, y, z]], [0, -1, 0], 0.5],
    [[[x, y, Z], [x, Y, Z], [X, Y, Z], [X, y, Z]], [0, 0, 1], 0.86],
    [[[x, y, z], [X, y, z], [X, Y, z], [x, Y, z]], [0, 0, -1], 0.74],
    [[[X, y, z], [X, y, Z], [X, Y, Z], [X, Y, z]], [1, 0, 0], 0.8],
    [[[x, y, z], [x, Y, z], [x, Y, Z], [x, y, Z]], [-1, 0, 0], 0.68],
  ]
}

function poly(ctx, pts) {
  ctx.beginPath()
  pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])))
  ctx.closePath()
}

function draw() {
  const cv = canvas.value
  if (!cv) return
  const dpr = window.devicePixelRatio || 1
  const ctx = cv.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  const text = cssVar('--sf-text', '#dce6f2')
  const muted = cssVar('--sf-text-muted', '#8a9bb0')
  ctx.fillStyle = cssVar('--sf-panel', '#121a26')
  ctx.fillRect(0, 0, size.w, size.h)
  const c = camera()

  // 地面格線
  ctx.strokeStyle = cssVar('--sf-border', 'rgba(255,255,255,.08)')
  ctx.globalAlpha = 0.5
  ctx.lineWidth = 1
  const ext = Math.ceil(scene.radius * 1.6)
  for (let i = -ext; i <= ext; i += 2) {
    const a = project(c, [scene.center[0] + i, 0, scene.center[2] - ext])
    const b = project(c, [scene.center[0] + i, 0, scene.center[2] + ext])
    const d = project(c, [scene.center[0] - ext, 0, scene.center[2] + i])
    const e = project(c, [scene.center[0] + ext, 0, scene.center[2] + i])
    if (a && b) { ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke() }
    if (d && e) { ctx.beginPath(); ctx.moveTo(...d); ctx.lineTo(...e); ctx.stroke() }
  }
  ctx.globalAlpha = 1

  // 網格地板與外框
  for (const s of scene.ships) {
    for (const g of s.grids || []) {
      const x = g.x + s.dx
      const floor = [[x, g.y, g.z], [x + g.width, g.y, g.z], [x + g.width, g.y, g.z + g.length], [x, g.y, g.z + g.length]]
        .map(p => project(c, p))
      if (floor.every(Boolean)) {
        poly(ctx, floor)
        ctx.fillStyle = g.unsecured ? 'rgba(220, 120, 160, .22)' : 'rgba(140, 160, 190, .22)'
        ctx.fill()
        ctx.strokeStyle = muted
        ctx.lineWidth = 1
        ctx.stroke()
      }
    }
  }

  // 貨櫃的面：由遠到近畫
  const faces = []
  for (const s of scene.ships) {
    for (const b of s.boxes || []) {
      for (const [pts, n, k] of cuboidFaces(b.x + s.dx, b.y, b.z, b.w, b.h, b.l)) {
        const center = pts.reduce((a, p) => [a[0] + p[0] / 4, a[1] + p[1] / 4, a[2] + p[2] / 4], [0, 0, 0])
        if (dot(n, sub(c.eye, center)) <= 0) continue
        const d = sub(center, c.eye)
        faces.push({ pts, k, size: b.size, top: n[1] === 1, depth: dot(d, d) })
      }
    }
  }
  faces.sort((a, b) => b.depth - a.depth)
  ctx.lineWidth = 1
  ctx.font = '600 12px system-ui, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  for (const f of faces) {
    const sp = f.pts.map(p => project(c, p))
    if (!sp.every(Boolean)) continue
    poly(ctx, sp)
    ctx.fillStyle = shade(COLORS[f.size] || '#999999', f.k)
    ctx.fill()
    ctx.strokeStyle = 'rgba(20, 28, 40, .55)'
    ctx.stroke()
    if (f.top) {
      const cx = sp.reduce((a, p) => a + p[0], 0) / 4, cy = sp.reduce((a, p) => a + p[1], 0) / 4
      const span = Math.hypot(sp[0][0] - sp[2][0], sp[0][1] - sp[2][1])
      if (span > 22) {
        ctx.fillStyle = 'rgba(15, 22, 32, .85)'
        ctx.fillText(String(f.size), cx, cy)
      }
    }
  }

  // 船名（容量）
  ctx.font = '600 14px system-ui, sans-serif'
  for (const s of scene.ships) {
    const p = project(c, [s.cx, 0, s.maxZ + 2])
    if (!p) continue
    ctx.fillStyle = text
    ctx.fillText(s.label, p[0], p[1])
  }
}

// ── 操作：拖拉旋轉、滾輪／兩指縮放 ──
const pointers = new Map()
let pinch = 0
function onDown(e) {
  canvas.value.setPointerCapture(e.pointerId)
  pointers.set(e.pointerId, [e.clientX, e.clientY])
}
function onMove(e) {
  if (!pointers.has(e.pointerId)) return
  const prev = pointers.get(e.pointerId)
  pointers.set(e.pointerId, [e.clientX, e.clientY])
  if (pointers.size === 2) {
    const [a, b] = [...pointers.values()]
    const d = Math.hypot(a[0] - b[0], a[1] - b[1])
    if (pinch) cam.dist = Math.max(4, Math.min(scene.radius * 8, cam.dist * pinch / d))
    pinch = d
  } else {
    cam.yaw -= (e.clientX - prev[0]) * 0.008
    cam.pitch = Math.max(0.08, Math.min(1.5, cam.pitch + (e.clientY - prev[1]) * 0.006))
  }
  draw()
}
function onUp(e) {
  pointers.delete(e.pointerId)
  if (pointers.size < 2) pinch = 0
}
function onWheel(e) {
  cam.dist = Math.max(4, Math.min(scene.radius * 8, cam.dist * (e.deltaY > 0 ? 1.12 : 0.89)))
  draw()
}

function resize() {
  const el = wrap.value, cv = canvas.value
  if (!el || !cv) return
  const dpr = window.devicePixelRatio || 1
  size = { w: el.clientWidth, h: el.clientHeight }
  cv.width = Math.round(size.w * dpr)
  cv.height = Math.round(size.h * dpr)
  cv.style.width = `${size.w}px`
  cv.style.height = `${size.h}px`
  draw()
}

let ro = null
let lastIds = ''
watch(() => props.ships, () => {
  buildScene()
  // 船的組合變了才重設視角；只是貨櫃變了就維持目前角度
  const ids = props.ships.map(s => s.id).join(',')
  if (ids !== lastIds) {
    lastIds = ids
    resetView()
  } else {
    draw()
  }
}, { deep: true })

onMounted(() => {
  buildScene()
  lastIds = props.ships.map(s => s.id).join(',')
  ro = new ResizeObserver(resize)
  ro.observe(wrap.value)
  resize()
  resetView()
})
onBeforeUnmount(() => ro?.disconnect())
</script>

<style scoped>
.cv3d { position: relative; width: 100%; height: clamp(22rem, 60vh, 40rem); border-radius: .5rem; overflow: hidden;
  border: 1px solid var(--sf-border); }
.cv3d__canvas { display: block; touch-action: none; cursor: grab; user-select: none; }
.cv3d__canvas:active { cursor: grabbing; }
.cv3d__tools { position: absolute; top: .5rem; right: .5rem; display: flex; gap: .35rem; }
.cv3d__legend { position: absolute; left: .5rem; bottom: .5rem; display: flex; flex-wrap: wrap; gap: .25rem .6rem;
  padding: .25rem .5rem; border-radius: .4rem; background: rgba(0, 0, 0, .35); color: #fff; font-size: 1rem; }
.cv3d__key { display: inline-flex; align-items: center; gap: .25rem; }
.cv3d__key i { width: .8rem; height: .8rem; border-radius: .15rem; display: inline-block; }
</style>
