// 讓瀏覽器下載一個檔案（待辦 B3，取代各頁自己寫的 Blob → createObjectURL → <a>.click() → revokeObjectURL）。
// 網址延後 1 秒才釋放：有些瀏覽器（Safari）在 click 之後才開始讀，立刻 revoke 會下載到空檔。

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function downloadJson(obj, filename) {
  downloadBlob(new Blob([JSON.stringify(obj, null, 2)], { type: 'application/json' }), filename)
}

export function downloadText(text, filename, type = 'text/plain;charset=utf-8') {
  downloadBlob(new Blob([text], { type }), filename)
}
