"""任務／勢力主檔的唯讀模型（Star Citizen Wiki API 的 missions／factions）。

由 tasks/scdata_sync.py 同步進 mission_master／faction_master，本模組只讀不寫；
要加欄位就改 src/scdata.py 的 map_mission／map_faction 再重跑同步。

跟藍圖的關聯：任務的獎勵藍圖池（blueprint_pools）在同步時就攤平成
`blueprint_uuids`（有索引），「這張藍圖由哪些任務解鎖」是在本地反查，
不用再打上游 API。

查詢一律加 is_current=True（上游移除的任務／勢力留著紀錄，但不顯示）。
"""

import re
from typing import Optional

from pymongo import ASCENDING

from src.models import name_search
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
        'reward_min': 1, 'reward_max': 1, 'reward_currency': 1, 'time_to_complete_minutes': 1,
        'reputation_gained': 1, 'cooldown_label': 1, 'star_systems': 1,
        'blueprint_pools': 1,
    }

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def _filter(cls, *, query: str = '', reward_scopes=None, star_systems=None,
                faction_uuids=None, legality=None, has_blueprints: bool = False, has_reward: bool = False,
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
        if has_reward:
            # 固定報酬（上游 FixedReward）：金額在 reward_min，少數有範圍的在 reward_max；
            # 其他任務的報酬是遊戲接取時依難度動態計算，資料裡沒有數字
            filt['$and'] = [*filt.get('$and', []), {'$or': [{'reward_min': {'$gt': 0}}, {'reward_max': {'$gt': 0}}]}]
        if missing_zh:
            filt['title_zh'] = {'$in': [None, '']}
        if (blueprint_uuid or '').strip():
            filt['blueprint_uuids'] = blueprint_uuid.strip()
        if (query or '').strip():
            # 名稱關鍵字（規則見 src/models/name_search.py）
            filt = name_search.merge(filt, name_search.strict_filter(query, cls.NAME_FIELDS))
        return filt

    @staticmethod
    def _attach_blueprint_names(rows: list) -> list:
        """獎勵藍圖池的每張藍圖補上主檔的中文名稱（`name_zh`）與是否預設可用（`is_available_by_default`，
        玩家頁「任務」分頁算已登記／未登記時視同已登記），一次 $in 查完。"""
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
                    it['is_available_by_default'] = bool(master.get('is_available_by_default'))
        return rows

    @classmethod
    def _attach_chain(cls, rows: list, visible_only: bool = False) -> list:
        """前置任務／完成後可接的任務（任務詳情的「前置任務」「完成後可接」）。

        - 每個前置任務補上中文標題（title_zh）與 linkable（主檔裡找得到、這個身分看得到，才能點開）
        - unlocks＝把這個任務列為前置任務的其他任務 [{uuid, title, title_zh}]（prerequisite_uuids 反查）
        """
        rows = [r for r in rows if r]
        if not rows:
            return rows
        pre_ids = {m.get('uuid') for r in rows for g in (r.get('prerequisite_groups') or [])
                   for m in (g.get('missions') or []) if m.get('uuid')}
        ids = [r['_id'] for r in rows if r.get('_id')]
        fields = {'title': 1, 'title_zh': 1, 'prerequisite_uuids': 1}
        known = {}
        if pre_ids:
            filt = add_visibility_filter({'_id': {'$in': list(pre_ids)}, 'is_current': True}, visible_only=visible_only)
            known = {d['_id']: d for d in cls._col().find(filt, fields)}
        unlocks: dict = {}
        if ids:
            filt = add_visibility_filter({'prerequisite_uuids': {'$in': ids}, 'is_current': True}, visible_only=visible_only)
            for d in cls._col().find(filt, fields).sort('title_lower', ASCENDING):
                for pid in d.get('prerequisite_uuids') or []:
                    unlocks.setdefault(pid, []).append(
                        {'uuid': d['_id'], 'title': d.get('title'), 'title_zh': d.get('title_zh')})
        for r in rows:
            for g in r.get('prerequisite_groups') or []:
                for m in g.get('missions') or []:
                    hit = known.get(m.get('uuid'))
                    m['title_zh'] = hit.get('title_zh') if hit else None
                    m['linkable'] = bool(hit)
            r['unlocks'] = unlocks.get(r.get('_id'), [])
            r.pop('prerequisite_uuids', None)
        return rows

    #: 列表可以排序的欄位（sort_by → 文件欄位）
    SORT_FIELDS = {
        'title': 'title_lower', 'title_zh': 'title_zh', 'reward_scope': 'reward_scope',
        'giver': ['faction_name', 'mission_giver'], 'star_systems': 'star_systems', 'illegal': 'illegal',
        # 固定報酬的金額在 reward_min（reward_max 多半是 0）
        'reward': ['reward_min', 'reward_max'], 'player_visible': 'player_visible',
        'reputation': 'reputation_gained.amount', 'cooldown': 'cooldown_seconds',
    }

    #: 列表的名稱搜尋欄位：標題（英文比字首、中文任意位置）、發布者、debug name（底線分段）
    NAME_FIELDS = name_search.NameFields(en=['title_lower'], zh=['title_zh', 'mission_giver'], code=['debug_name'],
                                         sort_field='title_lower')

    @classmethod
    def list_all(cls, limit: int = 50, offset: int = 0, sort_by: str = '', sort_dir: str = 'asc',
                 meta: Optional[dict] = None, **filters) -> tuple:
        """名稱關鍵字規則見 src/models/name_search.py：字首找不到時放寬成任意位置（meta['match']='loose'），
        沒有指定排序時依相符程度排。"""
        from src.models.sorting import sort_spec
        query = filters.pop('query', '')
        filt = cls._filter(**filters)
        limit = max(1, min(int(limit or 50), MAX_LIMIT))
        offset = max(0, int(offset or 0))
        spec = sort_spec(sort_by, sort_dir, cls.SORT_FIELDS, [('title_lower', ASCENDING), ('_id', ASCENDING)])
        rows, total, match = name_search.find(cls._col(), filt, query, cls.NAME_FIELDS, cls.PROJECTION,
                                              sort=spec, offset=offset, limit=limit, relevance=not sort_by)
        if meta is not None:
            meta['match'] = match
        return cls._attach_chain(cls._attach_blueprint_names(rows), visible_only=filters.get('visible_only', False)), total

    @classmethod
    def get(cls, mission_id: str, visible_only: bool = False) -> Optional[dict]:
        """單一任務；visible_only＝玩家端，玩家頁面不顯示的當作找不到。"""
        doc = cls._col().find_one(add_visibility_filter({'_id': mission_id}, visible_only=visible_only), cls.PROJECTION)
        return cls._attach_chain(cls._attach_blueprint_names([doc]), visible_only=visible_only)[0] if doc else None

    @classmethod
    def facets(cls, visible_only: bool = False) -> dict:
        """篩選下拉用：類型、星系、勢力（含任務數）；visible_only＝只算玩家頁面顯示的任務。"""
        col = cls._col()
        cur = add_visibility_filter({'is_current': True}, visible_only=visible_only)
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
        有好幾個池就取最高）與 `pool_size`（那個池共有幾張藍圖，抽中其中一張），
        以及 `pool_blueprints`（這個任務會給的**所有**藍圖，跨所有獎勵池去重：uuid／名稱／是否預設可用），
        玩家頁用來標出哪些自己已登記、哪些還沒（例如 10 張裡登記了 1 張）。"""
        uuid = (blueprint_uuid or '').strip()
        if not uuid:
            return []
        filt = add_visibility_filter({'is_current': True, 'blueprint_uuids': uuid},
                                     visible_only=visible_only)
        rows = list(cls._col().find(filt, cls.BRIEF_PROJECTION))
        out = []
        for row in rows:
            best = None
            pools = row.pop('blueprint_pools', None) or []
            # 任務會給的全部藍圖（所有池合起來、保留順序去重）
            row['_pool_uuids'] = list(dict.fromkeys(
                it.get('blueprint_uuid') for p in pools for it in (p.get('items') or []) if it.get('blueprint_uuid')))
            for pool in pools:
                items = pool.get('items') or []
                if any(it.get('blueprint_uuid') == uuid for it in items):
                    chance = pool.get('drop_chance')
                    if best is None or (chance or 0) > (best[0] or 0):
                        best = (chance, len(items))
            row['chance'], row['pool_size'] = best if best else (None, None)
            out.append(row)
        names = BlueprintMaster.names_by_ids({u for r in out for u in r['_pool_uuids']})
        for row in out:
            row['pool_blueprints'] = [{
                'uuid': u,
                'name': (names.get(u) or {}).get('name') or u,
                'name_zh': (names.get(u) or {}).get('name_zh'),
                'is_available_by_default': bool((names.get(u) or {}).get('is_available_by_default')),
            } for u in row.pop('_pool_uuids')]
        out.sort(key=lambda r: (-(r['chance'] or 0), (r.get('title') or '').lower()))
        return out

    @classmethod
    def for_commodity(cls, name: str, visible_only: bool = False, limit: int = 200) -> list:
        """要運送這種商品／礦物的任務（hauling_summary 的名稱相同，不分大小寫；「Agricium (Ore)」這種
        帶括號說明的也算），每筆附 `haul`：{min_amount, max_amount}（同一任務多筆取第一筆）。礦物頁「用在哪些任務」。"""
        n = (name or '').strip()
        if not n:
            return []
        rx = re.compile(rf'^{re.escape(n)}(\s*\(.*\))?$', re.IGNORECASE)
        filt = add_visibility_filter({'is_current': True, 'hauling_summary.name': rx},
                                     visible_only=visible_only)
        proj = {**cls.BRIEF_PROJECTION, 'hauling_summary': 1}
        proj.pop('blueprint_pools', None)
        out = []
        for row in cls._col().find(filt, proj).limit(max(1, min(int(limit), 500))):
            hauls = [h for h in row.pop('hauling_summary', None) or [] if isinstance(h, dict) and rx.match(h.get('name') or '')]
            row['haul'] = {'name': hauls[0].get('name'), 'min_amount': hauls[0].get('min_amount'),
                           'max_amount': hauls[0].get('max_amount')} if hauls else None
            out.append(row)
        out.sort(key=lambda r: (-(r.get('reward_max') or 0), (r.get('title') or '').lower()))
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



def standing_key(name) -> str:
    """聲望階級名稱比對用（不分大小寫、去空白）；PLACEHOLDER 這類上游佔位字當作沒有。"""
    text = (name or '').strip() if isinstance(name, str) else ''
    return '' if not text or 'placeholder' in text.lower() else text.lower()


def _steps_of(ladder) -> list:
    """一條階級表（list）→ [{name, min_reputation}]。"""
    out = []
    for step in ladder if isinstance(ladder, list) else []:
        if isinstance(step, str):
            out.append({'name': step, 'min_reputation': None})
            continue
        if not isinstance(step, dict):
            continue
        name = step.get('display_name') or step.get('name') or step.get('title') or step.get('label')
        value = next((step[k] for k in ('min_reputation', 'reputation', 'min', 'threshold', 'value')
                      if isinstance(step.get(k), (int, float)) and not isinstance(step.get(k), bool)), None)
        if name:
            out.append({'name': name, 'min_reputation': value})
    return out


#: 一條階級表在 dict 裡常見的 key
_STEP_KEYS = ('ranks', 'standings', 'steps', 'ladder', 'tiers', 'levels')
#: 「一種聲望」的名稱在 dict 裡常見的 key
_SCOPE_NAME_KEYS = ('scope', 'scope_name', 'display_name', 'name', 'title', 'label')


def _scope_steps(obj):
    """obj 是「一種聲望」（裡面有一條階級表）時回傳那條表，不是就回 None。"""
    if not isinstance(obj, dict):
        return None
    for k in _STEP_KEYS:
        if isinstance(obj.get(k), list):
            return obj[k]
    return None


def _scope_name(obj):
    return next((obj[k] for k in _SCOPE_NAME_KEYS if isinstance(obj.get(k), str) and obj.get(k)), None)


def ladder_scopes(ladder) -> list:
    """勢力 reputation_ladder → [{scope, steps}]。一個勢力可以有好幾種聲望（例如立場、貨運），各有一條階級表。

    上游結構不固定，認得這幾種（scope 是那種聲望的名稱，看不出來的是 None）：
      - [{name, min_reputation}, …]                     一條表
      - {ranks|standings|steps: […]}                    一條表
      - [{scope|name: 'Hauling', ranks: […]}, …]        多種聲望，每種一條
      - {'Hauling': […], 'Affinity': […]}               多種聲望，key 是名稱
    """
    if isinstance(ladder, list):
        dicts = [x for x in ladder if isinstance(x, dict)]
        if dicts and all(_scope_steps(x) is not None for x in dicts):
            out = []
            for x in dicts:
                steps = _steps_of(_scope_steps(x))
                if steps:
                    out.append({'scope': _scope_name(x), 'steps': steps})
            return out
        steps = _steps_of(ladder)
        return [{'scope': None, 'steps': steps}] if steps else []
    if isinstance(ladder, dict):
        own = _scope_steps(ladder)
        if own is not None:
            steps = _steps_of(own)
            return [{'scope': _scope_name(ladder), 'steps': steps}] if steps else []
        out = []
        for key, value in ladder.items():
            if isinstance(value, list):
                steps = _steps_of(value)
            elif isinstance(value, dict):
                steps = _steps_of(_scope_steps(value) or [])
            else:
                steps = []
            if steps:
                out.append({'scope': str(key), 'steps': steps})
        return out
    return []


def ladder_steps(ladder) -> list:
    """全部聲望種類的階級攤平成 [{name, min_reputation}]（同名只留第一個），任務說明換算「聲望門檻」分數用。"""
    out, seen = [], set()
    for sc in ladder_scopes(ladder):
        for st in sc['steps']:
            key = standing_key(st['name']) or st['name']
            if key not in seen:
                seen.add(key)
                out.append(st)
    return out


def _rep_scopes_for(mission: dict, faction_id: str, faction_name: str) -> list:
    """任務完成後給這個勢力的聲望是哪幾種（reputation_gained 的 scope）。"""
    out = []
    for r in mission.get('reputation_gained') or []:
        if not isinstance(r, dict) or not r.get('scope'):
            continue
        if r.get('faction_uuid') == faction_id or (faction_name and (r.get('faction') or '').strip().lower() == faction_name):
            if r['scope'] not in out:
                out.append(r['scope'])
    return out


class Faction:
    COLLECTION = FACTION_COLLECTION
    PROJECTION = {'raw': 0}

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @classmethod
    def _mission_counts(cls, visible_only: bool = False) -> dict:
        """`{faction_uuid: {'missions', 'blueprint_missions', 'mission_types', 'rep_scopes'}}`；
        visible_only＝只算玩家頁面顯示的任務。rep_scopes＝任務給這個勢力的聲望種類（reputation_gained 的 scope）。"""
        out = {}
        names = {r['_id']: (r.get('name') or '').strip().lower()
                 for r in cls._col().find({'is_current': True}, {'name': 1})}
        filt = add_visibility_filter({'is_current': True, 'faction_uuid': {'$nin': [None, '']}},
                                     visible_only=visible_only)
        for row in get_db()[MISSION_COLLECTION].find(
                filt,
                {'faction_uuid': 1, 'has_blueprints': 1, 'reward_scope': 1, 'reputation_gained': 1}):
            fid = row['faction_uuid']
            c = out.setdefault(fid, {'missions': 0, 'blueprint_missions': 0, 'mission_types': [], 'rep_scopes': []})
            c['missions'] += 1
            if row.get('has_blueprints'):
                c['blueprint_missions'] += 1
            if row.get('reward_scope') and row['reward_scope'] not in c['mission_types']:
                c['mission_types'].append(row['reward_scope'])
            for sc in _rep_scopes_for(row, fid, names.get(fid, '')):
                if sc not in c['rep_scopes']:
                    c['rep_scopes'].append(sc)
        return out

    @classmethod
    def list_all(cls, visible_only: bool = False) -> list:
        """全部勢力（約 64 筆，不分頁，篩選在前端做），附任務數（玩家只算玩家頁面顯示的任務）、
        任務類型 mission_types、聲望種類 scopes（階級表裡的種類＋任務會給的聲望種類）。"""
        counts = cls._mission_counts(visible_only=visible_only)
        rows = list(cls._col().find({'is_current': True}, cls.PROJECTION)
                    .sort('name_lower', ASCENDING))
        for row in rows:
            c = counts.get(row['_id']) or {}
            row['mission_count'] = c.get('missions', 0)
            row['blueprint_mission_count'] = c.get('blueprint_missions', 0)
            row['mission_types'] = sorted(c.get('mission_types') or [])
            scopes = [sc['scope'] for sc in ladder_scopes(row.get('reputation_ladder')) if sc['scope']]
            for sc in c.get('rep_scopes') or []:
                if sc not in scopes:
                    scopes.append(sc)
            row['scopes'] = scopes
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
    def get(cls, faction_id: str, visible_only: bool = False) -> Optional[dict]:
        """單一勢力＋它發布的任務（摘要；玩家只看得到玩家頁面顯示的任務）。"""
        doc = cls._col().find_one({'_id': faction_id}, cls.PROJECTION)
        if not doc:
            return None
        doc['missions'] = list(get_db()[MISSION_COLLECTION].find(
            add_visibility_filter({'is_current': True, 'faction_uuid': faction_id}, visible_only=visible_only),
            {'title': 1, 'title_zh': 1, 'reward_scope': 1, 'has_blueprints': 1,
             'blueprint_uuids': 1, 'illegal': 1},
        ).sort('title_lower', ASCENDING))
        for m in doc['missions']:
            m['blueprint_count'] = len(m.pop('blueprint_uuids', None) or [])
        return doc

    #: 勢力聲望分頁每個任務要的欄位（列表＋展開的 MissionDetail）
    REPUTATION_MISSION_FIELDS = {f: 1 for f in (
        'title', 'title_zh', 'description', 'description_zh', 'reward_scope', 'illegal', 'star_systems',
        'faction_uuid', 'faction_name', 'faction_name_zh', 'mission_giver', 'mission_giver_zh',
        'min_standing_name', 'max_standing_name', 'blueprint_pools', 'reward_min', 'reward_max', 'reward_currency',
        'time_to_complete_minutes',
        'reputation_gained', 'cooldown_seconds', 'shareable', 'once_only', 'has_combat',
        'enemy_count_min', 'enemy_count_max', 'has_chain', 'has_prerequisites', 'max_players_per_instance',
        'prerequisite_groups')}

    @classmethod
    def ladders(cls) -> dict:
        """{faction_uuid: [{name, min_reputation}]}，玩家頁任務說明顯示「聲望門檻」的分數用。"""
        return {r['_id']: ladder_steps(r.get('reputation_ladder'))
                for r in cls._col().find({'is_current': True}, {'reputation_ladder': 1})}

    @classmethod
    def reputation(cls, faction_id: str, visible_only: bool = False) -> Optional[dict]:
        """玩家頁「任務 › 勢力聲望」：勢力的聲望階級，每一階列出要這個階級才能接的任務。

        任務的 min_standing_name 對到階級名稱（不分大小寫）；沒有門檻的放 open，
        門檻對不到階級表的放 unmatched（名稱照原樣顯示）。
        """
        doc = cls._col().find_one({'_id': faction_id}, {'name': 1, 'name_zh': 1, 'reputation_ladder': 1,
                                                       'faction_type': 1, 'lawful': 1})
        if not doc:
            return None
        filt = add_visibility_filter({'is_current': True, 'faction_uuid': faction_id}, visible_only=visible_only)
        # 每個任務可以展開看細節（說明、條件、報酬、聲望異動、獎勵藍圖）：只取 MissionDetail 用得到的欄位
        missions = Mission._attach_chain(Mission._attach_blueprint_names(
            list(get_db()[MISSION_COLLECTION].find(filt, cls.REPUTATION_MISSION_FIELDS).sort('title_lower', ASCENDING))),
            visible_only=visible_only)
        name_l = (doc.get('name') or '').strip().lower()
        scopes = [{'scope': sc['scope'], 'ranks': [{**st, 'missions': []} for st in sc['steps']]}
                  for sc in ladder_scopes(doc.get('reputation_ladder'))]
        # 階級名稱 → 有這一階的聲望種類（同名可能出現在好幾種）
        by_key = {}
        for sc in scopes:
            for r in sc['ranks']:
                k = standing_key(r['name'])
                if k:
                    by_key.setdefault(k, []).append((sc, r))
        open_missions, unmatched, rep_scopes = [], [], []
        for m in missions:
            m['rep_scopes'] = _rep_scopes_for(m, faction_id, name_l)
            for s_ in m['rep_scopes']:
                if s_ not in rep_scopes:
                    rep_scopes.append(s_)
            key = standing_key(m.get('min_standing_name'))
            if not key:
                open_missions.append(m)
                continue
            hits = by_key.get(key)
            if not hits:
                unmatched.append(m)
                continue
            # 好幾種聲望都有這個階級名稱：優先放到這個任務給的聲望種類，再來是任務類型同名的
            wanted = [x.lower() for x in m['rep_scopes'] + [m.get('reward_scope') or '']]
            _, rank = next(((sc, r) for sc, r in hits if (sc['scope'] or '').lower() in wanted), hits[0])
            rank['missions'].append(m)
        # 階級表只有一條、沒寫種類名稱：任務給的聲望只有一種時就用它當名稱
        if len(scopes) == 1 and not scopes[0]['scope'] and len(rep_scopes) == 1:
            scopes[0]['scope'] = rep_scopes[0]
        # 任務會給、但階級表沒有的聲望種類也列出來（沒有階級，只有名稱）
        known = {(sc['scope'] or '').lower() for sc in scopes}
        extra = [{'scope': s_, 'ranks': []} for s_ in rep_scopes if s_.lower() not in known]
        return {'faction': {'_id': doc['_id'], 'name': doc.get('name'), 'name_zh': doc.get('name_zh'),
                            'faction_type': doc.get('faction_type'), 'lawful': doc.get('lawful')},
                'scopes': scopes + extra,
                # 舊欄位：第一種聲望的階級
                'ranks': scopes[0]['ranks'] if scopes else [],
                'open': open_missions, 'unmatched': unmatched}

    @classmethod
    def count_current(cls) -> int:
        return cls._col().count_documents({'is_current': True})
