"""借用船清單（ship_loaners）：RSI 官方 Loaner Ship Matrix 的每一列（抓取與解析見 src/rsi_loaners.py，
同步項目「借用船」，tasks/scdata_sync.py 的 _sync_loaners）。

每列一筆：
    {_id: 左欄正規化, ship: 左欄原文（例如「Hull D, E」）, names: [[展開的船名, 是否字首比對]…],
     loaners: [借用船英文名…], source_url, source_updated_at（文章最後更新）, is_current, _sync, first_seen_at}
清單裡拿掉的列標 is_current=False（不刪，留紀錄）。

概念船列表（src/models/ccu.py 的 concept_ships）用 for_ship() 對到借用船，
借用船再對到載具主檔（有 uuid、中文名就一起給）。
"""

from datetime import datetime

from src import rsi_loaners
from src.mongo import get_db

COLLECTION = 'ship_loaners'


def _col():
    return get_db()[COLLECTION]


def save(rows: list, run_id: str, stamp: datetime, source_updated_at=None, url: str = '') -> dict:
    col = _col()
    seen = written = 0
    for r in rows:
        key = rsi_loaners._norm(r['ship'])
        if not key:
            continue
        seen += 1
        doc = {'ship': r['ship'], 'names': [list(x) for x in rsi_loaners.parse_ship_names(r['ship'])],
               'loaners': r['loaners'], 'source_url': url or rsi_loaners.ARTICLE_URL,
               'source_updated_at': source_updated_at, 'is_current': True, '_sync': {'run_id': run_id, 'at': stamp}}
        res = col.update_one({'_id': key}, {'$set': doc, '$setOnInsert': {'first_seen_at': stamp}}, upsert=True)
        written += 1 if (res.upserted_id or res.modified_count) else 0
    retired = col.update_many({'_sync.run_id': {'$ne': run_id}, 'is_current': True},
                              {'$set': {'is_current': False, 'retired_at': stamp}}).modified_count
    return {'seen': seen, 'written': written, 'retired': retired}


def current_rows() -> list:
    return list(_col().find({'is_current': True}, {'_sync': 0}))


def for_ships(ships: list) -> dict:
    """[(key, 船名, 廠商)…] → {key: {ship（清單原文）, loaners: [{name, vehicle_uuid, name_zh}], source_url,
    source_updated_at}}；對不到的不放。一次讀清單、一次建載具索引。"""
    rows = current_rows()
    if not rows or not ships:
        return {}
    from src.models import ccu
    index = ccu._vehicle_index()
    out, uuids = {}, set()
    for key, name, mfr in ships:
        row = rsi_loaners.match_row(name, rows, mfr)
        if not row:
            continue
        loaners = []
        for ln in row.get('loaners') or []:
            uuid = ccu.match_vehicle(ln, '', index)
            loaners.append({'name': ln, 'vehicle_uuid': uuid})
            if uuid:
                uuids.add(uuid)
        out[key] = {'ship': row['ship'], 'loaners': loaners, 'source_url': row.get('source_url'),
                    'source_updated_at': row.get('source_updated_at')}
    zh = ccu._zh_names(uuids) if uuids else {}
    for v in out.values():
        for ln in v['loaners']:
            ln['name_zh'] = zh.get(ln['vehicle_uuid']) if ln['vehicle_uuid'] else None
    return out
