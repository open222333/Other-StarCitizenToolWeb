"""CCU 價格資料庫（RSI 官方商店的快照，抓取見 src/rsi_store.py，排程是同步項目「CCU」）。

兩個資料表：

rsi_ships（_id = RSI 商店的船 id）
    name, manufacturer, msrp（美金標準價）, focus, type, flyable_status, link,
    vehicle_uuid（對到載具主檔，對不到是 None）, is_current, retired_at,
    msrp_history: [{msrp, at}]   標準價變動時加一筆（第一次看到也算一筆）

ccu_offers（_id = 「種類:SKU id:船 id」，種類 ship＝單買的船、ccu＝升級）
    kind, sku_id, ship_rsi_id, ship_name, vehicle_uuid, from_rsi_id（ccu 才有：抓取時的起點船）,
    title, price（單買價／升級後價值）, msrp, savings（比標準價省多少）, upgrade_price（ccu：從起點船升上去的價差）,
    is_warbond, is_discount, insurance, stock（限量剩幾個，不限量 None）,
    first_seen_at, last_seen_at, is_current, ended_at,
    periods: [{start, end}]           每次「上架」一段；下架時補上 end，之後又出現就加新的一段
    price_history: [{price, at}]      價格變動時加一筆

RSI 商店只看得到「現在有賣的」，所以開始／結束日期是排程看到的時間（精度＝排程間隔）。
歷史資料抓不回來，備份在「CCU 價格紀錄」（src/backup.py）。
每筆都帶 source='rsi'、credibility='官方確認'。

ship_sale_history（_id = Open Hangar 的船名，同步項目「Open Hangar 歷史」，抓取見 src/openhangar.py）
    name, manufacturer, rsi_id（對到 rsi_ships，對不到 None）, vehicle_uuid, avail（出現頻率）,
    first_sold_at, on_sale, warbond_count, last_price, msrp,
    periods: [{start, end, price, msrp, sale_type, code}]   2021-11 起的每段上架（S 單買、W Warbond、U 未說明）
    source='openhangar', credibility='歷史紀錄'
    第三方整理的歷史，跟 rsi/ccu_offers 重疊的期間以 RSI 為準；授權 CC BY 4.0，顯示時要標註來源。
"""

from datetime import datetime

from pymongo import UpdateOne

from src.mongo import get_db

SHIPS = 'rsi_ships'
OFFERS = 'ccu_offers'
SALE_HISTORY = 'ship_sale_history'
#: price_history／msrp_history 最多留幾筆（太舊的丟掉）
HISTORY_MAX = 100


def offer_id(offer: dict) -> str:
    return f'{offer["kind"]}:{offer["sku_id"]}:{offer["ship_rsi_id"]}'


def _vehicle_index() -> dict:
    """載具主檔：小寫名稱 → uuid（只看現役的；同名取第一筆）。"""
    out = {}
    for v in get_db()['vehicle_master'].find({'is_current': {'$ne': False}}, {'name': 1}):
        name = str(v.get('name') or '').strip().lower()
        if name and name not in out:
            out[name] = v['_id']
    return out


def match_vehicle(name: str, manufacturer: str, index: dict):
    """RSI 的船名對到載具主檔：先比全名，再比「廠商＋船名」與去掉廠商字首的名稱。"""
    n = (name or '').strip().lower()
    m = (manufacturer or '').strip().lower()
    candidates = [n]
    if m:
        candidates.append(f'{m} {n}')
        if n.startswith(m + ' '):
            candidates.append(n[len(m) + 1:])
    for c in candidates:
        if c in index:
            return index[c]
    # 主檔名稱常帶廠商縮寫（例如「RSI Perseus」）：比對最後是船名的
    for key, uuid in index.items():
        if key.endswith(' ' + n):
            return uuid
    return None


def _push_capped(lst, item):
    lst = list(lst or []) + [item]
    return lst[-HISTORY_MAX:]


def save_ships(ships: list, run_id: str, stamp: datetime) -> dict:
    """寫入船（標準價變動記在 msrp_history），沒出現的標成下架。回傳 {seen, written, retired, linked}。"""
    col = get_db()[SHIPS]
    existing = {d['_id']: d for d in col.find({}, {'msrp': 1, 'msrp_history': 1})}
    index = _vehicle_index()
    ops, linked = [], 0
    for s in ships:
        old = existing.get(s['rsi_id']) or {}
        vehicle_uuid = match_vehicle(s['name'], s.get('manufacturer'), index)
        linked += 1 if vehicle_uuid else 0
        doc = {k: v for k, v in s.items() if k != 'rsi_id'}
        doc.update({'vehicle_uuid': vehicle_uuid, 'is_current': True, 'retired_at': None,
                    '_sync': {'run_id': run_id, 'at': stamp}})
        if s.get('msrp') is not None and (not old or old.get('msrp') != s['msrp']):
            doc['msrp_history'] = _push_capped(old.get('msrp_history'), {'msrp': s['msrp'], 'at': stamp})
        ops.append(UpdateOne({'_id': s['rsi_id']}, {'$set': doc, '$setOnInsert': {'first_seen_at': stamp}},
                             upsert=True))
    if ops:
        col.bulk_write(ops, ordered=False)
    retired = col.update_many({'_sync.run_id': {'$ne': run_id}, 'is_current': True},
                              {'$set': {'is_current': False, 'retired_at': stamp}}).modified_count
    return {'seen': len(ships), 'written': len(ops), 'retired': retired, 'linked': linked}


