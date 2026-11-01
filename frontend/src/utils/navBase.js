// 航線規劃的基本資料（地點、船、量子引擎），「航線規劃」「合約分配」共用同一份，只載一次。
import { computed, reactive, ref, watch } from 'vue'
import { maxOf } from '@/utils/cargoPack'

const places = ref([])
const ships = ref([])
const quantumDrives = ref([])
// 貨物（商品資料庫的 UEX 商品），只有「合約分配」用，另外載
const commodities = ref([])
let commoditiesPending = null
const loading = ref(false)
const error = ref('')
const loaded = ref(false)
let pending = null

async function getJson(fetcher, path) {
  const res = await fetcher(path)
  const body = res ? await res.json().catch(() => null) : null
  return { ok: !!res?.ok && !!body?.success, body }
}

// 選船的篩選（components/ShipFilter.vue），兩個分頁共用，記在這台瀏覽器
const FILTER_KEY = 'sc_route_ship_filter'
function loadFilter() {
  try {
    return JSON.parse(localStorage.getItem(FILTER_KEY) || 'null') || {}
  } catch {
    return {}
  }
}
const savedFilter = loadFilter()
export const shipFilter = reactive({
  hideNoCargo: savedFilter.hideNoCargo !== false,
  minScu: Number(savedFilter.minScu) > 0 ? Number(savedFilter.minScu) : null,
  fleetOnly: !!savedFilter.fleetOnly,
})
watch(shipFilter, () => {
  try {
    localStorage.setItem(FILTER_KEY, JSON.stringify(shipFilter))
  } catch { /* 存不了就算了 */ }
}, { deep: true })

/** 這艘船符不符合篩選（fleet：我的機庫的船 id Set；applyFleet＝false 時不套「只看我的機庫」） */
export function shipPasses(s, fleet, applyFleet = true) {
  const cargo = Number(s.cargo_scu) || 0
  if (shipFilter.hideNoCargo && cargo <= 0) return false
  if (Number(shipFilter.minScu) > 0 && cargo < Number(shipFilter.minScu)) return false
  if (applyFleet && shipFilter.fleetOnly && !fleet.has(s.id)) return false
  return true
}

// 飛船貨物網格（GET /starmap/nav/cargo-grids，sc-cargo.space）：選船後顯示 8／16／32 SCU 貨櫃最多裝幾個
export const cargoGrids = ref([])
let gridsPending = null
// 載具 UUID → 網格（同一艘船對到好幾個載具時每個都指過去）
export const gridByVehicle = computed(() => {
  const map = new Map()
  for (const g of cargoGrids.value) for (const u of g.vehicle_uuids || []) if (!map.has(u)) map.set(u, g)
  return map
})
export const BOX_SIZES = [8, 16, 32]
const boxCache = new Map()
/** 這艘船（載具 UUID）每種貨櫃最多裝幾個 { 8: n, 16: n, 32: n }；沒有網格資料回 null */
export function boxCapacity(vehicleId) {
  const g = gridByVehicle.value.get(vehicleId)
  if (!g?.official?.grids?.length) return null
  if (!boxCache.has(g.id)) boxCache.set(g.id, Object.fromEntries(BOX_SIZES.map(s => [s, maxOf(g.official.grids, s)])))
  return boxCache.get(g.id)
}

export function useNavBase(fetcher) {
  function load() {
    if (pending) return pending
    loading.value = true
    error.value = ''
    pending = (async () => {
      const [p, s, q] = await Promise.all([getJson(fetcher, '/starmap/nav/places'),
        getJson(fetcher, '/starmap/nav/ships'), getJson(fetcher, '/starmap/nav/quantum-drives')])
      loading.value = false
      pending = null
      if (!p.ok || !s.ok) {
        error.value = '讀取失敗。'
        return
      }
      places.value = p.body.data || []
      ships.value = s.body.data || []
      quantumDrives.value = q.ok ? q.body.data || [] : []
      loaded.value = true
    })()
    return pending
  }
  function loadCommodities() {
    if (commodities.value.length) return Promise.resolve()
    if (!commoditiesPending) {
      commoditiesPending = getJson(fetcher, '/starmap/nav/commodities').then((r) => {
        if (r.ok) commodities.value = r.body.data || []
        commoditiesPending = null
      })
    }
    return commoditiesPending
  }
  function loadCargoGrids() {
    if (cargoGrids.value.length) return Promise.resolve()
    if (!gridsPending) {
      gridsPending = getJson(fetcher, '/starmap/nav/cargo-grids').then((r) => {
        if (r.ok) {
          boxCache.clear()
          cargoGrids.value = r.body.data || []
        }
        gridsPending = null
      })
    }
    return gridsPending
  }
  return { places, ships, quantumDrives, commodities, loading, error, loaded, load, loadCommodities, loadCargoGrids }
}
