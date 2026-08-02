"""遊戲主檔的唯讀模型（物品 / 載具 / 商品）。

這三個 collection 由 tasks/scdata_sync.py 單向寫入，應用層只讀。
要新增欄位就改 src/scdata.py 的 mapper 再重跑同步，不要在這裡補資料。

重要：查詢一律加 is_current=True。舊 patch 移除的物品仍留在 DB（is_current=False），
      這樣庫存紀錄的 item_id 外鍵不會斷。
"""

import re
from typing import Optional

from pymongo import ASCENDING

from src.mongo import get_db


def escape_regex(text: str) -> str:
    """使用者輸入的 . * ( 不該被當成 regex 語法。"""
    return re.escape((text or '').strip())


class _MasterBase:
    """主檔共用的查詢邏輯。子類別只要覆寫 COLLECTION 與 PROJECTION。"""

    COLLECTION = ''
    PROJECTION: dict = {'name': 1}

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def get(cls, doc_id: str) -> Optional[dict]:
        """按 uuid 取單筆。不過濾 is_current —— 庫存可能指向已下架的物品。"""
        return cls._col().find_one({'_id': doc_id})

    @classmethod
    def search(cls, query: str = '', limit: int = 25, include_retired: bool = False) -> list:
        """名稱前綴搜尋，給 autocomplete 用。找不到才退回中綴搜尋。"""
        filt: dict = {} if include_retired else {'is_current': True}

        if (query or '').strip():
            prefix = escape_regex(query).lower()
            filt['$or'] = [
                {'name_lower': {'$regex': f'^{prefix}'}},
                {'class_name': {'$regex': escape_regex(query), '$options': 'i'}},
            ]

        rows = list(cls._col().find(filt, cls.PROJECTION)
                    .sort('name', ASCENDING).limit(limit))

        if not rows and (query or '').strip():
            fallback: dict = {} if include_retired else {'is_current': True}
            fallback['name_lower'] = {'$regex': escape_regex(query).lower()}
            rows = list(cls._col().find(fallback, cls.PROJECTION)
                        .sort('name', ASCENDING).limit(limit))
        return rows

    @classmethod
    def find_by_name(cls, name: str) -> Optional[dict]:
        """完整名稱比對（大小寫不敏感）。"""
        return cls._col().find_one({
            'is_current': True,
            'name_lower': (name or '').strip().lower(),
        })

    @classmethod
    def resolve(cls, value: str) -> Optional[dict]:
        """把使用者輸入解析成單一文件。

        優先序：uuid 直接命中 → 完整名稱 → 唯一的搜尋結果。
        對到多筆或找不到都回 None，由呼叫端決定要怎麼回報。
        """
        value = (value or '').strip()
        if not value:
            return None

        doc = cls.get(value)
        if doc:
            return doc

        doc = cls.find_by_name(value)
        if doc:
            return doc

        candidates = cls.search(value, limit=2)
        if len(candidates) == 1:
            return cls.get(candidates[0]['_id'])
        return None

    @classmethod
    def game_versions(cls) -> list:
        return sorted(v for v in cls._col().distinct('game_version', {'is_current': True}) if v)

    @classmethod
    def count_current(cls) -> int:
        return cls._col().count_documents({'is_current': True})


class ItemMaster(_MasterBase):
    COLLECTION = 'item_master'
    PROJECTION = {
        'name': 1, 'class_name': 1, 'type': 1, 'sub_type': 1, 'size': 1,
        'grade': 1, 'volume_uscu': 1, 'manufacturer_code': 1, 'is_current': 1,
    }

    @classmethod
    def list_by_type(cls, item_type: str = '', limit: int = 50, offset: int = 0) -> tuple:
        """回傳 (該頁資料, 總筆數)。"""
        filt: dict = {'is_current': True}
        if item_type:
            filt['type'] = item_type

        total = cls._col().count_documents(filt)
        rows = list(cls._col().find(filt, cls.PROJECTION)
                    .sort('name', ASCENDING).skip(offset).limit(limit))
        return rows, total

    @classmethod
    def types(cls) -> list:
        return sorted(t for t in cls._col().distinct('type', {'is_current': True}) if t)

    @classmethod
    def prices(cls, item: dict, limit: int = 10) -> list:
        """物品在哪買賣。

        先查 uex_items_prices（需 UEX token），沒有就退回 Wiki API 內嵌的
        raw.uex_prices —— 所以沒設 UEX_API_TOKEN 也還是查得到一部分價格。
        """
        db = get_db()
        uex_item = db['uex_items'].find_one({'wiki_uuid': item['_id']})

        if uex_item and uex_item.get('id') is not None:
            pipeline = [
                {'$match': {'id_item': uex_item['id']}},
                {'$lookup': {'from': 'uex_terminals', 'localField': 'id_terminal',
                             'foreignField': 'id', 'as': 'terminal'}},
                {'$unwind': {'path': '$terminal', 'preserveNullAndEmptyArrays': True}},
                {'$sort': {'price_buy': ASCENDING}},
                {'$limit': limit},
            ]
            rows = list(db['uex_items_prices'].aggregate(pipeline))
            if rows:
                return [{
                    'price_buy': row.get('price_buy'),
                    'price_sell': row.get('price_sell'),
                    'terminal_name': (row.get('terminal') or {}).get('name')
                                     or row.get('terminal_name'),
                    'location': (row.get('terminal') or {}).get('star_system_name'),
                    'source': 'uex',
                } for row in rows]

        embedded = ((item.get('raw') or {}).get('uex_prices') or {}).get('purchase') or []
        return [{
            'price_buy': row.get('price_buy'),
            'price_sell': row.get('price_sell'),
            'terminal_name': row.get('terminal_name'),
            'location': (row.get('starmap_location') or {}).get('name'),
            'game_version': row.get('game_version'),
            'source': 'wiki',
        } for row in embedded[:limit]]


class VehicleMaster(_MasterBase):
    COLLECTION = 'vehicle_master'
    PROJECTION = {
        'name': 1, 'class_name': 1, 'cargo_capacity_scu': 1,
        'vehicle_inventory_uscu': 1, 'manufacturer_code': 1, 'size_class': 1,
        'career': 1, 'role': 1, 'crew_max': 1, 'is_current': 1,
    }

    @classmethod
    def list_all(cls, limit: int = 50, offset: int = 0) -> tuple:
        filt = {'is_current': True}
        total = cls._col().count_documents(filt)
        rows = list(cls._col().find(filt, cls.PROJECTION)
                    .sort('name', ASCENDING).skip(offset).limit(limit))
        return rows, total


class CommodityMaster(_MasterBase):
    COLLECTION = 'commodity_master'
    PROJECTION = {
        'name': 1, 'key': 1, 'display_name': 1, 'commodity_groups': 1,
        'box_sizes_scu': 1, 'is_mineable': 1, 'is_current': 1,
    }

    @classmethod
    def list_all(cls, limit: int = 100, offset: int = 0) -> tuple:
        filt = {'is_current': True}
        total = cls._col().count_documents(filt)
        rows = list(cls._col().find(filt, cls.PROJECTION)
                    .sort('name', ASCENDING).skip(offset).limit(limit))
        return rows, total


class SyncRun:
    """同步批次紀錄，用來讓前端顯示「資料更新到哪個版本」。"""

    COLLECTION = 'sync_runs'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def latest(cls) -> Optional[dict]:
        return cls._col().find_one(sort=[('started_at', -1)])

    @classmethod
    def recent(cls, limit: int = 10) -> list:
        return list(cls._col().find({}, {'stats': 0}).sort('started_at', -1).limit(limit))
