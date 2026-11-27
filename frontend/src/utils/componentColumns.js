// 資料庫 › 飛船組件（components/ShipComponentDatabase.vue）的欄位：每種組件一組專屬參數＋共用參數。
// 資料是配裝模擬同一份（/item/loadout/items，後端 src/scdata_loadout.py 的 map_ship_item）；
// 欄位只要那個種類有任何一筆有值就顯示（visibleColumns），整欄空的不顯示。
// 每欄：key、label、get（排序用的原始值）、fmt（顯示）、unit（表頭單位）。
import { fmtNum } from './navFormat.js'
import { DMG_LABEL, TRACK_LABEL } from './loadoutConst.js'

const isNum = v => typeof v === 'number' && !Number.isNaN(v)
const num = (d = 0) => v => (isNum(v) ? fmtNum(v, d) : '—')
const auto = v => (isNum(v) ? fmtNum(v, Math.abs(v) < 10 && !Number.isInteger(v) ? 2 : 0) : '—')
const pct = v => (isNum(v) ? `${fmtNum(v * 100, Math.abs(v) < 0.1 ? 1 : 0)}%` : '—')
const scaled = (div, d = 0) => v => (isNum(v) ? fmtNum(v / div, d) : '—')
const text = v => (v == null || v === '' ? '—' : String(v))
const range = d => v => (Array.isArray(v) && v.some(isNum) ? v.map(x => (isNum(x) ? fmtNum(x, d) : '—')).join('–') : '—')

// left＝文字欄靠左（數字欄靠右）
const col = (key, label, get, fmt = auto, unit = '', left = false) => ({ key, label, get, fmt, unit, left })
const textCol = (key, label, get, fmt = text) => col(key, label, get, fmt, '', true)
// 手機卡片上佔整列的長文字欄
const wideCol = (...a) => ({ ...textCol(...a), wide: true })
const st = k => it => it?.stats?.[k] ?? null

const DMG_KEYS = Object.keys(DMG_LABEL)
/** 傷害：各類型有值的才列（物理 12／能量 30） */
function dmgText(d) {
  const parts = DMG_KEYS.filter(k => isNum(d?.[k]) && d[k]).map(k => `${DMG_LABEL[k]} ${fmtNum(d[k], d[k] < 10 ? 1 : 0)}`)
  return parts.length ? parts.join('／') : '—'
}
const mainDmg = d => DMG_KEYS.filter(k => isNum(d?.[k]) && d[k]).sort((a, b) => d[b] - d[a])[0] || null
/** 護盾吸收／抗性：{physical: [min, max]} 的各類型（最大值） */
const rangeMax = (key, k) => it => {
  const v = it?.stats?.[key]?.[k]
  return Array.isArray(v) ? (isNum(v[1]) ? v[1] : null) : (isNum(v) ? v : null)
}

