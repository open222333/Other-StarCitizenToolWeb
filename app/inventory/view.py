"""庫存管理 API。

職責分工：
  - Web（本藍圖）＝管理主控台。可操作任何歸屬，但寫入需 admin / operator。
  - Discord bot ＝玩家自助介面。玩家只能動自己的個人庫（見 bot/）。

兩邊共用 src/models/inventory.py 的邏輯，不各自實作。

歸屬（owner_type）：
  - `guild`  → 公會共享庫，player 一律忽略
  - `player` → 個人庫，必須帶 player（RSI handle）
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from src import WMS_SCOPE_ID
from src.models.inventory import (OWNER_GUILD, OWNER_PLAYER, Inventory, InventoryLog,
                                  StockError, uscu_to_scu)
from src.models.item import ItemMaster, VehicleMaster
from src.models.log import Log
from src.models.player import Player
from src.permissions import (PLAYER_CLAIM, READ_ROLES, WRITE_ROLES,
                             admin_api, require_role)
from src.sc_zh import location_name_zh
from app._shared import attach_item_names

app_inventory = Blueprint('app_inventory', __name__)

MAX_LIMIT = 200

# 玩家自助 token 的 identity 前綴（見 app/player/view.py）
PLAYER_IDENTITY_PREFIX = 'player:'


@app_inventory.errorhandler(StockError)
def handle_stock_error(err):
    """StockError 是預期中的使用者錯誤，訊息直接回給前端顯示。"""
    return jsonify({'success': False, 'message': str(err)}), 400


def _paging() -> tuple:
    try:
        limit = int(request.args.get('limit', 50))
    except ValueError:
        limit = 50
    try:
        offset = int(request.args.get('offset', 0))
    except ValueError:
        offset = 0
    return max(1, min(limit, MAX_LIMIT)), max(0, offset)


def _self_player_scid():
    """若這是玩家自助 token，回傳它的 star_citizen_id；後台 token 回 None。"""
    if not get_jwt().get(PLAYER_CLAIM):
        return None
    identity = get_jwt_identity() or ''
    if not identity.startswith(PLAYER_IDENTITY_PREFIX):
        return None
    return identity[len(PLAYER_IDENTITY_PREFIX):] or None


def _owner_from_args() -> tuple:
    """從 query string 解析歸屬。預設公會共享庫。

    玩家自助 token 一律被綁在自己的個人庫上 —— 否則帶
    `?owner_type=player&player=<別人的handle>` 就能讀到別人整個個人庫。
    （玩家要看自己的庫存有專用端點 /player/inventory，這裡只是防止繞道。）
    """
    scid = _self_player_scid()
    if scid:
        return OWNER_PLAYER, scid

    owner_type = (request.args.get('owner_type') or OWNER_GUILD).strip()
    player = (request.args.get('player') or '').strip() or None

    if owner_type == OWNER_PLAYER and not player:
        raise StockError('owner_type=player 時必須指定 player。')
    return owner_type, player


def _owner_from_body(data: dict) -> tuple:
    owner_type = (data.get('owner_type') or OWNER_GUILD).strip()
    player = (data.get('player') or '').strip() or None

    if owner_type == OWNER_PLAYER and not player:
        raise StockError('owner_type=player 時必須指定 player。')
    return owner_type, player


def _resolve_item_or_400(value: str) -> dict:
    """把 uuid 或名稱解析成物品。解析不出來就拋 StockError。"""
    value = (value or '').strip()
    if not value:
        raise StockError('必須指定 item。')

    item = ItemMaster.resolve(value)
    if not item:
        raise StockError(f'找不到物品「{value}」，或對到多筆。請改用 uuid（見 /item/search）。')
    return item


def _positive_int(data: dict, field: str) -> int:
    raw = data.get(field)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise StockError(f'{field} 必須是整數。')
    if value <= 0:
        raise StockError(f'{field} 必須大於 0。')
    if value > 1_000_000:
        raise StockError(f'{field} 超過單次上限 1,000,000。')
    return value


# ─────────────────────────────────────────────────────────── 查詢

@app_inventory.route('/', methods=['GET'])
@jwt_required()
def list_stock():
    """查庫存。
    ---
    tags: [Inventory]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: owner_type, type: string, enum: [guild, player], default: guild}
      - {in: query, name: player,     type: string, description: "owner_type=player 時必填（RSI handle）"}
      - {in: query, name: location,   type: string, description: "只看某個位置，可重複帶多個做多選"}
      - {in: query, name: item_id,    type: string, description: "只看某個物品（uuid）"}
      - {in: query, name: container,  type: string, description: "容器關鍵字（模糊比對）"}
      - {in: query, name: q,          type: string, description: "物品名稱關鍵字（中英文都比對）"}
      - {in: query, name: sort_by,    type: string, description: "item_name(預設)/location/container/quantity/total_scu"}
      - {in: query, name: sort_dir,   type: string, enum: [asc, desc], default: asc}
      - {in: query, name: limit,      type: integer, default: 50}
      - {in: query, name: offset,     type: integer, default: 0}
    responses:
      200:
        description: 成功
      400:
        description: 參數錯誤
    """
    owner_type, player = _owner_from_args()
    limit, offset = _paging()

    # getlist：單一值跟多選（後台列表的「位置」篩選）共用同一個 location
    # query key，跟 app/blueprint/view.py 的 player_id 是同一個道理。
    locations = request.args.getlist('location')
    container = (request.args.get('container') or '').strip()
    name_query = (request.args.get('q') or '').strip()
    sort_by = request.args.get('sort_by', 'item_name')
    sort_dir = -1 if request.args.get('sort_dir') == 'desc' else 1

    rows, total = Inventory.list_stock(
        WMS_SCOPE_ID, owner_type, player,
        item_id=(request.args.get('item_id') or '').strip(),
        offset=offset, limit=limit,
        locations=locations, container=container, name_query=name_query,
        sort_by=sort_by, sort_dir=sort_dir,
    )
    summary = Inventory.capacity(
        WMS_SCOPE_ID, owner_type, player,
        locations=locations, container=container, name_query=name_query,
    )
    return jsonify({'success': True, 'data': rows, 'total': total,
                    'limit': limit, 'offset': offset, 'summary': summary})


@app_inventory.route('/locations', methods=['GET'])
@jwt_required()
def list_locations():
    """已使用過的位置清單。
    ---
    tags: [Inventory]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': Inventory.distinct_locations(WMS_SCOPE_ID)})


