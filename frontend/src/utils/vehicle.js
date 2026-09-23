// 載具（太空船／地面載具／懸浮載具）顯示用的小工具，艦隊登記頁與「查詢 ›
// 船艦搜尋」共用。類型的判斷在後端（src/models/item.py 的 vehicle_type_of），
// 每筆回傳都帶 vehicle_type，前端只負責把代碼翻成中文。

export const VEHICLE_TYPE_LABELS = {
  ship:    '太空船',
  ground:  '地面載具',
  gravlev: '懸浮載具',
}

export function vehicleTypeLabel(type) {
  return VEHICLE_TYPE_LABELS[type] || type || '—'
}

/** 尺寸直接顯示遊戲資料的 size_class 數字（1～6，Vanduul 母艦是 10）。
 *  刻意不自己對應成「小型／中型」——官方各處的尺寸分級名稱並不一致，
 *  自己取名反而會跟玩家在遊戲裡看到的對不起來。 */
export function vehicleSizeLabel(size) {
  return size === null || size === undefined || size === '' ? '—' : `尺寸 ${size}`
}

/** 廠商顯示「全名（代碼）」，只有代碼時單獨顯示代碼。 */
export function manufacturerLabel(name, code) {
  const n = (name || '').trim()
  const c = (code || '').trim()
  if (n && c && n !== c) return `${n}（${c}）`
  return n || c || '—'
}
