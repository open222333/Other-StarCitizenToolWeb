<!--
  戰利品新增／編輯表單（規格書第 6.1 節／第 14.1 節新增流程）。
  用法：<LootFormModal ref="lootModalRef" :players="players" @saved="onLootSaved" />
-->
<template>
  <div class="modal fade" ref="modalEl" tabindex="-1">
    <div class="modal-dialog modal-lg">
      <div class="modal-content border-0 shadow">

        <div class="modal-header">
          <h5 class="modal-title">{{ editId ? '編輯戰利品' : '新增戰利品' }}</h5>
          <button type="button" class="btn-close" @click="hide"></button>
        </div>

        <div class="modal-body">
          <Transition name="alert-slide">
            <div v-if="error" class="alert alert-danger py-2 mb-3">{{ error }}</div>
          </Transition>

          <div class="row">
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">物品名稱 <span class="text-danger">*</span></label>
              <input v-model="form.name" type="text" class="form-control" required>
            </div>
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">英文名稱</label>
              <input v-model="form.name_en" type="text" class="form-control">
            </div>
          </div>

          <div class="row">
            <div class="col-sm-4 mb-3">
              <label class="form-label small fw-semibold">類型</label>
              <select v-model="form.category" class="form-select">
                <option value="">— 未分類 —</option>
                <option v-for="c in CATEGORY_OPTIONS" :key="c" :value="c">{{ c }}</option>
              </select>
            </div>
            <div class="col-sm-4 mb-3">
              <label class="form-label small fw-semibold">稀有度</label>
              <select v-model="form.rarity" class="form-select">
                <option v-for="r in RARITY_OPTIONS" :key="r" :value="r">{{ r }}</option>
              </select>
            </div>
            <div class="col-sm-4 mb-3">
              <label class="form-label small fw-semibold">數量</label>
              <input v-model.number="form.quantity" type="number" min="1" class="form-control">
            </div>
          </div>

          <div class="row">
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">取得地點</label>
              <input v-model="form.location" type="text" class="form-control" placeholder="Onyx Facility">
            </div>
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">取得方式</label>
              <input v-model="form.acquisition_method" type="text" class="form-control" placeholder="Boss 掉落">
            </div>
          </div>

          <div class="row">
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">取得玩家</label>
              <select v-model="form.obtained_by" class="form-select">
                <option value="">— 選擇玩家 —</option>
                <option v-for="p in players" :key="p._id" :value="p._id">{{ p.player_name }}</option>
              </select>
            </div>
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">目前持有人</label>
              <select v-model="form.current_owner" class="form-select">
                <option value="">— 團隊倉庫 / 待分配 —</option>
                <option v-for="p in players" :key="p._id" :value="p._id">{{ p.player_name }}</option>
              </select>
            </div>
          </div>

          <div class="row">
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">狀態</label>
              <select v-model="form.status" class="form-select">
                <option v-for="s in STATUS_OPTIONS" :key="s.value" :value="s.value">{{ s.label }}</option>
              </select>
            </div>
            <div class="col-sm-6 mb-3">
              <label class="form-label small fw-semibold">取得日期</label>
              <input v-model="form.obtained_at" type="date" class="form-control">
            </div>
          </div>

          <div class="mb-1">
            <label class="form-label small fw-semibold">備註</label>
            <textarea v-model="form.notes" class="form-control" rows="2"></textarea>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="hide">取消</button>
          <button type="button" class="btn btn-primary" :disabled="saving" @click="save">
            <span v-if="saving" class="spinner-border spinner-border-sm me-1"></span>
            儲存
          </button>
        </div>

      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { Modal } from 'bootstrap'
import { lootApi } from '@/api'

defineProps({
  players: { type: Array, default: () => [] },
})
const emit = defineEmits(['saved'])

// 第 6.2 節 Loot 類型
const CATEGORY_OPTIONS = [
  '手槍', '步槍', 'SMG', 'Shotgun', 'Sniper', '重武器', '近戰武器',
  '頭盔', '防彈衣', '背包', '防護服', '醫療裝備', '工具',
  '任務物品', '稀有物品', '特殊裝備', '掃描器', 'Rangefinder', '特殊道具',
  '彈藥', '消耗品', '材料', '未分類',
]
// 第 6.3 節 Loot 稀有度
const RARITY_OPTIONS = ['Common', 'Uncommon', 'Rare', 'Very Rare', 'Epic', 'Legendary', 'Unknown']
// 第 6.4 節 Loot 狀態
const STATUS_OPTIONS = [
  { value: 'in_stock',    label: '📦 庫存中' },
  { value: 'held',        label: '🎒 玩家持有' },
  { value: 'equipped',    label: '🔫 已裝備' },
  { value: 'transferred', label: '🤝 已轉交' },
  { value: 'sold',        label: '💰 已出售' },
  { value: 'lost',        label: '💀 已遺失' },
  { value: 'consumed',    label: '🗑️ 已消耗' },
  { value: 'unconfirmed', label: '❓ 未確認' },
]

const modalEl = ref(null)
let   bsModal = null

const editId = ref('')
const saving = ref(false)
const error  = ref('')
const form = reactive({
  name: '', name_en: '', category: '', rarity: 'Unknown', quantity: 1,
  location: '', acquisition_method: '', obtained_by: '', current_owner: '',
  status: 'in_stock', obtained_at: '', notes: '',
})

onMounted(() => { bsModal = new Modal(modalEl.value) })

function open(loot = null) {
  editId.value              = loot?._id                || ''
  error.value                = ''
  form.name                  = loot?.name                || ''
  form.name_en               = loot?.name_en             || ''
  form.category               = loot?.category            || ''
  form.rarity                = loot?.rarity              || 'Unknown'
  form.quantity               = loot?.quantity            || 1
  form.location               = loot?.location            || ''
  form.acquisition_method    = loot?.acquisition_method  || ''
  form.obtained_by            = loot?.obtained_by         || ''
  form.current_owner          = loot?.current_owner       || ''
  form.status                = loot?.status              || 'in_stock'
  form.obtained_at            = loot?.obtained_at         || ''
  form.notes                  = loot?.notes               || ''
  bsModal.show()
}

function hide() { bsModal.hide() }

async function save() {
  error.value = ''
  if (!form.name.trim()) { error.value = '物品名稱不得為空'; return }

  saving.value = true
  try {
    const payload = { ...form }
    const res = editId.value
      ? await lootApi.update(editId.value, payload)
      : await lootApi.create(payload)
    if (!res) return
    const data = await res.json()
    if (data.success) { hide(); emit('saved') }
    else { error.value = data.message || '儲存失敗' }
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.alert-slide-enter-active { transition: all .2s ease; }
.alert-slide-enter-from   { opacity: 0; transform: translateY(-4px); }
</style>
