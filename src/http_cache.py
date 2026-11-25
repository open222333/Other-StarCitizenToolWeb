"""主檔類公開 API 的瀏覽器快取（待辦 2-6、2-3）：成功的 GET JSON 回應加 ETag（回應內容的雜湊），
瀏覽器下次帶 If-None-Match，內容沒變就回 304、不用再傳一次。

- 只套在讀「遊戲資料」的路徑（MASTER_PREFIXES）；個人資料（倉庫、艦隊…）不加。
- 預設 `Cache-Control: private, no-cache`：每次都會問伺服器（資料一改就看得到，例如後台改了顯示／中文），
  只是沒變時省下傳輸；配裝資料一天才同步一次，允許瀏覽器直接用 10 分鐘（LONG_CACHE）。
- 端點自己設了 ETag／Cache-Control 的（例如船價列表用同步 run_id 當 ETag）不動。
- 用內容雜湊而不是同步 run_id：主檔除了同步，後台也會改（顯示與否、人工中文），run_id 抓不到這些變動。
"""

from flask import request

#: 加 ETag 的路徑前綴（GET、200、JSON）
MASTER_PREFIXES = ('/item/', '/mission/', '/mining/', '/blueprint/master', '/starmap/', '/news/tags')
#: 不加的（個人或後台、量大又每次不同的）
EXCLUDE_PREFIXES = ('/item/sync-', '/item/uex-')
#: 可以直接用快取一段時間的（秒）
LONG_CACHE = {'/item/loadout/': 600}


def _match(path: str, prefixes) -> bool:
    return any(path == p.rstrip('/') or path.startswith(p) for p in prefixes)


def apply(response):
    if request.method != 'GET' or response.status_code != 200 or response.direct_passthrough:
        return response
    path = request.path
    if not _match(path, MASTER_PREFIXES) or _match(path, EXCLUDE_PREFIXES):
        return response
    if not (response.mimetype or '').endswith('json') or response.headers.get('ETag'):
        return response
    if 'Cache-Control' not in response.headers:
        age = next((sec for p, sec in LONG_CACHE.items() if path.startswith(p)), 0)
        response.headers['Cache-Control'] = f'private, max-age={age}' if age else 'private, no-cache'
    response.add_etag()
    return response.make_conditional(request)


def register(app) -> None:
    app.after_request(apply)
