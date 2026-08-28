"""後台管理 SPA（Vue 3 + Vite build）的靜態檔服務。

## 為什麼 build 輸出在 app/ 外面

Vite 的 outDir 是專案根目錄的 `web-admin/`（見 frontend/vite.config.js），
**刻意不放在 `app/static/` 裡**。

原因是 docker-compose.api.yml 為了讓 Python 程式碼改動即時生效，掛了
`./app:/app/app`。只要建置產物在 `app/` 底下，這個 bind mount 就會把
Dockerfile 在容器裡建好的前端整個遮住 —— `docker compose build api` 跑得
再成功，實際被服務的還是 host 上那份舊的，而且完全沒有錯誤訊息。

搬到 `app/` 外面之後 `web-admin/` 不被任何 mount 覆蓋，「重新 build image」
就成為唯一且有效的前端建置方式。
"""

import os

from flask import Blueprint, jsonify, send_from_directory

app_admin = Blueprint('app_admin', __name__)

# app/admin/view.py → app/admin → app → 專案根目錄
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 允許用環境變數覆寫（例如把建置產物放到 volume 或 CDN 同步目錄）
_DIST_DIR = os.path.abspath(
    os.environ.get('ADMIN_DIST_DIR') or os.path.join(_PROJECT_ROOT, 'web-admin')
)

_MISSING_HINT = (
    '後台前端尚未建置。web-admin/ 目錄不存在或沒有 index.html。\n'
    '請執行：docker compose build api && docker compose up -d api\n'
    '（本機開發改用 cd frontend && npm run dev，走 port 5173）'
)


@app_admin.route('/', defaults={'path': ''})
@app_admin.route('/<path:path>')
def index(path):
    """服務 Vue 3 + Vite 打包後的靜態檔案。

    - 請求路徑對應實際檔案（js/css/assets）→ 直接回傳該檔案
    - 其他路徑（Vue Router 的前端路由）→ 回傳 index.html，由前端 router 接手
    """
    if not os.path.isfile(os.path.join(_DIST_DIR, 'index.html')):
        # 給出可執行的指示，而不是一個看不出原因的 404
        return jsonify({'success': False, 'message': _MISSING_HINT}), 503

    target = os.path.abspath(os.path.join(_DIST_DIR, path))
    # 防止 ../ 穿越出 dist 目錄
    if path and target.startswith(_DIST_DIR + os.sep) and os.path.isfile(target):
        return send_from_directory(_DIST_DIR, path)
    return send_from_directory(_DIST_DIR, 'index.html')
