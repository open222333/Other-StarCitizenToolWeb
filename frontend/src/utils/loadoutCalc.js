// 配裝模擬的純計算（玩家頁「配裝模擬」，見 components/LoadoutSimulator.vue）。
// 資料：GET /item/loadout/ships/<id>（掛點樹 slots＋items）、/item/loadout/items（配件），見 src/models/loadout.py。
// 槽位 node：{ id, port, types, min, max, editable, item, children, tags?, slaveable?, name?, item_class_name? }

/** 槽位分區（畫面上的卡片），依頂層槽位決定 */
export const SECTIONS = [
  { key: 'pilot', label: '駕駛武器', icon: 'bi bi-crosshair' },
  { key: 'manned', label: '有人砲塔', icon: 'bi bi-person-video' },
  { key: 'remote', label: '遙控砲塔', icon: 'bi bi-joystick' },
  { key: 'pdc', label: '點防禦', icon: 'bi bi-shield-shaded' },
  { key: 'missile', label: '飛彈與魚雷', icon: 'bi bi-rocket' },
  { key: 'shield', label: '護盾', icon: 'bi bi-shield-fill' },
  { key: 'power', label: '電源', icon: 'bi bi-lightning-charge' },
  { key: 'cooler', label: '冷卻', icon: 'bi bi-snow' },
  { key: 'quantum', label: '量子引擎', icon: 'bi bi-stars' },
  { key: 'radar', label: '雷達', icon: 'bi bi-broadcast' },
  { key: 'cm', label: '反制', icon: 'bi bi-asterisk' },
  { key: 'utility', label: '採礦／打撈／牽引', icon: 'bi bi-tools' },
]

/** 武器傷害分組（駕駛、有人砲塔、遙控砲塔、點防禦） */
export const WEAPON_GROUPS = ['pilot', 'manned', 'remote', 'pdc']

const base = t => (t || '').split('.')[0]
const sub = t => (t || '').split('.')[1] || ''

/** 配件種類符不符合槽位（WeaponGun.Gun、Turret…；配件子類是 UNDEFINED 時只比主類） */
export function typeMatch(item, types) {
  if (!item) return false
  return (types || []).some(t => {
    if (base(t) !== item.type) return false
    const s = sub(t)
    return !s || !item.sub_type || item.sub_type === 'UNDEFINED' || item.sub_type === s
  })
}

/** 配件能不能裝進這一格：種類、尺寸、需要的標籤（tags＝船本身＋上層槽位提供的標籤，小寫） */
export function fits(item, node, tags) {
  if (!typeMatch(item, node.types)) return false
  const size = item.size || 0
  if (size < (node.min || 0) || size > (node.max || node.min || 0)) return false
  const need = item.required_tags || []
  return need.every(t => tags.has(String(t).toLowerCase()))
}

/** 某一格可用的標籤：船本身的 tags＋上層各格的 PortTags（例如點防禦砲塔的 PDC） */
export function tagsFor(ship, path) {
  const out = new Set((ship?.tags || []).map(t => String(t).toLowerCase()))
  for (const n of path || []) for (const t of n.tags || []) out.add(String(t).toLowerCase())
  return out
}

/** 換上配件後重建子槽：同名子槽原本的配件裝得下就保留，否則用配件的預設 */
export function buildChildren(parentId, item, prev, itemOf, tags) {
  return (item?.ports || []).map(p => {
    const old = (prev || []).find(c => c.port === p.port)
    const node = { id: `${parentId}/${p.port}`, port: p.port, types: p.types, min: p.min, max: p.max,
      editable: p.editable, item: null, children: [] }
    const keep = old?.item && itemOf(old.item)
    node.item = keep && fits(keep, node, tags) ? old.item : (p.default || null)
    const child = itemOf(node.item)
    node.children = child ? buildChildren(node.id, child, old?.children, itemOf, tags) : []
    return node
  })
}

/** 換配件（null＝卸下）。nodes 是同一組的幾格，全部一起換 */
export function equip(nodes, itemId, itemOf, tagsOf) {
  for (const n of nodes) {
    n.item = itemId || null
    const it = itemOf(n.item)
    n.children = it ? buildChildren(n.id, it, n.children, itemOf, tagsOf(n)) : []
  }
}

