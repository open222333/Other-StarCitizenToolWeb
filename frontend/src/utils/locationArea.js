// 地點的「星系／行星／地點」三段篩選（全站共用）。
//
// 庫存的地點只存名稱字串（Area18、Lorville…），所屬星系／行星查地點資料庫
// （GET /starmap/storage-locations，src/models/starmap.py 的 storage_locations）。
// 查不到的地點（自由輸入的、地點資料還沒同步）沒有星系／行星：不篩星系／行星時照常出現，
// 選了星系或行星就不會符合。
//
// 三段之間是 AND、同一段內多選取聯集；行星的選項跟著已選的星系縮小、地點跟著星系＋行星縮小
// （見 components/LocationAreaFilter.vue）。
import { reactive } from 'vue'
import { loadStorageLocationRows, translate } from '@/utils/translations'

/** 地點名稱（小寫）→ { system, planet } */
const areas = reactive({})
let loading = null

export function loadLocationAreas() {
  if (!loading) {
    loading = loadStorageLocationRows().then((rows) => {
      if (!rows.length) loading = null   // 還沒同步／失敗：下次再試
      for (const r of rows) {
        const key = (r.name || '').toLowerCase()
        if (key && !areas[key]) areas[key] = { system: r.system || '', planet: r.planet || '' }
      }
    })
  }
  return loading
}

/** 某地點的所屬星系／行星（查不到回空字串）。 */
export function areaOf(name) {
  return areas[(name || '').toLowerCase()] || { system: '', planet: '' }
}

/** 星系／行星／地點的顯示文字：英文（中文）。 */
export function placeLabel(en) {
  if (!en) return ''
  const zh = translate('location', en)
  return zh && zh !== en ? `${en}（${zh}）` : en
}

const byLabel = (a, b) => a.label.localeCompare(b.label, 'zh-Hant')

function uniqueOptions(values, labelFor) {
  return [...new Set(values.filter(Boolean))].map(v => ({ value: v, label: labelFor(v) })).sort(byLabel)
}

/** 一個地點符不符合 { systems, planets, locations }（皆為陣列，空 = 不篩）。 */
export function matchArea(name, { systems = [], planets = [], locations = [] } = {}) {
  if (locations.length && !locations.includes(name)) return false
  if (!systems.length && !planets.length) return true
  const a = areaOf(name)
  return (!systems.length || systems.includes(a.system)) && (!planets.length || planets.includes(a.planet))
}

/**
 * 三段下拉的選項。names：候選地點名稱；sel：目前已選的 { systems, planets }。
 * 也可以傳 areaFor(name) 自己給星系／行星（例如 UEX 終端，資料自己就帶）。
 */
export function areaOptions(names, sel = {}, { locLabel = placeLabel, areaFor = areaOf, sort = true } = {}) {
  const systems = sel.systems || []
  const planets = sel.planets || []
  const list = [...new Set((names || []).filter(Boolean))]
  const inSystem = list.filter(n => !systems.length || systems.includes(areaFor(n).system))
  const inPlanet = inSystem.filter(n => !planets.length || planets.includes(areaFor(n).planet))
  return {
    systems: uniqueOptions(list.map(n => areaFor(n).system), placeLabel),
    planets: uniqueOptions(inSystem.map(n => areaFor(n).planet), placeLabel),
    locations: (() => {
      const opts = inPlanet.map(n => ({ value: n, label: locLabel(n) }))
      return sort ? opts.sort(byLabel) : opts
    })(),
  }
}
