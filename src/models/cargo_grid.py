"""飛船貨物網格（cargo_grid_master，sc-cargo.space 的資料，「貨物網格」同步項目，見 src/scdata.py 的 map_cargo_grid）。

sc-cargo.space 的船名跟遊戲／Wiki 的寫法不一定一樣（Hull-C ↔ Hull C、有沒有廠商前綴），
所以對應到載具主檔（vehicle_master）時把名稱只留英數字、轉小寫再比對，船名、廠商＋船名、
別名（alternativeNames）都試；完全對不到的再用「載具名稱以船名開頭」補對（見 link_vehicles）。
對到的寫進 vehicle_uuids（同名變體可能好幾艘）。
"""

import re

from pymongo import UpdateOne

from src.mongo import get_db

COLLECTION = 'cargo_grid_master'


def _norm(text) -> str:
    return re.sub(r'[^a-z0-9]', '', str(text or '').lower())


#: 概念船標記（[Concept]、[Cargo Concept]…）比對時拿掉
_TAG = re.compile(r'\[[^\]]*\]')
#: 「Aurora CL (Mk I)」→「Aurora Mk I CL」（遊戲把型號放在後面）
_MARK_LAST = re.compile(r'^(\S+) (.+) \((Mk [IVX]+)\)$', re.I)
#: 廠商縮寫前綴（C.O. Nomad）
_ABBR_PREFIX = re.compile(r'^(?:[A-Za-z]\.){2,}\s+')
#: 開頭比對的最短長度（太短的名稱容易誤配）
PREFIX_MIN = 4


def _vehicle_keys(v: dict) -> set:
    """一艘載具可以用來比對的名稱（正規化後）：名稱、遊戲名稱、廠商＋名稱、去掉廠商前綴的名稱。"""
    names = {v.get('name'), v.get('game_name')}
    for mfr in (v.get('manufacturer_name'), v.get('manufacturer_code')):
        if not mfr:
            continue
        if v.get('name'):
            names.add(f'{mfr} {v["name"]}')
        for n in (v.get('name'), v.get('game_name')):
            if n and n.lower().startswith(mfr.lower() + ' '):
                names.add(n[len(mfr):])
    names |= {_ABBR_PREFIX.sub('', n) for n in names if n}
    return {_norm(n) for n in names if _norm(n)}


def _grid_keys(row: dict) -> set:
    """一筆貨物網格的船名（正規化後）：船名、廠商＋船名、別名；概念船標記拿掉的版本也算。"""
    names = [row.get('name'), f'{row.get("manufacturer") or ""} {row.get("name") or ""}',
             *(row.get('alternative_names') or [])]
    names += [_TAG.sub('', n or '') for n in names]
    names += [_MARK_LAST.sub(r'\1 \3 \2', n.strip()) for n in names if n]
    return {_norm(n) for n in names if _norm(n)}


def link_vehicles() -> int:
    """把每艘船的貨物網格對到載具主檔，寫 vehicle_uuids／vehicle_names，回傳有變動的筆數。

    先找名稱完全一樣的；完全對不到的船，再找名稱以它開頭的載具（sc-cargo.space 常寫短名，
    例如 C2 Hercules ↔ C2 Hercules Starlifter、MPUV-C ↔ MPUV Cargo）。開頭比對只用在
    沒被任何網格完全對到的載具，同一艘載具符合好幾個網格時給名稱最長（最具體）的那個。
    """
    db = get_db()
    vehicles = list(db['vehicle_master'].find({'is_current': {'$ne': False}},
                                              {'name': 1, 'game_name': 1, 'manufacturer_name': 1,
                                               'manufacturer_code': 1}))
    keys = {v['_id']: _vehicle_keys(v) for v in vehicles}
    by_id = {v['_id']: v for v in vehicles}
    index: dict = {}
    for v in vehicles:
        for k in keys[v['_id']]:
            index.setdefault(k, []).append(v)
    rows = list(db[COLLECTION].find({}, {'name': 1, 'manufacturer': 1, 'alternative_names': 1, 'vehicle_uuids': 1}))
    hits_of: dict = {}
    for row in rows:
        hits = {}
        for k in _grid_keys(row):
            for v in index.get(k, []):
                hits[v['_id']] = v.get('name')
        hits_of[row['_id']] = hits
    # 開頭比對：完全對不到的網格 × 沒被完全對到的載具
    claimed = {vid for hits in hits_of.values() for vid in hits}
    best: dict = {}   # 載具 → (比對到的名稱長度, 網格 _id)
    for row in rows:
        if hits_of[row['_id']]:
            continue
        for gk in _grid_keys(row):
            if len(gk) < PREFIX_MIN:
                continue
            for vid, vks in keys.items():
                if vid in claimed or not any(k.startswith(gk) and k != gk for k in vks):
                    continue
                if vid not in best or best[vid][0] < len(gk):
                    best[vid] = (len(gk), row['_id'])
    for vid, (_, gid) in best.items():
        hits_of[gid][vid] = by_id[vid].get('name')
    ops = []
    for row in rows:
        hits = hits_of[row['_id']]
        uuids = sorted(hits)
        if uuids != (row.get('vehicle_uuids') or []):
            ops.append(UpdateOne({'_id': row['_id']}, {'$set': {
                'vehicle_uuids': uuids, 'vehicle_names': [hits[u] for u in uuids],
                'vehicle_uuid': uuids[0] if uuids else None}}))
    if ops:
        db[COLLECTION].bulk_write(ops, ordered=False)
    return len(ops)
