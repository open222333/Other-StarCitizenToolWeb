"""星際公民遊戲資料來源客戶端（Star Citizen Wiki API + UEX Corp API）。

沒有官方 CIG API，遊戲資料一律來自社群眾包／解包的第三方 API：

  - Star Citizen Wiki API：物品、載具、商品規格。免費、無 token、按 patch 版本分版。
  - UEX Corp API 2.0：價格、終端與商店位置。需要免費 token（後台「資料同步排程」頁設定，或 UEX_API_TOKEN 環境變數）。

本模組只負責「抓取與欄位映射」，寫入資料庫由 tasks/scdata_sync.py 負責。
這樣抓取邏輯可以不碰 MongoDB 單獨測試。

Unofficial Star Citizen fan tool. Not affiliated with the Cloud Imperium group of companies.
"""

import logging
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Iterator, Optional

import httpx

from src import (SCDATA_BULK_SIZE, SCDATA_HTTP_TIMEOUT, SCDATA_MAX_RETRIES,
                 SCDATA_PAGE_SIZES, SCDATA_REQUEST_DELAY, SCDATA_USER_AGENT,
                 SCDATA_SCUNPACKED_BASE, SCDATA_TRANSLATION_INI_URL, SCDATA_UEX_API_BASE,
                 SCDATA_WIKI_API_BASE)
from src.sc_zh import (
    amenity_zh,
    clean_mission_text,
    faction_name_zh,
    faction_texts_zh,
    item_name_zh,
    location_name_zh,
    mining_deposit_name_zh,
    mining_resource_name_zh,
    mission_giver_zh,
    mission_text_zh,
    jurisdiction_zh,
    starmap_description_zh,
    starmap_name_zh,
    starmap_type_zh,
)

logger = logging.getLogger(__name__)

# 1 SCU = 1,000,000 µSCU。API 的 volume_converted 單位是 µSCU
USCU_PER_SCU = 1_000_000

BULK_SIZE = SCDATA_BULK_SIZE


def uscu_to_scu(uscu) -> float:
    """µSCU → SCU。庫存體積計算一律走這個，不要自己除。"""
    return round((uscu or 0) / USCU_PER_SCU, 4)


class ScDataError(Exception):
    """上游 API 取得失敗。"""


# ─────────────────────────────────────────────────────────── HTTP

def build_client(token: str = '') -> httpx.Client:
    headers = {'User-Agent': SCDATA_USER_AGENT, 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    return httpx.Client(timeout=SCDATA_HTTP_TIMEOUT, headers=headers, follow_redirects=True)


def _retry_after_seconds(raw: str, fallback: float) -> float:
    """解析 Retry-After。RFC 9110 允許「秒數」或「HTTP-date」兩種格式。

    只認秒數的話，回傳 HTTP-date 的上游會讓 float() 丟 ValueError ——
    而那個例外在舊版沒被 except 攔到，等於整輪同步直接掛掉。
    """
    raw = (raw or '').strip()
    if not raw:
        return fallback
    try:
        return max(0.0, float(raw))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return fallback
    if when is None:
        return fallback
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (when - datetime.now(timezone.utc)).total_seconds())


def get_json(client: httpx.Client, url: str, params: Optional[dict] = None) -> dict:
    """帶指數退避的 GET。429 / 5xx / 連線錯誤 / 非 JSON 回應都會重試。

    回傳一定是 dict —— 上游若回 JSON 陣列或純字串，呼叫端的
    `payload.get('data')` 會炸在很遠的地方（AttributeError），
    所以在這裡就當成「回應格式不對」處理並重試。
    """
    delay = 1.0
    last_err = None

    for attempt in range(1, SCDATA_MAX_RETRIES + 1):
        try:
            resp = client.get(url, params=params)

            if resp.status_code == 429:
                wait = _retry_after_seconds(resp.headers.get('Retry-After', ''), delay)
                last_err = f'HTTP 429（Retry-After={resp.headers.get("Retry-After", "-")}）'
                logger.warning('scdata: 429 rate limited, 等 %.1fs 重試 (%d/%d)',
                               wait, attempt, SCDATA_MAX_RETRIES)
                time.sleep(wait)
                delay = min(delay * 2, 60)
                continue

            if resp.status_code >= 500:
                last_err = f'HTTP {resp.status_code}'
                logger.warning('scdata: HTTP %d, 等 %.1fs 重試 (%d/%d)',
                               resp.status_code, delay, attempt, SCDATA_MAX_RETRIES)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue

            if 400 <= resp.status_code < 500:
                # 4xx（429 除外）是請求本身有問題（缺參數、token 錯…），重試幾次結果都一樣，
                # 直接回報，順便帶上回應內容——UEX 會在 body 說明缺什麼參數
                raise ScDataError(f'{url} HTTP {resp.status_code}: {resp.text[:300].strip()}')

            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                raise ValueError(f'預期 JSON object，收到 {type(payload).__name__}')
            return payload

        # ValueError 涵蓋 json.JSONDecodeError（維護頁面回 200 + HTML 就是這種）
        # 與上面自己拋的格式檢查 —— 舊版沒攔它，所以那兩種情況一次都不重試。
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as err:
            last_err = err
            logger.warning('scdata: 請求失敗 %s: %s (%d/%d)',
                           url, err, attempt, SCDATA_MAX_RETRIES)
            time.sleep(delay)
            delay = min(delay * 2, 60)

    raise ScDataError(f'{url} 重試 {SCDATA_MAX_RETRIES} 次後仍失敗: {last_err}')


