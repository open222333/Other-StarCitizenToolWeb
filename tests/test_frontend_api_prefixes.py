"""確保「玩家站呼叫的 API 前綴」三份清單不會漂移。

背景（見 frontend/vite.api-prefixes.mjs 檔頭）：這份清單有三個消費者
（vite.config.js / vite.config.web.js 的 dev proxy、conf/nginx-web/default.conf
的生產環境反向代理正則），過去各自維護一份、然後漂移，已經發生過三次
（/item、/inventory，這次又是 /mining）——症狀永遠一樣：漏掉的前綴會落到
SPA 的 index.html fallback，前端 fetch 回來一份 HTML 卻以為是 JSON，
畫面顯示「沒有資料」而不是任何錯誤，非常難排查（這次就是一路查到
mongosh、Python model 都證實資料正確，最後才發現是 nginx 正則沒加）。

這支測試只做一件事：讀兩份設定檔（不是真的啟動 nginx），把清單抽出來
互相比對，兩邊都要完全一致。有落差就直接在 CI/測試階段炸掉，
不用等到有人手動點開玩家站才發現「沒有資料」。
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_PREFIXES_MJS = REPO_ROOT / 'frontend' / 'vite.api-prefixes.mjs'
NGINX_WEB_CONF = REPO_ROOT / 'conf' / 'nginx-web' / 'default.conf'


def _prefixes_from_mjs() -> set:
    """從 `export const API_PREFIXES = [...]` 陣列裡抽出所有字串。"""
    src = API_PREFIXES_MJS.read_text(encoding='utf-8')
    m = re.search(r'export const API_PREFIXES\s*=\s*\[(.*?)\]', src, re.S)
    assert m, f'在 {API_PREFIXES_MJS} 找不到 API_PREFIXES 陣列，檔案格式是不是變了？'
    return set(re.findall(r"'([^']+)'", m.group(1)))


def _prefixes_from_nginx() -> set:
    """從 `location ~ ^/(a|b|c)(/|$) {` 這行正則抽出所有前綴（補回開頭的 /）。"""
    src = NGINX_WEB_CONF.read_text(encoding='utf-8')
    m = re.search(r'location ~ \^/\(([a-z|]+)\)\(/\|\$\)', src)
    assert m, f'在 {NGINX_WEB_CONF} 找不到 API 反向代理的 location 正則，格式是不是變了？'
    return {f'/{name}' for name in m.group(1).split('|')}


def test_vite_and_nginx_api_prefixes_match():
    mjs_prefixes = _prefixes_from_mjs()
    nginx_prefixes = _prefixes_from_nginx()

    only_in_mjs = mjs_prefixes - nginx_prefixes
    only_in_nginx = nginx_prefixes - mjs_prefixes

    assert not only_in_mjs, (
        f'{API_PREFIXES_MJS.name} 裡有但 nginx-web 正則沒有的前綴：{only_in_mjs}——'
        'production 環境的玩家站會把這些路徑的請求 fallback 回 index.html，'
        '前端拿到 HTML 卻以為是 JSON，畫面顯示「沒有資料」而不是任何錯誤。'
        '記得同步更新 conf/nginx-web/default.conf 的 location 正則。'
    )
    assert not only_in_nginx, (
        f'conf/nginx-web/default.conf 裡有但 {API_PREFIXES_MJS.name} 沒有的前綴：'
        f'{only_in_nginx}——這樣本機 `npm run dev` 的 dev proxy 會漏掉這個前綴，'
        '兩邊環境行為不一致。記得同步更新 vite.api-prefixes.mjs。'
    )
