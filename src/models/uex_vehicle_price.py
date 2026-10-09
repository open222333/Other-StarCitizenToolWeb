"""UEX 的載具遊戲內購買價／租船價，對應到載具主檔 vehicle_master。

資料由「資料同步排程」的 UEX 項目同步（需要 UEX token）：
  - uex_vehicles：UEX /vehicles（UEX 自己的載具 id、uuid、名稱）
  - uex_vehicles_purchases：UEX /vehicles_purchases_prices_all，一筆＝「某載具 × 某終端」的
    遊戲內購買價 price_buy（aUEC），_id 是 `id_vehicle:id_terminal`
  - uex_vehicles_rentals：UEX /vehicles_rentals_prices_all，一筆＝「某載具 × 某終端」的租船價 price_rent

價格列只有 UEX 的 id_vehicle，要先對到 vehicle_master._id（遊戲 uuid）：
  1. uex_vehicles.uuid 直接等於 vehicle_master._id
  2. 對不到才用名稱比：UEX 的 name／name_full 跟主檔的 name、game_name、「廠商名 + name」比（不分大小寫）
價格是玩家回報到 UEX 的，新舊不一，畫面上要附 date_modified。

官網現金價（美金）不在這裡，是 vehicle_master.msrp（Wiki API）。
"""

import re
from typing import Optional

from src.mongo import get_db
from src.models.uex_commodity_price import TERMINALS, _id_variants, _num, terminal_summary

VEHICLES = 'uex_vehicles'
PURCHASES = 'uex_vehicles_purchases'
RENTALS = 'uex_vehicles_rentals'

#: kind → (collection, 價格欄位)
KINDS = {
    'purchase': (PURCHASES, 'price_buy'),
    'rental': (RENTALS, 'price_rent'),
}
MAX_ADMIN_LIMIT = 200


def _norm(text) -> str:
    return re.sub(r'\s+', ' ', text).strip().lower() if isinstance(text, str) else ''


def vehicle_links() -> dict:
    """{UEX 載具 id（字串）: vehicle_master._id}；對不到的不列。"""
    db = get_db()
    master_ids = set()
    by_name: dict = {}
    for m in db['vehicle_master'].find({}, {'name': 1, 'game_name': 1, 'manufacturer_name': 1}):
        master_ids.add(m['_id'])
        names = [m.get('name'), m.get('game_name')]
        if m.get('manufacturer_name') and m.get('name'):
            names.append(f"{m['manufacturer_name']} {m['name']}")
        for n in names:
            if _norm(n):
                by_name.setdefault(_norm(n), m['_id'])
    out = {}
    for u in db[VEHICLES].find({}, {'id': 1, 'uuid': 1, 'name': 1, 'name_full': 1}):
        uex_id = str(u.get('id', u['_id']))
        if u.get('uuid') in master_ids:
            out[uex_id] = u['uuid']
            continue
        for n in (u.get('name_full'), u.get('name')):
            hit = by_name.get(_norm(n))
            if hit:
                out[uex_id] = hit
                break
    return out


def _uex_ids_by_vehicle(links: dict) -> dict:
    inv: dict = {}
    for uex_id, uuid in links.items():
        inv.setdefault(uuid, []).append(uex_id)
    return inv


def summary_map(vehicle_uuids=None) -> dict:
    """{vehicle_uuid: {buy_min, buy_count, rent_min, rent_count}}，只列有價格的載具。

    vehicle_uuids 給了就只算這些（列表頁一頁 50 筆用）。
    """
    links = vehicle_links()
    wanted = set(vehicle_uuids) if vehicle_uuids is not None else None
    if wanted is not None:
        links = {k: v for k, v in links.items() if v in wanted}
    if not links:
        return {}
    variants = [v for uex_id in links for v in _id_variants(uex_id)]
    out: dict = {}
    for kind, (collection, field) in KINDS.items():
        short = 'buy' if kind == 'purchase' else 'rent'
        for row in get_db()[collection].find({'id_vehicle': {'$in': variants}, field: {'$gt': 0}},
                                             {'id_vehicle': 1, field: 1}):
            uuid = links.get(str(row.get('id_vehicle')))
            price = _num(row.get(field))
            if not uuid or not price:
                continue
            s = out.setdefault(uuid, {'buy_min': None, 'buy_count': 0, 'rent_min': None, 'rent_count': 0})
            s[f'{short}_count'] += 1
            if s[f'{short}_min'] is None or price < s[f'{short}_min']:
                s[f'{short}_min'] = price
    return out


#: 「取得方式」篩選的值 → summary_map 裡要有值的欄位
ACQUIRE_FIELDS = {'buy': 'buy_min', 'rent': 'rent_min'}


def vehicle_ids_with(acquire) -> set:
    """「只看可用遊戲幣購買／可租船」：有對應價格的 vehicle uuid。

    acquire：'buy'／'rent' 的清單，多選取聯集（同站其他多選篩選的規則）；不認得的值忽略。
    """
    fields = [ACQUIRE_FIELDS[a] for a in (acquire or []) if a in ACQUIRE_FIELDS]
    if not fields:
        return set()
    return {uuid for uuid, s in summary_map().items() if any(s.get(f) for f in fields)}


