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
from typing import Callable, Iterator, Optional

import httpx

from src import (SCDATA_BULK_SIZE, SCDATA_HTTP_TIMEOUT, SCDATA_MAX_RETRIES,
                 SCDATA_PAGE_SIZES, SCDATA_REQUEST_DELAY, SCDATA_USER_AGENT,
                 SCDATA_UEX_API_BASE, SCDATA_WIKI_API_BASE, UEX_API_TOKEN)

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


def get_json(client: httpx.Client, url: str, params: Optional[dict] = None) -> dict:
    """帶指數退避的 GET。429 / 5xx / 連線錯誤都會重試。"""
    delay = 1.0
    last_err = None

    for attempt in range(1, SCDATA_MAX_RETRIES + 1):
        try:
            resp = client.get(url, params=params)

            if resp.status_code == 429:
                wait = float(resp.headers.get('Retry-After', delay))
                logger.warning('scdata: 429 rate limited, 等 %.1fs 重試 (%d/%d)',
                               wait, attempt, SCDATA_MAX_RETRIES)
                time.sleep(wait)
                delay = min(delay * 2, 60)
                continue

            if resp.status_code >= 500:
                logger.warning('scdata: HTTP %d, 等 %.1fs 重試 (%d/%d)',
                               resp.status_code, delay, attempt, SCDATA_MAX_RETRIES)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue

            resp.raise_for_status()
            return resp.json()

        except (httpx.TransportError, httpx.HTTPStatusError) as err:
            last_err = err
            logger.warning('scdata: 請求失敗 %s: %s (%d/%d)',
                           url, err, attempt, SCDATA_MAX_RETRIES)
            time.sleep(delay)
            delay = min(delay * 2, 60)

    raise ScDataError(f'{url} 重試 {SCDATA_MAX_RETRIES} 次後仍失敗: {last_err}')


def wiki_rows(client: httpx.Client, resource: str) -> Iterator[dict]:
    """走訪 Wiki API 分頁（Laravel JSON:API 風格 page[size] / page[number]）。

    直接跟著 links.next 走，不自己算頁數 —— 總筆數會在同步途中變動。
    """
    url = f'{SCDATA_WIKI_API_BASE}/{resource}'
    params = {
        'page[size]': SCDATA_PAGE_SIZES.get(resource, 100),
        'page[number]': 1,
    }

    while url:
        payload = get_json(client, url, params)
        params = None  # links.next 已含查詢字串

        rows = payload.get('data') or []
        meta = payload.get('meta') or {}
        logger.info('scdata: %s 第 %s/%s 頁 (%d 筆, 共 %s)',
                    resource, meta.get('current_page', '?'), meta.get('last_page', '?'),
                    len(rows), meta.get('total', '?'))

        for row in rows:
            yield row

        url = (payload.get('links') or {}).get('next')
        if url:
            time.sleep(SCDATA_REQUEST_DELAY)


def uex_rows(client: httpx.Client, resource: str) -> list:
    """UEX 回應格式：{"status": "ok", "data": [...]}"""
    payload = get_json(client, f'{SCDATA_UEX_API_BASE}/{resource}/')
    status = payload.get('status')
    if status != 'ok':
        raise ScDataError(f'UEX {resource} 回傳 status={status}')
    return payload.get('data') or []


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


# resource -> (collection 名稱, mapper)。要加新資源就在這裡加一組。
WIKI_RESOURCES: dict = {
    'items': ('item_master', map_item),
    'vehicles': ('vehicle_master', map_vehicle),
    'commodities': ('commodity_master', map_commodity),
}

# resource -> (collection, 用來組 _id 的欄位候選)
# 註：UEX 欄位名稱依官方文件，第一次同步後請用 db.uex_items.findOne() 確認
UEX_RESOURCES: dict = {
    'items': ('uex_items', ['id']),
    'terminals': ('uex_terminals', ['id']),
    'items_prices_all': ('uex_items_prices', ['id_item', 'id_terminal']),
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
