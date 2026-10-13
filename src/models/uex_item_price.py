"""物品的遊戲內買賣價（UEX，aUEC）：後台「物品」、玩家頁「倉庫 › 物品資料」。

資料（「UEX 價格」同步項目，需 token）：
  - uex_items：UEX 的物品，wiki_uuid＝item_master._id（同步時從 UEX 的 uuid 帶進來）
  - uex_items_prices：一筆＝「某物品 × 某交易終端」，price_buy > 0 代表這個終端買得到、
    price_sell > 0 代表這個終端收

UEX 沒有這個物品的價格時，退回 Wiki API 內嵌在 item_master.raw.uex_prices 的購買價
（舊的 /item/<id>/prices 跟 Discord bot 也是這樣，見 ItemMaster.prices）。
"""

from src.models.uex_commodity_price import TERMINALS, _id_variants, _num, terminal_summary
from src.mongo import get_db

ITEMS = 'uex_items'
PRICES = 'uex_items_prices'

#: 取得方式篩選：buy＝買得到、sell＝能賣
ACQUIRE_FIELDS = {'buy': 'price_buy', 'sell': 'price_sell'}


def _uex_ids(item_ids) -> dict:
    """{item_master._id: [UEX 物品 id（字串、數字兩種寫法）]}"""
    ids = [str(i) for i in item_ids if i]
    out: dict = {}
    if not ids:
        return out
    for row in get_db()[ITEMS].find({'wiki_uuid': {'$in': ids}}, {'id': 1, 'wiki_uuid': 1}):
        if row.get('id') is not None:
            out.setdefault(row['wiki_uuid'], []).extend(_id_variants(row['id']))
    return out


def _price_rows(uex_ids: list) -> list:
    if not uex_ids:
        return []
    return list(get_db()[PRICES].find({'id_item': {'$in': uex_ids}}))


def prices_for(item_id: str) -> dict:
    """{buy: [...], sell: [...], source: 'uex'|'wiki'|None}；buy 由便宜到貴、sell 由高到低。
    每筆 {terminal（見 terminal_summary）, price, date_modified}。"""
    rows = _price_rows(_uex_ids([item_id]).get(str(item_id), []))
    if rows:
        terminals = {str(t.get('id', t.get('_id'))): t for t in get_db()[TERMINALS].find(
            {'id': {'$in': [v for r in rows for v in _id_variants(r.get('id_terminal'))]}})}
        buy, sell = [], []
        for r in rows:
            term = terminal_summary(terminals.get(str(r.get('id_terminal'))), r)
            for key, out in (('price_buy', buy), ('price_sell', sell)):
                price = _num(r.get(key))
                if price and price > 0:
                    out.append({'terminal': term, 'price': price, 'date_modified': r.get('date_modified')})
        buy.sort(key=lambda x: x['price'])
        sell.sort(key=lambda x: -x['price'])
        return {'buy': buy, 'sell': sell, 'source': 'uex'}

    item = get_db()['item_master'].find_one({'_id': str(item_id)}, {'raw.uex_prices': 1}) or {}
    embedded = (((item.get('raw') or {}).get('uex_prices') or {}).get('purchase')) or []
    buy = []
    for r in embedded:
        price = _num(r.get('price_buy'))
        if not price or price <= 0:
            continue
        place = (r.get('starmap_location') or {}).get('name')
        buy.append({'terminal': {'id': None, 'name': r.get('terminal_name') or '', 'star_system': None,
                                 'planet': None, 'place': place, 'location': [place] if place else []},
                    'price': price, 'date_modified': None})
    buy.sort(key=lambda x: x['price'])
    return {'buy': buy, 'sell': [], 'source': 'wiki' if buy else None}


def attach_summaries(rows: list) -> list:
    """每筆加 uex_price：{buy_min, buy_count, sell_max, sell_count}（沒有價格是 None）。只看 UEX。"""
    mapping = _uex_ids(r.get('_id') for r in rows)
    by_uex: dict = {}
    for p in _price_rows([v for vs in mapping.values() for v in vs]):
        by_uex.setdefault(str(p.get('id_item')), []).append(p)
    for row in rows:
        prices = [p for v in {str(x) for x in mapping.get(row.get('_id'), [])} for p in by_uex.get(v, [])]
        buys = [n for n in (_num(p.get('price_buy')) for p in prices) if n and n > 0]
        sells = [n for n in (_num(p.get('price_sell')) for p in prices) if n and n > 0]
        row['uex_price'] = {
            'buy_min': min(buys) if buys else None, 'buy_count': len(buys),
            'sell_max': max(sells) if sells else None, 'sell_count': len(sells),
        } if (buys or sells) else None
    return rows


def item_ids_with(acquire) -> list:
    """有 UEX 價格（buy＝買得到、sell＝能賣，多個取聯集）的 item_master._id。"""
    fields = [ACQUIRE_FIELDS[a] for a in acquire or [] if a in ACQUIRE_FIELDS]
    if not fields:
        return []
    db = get_db()
    uex_ids = set()
    for field in fields:
        uex_ids |= {str(v) for v in db[PRICES].distinct('id_item', {field: {'$gt': 0}})}
    out = set()
    for row in db[ITEMS].find({'wiki_uuid': {'$ne': None}}, {'id': 1, 'wiki_uuid': 1}):
        if str(row.get('id')) in uex_ids and row.get('wiki_uuid'):
            out.add(row['wiki_uuid'])
    return sorted(out)