# 部分資源需要額外的查詢參數才會回傳完整資料。
#
# blueprints 的列表回應預設把 ingredients / dismantle_returns / output 留空
# （只給 ingredient_count 這種摘要）。加上 include 之後列表就會帶完整配方，
# 省下逐筆打 1,606 次明細端點 —— 那會讓同步從 33 個請求變成 1,639 個。
WIKI_QUERY_EXTRA: dict = {
    'blueprints': {'include': 'ingredients,output,dismantle_returns'},
    # 任務列表預設只有 has_blueprints 標記，帶 include 才會附上獎勵藍圖池
    # （哪些藍圖、掉落機率）——不用逐筆打 /missions/<uuid>。
    'missions': {'include': 'blueprints'},
}

# 列表回應欄位太少、要逐筆打明細端點補齊的資源（筆數要小）。
# factions 列表只有名稱／類型／合法與否，說明、總部、聲望階級都只在明細裡；
# 目前 64 筆，多 64 個請求。明細抓失敗就用列表那筆，不拖垮整個資源。
WIKI_DETAIL_RESOURCES = {'factions'}

# wiki_rows() 的絕對安全網：萬一 meta.current_page 卡住不前進，最多跑這麼多
# 頁就強制停止。目前最大的資源（items）約 124 頁，留了充分餘裕。獨立成模組
# 常數是為了讓測試能 monkeypatch 成一個小數字，不用真的跑 500 輪。
WIKI_PAGINATION_MAX_PAGES = 500


def wiki_rows(client: httpx.Client, resource: str) -> Iterator[dict]:
    """走訪 Wiki API 分頁（Laravel JSON:API 風格 page[size] / page[number]）。

    自己算下一頁的 page[number]，**不**跟著 `links.next` 走。

    ⚠️ 這是踩過真的很隱蔽的上游 bug 之後才改的：blueprints 這種帶 include
    的大分頁，實測到從某一頁開始（目前觀察是第 9 頁），上游回應的
    `links`（不只 next，連 first/prev/1/2/...這些分頁按鈕連結全部）會把
    「這次請求本身用的 page[number]」跟「目標頁碼」兩個 query key 一起
    留在 URL 裡，變成 `...page[number]=9&page[size]=50&...&page[number]=10`
    這種帶重複 key 的畸形連結。乍看只是連結長得醜，但實測直接拿這個畸形
    URL 去打，上游會用**第一個** page[number]（也就是舊頁碼 9），回傳的
    還是第 9 頁的資料，不是第 10 頁——而且拿它自己回的 links.next 再打
    一次，會拿到一模一樣的畸形 URL，形成真正的無窮迴圈（不逾時也不報錯，
    整輪同步卡死）。乾淨地用單一 `page[number]=10` 直接打則能正確拿到
    第 10 頁，證實問題出在上游「產生分頁連結」的邏輯，不是頁碼本身失效。

    改法：完全不解析上游的 links，自己用 `meta.current_page + 1` 組下一頁
    的乾淨請求（跟第一次請求用同一份 base_params，只換 page[number]）。
    `meta.current_page`／`meta.last_page` 這兩個純數字欄位是準的（上游只有
    「產生連結」那段邏輯有 bug，回報目前在第幾頁是對的），拿頁碼自己組
    URL 就完全避開畸形連結，不需要再靠「重複 URL 判斷迴圈」這種被動防禦。

    仍保留一個絕對安全網（WIKI_PAGINATION_MAX_PAGES）：萬一 meta 本身也不
    可信、current_page 卡住不動，最多跑這麼多頁就強制停止，不會真的無窮
    迴圈。
    """
    base_params = {
        'page[size]': SCDATA_PAGE_SIZES.get(resource, 100),
        **WIKI_QUERY_EXTRA.get(resource, {}),
    }
    url = f'{SCDATA_WIKI_API_BASE}/{resource}'

    page = 1
    for _ in range(WIKI_PAGINATION_MAX_PAGES):
        payload = get_json(client, url, {**base_params, 'page[number]': page})

        rows = payload.get('data') or []
        meta = payload.get('meta') or {}
        current_page = meta.get('current_page', page)
        last_page = meta.get('last_page', current_page)
        logger.info('scdata: %s 第 %s/%s 頁 (%d 筆, 共 %s)',
                    resource, current_page, last_page, len(rows), meta.get('total', '?'))

        for row in rows:
            yield row

        if not rows or current_page >= last_page:
            return

        # 用回報的 current_page（而不是自己的 page 計數器）算下一頁，
        # 上游如果因為快取或其他原因把某一頁重複回給我們，至少不會因為
        # 「頁碼一直往前跳」而卡死——跳號也能正確接續下一頁。
        page = current_page + 1
        time.sleep(SCDATA_REQUEST_DELAY)
    else:
        logger.error(
            'scdata: %s 分頁超過 %d 頁仍未結束，判定 meta 不可信，強制停止',
            resource, WIKI_PAGINATION_MAX_PAGES)


def wiki_detail(client: httpx.Client, resource: str, uuid: str) -> Optional[dict]:
    """單筆明細（`/<resource>/<uuid>` 的 data）。抓不到回 None，由呼叫端退回用列表資料。"""
    if not uuid:
        return None
    try:
        payload = get_json(client, f'{SCDATA_WIKI_API_BASE}/{resource}/{uuid}')
    except ScDataError as err:
        logger.warning('scdata: %s/%s 明細抓取失敗，改用列表資料：%s', resource, uuid, err)
        return None
    data = payload.get('data')
    return data if isinstance(data, dict) else None


def uex_rows(client: httpx.Client, resource: str, params: Optional[dict] = None) -> list:
    """UEX 回應格式：{"status": "ok", "data": [...]}"""
    payload = get_json(client, f'{SCDATA_UEX_API_BASE}/{resource}/', params=params)
    status = payload.get('status')
    if status != 'ok':
        raise ScDataError(f'UEX {resource} 回傳 status={status}')
    return payload.get('data') or []