const WEAPON = [
  col('sustained', '持續 DPS', st('sustained')),
  col('dps', '爆發 DPS', st('dps')),
  col('alpha', '單發傷害', st('alpha')),
  wideCol('damage', '傷害類型', it => mainDmg(it?.stats?.damage), (v, it) => dmgText(it?.stats?.damage)),
  textCol('fire_mode', '射擊模式', st('fire_mode')),
  col('rpm', '射速', st('rpm'), num(), '發/分'),
  col('range', '射程', st('range'), num(), 'm'),
  col('speed', '彈速', st('speed'), num(), 'm/s'),
  col('ammo', '彈藥', st('ammo'), num()),
  col('pen_distance', '穿透距離', st('pen_distance'), num(2), 'm'),
  col('pen_near', '穿透近端半徑', st('pen_near'), num(2), 'm'),
  col('pen_far', '穿透遠端半徑', st('pen_far'), num(2), 'm'),
  col('overheat_s', '過熱前連射', st('overheat_s'), num(1), '秒'),
  col('overheat_fix_s', '過熱恢復', st('overheat_fix_s'), num(1), '秒'),
  col('cap_load', '電容容量', st('cap_load'), num()),
  col('cap_regen', '電容回充', st('cap_regen'), auto, '/秒'),
  col('cap_fire_s', '滿電連射', st('cap_fire_s'), num(1), '秒'),
  col('cap_recharge_s', '電容充滿', st('cap_recharge_s'), num(1), '秒'),
]
const MINING = [
  col('mining_power', '採礦功率', st('mining_power')),
  col('mining_min_power', '最小功率', st('mining_min_power')),
  col('optimal_range', '最佳距離', st('optimal_range'), num(), 'm'),
  col('max_range', '最大距離', st('max_range'), num(), 'm'),
  col('module_slots', '模組槽', st('module_slots'), num()),
]
const MISSILE = [
  col('damage_total', '傷害', st('damage_total'), num()),
  wideCol('damage', '傷害類型', it => mainDmg(it?.stats?.damage), (v, it) => dmgText(it?.stats?.damage)),
  textCol('tracking', '追蹤', st('tracking'), v => (v ? TRACK_LABEL[v] || v : '—')),
  col('lock_time', '鎖定時間', st('lock_time'), num(1), '秒'),
  col('lock_angle', '鎖定角度', st('lock_angle'), num(), '°'),
  col('lock_min', '最短鎖定距離', it => it?.stats?.lock_range?.[0] ?? null, scaled(1000, 1), 'km'),
  col('lock_max', '最遠鎖定距離', it => it?.stats?.lock_range?.[1] ?? null, scaled(1000, 1), 'km'),
  col('speed', '速度', st('speed'), num(), 'm/s'),
  col('distance', '射程', st('distance'), scaled(1000, 1), 'km'),
]
const SHIELD = [
  col('hp', '護盾 HP', st('hp'), num()),
  col('regen', '回充', st('regen'), num(), '/秒'),
  col('damaged_delay', '受擊後延遲', st('damaged_delay'), num(1), '秒'),
  col('downed_delay', '擊破後延遲', st('downed_delay'), num(1), '秒'),
  ...DMG_KEYS.map(k => col(`abs_${k}`, `${DMG_LABEL[k]}吸收`, rangeMax('absorption', k), pct)),
  ...DMG_KEYS.map(k => col(`res_${k}`, `${DMG_LABEL[k]}抗性`, rangeMax('resistance', k), pct)),
]

/** 各種類專屬的參數（沒列到的種類只有共用參數） */
const TYPE_COLS = {
  WeaponGun: WEAPON,
  WeaponMining: [...MINING, ...WEAPON],
  Missile: MISSILE,
  Bomb: MISSILE,
  MissileLauncher: [col('count', '飛彈數', st('count'), num()), col('missile_size', '飛彈尺寸', st('missile_size'), v => (isNum(v) ? `S${v}` : '—'))],
  BombLauncher: [col('count', '炸彈數', st('count'), num()), col('missile_size', '炸彈尺寸', st('missile_size'), v => (isNum(v) ? `S${v}` : '—'))],
  Shield: SHIELD,
  QuantumDrive: [
    col('speed', '量子速度', st('speed'), scaled(1000), 'km/s'),
    col('spline_speed', '曲線航行速度', st('spline_speed'), scaled(1000), 'km/s'),
    col('spool', '啟動時間', st('spool'), num(1), '秒'),
    col('cooldown', '冷卻時間', st('cooldown'), num(1), '秒'),
    col('fuel_req', '油耗', st('fuel_req'), v => (isNum(v) ? fmtNum(v * 1000, 2) : '—'), '每 Gm'),
    col('stage1_accel', '第一段加速', st('stage1_accel'), num(), 'm/s²'),
    col('stage2_accel', '第二段加速', st('stage2_accel'), num(), 'm/s²'),
  ],
  JumpDrive: [
    col('align', '對準速率', st('align')),
    col('tune', '調諧速率', st('tune')),
    col('fuel_eff', '油耗倍率', st('fuel_eff')),
  ],
  Radar: [
    ...['ir', 'em', 'cs', 'rs'].map(k => col(`sens_${k}`, `${k.toUpperCase()} 靈敏度`, it => it?.stats?.sensitivity?.[k] ?? null, pct)),
    col('cooldown', '冷卻', st('cooldown'), num(1), '秒'),
  ],
  WeaponDefensive: [
    textCol('cm_type', '類型', st('cm_type')),
    col('ammo', '數量', st('ammo'), num()),
  ],
  Turret: [
    col('yaw', '水平轉速', st('yaw'), num(), '°/秒'),
    col('pitch', '垂直轉速', st('pitch'), num(), '°/秒'),
    col('yaw_limit', '水平角度', st('yaw_limit'), range(0), '°'),
    col('pitch_limit', '垂直角度', st('pitch_limit'), range(0), '°'),
  ],
}
TYPE_COLS.TurretBase = TYPE_COLS.Turret
// 發電機、冷卻器的主要數值就是共用參數裡的發電／冷卻產出，放最前面
TYPE_COLS.PowerPlant = [col('power_gen', '發電', st('power_gen'), auto)]
TYPE_COLS.Cooler = [col('coolant_gen', '冷卻產出', st('coolant_gen'), auto)]

