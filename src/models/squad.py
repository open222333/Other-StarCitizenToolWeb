"""戰術小隊分配表（玩家頁「工具箱 › 戰術小隊」，計劃見 docs/戰術小隊分配表實作計劃.md）。

一張表一筆文件（squad_boards），艦隊 → 小隊 → 艦船 → 人員都嵌在裡面，一次讀寫整張：

    {title, event_at, note, owner_scid, share_token, rev, created_at, updated_at, updated_by,
     fleets: [{id, name, note,
               squads: [{id, name, note, leader,
                         ships:   [{id, vehicle_id, vehicle_name, label, crew: [人員…]}],
                         members: [人員…]}]}]}     # members＝小隊裡不在船上的人
    人員：{id, scid, name, roles: [職位…]}      # scid 是 None＝沒註冊網站的人，只記名字；職位可兼職（最多 MAX_ROLES 個）

- 舊資料（沒有艦隊那一層的 squads、人員只有一個 role）讀取時用 upgrade() 轉成新格式：
  全部小隊放進一個預設艦隊、role 變成 [role]；下次儲存就寫成新格式（順便 $unset 舊的 squads）。

- 登入玩家都能建立、看全部的表；只有建立者能改、刪、設定分享。
- 分享碼（secrets.token_urlsafe）開啟後，不登入也能用 /player/squads/shared/<碼> 唯讀看。
  公開回應用 public_view() 逐欄位挑出來（白名單），不從完整文件刪欄位，
  之後文件多了欄位也不會不小心流出去。
- 人員存 scid＋當時的名字；讀取時用 scid 重新查暱稱（玩家改名會跟著變，被移除就用存下來的名字）。
- 艦船存 vehicle_id＋當時的船名（主檔下架還是顯示得出來）。
- rev：每次儲存加 1，前端帶的 rev 跟資料庫不同就回衝突（同一個人開兩個視窗）。
"""

import re
import secrets
from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument

from src.models.item import VehicleMaster
from src.timeutil import iso_utc
from src.models.player import Player
from src.mongo import get_db

COLLECTION = 'squad_boards'

MAX_BOARDS_PER_OWNER = 50
MAX_FLEETS = 10
MAX_SQUADS = 20           # 整張表（所有艦隊加起來）
MAX_SHIPS_PER_SQUAD = 30
MAX_PEOPLE = 300
MAX_TITLE = 60
MAX_NOTE = 500
MAX_NAME = 40
MAX_ROLE = 40
MAX_LABEL = 40
MAX_ROLES = 3

#: 職位下拉的預設選項（前端也可以自填）
DEFAULT_ROLES = ['駕駛', '副駕駛', '砲手', '工程師', '醫療', '陸戰', '其他']

_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,24}$')
_EVENT_AT_RE = re.compile(r'^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$')


class SquadError(ValueError):
    """輸入不合法，訊息可以直接給使用者看。"""


class SquadConflict(Exception):
    """rev 跟資料庫不同：表已經在別的視窗被改過。"""


def _col():
    return get_db()[COLLECTION]


def _oid(board_id):
    try:
        return ObjectId(str(board_id))
    except (InvalidId, TypeError):
        return None


def _roles_of(raw: dict) -> list:
    """人員的職位清單：新格式 roles，舊格式 role（字串）轉成 [role]；去空白、去重複，順序照原本。"""
    roles = raw.get('roles')
    if roles is None:
        roles = [raw.get('role')] if raw.get('role') else []
    if not isinstance(roles, list):
        raise SquadError('職位資料格式錯誤')
    out = []
    for r in roles:
        t = _text(r, MAX_ROLE, '職位')
        if t and t not in out:
            out.append(t)
    if len(out) > MAX_ROLES:
        raise SquadError(f'每人最多兼 {MAX_ROLES} 個職位')
    return out


def upgrade(doc: dict) -> dict:
    """舊格式轉新格式（直接改 doc，回傳同一個）：沒有 fleets 的把 squads 放進預設艦隊；人員 role → roles。"""
    if not isinstance(doc.get('fleets'), list):
        doc['fleets'] = [{'id': 'f0', 'name': '艦隊 1', 'note': '', 'squads': doc.get('squads') or []}]
    doc.pop('squads', None)
    for p in _iter_people(doc):
        if 'roles' not in p:
            p['roles'] = [p['role']] if p.get('role') else []
        p.pop('role', None)
    return doc


def _squads(board: dict):
    """表裡全部的小隊（新格式走艦隊；還沒轉的舊格式直接看 squads）。"""
    if isinstance(board.get('fleets'), list):
        for f in board['fleets']:
            yield from f.get('squads') or []
    else:
        yield from board.get('squads') or []