# display_names_by_scid 回傳的所有欄位都要複製進列 —— 抽成一支是因為
# /inventory/where 與 /inventory/search 都要做同一件事，各寫一次的話
# 之後多一個欄位（例如 Discord）就會有一邊漏掉。
_HOLDER_FIELDS = ('nickname', 'player_name', 'discord_name', 'discord_id')


def _add_holder_info(rows: list) -> None:
    """就地補上持有者的顯示名稱與（已按公開設定遮蔽的）聯絡方式。

    inventory.player 存的是 RSI handle（＝star_citizen_id），只有代號。
    Discord 的遮蔽在 Player.display_names_by_scid 裡做，這裡只負責搬。
    """
    names = Player.display_names_by_scid(r.get('player') for r in rows)
    for row in rows:
        info = names.get(row.get('player')) or {}
        for key in _HOLDER_FIELDS:
            row[key] = info.get(key, '')


@app_inventory.route('/where/<item_id>', methods=['GET'])
@jwt_required()
def where_item(item_id):
    """某個物品在所有位置的分布（跨公會庫與個人庫）。
    ---
    tags: [Inventory]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: item_id, type: string, required: true, description: "遊戲 uuid"}
    responses:
      200:
        description: 成功
      404:
        description: 找不到物品
    """
    item = ItemMaster.get(item_id)
    if not item:
        return jsonify({'success': False, 'message': '找不到物品'}), 404

    rows = Inventory.find_item_locations(WMS_SCOPE_ID, item_id)

    # 補上持有者的顯示名稱：inventory.player 存的是 RSI handle
    # （＝star_citizen_id），只有代號。前端要顯示「暱稱（遊戲ID）」，
    # 所以在這裡一次批次補齊，而不是讓前端逐列再打 API。
    _add_holder_info(rows)

    unit_scu = uscu_to_scu(item.get('volume_uscu'))
    total = sum(row['quantity'] for row in rows)

    return jsonify({'success': True, 'data': rows, 'item': {
        'item_id': item_id,
        'name': item.get('name'),
        'name_zh': item.get('name_zh'),
        'volume_scu': unit_scu,
        'is_current': item.get('is_current', True),
    }, 'summary': {
        'total_quantity': total,
        'total_scu': round(unit_scu * total, 4),
    }})


