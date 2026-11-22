// 前端 fetch＋JSON 的共用寫法（待辦 3-3）：fetcher（apiFetch／playerFetch，失敗可能回 null）→ 解析 JSON → 檢查 success。
// 回傳 { ok, body, data, message, status }：ok＝HTTP 成功而且 body.success；data＝body.data；
// message＝後端給的錯誤訊息（沒有就用 fallback）。呼叫端不用再各自寫 res.json().catch(...)。

export async function getJson(fetcher, path, init, fallback = '讀取失敗') {
  const res = await fetcher(path, init)
  const body = res ? await res.json().catch(() => null) : null
  const ok = !!res?.ok && !!body?.success
  return { ok, body, data: ok ? body.data : undefined, message: ok ? '' : (body?.message || fallback), status: res?.status ?? 0 }
}
