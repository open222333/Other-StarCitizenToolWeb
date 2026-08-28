import { defineStore } from 'pinia'
import { ref } from 'vue'
import { playerApi } from '@/api'

export const usePlayerStore = defineStore('player', () => {
  const players = ref([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    const res = await playerApi.list()
    if (res) {
      const data = await res.json()
      players.value = data.data || []
    }
    loading.value = false
  }

  function byId(id) {
    return players.value.find(p => p._id === id) || null
  }

  return { players, loading, load, byId }
})
