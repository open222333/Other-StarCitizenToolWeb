"""`/docs/` 說明頁。

⚠️ 這支原本是 `render_template('docs/index.html', …)`，但整個專案**沒有**
`templates/` 目錄（也沒有在 Blueprint 上指定 template_folder），所以每一次
請求都是 TemplateNotFound → 被全域 handler 轉成 500「伺服器內部錯誤」，
而 README 又把這個網址列在「API 與文件」表格裡。

改成直接回一頁自帶樣式的靜態 HTML：不需要模板檔案，也就不會再有
「檔案沒跟著部署」這種失敗模式。真正的 API 文件在 /apidocs（Swagger UI），
這一頁只負責當入口與講清楚兩個前端的差別。
"""
from flask import Blueprint, Response

from src import ADMIN_TITLE

app_docs = Blueprint('app_docs', __name__)

_PAGE = """<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · 說明</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font: 16px/1.7 system-ui, -apple-system, "Noto Sans TC", sans-serif;
         max-width: 46rem; margin: 0 auto; padding: 2.5rem 1.25rem; }}
  h1 {{ font-size: 1.5rem; margin-bottom: .25rem; }}
  p.sub {{ opacity: .7; margin-top: 0; }}
  h2 {{ font-size: 1.05rem; margin-top: 2rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: .5rem 0 1rem; }}
  th, td {{ text-align: left; padding: .45rem .6rem; border-bottom: 1px solid #8883; vertical-align: top; }}
  code {{ background: #8882; padding: .1rem .35rem; border-radius: .25rem; }}
  a {{ color: #2563eb; }}
  @media (prefers-color-scheme: dark) {{ a {{ color: #7dd3fc; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="sub">星際公民公會倉庫管理系統 · 說明入口</p>

<h2>API 文件</h2>
<p><a href="/apidocs">Swagger UI（/apidocs）</a> —— 所有端點、參數與回應格式。
需要 token 的端點請先用 <code>POST /auth/login</code> 取得，再填進右上角的 Authorize。</p>

<h2>兩個前端不要搞混</h2>
<table>
  <tr><th>用途</th><th>登入頁</th><th>身分來源</th></tr>
  <tr><td>公會管理後台</td><td><code>/admin/login</code></td><td>後台帳號（admin／operator／viewer）</td></tr>
  <tr><td>玩家自助</td><td>玩家站的 <code>/login</code></td><td>遊戲ID（Star Citizen ID）＋密碼</td></tr>
</table>
<p>兩者是完全分開的身分體系，token 不能互用。用錯頁面登入會一直顯示帳號或密碼錯誤。</p>

<h2>Discord bot</h2>
<p>先在玩家站「我的資料 → 產生 Discord 綁定碼」取得 8 碼，再到 Discord 打
<code>/bind handle:&lt;你的遊戲ID&gt; code:&lt;綁定碼&gt;</code>（10 分鐘內有效）。
綁定後才能用 <code>/add</code>、<code>/remove</code>、<code>/stock</code> 操作自己的個人庫。</p>

<h2>其他</h2>
<p>部署、備份還原、遊戲資料同步與擴充教學都在版本庫的 <code>README.md</code>。</p>
</body>
</html>
"""


@app_docs.route('/')
def index():
    return Response(_PAGE.format(title=ADMIN_TITLE), mimetype='text/html')
