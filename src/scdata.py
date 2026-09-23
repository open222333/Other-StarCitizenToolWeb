"""星際公民遊戲資料來源客戶端（Star Citizen Wiki API + UEX Corp API）。

沒有官方 CIG API，遊戲資料一律來自社群眾包／解包的第三方 API：

  - Star Citizen Wiki API：物品、載具、商品規格。免費、無 token、按 patch 版本分版。
  - UEX Corp API 2.0：價格、終端與商店位置。需要免費 token（UEX_API_TOKEN 環境變數）。

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
                 SCDATA_SCUNPACKED_BASE, SCDATA_UEX_API_BASE, SCDATA_WIKI_API_BASE,
                 UEX_API_TOKEN)
from src.sc_zh import (
    item_name_zh,
    location_name_zh,
    mining_deposit_name_zh,
    mining_resource_name_zh,
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
}

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


def uex_rows(client: httpx.Client, resource: str) -> list:
    """UEX 回應格式：{"status": "ok", "data": [...]}"""
    payload = get_json(client, f'{SCDATA_UEX_API_BASE}/{resource}/')
    status = payload.get('status')
    if status != 'ok':
        raise ScDataError(f'UEX {resource} 回傳 status={status}')
    return payload.get('data') or []


def fetch_scunpacked_rows(client: httpx.Client, path: str) -> list:
    """抓 scunpacked-data 的靜態 JSON 檔（GitHub raw，單一請求、無分頁、無 token）。

    這批檔案的回應是「裸陣列」（`[...]`），不是 Wiki API 那種 `{"data": [...]}`
    包裝，跟 get_json() 預期回傳 dict 的假設不同，所以另外寫一支；重試邏輯
    （429 / 5xx / 連線錯誤都重試）照抄 get_json()。

    :param path: 相對於 SCDATA_SCUNPACKED_BASE 的檔案路徑，例如 'resources/resources.json'
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
            if not isinstance(payload, list):
                raise ValueError(f'預期 JSON 陣列，收到 {type(payload).__name__}')
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
        # 社群繁中化包查表，查不到就是 None（見 src/sc_zh.py 說明來源與涵蓋範圍）
        'name_zh': item_name_zh(name),
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
        'name_zh': item_name_zh(name),
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
            # 中文名稱來自翻譯包（見 src/sc_zh.py 檔頭），這裡是同步當下
            # 的快照——sc_mining_resource_names_zh.json 改了之後，要等下一次
            # 同步跑過才會反映到這個 collection 裡，不是即時查表。
            # 查不到就是 None，前端退回顯示英文名。
            'resource_name_zh': mining_resource_name_zh(resource_key),
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


# resource -> (collection 名稱, mapper)。要加新資源就在這裡加一組。
WIKI_RESOURCES: dict = {
    'items': ('item_master', map_item),
    'vehicles': ('vehicle_master', map_vehicle),
    'commodities': ('commodity_master', map_commodity),
    'blueprints': ('blueprint_master', map_blueprint),
}

# resource -> (collection, 用來組 _id 的欄位候選)
# 註：UEX 欄位名稱依官方文件，第一次同步後請用 db.uex_items.findOne() 確認
UEX_RESOURCES: dict = {
    'items': ('uex_items', ['id']),
    'terminals': ('uex_terminals', ['id']),
    'items_prices_all': ('uex_items_prices', ['id_item', 'id_terminal']),
}

# resource -> (collection 名稱, 檔案路徑, mapper)。跟 WIKI_RESOURCES 不同的是
# 沒有分頁、不用 token——scunpacked-data 就是幾個公開的靜態 JSON 檔。
SCUNPACKED_RESOURCES: dict = {
    'mining_deposits': ('mining_deposit_master', 'resources/resources.json', map_mining_deposit),
    'mining_locations': ('mining_location_master', 'resources/locations.json', map_mining_location),
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
    return bool(UEX_API_TOKEN)