def fetch_translation_ini(client: httpx.Client, url: str = '') -> str:
    """下載社群繁中化包的 global.ini（約 10MB 純文字），回傳解碼後的字串。

    重試邏輯（429 / 5xx / 連線錯誤）同 fetch_scunpacked_rows()。檔頭有 UTF-8
    BOM，用 utf-8-sig 解碼去掉。內容明顯不像 global.ini（太短）也當成失敗重試，
    避免 GitHub 回一頁錯誤 HTML 就被當成「翻譯全部消失」寫進資料庫。
    """
    url = url or SCDATA_TRANSLATION_INI_URL
    delay = 1.0
    last_err = None

    for attempt in range(1, SCDATA_MAX_RETRIES + 1):
        try:
            resp = client.get(url)

            if resp.status_code == 429:
                wait = _retry_after_seconds(resp.headers.get('Retry-After', ''), delay)
                last_err = f'HTTP 429（Retry-After={resp.headers.get("Retry-After", "-")}）'
                logger.warning('scdata: 翻譯包 429 rate limited, 等 %.1fs 重試 (%d/%d)',
                               wait, attempt, SCDATA_MAX_RETRIES)
                time.sleep(wait)
                delay = min(delay * 2, 60)
                continue

            if resp.status_code >= 500:
                last_err = f'HTTP {resp.status_code}'
                logger.warning('scdata: 翻譯包 HTTP %d, 等 %.1fs 重試 (%d/%d)',
                               resp.status_code, delay, attempt, SCDATA_MAX_RETRIES)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue

            resp.raise_for_status()
            text = resp.content.decode('utf-8-sig')
            if text.count('=') < 1000:
                raise ValueError(f'內容不像 global.ini（只有 {len(text)} 字元）')
            return text

        except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as err:
            last_err = err
            logger.warning('scdata: 翻譯包下載失敗: %s (%d/%d)', err, attempt, SCDATA_MAX_RETRIES)
            time.sleep(delay)
            delay = min(delay * 2, 60)

    raise ScDataError(f'翻譯包下載失敗（{url}）：{last_err}')


#: 遊戲英文在地化表（scunpacked-data），翻譯同步的英文主語言來源
SCUNPACKED_LABELS_PATH = 'labels.json'


def _loc_key(raw_key) -> str:
    """localization key 正規化：去掉 BOM 與 `,P` 之類的旗標（英文表與翻譯包都有，
    位置一樣——約 1.3 萬筆），兩邊才對得上。"""
    return str(raw_key).lstrip('\ufeff').split(',', 1)[0].strip()


def iter_translation_ini(text: str):
    """逐行解析 global.ini，yield (key, value)。值原樣保留（包含字面上的 \\n）。

    自己用 str.find 逐行切，不用 splitlines()／StringIO：檔案約 10MB、9 萬行，
    splitlines 會一次產生整份字串清單，StringIO 會再複製一份（而且是較寬的內部
    編碼），worker 記憶體（256MB）吃不消多留一份。
    """
    text = text or ''
    pos = 1 if text.startswith('\ufeff') else 0
    size = len(text)
    while pos < size:
        end = text.find('\n', pos)
        if end == -1:
            end = size
        line = text[pos:end].rstrip('\r')
        pos = end + 1
        if '=' not in line or line.lstrip().startswith(';'):
            continue
        key, value = line.split('=', 1)
        key = _loc_key(key)
        if key:
            yield key, value


def normalize_labels(labels: dict) -> dict:
    """遊戲英文表 → {正規化後的 key: 英文}（去掉 BOM／`,P`，沒有英文的丟掉）。

    同步時先轉好就把原始 dict 丟掉，再去下載翻譯包——兩份 10MB 級的表不要同時
    留在 worker 記憶體裡（container 只有 256MB）。
    """
    english = {}
    for raw_key, en in labels.items():
        if isinstance(en, str) and en.strip():
            english[_loc_key(raw_key)] = en.strip()
    return english


def iter_translation_entries(english: dict, ini_text: str, lang: str):
    """遊戲英文表（normalize_labels 的結果）+ 某語言的 global.ini → yield (_id, text, None)。

    ⚠️ 會邊處理邊把 english 裡用過的 key 拿掉（省下另外記一份「處理過哪些 key」
    的集合），呼叫端傳進來的 dict 之後就不完整了，不要再拿去用。

    以英文表為準（英文是主語言）。翻譯包有、英文表沒有的 key 也收，英文就用
    翻譯包中英並列格式裡的英文（「English\\n中文」的前半）；兩邊都沒有英文的
    不收（沒有英文就無從反查）。中英並列格式會拿掉英文部分，見
    src/models/translation.py 的 strip_english。
    """
    from src.models.translation import LANG_EN, strip_english

    for key, value in iter_translation_ini(ini_text):
        en = english.pop(key, None)
        if not en:
            en = value.split('\\n', 1)[0].strip() if '\\n' in value else ''
            if not en:
                continue
        text = {LANG_EN: en}
        translated = strip_english(value, en)
        if translated:
            text[lang] = translated
        yield key, text, None

    # 剩下的是翻譯包沒有的 key：只有英文
    while english:
        key, en = english.popitem()
        yield key, {LANG_EN: en}, None


