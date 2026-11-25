"""配裝模擬（玩家頁「配裝模擬」，見 frontend/src/components/LoadoutSimulator.vue）。

資料由「配裝」同步項目從 scunpacked-data 寫入（見 src/scdata_loadout.py）：
  - ship_loadout_master：每艘船的掛點樹（slots）與船體、裝甲、穿透倍率、飛行數值
  - ship_item_master：艦船配件的精簡數值（stats）、子槽（ports）、標籤

換配件、算傷害／護盾／量子都在前端做（frontend/src/utils/loadoutCalc.js），後端只給資料。
"""

import re

from src.mongo import get_db
from src.models.nav import _VARIANT_RE
from src.models import uex_item_price

SHIP_COLLECTION = 'ship_loadout_master'
ITEM_COLLECTION = 'ship_item_master'

_HIDE = {'_sync': 0, 'first_seen_at': 0, 'is_current': 0, 'retired_at': 0, 'name_lower': 0}
LIST_FIELDS = {'name': 1, 'name_zh': 1, 'class_name': 1, 'manufacturer': 1, 'manufacturer_name': 1,
               'size': 1, 'career': 1, 'role': 1, 'role_zh': 1, 'is_spaceship': 1}
MAX_IDS = 500
_TYPE_RE = re.compile(r'^[A-Za-z]+$')


#: 船清單快取：「配裝」「載具」同步的 run_id 都沒變就用上次排好的（待辦 2-3）；沒有同步紀錄（測試）不快取
_ships_cache: dict = {'key': None, 'rows': None}


def _sync_version() -> str:
    runs = {d['_id']: d.get('last_run_id') or '' for d in get_db()['sync_jobs'].find(
        {'_id': {'$in': ['loadout', 'vehicles']}}, {'last_run_id': 1})}
    return f"{runs.get('loadout', '')}|{runs.get('vehicles', '')}"


def ships() -> list:
    """可以配裝的船（快取，見 _ships_cache）。"""
    key = _sync_version()
    if key.strip('|') and _ships_cache['key'] == key and _ships_cache['rows'] is not None:
        return _ships_cache['rows']
    rows = _ships()
    if key.strip('|'):
        _ships_cache.update(key=key, rows=rows)
    return rows


def _ships() -> list:
    """可以配裝的船。同名的只留一筆（玩家載具主檔有的優先，再來是沒有 NPC／任務變體尾巴、class_name 最短的）。"""
    db = get_db()
    rows = list(db[SHIP_COLLECTION].find({'is_current': {'$ne': False}}, LIST_FIELDS))
    known_ids, known_cls = set(), set()
    for v in db['vehicle_master'].find({'is_current': {'$ne': False}}, {'class_name': 1}):
        known_ids.add(v['_id'])
        if v.get('class_name'):
            known_cls.add(v['class_name'].lower())

    def rank(r):
        cls = r.get('class_name') or ''
        known = r['_id'] in known_ids or cls.lower() in known_cls
        return (not known, bool(_VARIANT_RE.search(cls)), len(cls), cls)

    best = {}
    for r in sorted(rows, key=rank):
        key = (r.get('name') or '').strip().lower()
        if key and key not in best:
            best[key] = r
    out = [{'id': r['_id'], **{k: r.get(k) for k in LIST_FIELDS}} for r in best.values()]
    out.sort(key=lambda r: (r['name'] or '').lower())
    return out


def _slot_items(slots, out: set):
    for s in slots or []:
        if s.get('item'):
            out.add(s['item'])
        _slot_items(s.get('children'), out)


def _clean_item(doc: dict) -> dict:
    doc['id'] = doc.pop('_id')
    return doc


def items_by_ids(ids) -> dict:
    """{uuid: 配件}，連同這些配件子槽的預設配件（例如砲塔預設裝的武器）一起帶出來。"""
    col = get_db()[ITEM_COLLECTION]
    out, want = {}, {i for i in ids if isinstance(i, str) and i}
    for _ in range(4):                     # 砲塔 → 雲台 → 武器，最多幾層
        want -= set(out)
        if not want:
            break
        found = list(col.find({'_id': {'$in': list(want)[:MAX_IDS]}}, _HIDE))
        if not found:
            break
        nxt = set()
        for d in found:
            d = _clean_item(d)
            out[d['id']] = d
            nxt.update(p['default'] for p in d.get('ports') or [] if p.get('default'))
        want = nxt
    return out


def ship(ship_id: str):
    """一艘船的掛點樹＋數值，附上樹裡用到的配件（items）。"""
    doc = get_db()[SHIP_COLLECTION].find_one({'_id': ship_id}, _HIDE)
    if not doc:
        return None
    doc['id'] = doc.pop('_id')
    ids: set = set()
    _slot_items(doc.get('slots'), ids)
    doc['items'] = items_by_ids(ids)
    annotate(list(doc['items'].values()))
    return doc


def items(types=None, ids=None) -> list:
    """配件清單：types＝主類（WeaponGun、Missile…），ids＝指定 UUID；兩個都給就合併。"""
    col = get_db()[ITEM_COLLECTION]
    found = {}
    types = [t for t in (types or []) if isinstance(t, str) and _TYPE_RE.match(t)]
    if types:
        for d in col.find({'is_current': {'$ne': False}, 'type': {'$in': types}}, _HIDE):
            d = _clean_item(d)
            found[d['id']] = d
    if ids:
        found.update(items_by_ids(ids[:MAX_IDS]))
    annotate(list(found.values()))
    return sorted(found.values(), key=lambda d: (d.get('type') or '', d.get('size') or 0, (d.get('name') or '').lower()))


def annotate(rows: list) -> list:
    """配件附上取得方式（配件的 UUID 跟 Wiki 物品主檔、藍圖的產出物同一套）：
    price＝UEX 最低購買價（aUEC，買不到是 None）、buyable、blueprint＝做得出這個配件的藍圖 UUID（沒有是 None）。
    配裝模擬用來標「可購買／可製作」、算購物車；可製作的才能調品質（見 frontend/src/utils/loadoutCraft.js）。"""
    if not rows:
        return rows
    tmp = [{'_id': d['id']} for d in rows]
    uex_item_price.attach_summaries(tmp)
    price = {t['_id']: (t.get('uex_price') or {}).get('buy_min') for t in tmp}
    bp = {}
    for b in get_db()['blueprint_master'].find(
            {'output_item_uuid': {'$in': [d['id'] for d in rows]}, 'is_current': True},
            {'_id': 1, 'output_item_uuid': 1}).sort('_id', 1):
        bp.setdefault(b['output_item_uuid'], b['_id'])
    for d in rows:
        d['price'] = price.get(d['id'])
        d['buyable'] = d['price'] is not None
        d['blueprint'] = bp.get(d['id'])
    return rows
