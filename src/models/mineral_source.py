"""礦物的取得方式（後台手動填寫）：mineral_sources。

遊戲資料（scunpacked-data）只有「哪些地點會刷出哪些礦床」，有些礦物要先完成特殊行動、任務或活動才挖得到
（例如科力晶 Carinite），資料裡沒有、也標不出產地。這些由管理員在後台「礦物」補上，玩家頁「資料庫 › 礦物」顯示。

為什麼另開 collection：礦物沒有自己的文件（礦物資料庫是從礦床成分 mining_deposit_master 加地點
mining_location_master 即時彙整），而那兩個 collection 是同步排程整份覆寫的，人工資料放進去會被蓋掉。

自動判斷（auto_sources）：Star Citizen Wiki API 的 commodities（同步項目「商品」寫進 commodity_master）
標成可開採（is_mineable）、卻沒有任何產地（locations／methods 都空）的礦物，就是要特殊方式才拿得到的候選，
例如 Carinite。這份是每次讀取時從 commodity_master 算出來的（跟著排程同步更新），不寫進 mineral_sources，
所以不會蓋掉管理員手填的內容；玩家頁以手填為主，沒填的才顯示自動判斷。

一筆＝一種礦物，_id＝礦床成分的 resource_key（例如 Carinite、CarinitePure）：
    resource_name   英文名稱（顯示用，填寫當下的快照）
    methods         取得方式代碼清單（METHODS）
    description     說明（Markdown，前端先跳脫再轉換，見 frontend/src/utils/markdown.js）
    locations       相關地點（文字清單：星圖地點英文名稱或自由輸入）
    source_url      參考連結（只接受 http／https）
    updated_by／updated_at
"""

from datetime import datetime
from typing import Optional

from src.mongo import get_db

COLLECTION = 'mineral_sources'

#: 取得方式：代碼 → 顯示文字（前端用同一份，見 GET /mining/sources 的 methods）
METHODS = {
    'special': '特殊行動',
    'mission': '任務獎勵',
    'cave': '洞穴',
    'event': '活動限定',
    'other': '其他',
}
#: 前端顯示用（含自動判斷的代碼）
METHOD_LABELS = {**METHODS, 'unplaced': '需特殊取得'}
DESCRIPTION_MAX = 5000
LOCATIONS_MAX = 30
TEXT_MAX = 200


def _col():
    return get_db()[COLLECTION]


def _clean_text(value, limit: int = TEXT_MAX) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ''


def clean(data: dict) -> dict:
    """驗證並整理輸入；不合法丟 ValueError。"""
    if not isinstance(data, dict):
        raise ValueError('資料格式錯誤')
    methods = data.get('methods') or []
    if not isinstance(methods, list) or not all(isinstance(m, str) for m in methods):
        raise ValueError('methods 必須是字串陣列')
    unknown = [m for m in methods if m not in METHODS]
    if unknown:
        raise ValueError(f'不認得的取得方式：{"、".join(unknown)}')
    description = data.get('description') or ''
    if not isinstance(description, str):
        raise ValueError('說明必須是文字')
    if len(description) > DESCRIPTION_MAX:
        raise ValueError(f'說明最多 {DESCRIPTION_MAX} 字')
    locations = data.get('locations') or []
    if not isinstance(locations, list) or not all(isinstance(x, str) for x in locations):
        raise ValueError('locations 必須是字串陣列')
    locations = list(dict.fromkeys(x.strip()[:TEXT_MAX] for x in locations if x.strip()))
    if len(locations) > LOCATIONS_MAX:
        raise ValueError(f'相關地點最多 {LOCATIONS_MAX} 個')
    url = _clean_text(data.get('source_url'), 500)
    if url and not url.lower().startswith(('http://', 'https://')):
        raise ValueError('參考連結必須是 http:// 或 https:// 開頭')
    out = {
        'methods': list(dict.fromkeys(methods)),
        'description': description.strip(),
        'locations': locations,
        'source_url': url or None,
        'resource_name': _clean_text(data.get('resource_name')) or None,
    }
    if not out['methods'] and not out['description']:
        raise ValueError('至少要選一種取得方式或填寫說明')
    return out


def list_all() -> list:
    return list(_col().find({}).sort('_id', 1))


def get(key: str) -> Optional[dict]:
    return _col().find_one({'_id': key})


def upsert(key: str, data: dict, username: str = '') -> dict:
    key = (key or '').strip()
    if not key or len(key) > TEXT_MAX:
        raise ValueError('礦物代碼錯誤')
    doc = clean(data)
    doc.update({'updated_by': username or None, 'updated_at': datetime.utcnow()})
    _col().update_one({'_id': key}, {'$set': doc}, upsert=True)
    return get(key)


def delete(key: str) -> bool:
    return _col().delete_one({'_id': (key or '').strip()}).deleted_count > 0


#: 自動判斷的取得方式代碼（不在 METHODS 裡，前端顯示「需特殊取得」）
AUTO_METHOD = 'unplaced'


def _desc_zh(text: str) -> Optional[str]:
    """遊戲說明的中文（翻譯包 items_commodities_<key>_desc）。"""
    if not text:
        return None
    from src.models import translation as T
    return T.by_english(text, ['items_commodities_'])


def auto_sources() -> dict:
    """{resource_key: 自動判斷}：commodity_master 裡可開採但遊戲資料沒標產地的礦物。

    key 用商品的 key（遊戲內代碼，跟礦床成分的 resource_key 一樣，例如 Carinite、CarinitePure）。
    """
    col = get_db()['commodity_master']
    q = {'is_current': {'$ne': False}, 'is_mineable': True}
    out = {}
    rows = col.find(
        q,
        {'key': 1, 'name': 1, 'methods': 1, 'systems': 1, 'location_count': 1, 'description': 1, 'web_url': 1,
         'raw.methods': 1, 'raw.locations': 1, 'raw.description': 1, '_sync': 1})
    for r in rows:
        raw = r.get('raw') or {}
        methods = r.get('methods') if 'methods' in r else raw.get('methods')
        loc_count = r.get('location_count') if 'location_count' in r else len(raw.get('locations') or [])
        if methods or loc_count or not r.get('key'):
            continue
        desc = r.get('description') if 'description' in r else raw.get('description')
        if desc and '<=' in desc:   # 佔位文字
            desc = None
        out[r['key']] = {
            'key': r['key'], 'resource_name': r.get('name'), 'methods': [AUTO_METHOD],
            # _desc_zh → T.by_english 有行程內快取（翻譯版本變了才清），每筆一次查詢只發生在冷快取
            'description_en': desc, 'description_zh': _desc_zh(desc),
            'web_url': r.get('web_url'), 'source': 'Star Citizen Wiki API',
            'synced_at': (r.get('_sync') or {}).get('at'),
        }
    return out
