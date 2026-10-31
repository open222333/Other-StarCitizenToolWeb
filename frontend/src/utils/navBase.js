// 航線規劃的基本資料（地點、船、量子引擎），「航線規劃」「合約分配」共用同一份，只載一次。
import { ref } from 'vue'

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
  return { places, ships, quantumDrives, commodities, loading, error, loaded, load, loadCommodities }
}
