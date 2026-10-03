"""任務／勢力主檔的唯讀模型（Star Citizen Wiki API 的 missions／factions）。

由 tasks/scdata_sync.py 同步進 mission_master／faction_master，本模組只讀不寫；
要加欄位就改 src/scdata.py 的 map_mission／map_faction 再重跑同步。

跟藍圖的關聯：任務的獎勵藍圖池（blueprint_pools）在同步時就攤平成
`blueprint_uuids`（有索引），「這張藍圖由哪些任務解鎖」是在本地反查，
不用再打上游 API。

查詢一律加 is_current=True（上游移除的任務／勢力留著紀錄，但不顯示）。
"""

from typing import Optional

from pymongo import ASCENDING

from src.models.item import BlueprintMaster, escape_regex
from src.mongo import get_db
from src.models.visibility import add_filter as add_visibility_filter

MISSION_COLLECTION = 'mission_master'
FACTION_COLLECTION = 'faction_master'

MAX_LIMIT = 200


def _clean_list(value) -> list:
    values = [value] if isinstance(value, str) else list(value or [])
    return list(dict.fromkeys(v.strip() for v in values if isinstance(v, str) and v.strip()))


def _in(values: list):
    return values[0] if len(values) == 1 else {'$in': values}


class Mission:
    COLLECTION = MISSION_COLLECTION

    #: 列表／明細都不帶 raw（整包上游 JSON）
    PROJECTION = {'raw': 0}

    #: 玩家頁「這張藍圖的解鎖任務」只需要這些
    BRIEF_PROJECTION = {
        'title': 1, 'title_zh': 1, 'description': 1, 'description_zh': 1,
        'mission_giver': 1, 'mission_giver_zh': 1,
        'faction_uuid': 1, 'faction_name': 1, 'faction_name_zh': 1,
        'reward_scope': 1, 'illegal': 1, 'shareable': 1, 'once_only': 1,
        'reward_min': 1, 'reward_max': 1, 'reward_currency': 1,
        'reputation_gained': 1, 'cooldown_label': 1, 'star_systems': 1,
        'blueprint_pools': 1,
    }

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def _filter(cls, *, query: str = '', reward_scopes=None, star_systems=None,
                faction_uuids=None, legality=None, has_blueprints: bool = False,
                missing_zh: bool = False, mission_id: str = '', blueprint_uuid: str = '',
                visible_only: bool = False, visibility=None) -> dict:
        filt: dict = {'is_current': True}
        add_visibility_filter(filt, visible_only=visible_only, visibility=visibility)
        if (mission_id or '').strip():
            filt['_id'] = mission_id.strip()
        scopes = _clean_list(reward_scopes)
        if scopes:
            filt['reward_scope'] = _in(scopes)
        systems = _clean_list(star_systems)
        if systems:
            filt['star_systems'] = _in(systems)
        factions = _clean_list(faction_uuids)
        if factions:
            filt['faction_uuid'] = _in(factions)
        legal = _clean_list(legality)
        wants = {v for v in legal if v in ('legal', 'illegal')}
        if len(wants) == 1:
            filt['illegal'] = wants == {'illegal'}
        if has_blueprints:
            filt['has_blueprints'] = True
        if missing_zh:
            filt['title_zh'] = {'$in': [None, '']}
        if (blueprint_uuid or '').strip():
            filt['blueprint_uuids'] = blueprint_uuid.strip()
        if (query or '').strip():
            pattern = escape_regex(query)
            filt['$or'] = [
                {'title_lower': {'$regex': pattern.lower()}},
                {'title_zh': {'$regex': pattern}},
                {'debug_name': {'$regex': pattern, '$options': 'i'}},
                {'mission_giver': {'$regex': pattern, '$options': 'i'}},
            ]
        return filt

    @staticmethod
    def _attach_blueprint_names(rows: list) -> list:
        """獎勵藍圖池的每張藍圖補上主檔的中文名稱（`name_zh`），一次 $in 查完。"""
        uuids = {it.get('blueprint_uuid') for r in rows for p in (r.get('blueprint_pools') or [])
                 for it in (p.get('items') or []) if it.get('blueprint_uuid')}
        if not uuids:
            return rows
        names = BlueprintMaster.names_by_ids(uuids)
        for r in rows:
            for p in r.get('blueprint_pools') or []:
                for it in p.get('items') or []:
                    master = names.get(it.get('blueprint_uuid')) or {}
                    it['name_zh'] = master.get('name_zh')
        return rows

    @classmethod
    def list_all(cls, limit: int = 50, offset: int = 0, **filters) -> tuple:
        filt = cls._filter(**filters)
        limit = max(1, min(int(limit or 50), MAX_LIMIT))
        offset = max(0, int(offset or 0))
        total = cls._col().count_documents(filt)
        rows = list(cls._col().find(filt, cls.PROJECTION)
                    .sort([('title_lower', ASCENDING), ('_id', ASCENDING)])
                    .skip(offset).limit(limit))
        return cls._attach_blueprint_names(rows), total

    @classmethod
    def get(cls, mission_id: str) -> Optional[dict]:
        doc = cls._col().find_one({'_id': mission_id}, cls.PROJECTION)
        return cls._attach_blueprint_names([doc])[0] if doc else None

    @classmethod
    def facets(cls) -> dict:
        """篩選下拉用：類型、星系、勢力（含任務數）。"""
        col = cls._col()
        cur = {'is_current': True}
        scopes = sorted(v for v in col.distinct('reward_scope', cur) if v)
        systems = sorted(v for v in col.distinct('star_systems', cur) if v)
        factions = {}
        for row in col.find({**cur, 'faction_uuid': {'$nin': [None, '']}},
                            {'faction_uuid': 1, 'faction_name': 1, 'faction_name_zh': 1}):
            f = factions.setdefault(row['faction_uuid'], {
                'uuid': row['faction_uuid'], 'name': row.get('faction_name') or '',
                'name_zh': row.get('faction_name_zh'), 'count': 0})
            f['count'] += 1
        return {
            'reward_scopes': scopes,
            'star_systems': systems,
            'factions': sorted(factions.values(), key=lambda f: f['name'].lower()),
        }

    @classmethod
    def for_blueprint(cls, blueprint_uuid: str, visible_only: bool = False) -> list:
        """會給這張藍圖的任務，每筆附上 `chance`（含這張藍圖的獎勵池掉落機率，
        有好幾個池就取最高）與 `pool_size`（那個池共有幾張藍圖，抽中其中一張）。"""
        uuid = (blueprint_uuid or '').strip()
        if not uuid:
            return []
        filt = add_visibility_filter({'is_current': True, 'blueprint_uuids': uuid},
                                     visible_only=visible_only)
        rows = list(cls._col().find(filt, cls.BRIEF_PROJECTION))
        out = []
        for row in rows:
            best = None
            for pool in row.pop('blueprint_pools', None) or []:
                items = pool.get('items') or []
                if any(it.get('blueprint_uuid') == uuid for it in items):
                    chance = pool.get('drop_chance')
                    if best is None or (chance or 0) > (best[0] or 0):
                        best = (chance, len(items))
            row['chance'], row['pool_size'] = best if best else (None, None)
            out.append(row)
        out.sort(key=lambda r: (-(r['chance'] or 0), (r.get('title') or '').lower()))
        return out

    @classmethod
    def counts_for_blueprints(cls, blueprint_uuids, visible_only: bool = False) -> dict:
        """`{blueprint_uuid: 會給它的任務數}`，只回有任務的。"""
        ids = _clean_list(list(blueprint_uuids or []))
        if not ids:
            return {}
        pipeline = [
            {'$match': add_visibility_filter({'is_current': True, 'blueprint_uuids': {'$in': ids}},
                                             visible_only=visible_only)},
            {'$project': {'blueprint_uuids': 1}},
            {'$unwind': '$blueprint_uuids'},
            {'$match': {'blueprint_uuids': {'$in': ids}}},
            {'$group': {'_id': '$blueprint_uuids', 'n': {'$sum': 1}}},
        ]
        return {r['_id']: r['n'] for r in cls._col().aggregate(pipeline)}

    @classmethod
    def blueprint_uuids_with_missions(cls, visible_only: bool = False) -> list:
        """有任務會給的所有藍圖 uuid（藍圖資料庫「只看需任務解鎖」用）。"""
        filt = add_visibility_filter({'is_current': True}, visible_only=visible_only)
        return [v for v in cls._col().distinct('blueprint_uuids', filt) if v]

    @classmethod
    def relink_blueprints(cls) -> int:
        """用存著的上游原始資料（raw.blueprints）重新算每個任務的獎勵藍圖對應，
        回傳有變動的任務數。

        任務同步時若藍圖主檔還沒有那張藍圖（例如藍圖還沒同步、或剛好在同步中），
        靠產出物品反查的那幾筆會對不到；藍圖同步完再跑一次就補上，不用重抓任務。
        """
        from pymongo import UpdateOne
        from src.scdata import parse_blueprint_pools

        ops = []
        for row in cls._col().find({'raw.blueprints.0': {'$exists': True}},
                                   {'raw.blueprints': 1, 'blueprint_uuids': 1}):
            pools, uuids = parse_blueprint_pools((row.get('raw') or {}).get('blueprints'))
            if uuids != (row.get('blueprint_uuids') or []):
                ops.append(UpdateOne({'_id': row['_id']}, {'$set': {
                    'blueprint_pools': pools, 'blueprint_uuids': uuids}}))
        if ops:
            cls._col().bulk_write(ops, ordered=False)
        return len(ops)

    @classmethod
    def refresh_translations(cls) -> int:
        """用存著的上游原始資料重新比對中文（標題、說明、發布者、勢力名稱），回傳有變動的筆數。

        中文是同步當下從 sc_translations 查的快照；翻譯同步晚於任務同步（或兩者同時跑）
        時，任務會先存成沒有中文。翻譯同步完會自動跑這支補上，不用重抓任務。
        """
        from pymongo import UpdateOne
        from src.sc_zh import faction_name_zh, mission_giver_zh, mission_text_zh

        fields = ('title_zh', 'title_key', 'description_zh', 'mission_giver_zh', 'faction_name_zh')
        ops = []
        for row in cls._col().find({}, {'raw.title': 1, 'raw.description': 1, 'mission_giver': 1,
                                        'faction_name': 1, **{f: 1 for f in fields}}):
            raw = row.get('raw') or {}
            texts = mission_text_zh((raw.get('title') or '').strip(), raw.get('description') or '')
            new = {
                'title_zh': texts['title_zh'],
                'title_key': texts['title_key'],
                'description_zh': texts['description_zh'],
                'mission_giver_zh': mission_giver_zh(row['mission_giver']) if row.get('mission_giver') else None,
                'faction_name_zh': faction_name_zh(row['faction_name']) if row.get('faction_name') else None,
            }
            if any(row.get(f) != new[f] for f in fields):
                ops.append(UpdateOne({'_id': row['_id']}, {'$set': new}))
            if len(ops) >= 500:
                cls._col().bulk_write(ops, ordered=False)
                ops = []
        changed = len(ops)
        if ops:
            cls._col().bulk_write(ops, ordered=False)
        return changed

    @classmethod
    def count_current(cls) -> int:
        return cls._col().count_documents({'is_current': True})