/** 頂層槽位屬於哪一區 */
export function sectionOf(node, itemOf) {
  const it = itemOf(node.item)
  const types = node.types || []
  const has = b => types.some(t => base(t) === b) || it?.type === b
  if ((node.tags || []).some(t => String(t).toUpperCase() === 'PDC') || it?.sub_type === 'PDCTurret') return 'pdc'
  if (has('TurretBase') || it?.sub_type === 'MannedTurret' || types.some(t => sub(t) === 'MannedTurret')) return 'manned'
  if (has('MissileLauncher') || has('BombLauncher') || has('Missile') || has('Bomb')) return 'missile'
  if (has('Shield')) return 'shield'
  if (has('PowerPlant')) return 'power'
  if (has('Cooler')) return 'cooler'
  if (has('QuantumDrive') || has('JumpDrive')) return 'quantum'
  if (has('Radar')) return 'radar'
  if (has('WeaponDefensive')) return 'cm'
  if (has('WeaponMining') || has('SalvageHead') || has('TractorBeam')) return 'utility'
  // 機鼻／機腹的球形砲塔、雲台都是駕駛在打；上下方的遙控砲塔才算遙控（可連動的見 slaveable）
  const remote = ['TopTurret', 'BottomTurret', 'MissileTurret', 'Utility']
  if (it?.type === 'Turret' && remote.includes(it.sub_type)) return 'remote'
  if (types.some(t => base(t) === 'Turret' && remote.includes(sub(t)))) return 'remote'
  if (has('WeaponGun') || has('Turret')) return 'pilot'
  return 'utility'
}

/** 樹裡每一格（深度優先），callback(node, root) */
export function walk(nodes, fn, root = null) {
  for (const n of nodes || []) {
    if (fn(n, root || n) === false) continue      // 回傳 false＝不往下走
    walk(n.children, fn, root || n)
  }
}

/** 整艘船目前配裝的總數值 */
export function summarize(ship, slots, itemOf, shieldEff = null) {
  // shieldEff：{槽位 id: 電源效率}（電源分配給護盾的格數，影響回充；見 utils/loadoutPower.js）
  const w = Object.fromEntries(WEAPON_GROUPS.map(k => [k, { alpha: 0, dps: 0, sustained: 0, count: 0 }]))
  const missiles = { count: 0, damage: 0, byName: new Map() }
  const shield = { hp: 0, regen: 0, count: 0, absorption: null, resistance: null }
  const power = { gen: 0 }
  const cooling = { gen: 0 }
  const shields = []
  let qd = null
  let slaved = { alpha: 0, dps: 0, sustained: 0 }
  for (const root of slots || []) {
    const sec = sectionOf(root, itemOf)
    walk([root], n => {
      const it = itemOf(n.item)
      if (!it) return
      const s = it.stats || {}
      if (it.type === 'WeaponGun') {
        const g = w[WEAPON_GROUPS.includes(sec) ? sec : 'pilot']
        g.alpha += s.alpha || 0
        g.dps += s.dps || 0
        g.sustained += s.sustained || 0
        g.count++
        if (sec === 'remote' && root.slaveable) {
          slaved.alpha += s.alpha || 0
          slaved.dps += s.dps || 0
          slaved.sustained += s.sustained || 0
        }
      } else if (it.type === 'Missile' || it.type === 'Bomb') {
        missiles.count++
        // 集束飛彈：子彈頭的傷害算在母彈裡，子彈頭本身不另外算一顆
        let dmg = s.damage_total || 0
        walk(n.children, c => { const ci = itemOf(c.item); if (ci && (ci.type === 'Missile' || ci.type === 'Bomb')) dmg += ci.stats?.damage_total || 0 })
        missiles.damage += dmg
        const m = missiles.byName.get(it.id) || { item: it, count: 0 }
        m.count++
        missiles.byName.set(it.id, m)
        return false
      } else if (it.type === 'Shield') {
        shields.push({ it, id: n.id })
      } else if (it.type === 'QuantumDrive' && !qd) {
        qd = it
      }
      if (s.power_gen) power.gen += s.power_gen
      if (s.coolant_gen) cooling.gen += s.coolant_gen
    })
  }
  // 同時運作的護盾有上限（ship.shield_slots），取最強的幾個，其餘算備用
  shields.sort((a, b) => (b.it.stats?.hp || 0) - (a.it.stats?.hp || 0))
  const activeShields = ship?.shield_slots > 0 ? shields.slice(0, ship.shield_slots) : shields
  for (const { it, id } of activeShields) {
    shield.hp += it.stats?.hp || 0
    shield.regen += (it.stats?.regen || 0) * (shieldEff ? shieldEff[id] ?? 1 : 1)
    shield.regenMax = (shield.regenMax || 0) + (it.stats?.regen || 0)
    shield.absorption ||= it.stats?.absorption || null
    shield.resistance ||= it.stats?.resistance || null
  }
  shield.count = activeShields.length
  shield.spare = shields.length - activeShields.length
  const sum = k => WEAPON_GROUPS.reduce((a, g) => a + w[g][k], 0)
  const fuel = ship?.fuel?.quantum
  const req = qd?.stats?.fuel_req
  return {
    weapons: w,
    // 駕駛能開火的：駕駛武器＋可連動的遙控砲塔
    pilotTotal: { alpha: w.pilot.alpha + slaved.alpha, dps: w.pilot.dps + slaved.dps,
      sustained: w.pilot.sustained + slaved.sustained },
    total: { alpha: sum('alpha'), dps: sum('dps'), sustained: sum('sustained') },
    missiles: { count: missiles.count, damage: missiles.damage, kinds: [...missiles.byName.values()] },
    shield,
    power,
    cooling,
    quantum: qd ? {
      item: qd, speed: qd.stats?.speed, spool: qd.stats?.spool, cooldown: qd.stats?.cooldown,
      // 油箱 ÷ 每 Gm 油耗（fuel_req × 1000）＝可跑幾 Gm
      range_gm: fuel && req ? fuel / (req * 1000) : null,
    } : null,
  }
}