def fetch_scunpacked_rows(client: httpx.Client, path: str, expect: type = list):
    """抓 scunpacked-data 的靜態 JSON 檔（GitHub raw，單一請求、無分頁、無 token）。

    這批檔案的回應是「裸陣列」（`[...]`），不是 Wiki API 那種 `{"data": [...]}`
    包裝，跟 get_json() 預期回傳 dict 的假設不同，所以另外寫一支；重試邏輯
    （429 / 5xx / 連線錯誤都重試）照抄 get_json()。

    :param path: 相對於 SCDATA_SCUNPACKED_BASE 的檔案路徑，例如 'resources/resources.json'
    :param expect: 預期的最外層型別；大部分檔案是陣列，labels.json（遊戲英文在地化表）是物件
    """
    url = f'{SCDATA_SCUNPACKED_BASE}/{path}'
    delay = 1.0
    last_err = None

    for attempt in range(1, SCDATA_MAX_RETRIES + 1):
        try:
            resp = client.get(url)

            if resp.status_code == 429:
                wait = _retry_after_seconds(resp.headers.get('Retry-After', ''), delay)
                last_err = f'HTTP 429（Retry-After={resp.headers.get("Retry-After", "-")}）'
                logger.warning('scdata: scunpacked %s 429 rate limited, 等 %.1fs 重試 (%d/%d)',
                               path, wait, attempt, SCDATA_MAX_RETRIES)
                time.sleep(wait)
                delay = min(delay * 2, 60)
                continue

            if resp.status_code >= 500:
                last_err = f'HTTP {resp.status_code}'
                logger.warning('scdata: scunpacked %s HTTP %d, 等 %.1fs 重試 (%d/%d)',
                               path, resp.status_code, delay, attempt, SCDATA_MAX_RETRIES)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue

            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, expect):
                raise ValueError(f'預期 JSON {expect.__name__}，收到 {type(payload).__name__}')
            return payload

        # ValueError 涵蓋 json.JSONDecodeError 與上面自己拋的格式檢查——
        # 跟 get_json() 同樣道理，這兩種情況也要重試而不是直接讓整輪同步掛掉。
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as err:
            last_err = err
            logger.warning('scdata: scunpacked %s 請求失敗: %s (%d/%d)',
                           path, err, attempt, SCDATA_MAX_RETRIES)
            time.sleep(delay)
            delay = min(delay * 2, 60)

    raise ScDataError(f'scunpacked {path} 重試 {SCDATA_MAX_RETRIES} 次後仍失敗: {last_err}')


# ─────────────────────────────────────────────── 欄位映射
#
# 把 WMS 真正會查詢／排序的欄位拉平到頂層（好建索引），
# 原始 JSON 整包塞進 raw 保留 —— 未來要加欄位不用重新抓 API。

def map_item(doc: dict) -> Optional[dict]:
    if not doc.get('uuid'):
        return None

    dim = doc.get('dimension') or {}
    mfr = doc.get('manufacturer') or {}
    desc = doc.get('description') or {}
    name = doc.get('name') or ''

    return {
        '_id': doc['uuid'],
        'class_name': doc.get('class_name'),
        'slug': doc.get('slug'),
        'name': name,
        # 前綴查詢（^abc）要走索引就得靠這個小寫欄位
        'name_lower': name.lower(),
        # 查 sc_translations（翻譯同步在同一輪、主檔之前跑），查不到就是 None
        'name_zh': item_name_zh(name, doc.get('class_name') or ''),
        'description_en': desc.get('en_EN') if isinstance(desc, dict) else None,
        'type': doc.get('type'),
        'sub_type': doc.get('sub_type'),
        'classification': doc.get('classification'),
        'size': doc.get('size'),
        'grade': doc.get('grade'),
        'mass': doc.get('mass'),
        # 倉儲容量計算用，單位是 µSCU
        'volume_uscu': dim.get('volume_converted'),
        'volume_unit': dim.get('volume_converted_unit'),
        'volume_m3': dim.get('volume'),
        'cargo_dimension': dim.get('cargo_dimension'),
        'manufacturer_code': mfr.get('code'),
        'manufacturer_name': mfr.get('name'),
        'is_lootable': doc.get('is_lootable'),
        'is_craftable': doc.get('is_craftable'),
        'is_base_variant': doc.get('is_base_variant'),
        'tags': doc.get('tags') or [],
        'game_version': doc.get('version'),
        'source_updated_at': doc.get('updated_at'),
        'web_url': doc.get('web_url'),
        'raw': doc,
    }


def map_vehicle(doc: dict) -> Optional[dict]:
    if not doc.get('uuid'):
        return None

    mfr = doc.get('manufacturer') or {}
    crew = doc.get('crew') or {}
    name = doc.get('name') or ''

    return {
        '_id': doc['uuid'],
        'class_name': doc.get('class_name'),
        'slug': doc.get('slug'),
        'name': name,
        'name_lower': name.lower(),
        'game_name': doc.get('game_name'),
        # 注意單位：cargo_capacity 已經是 SCU，vehicle_inventory 是 µSCU
        'cargo_capacity_scu': doc.get('cargo_capacity'),
        'vehicle_inventory_uscu': doc.get('vehicle_inventory'),
        'inventory_containers': doc.get('inventory_containers') or [],
        'cargo_grids': doc.get('cargo_grids') or [],
        'ore_capacity': doc.get('ore_capacity'),
        'mass_hull': doc.get('mass_hull'),
        'crew_min': crew.get('min'),
        'crew_max': crew.get('max'),
        'size_class': doc.get('size_class'),
        'career': doc.get('career'),
        'role': doc.get('role'),
        'manufacturer_code': mfr.get('code'),
        'manufacturer_name': mfr.get('name'),
        'is_spaceship': doc.get('is_spaceship'),
        'is_gravlev': doc.get('is_gravlev'),
        'msrp': doc.get('msrp'),
        'game_version': doc.get('version'),
        'source_updated_at': doc.get('updated_at'),
        'web_url': doc.get('web_url'),
        'raw': doc,
    }


def map_commodity(doc: dict) -> Optional[dict]:
    if not doc.get('uuid'):
        return None

    name = doc.get('name') or ''
    return {
        '_id': doc['uuid'],
        'key': doc.get('key'),
        'slug': doc.get('slug'),
        'name': name,
        'name_lower': name.lower(),
        'display_name': doc.get('display_name'),
        'commodity_groups': doc.get('commodity_groups') or [],
        # 貨櫃拆併櫃用：可用的箱體規格（SCU）
        'box_sizes_scu': doc.get('box_sizes_scu') or [],
        'density_g_per_cc': doc.get('density_g_per_cc'),
        'is_mineable': doc.get('is_mineable'),
        'has_salvage': doc.get('has_salvage'),
        'tier': doc.get('tier'),
        'web_url': doc.get('web_url'),
        'raw': doc,
    }


