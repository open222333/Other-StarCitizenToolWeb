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
    store_confirmed（單買：RSI 商店確認真的有在賣才是 True；沒有這個的不上時間軸）, store_only（商店有、升級工具沒列，
    sku_id 是商店的品項 id）, store_sku_id, store_url,
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
    第三方整理的歷史，只補「我們開始抓 RSI 商店之前」的期間（rsi_since()；之後一律以 RSI 官方商店為準，
    Open Hangar 在那之後的上架段不收、跨過那天的截到那天；實際比對過 Open Hangar 有標錯 Warbond、重複上架的情形）；
    授權 CC BY 4.0，顯示時要標註來源。
"""

import re
from datetime import datetime

from pymongo import UpdateOne

from src.mongo import get_db
from src.sync_version import LatestCache, run_ids
from src.textnorm import norm_ascii as _norm  # 船名比對的正規化（I1：共用一份）

SHIPS = 'rsi_ships'
OFFERS = 'ccu_offers'
SALE_HISTORY = 'ship_sale_history'
#: price_history／msrp_history 最多留幾筆（太舊的丟掉）
HISTORY_MAX = 100


def offer_id(offer: dict) -> str:
    # 商店補的（store_only）用商店的品項 id，跟升級工具的 SKU id 是不同的編號，加 s 前綴分開
    sku = f's{offer["sku_id"]}' if offer.get('store_only') else offer['sku_id']
    return f'{offer["kind"]}:{sku}:{offer["ship_rsi_id"]}'


def _vehicle_index() -> dict:
    """載具主檔：正規化名稱 → uuid（只看現役的；同名取第一筆）。

    名稱收 name、game_name（遊戲內全名，例如「Crusader M2 Hercules Starlifter」）、「廠商全名 + name」。"""
    out = {}
    for v in get_db()['vehicle_master'].find({'is_current': {'$ne': False}},
                                             {'name': 1, 'game_name': 1, 'manufacturer_name': 1}):
        names = [v.get('name'), v.get('game_name')]
        if v.get('manufacturer_name') and v.get('name'):
            names.append(f"{v['manufacturer_name']} {v['name']}")
        for n in names:
            key = _norm(n)
            if key and key not in out:
                out[key] = v['_id']
    return out


def match_vehicle(name: str, manufacturer: str, index: dict):
    """RSI／Open Hangar 的船名對到載具主檔。依序：
      1. 全名、「廠商＋船名」、去掉廠商字首的名稱（不分大小寫、忽略標點）
      2. 主檔名稱的結尾是這個船名（主檔常帶廠商縮寫，例如「RSI Perseus」）
      3. 主檔名稱以這個船名開頭、而且只有一艘（商店寫「M2 Hercules」、主檔是「M2 Hercules Starlifter」）
    """
    n = _norm(name)
    m = _norm(manufacturer)
    if not n:
        return None
    candidates = [n]
    if m:
        candidates.append(f'{m} {n}')
        if n.startswith(m + ' '):
            candidates.append(n[len(m) + 1:])
    for c in candidates:
        if c in index:
            return index[c]
    for c in candidates:
        for key, uuid in index.items():
            if key.endswith(' ' + c):
                return uuid
    for c in candidates:
        hits = {uuid for key, uuid in index.items() if key.startswith(c + ' ')}
        if len(hits) == 1:
            return hits.pop()
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


# ── 玩家頁「資料庫 › 船價」：RSI 商店（官方）＋ Open Hangar（歷史）合起來看 ─────────

def _zh_names(uuids) -> dict:
    """載具 uuid → 中文名稱（查不到的不列）。"""
    from src.sc_zh import vehicle_name_zh
    out = {}
    ids = [u for u in set(uuids) if u]
    if not ids:
        return out
    for v in get_db()['vehicle_master'].find({'_id': {'$in': ids}}, {'class_name': 1, 'name': 1, 'game_name': 1}):
        zh = vehicle_name_zh(v.get('class_name') or '', v.get('name') or '', game_name=v.get('game_name') or '')
        if zh and zh != v.get('name'):
            out[v['_id']] = zh
    return out


def _overlaps(a_start, a_end, b_start, b_end, now) -> bool:
    return a_start <= (b_end or now) and b_start <= (a_end or now)


def _rsi_periods(offers: list) -> list:
    """RSI 的單買 SKU → 時間軸上的段（每段帶當時最後看到的價格）。
    只收商店確認過有在賣的（store_confirmed，見 src/rsi_store.py 的 confirm_ship_offers）：升級工具一直列著、
    商店早就沒賣的 Warbond（例如 M2 WB $480，從我們第一次抓的 2026-11-14 掛到現在）不算上架，不上時間軸。
    商店確認上線（2026-11-27）之前就結束的 SKU 沒有這個欄位，真假無法回頭判斷，一律不上時間軸（刻意的，不補舊資料）。"""
    out = []
    for o in offers:
        if o.get('kind') != 'ship' or not o.get('store_confirmed'):
            continue
        for p in o.get('periods') or []:
            if not p.get('start'):
                continue
            out.append({'start': p['start'], 'end': p.get('end'), 'price': o.get('price'), 'msrp': o.get('msrp'),
                        'sale_type': 'warbond' if o.get('is_warbond') else 'standard',
                        'source': 'rsi', 'credibility': '官方確認', 'title': o.get('title') or '',
                        'insurance': o.get('insurance')})
    return out


def rsi_since():
    """我們開始抓 RSI 商店的時間（ccu_offers 最早的 first_seen_at）；還沒抓過回 None。"""
    doc = get_db()[OFFERS].find_one({'first_seen_at': {'$ne': None}}, {'first_seen_at': 1}, sort=[('first_seen_at', 1)])
    return (doc or {}).get('first_seen_at')


def _merged_periods(history: dict, offers: list, now: datetime, since=None) -> list:
    """一艘船的上架段：RSI 的全收；Open Hangar 的只收 since（開始抓 RSI 的時間）之前的部分——
    開始時間在 since 之後的不收，跨過 since 的結束時間截到 since；跟同種類的 RSI 段重疊的也不收。新的在前。"""
    rsi = _rsi_periods(offers)
    out = list(rsi)
    for p in (history or {}).get('periods') or []:
        start, end = p['start'], p.get('end')
        if since is not None:
            if start >= since:
                continue
            if end is None or end > since:
                end = since
        if any(r['sale_type'] == p.get('sale_type') and _overlaps(start, end, r['start'], r['end'], now)
               for r in rsi):
            continue
        out.append({'start': start, 'end': end, 'price': p.get('price'), 'msrp': p.get('msrp'),
                    'sale_type': p.get('sale_type'), 'source': 'openhangar', 'credibility': '歷史紀錄'})
    out.sort(key=lambda p: p['start'], reverse=True)
    return out


def _price_row(key: str, history: dict, ship: dict, offers: list, now: datetime, since=None) -> dict:
    periods = _merged_periods(history, offers, now, since)
    wb = [p for p in periods if p['sale_type'] == 'warbond']
    open_now = [p for p in periods if p['end'] is None]
    history = history or {}
    ship = ship or {}
    return {
        'key': key,
        'name': history.get('name') or ship.get('name') or '',
        'manufacturer': ship.get('manufacturer') or history.get('manufacturer'),
        'vehicle_uuid': ship.get('vehicle_uuid') or history.get('vehicle_uuid'),
        'msrp': ship.get('msrp') if ship.get('msrp') is not None else history.get('msrp'),
        'msrp_source': 'rsi' if ship.get('msrp') is not None else ('openhangar' if history.get('msrp') is not None else None),
        'avail': history.get('avail'),
        'first_sold_at': history.get('first_sold_at'),
        'on_sale': bool(open_now),
        'warbond_now': any(p['sale_type'] == 'warbond' for p in open_now),
        'price_now': min((p['price'] for p in open_now if p['price'] is not None), default=None),
        'last_warbond': ({'price': wb[0]['price'], 'start': wb[0]['start'], 'end': wb[0]['end']} if wb else None),
        'warbond_count': len(wb),
        'period_count': len(periods),
        'link': ship.get('link'),
        '_periods': periods,
    }


def _price_rows(history_filter=None, ship_filter=None, offer_filter=None) -> list:
    """history_filter 為 None＝全部船（列表）；給了就只組那幾艘（明細，連 RSI 船、SKU 也只查那幾艘）。"""
    db = get_db()
    now = datetime.utcnow()
    histories = list(db[SALE_HISTORY].find(history_filter or {}, {'_sync': 0}))
    ships = {d['_id']: d for d in db[SHIPS].find(ship_filter or {}, {'msrp_history': 0, '_sync': 0})}
    offers_by_ship = {}
    for o in db[OFFERS].find({'kind': 'ship', **(offer_filter or {})}, {'price_history': 0, '_sync': 0}):
        offers_by_ship.setdefault(o.get('ship_rsi_id'), []).append(o)
    rows, used = [], set()
    index = None
    since = rsi_since()
    for h in histories:
        rid = h.get('rsi_id')
        used.add(rid)
        rows.append(_price_row(h['_id'], h, ships.get(rid), offers_by_ship.get(rid) or [], now, since))
    if history_filter is None:
        # RSI 有、Open Hangar 沒有紀錄的船（例如從沒單賣過）
        for rid, s in ships.items():
            if rid not in used and s.get('is_current', True):
                rows.append(_price_row(f'rsi:{rid}', None, s, offers_by_ship.get(rid) or [], now, since))
    # 同步當下對不到載具的（例如載具主檔比商店資料晚同步、或之後比對規則改進了），讀取時再對一次
    for r in rows:
        if not r['vehicle_uuid'] and r['name']:
            index = index if index is not None else _vehicle_index()
            r['vehicle_uuid'] = match_vehicle(r['name'], r.get('manufacturer'), index)
    zh = _zh_names(r['vehicle_uuid'] for r in rows)
    for r in rows:
        r['name_zh'] = zh.get(r['vehicle_uuid'])
    return rows


#: 列表快取：資料只在「CCU」「Open Hangar 歷史」「艦船」三個同步項目跑完時才會變（艦船影響船名比對與中文名），
#: 用這三項最後一次的 run_id 當版本；版本沒變就直接回上次組好的（每個 gunicorn worker 各一份，見待辦 A2）
PRICE_LIST_JOBS = ('ccu', 'openhangar', 'vehicles')


def price_list_version() -> str:
    """三個同步項目最後的 run_id 串起來（ETag 也用這個）。"""
    return run_ids(*PRICE_LIST_JOBS)


def _price_list_rows() -> list:
    rows = _price_rows()
    for r in rows:
        r.pop('_periods')
    rows.sort(key=lambda r: (r['name'] or '').lower())
    return rows


_list_cache = LatestCache(_price_list_rows)


def ship_price_list() -> list:
    """每艘船一列（不含各段明細）。同一個版本（price_list_version）只組一次。"""
    return _list_cache.get(price_list_version())


def ship_price_detail(key: str):
    """一艘船的上架段明細（新的在前）；找不到回 None。"""
    key = str(key or '')
    if key.startswith('rsi:'):
        try:
            rid = int(key[4:])
        except ValueError:
            return None
        ship = get_db()[SHIPS].find_one({'_id': rid}, {'msrp_history': 0, '_sync': 0})
        if not ship:
            return None
        offers = list(get_db()[OFFERS].find({'kind': 'ship', 'ship_rsi_id': rid}, {'price_history': 0, '_sync': 0}))
        row = _price_row(key, None, ship, offers, datetime.utcnow())
    else:
        # 只查這一艘：先拿歷史那筆的 rsi_id，RSI 船與單買 SKU 也只查它（不要把整張表讀回來，待辦 A1）
        hist = get_db()[SALE_HISTORY].find_one({'_id': key}, {'rsi_id': 1})
        if not hist:
            return None
        rid = hist.get('rsi_id')
        rows = _price_rows({'_id': key}, {'_id': rid}, {'ship_rsi_id': rid})
        if not rows:
            return None
        row = rows[0]
    row['periods'] = row.pop('_periods')
    if 'name_zh' not in row:   # rsi: 路徑沒經過 _price_rows（待辦 A3：history 路徑已經查過中文，不再查一次）
        row['name_zh'] = _zh_names([row['vehicle_uuid']]).get(row['vehicle_uuid'])
    return row


# ── 資料庫 › 艦船：RSI 商店裡還沒做進遊戲的船（概念、製作中）───────────────
# 艦船列表的資料（vehicle_master）來自遊戲檔案，概念船沒有遊戲內的實體所以不會出現；
# 這裡從 RSI 商店（rsi_ships）補：還不能飛、而且對不到載具主檔的船。只有美金價與上架紀錄，沒有遊戲內數值。

#: RSI 的 flyableStatus（正規化成只留小寫字母）→ 狀態
CONCEPT_STATUSES = {'inconcept': 'concept', 'concept': 'concept', 'inproduction': 'production', 'production': 'production'}


def concept_status(flyable_status) -> str:
    """'In Concept'／'in-concept' → concept；'In Production' → production；可以飛或不明 → ''。"""
    return CONCEPT_STATUSES.get(re.sub(r'[^a-z]', '', str(flyable_status or '').lower()), '')


#: 概念船清單快取：只留最新一份（key＝船價同步版本＋借用船同步＋翻譯版本），同 _list_cache 的做法
_concept_cache = LatestCache(lambda: _concept_ships())


def concept_ships() -> list:
    """同 _concept_ships()，結果快取一份；船價、借用船同步或翻譯版本變了才重算。
    沒有任何同步紀錄（例如測試）時不快取。艦船列表每次請求都會用到（待辦 E2）。"""
    from src.models import translation as T
    version = price_list_version()
    if not version.strip('|'):
        return _concept_ships()
    return _concept_cache.get((version, run_ids('loaners'), T.cache_version()))


def _concept_ships() -> list:
    """概念／製作中的船：[{_id: 'rsi:<id>', name, name_zh, manufacturer_name, manufacturer_code, msrp, role, role_zh,
    vehicle_type, is_concept, concept_status, price_key（船價明細用，見 ship_price_detail）, link,
    loaner（RSI 借用船清單對到的那一列，見 src/models/ship_loaner.py；對不到是 None）}]，依名稱排。"""
    db = get_db()
    hist = {h['rsi_id']: h['_id'] for h in db[SALE_HISTORY].find({'rsi_id': {'$ne': None}}, {'rsi_id': 1})}
    codes = {}
    for v in db['vehicle_master'].find({'manufacturer_name': {'$ne': None}}, {'manufacturer_name': 1, 'manufacturer_code': 1}):
        codes.setdefault(_norm(v.get('manufacturer_name')), v.get('manufacturer_code'))
    rows = []
    for s in db[SHIPS].find({'is_current': {'$ne': False}}, {'msrp_history': 0, '_sync': 0}):
        status = concept_status(s.get('flyable_status'))
        if not status or s.get('vehicle_uuid'):
            continue
        rows.append({'_id': f"rsi:{s['_id']}", 'name': s.get('name') or '', 'manufacturer_name': s.get('manufacturer'),
                     'manufacturer_code': codes.get(_norm(s.get('manufacturer'))), 'msrp': s.get('msrp'),
                     'role': s.get('focus'), 'vehicle_type': 'ship', 'is_concept': True, 'concept_status': status,
                     'price_key': hist.get(s['_id']) or f"rsi:{s['_id']}", 'link': s.get('link')})
    _attach_concept_zh(rows)
    from src.models import ship_loaner
    loaners = ship_loaner.for_ships([(r['_id'], r['name'], r.get('manufacturer_name')) for r in rows])
    for r in rows:
        r['loaner'] = loaners.get(r['_id'])
    rows.sort(key=lambda r: r['name'].lower())
    return rows


def _attach_concept_zh(rows: list) -> None:
    """概念船的中文（遊戲資料沒有這些船，用英文名反查翻譯）：船名試「名稱」「廠商第一個字＋名稱」「廠商全名＋名稱」
    （RSI 商店的名稱常少了廠商前綴，翻譯包是遊戲內全名），查不到就沒有 name_zh；角色用 RSI 的 focus 查。
    翻譯包也沒有的，可以在 src/data/sc_translation_manual.json 的 vehicle 加人工條目（id＝英文船名）。"""
    from src.sc_zh import vehicle_name_zh, vehicle_role_zh
    for r in rows:
        name, mfr = r.get('name') or '', (r.get('manufacturer_name') or '').strip()
        tries = [name] + ([f'{mfr.split()[0]} {name}', f'{mfr} {name}'] if mfr else [])
        r['name_zh'] = next((zh for t in tries if (zh := vehicle_name_zh(name=t))), None)
        r['role_zh'] = vehicle_role_zh(r.get('role')) if r.get('role') else None
