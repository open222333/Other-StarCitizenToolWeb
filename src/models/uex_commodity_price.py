"""UEX 商品在各交易終端的買賣價（`uex_commodities_prices`）與交易終端（`uex_terminals`）。

資料由「資料同步排程」的 UEX 項目同步（需要 UEX token）：
  - uex_commodities_prices：UEX /commodities_prices_all，一筆＝「某商品 × 某終端」，
    _id 是 `id_commodity:id_terminal`。price_buy＝在這個終端**買進**的價格（> 0 才代表買得到），
    price_sell＝賣給這個終端的價格；scu_buy／status_buy 是終端的庫存量／庫存狀態。
    價格是玩家回報的，新舊不一，畫面上要附 date_modified。
  - uex_terminals：UEX /terminals，終端名稱與所在星系、星球、太空站…。
  - uex_commodities：商品縮寫與名稱（見 src/models/uex_commodity.py）。

UEX 欄位直接整筆存（同步時 dict(row)），這裡讀的時候欄位缺了就當 None，
不假設 UEX 一定有哪個欄位——上游加減欄位不會讓這裡壞掉。
價格列本身通常就帶 commodity_name／terminal_name／star_system_name 等名稱，
沒帶的話用 id 回頭查 uex_commodities／uex_terminals 補。

中文：這裡只回英文，前端用 utils/translations.js（資料庫 sc_translations）翻。
"""

import re
from typing import Optional

from src.mongo import get_db
from src.models.uex_commodity import COLLECTION as COMMODITIES

PRICES = 'uex_commodities_prices'
TERMINALS = 'uex_terminals'

#: 玩家頁一次最多勾幾種商品（查「同時買得到」的地點）
MAX_SELECTED = 20
#: 後台價格列表一頁最多幾筆
MAX_ADMIN_LIMIT = 200

#: 地點路徑用到的欄位（由大到小；重複的名稱只留一次，例如 orbit 跟 planet 常常同名）
_LOC_FIELDS = ('star_system_name', 'planet_name', 'orbit_name', 'moon_name',
               'space_station_name', 'city_name', 'outpost_name', 'poi_name')

#: 後台「商品價格」列出的 UEX 原始欄位
PRICE_FIELDS = ('price_buy', 'price_buy_min', 'price_buy_max', 'price_buy_avg', 'scu_buy', 'scu_buy_avg',
                'status_buy', 'price_sell', 'price_sell_min', 'price_sell_max', 'price_sell_avg',
                'scu_sell', 'scu_sell_stock', 'scu_sell_avg', 'status_sell', 'container_sizes',
                'date_added', 'date_modified')

#: 後台「交易終端」列出的 UEX 原始欄位
TERMINAL_FIELDS = ('id', 'name', 'nickname', 'displayname', 'code', 'type', 'faction_name', 'company_name',
                   'max_container_size', 'is_available', 'is_available_live', 'is_visible', 'is_player_owned',
                   'is_refinery', 'is_cargo_center', 'is_habitation', 'has_loading_dock', 'has_docking_port',
                   'has_freight_elevator', 'is_auto_load', 'date_added', 'date_modified') + _LOC_FIELDS


def _num(value) -> Optional[float]:
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive(value) -> bool:
    n = _num(value)
    return n is not None and n > 0


def _id_variants(value) -> list:
    """UEX 的 id 是數字，但前端／URL 傳進來是字串；兩種都比對。"""
    text = str(value).strip()
    out = [text]
    if re.fullmatch(r'-?\d+', text):
        out.append(int(text))
    return out


def _clean_ids(values) -> list:
    out = []
    for v in values or []:
        text = str(v).strip()
        if text and text not in out:
            out.append(text)
    return out


def _doc_id(doc: dict, field: str = 'id') -> str:
    return str(doc.get(field, doc.get('_id')))


def location_path(*sources) -> list:
    """地點路徑（星系 › 星球 › 衛星 › 太空站／城市／前哨站），依序從各個來源取第一個有值的。"""
    path = []
    for field in _LOC_FIELDS:
        value = next((s.get(field) for s in sources if s and s.get(field)), None)
        if value and value not in path:
            path.append(value)
    return path


def terminal_summary(terminal: Optional[dict], price_row: Optional[dict] = None) -> dict:
    """終端摘要；terminal 是 uex_terminals 的文件，沒有的話用價格列帶的名稱補。"""
    t = terminal or {}
    p = price_row or {}
    name = (t.get('displayname') or t.get('nickname') or t.get('name')
            or p.get('terminal_name') or p.get('terminal_code') or '')
    return {
        'id': str(t.get('id', p.get('id_terminal', t.get('_id')))),
        'name': name,
        'code': t.get('code') or p.get('terminal_code') or None,
        'type': t.get('type') or None,
        'star_system': t.get('star_system_name') or p.get('star_system_name') or None,
        'location': location_path(t, p),
        'faction': t.get('faction_name') or p.get('faction_name') or None,
        'max_container_size': t.get('max_container_size'),
        'is_player_owned': bool(t.get('is_player_owned') or p.get('terminal_is_player_owned')),
    }


