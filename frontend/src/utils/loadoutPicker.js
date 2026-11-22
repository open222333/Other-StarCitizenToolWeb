// 配裝模擬「更換配件」視窗（components/LoadoutPicker.vue）的欄位與篩選：依配件種類決定表格欄位、篩選分組。
import { fmtNum } from './navFormat.js'

export const DMG_LABEL = { physical: '實彈', energy: '能量', distortion: '扭曲', thermal: '熱能', biochemical: '生化', stun: '暈眩' }
const DMG_SHORT = { physical: '實彈', energy: '能量', distortion: '扭曲' }
export const CLASS_LABEL = { Military: '軍用', Civilian: '民用', Industrial: '工業', Stealth: '隱形', Competition: '競賽' }

// 武器類型：資料沒有欄位，從 class name 判斷（HRST_LaserScatterGun_S3 → 散彈）
const WEAPON_KINDS = [['cannon', '加農'], ['repeater', '連發'], ['gatling', '格林'], ['scattergun', '散彈'],
  ['massdriver', '質量投射'], ['beam', '光束'], ['rocket', '火箭']]
export function weaponKind(it) {
  const cn = (it.class_name || '').toLowerCase()
  if (it.sub_type === 'Rocket' || /rpod|rocket/.test(cn)) return 'rocket'
  for (const [k] of WEAPON_KINDS) if (cn.includes(k)) return k
  return 'other'
}
const WEAPON_KIND_LABEL = Object.fromEntries([...WEAPON_KINDS, ['other', '其他']])
export const weaponKindLabel = k => WEAPON_KIND_LABEL[k] || k

/** 武器主要傷害類型（傷害最大的那一種） */
export function dmgKind(it) {
  const d = it.stats?.damage || {}
  let best = ''
  for (const [k, v] of Object.entries(d)) if (v && (!best || v > d[best])) best = k
  return best
}
export const dmgLabel = k => DMG_SHORT[k] || DMG_LABEL[k] || ''

const num = (v, d = 0) => (v == null || Number.isNaN(v) ? '—' : fmtNum(v, d))
const pct = v => (v == null ? '—' : `${fmtNum(v * 100)}%`)
const col = (key, label, get, fmt = v => num(v), opt = {}) => ({ key, label, get, fmt, ...opt })
const power = col('power', '耗電', it => it.stats?.power_use?.[1] ?? null, v => num(v, v < 1 ? 1 : 0))
const em = col('em', 'EM', it => it.stats?.em ?? null)
const hp = col('hp', '耐久', it => it.hp ?? null)

