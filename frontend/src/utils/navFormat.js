// 航線規劃共用的顯示格式（components/RoutePlanner.vue、ContractPlanner.vue、RouteLegsTable.vue、ShipPicker.vue）。

export function fmtNum(v, digits = 0) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: digits })
}

export function fmtDist(m) {
  if (!m) return '0 km'
  if (m >= 1e9) return `${fmtNum(m / 1e9, 2)} Gm`
  return `${fmtNum(m / 1000)} km`
}

export function fmtTime(s) {
  const t = Math.round(s || 0)
  const h = Math.floor(t / 3600), mm = Math.floor((t % 3600) / 60), ss = t % 60
  if (h) return `${h} 時 ${mm} 分`
  return mm ? `${mm} 分 ${ss} 秒` : `${ss} 秒`
}

export const fmtSpeed = v => (v ? `${fmtNum(v / 1000)} km/s` : '—')

export const placeLabel = p => (p?.name_zh && p.name_zh !== p.name ? `${p.name_zh}（${p.name}）` : (p?.name || ''))
export const placePath = p => [p?.system_zh || p?.system, ...(p?.path_zh || []).slice(1)].filter(Boolean).join(' › ')
export const shipLabel = s => (s?.name_zh && s.name_zh !== s.name ? `${s.name_zh}（${s.name}）` : (s?.name || ''))