def map_blueprint(doc: dict) -> Optional[dict]:
    """製造藍圖（Star Citizen 4.10 的 crafting 配方）。

    ⚠️ 這是**遊戲主檔**，跟 src/models/blueprint.py 的 `blueprints` collection
    是兩件不同的事：
      - blueprint_master（這裡）＝ 遊戲裡總共存在哪些配方，由 API 同步，唯讀
      - blueprints        ＝ 某個玩家聲稱自己擁有哪張藍圖，玩家自己填

    兩者靠 blueprints.blueprint_uuid 連起來（可為空，允許自由輸入）。

    `output_item_uuid` 直接對得上 item_master._id，所以「這張藍圖產出哪個物品」
    「這個物品要什麼材料」都能 join 現有物品主檔。
    """
    if not doc.get('uuid'):
        return None

    output = doc.get('output') or {}
    name = doc.get('output_name') or output.get('name') or ''

    # ingredients 只在帶 include 時才有內容（見 WIKI_QUERY_EXTRA），
    # 拉平成精簡結構方便前端直接用，原始資料仍在 raw。
    ingredients = []
    for ing in (doc.get('ingredients') or []):
        ingredients.append({
            'name': ing.get('name'),
            'kind': ing.get('kind'),
            'item_uuid': ing.get('item_uuid'),
            'resource_type_uuid': ing.get('resource_type_uuid'),
            'quantity': ing.get('quantity'),
            'quantity_scu': ing.get('quantity_scu'),
        })

    dismantle = []
    for ret in (doc.get('dismantle_returns') or []):
        dismantle.append({
            'name': ret.get('name'),
            'resource_type_uuid': ret.get('resource_type_uuid'),
            'quantity_scu': ret.get('quantity_scu'),
        })

    return {
        '_id': doc['uuid'],
        # 例如 BP_CRAFT_AMRS_LaserCannon_S1
        'key': doc.get('key'),
        'name': name,
        # 前綴查詢（^abc）要走索引就得靠這個小寫欄位（比照 map_item）
        'name_lower': name.lower(),
        'name_zh': item_name_zh(name, doc.get('output_class') or ''),
        'category_uuid': doc.get('category_uuid'),
        # 對應 item_master._id
        'output_item_uuid': doc.get('output_item_uuid'),
        'output_class': doc.get('output_class'),
        'output_type': output.get('type'),
        'output_type_label': output.get('type_label'),
        'output_sub_type': output.get('sub_type') or output.get('subtype'),
        'output_grade': output.get('grade'),
        'craft_time_seconds': doc.get('craft_time_seconds'),
        'craft_time_label': doc.get('craft_time_label'),
        'is_available_by_default': doc.get('is_available_by_default'),
        'ingredient_count': doc.get('ingredient_count'),
        'unlocking_missions_count': doc.get('unlocking_missions_count'),
        'ingredients': ingredients,
        'dismantle_returns': dismantle,
        'game_version': doc.get('game_version'),
        'web_url': doc.get('web_url'),
        'raw': doc,
    }


def map_mining_deposit(doc: dict) -> Optional[dict]:
    """礦床成分機率表（scunpacked-data resources.json 裡 Kind == 'mineable' 的項目）。

    ⚠️ 這是**靜態**的成分機率對照——某種礦床可能含哪些礦物、比例區間（%）、
    出現機率，跟著遊戲改版變動；不是玩家實際掃描一顆礦石時看到的即時「回波」
    數值，那是遊戲端當下隨機生成的，本來就沒有外部資料源可以同步。
    """
    if doc.get('Kind') != 'mineable' or not doc.get('UUID'):
        return None

    comp = doc.get('Composition') or {}
    parts_raw = comp.get('Parts') or []
    if not parts_raw:
        return None

    parts = []
    for part in parts_raw:
        resource_key = part.get('Key')
        parts.append({
            'resource_key': resource_key,
            'resource_name': part.get('Name'),
            # 中文名稱查 sc_translations（見 src/sc_zh.py），是同步當下的快照：
            # 翻譯更新後要等下一次同步才會反映到這個 collection。
            # 查不到就是 None，前端退回顯示英文名。
            'resource_name_zh': mining_resource_name_zh(resource_key, part.get('Name') or ''),
            'min_percentage': part.get('MinPercentage'),
            'max_percentage': part.get('MaxPercentage'),
            'probability': part.get('Probability'),
        })

    # DepositName 幾乎都有值；doc['Name'] 常常是資料集還沒補上的
    # "<= PLACEHOLDER =>"，只在 DepositName 也缺的極端情況才退回去用。
    deposit_name = comp.get('DepositName') or doc.get('Key') or ''

    return {
        '_id': doc['UUID'],
        'key': doc.get('Key'),
        'deposit_name': deposit_name,
        'deposit_name_lower': deposit_name.lower(),
        'deposit_name_zh': mining_deposit_name_zh(deposit_name),
        'tier': doc.get('Tier'),
        'min_distinct_elements': comp.get('MinimumDistinctElements'),
        'parts': parts,
        # 船艦感測器掃描單顆這種礦床/岩石回傳的基準雷達截面訊號值（RS）。
        # 一叢礦石是這個值的整數倍（1~10 顆），例如某礦床單顆訊號 3000，
        # 掃到 3 顆一叢就會顯示 9000 —— 前端「回波比對」拿玩家輸入的
        # 掃描值去反查是哪個礦床（乘以 1~10 有沒有對得上）。
        # 少數 FPS 徒手採礦專用的項目這個值是 0（船艦掃描器用不到），
        # 前端比對時要排除。
        'signature': doc.get('Signature'),
        'raw': doc,
    }


