import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { lootApi } from '@/api'

// 對應規格書第 12.2 節篩選條件
const DEFAULT_FILTERS = {
  category: '',
  rarity: '',
  location: '',
  status: '',
  player: '',
}

export const useLootStore = defineStore('loot', () => {
  const items    = ref([])
  const loading  = ref(false)
  const keyword  = ref('')                       // 第 12.1 節：全域搜尋關鍵字
  const filters  = ref({ ...DEFAULT_FILTERS })    // 第 12.2 節：篩選條件

  const filtered = computed(() => {
    return items.value.filter(item => {
      if (filters.value.category && item.category !== filters.value.category) return false
      if (filters.value.rarity   && item.rarity   !== filters.value.rarity)   return false
      if (filters.value.location && item.location !== filters.value.location) return false
      if (filters.value.status   && item.status   !== filters.value.status)   return false
      if (filters.value.player   && item.obtained_by !== filters.value.player) return false
      if (keyword.value) {
        const kw = keyword.value.toLowerCase()
        const hay = `${item.name} ${item.name_en || ''} ${item.location || ''}`.toLowerCase()
        if (!hay.includes(kw)) return false
      }
      return true
    })
  })

  async function load() {
    loading.value = true
    const res = await lootApi.list()
    if (res) {
      const data = await res.json()
      items.value = data.data || []
    }
    loading.value = false
  }

  function resetFilters() {
    filters.value = { ...DEFAULT_FILTERS }
  }

  return { items, loading, keyword, filters, filtered, load, resetFilters }
})
