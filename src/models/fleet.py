"""艦隊（玩家擁有的船／載具）名冊模型。

跟藍圖名冊（src/models/blueprint.py）同一套設計：每筆是「某位玩家有某款
載具」，`vehicle_uuid` 指向 `vehicle_master`（API 同步的遊戲主檔），
`player_id` 指向 `players._id`。

跟藍圖不同的是多了 `quantity` —— 同一款船可能買了好幾艘（例如兩台
Cyclone 當地面接駁），所以一款一筆、另外記數量，而不是一艘一筆（那樣
「誰有這艘船」的統計會把同一個人算好幾次）。
"""

import re
from datetime import datetime

from bson import ObjectId
from pymongo.errors import BulkWriteError

from src.models.blueprint import _redact_contact
from src.models.item import VehicleMaster
from src.mongo import get_db

#: 單款船最多登記幾艘。遊戲裡沒有真的上限，但數字欄位沒有上限的話，
#: 打錯一個 0 就會讓「艦隊總數」之類的統計失真，99 對公會用途已經很寬鬆。
MAX_QUANTITY = 99

#: 「查詢 › 持有船艦」每一款船最多列出幾位持有者（總數另外用 holder_count 帶出去），
#: 理由同 src/models/blueprint.py 的 HOLDERS_PER_GROUP。
HOLDERS_PER_GROUP = 50

#: 玩家名冊一個人最多能有幾筆艦隊登記（查「我的艦隊」時的上限），
#: 比 vehicle_master 全部筆數（約 300）高就不會截斷。
PLAYER_MAX = 1000

#: 配件連結（例如 erkul.games 的分享連結）：玩家在自己的艦隊登記上填，公開給其他玩家看
LOADOUT_MAX_LINKS = 10
LOADOUT_LABEL_MAX = 50
LOADOUT_URL_MAX = 500
#: 每艘船自己看的區別名稱（同一款船有好幾艘時用），只回給登記者本人
UNIT_NAME_MAX = 50
_URL_RE = re.compile(r'^https?://[^\s/]+\.[^\s]+$', re.IGNORECASE)
#: 只填分享代碼（https://erkul.games/s/abcd1234 後面那段）時補成完整網址
ERKUL_SHARE_BASE = 'https://erkul.games/s/'
_SHARE_CODE_RE = re.compile(r'^[A-Za-z0-9_-]{4,64}$')
_BARE_HOST_RE = re.compile(r'^[a-z0-9-]+(\.[a-z0-9-]+)+/\S*$', re.IGNORECASE)


def normalize_loadout_url(value: str) -> str:
    """配件網址：完整網址照用；只填 erkul 分享代碼（例如 abcd1234）補成
    https://erkul.games/s/<代碼>；少了 https:// 的（erkul.games/s/xxx）補上。"""
    text = (value or '').strip()
    if _SHARE_CODE_RE.match(text):
        return ERKUL_SHARE_BASE + text
    if _BARE_HOST_RE.match(text):
        return 'https://' + text
    return text


def clean_loadout_links(links, previous=None) -> list:
    """驗證並整理配件連結 [{label, url}]，回傳 [{label, url, added_at}]（空清單＝清掉）。

    網址沒變的保留原本的 added_at——外部配裝計算器的分享連結是當時遊戲版本的配置，
    看加入時間才知道多舊。格式不對丟 ValueError（訊息直接給玩家看）。
    """
    if not isinstance(links, list):
        raise ValueError('配件連結格式錯誤')
    if len(links) > LOADOUT_MAX_LINKS:
        raise ValueError(f'配件網址最多 {LOADOUT_MAX_LINKS} 條')
    added = {l.get('url'): l.get('added_at') for l in previous or [] if isinstance(l, dict)}
    now = datetime.utcnow()
    out, seen = [], set()
    for i, link in enumerate(links, 1):
        if not isinstance(link, dict):
            raise ValueError(f'第 {i} 條配件連結格式錯誤')
        url = normalize_loadout_url(link.get('url')) if isinstance(link.get('url'), str) else ''
        label = link.get('label').strip() if isinstance(link.get('label'), str) else ''
        if not url:
            raise ValueError(f'第 {i} 條配件網址是空的')
        if not _URL_RE.match(url):
            raise ValueError(f'第 {i} 條配件網址格式不對（填 erkul 分享代碼或完整網址）')
        if len(url) > LOADOUT_URL_MAX:
            raise ValueError(f'第 {i} 條配件網址太長')
        if len(label) > LOADOUT_LABEL_MAX:
            raise ValueError(f'第 {i} 條配件網址標籤最多 {LOADOUT_LABEL_MAX} 字')
        if url in seen:
            continue
        seen.add(url)
        out.append({'label': label or None, 'url': url, 'added_at': added.get(url) or now})
    return out