/** 每種組件都有的參數：電力、冷卻、訊號、耐久、質量、取得方式 */
const COMMON = [
  col('power_gen', '發電', st('power_gen'), auto),
  col('coolant_gen', '冷卻產出', st('coolant_gen'), auto),
  col('power_min', '耗電（最低）', it => it?.stats?.power_use?.[0] ?? null, auto),
  col('power_max', '耗電（最高）', it => it?.stats?.power_use?.[1] ?? null, auto),
  col('coolant_min', '耗冷卻（最低）', it => it?.stats?.coolant_use?.[0] ?? null, auto),
  col('coolant_max', '耗冷卻（最高）', it => it?.stats?.coolant_use?.[1] ?? null, auto),
  wideCol('power_ranges', '電源分段效能', it => it?.stats?.power_ranges?.length ?? null,
    (v, it) => (it?.stats?.power_ranges?.length
      ? it.stats.power_ranges.map(([s, m]) => `${fmtNum(s)} 格 ${fmtNum(m * 100)}%`).join('／') : '—')),
  col('em', 'EM', st('em'), num()),
  col('ir', 'IR', st('ir'), num()),
  col('hp', '耐久', it => it?.hp ?? null, num()),
  col('mass', '質量', it => it?.mass ?? null, num(), 'kg'),
  col('price', '最低售價', it => it?.price ?? null, num(), 'aUEC'),
]

/** 名稱、尺寸、等級、分類、廠商（每種都有，不會因為沒值被拿掉）；classLabel＝組件類別的中文（utils/loadoutLabels.js） */
export const baseColumns = classLabel => [
  textCol('name', '名稱', it => it?.name_zh || it?.name || null),
  textCol('size', '尺寸', it => it?.size ?? null, v => (isNum(v) ? `S${v}` : '—')),
  textCol('grade', '等級', it => it?.grade || null),
  textCol('item_class', '分類', it => it?.item_class || null, v => (v ? classLabel(v) : '—')),
  textCol('manufacturer', '廠商', it => it?.manufacturer_name || it?.manufacturer || null),
  // 取得方式：後端 annotate 的 buyable（UEX 買得到）、blueprint（有藍圖可製作）；排序時兩者都可的在前
  wideCol('acquire', '取得', it => (it?.buyable ? 2 : 0) + (it?.blueprint ? 1 : 0) || null, (v, it) => acquireLabel(it)),
]

/** 取得方式文字：可購買／可製作 */
export function acquireLabel(it) {
  return [it?.buyable ? '可購買' : '', it?.blueprint ? '可製作' : ''].filter(Boolean).join('／') || '—'
}

/** 某種組件的參數欄（不含 BASE_COLS）：專屬在前、共用在後；同 key 只留一個（護盾的 hp 是護盾 HP，耐久另一欄） */
export function componentColumns(type) {
  const seen = new Set()
  const out = []
  for (const c of [...(TYPE_COLS[type] || []), ...COMMON]) {
    const k = c.key === 'hp' && seen.has('hp') ? 'durability' : c.key
    if (seen.has(k)) continue
    seen.add(k)
    out.push(k === c.key ? c : { ...c, key: k })
  }
  return out
}

/** 只留至少一筆有值的欄位（0 也算有值；整欄都空就不顯示） */
export function visibleColumns(cols, items) {
  return cols.filter(c => (items || []).some(it => {
    const v = c.get(it)
    return v !== null && v !== undefined && v !== '' && !(typeof v === 'number' && Number.isNaN(v))
  }))
}
