"""RSI 官方商店的 CCU（Cross-Chassis Upgrade）資料：抓取與欄位映射（寫入見 src/models/ccu.py）。

資料來源是官網「升級」工具（https://robertsspaceindustries.com/pledge/ship-upgrades）背後用的端點，
不需要登入（匿名 token）。⚠️ 這不是 RSI 公開文件化的 API，欄位可能隨官網改版變動：
抓下來的原始回應會整份記在 log 與 rsi_ships.raw，映射函式對缺欄位一律容錯，
抓到的船數跟上次差太多時整輪判定失敗、不下架任何資料（見 tasks/scdata_sync.py 的 _sync_ccu）。

流程：
  1. POST /api/account/v2/setAuthToken            → 匿名的 Rsi-Token cookie
  2. POST /api/ship-upgrades/setContextToken       → 升級工具的 context cookie
  3. GraphQL initShipUpgrade                       → 全部船：標準價（msrp）＋單買的船 SKU（含 Warbond 版）
  4. GraphQL filterShips(fromId=最便宜的船)          → 每艘船目前能買的升級 SKU 與升級價
  5. 商店 GraphQL（/graphql 的 store.search，Standalone Ships 分類）→ 商店「現在真的有在賣」的單買船

⚠️ 第 3 步的 SKU 不等於商店有在賣：升級工具會一直列著 Warbond Edition（標 available），
例如 M2 Hercules 的 WB $480 在商店早就沒賣了。所以單買船的 SKU 一律要在第 5 步的商店清單裡找到
同一艘船、同樣價格、同樣是不是 Warbond 的品項才算上架（confirm_ship_offers）；商店有、升級工具沒列的
（例如新船的 WB）另外補一筆（store_only）。升級（CCU）只在升級工具買，不用再確認。

價格單位：回應是「分」（app.pricing.exponent，預設 2），這裡一律換成美金（未稅）。
只抓「現在商店有賣的」：歷史（開始、結束日期）靠排程每次的快照累積（src/models/ccu.py）。
"""

import logging
import re
from typing import Optional

import httpx

from src.textnorm import norm_ascii as _norm  # 船名比對的正規化（I1：共用一份）

logger = logging.getLogger(__name__)

RSI_BASE = 'https://robertsspaceindustries.com'
AUTH_TOKEN_URL = f'{RSI_BASE}/api/account/v2/setAuthToken'
CONTEXT_TOKEN_URL = f'{RSI_BASE}/api/ship-upgrades/setContextToken'
GRAPHQL_URL = f'{RSI_BASE}/pledge-store/api/upgrade/graphql'
UPGRADE_PAGE = f'{RSI_BASE}/pledge/ship-upgrades'
#: 商店（pledge store）的 GraphQL；Standalone Ships 的 product id 是 72
STORE_GRAPHQL_URL = f'{RSI_BASE}/graphql'
STANDALONE_PRODUCT = '72'
STORE_PAGE_SIZE = 100
STORE_MAX_PAGES = 10
STORE_QUERY = """query StoreSkus($storeFront: String, $query: SearchQuery) {
  store(name: $storeFront, browse: true) {
    search(query: $query) {
      count
      resources {
        ... on TySku { id name isWarbond url price { amount } stock { available } gameItems { name kind } }
      }
    }
  }
}
"""

INIT_QUERY = """query initShipUpgrade {
  ships {
    id
    name
    msrp
    link
    focus
    type
    flyableStatus
    manufacturer { id name }
    skus { id title available price body unlimitedStock availableStock }
  }
  app { pricing { currencyCode exponent } }
}
"""

FILTER_QUERY = """query filterShips($fromId: Int, $toId: Int, $fromFilters: [FilterConstraintValues], $toFilters: [FilterConstraintValues]) {
  from(to: $toId, filters: $fromFilters) { ships { id } }
  to(from: $fromId, filters: $toFilters) {
    ships {
      id
      skus { id title price upgradePrice available availableStock unlimitedStock }
    }
  }
}
"""


class RsiStoreError(Exception):
    """RSI 商店回應不對（被擋、格式變了、GraphQL 回錯誤）。"""


# ─────────────────────────────────────────────────────────── 抓取

def _rsi_headers(client: httpx.Client) -> dict:
    headers = {'Content-Type': 'application/json', 'Origin': RSI_BASE, 'Referer': UPGRADE_PAGE}
    token = client.cookies.get('Rsi-Token')
    if token:
        headers['x-rsi-token'] = token
    return headers