def _locations_matching(query: str) -> list:
    """地點名稱含 query 的地點（英文名或中文對照都算）。

    不用 Mongo regex 直接撈是因為中文對照表在程式裡（src/sc_zh.py 的
    JSON），不在 DB 欄位上 —— 打「羅威爾」的時候 DB 裡只有 "Lorville"，
    regex 永遠不會命中。這裡先拿 distinct 地點（實務上幾十個），
    再在 Python 端同時比對英文與中文。
    """
    q = (query or '').strip().lower()
    if not q:
        return []
    out = []
    for loc in Inventory.distinct_locations(WMS_SCOPE_ID):
        zh = location_name_zh(loc) or ''
        if q in loc.lower() or (zh and q in zh.lower()):
            out.append(loc)
    return out


@app_inventory.route('/search', methods=['GET'])
@jwt_required()
def search_stock():
    """一個關鍵字同時搜物品名稱、地點、玩家暱稱、玩家遊戲ID。

    給玩家站「查詢 › 物品庫存」用。跟 /inventory/where/<item_id> 的差別是
    那支要先知道確切的 item_id（前端得先跑一次 autocomplete 讓人選），
    這支讓使用者直接打字：打物品名就看到誰有、打暱稱就看到那個人有什麼、
    打地點就看到那裡放了什麼。

    三種來源取聯集而不是交集：使用者打一串字時心裡只有一個意圖，
    但我們猜不到是哪一種，所以三種都試、命中就回。
    ---
    tags: [Inventory]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q, type: string, required: true, description: "物品名稱／地點／玩家暱稱／遊戲ID"}
      - {in: query, name: limit, type: integer, default: 100, description: "最多 300"}
    responses:
      200:
        description: 成功
      400:
        description: 缺少 q
    """
    q = (request.args.get('q') or '').strip()
    if not q:
        return jsonify({'success': False, 'message': '缺少搜尋關鍵字 q'}), 400

    try:
        limit = int(request.args.get('limit', 100))
    except ValueError:
        limit = 100

    item_ids  = ItemMaster.ids_matching(q)
    players   = Player.scids_matching(q)
    locations = _locations_matching(q)

    rows = Inventory.search_any(
        WMS_SCOPE_ID, item_ids=item_ids, players=players,
        locations=locations, limit=limit,
    )

    # 補持有者顯示名稱（跟 where_item 同一套，見那邊的說明）
    _add_holder_info(rows)

    return jsonify({'success': True, 'data': rows, 'matched': {
        # 讓前端能說「比對到 2 個物品、1 位玩家」，也方便除錯搜不到的情況
        'items':     len(item_ids),
        'players':   len(players),
        'locations': len(locations),
    }})