def map_mining_location(doc: dict) -> Optional[dict]:
    """星系／地點 -> 可能出現哪些礦床、機率多少（scunpacked-data locations.json）。

    每筆是一個「地點群組」（Provider），底下 Groups[].Deposits[] 用
    ResourceUUID 連到 resources.json 的礦床項目——查詢端要顯示礦床名稱
    得自己做 id 對照，這裡先只存原始的 uuid 關聯，不在同步階段展開。
    """
    provider = doc.get('Provider') or {}
    provider_uuid = provider.get('UUID')
    if not provider_uuid:
        return None

    groups = []
    for group in (doc.get('Groups') or []):
        deposits = []
        for dep in (group.get('Deposits') or []):
            resource_uuid = dep.get('ResourceUUID')
            if not resource_uuid:
                continue
            deposits.append({
                'resource_uuid': resource_uuid,
                'relative_probability': dep.get('RelativeProbability'),
            })
        if not deposits:
            continue
        groups.append({
            'group_name': group.get('GroupName'),
            'group_probability': group.get('GroupProbability'),
            'deposits': deposits,
        })

    if not groups:
        return None

    locations = doc.get('Locations') or []
    # 有些 Provider 底下掛好幾個 Locations，優先挑有標星系的那筆。
    picked = next((loc for loc in locations if loc.get('System')),
                  locations[0] if locations else {})
    system = picked.get('System')
    location_name = picked.get('Name') or provider.get('Name') or ''

    return {
        '_id': provider_uuid,
        'provider_name': provider.get('Name'),
        'system': system,
        'location_name': location_name,
        'location_name_lower': location_name.lower(),
        'location_name_zh': location_name_zh(location_name),
        'groups': groups,
        'raw': doc,
    }


def _uuid_from_link(link) -> Optional[str]:
    """`https://api.star-citizen.wiki/api/blueprints/<uuid>` → `<uuid>`。"""
    if not isinstance(link, str) or not link.strip():
        return None
    tail = link.rstrip('/').rsplit('/', 1)[-1]
    return tail or None


def _names(values) -> list:
    """星系這類欄位上游可能給字串或 {name: ...}，統一成名稱清單。"""
    out = []
    for v in values or []:
        name = v.get('name') if isinstance(v, dict) else v
        if isinstance(name, str) and name.strip() and name.strip() not in out:
            out.append(name.strip())
    return out


_API_BLUEPRINT_LINK = '/api/blueprints/'


def _entry_blueprint_uuid(entry: dict) -> Optional[str]:
    """獎勵藍圖的一筆 → 藍圖 uuid（找不到回 None，之後再用物品 uuid 對主檔）。

    上游不同端點給的形狀不一樣：明細是「池 → items[]」，每筆 item 的 `uuid` 是
    **產出物品**的 uuid、藍圖 uuid 在 `blueprint_link`（.../api/blueprints/<uuid>）；
    列表帶 include=blueprints 時可能直接是一串藍圖物件。只信 API 連結（網頁連結
    web_blueprint_link 的結尾是名稱 slug，不是 uuid）。
    """
    if entry.get('blueprint_uuid'):
        return str(entry['blueprint_uuid'])
    for field in ('blueprint_link', 'link', 'api_link'):
        link = entry.get(field)
        if isinstance(link, str) and _API_BLUEPRINT_LINK in link:
            return _uuid_from_link(link)
    if str(entry.get('key') or '').upper().startswith('BP_') and entry.get('uuid'):
        return str(entry['uuid'])
    return None


def parse_blueprint_pools(raw) -> tuple:
    """任務的獎勵藍圖 → (pools, 攤平的藍圖 uuid)。

    pools：[{pool_uuid, drop_chance, items: [{name, item_uuid, blueprint_uuid}]}]。
    兩種上游形狀都吃：「池 → items[]」（明細端點），以及直接一串藍圖物件（每筆當成
    自己一個池）。連結裡拿不到藍圖 uuid 的，用產出物品 uuid 到藍圖主檔
    （blueprint_master.output_item_uuid）反查——所以藍圖要先同步過。
    """
    from src.models.item import BlueprintMaster   # 避免 import 迴圈

    pools = []
    for pool in raw or []:
        if not isinstance(pool, dict):
            continue
        entries = pool.get('items') if isinstance(pool.get('items'), list) else [pool]
        chance = pool.get('drop_chance')
        if chance is None and pool.get('drop_chance_percent') is not None:
            chance = pool['drop_chance_percent'] / 100
        if chance is None:
            chance = pool.get('chance')
        items = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            item_uuid = e.get('output_item_uuid') or e.get('item_uuid') \
                or (e.get('uuid') if 'items' in pool or e.get('item_link') else None)
            items.append({
                'name': e.get('name') or e.get('output_name'),
                'item_uuid': item_uuid,
                'blueprint_uuid': _entry_blueprint_uuid(e),
                '_candidates': [v for v in (e.get('uuid'), item_uuid) if v],
            })
        pools.append({'pool_uuid': pool.get('pool_uuid'), 'drop_chance': chance, 'items': items})

    # 連結裡沒有藍圖 uuid 的，用候選 uuid（藍圖本身或產出物品）到主檔對
    missing = {c for p in pools for it in p['items'] if not it['blueprint_uuid'] for c in it['_candidates']}
    resolved = BlueprintMaster.resolve_ids(missing) if missing else {}
    blueprint_uuids = []
    for p in pools:
        for it in p['items']:
            if not it['blueprint_uuid']:
                it['blueprint_uuid'] = next((resolved[c] for c in it['_candidates'] if c in resolved), None)
            it.pop('_candidates', None)
            if it['blueprint_uuid'] and it['blueprint_uuid'] not in blueprint_uuids:
                blueprint_uuids.append(it['blueprint_uuid'])
    return pools, blueprint_uuids