def _post_json(client: httpx.Client, url: str, payload, label: str):
    resp = client.post(url, json=payload, headers=_rsi_headers(client))
    if resp.status_code >= 400:
        raise RsiStoreError(f'{label}：HTTP {resp.status_code}')
    try:
        return resp.json()
    except ValueError:
        raise RsiStoreError(f'{label}：回應不是 JSON（可能被 Cloudflare 擋下）') from None


def open_session(client: httpx.Client) -> None:
    """取得匿名 token 與升級工具的 context（cookie 存在 client 裡）。"""
    _post_json(client, AUTH_TOKEN_URL, {}, 'setAuthToken')
    _post_json(client, CONTEXT_TOKEN_URL, {}, 'setContextToken')


def graphql(client: httpx.Client, operation: str, query: str, variables: Optional[dict] = None,
            url: str = GRAPHQL_URL) -> dict:
    body = _post_json(client, url,
                      [{'operationName': operation, 'variables': variables or {}, 'query': query}],
                      f'GraphQL {operation}')
    first = body[0] if isinstance(body, list) and body else body
    if not isinstance(first, dict):
        raise RsiStoreError(f'GraphQL {operation}：回應格式不對')
    if first.get('errors'):
        msg = '; '.join(str(e.get('message', e)) for e in first['errors'][:3] if isinstance(e, dict))
        raise RsiStoreError(f'GraphQL {operation}：{msg or first["errors"]}')
    data = first.get('data')
    if not isinstance(data, dict):
        raise RsiStoreError(f'GraphQL {operation}：沒有 data')
    return data


def fetch_store(client: httpx.Client) -> dict:
    """抓一輪：{'ships': [...], 'upgrades': [...], 'from_id': int, 'exponent': int}（原始欄位，未映射）。"""
    open_session(client)
    init = graphql(client, 'initShipUpgrade', INIT_QUERY)
    ships = [s for s in (init.get('ships') or []) if isinstance(s, dict)]
    if not ships:
        raise RsiStoreError('initShipUpgrade 沒有任何船')
    exponent = _exponent(init)
    base = cheapest_ship(ships)
    upgrades = []
    if base is not None:
        data = graphql(client, 'filterShips', FILTER_QUERY,
                       {'fromId': base['id'], 'toId': None, 'fromFilters': [], 'toFilters': []})
        upgrades = [s for s in ((data.get('to') or {}).get('ships') or []) if isinstance(s, dict)]
    listing = fetch_store_listing(client)
    return {'ships': ships, 'upgrades': upgrades, 'from_id': base['id'] if base else None, 'exponent': exponent,
            'listing': listing}


def fetch_store_listing(client: httpx.Client) -> list:
    """商店 Standalone Ships 分類現在列著的全部品項（原始欄位），一頁 100 筆翻到底。
    一筆都沒有、或翻到 STORE_MAX_PAGES 頁還沒翻完都丟 RsiStoreError（不完整的清單會把沒抓到的當成下架）。"""
    out = []
    for page in range(1, STORE_MAX_PAGES + 1):
        data = graphql(client, 'StoreSkus', STORE_QUERY,
                       {'storeFront': 'pledge',
                        'query': {'skus': {'products': [STANDALONE_PRODUCT]}, 'limit': STORE_PAGE_SIZE, 'page': page}},
                       url=STORE_GRAPHQL_URL)
        rows = [r for r in ((((data.get('store') or {}).get('search') or {}).get('resources')) or []) if isinstance(r, dict)]
        out += rows
        if len(rows) < STORE_PAGE_SIZE:
            break
    else:
        # 翻到上限頁還是滿的：後面還有沒抓到的品項，照算會把它們當成商店沒賣、提早下架（I2）
        raise RsiStoreError(f'商店的單買船清單超過 {STORE_MAX_PAGES} 頁（每頁 {STORE_PAGE_SIZE} 筆）沒翻完，'
                            '不更新；品項真的變多就調高 STORE_MAX_PAGES')
    if not out:
        raise RsiStoreError('商店的單買船清單是空的（可能格式改了），不更新')
    return out


# ─────────────────────────────────────────────────────────── 映射（純函式，可單獨測試）

def _exponent(init: dict) -> int:
    try:
        return int((((init.get('app') or {}).get('pricing') or {}).get('exponent')))
    except (TypeError, ValueError):
        return 2


def to_usd(cents, exponent: int = 2) -> Optional[float]:
    """分 → 美金；不是數字回 None。"""
    try:
        value = float(cents)
    except (TypeError, ValueError):
        return None
    return round(value / (10 ** exponent), 2)