def _commodity_map(ids=None) -> dict:
    filt = {'_id': {'$in': [str(i) for i in ids]}} if ids is not None else {}
    fields = {'id': 1, 'code': 1, 'name': 1, 'kind': 1, 'is_illegal': 1, 'is_raw': 1}
    return {_doc_id(c): c for c in get_db()[COMMODITIES].find(filt, fields)}


def _terminal_map(ids=None) -> dict:
    filt = {'_id': {'$in': [str(i) for i in ids]}} if ids is not None else {}
    return {_doc_id(t): t for t in get_db()[TERMINALS].find(filt)}


def _commodity_summary(cid: str, commodity: Optional[dict], price_row: Optional[dict] = None) -> dict:
    c = commodity or {}
    p = price_row or {}
    return {
        'id': cid,
        'code': c.get('code') or p.get('commodity_code') or None,
        'name': c.get('name') or p.get('commodity_name') or '',
        'kind': c.get('kind') or None,
        'is_illegal': bool(c.get('is_illegal')),
    }


def _newer(a: dict, b: dict) -> dict:
    """同一個「商品 × 終端」重複時取較新的那筆（理論上 _id 已經保證唯一，這裡只是防呆）。"""
    return a if (_num(a.get('date_modified')) or 0) >= (_num(b.get('date_modified')) or 0) else b