def save_offers(offers: list, ships: list, run_id: str, stamp: datetime) -> dict:
    """寫入目前有賣的 SKU：新上架（或下架後又出現）開一段 period，價格變動記 price_history；
    這次沒出現的標成下架（is_current False、ended_at、補上最後一段的 end）。"""
    col = get_db()[OFFERS]
    ship_by_id = {s['rsi_id']: s for s in ships}
    ships_col = {d['_id']: d.get('vehicle_uuid') for d in get_db()[SHIPS].find({}, {'vehicle_uuid': 1})}
    existing = {d['_id']: d for d in col.find({}, {'is_current': 1, 'periods': 1, 'price': 1, 'price_history': 1})}
    ops, opened = [], 0
    seen_ids = set()
    for o in offers:
        _id = offer_id(o)
        if _id in seen_ids:
            continue
        seen_ids.add(_id)
        old = existing.get(_id)
        ship = ship_by_id.get(o['ship_rsi_id']) or {}
        doc = dict(o)
        doc.update({'ship_name': ship.get('name') or '', 'vehicle_uuid': ships_col.get(o['ship_rsi_id']),
                    'last_seen_at': stamp, 'is_current': True, 'ended_at': None,
                    'source': 'rsi', 'credibility': '官方確認',
                    '_sync': {'run_id': run_id, 'at': stamp}})
        if o.get('from_rsi_id') is not None:
            doc['from_ship_name'] = (ship_by_id.get(o['from_rsi_id']) or {}).get('name') or ''
        if not old or not old.get('is_current'):
            doc['periods'] = _push_capped((old or {}).get('periods'), {'start': stamp, 'end': None})
            opened += 1
        if not old or old.get('price') != o.get('price'):
            doc['price_history'] = _push_capped((old or {}).get('price_history'), {'price': o.get('price'), 'at': stamp})
        ops.append(UpdateOne({'_id': _id}, {'$set': doc, '$setOnInsert': {'first_seen_at': stamp}}, upsert=True))
    if ops:
        col.bulk_write(ops, ordered=False)

    # 下架：這次沒看到、原本還在賣的
    ended = 0
    for d in col.find({'_id': {'$nin': list(seen_ids)}, 'is_current': True}, {'periods': 1, 'last_seen_at': 1}):
        periods = list(d.get('periods') or [])
        end = d.get('last_seen_at') or stamp
        if periods and periods[-1].get('end') is None:
            periods[-1] = {**periods[-1], 'end': end}
        col.update_one({'_id': d['_id']}, {'$set': {'is_current': False, 'ended_at': end, 'periods': periods}})
        ended += 1
    return {'seen': len(seen_ids), 'written': len(ops), 'opened': opened, 'ended': ended}


def save_sale_history(ships: list, run_id: str, stamp: datetime) -> dict:
    """Open Hangar 的整份歷史（每次都是完整的）：逐艘覆寫 periods。回傳 {seen, written, linked_rsi, linked_vehicle}。

    Open Hangar 這次沒列到的船不刪（保留上次的紀錄）。"""
    from src import openhangar
    col = get_db()[SALE_HISTORY]
    rsi_by_name = {}
    for d in get_db()[SHIPS].find({}, {'name': 1}):
        rsi_by_name.setdefault(str(d.get('name') or '').strip().lower(), d['_id'])
    index = _vehicle_index()
    ops, linked_rsi, linked_vehicle = [], 0, 0
    for s in ships:
        rsi_id = s.get('rsi_id')
        if rsi_id is None:
            rsi_id = rsi_by_name.get(s['name'].strip().lower())
        vehicle_uuid = match_vehicle(s['name'], s.get('manufacturer'), index)
        linked_rsi += rsi_id is not None
        linked_vehicle += vehicle_uuid is not None
        doc = {k: v for k, v in s.items() if k != 'rsi_id'}
        doc.update({'rsi_id': rsi_id, 'vehicle_uuid': vehicle_uuid,
                    'source': openhangar.SOURCE, 'credibility': openhangar.CREDIBILITY,
                    '_sync': {'run_id': run_id, 'at': stamp}})
        ops.append(UpdateOne({'_id': s['name']}, {'$set': doc, '$setOnInsert': {'first_imported_at': stamp}},
                             upsert=True))
    if ops:
        col.bulk_write(ops, ordered=False)
    return {'seen': len(ships), 'written': len(ops), 'linked_rsi': linked_rsi, 'linked_vehicle': linked_vehicle}