def cheapest_ship(ships: list) -> Optional[dict]:
    """標準價最低（> 0）的船：拿它當升級的起點，才看得到所有船的升級 SKU。"""
    priced = [s for s in ships if isinstance(s.get('msrp'), (int, float)) and s['msrp'] > 0 and s.get('id') is not None]
    return min(priced, key=lambda s: s['msrp']) if priced else None


_INSURANCE_RE = re.compile(r'\b(LTI|lifetime insurance|(\d+)\s*-?\s*(year|month)s?\s*insurance)\b', re.I)
_TAG_RE = re.compile(r'<[^>]+>')


def parse_insurance(*texts) -> Optional[str]:
    """從 SKU 標題／說明找保險期限：'LTI'、'120 個月'、'10 年'…；找不到回 None。"""
    for text in texts:
        if not text:
            continue
        m = _INSURANCE_RE.search(_TAG_RE.sub(' ', str(text)))
        if not m:
            continue
        if m.group(2):
            n, unit = int(m.group(2)), m.group(3).lower()
            return f'{n} 年' if unit.startswith('year') else f'{n} 個月'
        return 'LTI'
    return None


def _is_warbond(title) -> bool:
    return 'warbond' in str(title or '').lower()


def _stock(sku: dict):
    if sku.get('unlimitedStock'):
        return None
    try:
        return int(sku.get('availableStock'))
    except (TypeError, ValueError):
        return None


def map_ships(raw_ships: list, exponent: int = 2) -> list:
    """船：{rsi_id, name, msrp（美金）, manufacturer, focus, type, flyable_status, link}。沒 id 或名稱的略過。"""
    out = []
    for s in raw_ships:
        if s.get('id') is None or not s.get('name'):
            continue
        out.append({
            'rsi_id': int(s['id']),
            'name': str(s['name']).strip(),
            'msrp': to_usd(s.get('msrp'), exponent),
            'manufacturer': ((s.get('manufacturer') or {}).get('name') or '').strip(),
            'focus': s.get('focus') or '',
            'type': s.get('type') or '',
            'flyable_status': s.get('flyableStatus') or '',
            'link': (RSI_BASE + s['link']) if str(s.get('link') or '').startswith('/') else (s.get('link') or ''),
        })
    return out


def map_ship_offers(raw_ships: list, exponent: int = 2) -> list:
    """單買的船（standalone）SKU。price 比標準價低的標 is_discount，標題有 Warbond 的標 is_warbond。"""
    out = []
    for s in raw_ships:
        if s.get('id') is None:
            continue
        msrp = to_usd(s.get('msrp'), exponent)
        for sku in s.get('skus') or []:
            if not isinstance(sku, dict) or sku.get('id') is None or sku.get('available') is False:
                continue
            price = to_usd(sku.get('price'), exponent)
            if price is None:
                continue
            savings = round(msrp - price, 2) if msrp is not None and price < msrp else 0.0
            out.append({
                'kind': 'ship', 'sku_id': int(sku['id']), 'ship_rsi_id': int(s['id']),
                'title': str(sku.get('title') or '').strip(), 'price': price, 'msrp': msrp, 'savings': savings,
                'is_warbond': _is_warbond(sku.get('title')), 'is_discount': savings > 0,
                'insurance': parse_insurance(sku.get('title'), sku.get('body')),
                'stock': _stock(sku),
            })
    return out


def map_upgrade_offers(raw_targets: list, ships_by_id: dict, from_id, exponent: int = 2) -> list:
    """升級 SKU（CCU）：每艘目標船目前能買的升級。

    upgrade_price＝從最便宜的船升上去要付的錢（RSI 算好的）；value＝這個升級讓目標船值多少（sku.price）。
    value 比目標船標準價低就是有折扣的 CCU（is_discount；標題有 Warbond 的另標 is_warbond），savings＝標準價 − value，
    從任何比較便宜的船升上去都省這麼多（CCU 的價差＝value − 來源船的價值）。
    """
    out = []
    for t in raw_targets:
        if t.get('id') is None:
            continue
        target = ships_by_id.get(int(t['id'])) or {}
        msrp = target.get('msrp')
        for sku in t.get('skus') or []:
            if not isinstance(sku, dict) or sku.get('id') is None or sku.get('available') is False:
                continue
            value = to_usd(sku.get('price'), exponent)
            if value is None:
                continue
            savings = round(msrp - value, 2) if msrp is not None and value < msrp else 0.0
            out.append({
                'kind': 'ccu', 'sku_id': int(sku['id']), 'ship_rsi_id': int(t['id']),
                'from_rsi_id': int(from_id) if from_id is not None else None,
                'title': str(sku.get('title') or '').strip(), 'price': value, 'msrp': msrp, 'savings': savings,
                'upgrade_price': to_usd(sku.get('upgradePrice'), exponent),
                'is_warbond': _is_warbond(sku.get('title')), 'is_discount': savings > 0,
                'insurance': parse_insurance(sku.get('title')),
                'stock': _stock(sku),
            })
    return out


