// 列表點欄位標題排序（全站共用，搭配 components/SortTh.vue）。
//
// 兩種用法：
//  - 前端排序（資料整包已載入）：useTableSort(rowsRef, { accessors: { 欄位: row => 值 } })
//    回傳的 sorted 是排好的陣列，v-for 改用它。
//  - 後端排序（後端分頁的列表）：useTableSort(null, { onChange: (key, dir) => reload(0) })
//    不排資料，只記住目前的排序欄位／方向，改變時呼叫 onChange，查詢時帶 sort_by／sort_dir。
//
// 點同一欄：升冪 → 降冪 → 取消排序（回到原本順序）；點別欄從升冪開始。
// 比較規則：數字照數值、其他照字串（中文用 zh-Hant、數字段落照數值，例如 S2 < S10），
// 空值（null／undefined／''）一律排最後。
import { computed, ref, unref } from 'vue'

const collator = new Intl.Collator('zh-Hant', { numeric: true, sensitivity: 'base' })

function isEmpty(v) {
  return v === null || v === undefined || v === '' || (typeof v === 'number' && Number.isNaN(v))
}

export function compareValues(a, b) {
  if (isEmpty(a) && isEmpty(b)) return 0
  if (isEmpty(a)) return 1
  if (isEmpty(b)) return -1
  if (typeof a === 'boolean' || typeof b === 'boolean') return Number(!!b) - Number(!!a)
  if (typeof a === 'number' && typeof b === 'number') return a - b
  if (a instanceof Date || b instanceof Date) return new Date(a) - new Date(b)
  return collator.compare(String(a), String(b))
}

export function useTableSort(rows, { accessors = {}, key = '', dir = 'asc', onChange = null, cycle = true } = {}) {
  const sortKey = ref(key)
  const sortDir = ref(dir)

  function toggle(field) {
    if (sortKey.value !== field) {
      sortKey.value = field
      sortDir.value = 'asc'
    } else if (sortDir.value === 'asc') {
      sortDir.value = 'desc'
    } else if (cycle) {
      sortKey.value = ''
      sortDir.value = 'asc'
    } else {
      sortDir.value = 'asc'
    }
    if (onChange) onChange(sortKey.value, sortDir.value)
  }

  /** 依目前的排序狀態排一份清單（同一個排序狀態套用到好幾張表時用，例如每個部位一張表） */
  function sortList(list) {
    list = list || []
    const field = sortKey.value
    if (!field) return list
    const get = accessors[field] || (r => r?.[field])
    const sign = sortDir.value === 'desc' ? -1 : 1
    return list
      .map((row, i) => ({ row, i, v: get(row) }))
      .sort((x, y) => {
        // 空值不管升降冪都排最後
        if (isEmpty(x.v) !== isEmpty(y.v)) return isEmpty(x.v) ? 1 : -1
        return sign * compareValues(x.v, y.v) || x.i - y.i
      })
      .map(x => x.row)
  }

  const sorted = computed(() => sortList(unref(rows)))

  /** 後端排序用：查詢參數 { sort_by, sort_dir }（沒排序回空物件） */
  const params = computed(() => (sortKey.value ? { sort_by: sortKey.value, sort_dir: sortDir.value } : {}))

  return { sortKey, sortDir, toggle, sorted, sortList, params }
}
