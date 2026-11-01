"""飛船貨物網格（cargo_grid_master，sc-cargo.space 的資料，「貨物網格」同步項目，見 src/scdata.py 的 map_cargo_grid）。

sc-cargo.space 的船名跟遊戲／Wiki 的寫法不一定一樣（Hull-C ↔ Hull C、有沒有廠商前綴），
所以對應到載具主檔（vehicle_master）時把名稱只留英數字、轉小寫再比對，船名、廠商＋船名、
別名（alternativeNames）都試；對到的寫進 vehicle_uuids（同名變體可能好幾艘）。
"""

import re

from pymongo import UpdateOne

from src.mongo import get_db

COLLECTION = 'cargo_grid_master'


def _norm(text) -> str:
    return re.sub(r'[^a-z0-9]', '', str(text or '').lower())


def link_vehicles() -> int:
    """把每艘船的貨物網格對到載具主檔，寫 vehicle_uuids／vehicle_names，回傳有變動的筆數。"""
    db = get_db()
    index: dict = {}
    for v in db['vehicle_master'].find({'is_current': {'$ne': False}},
                                       {'name': 1, 'game_name': 1, 'manufacturer_name': 1, 'manufacturer_code': 1}):
        names = {v.get('name'), v.get('game_name')}
        for mfr in (v.get('manufacturer_name'), v.get('manufacturer_code')):
            if mfr and v.get('name'):
                names.add(f'{mfr} {v["name"]}')
            if mfr and v.get('game_name') and _norm(v['game_name']).startswith(_norm(mfr)):
                names.add(v['game_name'][len(mfr):])
        for n in names:
            if _norm(n):
                index.setdefault(_norm(n), []).append(v)
    ops = []
    for row in db[COLLECTION].find({}, {'name': 1, 'manufacturer': 1, 'alternative_names': 1,
                                        'vehicle_uuids': 1}):
        hits = {}
        for n in [row.get('name'), f'{row.get("manufacturer") or ""} {row.get("name") or ""}',
                  *(row.get('alternative_names') or [])]:
            for v in index.get(_norm(n), []):
                hits[v['_id']] = v.get('name')
        uuids = sorted(hits)
        if uuids != (row.get('vehicle_uuids') or []):
            ops.append(UpdateOne({'_id': row['_id']}, {'$set': {
                'vehicle_uuids': uuids, 'vehicle_names': [hits[u] for u in uuids],
                'vehicle_uuid': uuids[0] if uuids else None}}))
    if ops:
        db[COLLECTION].bulk_write(ops, ordered=False)
    return len(ops)