# ─────────────────────────────────────────────────────────── 商店確認

_STORE_SUFFIX_RE = re.compile(r'\s+-\s+(\d+\s*(year|month)s?|lti|best in show.*|[^-]*edition)\s*$', re.I)


def store_base_name(name: str) -> str:
    """商店品項名稱去掉版本尾巴：「M2 Hercules - 10 Year」→「M2 Hercules」、「Perseus - Best in Show 2956 Edition」→「Perseus」。"""
    return _STORE_SUFFIX_RE.sub('', str(name or '').strip()).strip()


def map_store_listing(resources: list, exponent: int = 2) -> list:
    """商店品項：{store_id, name, base, ship_names（品項裡的船）, price（美金）, is_warbond, url}；下架（stock 不可買）的不收。"""
    out = []
    for r in resources:
        if r.get('id') is None or (r.get('stock') or {}).get('available') is False:
            continue
        price = to_usd((r.get('price') or {}).get('amount'), exponent)
        if price is None:
            continue
        ships = [g.get('name') for g in r.get('gameItems') or [] if isinstance(g, dict) and g.get('kind') == 'SHIP']
        out.append({'store_id': int(r['id']), 'name': str(r.get('name') or '').strip(), 'base': store_base_name(r.get('name')),
                    'ship_names': [n for n in ships if n], 'price': price, 'is_warbond': bool(r.get('isWarbond')),
                    'url': (RSI_BASE + r['url']) if str(r.get('url') or '').startswith('/') else (r.get('url') or '')})
    return out


def confirm_ship_offers(offers: list, ships: list, listing: list) -> tuple:
    """單買船的 SKU 只留商店真的有在賣的（同一艘船、同樣價格、同樣是不是 Warbond），標 store_confirmed；
    商店有、升級工具沒列的補一筆 store_only。升級（kind ccu）原樣保留。回傳 (offers, 統計)。

    船的比對：商店品項名稱去掉版本尾巴（或品項裡的船名）跟升級工具的船名一樣（忽略大小寫、標點）。
    補 store_only 只看品項名稱（不看品項裡的船），避免「Galaxy Complete」這種套組被當成 Galaxy 本體。
    """
    by_name = {}
    for s in ships:
        by_name.setdefault(_norm(s['name']), s)
    store_by_ship, base_ship = {}, {}
    for item in listing:
        base = by_name.get(_norm(item['base']))
        ship = base or next((by_name[_norm(n)] for n in item['ship_names'] if _norm(n) in by_name), None)
        if ship:
            store_by_ship.setdefault(ship['rsi_id'], []).append(item)
            if base:
                base_ship[item['store_id']] = base
    out, used = [], set()
    stats = {'confirmed': 0, 'dropped': 0, 'store_only': 0}
    for o in offers:
        if o.get('kind') != 'ship':
            out.append(o)
            continue
        match = next((it for it in store_by_ship.get(o['ship_rsi_id'], [])
                      if it['store_id'] not in used and abs(it['price'] - o['price']) < 0.005
                      and it['is_warbond'] == bool(o.get('is_warbond'))), None)
        if not match:
            stats['dropped'] += 1
            continue
        used.add(match['store_id'])
        out.append({**o, 'store_confirmed': True, 'store_sku_id': match['store_id'], 'store_url': match['url']})
        stats['confirmed'] += 1
    for item in listing:
        ship = base_ship.get(item['store_id'])
        if not ship or item['store_id'] in used:
            continue
        msrp = ship.get('msrp')
        savings = round(msrp - item['price'], 2) if msrp is not None and item['price'] < msrp else 0.0
        out.append({'kind': 'ship', 'sku_id': item['store_id'], 'ship_rsi_id': ship['rsi_id'], 'title': item['name'],
                    'price': item['price'], 'msrp': msrp, 'savings': savings, 'is_warbond': item['is_warbond'],
                    'is_discount': savings > 0, 'insurance': parse_insurance(item['name']), 'stock': None,
                    'store_confirmed': True, 'store_only': True, 'store_sku_id': item['store_id'], 'store_url': item['url']})
        used.add(item['store_id'])
        stats['store_only'] += 1
    return out, stats
