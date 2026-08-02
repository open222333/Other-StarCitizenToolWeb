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
from flask_jwt_extended import get_jwt_identity, jwt_required

from src import WMS_SCOPE_ID
from src.models.inventory import (OWNER_GUILD, OWNER_PLAYER, Inventory, InventoryLog,
                                  StockError, uscu_to_scu)
from src.models.item import ItemMaster, VehicleMaster
from src.models.log import Log
from src.permissions import require_role

app_inventory = Blueprint('app_inventory', __name__)

MAX_LIMIT = 200
WRITE_ROLES = ('admin', 'operator')


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


def _owner_from_args() -> tuple:
    """從 query string 解析歸屬。預設公會共享庫。"""
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
      - {in: query, name: location,   type: string, description: "只看某個位置"}
      - {in: query, name: item_id,    type: string, description: "只看某個物品（uuid）"}
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

    rows, total = Inventory.list_stock(
        WMS_SCOPE_ID, owner_type, player,
        location=(request.args.get('location') or '').strip(),
        item_id=(request.args.get('item_id') or '').strip(),
        offset=offset, limit=limit,
    )
    summary = Inventory.capacity(
        WMS_SCOPE_ID, owner_type, player,
        location=(request.args.get('location') or '').strip(),
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
    unit_scu = uscu_to_scu(item.get('volume_uscu'))
    total = sum(row['quantity'] for row in rows)

    return jsonify({'success': True, 'data': rows, 'item': {
        'item_id': item_id,
        'name': item.get('name'),
        'volume_scu': unit_scu,
        'is_current': item.get('is_current', True),
    }, 'summary': {
        'total_quantity': total,
        'total_scu': round(unit_scu * total, 4),
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
@jwt_required()
def history():
    """庫存異動紀錄。
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

    # 補上物品名稱，前端不必再逐筆查
    names: dict = {}
    for row in rows:
        item_id = row.get('item_id')
        if item_id and item_id not in names:
            item = ItemMaster.get(item_id)
            names[item_id] = (item or {}).get('name') or item_id
        row['item_name'] = names.get(item_id)

    return jsonify({'success': True, 'data': rows})


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