def map_mission(doc: dict) -> Optional[dict]:
    """任務（Star Citizen Wiki API /missions?include=blueprints）。

    中文標題／說明／發布者／勢力名稱是同步當下從 sc_translations 查的快照
    （翻譯先同步、主檔後同步，見 tasks/scdata_sync.py 的 _do_sync），查不到是 None。
    """
    if not doc.get('uuid'):
        return None

    title = (doc.get('title') or '').strip()
    description = clean_mission_text(doc.get('description') or '') or ''
    texts = mission_text_zh(title, doc.get('description') or '')
    faction = doc.get('faction') or {}
    faction_name = (faction.get('name') or '').strip() if isinstance(faction, dict) else ''
    giver = (doc.get('mission_giver') or '').strip()

    pools, blueprint_uuids = parse_blueprint_pools(doc.get('blueprints'))

    reputation = []
    for rep in (doc.get('reputation_gained') or []):
        if isinstance(rep, dict):
            reputation.append({
                'faction': rep.get('faction'),
                'faction_uuid': rep.get('faction_uuid'),
                'scope': rep.get('scope'),
                'tier': rep.get('tier'),
                'amount': rep.get('amount'),
            })

    return {
        '_id': doc['uuid'],
        'title': title,
        'title_lower': title.lower(),
        'title_zh': texts['title_zh'],
        'title_key': texts['title_key'],
        'description': description,
        'description_zh': texts['description_zh'],
        'debug_name': doc.get('debug_name'),
        'mission_giver': giver,
        'mission_giver_zh': mission_giver_zh(giver) if giver else None,
        'faction_uuid': faction.get('uuid') if isinstance(faction, dict) else None,
        'faction_name': faction_name,
        'faction_name_zh': faction_name_zh(faction_name) if faction_name else None,
        # 上游的任務分類（Hauling／Assassination／…），畫面上的「類型」
        'reward_scope': doc.get('reward_scope'),
        'illegal': bool(doc.get('illegal')),
        'legality_label': doc.get('legality_label'),
        'rank_index': doc.get('rank_index'),
        'shareable': doc.get('shareable'),
        'once_only': doc.get('once_only'),
        'has_combat': doc.get('has_combat'),
        'has_defend_objective': doc.get('has_defend_objective'),
        'has_hauling': doc.get('has_hauling'),
        'has_chain': doc.get('has_chain'),
        'has_prerequisites': doc.get('has_prerequisites'),
        'enemy_count_min': doc.get('enemy_count_min'),
        'enemy_count_max': doc.get('enemy_count_max'),
        'reward_min': doc.get('reward_min'),
        'reward_max': doc.get('reward_max'),
        'reward_currency': doc.get('reward_currency'),
        'reputation_amount': doc.get('reputation_amount'),
        'reputation_gained': reputation,
        'min_standing_name': doc.get('min_standing_name'),
        'max_standing_name': doc.get('max_standing_name'),
        'min_crime_stat': doc.get('min_crime_stat'),
        'max_crime_stat': doc.get('max_crime_stat'),
        'available_in_prison': doc.get('available_in_prison'),
        'time_to_complete_minutes': doc.get('time_to_complete_minutes'),
        'cooldown_seconds': doc.get('cooldown_seconds'),
        'cooldown_label': doc.get('cooldown_label'),
        'max_players_per_instance': doc.get('max_players_per_instance'),
        'hauling_summary': doc.get('hauling_summary') or [],
        'star_systems': _names(doc.get('star_systems')),
        'variant_count': doc.get('variant_count'),
        'released': doc.get('released'),
        'work_in_progress': doc.get('work_in_progress'),
        'not_for_release': doc.get('not_for_release'),
        'has_blueprints': bool(doc.get('has_blueprints')),
        'blueprint_pools': pools,
        # 攤平的藍圖 uuid（有索引），「這張藍圖由哪些任務解鎖」靠它反查
        'blueprint_uuids': blueprint_uuids,
        'game_version': doc.get('game_version') or doc.get('version'),
        'web_url': doc.get('web_url'),
        'raw': doc,
    }


def map_faction(doc: dict) -> Optional[dict]:
    """勢力（Star Citizen Wiki API /factions，列表＋明細合併後的那筆）。

    介紹欄位（說明、總部、領導…）的中文來自翻譯包同前綴的 RepUI 條目
    （見 src/sc_zh.py 的 faction_texts_zh），是同步當下的快照。
    """
    if not doc.get('uuid'):
        return None
    name = (doc.get('name') or '').strip()
    texts = faction_texts_zh(name) if name else {}
    out = {
        '_id': doc['uuid'],
        'name': name,
        'name_lower': name.lower(),
        'name_zh': texts.get('name_zh'),
        'faction_type': doc.get('faction_type'),
        'lawful': doc.get('lawful'),
        'is_npc': doc.get('is_npc'),
        'has_reputation': doc.get('has_reputation'),
        'able_to_arrest': doc.get('able_to_arrest'),
        'polices_criminality': doc.get('polices_criminality'),
        'polices_lawful_trespass': doc.get('polices_lawful_trespass'),
        'no_legal_rights': doc.get('no_legal_rights'),
        'default_reaction': doc.get('default_reaction'),
        # 結構隨上游變動，原樣保留，前端只做容錯顯示
        'reputation_ladder': doc.get('reputation_ladder'),
        'web_url': doc.get('web_url'),
        'raw': doc,
    }
    for field in ('description', 'focus', 'headquarters', 'leadership', 'area', 'founded'):
        value = doc.get(field)
        out[field] = value.strip() if isinstance(value, str) else value
        out[f'{field}_zh'] = texts.get(f'{field}_zh')
    return out


