"""AI 可以呼叫的查詢工具（唯讀）。

只回玩家頁本來就看得到的資料：持有者的暱稱／遊戲ID、數量、地點、識別名稱；
Discord 走 Player.display_names_by_scid 的公開設定；不公開的配件網址、密碼、token 一律不給。
每個工具的結果都截短（MAX_ROWS），免得吃光 AI 的 token。
"""

import json

from src import WMS_SCOPE_ID
from src.models.blueprint import Blueprint
from src.models.fleet import Fleet
from src.models.inventory import Inventory
from src.models.item import ItemMaster, VehicleMaster
from src.models.player import Player
from src.models import nav
from src.models.uex_commodity_price import UexCommodityPrice

MAX_ROWS = 30
MAX_PLAYERS = 5


def _fn(name, description, props, required=()):
    return {'type': 'function', 'function': {
        'name': name, 'description': description,
        'parameters': {'type': 'object', 'properties': props, 'required': list(required)}}}


_NAME = {'type': 'string', 'description': '名稱關鍵字（英文或中文，可以是部分名稱）'}
_PLAYER = {'type': 'string', 'description': '只看這位玩家（遊戲ID或暱稱，可以是部分）；不限定就不要給'}

TOOLS = [
    _fn('find_item_holders', '查公會裡誰有某個物品、放在哪裡、幾個（倉庫庫存，含公會共享庫）。',
        {'name': _NAME, 'player': _PLAYER}, ['name']),
    _fn('find_blueprint_holders', '查公會裡誰登記了某張藍圖。',
        {'name': _NAME, 'player': _PLAYER}, ['name']),
    _fn('find_ship_holders', '查公會裡誰有某款船／載具、幾艘、每艘的識別名稱。',
        {'name': _NAME, 'player': _PLAYER}, ['name']),
    _fn('player_summary', '查某位玩家有哪些物品、藍圖、船艦。',
        {'player': {'type': 'string', 'description': '玩家的遊戲ID或暱稱（可以是部分）'}}, ['player']),
    _fn('where_to_buy', '查物品或商品（貨物、礦物）在哪裡買得到、價格（UEX 玩家回報的資料）。',
        {'name': _NAME}, ['name']),
]


def _label(nickname, player_name, scid) -> str:
    name = (nickname or '').strip() or (player_name or '').strip()
    scid = (scid or '').strip()
    if not scid:
        return name or '—'
    return f'{name}（{scid}）' if name else scid


def _players(query: str) -> list:
    """玩家關鍵字 → 遊戲ID 清單（最多 MAX_PLAYERS 位）。"""
    return Player.scids_matching(query or '', limit=MAX_PLAYERS) if (query or '').strip() else []


def find_item_holders(name: str, player: str = '') -> dict:
    ids = ItemMaster.ids_matching(name, limit=1000)
    if not ids:
        return {'found': False, 'message': f'物品資料庫找不到「{name}」'}
    scids = _players(player) if player else ['']
    if player and not scids:
        return {'found': False, 'message': f'找不到玩家「{player}」'}
    rows = []
    for scid in scids:
        rows += Inventory.search_filtered(WMS_SCOPE_ID, item_ids=ids, player_scid=scid, limit=300)
    names = Player.display_names_by_scid(r.get('player') for r in rows)
    items: dict = {}
    for r in rows:
        item = items.setdefault(r.get('item_id'), {
            'item': r.get('item_name_zh') or r.get('item_name'), 'item_en': r.get('item_name'),
            'total': 0, 'holders': []})
        item['total'] += r.get('quantity') or 0
        if r.get('owner_type') == 'guild':
            holder = '公會共享庫'
        else:
            info = names.get(r.get('player')) or {}
            holder = _label(info.get('nickname'), info.get('player_name'), r.get('player'))
        item['holders'].append({'holder': holder, 'location': r.get('location'),
                                'container': r.get('container') or None, 'quantity': r.get('quantity')})
    out = sorted(items.values(), key=lambda x: -x['total'])[:MAX_ROWS]
    for x in out:
        x['holders'] = x['holders'][:MAX_ROWS]
    return {'found': bool(out), 'items': out}


def find_blueprint_holders(name: str, player: str = '') -> dict:
    scids = _players(player) if player else ['']
    if player and not scids:
        return {'found': False, 'message': f'找不到玩家「{player}」'}
    groups = []
    for scid in scids:
        groups += Blueprint.find_holders(query=name, limit=MAX_ROWS, player_scid=scid)
    out = [{'blueprint': g.get('name_zh') or g.get('name'), 'blueprint_en': g.get('name'),
            'holder_count': g.get('holder_count'),
            'holders': [_label(h.get('nickname'), h.get('player_name'), h.get('star_citizen_id'))
                        for h in (g.get('holders') or [])][:MAX_ROWS]}
           for g in groups][:MAX_ROWS]
    return {'found': bool(out), 'blueprints': out}


