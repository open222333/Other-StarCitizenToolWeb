"""星圖地點的唯讀模型（scunpacked-data starmap.json → starmap_master）。

由 tasks/scdata_sync.py 的「地點」同步項目寫入，本模組只讀；另外提供兩個同步後
的整理步驟：

  - rebuild_hierarchy()：依 parent_uuid 算出每個地點的上層名稱、所屬星系、路徑
    （mapper 一次只看一筆，算不出來，要整份寫完才能補）
  - refresh_translations()：翻譯同步完重新比對中文（名稱、說明、類型、管轄、設施）

查詢一律加 is_current=True。約 2,000 筆，後端分頁、篩選。
"""

from typing import Optional

from pymongo import ASCENDING, UpdateOne

from src.models.item import escape_regex
from src.mongo import get_db
from src.models.visibility import add_filter as add_visibility_filter, hidden_filter

COLLECTION = 'starmap_master'
MAX_LIMIT = 200

#: 走到這幾種類型就當成「所屬星系」
_SYSTEM_TYPES = ('SolarSystem', 'Star')

#: 地點屬性：欄位名稱 → 對應的設施（starmap.json Amenities 的 DisplayName）。
#: 每個屬性在 starmap_master 都是一個布林欄位（同步時由 mapper 從設施清單算出來），
#: 後台可以直接用欄位篩選。顯示名稱用設施的英文去翻譯資料庫查（Maps_Amenities_*）。
FEATURES = [
    ('has_hangar', ['Hangar (S)', 'Hangar (M)', 'Hangar (L)', 'Hangar (XL)']),
    ('has_landing_pad', ['Landing Pad (S)', 'Landing Pad (M)', 'Landing Pad (L)', 'Landing Pad (XL)']),
    ('has_docking', ['Docking']),
    ('has_commodity_trading', ['Commodity Trading']),
    ('has_loading_dock', ['Loading Dock']),
    ('has_garage', ['Garage']),
    ('has_vehicle_services', ['Vehicle Services']),
    ('has_refinery', ['Refinery']),
    ('has_clinic', ['Clinic']),
    ('has_hospital', ['Hospital']),
    ('has_food_court', ['Food Court']),
    ('shop_weapons', ['Buy Weapons']),
    ('shop_armor', ['Buy Armor']),
    ('shop_clothing', ['Buy Clothing']),
    ('shop_ship_items', ['Buy Ship Items/Weapons']),
    ('shop_vehicles', ['Buy Vehicles', 'Buy/Rent Vehicles']),
    ('rent_vehicles', ['Rent Vehicles', 'Buy/Rent Vehicles']),
]
FEATURE_KEYS = [k for k, _ in FEATURES]
_FEATURE_BY_AMENITY = {}
for _key, _names in FEATURES:
    for _n in _names:
        _FEATURE_BY_AMENITY.setdefault(_n.lower(), []).append(_key)

#: 「可存放」的自動判斷：有機庫、停機坪、對接口，或商品交易（貨運電梯）、裝卸區。
#: 這是從設施推斷的，不是遊戲的官方標記——後台可以個別手動蓋過（can_store_override）。
STORAGE_FEATURES = ('has_hangar', 'has_landing_pad', 'has_docking',
                    'has_commodity_trading', 'has_loading_dock')


def features_from_amenities(amenity_names) -> dict:
    """設施名稱清單 → 各屬性欄位（全部都有值，沒有的是 False）＋機庫／停機坪尺寸＋自動可存放。"""
    out = {k: False for k in FEATURE_KEYS}
    hangar_sizes, pad_sizes = [], []
    for name in amenity_names or []:
        low = (name or '').strip().lower()
        for key in _FEATURE_BY_AMENITY.get(low, []):
            out[key] = True
        size = low[low.find('(') + 1:low.find(')')].upper() if '(' in low and ')' in low else ''
        if size and low.startswith('hangar') and size not in hangar_sizes:
            hangar_sizes.append(size)
        if size and low.startswith('landing pad') and size not in pad_sizes:
            pad_sizes.append(size)
    order = ['XS', 'S', 'M', 'L', 'XL']
    out['hangar_sizes'] = sorted(hangar_sizes, key=lambda x: order.index(x) if x in order else 99)
    out['landing_pad_sizes'] = sorted(pad_sizes, key=lambda x: order.index(x) if x in order else 99)
    out['can_store_auto'] = any(out[k] for k in STORAGE_FEATURES)
    return out