def attach_summaries(rows: list, key: str = '_id', target: Optional[str] = None) -> list:
    """把 summary_map 的結果掛到每一列的 `uex_price`（沒有價格就是 None）。

    key：列裡放 vehicle uuid 的欄位；target：要掛在列裡哪個子 dict（例如艦隊列的 'vehicle'）。
    """
    uuids = [r.get(key) for r in rows if r.get(key)]
    summaries = summary_map(uuids) if uuids else {}
    for r in rows:
        holder = r.get(target) if target else r
        if isinstance(holder, dict):
            holder['uex_price'] = summaries.get(r.get(key))
    return rows


def prices_for(vehicle_uuid: str) -> dict:
    """某載具的遊戲內購買／租船地點：{purchase: [...], rental: [...]}，各自依價格由低到高。"""
    inv = _uex_ids_by_vehicle(vehicle_links())
    uex_ids = inv.get(vehicle_uuid) or []
    out = {'purchase': [], 'rental': []}
    if not uex_ids:
        return out
    variants = [v for i in uex_ids for v in _id_variants(i)]
    for kind, (collection, field) in KINDS.items():
        rows = [r for r in get_db()[collection].find({'id_vehicle': {'$in': variants}, field: {'$gt': 0}})
                if r.get('id_terminal') not in (None, '')]
        terminals = {str(t.get('id', t['_id'])): t for t in get_db()[TERMINALS].find(
            {'_id': {'$in': list({str(r['id_terminal']) for r in rows})}})}
        items = [{
            'terminal': terminal_summary(terminals.get(str(r['id_terminal'])), r),
            'price': _num(r.get(field)),
            'date_modified': r.get('date_modified'),
        } for r in rows]
        out[kind] = sorted(items, key=lambda x: (x['price'] or 0, x['terminal']['name'] or ''))
    return out


def admin_list(kind: str, *, q: str = '', star_system: str = '', limit: int = 50, offset: int = 0) -> tuple:
    """後台「艦船 › 購買價格／租船價格」：價格表原始內容（分頁），附對應到的載具主檔。"""
    if kind not in KINDS:
        raise ValueError('kind 只能是 purchase 或 rental')
    collection, field = KINDS[kind]
    db = get_db()
    limit = max(1, min(int(limit or 50), MAX_ADMIN_LIMIT))
    offset = max(0, int(offset or 0))
    conds = []
    if star_system:
        tids = [v for t in db[TERMINALS].find({'star_system_name': star_system}, {'id': 1})
                for v in _id_variants(str(t.get('id', t['_id'])))]
        conds.append({'$or': [{'star_system_name': star_system}, {'id_terminal': {'$in': tids}}]})
    q = (q or '').strip()
    if q:
        rx = re.compile(re.escape(q), re.IGNORECASE)
        vids = [v for u in db[VEHICLES].find({'$or': [{'name': rx}, {'name_full': rx}]}, {'id': 1})
                for v in _id_variants(str(u.get('id', u['_id'])))]
        tids = [v for t in db[TERMINALS].find(
            {'$or': [{'name': rx}, {'nickname': rx}, {'displayname': rx}, {'code': rx}]}, {'id': 1})
            for v in _id_variants(str(t.get('id', t['_id'])))]
        conds.append({'$or': [{'vehicle_name': rx}, {'terminal_name': rx},
                              {'id_vehicle': {'$in': vids}}, {'id_terminal': {'$in': tids}}]})
    filt = {'$and': conds} if conds else {}
    total = db[collection].count_documents(filt)
    docs = list(db[collection].find(filt).sort([('vehicle_name', 1), (field, 1), ('_id', 1)])
                .skip(offset).limit(limit))

    links = vehicle_links()
    uex = {str(u.get('id', u['_id'])): u for u in db[VEHICLES].find(
        {'_id': {'$in': list({str(d.get('id_vehicle')) for d in docs})}}, {'id': 1, 'name': 1, 'name_full': 1})}
    masters = {m['_id']: m for m in db['vehicle_master'].find(
        {'_id': {'$in': list({links[str(d.get('id_vehicle'))] for d in docs if str(d.get('id_vehicle')) in links})}},
        {'name': 1})}
    terminals = {str(t.get('id', t['_id'])): t for t in db[TERMINALS].find(
        {'_id': {'$in': list({str(d.get('id_terminal')) for d in docs})}})}
    rows = []
    for d in docs:
        vid = str(d.get('id_vehicle'))
        u = uex.get(vid) or {}
        uuid = links.get(vid)
        rows.append({
            'id': str(d['_id']),
            'uex_vehicle': {'id': vid, 'name': u.get('name_full') or u.get('name') or d.get('vehicle_name') or ''},
            'vehicle': {'uuid': uuid, 'name': (masters.get(uuid) or {}).get('name')} if uuid else None,
            'terminal': terminal_summary(terminals.get(str(d.get('id_terminal'))), d),
            'price': _num(d.get(field)),
            'date_added': d.get('date_added'),
            'date_modified': d.get('date_modified'),
        })
    return rows, total
