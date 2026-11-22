// 把使用者／資料庫的文字放進 HTML 字串前跳脫（ConfirmModal 的訊息是 HTML，名稱要先跳脫）。待辦 C8。
export function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}