class UexCommodityPrice:

    # ── 玩家頁「查詢 › 商品購買地點」 ──────────────────────────────

    @staticmethod
    def buyable_commodities() -> list:
        """至少在一個終端買得到（price_buy > 0）的商品，附可購買的終端數，依名稱排序。"""
        counts: dict = {}
        sample: dict = {}
        for row in get_db()[PRICES].find(
                {'price_buy': {'$gt': 0}},
                {'id_commodity': 1, 'id_terminal': 1, 'commodity_name': 1, 'commodity_code': 1}):
            if row.get('id_commodity') in (None, ''):
                continue
            cid = str(row['id_commodity'])
            counts.setdefault(cid, set()).add(str(row.get('id_terminal')))
            sample.setdefault(cid, row)
        commodities = _commodity_map(list(counts))
        out = [{**_commodity_summary(cid, commodities.get(cid), sample[cid]), 'terminal_count': len(tids)}
               for cid, tids in counts.items()]
        return sorted(out, key=lambda r: ((r['name'] or '').lower(), r['code'] or ''))

    @staticmethod
    def buy_locations(commodity_ids, star_systems=None) -> dict:
        """勾選的商品「全部」都買得到的終端。

        回傳 {locations: [{terminal, items: [...]}], commodities: [{…, terminal_count}]}；
        commodities 是每種商品各自買得到的終端數（結果是空的時候看得出是哪一種卡住）。
        商品超過 MAX_SELECTED 種丟 ValueError。
        """
        ids = _clean_ids(commodity_ids)
        if not ids:
            return {'locations': [], 'commodities': []}
        if len(ids) > MAX_SELECTED:
            raise ValueError(f'一次最多選 {MAX_SELECTED} 種商品')
        systems = {s for s in (star_systems or []) if s}

        variants = [v for i in ids for v in _id_variants(i)]
        by_terminal: dict = {}
        for row in get_db()[PRICES].find({'id_commodity': {'$in': variants}, 'price_buy': {'$gt': 0}}):
            if row.get('id_terminal') in (None, ''):
                continue
            tid, cid = str(row['id_terminal']), str(row['id_commodity'])
            slot = by_terminal.setdefault(tid, {})
            slot[cid] = _newer(row, slot[cid]) if cid in slot else row

        commodities = _commodity_map(ids)
        first_row = {}
        for tid, rows in by_terminal.items():
            for cid, row in rows.items():
                first_row.setdefault(cid, row)
        summary = [{**_commodity_summary(cid, commodities.get(cid), first_row.get(cid)),
                    'terminal_count': sum(1 for rows in by_terminal.values() if cid in rows)}
                   for cid in ids]

        need = set(ids)
        hits = {tid: rows for tid, rows in by_terminal.items() if need <= set(rows)}
        terminals = _terminal_map(list(hits))
        locations = []
        for tid, rows in hits.items():
            any_row = rows[ids[0]]
            term = terminal_summary(terminals.get(tid), any_row)
            if systems and term['star_system'] not in systems:
                continue
            items = []
            for cid in ids:
                row = rows[cid]
                items.append({
                    **_commodity_summary(cid, commodities.get(cid), row),
                    'price_buy': _num(row.get('price_buy')),
                    'price_buy_avg': _num(row.get('price_buy_avg')),
                    'scu_buy': _num(row.get('scu_buy')),
                    'status_buy': row.get('status_buy'),
                    'date_modified': row.get('date_modified'),
                })
            locations.append({'terminal': term, 'items': items})
        locations.sort(key=lambda r: ([(x or '').lower() for x in r['terminal']['location']],
                                      (r['terminal']['name'] or '').lower()))
        return {'locations': locations, 'commodities': summary}

    @staticmethod
    def star_systems() -> list:
        """有交易終端的星系（給篩選選單）。"""
        names = {t.get('star_system_name') for t in get_db()[TERMINALS].find({}, {'star_system_name': 1})}
        if not names - {None, ''}:
            names = set(get_db()[PRICES].distinct('star_system_name'))
        return sorted(n for n in names if n)

    # ── 後台「商品資料庫 › 商品價格／交易終端」 ────────────────────

    @classmethod
    def admin_list(cls, *, q: str = '', commodity: str = '', star_system: str = '', side: str = '',
                   limit: int = 50, offset: int = 0) -> tuple:
        """價格列（分頁）。side：'buy' 只看買得到的、'sell' 只看能賣的。回傳 (rows, total)。"""
        db = get_db()
        limit = max(1, min(int(limit or 50), MAX_ADMIN_LIMIT))
        offset = max(0, int(offset or 0))
        conds = []
        if commodity:
            conds.append({'id_commodity': {'$in': _id_variants(commodity)}})
        if star_system:
            tids = [v for t in db[TERMINALS].find({'star_system_name': star_system}, {'id': 1})
                    for v in _id_variants(_doc_id(t))]
            conds.append({'$or': [{'star_system_name': star_system}, {'id_terminal': {'$in': tids}}]})
        if side == 'buy':
            conds.append({'price_buy': {'$gt': 0}})
        elif side == 'sell':
            conds.append({'price_sell': {'$gt': 0}})
        q = (q or '').strip()
        if q:
            rx = re.compile(re.escape(q), re.IGNORECASE)
            cids = [v for c in db[COMMODITIES].find({'$or': [{'name': rx}, {'code': rx}]}, {'id': 1})
                    for v in _id_variants(_doc_id(c))]
            tids = [v for t in db[TERMINALS].find(
                {'$or': [{'name': rx}, {'nickname': rx}, {'displayname': rx}, {'code': rx}]}, {'id': 1})
                for v in _id_variants(_doc_id(t))]
            conds.append({'$or': [{'commodity_name': rx}, {'commodity_code': rx}, {'terminal_name': rx},
                                  {'id_commodity': {'$in': cids}}, {'id_terminal': {'$in': tids}}]})
        filt = {'$and': conds} if conds else {}

        total = db[PRICES].count_documents(filt)
        docs = list(db[PRICES].find(filt).sort([('commodity_name', 1), ('terminal_name', 1), ('_id', 1)])
                    .skip(offset).limit(limit))
        commodities = _commodity_map({str(d.get('id_commodity')) for d in docs})
        terminals = _terminal_map({str(d.get('id_terminal')) for d in docs})
        rows = []
        for d in docs:
            cid, tid = str(d.get('id_commodity')), str(d.get('id_terminal'))
            rows.append({
                'id': str(d['_id']),
                'commodity': _commodity_summary(cid, commodities.get(cid), d),
                'terminal': terminal_summary(terminals.get(tid), d),
                **{f: d.get(f) for f in PRICE_FIELDS},
            })
        return rows, total

    @staticmethod
    def admin_terminals() -> list:
        """全部交易終端（一次載入，篩選在前端），附這個終端有幾筆可買／可賣的商品價格。"""
        counts: dict = {}
        for row in get_db()[PRICES].find({}, {'id_terminal': 1, 'price_buy': 1, 'price_sell': 1}):
            c = counts.setdefault(str(row.get('id_terminal')), {'buy': 0, 'sell': 0})
            c['buy'] += 1 if _positive(row.get('price_buy')) else 0
            c['sell'] += 1 if _positive(row.get('price_sell')) else 0
        rows = []
        for t in get_db()[TERMINALS].find({}):
            tid = _doc_id(t)
            row = {f: t.get(f) for f in TERMINAL_FIELDS}
            row['id'] = tid
            row['location'] = location_path(t)
            row['commodity_buy_count'] = counts.get(tid, {}).get('buy', 0)
            row['commodity_sell_count'] = counts.get(tid, {}).get('sell', 0)
            rows.append(row)
        return sorted(rows, key=lambda r: ([(x or '').lower() for x in r['location']], (r['name'] or '').lower()))