@app_inventory.route('/capacity', methods=['GET'])
@jwt_required()
def capacity():
    """算佔用多少 SCU，可比對某艘船的貨艙裝不裝得下。

    注意 `unknown_volume` > 0 時 `total_scu` 是低估值 —— 有物品在主檔裡沒有體積資料。
    ---
    tags: [Inventory]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: owner_type, type: string, enum: [guild, player], default: guild}
      - {in: query, name: player,     type: string}
      - {in: query, name: location,   type: string, description: "留空 = 全部位置"}
      - {in: query, name: ship,       type: string, description: "載具 uuid 或名稱，用來比對容量"}
    responses:
      200:
        description: 成功
      400:
        description: 參數錯誤
    """
    owner_type, player = _owner_from_args()
    location = (request.args.get('location') or '').strip()
    summary = Inventory.capacity(WMS_SCOPE_ID, owner_type, player, location=location)

    payload = {'success': True, 'data': summary,
               'owner_type': owner_type, 'player': player, 'location': location or None}

    ship = (request.args.get('ship') or '').strip()
    if ship:
        vehicle = VehicleMaster.resolve(ship)
        if not vehicle:
            payload['ship'] = {'error': f'找不到載具「{ship}」'}
        else:
            cargo = vehicle.get('cargo_capacity_scu') or 0
            needed = summary['total_scu']
            fits = cargo > 0 and needed <= cargo

            payload['ship'] = {
                'name': vehicle.get('name'),
                'cargo_capacity_scu': cargo,
                'vehicle_inventory_scu': uscu_to_scu(vehicle.get('vehicle_inventory_uscu')),
                'needed_scu': needed,
                'fits': fits,
                'remaining_scu': round(cargo - needed, 4) if fits else 0,
                # 裝不下時要跑幾趟
                'trips': int(-(-needed // cargo)) if cargo > 0 and needed > cargo else 1,
            }

    return jsonify(payload)


@app_inventory.route('/history', methods=['GET'])
@admin_api(*READ_ROLES)
def history():
    """庫存異動紀錄（整個 scope，含操作者與備註）。

    這是管理端的全域紀錄，所以限後台帳號。玩家要看自己的異動紀錄
    請用 `/player/inventory/history`。
    ---
    tags: [Inventory]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: item_id, type: string, description: "只看某個物品"}
      - {in: query, name: limit,   type: integer, default: 20, description: "最多 200"}
    responses:
      200:
        description: 成功
    """
    limit, _ = _paging()
    rows = InventoryLog.recent(
        WMS_SCOPE_ID, limit=limit,
        item_id=(request.args.get('item_id') or '').strip(),
    )

    # 補上物品名稱，前端不必再逐筆查（單一 $in 批次查，見 app/_shared.py）
    return jsonify({'success': True, 'data': attach_item_names(rows)})


# ─────────────────────────────────────────────────────── 異動（需 admin/operator）

@app_inventory.route('/add', methods=['POST'])
@jwt_required()
@require_role(*WRITE_ROLES)
def add_stock():
    """入庫。
    ---
    tags: [Inventory]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [item, quantity, location]
          properties:
            item:       {type: string,  description: "遊戲 uuid 或完整名稱"}
            quantity:   {type: integer, description: "大於 0"}
            location:   {type: string}
            container:  {type: string,  description: "容器／箱號，可留空"}
            owner_type: {type: string,  enum: [guild, player], default: guild}
            player:     {type: string,  description: "owner_type=player 時必填"}
            note:       {type: string}
    responses:
      200:
        description: 入庫成功
      400:
        description: 參數錯誤
      403:
        description: 權限不足
    """
    data = request.get_json() or {}
    owner_type, player = _owner_from_body(data)
    item = _resolve_item_or_400(data.get('item'))
    quantity = _positive_int(data, 'quantity')
    actor = get_jwt_identity()

    doc = Inventory.adjust(
        WMS_SCOPE_ID, owner_type, player,
        location=data.get('location') or '', container=data.get('container'),
        item_id=item['_id'], delta=quantity,
        actor=actor, actor_id=f'web:{actor}', note=(data.get('note') or '').strip(),
    )

    Log.create(username=actor, action='inventory_add',
               detail=f"{item['name']} +{quantity} @ {doc['location']}", success=True)

    unit_scu = uscu_to_scu(item.get('volume_uscu'))
    return jsonify({'success': True, 'data': {
        'item_id': item['_id'], 'item_name': item['name'],
        'quantity': doc['quantity'], 'delta': quantity,
        'location': doc['location'], 'container': doc.get('container'),
        'owner_type': owner_type, 'player': player,
        'added_scu': round(unit_scu * quantity, 4),
        'total_scu': round(unit_scu * doc['quantity'], 4),
    }})


@app_inventory.route('/remove', methods=['POST'])
@jwt_required()
@require_role(*WRITE_ROLES)
def remove_stock():
    """出庫。庫存不足會回 400 且不改動任何資料。
    ---
    tags: [Inventory]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [item, quantity, location]
          properties:
            item:       {type: string}
            quantity:   {type: integer}
            location:   {type: string}
            container:  {type: string}
            owner_type: {type: string, enum: [guild, player], default: guild}
            player:     {type: string}
            note:       {type: string}
    responses:
      200:
        description: 出庫成功
      400:
        description: 庫存不足或參數錯誤
      403:
        description: 權限不足
    """
    data = request.get_json() or {}
    owner_type, player = _owner_from_body(data)
    item = _resolve_item_or_400(data.get('item'))
    quantity = _positive_int(data, 'quantity')
    actor = get_jwt_identity()

    doc = Inventory.adjust(
        WMS_SCOPE_ID, owner_type, player,
        location=data.get('location') or '', container=data.get('container'),
        item_id=item['_id'], delta=-quantity,
        actor=actor, actor_id=f'web:{actor}', note=(data.get('note') or '').strip(),
    )

    Log.create(username=actor, action='inventory_remove',
               detail=f"{item['name']} -{quantity} @ {doc['location']}", success=True)

    return jsonify({'success': True, 'data': {
        'item_id': item['_id'], 'item_name': item['name'],
        'quantity': doc['quantity'], 'delta': -quantity,
        'location': doc['location'], 'container': doc.get('container'),
        'owner_type': owner_type, 'player': player,
        'emptied': doc['quantity'] == 0,
    }})


@app_inventory.route('/move', methods=['POST'])
@jwt_required()
@require_role(*WRITE_ROLES)
def move_stock():
    """移庫。

    非交易操作：先扣來源再加目的地，加失敗會回復來源。
    補償也失敗時會在 inventory_log 留 move_rollback_failed 供人工對帳。
    ---
    tags: [Inventory]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [item, quantity, source, destination]
          properties:
            item:                  {type: string}
            quantity:              {type: integer}
            source:                {type: string, description: "來源位置"}
            destination:           {type: string, description: "目的位置"}
            source_container:      {type: string}
            destination_container: {type: string}
            owner_type:            {type: string, enum: [guild, player], default: guild}
            player:                {type: string}
    responses:
      200:
        description: 移庫成功
      400:
        description: 來源庫存不足或參數錯誤
      403:
        description: 權限不足
    """
    data = request.get_json() or {}
    owner_type, player = _owner_from_body(data)
    item = _resolve_item_or_400(data.get('item'))
    quantity = _positive_int(data, 'quantity')
    actor = get_jwt_identity()

    result = Inventory.move(
        WMS_SCOPE_ID, owner_type, player, item_id=item['_id'], quantity=quantity,
        src_location=data.get('source') or '', src_container=data.get('source_container'),
        dst_location=data.get('destination') or '',
        dst_container=data.get('destination_container'),
        actor=actor, actor_id=f'web:{actor}',
    )

    Log.create(
        username=actor, action='inventory_move',
        detail=f"{item['name']} ×{quantity}: {data.get('source')} → {data.get('destination')}",
        success=True,
    )

    return jsonify({'success': True, 'data': {
        'item_id': item['_id'], 'item_name': item['name'], 'quantity': quantity,
        'source': {'location': result['src']['location'],
                   'container': result['src'].get('container'),
                   'remaining': result['src']['quantity']},
        'destination': {'location': result['dst']['location'],
                        'container': result['dst'].get('container'),
                        'quantity': result['dst']['quantity']},
        'owner_type': owner_type, 'player': player,
    }})