class Faction:
    COLLECTION = FACTION_COLLECTION
    PROJECTION = {'raw': 0}

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def _mission_counts(cls) -> dict:
        """`{faction_uuid: {'missions': n, 'blueprint_missions': n}}`"""
        out = {}
        for row in get_db()[MISSION_COLLECTION].find(
                {'is_current': True, 'faction_uuid': {'$nin': [None, '']}},
                {'faction_uuid': 1, 'has_blueprints': 1}):
            c = out.setdefault(row['faction_uuid'], {'missions': 0, 'blueprint_missions': 0})
            c['missions'] += 1
            if row.get('has_blueprints'):
                c['blueprint_missions'] += 1
        return out

    @classmethod
    def list_all(cls) -> list:
        """全部勢力（約 64 筆，不分頁，篩選在前端做），附任務數。"""
        counts = cls._mission_counts()
        rows = list(cls._col().find({'is_current': True}, cls.PROJECTION)
                    .sort('name_lower', ASCENDING))
        for row in rows:
            c = counts.get(row['_id']) or {}
            row['mission_count'] = c.get('missions', 0)
            row['blueprint_mission_count'] = c.get('blueprint_missions', 0)
        return rows

    @classmethod
    def refresh_translations(cls) -> int:
        """同 Mission.refresh_translations：用存著的資料重新比對勢力的中文。"""
        from pymongo import UpdateOne
        from src.sc_zh import faction_texts_zh

        ops = []
        for row in cls._col().find({}):
            texts = faction_texts_zh(row.get('name') or '')
            if any(row.get(k) != v for k, v in texts.items()):
                ops.append(UpdateOne({'_id': row['_id']}, {'$set': texts}))
        if ops:
            cls._col().bulk_write(ops, ordered=False)
        return len(ops)

    @classmethod
    def get(cls, faction_id: str) -> Optional[dict]:
        """單一勢力＋它發布的任務（摘要）。"""
        doc = cls._col().find_one({'_id': faction_id}, cls.PROJECTION)
        if not doc:
            return None
        doc['missions'] = list(get_db()[MISSION_COLLECTION].find(
            {'is_current': True, 'faction_uuid': faction_id},
            {'title': 1, 'title_zh': 1, 'reward_scope': 1, 'has_blueprints': 1,
             'blueprint_uuids': 1, 'illegal': 1},
        ).sort('title_lower', ASCENDING))
        for m in doc['missions']:
            m['blueprint_count'] = len(m.pop('blueprint_uuids', None) or [])
        return doc

    @classmethod
    def count_current(cls) -> int:
        return cls._col().count_documents({'is_current': True})
