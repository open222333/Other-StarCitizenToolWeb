import { defineStore } from 'pinia'
import { ref } from 'vue'
import { playerApi } from '@/api'

export const usePlayerStore = defineStore('player', () => {
  const players = ref([])
  const loading = ref(false)
  // 目前這份清單是否含已移除的玩家（load(true) 之後為 true）
  const includeDeleted = ref(false)

  async function load(withDeleted = includeDeleted.value) {
    loading.value = true
    includeDeleted.value = !!withDeleted
    const res = await playerApi.list(withDeleted)
    if (res) {
      const data = await res.json()
      players.value = data.data || []
    }
    loading.value = false
  }

  function byId(id) {
    return players.value.find(p => p._id === id) || null
  }

  return { players, loading, includeDeleted, load, byId }
})
