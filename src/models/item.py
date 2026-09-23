"""遊戲主檔的唯讀模型（物品 / 載具 / 商品 / 製造藍圖）。

這四個 collection 由 tasks/scdata_sync.py 單向寫入，應用層只讀。
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
    def names_by_ids(cls, doc_ids) -> dict:
        """一次查多個 uuid 的顯示名稱，回傳 `{uuid: {'name':…, 'name_zh':…}}`。

        給「異動紀錄要補上物品名稱」這類清單用。原本兩支 /history 端點是
        逐筆 `find_one`（一頁最多 200 筆就是最多 200 次往返），而且
        `get()` 沒有 projection —— 每次把完整文件連 `raw`（整包 API 原始
        JSON）撈回來，只為了取兩個字串。這裡改成單一 `$in` + projection：
        往返從 N 次變 1 次，傳輸量少一到兩個數量級。

        不過濾 is_current：紀錄可能指向舊 patch 移除的物品，藏起來會讓
        使用者以為紀錄壞了（跟 get() / ids_matching() 的理由一致）。
        """
        ids = [i for i in {str(i) for i in doc_ids if i} if i]
        if not ids:
            return {}
        rows = cls._col().find({'_id': {'$in': ids}},
                               {'_id': 1, 'name': 1, 'name_zh': 1})
        return {r['_id']: {'name': r.get('name'), 'name_zh': r.get('name_zh')}
                for r in rows}

    @classmethod
    def ids_matching(cls, query: str, limit: int = 300) -> list:
        """名稱（英文或中文）含 query 的所有 uuid，給複合搜尋當 join key 用。

        跟 search() 的差別有兩個，所以沒有共用：
        - search() 是 autocomplete 用的，前綴優先、只要 25 筆就夠；這支是
          「把這串字能對到的物品全撈出來」，所以直接用中綴、上限拉高。
        - 這支**不過濾 is_current**：庫存裡可能還放著舊 patch 移除的物品，
          搜尋時把它們藏起來會讓人以為東西不見了（列表上另有 item_retired 標記）。
        """
        q = (query or '').strip()
        if not q:
            return []
        pattern = escape_regex(q)
        rows = cls._col().find(
            {'$or': [
                {'name_lower': {'$regex': pattern.lower()}},
                {'name_zh':    {'$regex': pattern}},
            ]},
            {'_id': 1},
        ).limit(max(1, min(limit, 1000)))
        return [r['_id'] for r in rows]

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
        'name': 1, 'name_zh': 1, 'class_name': 1, 'type': 1, 'sub_type': 1,
        'size': 1, 'grade': 1, 'volume_uscu': 1, 'manufacturer_code': 1,
        'is_current': 1,
    }

    @classmethod
    def search(cls, query: str = '', limit: int = 25, include_retired: bool = False) -> list:
        """名稱前綴搜尋，給 autocomplete 用。

        覆寫 _MasterBase 的版本，多比對 name_zh —— 原本只比對英文
        name_lower／class_name，打中文名（例如「鋁礦石」）搜尋物品會是空的，
        跟 BlueprintMaster.search() 已經在比對 name_zh 不一致（見那邊的說明，
        「查詢」頁的物品名稱自動完成欄位需要中英文都找得到）。
        """
        filt: dict = {} if include_retired else {'is_current': True}

        if (query or '').strip():
            escaped = escape_regex(query)
            filt['$or'] = [
                {'name_lower': {'$regex': f'^{escaped.lower()}'}},
                {'class_name': {'$regex': escaped, '$options': 'i'}},
                {'name_zh': {'$regex': escaped}},
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
    def ids_of_type(cls, item_type: str, limit: int = 1000) -> list:
        """某個類型底下所有現行物品的 uuid，給「查詢 › 物品庫存」的
        「物品類型」欄位篩選當 join key 用（先解析成一組 item_id，
        再跟位置／持有者條件一起做 AND 篩選，見 Inventory.search_filtered）。

        跟 ids_matching() 一樣不需要顯示欄位，只回 id；跟 list_by_type()
        不同的是這裡不分頁 —— 呼叫端要的是「這個類型全部的 id」拿去比對，
        不是要分頁瀏覽。
        """
        item_type = (item_type or '').strip()
        if not item_type:
            return []
        rows = cls._col().find(
            {'is_current': True, 'type': item_type}, {'_id': 1},
        ).limit(max(1, min(limit, 2000)))
        return [r['_id'] for r in rows]

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
        'vehicle_inventory_uscu': 1, 'manufacturer_code': 1, 'manufacturer_name': 1,
        'size_class': 1, 'career': 1, 'role': 1, 'crew_min': 1, 'crew_max': 1,
        'mass_hull': 1, 'msrp': 1, 'is_current': 1,
    }

    # 管理後台艦船列表可點擊排序的欄位（全站搜尋優化計畫，比照
    # BlueprintMaster.SORTABLE_FIELDS 的白名單作法，避免把任意欄位名稱
    # 直接丟給 $sort）。
    SORTABLE_FIELDS = {'name', 'crew_max', 'cargo_capacity_scu', 'mass_hull', 'msrp', 'size_class'}

    @classmethod
    def _build_query(cls, *, careers=None, roles=None, manufacturer_codes=None,
                      size_classes=None, query: str = '') -> dict:
        filt: dict = {'is_current': True}
        if careers:
            filt['career'] = {'$in': list(careers)}
        if roles:
            filt['role'] = {'$in': list(roles)}
        if manufacturer_codes:
            filt['manufacturer_code'] = {'$in': list(manufacturer_codes)}
        if size_classes:
            # size_class 存的是數字，query string 進來一律是字串，這裡轉型
            # 失敗的值直接丟掉（不讓整個查詢因為一個壞值而 500）。
            sizes = []
            for s in size_classes:
                try:
                    sizes.append(int(s))
                except (TypeError, ValueError):
                    continue
            if sizes:
                filt['size_class'] = {'$in': sizes}
        keyword = (query or '').strip()
        if keyword:
            pattern = escape_regex(keyword)
            filt['name_lower'] = {'$regex': pattern.lower()}
        return filt

    @classmethod
    def list_all(cls, limit: int = 50, offset: int = 0, careers=None, roles=None,
                 manufacturer_codes=None, size_classes=None, query: str = '',
                 sort_by: str = 'name', sort_dir: int = 1) -> tuple:
        filt = cls._build_query(careers=careers, roles=roles,
                                 manufacturer_codes=manufacturer_codes,
                                 size_classes=size_classes, query=query)
        sort_field = sort_by if sort_by in cls.SORTABLE_FIELDS else 'name'
        total = cls._col().count_documents(filt)
        rows = list(cls._col().find(filt, cls.PROJECTION)
                    .sort(sort_field, sort_dir).skip(offset).limit(limit))
        return rows, total

    @classmethod
    def count(cls, careers=None, roles=None, manufacturer_codes=None,
              size_classes=None, query: str = '') -> int:
        filt = cls._build_query(careers=careers, roles=roles,
                                 manufacturer_codes=manufacturer_codes,
                                 size_classes=size_classes, query=query)
        return cls._col().count_documents(filt)

    @classmethod
    def careers(cls) -> list:
        return sorted(v for v in cls._col().distinct('career', {'is_current': True}) if v)

    @classmethod
    def roles(cls) -> list:
        return sorted(v for v in cls._col().distinct('role', {'is_current': True}) if v)

    @classmethod
    def size_classes(cls) -> list:
        return sorted(v for v in cls._col().distinct('size_class', {'is_current': True})
                      if v is not None)

    @classmethod
    def manufacturers(cls) -> list:
        """{value: 廠商代碼, label: 廠商全名} —— 篩選用代碼，畫面顯示全名。"""
        pipeline = [
            {'$match': {'is_current': True, 'manufacturer_code': {'$ne': None}}},
            {'$group': {'_id': '$manufacturer_code',
                        'name': {'$first': '$manufacturer_name'}}},
            {'$sort': {'_id': 1}},
        ]
        return [{'value': row['_id'], 'label': row.get('name') or row['_id']}
                for row in cls._col().aggregate(pipeline)]


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


class BlueprintMaster(_MasterBase):
    """製造藍圖主檔（Star Citizen 4.10 的 crafting 配方，1,600+ 筆）。

    ⚠️ 跟 src/models/blueprint.py 的 `blueprints` 是**兩個不同的東西**：
      - blueprint_master（這裡）＝ 遊戲裡存在哪些配方，API 同步、唯讀
      - blueprints                ＝ 某位玩家擁有哪張藍圖，玩家自己登記

    兩者靠 blueprints.blueprint_uuid 連起來（可為空，仍允許自由輸入名稱）。
    """

    COLLECTION = 'blueprint_master'
    PROJECTION = {
        'name': 1, 'name_zh': 1, 'key': 1, 'output_item_uuid': 1,
        'output_type': 1, 'output_type_label': 1, 'output_grade': 1,
        'craft_time_seconds': 1, 'craft_time_label': 1,
        'ingredient_count': 1, 'is_available_by_default': 1,
        'is_current': 1,
    }

    # 含配方明細的完整投影（單筆查詢用）。一律排除 raw ——
    # 那是整包 API 原始 JSON，前端不需要，而且會讓回應大好幾倍。
    DETAIL_PROJECTION = {'raw': 0}

    @classmethod
    def get(cls, doc_id: str) -> Optional[dict]:
        """按 uuid 取單筆（含 ingredients / dismantle_returns，但不含 raw）。"""
        return cls._col().find_one({'_id': doc_id}, cls.DETAIL_PROJECTION)

    @classmethod
    def search(cls, query: str = '', limit: int = 25, include_retired: bool = False) -> list:
        """名稱前綴搜尋。

        覆寫 _MasterBase 的版本 —— 它比對 class_name，但藍圖主檔沒有那個欄位
        （對應的是 key，例如 BP_CRAFT_AMRS_LaserCannon_S1）。不覆寫的話那個
        $or 分支永遠不會命中，等於白做一次索引查詢。
        中文名也一併比對，這樣打「雷射」也找得到。
        """
        filt: dict = {} if include_retired else {'is_current': True}

        if (query or '').strip():
            escaped = escape_regex(query)
            filt['$or'] = [
                {'name_lower': {'$regex': f'^{escaped.lower()}'}},
                {'key': {'$regex': escaped, '$options': 'i'}},
                {'name_zh': {'$regex': escaped}},
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
    def list_all(cls, limit: int = 50, offset: int = 0,
                 output_type: str = '', available_only: bool = False,
                 query: str = '') -> tuple:
        """分頁列出藍圖主檔。

        `query` 是名稱關鍵字（中英文都比對）。有這個參數，前端「瀏覽整份清單
        並勾選」才能一邊篩名稱一邊翻頁 —— search() 只回前 25 筆、沒有分頁，
        當清單有 1,600 筆時不夠用。
        """
        filt: dict = {'is_current': True}
        if (output_type or '').strip():
            filt['output_type'] = output_type.strip()
        if available_only:
            filt['is_available_by_default'] = True
        if (query or '').strip():
            pattern = escape_regex(query)
            filt['$or'] = [
                {'name_lower': {'$regex': pattern.lower()}},
                {'name_zh': {'$regex': pattern}},
            ]

        total = cls._col().count_documents(filt)
        rows = list(cls._col().find(filt, cls.PROJECTION)
                    .sort('name', ASCENDING).skip(offset).limit(limit))
        return rows, total

    @classmethod
    def for_output_item(cls, item_uuid: str) -> list:
        """做出這個物品的所有配方（給物品詳細頁「怎麼做出來」用）。"""
        if not (item_uuid or '').strip():
            return []
        return list(cls._col().find(
            {'output_item_uuid': item_uuid.strip(), 'is_current': True},
            cls.DETAIL_PROJECTION).sort('name', ASCENDING))

    @classmethod
    def output_types(cls) -> list:
        """所有產出物類型（給前端做篩選下拉）。"""
        values = cls._col().distinct('output_type', {'is_current': True})
        return sorted(v for v in values if v)

    @classmethod
    def uuids_of_type(cls, output_type: str, limit: int = 2000) -> list:
        """某個產出類型底下所有現行藍圖的 uuid，給「查詢 › 持有藍圖」的
        「藍圖類型」欄位篩選當 join key 用（見 Blueprint.find_holders 的
        blueprint_uuids 參數）。

        玩家自由輸入、沒有對到主檔的登記天生沒有 blueprint_uuid，篩類型時
        本來就篩不到那些——是預期行為，不是這支的責任。
        """
        output_type = (output_type or '').strip()
        if not output_type:
            return []
        rows = cls._col().find(
            {'is_current': True, 'output_type': output_type}, {'_id': 1},
        ).limit(max(1, min(limit, 5000)))
        return [r['_id'] for r in rows]

    @classmethod
    def count_current(cls) -> int:
        return cls._col().count_documents({'is_current': True})


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