def _text(value, limit: int, label: str, *, required: bool = False) -> str:
    text = str(value or '').strip()
    if required and not text:
        raise SquadError(f'{label}不得為空')
    if len(text) > limit:
        raise SquadError(f'{label}太長（最多 {limit} 字）')
    return text


class _Ids:
    """整張表的 id 不重複；前端傳來的 id 格式不對或重複就重新產生。"""

    def __init__(self):
        self.used = set()
        self.n = 0

    def take(self, value, prefix: str) -> str:
        value = str(value or '')
        if _ID_RE.match(value) and value not in self.used:
            self.used.add(value)
            return value
        while True:
            self.n += 1
            new = f'{prefix}{self.n}'
            if new not in self.used:
                self.used.add(new)
                return new


def clean_board(data: dict) -> dict:
    """驗證並整理前端送來的整張表（title、event_at、note、squads）。

    人員的 scid 都要查得到玩家、艦船的 vehicle_id 都要在主檔裡，否則丟 SquadError；
    人員名字、船名由後端補（不信任前端傳的顯示名稱）。
    """
    if not isinstance(data, dict):
        raise SquadError('資料格式錯誤')
    title = _text(data.get('title'), MAX_TITLE, '名稱', required=True)
    event_at = str(data.get('event_at') or '').strip()
    if event_at and not _EVENT_AT_RE.match(event_at):
        raise SquadError('行動時間格式錯誤')
    note = _text(data.get('note'), MAX_NOTE, '備註')

    # 舊版前端只送 squads（沒有艦隊）：放進一個預設艦隊
    raw_fleets = data.get('fleets')
    if raw_fleets is None:
        raw_fleets = [{'name': '', 'squads': data.get('squads') or []}]
    if not isinstance(raw_fleets, list):
        raise SquadError('艦隊資料格式錯誤')
    if len(raw_fleets) > MAX_FLEETS:
        raise SquadError(f'艦隊最多 {MAX_FLEETS} 個')
    if any(not isinstance(f, dict) or not isinstance(f.get('squads') or [], list) for f in raw_fleets):
        raise SquadError('艦隊資料格式錯誤')
    if sum(len(f.get('squads') or []) for f in raw_fleets) > MAX_SQUADS:
        raise SquadError(f'小隊最多 {MAX_SQUADS} 個')

    ids = _Ids()
    people = []        # 所有人員（最後一起查 scid）
    vehicle_ids = set()

    def person(raw) -> dict:
        if not isinstance(raw, dict):
            raise SquadError('人員資料格式錯誤')
        scid = str(raw.get('scid') or '').strip() or None
        name = _text(raw.get('name'), MAX_NAME, '人員名稱', required=not scid)
        out = {'id': ids.take(raw.get('id'), 'm'), 'scid': scid, 'name': name, 'roles': _roles_of(raw)}
        people.append(out)
        return out

    def squad(rs, n) -> dict:
        if not isinstance(rs, dict):
            raise SquadError('小隊資料格式錯誤')
        raw_ships = rs.get('ships') or []
        raw_members = rs.get('members') or []
        if not isinstance(raw_ships, list) or not isinstance(raw_members, list):
            raise SquadError('小隊資料格式錯誤')
        if len(raw_ships) > MAX_SHIPS_PER_SQUAD:
            raise SquadError(f'每個小隊最多 {MAX_SHIPS_PER_SQUAD} 艘船')
        ships = []
        for rv in raw_ships:
            if not isinstance(rv, dict):
                raise SquadError('艦船資料格式錯誤')
            vid = str(rv.get('vehicle_id') or '').strip()
            if not vid:
                raise SquadError('艦船沒有選船')
            vehicle_ids.add(vid)
            crew = rv.get('crew') or []
            if not isinstance(crew, list):
                raise SquadError('人員資料格式錯誤')
            ships.append({'id': ids.take(rv.get('id'), 'v'), 'vehicle_id': vid, 'vehicle_name': '',
                          'label': _text(rv.get('label'), MAX_LABEL, '艦船識別名稱'),
                          'crew': [person(p) for p in crew]})
        members = [person(p) for p in raw_members]
        out = {'id': ids.take(rs.get('id'), 's'),
               'name': _text(rs.get('name'), MAX_NAME, '小隊名稱') or f'小隊 {n}',
               'note': _text(rs.get('note'), MAX_NOTE, '小隊備註'),
               'leader': None, 'ships': ships, 'members': members}
        member_ids = {p['id'] for p in members} | {p['id'] for v in ships for p in v['crew']}
        leader = str(rs.get('leader') or '')
        # 前端的 leader 指的是前端的人員 id；id 被重新產生時就對不上，當作沒設
        out['leader'] = leader if leader in member_ids else None
        return out

    fleets = []
    n_squad = 0
    for fi, rf in enumerate(raw_fleets):
        squads = []
        for rs in rf.get('squads') or []:
            n_squad += 1
            squads.append(squad(rs, n_squad))
        fleets.append({'id': ids.take(rf.get('id'), 'f'),
                       'name': _text(rf.get('name'), MAX_NAME, '艦隊名稱') or f'艦隊 {fi + 1}',
                       'note': _text(rf.get('note'), MAX_NOTE, '艦隊備註'),
                       'squads': squads})

    if len(people) > MAX_PEOPLE:
        raise SquadError(f'人員最多 {MAX_PEOPLE} 人')

    # 綁定的玩家都要存在；名字用目前的暱稱（沒有就遊戲ID）
    scids = {p['scid'] for p in people if p['scid']}
    names = Player.display_names_by_scid(scids) if scids else {}
    missing = sorted(scids - set(names))
    if missing:
        raise SquadError(f'找不到玩家：{"、".join(missing[:5])}')
    for p in people:
        if p['scid']:
            p['name'] = names[p['scid']]['nickname'] or p['scid']

    vehicles = VehicleMaster.by_ids(vehicle_ids) if vehicle_ids else {}
    missing = sorted(vehicle_ids - set(vehicles))
    if missing:
        raise SquadError('找不到艦船，請重新選船')
    for f in fleets:
        for sq in f['squads']:
            for v in sq['ships']:
                v['vehicle_name'] = vehicles[v['vehicle_id']].get('name') or v['vehicle_id']

    return {'title': title, 'event_at': event_at, 'note': note, 'fleets': fleets}