/** 同一層裡一模一樣的槽位（種類、尺寸、能不能換、裝的東西連子槽都一樣）合成一組顯示「N×」 */
export function signature(node, itemOf) {
  // 左右兩邊的雲台常常是不同 UUID 的同款配件，用名稱＋尺寸比
  const it = itemOf ? itemOf(node.item) : null
  return JSON.stringify([node.types, node.min, node.max, node.editable, it ? [it.name, it.size, it.type] : node.name || node.item,
    (node.children || []).map(c => signature(c, itemOf))])
}

export function groupNodes(nodes, itemOf) {
  const map = new Map()
  for (const n of nodes || []) {
    const key = signature(n, itemOf)
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(n)
  }
  return [...map.values()]
}

/** 一組槽位的子槽，依位置對齊再分組：回傳 [[node…]…] */
export function childGroups(members, itemOf) {
  const first = members[0]
  return groupNodes(first?.children, itemOf).map(g => {
    const idx = g.map(c => first.children.indexOf(c))
    return members.flatMap(m => idx.map(i => m.children[i]).filter(Boolean))
  })
}

// ── 存成連結：只記跟預設不同的格子 ──

export function itemMap(slots) {
  const out = {}
  walk(slots, n => { out[n.id] = n.item || '' })
  return out
}

export function diff(defaults, slots) {
  const now = itemMap(slots)
  return Object.entries(now).filter(([id, item]) => (defaults[id] ?? null) !== item)
    .sort((a, b) => a[0].split('/').length - b[0].split('/').length)
}

export function encodeChanges(changes) {
  if (!changes.length) return ''
  // 槽位名稱幾乎都是 hardpoint_ 開頭，縮成 ~ 讓連結短一點
  const short = changes.map(([id, item]) => [id.replace(/hardpoint_/g, '~'), item])
  const bytes = new TextEncoder().encode(JSON.stringify(short))
  let bin = ''
  bytes.forEach(b => { bin += String.fromCharCode(b) })
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

export function decodeChanges(text) {
  try {
    const b64 = String(text || '').replace(/-/g, '+').replace(/_/g, '/')
    const bin = atob(b64 + '==='.slice((b64.length + 3) % 4))
    const v = JSON.parse(new TextDecoder().decode(Uint8Array.from(bin, c => c.charCodeAt(0))))
    return Array.isArray(v) ? v.filter(x => Array.isArray(x) && typeof x[0] === 'string' && typeof x[1] === 'string')
      .map(([id, item]) => [id.replace(/~/g, 'hardpoint_'), item]) : []
  } catch {
    return []
  }
}

export function findNode(slots, id) {
  let hit = null
  walk(slots, n => { if (!hit && n.id === id) hit = n })
  return hit
}

/** 一格從上到下的路徑（含自己），算標籤用 */
export function pathTo(slots, id) {
  const stack = []
  const visit = nodes => {
    for (const n of nodes || []) {
      stack.push(n)
      if (n.id === id || visit(n.children)) return true
      stack.pop()
    }
    return false
  }
  return visit(slots) ? [...stack] : []
}