def find_ship_holders(name: str, player: str = '') -> dict:
    uuids = VehicleMaster.ids_matching_filter(query=name)
    if uuids is not None and not uuids:
        return {'found': False, 'message': f'船艦資料庫找不到「{name}」'}
    scids = _players(player) if player else ['']
    if player and not scids:
        return {'found': False, 'message': f'找不到玩家「{player}」'}
    groups = []
    for scid in scids:
        groups += Fleet.find_holders(vehicle_uuids=uuids, player_scid=scid, limit=MAX_ROWS)
    out = []
    for g in groups[:MAX_ROWS]:
        v = g.get('vehicle') or {}
        out.append({
            'ship': v.get('name_zh') or v.get('name') or g.get('name'), 'ship_en': v.get('name') or g.get('name'),
            'cargo_scu': v.get('cargo_capacity_scu'), 'total': g.get('total_quantity'),
            'holders': [{'holder': _label(h.get('nickname'), h.get('player_name'), h.get('star_citizen_id')),
                         'quantity': h.get('quantity'),
                         'unit_names': [n for n in (h.get('unit_names') or []) if n]}
                        for h in (g.get('holders') or [])][:MAX_ROWS],
        })
    return {'found': bool(out), 'ships': out}


def player_summary(player: str) -> dict:
    scids = _players(player)
    if not scids:
        return {'found': False, 'message': f'找不到玩家「{player}」'}
    if len(scids) > 1:
        names = Player.display_names_by_scid(scids)
        return {'found': False, 'message': '符合的玩家不只一位，請講清楚是哪一位',
                'candidates': [_label((names.get(s) or {}).get('nickname'), (names.get(s) or {}).get('player_name'), s)
                               for s in scids]}
    scid = scids[0]
    info = Player.display_names_by_scid([scid]).get(scid) or {}
    stock = Inventory.search_filtered(WMS_SCOPE_ID, player_scid=scid, limit=300)
    items: dict = {}
    for r in stock:
        name = r.get('item_name_zh') or r.get('item_name')
        items[name] = items.get(name, 0) + (r.get('quantity') or 0)
    bps = Blueprint.find_holders(limit=200, player_scid=scid)
    ships = Fleet.find_holders(player_scid=scid, limit=200)
    return {
        'found': True,
        'player': _label(info.get('nickname'), info.get('player_name'), scid),
        'items': [{'item': k, 'quantity': v} for k, v in sorted(items.items(), key=lambda kv: -kv[1])][:MAX_ROWS],
        'item_kinds': len(items),
        'blueprints': [g.get('name_zh') or g.get('name') for g in bps][:MAX_ROWS],
        'blueprint_count': len(bps),
        'ships': [{'ship': (g.get('vehicle') or {}).get('name_zh') or g.get('name'), 'quantity': g.get('total_quantity')}
                  for g in ships][:MAX_ROWS],
        'ship_kinds': len(ships),
    }


def where_to_buy(name: str) -> dict:
    out: dict = {'found': False}
    item = ItemMaster.resolve(name)
    if not item:
        hits = ItemMaster.search(name, limit=1)
        item = ItemMaster.get(hits[0]['_id']) if hits else None
    if item:
        rows = [r for r in ItemMaster.prices(item, limit=20) if r.get('price_buy')]
        out['item'] = {
            'name': item.get('name_zh') or item.get('name'), 'name_en': item.get('name'),
            'buy': [{'price_auec': r['price_buy'], 'terminal': r.get('terminal_name'), 'location': r.get('location')}
                    for r in sorted(rows, key=lambda r: r['price_buy'])[:10]],
        }
        out['found'] = bool(rows)
    q = (name or '').strip().lower()
    cands = nav.commodities() if q else []
    def _names(c):
        return [(c.get('name') or '').lower(), (c.get('code') or '').lower(), (c.get('name_zh') or '').lower()]
    commodity = (next((c for c in cands if q in _names(c)), None)
                 or next((c for c in cands if any(q in n for n in _names(c) if n)), None))
    if commodity:
        locs = UexCommodityPrice.buy_locations([commodity['id']]).get('locations') or []
        buys = []
        for loc in locs:
            row = (loc.get('items') or [{}])[0]
            term = loc.get('terminal') or {}
            buys.append({'price_auec_per_scu': row.get('price_buy'), 'terminal': term.get('name'),
                         'location': ' › '.join(x for x in term.get('location') or [] if x)})
        buys.sort(key=lambda r: r['price_auec_per_scu'] or 0)
        out['commodity'] = {'name': commodity.get('name_zh') or commodity.get('name'), 'name_en': commodity.get('name'),
                            'buy': buys[:10]}
        out['found'] = out['found'] or bool(buys)
    if not item and not commodity:
        out['message'] = f'找不到叫「{name}」的物品或商品'
    return out


_IMPL = {
    'find_item_holders': find_item_holders,
    'find_blueprint_holders': find_blueprint_holders,
    'find_ship_holders': find_ship_holders,
    'player_summary': player_summary,
    'where_to_buy': where_to_buy,
}


def run(name: str, arguments) -> str:
    """執行工具，回傳給 AI 的 JSON 字串（錯誤也包成 JSON，讓 AI 自己解釋）。"""
    fn = _IMPL.get(name)
    if not fn:
        return json.dumps({'error': f'沒有這個工具：{name}'}, ensure_ascii=False)
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
        if not isinstance(args, dict):
            raise ValueError
        allowed = fn.__code__.co_varnames[:fn.__code__.co_argcount]
        args = {k: str(v) for k, v in args.items() if k in allowed and v not in (None, '')}
        result = fn(**args)
    except TypeError:
        return json.dumps({'error': '參數不完整'}, ensure_ascii=False)
    except ValueError:
        return json.dumps({'error': '參數格式錯誤'}, ensure_ascii=False)
    return json.dumps(result, ensure_ascii=False, default=str)