def _iter_people(board: dict):
    for s in _squads(board):
        for v in s.get('ships') or []:
            yield from v.get('crew') or []
        yield from s.get('members') or []


def _iso(dt):
    """datetime 轉 ISO；其他值（已是字串、None）原樣回傳。"""
    return iso_utc(dt) if isinstance(dt, datetime) else dt


def _stats(board: dict) -> dict:
    squads = list(_squads(board))
    return {
        'fleet_count': len(board['fleets']) if isinstance(board.get('fleets'), list) else 1,
        'squad_count': len(squads),
        'ship_count': sum(len(s.get('ships') or []) for s in squads),
        'people_count': sum(1 for _ in _iter_people(board)),
    }


def _refresh(board: dict) -> dict:
    """讀取時補上目前的暱稱、玩家是否還在、船的建議乘員數（直接改 board，回傳同一個）。"""
    people = list(_iter_people(board))
    scids = {p.get('scid') for p in people if p.get('scid')}
    names = Player.display_names_by_scid(scids) if scids else {}
    for p in people:
        info = names.get(p.get('scid')) if p.get('scid') else None
        if info:
            p['name'] = info['nickname'] or p['scid']
        p['registered'] = bool(info)
    vids = {v.get('vehicle_id') for s in _squads(board) for v in s.get('ships') or []}
    vehicles = VehicleMaster.by_ids(vids) if vids else {}
    for s in _squads(board):
        for v in s.get('ships') or []:
            master = vehicles.get(v.get('vehicle_id')) or {}
            if master.get('name'):
                v['vehicle_name'] = master['name']
            v['crew_max'] = master.get('crew_max')
    return board


def _owner_name(scids) -> dict:
    names = Player.display_names_by_scid(scids) if scids else {}
    return {s: (names.get(s) or {}).get('nickname') or s for s in scids}


def _serialize(doc: dict, viewer_scid: str) -> dict:
    out = upgrade({k: v for k, v in doc.items() if k != '_id'})
    out['id'] = str(doc['_id'])
    for k in ('created_at', 'updated_at'):
        out[k] = _iso(out.get(k))
    out['can_edit'] = doc.get('owner_scid') == viewer_scid
    if not out['can_edit']:
        out['share_token'] = None     # 分享碼只給建立者看（別人看了也不能做什麼，但沒必要給）
    out['owner_name'] = _owner_name([doc.get('owner_scid')]).get(doc.get('owner_scid'))
    out['default_roles'] = DEFAULT_ROLES
    out['max_roles'] = MAX_ROLES
    return _refresh(out)