def clean_unit_names(names, quantity: int) -> list:
    """整理每艘船的區別名稱：第 i 個對應第 i 艘，空字串＝沒取名；
    超過數量的截掉、結尾的空白名稱去掉。格式不對丟 ValueError。"""
    if not isinstance(names, list):
        raise ValueError('區別名稱格式錯誤')
    out = []
    for i, name in enumerate(names[:max(0, int(quantity))], 1):
        if name is None:
            name = ''
        if not isinstance(name, str):
            raise ValueError(f'第 {i} 艘的區別名稱格式錯誤')
        name = name.strip()
        if len(name) > UNIT_NAME_MAX:
            raise ValueError(f'第 {i} 艘的區別名稱最多 {UNIT_NAME_MAX} 字')
        out.append(name)
    while out and not out[-1]:
        out.pop()
    return out


def clamp_quantity(value, default: int = 1) -> int:
    """把 client 傳來的數量轉成 1..MAX_QUANTITY 的整數；轉不了就用 default。"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, MAX_QUANTITY))


def _vehicle_summary(master: dict | None) -> dict | None:
    if not master:
        return None
    return {
        'name': master.get('name'),
        'name_zh': master.get('name_zh'),
        'size_class': master.get('size_class'),
        'vehicle_type': master.get('vehicle_type'),
        'manufacturer_code': master.get('manufacturer_code'),
        'manufacturer_name': master.get('manufacturer_name'),
        'role': master.get('role'),
        'role_zh': master.get('role_zh'),
        'career': master.get('career'),
        'is_current': master.get('is_current'),
        'note': master.get('note'),   # 後台手寫的說明
        'system_note': master.get('system_note'),   # 同名變體的區別（自動產生）
    }


class Fleet:
    COLLECTION = 'fleet'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @staticmethod
    def _serialize(doc: dict) -> dict:
        doc = dict(doc)
        doc['_id'] = str(doc['_id'])
        if doc.get('player_id'):
            doc['player_id'] = str(doc['player_id'])
        return doc

    # ── 自己的艦隊 ─────────────────────────────────────────────────

    @classmethod
    def find_for_player(cls, player_id: str) -> list:
        """某位玩家的艦隊（不含已刪除），每筆補上 `vehicle`（主檔摘要）。"""
        try:
            query = {'player_id': ObjectId(player_id), 'deleted_at': None}
        except Exception:
            return []
        rows = [cls._serialize(r) for r in
                cls._col().find(query).sort('name', 1).limit(PLAYER_MAX)]
        masters = VehicleMaster.by_ids(r.get('vehicle_uuid') for r in rows)
        for row in rows:
            row['vehicle'] = _vehicle_summary(masters.get(row.get('vehicle_uuid')))
        return rows

    @classmethod
    def registered_uuids_for_player(cls, player_id: str, uuids=None) -> set:
        """這位玩家已經登記過哪些載具 uuid（批量登記頁標「已登記」、送出時再擋一次）。"""
        try:
            query = {'player_id': ObjectId(player_id), 'deleted_at': None}
        except Exception:
            return set()
        if uuids is not None:
            wanted = [u for u in {str(u) for u in uuids if u} if u]
            if not wanted:
                return set()
            query['vehicle_uuid'] = {'$in': wanted}
        return {row['vehicle_uuid'] for row in
                cls._col().find(query, {'vehicle_uuid': 1, '_id': 0})
                if row.get('vehicle_uuid')}

    @classmethod
    def bulk_create_for_player(cls, player_id: str, items, quantity: int = 1) -> dict:
        """一次登記多款載具，回傳 `{'added': [...], 'skipped': [...]}`。

        `items` 是 `[{'uuid':…, 'name':…}, …]`，名稱由呼叫端從主檔取。
        已經登記過的款式**跳過**（要加艘數請到「我的艦隊」改數量），理由跟
        藍圖批量登記一樣：手滑按兩下不該多出一整批重複資料。並發重複由
        src/mongo.py 的 (player_id, vehicle_uuid) partial 唯一索引擋下，撞到的
        歸類成 skipped。
        """
        pairs = [(str(item.get('uuid') or '').strip(), item.get('name') or '')
                 for item in (items or [])]
        pairs = [(uuid, name) for uuid, name in pairs if uuid and name]
        if not pairs:
            return {'added': [], 'skipped': []}

        already = cls.registered_uuids_for_player(player_id, [u for u, _ in pairs])
        seen = set()
        fresh = []
        for uuid, name in pairs:
            if uuid in already or uuid in seen:
                continue
            seen.add(uuid)
            fresh.append((uuid, name))
        if not fresh:
            return {'added': [], 'skipped': sorted({u for u, _ in pairs})}

        qty = clamp_quantity(quantity)
        now = datetime.utcnow()
        docs = [{
            'player_id':    ObjectId(player_id),
            'vehicle_uuid': uuid,
            'name':         name,
            'quantity':     qty,
            'notes':        '',
            'created_at':   now,
            'updated_at':   now,
            'deleted_at':   None,
        } for uuid, name in fresh]

        added = [uuid for uuid, _ in fresh]
        try:
            cls._col().insert_many(docs, ordered=False)
        except BulkWriteError as err:
            write_errors = err.details.get('writeErrors', [])
            if any(e.get('code') != 11000 for e in write_errors):
                raise
            # 用 index 回推是哪一筆撞到，理由見 Blueprint.bulk_create_for_player
            duplicated = set()
            for e in write_errors:
                pos = e.get('index')
                if isinstance(pos, int) and 0 <= pos < len(docs):
                    duplicated.add(docs[pos]['vehicle_uuid'])
                else:
                    uuid = (e.get('keyValue') or {}).get('vehicle_uuid')
                    if uuid:
                        duplicated.add(uuid)
            added = [uuid for uuid in added if uuid not in duplicated]
            already = set(already) | duplicated

        return {'added': added, 'skipped': sorted(already)}

    @classmethod
    def update_for_player(cls, fleet_id: str, player_id: str, *,
                          quantity=None, notes=None, loadout_links=None,
                          unit_names=None) -> bool:
        """改自己名下某筆登記的數量／備註／配件連結／每艘的區別名稱（只能改自己的）。

        loadout_links、unit_names 格式不對丟 ValueError（見 clean_loadout_links、
        clean_unit_names）。數量改少時，多出來那幾艘的區別名稱一起截掉。
        """
        try:
            query = {'_id': ObjectId(fleet_id), 'player_id': ObjectId(player_id),
                     'deleted_at': None}
        except Exception:
            return False
        set_fields: dict = {}
        current = None
        if loadout_links is not None or unit_names is not None or quantity is not None:
            current = cls._col().find_one(
                query, {'loadout_links': 1, 'unit_names': 1, 'quantity': 1})
            if not current:
                return False
        if quantity is not None:
            set_fields['quantity'] = clamp_quantity(quantity)
        if notes is not None:
            set_fields['notes'] = str(notes)[:500]
        if loadout_links is not None:
            set_fields['loadout_links'] = clean_loadout_links(loadout_links, current.get('loadout_links'))
        if current is not None:
            qty = set_fields.get('quantity') or clamp_quantity(current.get('quantity'))
            if unit_names is not None:
                set_fields['unit_names'] = clean_unit_names(unit_names, qty)
            elif current.get('unit_names') and len(current['unit_names']) > qty:
                set_fields['unit_names'] = clean_unit_names(current['unit_names'], qty)
        if not set_fields:
            return False
        set_fields['updated_at'] = datetime.utcnow()
        return cls._col().update_one(query, {'$set': set_fields}).matched_count > 0

    @classmethod
    def soft_delete(cls, fleet_id: str, player_id: str) -> bool:
        """軟刪除自己名下的一筆登記（開發原則：重要資料不永久刪除）。"""
        try:
            query = {'_id': ObjectId(fleet_id), 'player_id': ObjectId(player_id),
                     'deleted_at': None}
        except Exception:
            return False
        result = cls._col().update_one(
            query, {'$set': {'deleted_at': datetime.utcnow()}})
        return result.matched_count > 0

    # ── 後台：玩家擁有艦船（唯讀列表）─────────────────────────────────

    ADMIN_SORTS = {'name': [('name_lower', 1), ('player_key', 1)],
                   'player': [('player_key', 1), ('name_lower', 1)],
                   'quantity': [('quantity', -1), ('name_lower', 1)],
                   'updated': [('updated_at', -1)]}

    @classmethod
    def admin_list(cls, *, query: str = '', player: str = '', vehicle_uuids=None,
                   sort: str = 'name', limit: int = 50, offset: int = 0) -> tuple:
        """後台「艦船 › 玩家擁有艦船」：每一筆登記一列（玩家、船、數量），分頁。

        query：船名（英文，部分比對）；vehicle_uuids 不是 None 時改用這些 uuid（中文船名
        由呼叫端先查成 uuid）。player：遊戲ID／暱稱／玩家名稱（部分比對）。
        已軟刪除的登記、已軟刪除的玩家都不列；不回傳玩家自己寫的備註 notes。
        回傳 (rows, total)。
        """
        match: dict = {'deleted_at': None}
        if vehicle_uuids is not None:
            match['vehicle_uuid'] = {'$in': list(vehicle_uuids)}
        elif (query or '').strip():
            match['name'] = {'$regex': re.escape(query.strip()), '$options': 'i'}

        pipeline: list = [
            {'$match': match},
            {'$lookup': {'from': 'players', 'localField': 'player_id',
                         'foreignField': '_id', 'as': 'player'}},
            {'$unwind': {'path': '$player', 'preserveNullAndEmptyArrays': True}},
            {'$match': {'$or': [{'player': {'$exists': False}}, {'player.deleted_at': None}]}},
        ]
        if (player or '').strip():
            pattern = {'$regex': re.escape(player.strip()), '$options': 'i'}
            pipeline.append({'$match': {'$or': [{'player.star_citizen_id': pattern},
                                                {'player.nickname': pattern},
                                                {'player.player_name': pattern}]}})
        pipeline += [
            {'$addFields': {'name_lower': {'$toLower': '$name'},
                            'player_key': {'$toLower': {'$ifNull': ['$player.star_citizen_id', '']}}}},
            {'$sort': dict(cls.ADMIN_SORTS.get(sort) or cls.ADMIN_SORTS['name'])},
            {'$facet': {
                'rows': [{'$skip': max(0, int(offset))}, {'$limit': max(1, min(int(limit), 200))},
                         {'$project': {'notes': 0, 'unit_names': 0, 'name_lower': 0, 'player_key': 0,
                                       'player.password': 0, 'player.password_hash': 0}}],
                'total': [{'$count': 'n'}],
            }},
        ]
        result = next(iter(cls._col().aggregate(pipeline, allowDiskUse=True)), {}) or {}
        rows = result.get('rows') or []
        total = (result.get('total') or [{}])[0].get('n', 0)
        masters = VehicleMaster.by_ids(r.get('vehicle_uuid') for r in rows)
        out = []
        for r in rows:
            p = r.get('player') or {}
            out.append({
                '_id': str(r['_id']),
                'vehicle_uuid': r.get('vehicle_uuid'),
                'name': r.get('name'),
                'quantity': r.get('quantity'),
                'loadout_links': r.get('loadout_links') or [],
                'created_at': r.get('created_at'),
                'updated_at': r.get('updated_at'),
                'player': {'_id': str(p['_id']) if p.get('_id') else None,
                           'star_citizen_id': p.get('star_citizen_id'),
                           'nickname': p.get('nickname'),
                           'player_name': p.get('player_name')} if p else None,
                'vehicle': _vehicle_summary(masters.get(r.get('vehicle_uuid'))),
            })
        return out, total

    # ── 公會互查：誰有這款船 ────────────────────────────────────────

    @classmethod
    def find_holders(cls, vehicle_uuids=None, player_scid: str = '', limit: int = 100) -> list:
        """「查詢 › 持有船艦」：同一款船的持有者聚成一組。

        vehicle_uuids：呼叫端用尺寸／類型／廠商／角色／名稱先解析出來的載具
        uuid（見 VehicleMaster.ids_matching_filter）。None 代表不篩載具；
        空陣列代表篩了但沒有載具符合，直接回空。

        player_scid：只看這個人的（比對 players.star_citizen_id）。

        回傳欄位不含 notes（那是玩家寫給自己的備註），Discord 只有本人勾了
        公開才給，見 src/models/blueprint.py 的 _redact_contact。
        """
        match: dict = {'deleted_at': None}
        if vehicle_uuids is not None:
            if not vehicle_uuids:
                return []
            match['vehicle_uuid'] = {'$in': list(vehicle_uuids)}

        pipeline: list = [
            {'$match': match},
            {'$lookup': {'from': 'players', 'localField': 'player_id',
                         'foreignField': '_id', 'as': 'player'}},
            {'$unwind': {'path': '$player', 'preserveNullAndEmptyArrays': True}},
            # 已軟刪除的玩家不該出現在別人的查詢結果裡
            {'$match': {'$or': [{'player': {'$exists': False}},
                                {'player.deleted_at': None}]}},
        ]
        if (player_scid or '').strip():
            pipeline.append({'$match': {'player.star_citizen_id': player_scid.strip()}})

        pipeline += [
            {'$group': {
                '_id': '$vehicle_uuid',
                'name': {'$first': '$name'},
                'holders': {'$push': {
                    'nickname': '$player.nickname',
                    'player_name': '$player.player_name',
                    'star_citizen_id': '$player.star_citizen_id',
                    'quantity': '$quantity',
                    'discord_name': '$player.discord_name',
                    'discord_id': '$player.discord_id',
                    'discord_public': '$player.discord_public',
                    # 玩家自己填的配件連結（公開）；沒填過的舊登記給空陣列
                    'loadout_links': {'$ifNull': ['$loadout_links', []]},
                }},
                'holder_count': {'$sum': 1},
                'total_quantity': {'$sum': '$quantity'},
            }},
            {'$sort': {'holder_count': -1, 'name': 1}},
            {'$limit': max(1, min(limit, 300))},
            {'$addFields': {'holders': {'$slice': ['$holders', HOLDERS_PER_GROUP]}}},
        ]
        groups = list(cls._col().aggregate(pipeline, allowDiskUse=True))
        masters = VehicleMaster.by_ids(g['_id'] for g in groups)
        for group in groups:
            group['vehicle_uuid'] = group['_id']
            group['holders'] = [_redact_contact(h) for h in group.get('holders') or []]
            group['vehicle'] = _vehicle_summary(masters.get(group['_id']))
        return groups