# resource -> (collection 名稱, mapper)。要加新資源就在這裡加一組。
WIKI_RESOURCES: dict = {
    'items': ('item_master', map_item),
    'vehicles': ('vehicle_master', map_vehicle),
    'commodities': ('commodity_master', map_commodity),
    'blueprints': ('blueprint_master', map_blueprint),
    'factions': ('faction_master', map_faction),
    'missions': ('mission_master', map_mission),
}

# resource -> (collection, 用來組 _id 的欄位候選)
# 註：UEX 欄位名稱依官方文件，第一次同步後請用 db.uex_items.findOne() 確認
UEX_RESOURCES: dict = {
    'items': ('uex_items', ['id']),
    'terminals': ('uex_terminals', ['id']),
    'items_prices_all': ('uex_items_prices', ['id_item', 'id_terminal']),
    # 商品（含礦物）的縮寫代碼 code，例如 AGRI、QUAN；礦物資料庫靠名稱關聯（src/models/uex_commodity.py）
    'commodities': ('uex_commodities', ['id']),
}

_UNSET_MARKERS = ('<= UNINITIALIZED =>', '<= PLACEHOLDER =>')


def _real_text(value) -> str:
    """scunpacked 的未設定值（'<= UNINITIALIZED =>'、'<= PLACEHOLDER =>'）當成空字串。"""
    if not isinstance(value, str):
        return ''
    value = value.strip()
    return '' if any(m in value for m in _UNSET_MARKERS) else value


def map_starmap(doc: dict) -> Optional[dict]:
    """星圖地點（scunpacked-data starmap.json，約 2,000 筆：星系、行星、衛星、太空站、
    前哨站、小行星…）。

    上層關係只存 parent_uuid；所屬星系、上層名稱要等整份寫完才算得出來，
    同步完由 src/models/starmap.py 的 Starmap.rebuild_hierarchy() 補上。
    中文是同步當下從 sc_translations 查的快照（見 src/sc_zh.py「星圖地點」一節）；
    翻譯更新後由 Starmap.refresh_translations() 重新比對。
    """
    if not doc.get('UUID'):
        return None
    type_ = doc.get('Type') or {}
    type_code = type_.get('Name') or ''
    name = _real_text(doc.get('Name'))
    description = _real_text(doc.get('Description'))
    jurisdiction = doc.get('Jurisdiction') if isinstance(doc.get('Jurisdiction'), dict) else {}
    jurisdiction_name = _real_text(jurisdiction.get('Name'))
    affiliation = doc.get('Affiliation') if isinstance(doc.get('Affiliation'), dict) else {}
    from src.models.starmap import features_from_amenities   # 避免 import 迴圈
    amenities = []
    for a in doc.get('Amenities') or []:
        if not isinstance(a, dict):
            continue
        label = _real_text(a.get('DisplayName')) or _real_text(a.get('Name'))
        if label and label not in (x['name'] for x in amenities):
            amenities.append({'name': label, 'name_zh': amenity_zh(label)})
    quantum = doc.get('QuantumTravel') or {}
    tag = doc.get('LocationHierarchyTag') if isinstance(doc.get('LocationHierarchyTag'), dict) else {}

    return {
        '_id': doc['UUID'],
        'name': name,
        'name_lower': name.lower(),
        'name_zh': starmap_name_zh(name) if name else None,
        'is_named': bool(name),
        'description': description,
        'description_zh': starmap_description_zh(description) if description else None,
        'type': type_code,
        'type_zh': starmap_type_zh(type_code),
        'classification': _real_text(type_.get('Classification')),
        'quantum_travel': bool(type_.get('ValidQuantumTravelDestination')),
        'parent_uuid': doc.get('ParentUUID'),
        'hierarchy_tag': tag.get('Name'),
        'jurisdiction': jurisdiction_name,
        'jurisdiction_zh': jurisdiction_zh(jurisdiction_name) if jurisdiction_name else None,
        'is_prison': bool(jurisdiction.get('IsPrison')),
        'affiliation': _real_text(affiliation.get('DisplayName') or affiliation.get('Name')),
        'amenities': amenities,
        'amenity_count': len(amenities),
        # 各屬性一個布林欄位（has_hangar、shop_weapons…）、機庫／停機坪尺寸、自動「可存放」。
        # 實際的 can_store 要套上人工修正，同步完由 Starmap.apply_storage() 算
        **features_from_amenities(x['name'] for x in amenities),
        'respawn_type': None if doc.get('RespawnLocationType') in (None, 'None') else doc.get('RespawnLocationType'),
        'nav_icon': doc.get('NavIcon'),
        'size': doc.get('Size'),
        'arrival_radius': quantum.get('ArrivalRadius'),
        'hide_in_starmap': bool(doc.get('HideInStarmap')),
        'is_scannable': bool(doc.get('IsScannable')),
        'raw': doc,
    }


# resource -> (collection 名稱, 檔案路徑, mapper)。跟 WIKI_RESOURCES 不同的是
# 沒有分頁、不用 token——scunpacked-data 就是幾個公開的靜態 JSON 檔。
SCUNPACKED_RESOURCES: dict = {
    'mining_deposits': ('mining_deposit_master', 'resources/resources.json', map_mining_deposit),
    'mining_locations': ('mining_location_master', 'resources/locations.json', map_mining_location),
    'starmap': ('starmap_master', 'starmap.json', map_starmap),
}

#: 同步項目 → 它包含的 scunpacked 資源（見 src/models/sync_schedule.py 的 SYNC_JOBS）
SCUNPACKED_JOBS: dict = {
    'mining': ['mining_deposits', 'mining_locations'],
    'locations': ['starmap'],
}


def uex_doc_id(row: dict, key_fields: list) -> Optional[str]:
    parts = []
    for field in key_fields:
        value = row.get(field)
        if value in (None, ''):
            return None
        parts.append(str(value))
    return ':'.join(parts)


def has_uex_token() -> bool:
    from src.models.app_setting import UexToken   # 後台設定優先，其次環境變數
    return bool(UexToken.get())