class SquadBoard:

    @staticmethod
    def list_all() -> list:
        """全部的表（只有統計數字，不含小隊內容），最近更新的在前。"""
        docs = list(_col().find({}).sort('updated_at', -1).limit(500))
        owners = _owner_name({d.get('owner_scid') for d in docs if d.get('owner_scid')})
        return [{
            'id': str(d['_id']), 'title': d.get('title'), 'event_at': d.get('event_at') or '',
            'owner_scid': d.get('owner_scid'), 'owner_name': owners.get(d.get('owner_scid')),
            'shared': bool(d.get('share_token')), 'updated_at': _iso(d.get('updated_at')),
            **_stats(d),
        } for d in docs]

    @staticmethod
    def get(board_id) -> dict | None:
        oid = _oid(board_id)
        return _col().find_one({'_id': oid}) if oid else None

    @staticmethod
    def view(doc: dict, viewer_scid: str) -> dict:
        return _serialize(doc, viewer_scid)

    @staticmethod
    def create(owner_scid: str, data: dict | None = None, copy_from: dict | None = None) -> dict:
        if _col().count_documents({'owner_scid': owner_scid}) >= MAX_BOARDS_PER_OWNER:
            raise SquadError(f'每人最多 {MAX_BOARDS_PER_OWNER} 張分配表，請先刪掉不用的')
        if copy_from:
            src = upgrade({k: copy_from.get(k) for k in ('title', 'event_at', 'note', 'squads', 'fleets') if k in copy_from})
            src['title'] = (str(data.get('title') or '').strip() if data else '') or \
                f'{copy_from.get("title") or ""}（複本）'[:MAX_TITLE]
            body = clean_board(src)
        else:
            body = clean_board(data or {})
        now = datetime.utcnow()
        doc = {**body, 'owner_scid': owner_scid, 'share_token': None, 'rev': 1,
               'created_at': now, 'updated_at': now, 'updated_by': owner_scid}
        doc['_id'] = _col().insert_one(doc).inserted_id
        return doc

    @staticmethod
    def save(doc: dict, data: dict, editor_scid: str) -> dict:
        """整張儲存；data 要帶 rev，跟資料庫不同丟 SquadConflict。"""
        try:
            rev = int(data.get('rev'))
        except (TypeError, ValueError):
            raise SquadError('缺少版本號（rev）') from None
        body = clean_board(data)
        updated = _col().find_one_and_update(
            {'_id': doc['_id'], 'rev': rev},
            {'$set': {**body, 'updated_at': datetime.utcnow(), 'updated_by': editor_scid},
             '$unset': {'squads': ''},           # 舊格式（沒有艦隊那一層）的欄位
             '$inc': {'rev': 1}},
            return_document=ReturnDocument.AFTER,
        )
        if not updated:
            raise SquadConflict()
        return updated

    @staticmethod
    def delete(doc: dict) -> None:
        _col().delete_one({'_id': doc['_id']})

    @staticmethod
    def set_share(doc: dict, enabled: bool, regenerate: bool = False) -> str | None:
        token = doc.get('share_token')
        if not enabled:
            token = None
        elif regenerate or not token:
            token = secrets.token_urlsafe(16)
        _col().update_one({'_id': doc['_id']}, {'$set': {'share_token': token}})
        return token

    @staticmethod
    def find_shared(token: str) -> dict | None:
        token = str(token or '')
        if not token or len(token) > 64:
            return None
        return _col().find_one({'share_token': token})

    @staticmethod
    def public_view(doc: dict) -> dict:
        """公開頁的資料：逐欄位挑（白名單），人員只有顯示名稱、是否註冊和職位。"""
        board = _refresh(upgrade({k: doc.get(k) for k in ('squads', 'fleets') if k in doc}))

        def pub_person(p):
            return {'id': p.get('id'), 'name': p.get('name') or '', 'roles': list(p.get('roles') or []),
                    'registered': bool(p.get('registered'))}

        def pub_squad(s):
            return {
                'id': s.get('id'), 'name': s.get('name') or '', 'note': s.get('note') or '',
                'leader': s.get('leader'),
                'ships': [{'id': v.get('id'), 'vehicle_name': v.get('vehicle_name') or '',
                           'label': v.get('label') or '', 'crew_max': v.get('crew_max'),
                           'crew': [pub_person(p) for p in v.get('crew') or []]}
                          for v in s.get('ships') or []],
                'members': [pub_person(p) for p in s.get('members') or []],
            }

        return {
            'title': doc.get('title') or '',
            'event_at': doc.get('event_at') or '',
            'note': doc.get('note') or '',
            'owner_name': _owner_name([doc.get('owner_scid')]).get(doc.get('owner_scid')),
            'updated_at': _iso(doc.get('updated_at')),
            'fleets': [{'id': f.get('id'), 'name': f.get('name') or '', 'note': f.get('note') or '',
                        'squads': [pub_squad(s) for s in f.get('squads') or []]}
                       for f in board['fleets']],
        }