/** 各種類的欄位：key、label、get（排序用的數值）、fmt（顯示）；first＝預設排序欄（大到小） */
const COLS = {
  WeaponGun: [
    col('sustained', '持續 DPS', it => it.stats?.sustained ?? null, undefined, { first: true }),
    col('dps', '爆發 DPS', it => it.stats?.dps ?? null),
    col('alpha', '單發', it => it.stats?.alpha ?? null, v => num(v, v < 10 ? 1 : 0)),
    col('rpm', '射速', it => it.stats?.rpm ?? null),
    col('range', '射程', it => it.stats?.range ?? null),
    col('speed', '彈速', it => it.stats?.speed ?? null),
    col('pen', '穿透', it => it.stats?.pen_distance ?? null, v => num(v, 2)),
    power, em,
    col('ammo', '彈藥', it => it.stats?.ammo ?? null),
    hp,
  ],
  Shield: [
    col('shp', '護盾 HP', it => it.stats?.hp ?? null, undefined, { first: true }),
    col('regen', '回充／秒', it => it.stats?.regen ?? null),
    col('delay', '受擊延遲', it => it.stats?.damaged_delay ?? null, v => num(v, 1)),
    col('down', '擊破延遲', it => it.stats?.downed_delay ?? null, v => num(v, 1)),
    col('abs', '物理吸收', it => it.stats?.absorption?.physical?.[1] ?? null, pct),
    power, em, hp,
  ],
  Cooler: [
    col('cool', '冷卻', it => it.stats?.coolant_gen ?? null, undefined, { first: true }),
    power, em, col('ir', 'IR', it => it.stats?.ir ?? null), hp,
  ],
  PowerPlant: [
    col('gen', '發電', it => it.stats?.power_gen ?? null, undefined, { first: true }),
    em, hp,
  ],
  QuantumDrive: [
    col('qspeed', '速度 km/s', it => it.stats?.speed ?? null, v => num(v == null ? v : v / 1000), { first: true }),
    col('spool', '啟動 秒', it => it.stats?.spool ?? null, v => num(v, 1)),
    col('qcd', '冷卻 秒', it => it.stats?.cooldown ?? null, v => num(v, 1)),
    col('fuel', '每 Gm 油耗', it => it.stats?.fuel_req ?? null, v => num(v == null ? v : v * 1000, 2)),
    power, em, hp,
  ],
  Radar: [
    col('sem', 'EM 靈敏度', it => it.stats?.sensitivity?.em ?? null, pct, { first: true }),
    col('sir', 'IR 靈敏度', it => it.stats?.sensitivity?.ir ?? null, pct),
    col('scs', 'CS 靈敏度', it => it.stats?.sensitivity?.cs ?? null, pct),
    power, em, hp,
  ],
  Missile: [
    col('mdmg', '傷害', it => it.stats?.damage_total ?? null, undefined, { first: true }),
    col('lock', '鎖定 秒', it => it.stats?.lock_time ?? null, v => num(v, 1)),
    col('mspeed', '速度', it => it.stats?.speed ?? null),
    col('lrange', '鎖定距離 km', it => it.stats?.lock_range?.[1] ?? null, v => num(v == null ? v : v / 1000, 1)),
  ],
}
COLS.Bomb = COLS.Missile

/** 主要種類：選了「種類」篩選就是它，否則是數量最多的那一種（砲塔槽可裝武器或雲台，以武器為主） */
export function mainType(items, picked = '') {
  if (picked) return picked
  const counts = new Map()
  for (const it of items) counts.set(it.type, (counts.get(it.type) || 0) + 1)
  return [...counts].sort((a, b) => b[1] - a[1])[0]?.[0] || ''
}

/** 欄位：依主要種類（其他種類的配件在這些欄位顯示「—」）；沒有專屬欄位的種類用「主要數值」 */
export function columnsFor(type, primary) {
  if (COLS[type]) return COLS[type]
  return [col('primary', '主要數值', it => primary(it)?.value ?? null, (v, it) => primary(it)?.text ?? '—', { first: true })]
}

/** 篩選分組：[{ key, label, get, options: [{ value, label, count }] }]；選項少於 2 個的分組不顯示 */
export function filterGroups(items, typeLabel) {
  const groups = []
  const add = (key, label, get, labelOf, byValue = false) => {
    const counts = new Map()
    for (const it of items) {
      const v = get(it)
      if (v) counts.set(v, (counts.get(v) || 0) + 1)
    }
    if (counts.size < 2) return
    groups.push({ key, label, get,
      options: [...counts].map(([value, count]) => ({ value, label: labelOf(value), count }))
        .sort((a, b) => (byValue ? String(a.value).localeCompare(String(b.value)) : b.count - a.count)) })
  }
  add('type', '種類', it => it.type, v => typeLabel([v]))
  const types = new Set(items.map(it => it.type))
  if (types.has('WeaponGun')) {
    add('dmg', '傷害類型', it => (it.type === 'WeaponGun' ? dmgKind(it) : ''), dmgLabel)
    add('wkind', '武器類型', it => (it.type === 'WeaponGun' ? weaponKind(it) : ''), weaponKindLabel)
  }
  add('size', '尺寸', it => (it.size != null ? String(it.size) : ''), v => `S${v}`, true)
  add('class', '分類', it => it.item_class || '', v => CLASS_LABEL[v] || v)
  add('grade', '等級', it => it.grade || '', v => v, true)
  if (types.has('Missile') || types.has('Bomb')) {
    add('track', '追蹤', it => it.stats?.tracking || '', v => ({ Electromagnetic: '電磁', Infrared: '紅外線', CrossSection: '截面' }[v] || v))
  }
  return groups
}