def _clean_list(value) -> list:
    values = [value] if isinstance(value, str) else list(value or [])
    return list(dict.fromkeys(v.strip() for v in values if isinstance(v, str) and v.strip()))


def _in(values: list):
    return values[0] if len(values) == 1 else {'$in': values}


def _feature_label(key: str, names: list) -> str:
    """一個屬性對應好幾種設施時（機庫 S～XL、停機坪 S～XL）的英文顯示名稱。"""
    base = names[0].split(' (')[0]
    return base if all(n.startswith(base) for n in names) else ' / '.join(names)


class Starmap:
    COLLECTION = COLLECTION
    PROJECTION = {'raw': 0}

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    # ── 查詢 ───────────────────────────────────────────────────

    @classmethod
    def _filter(cls, *, query: str = '', types=None, systems=None, jurisdictions=None,
                amenities=None, features=None, can_store=None, visibility=None, named_only: bool = True,
                missing_zh: bool = False, location_id: str = '', parent_id: str = '') -> dict:
        filt: dict = {'is_current': True}
        # 屬性：勾幾個就要全部都有（例如「有機庫」＋「武器商店」）
        for key in _clean_list(features):
            if key in FEATURE_KEYS:
                filt[key] = True
        add_visibility_filter(filt, visibility=visibility)
        if can_store is not None:
            filt['can_store'] = True if can_store else {'$ne': True}   # 還沒算過的當成不可存放
        if (location_id or '').strip():
            filt['_id'] = location_id.strip()
        if (parent_id or '').strip():
            filt['parent_uuid'] = parent_id.strip()
        if named_only:
            filt['is_named'] = True
        for field, values in (('type', types), ('system_name', systems),
                              ('jurisdiction', jurisdictions), ('amenities.name', amenities)):
            vals = _clean_list(values)
            if vals:
                filt[field] = _in(vals)
        if missing_zh:
            filt['name_zh'] = {'$in': [None, '']}
        if (query or '').strip():
            pattern = escape_regex(query)
            filt['$or'] = [
                {'name_lower': {'$regex': pattern.lower()}},
                {'name_zh': {'$regex': pattern}},
                {'parent_name': {'$regex': pattern, '$options': 'i'}},
            ]
        return filt

    @classmethod
    def list_all(cls, limit: int = 50, offset: int = 0, **filters) -> tuple:
        filt = cls._filter(**filters)
        limit = max(1, min(int(limit or 50), MAX_LIMIT))
        offset = max(0, int(offset or 0))
        total = cls._col().count_documents(filt)
        rows = list(cls._col().find(filt, cls.PROJECTION)
                    .sort([('system_name', ASCENDING), ('path_sort', ASCENDING), ('_id', ASCENDING)])
                    .skip(offset).limit(limit))
        return rows, total

    @classmethod
    def get(cls, location_id: str) -> Optional[dict]:
        """單一地點＋它底下的地點（摘要）。"""
        doc = cls._col().find_one({'_id': location_id}, cls.PROJECTION)
        if not doc:
            return None
        doc['children'] = list(cls._col().find(
            {'is_current': True, 'parent_uuid': location_id},
            {'name': 1, 'name_zh': 1, 'type': 1, 'type_zh': 1, 'is_named': 1},
        ).sort('name_lower', ASCENDING))
        return doc

    @classmethod
    def facets(cls) -> dict:
        """篩選下拉用：類型、星系、管轄、設施（含筆數，只算有名稱的）。"""
        col = cls._col()
        base = {'is_current': True, 'is_named': True}

        def count_by(field, label_field=None):
            out = {}
            for row in col.find({**base, field: {'$nin': [None, '']}},
                                {field: 1, **({label_field: 1} if label_field else {})}):
                key = row.get(field)
                item = out.setdefault(key, {'value': key, 'label_zh': row.get(label_field) if label_field else None,
                                            'count': 0})
                item['count'] += 1
            return sorted(out.values(), key=lambda x: str(x['value']).lower())

        amen = {}
        for row in col.find({**base, 'amenity_count': {'$gt': 0}}, {'amenities': 1}):
            for a in row.get('amenities') or []:
                item = amen.setdefault(a['name'], {'value': a['name'], 'label_zh': a.get('name_zh'), 'count': 0})
                item['count'] += 1
        from src.sc_zh import starmap_feature_zh
        features = []
        for key, names in FEATURES:
            features.append({'value': key, 'label': names[0] if len(names) == 1 else _feature_label(key, names),
                             'label_zh': starmap_feature_zh(key, names),
                             'storage': key in STORAGE_FEATURES,
                             'count': col.count_documents({**base, key: True})})
        return {
            'features': features,
            'can_store': {'yes': col.count_documents({**base, 'can_store': True}),
                          'no': col.count_documents({**base, 'can_store': {'$ne': True}}),
                          'override': col.count_documents({**base, 'can_store_override': {'$in': [True, False]}})},
            'types': count_by('type', 'type_zh'),
            'systems': count_by('system_name', 'system_name_zh'),
            'jurisdictions': count_by('jurisdiction', 'jurisdiction_zh'),
            'amenities': sorted(amen.values(), key=lambda x: x['value'].lower()),
        }

    @classmethod
    def count_current(cls) -> int:
        return cls._col().count_documents({'is_current': True})

    # ── 可存放（自動判斷＋人工修正）────────────────────────────────

    @classmethod
    def set_storage_override(cls, location_id: str, value, username: str = '') -> Optional[dict]:
        """人工設定「可存放」：True／False 蓋過自動判斷，None 回到自動。找不到地點回 None。

        存在同一筆文件的 can_store_override（mapper 不會輸出這個欄位，所以同步不會蓋掉）。
        """
        from datetime import datetime
        if value not in (True, False, None):
            raise ValueError('can_store 只能是 true、false 或 null')
        doc = cls._col().find_one({'_id': location_id}, {'can_store_auto': 1})
        if not doc:
            return None
        effective = doc.get('can_store_auto', False) if value is None else value
        cls._col().update_one({'_id': location_id}, {'$set': {
            'can_store_override': value, 'can_store': bool(effective),
            'can_store_updated_by': username or None, 'can_store_updated_at': datetime.utcnow()}})
        return cls._col().find_one({'_id': location_id}, cls.PROJECTION)

    @classmethod
    def storage_locations(cls) -> list:
        """可存放的地點（庫存地點下拉／bot 自動完成用）：同名只留一個，依星系、上下層排序。"""
        out, seen = [], set()
        cursor = cls._col().find(
            {'is_current': True, 'is_named': True, 'can_store': True, **hidden_filter()},
            {'name': 1, 'name_zh': 1, 'type': 1, 'type_zh': 1, 'system_name': 1, 'system_name_zh': 1,
             'parent_name': 1, 'parent_name_zh': 1},
        ).sort([('system_name', ASCENDING), ('path_sort', ASCENDING), ('_id', ASCENDING)])
        for row in cursor:
            name = (row.get('name') or '').strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append({'name': name, 'name_zh': row.get('name_zh'),
                        'type': row.get('type'), 'type_zh': row.get('type_zh'),
                        'system': row.get('system_name'), 'system_zh': row.get('system_name_zh'),
                        'parent': row.get('parent_name'), 'parent_zh': row.get('parent_name_zh')})
        return out

    @classmethod
    def apply_storage(cls) -> int:
        """依 can_store_auto 與 can_store_override 算出實際的 can_store（同步完會跑），回傳變動筆數。"""
        ops = []
        for row in cls._col().find({}, {'can_store_auto': 1, 'can_store_override': 1, 'can_store': 1}):
            override = row.get('can_store_override')
            effective = bool(row.get('can_store_auto')) if override is None else bool(override)
            if row.get('can_store') != effective:
                ops.append(UpdateOne({'_id': row['_id']}, {'$set': {'can_store': effective}}))
        for i in range(0, len(ops), 1000):
            cls._col().bulk_write(ops[i:i + 1000], ordered=False)
        return len(ops)

    # ── 同步後整理 ─────────────────────────────────────────────

    @classmethod
    def rebuild_hierarchy(cls) -> int:
        """依 parent_uuid 補上 parent_name／parent_name_zh／system_name／system_name_zh／
        path（由上而下的英文名稱清單）／path_zh（同，有中文用中文）／path_sort，回傳有變動的筆數。"""
        rows = {r['_id']: r for r in cls._col().find(
            {}, {'name': 1, 'name_zh': 1, 'type': 1, 'parent_uuid': 1, 'parent_name': 1,
                 'system_name': 1, 'path': 1, 'path_zh': 1, 'parent_name_zh': 1, 'system_name_zh': 1})}

        def chain(uid):
            out, seen = [], set()
            while uid and uid in rows and uid not in seen:   # seen：防上游資料有循環
                seen.add(uid)
                out.append(rows[uid])
                uid = rows[uid].get('parent_uuid')
            return list(reversed(out))   # 由上而下

        ops = []
        for uid, row in rows.items():
            ancestors = chain(row.get('parent_uuid'))
            parent = ancestors[-1] if ancestors else None
            system = next((a for a in ancestors if a.get('type') in _SYSTEM_TYPES), None)
            if system is None and row.get('type') in _SYSTEM_TYPES:
                system = row
            path = [a.get('name') or '' for a in ancestors]
            new = {
                'parent_name': (parent or {}).get('name') or None,
                'parent_name_zh': (parent or {}).get('name_zh'),
                'system_name': (system or {}).get('name') or None,
                'system_name_zh': (system or {}).get('name_zh'),
                'path': path,
                'path_zh': [a.get('name_zh') or a.get('name') or '' for a in ancestors],
                # 排序：同一星系內照路徑、再照名稱，讓上下層排在一起
                'path_sort': ' / '.join([*path, row.get('name') or '~']).lower(),
            }
            if any(row.get(k) != v for k, v in new.items()):
                ops.append(UpdateOne({'_id': uid}, {'$set': new}))
        for i in range(0, len(ops), 1000):
            cls._col().bulk_write(ops[i:i + 1000], ordered=False)
        return len(ops)

    @classmethod
    def refresh_translations(cls) -> int:
        """用存著的英文重新比對中文（翻譯同步完會自動跑），回傳有變動的筆數。"""
        from src.sc_zh import (amenity_zh, jurisdiction_zh, starmap_description_zh,
                               starmap_name_zh, starmap_type_zh)

        ops = []
        for row in cls._col().find({}, {'name': 1, 'description': 1, 'type': 1, 'jurisdiction': 1,
                                        'amenities': 1, 'name_zh': 1, 'description_zh': 1,
                                        'type_zh': 1, 'jurisdiction_zh': 1}):
            new = {
                'name_zh': starmap_name_zh(row.get('name') or ''),
                'description_zh': starmap_description_zh(row.get('description') or ''),
                'type_zh': starmap_type_zh(row.get('type') or ''),
                'jurisdiction_zh': jurisdiction_zh(row.get('jurisdiction') or ''),
                'amenities': [{'name': a['name'], 'name_zh': amenity_zh(a['name'])}
                              for a in row.get('amenities') or [] if a.get('name')],
            }
            if any(row.get(k) != v for k, v in new.items()):
                ops.append(UpdateOne({'_id': row['_id']}, {'$set': new}))
        for i in range(0, len(ops), 1000):
            cls._col().bulk_write(ops[i:i + 1000], ordered=False)
        if ops:
            cls.rebuild_hierarchy()   # 上層／星系的中文是從上層複製過來的，跟著更新
        return len(ops)
