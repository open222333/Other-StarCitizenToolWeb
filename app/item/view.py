"""遊戲主檔查詢（唯讀）。

資料由 tasks/scdata_sync.py 從社群 API 同步而來，本藍圖只讀不寫。

查詢一律只回 is_current=True 的資料；已被遊戲移除的物品仍留在 DB
（庫存外鍵需要），要查到它們得用 include_retired=1。
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from src.models.item import CommodityMaster, ItemMaster, SyncRun, VehicleMaster
from src.models.inventory import uscu_to_scu

app_item = Blueprint('app_item', __name__)

MAX_LIMIT = 200


def _paging() -> tuple:
    """統一解析 limit / offset，並夾在合理範圍內。"""
    try:
        limit = int(request.args.get('limit', 50))
    except ValueError:
        limit = 50
    try:
        offset = int(request.args.get('offset', 0))
    except ValueError:
        offset = 0
    return max(1, min(limit, MAX_LIMIT)), max(0, offset)


@app_item.route('/', methods=['GET'])
@jwt_required()
def list_items():
    """物品主檔列表。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: type,   type: string,  description: "依類型過濾（見 /item/types）"}
      - {in: query, name: limit,  type: integer, default: 50, description: "最多 200"}
      - {in: query, name: offset, type: integer, default: 0}
    responses:
      200:
        description: 成功
    """
    limit, offset = _paging()
    rows, total = ItemMaster.list_by_type(
        item_type=(request.args.get('type') or '').strip(),
        limit=limit, offset=offset,
    )
    for row in rows:
        row['volume_scu'] = uscu_to_scu(row.get('volume_uscu'))
    return jsonify({'success': True, 'data': rows, 'total': total,
                    'limit': limit, 'offset': offset})


@app_item.route('/search', methods=['GET'])
@jwt_required()
def search_items():
    """物品名稱搜尋（供前端 autocomplete 使用）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q,     type: string,  required: true, description: "名稱或 class name 的一部分"}
      - {in: query, name: limit, type: integer, default: 25, description: "最多 200"}
    responses:
      200:
        description: 成功
      400:
        description: q 不得為空
    """
    query = (request.args.get('q') or '').strip()
    if not query:
        return jsonify({'success': False, 'message': 'q 不得為空'}), 400

    limit, _ = _paging()
    rows = ItemMaster.search(query, limit=min(limit, 50))
    for row in rows:
        row['volume_scu'] = uscu_to_scu(row.get('volume_uscu'))
    return jsonify({'success': True, 'data': rows})


@app_item.route('/types', methods=['GET'])
@jwt_required()
def list_types():
    """所有物品類型。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': ItemMaster.types()})


@app_item.route('/<item_id>', methods=['GET'])
@jwt_required()
def get_item(item_id):
    """單一物品完整資料（含 raw 原始 API 回應）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: path,  name: item_id,  type: string,  required: true, description: "遊戲 uuid"}
      - {in: query, name: with_raw, type: integer, default: 0, description: "1 = 一併回傳 raw"}
    responses:
      200:
        description: 成功
      404:
        description: 找不到物品
    """
    item = ItemMaster.get(item_id)
    if not item:
        return jsonify({'success': False, 'message': '找不到物品'}), 404

    if request.args.get('with_raw') != '1':
        item.pop('raw', None)
    item['volume_scu'] = uscu_to_scu(item.get('volume_uscu'))
    return jsonify({'success': True, 'data': item})


@app_item.route('/<item_id>/prices', methods=['GET'])
@jwt_required()
def get_item_prices(item_id):
    """物品在哪買賣、價格多少。

    優先用 UEX 資料（需 UEX_API_TOKEN），沒有就退回 Wiki API 內嵌的價格。
    兩者都是社群眾包，與實際伺服器可能有落差。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: item_id, type: string, required: true}
    responses:
      200:
        description: 成功
      404:
        description: 找不到物品
    """
    item = ItemMaster.get(item_id)
    if not item:
        return jsonify({'success': False, 'message': '找不到物品'}), 404

    rows = ItemMaster.prices(item, limit=20)
    return jsonify({'success': True, 'data': rows,
                    'source': rows[0]['source'] if rows else None})


@app_item.route('/vehicles', methods=['GET'])
@jwt_required()
def list_vehicles():
    """載具主檔列表（含 SCU 貨艙容量）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q,      type: string,  description: "名稱前綴搜尋"}
      - {in: query, name: limit,  type: integer, default: 50}
      - {in: query, name: offset, type: integer, default: 0}
    responses:
      200:
        description: 成功
    """
    limit, offset = _paging()
    query = (request.args.get('q') or '').strip()

    if query:
        rows = VehicleMaster.search(query, limit=limit)
        total = len(rows)
    else:
        rows, total = VehicleMaster.list_all(limit=limit, offset=offset)

    for row in rows:
        row['vehicle_inventory_scu'] = uscu_to_scu(row.get('vehicle_inventory_uscu'))
    return jsonify({'success': True, 'data': rows, 'total': total,
                    'limit': limit, 'offset': offset})


@app_item.route('/commodities', methods=['GET'])
@jwt_required()
def list_commodities():
    """商品主檔列表（含可用箱體規格）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q,      type: string,  description: "名稱前綴搜尋"}
      - {in: query, name: limit,  type: integer, default: 100}
      - {in: query, name: offset, type: integer, default: 0}
    responses:
      200:
        description: 成功
    """
    limit, offset = _paging()
    query = (request.args.get('q') or '').strip()

    if query:
        rows = CommodityMaster.search(query, limit=limit)
        total = len(rows)
    else:
        rows, total = CommodityMaster.list_all(limit=limit, offset=offset)

    return jsonify({'success': True, 'data': rows, 'total': total,
                    'limit': limit, 'offset': offset})


@app_item.route('/sync-status', methods=['GET'])
@jwt_required()
def sync_status():
    """遊戲資料同步狀態（前端顯示「資料更新到哪個版本」用）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    run = SyncRun.latest()
    if run:
        run.pop('stats', None)

    return jsonify({'success': True, 'data': {
        'latest_run': run,
        'game_versions': ItemMaster.game_versions(),
        'counts': {
            'items': ItemMaster.count_current(),
            'vehicles': VehicleMaster.count_current(),
            'commodities': CommodityMaster.count_current(),
        },
    }})
