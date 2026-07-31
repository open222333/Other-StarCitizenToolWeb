import os
from flask import Blueprint, send_from_directory, current_app

app_admin = Blueprint('app_admin', __name__)

# Vue build 輸出目錄（相對於 app/ 資料夾）
_DIST_REL = os.path.join('static', 'admin')


def _dist_dir():
    return os.path.join(current_app.root_path, _DIST_REL)


@app_admin.route('/', defaults={'path': ''})
@app_admin.route('/<path:path>')
def index(path):
    """
    服務 Vue 3 + Vite 打包後的靜態檔案。

    - 若請求的路徑對應實際檔案（js/css/assets）→ 直接回傳該檔案
    - 其他路徑（Vue Router 路由）→ 回傳 index.html，由前端 router 接手
    """
    dist   = _dist_dir()
    target = os.path.abspath(os.path.join(dist, path))
    if path and target.startswith(dist + os.sep) and os.path.isfile(target):
        return send_from_directory(dist, path)
    return send_from_directory(dist, 'index.html')
