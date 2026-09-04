"""遊戲主檔查詢（唯讀）。

資料由 tasks/scdata_sync.py 從社群 API 同步而來，本藍圖只讀不寫。

查詢一律只回 is_current=True 的資料；已被遊戲移除的物品仍留在 DB
（庫存外鍵需要），要查到它們得用 include_retired=1。
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from src.limiter import limiter
from src.models.item import CommodityMaster, ItemMaster, SyncRun, VehicleMaster
from src.models.inventory import uscu_to_scu
from src.models.sync_schedule import SyncSchedule, SyncScheduleError
from src.permissions import READ_ROLES, WRITE_ROLES, admin_api, require_role

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
        # ⚠️ search() 只回前 limit 筆，所以 total 只能是「本頁筆數」。
        #    照舊回 len(rows) 的話 total == limit，前端算出「只有一頁」，
        #    使用者永遠翻不到第二頁（而且不會有任何錯誤徵兆）。
        #    回 None 讓前端知道「總數未知」，分頁改用「本頁滿了就還有下一頁」。
        rows = VehicleMaster.search(query, limit=limit)
        total = None
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
        # 同上：搜尋模式沒有總數，回 None 而不是騙人的 len(rows)
        rows = CommodityMaster.search(query, limit=limit)
        total = None
    else:
        rows, total = CommodityMaster.list_all(limit=limit, offset=offset)

    return jsonify({'success': True, 'data': rows, 'total': total,
                    'limit': limit, 'offset': offset})


@app_item.route('/sync-status', methods=['GET'])
@admin_api(*READ_ROLES)
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


@app_item.route('/sync', methods=['POST'])
@jwt_required()
@require_role(*WRITE_ROLES)
@limiter.limit('4 per hour')
def trigger_sync():
    """手動觸發遊戲主檔同步（items / vehicles / commodities + UEX）。

    平常靠 tasks/celeryconfig.py 的每 5 分鐘心跳（check-sync-schedule）判斷是否到期，
    實際排程（cron）存在 DB 的 sync_schedule，可於後台設定頁修改。
    這支只是給後台一個「立刻同步」按鈕用，非同步丟給 Celery worker 執行，
    不會卡住這個 request（全量同步約 5～10 分鐘）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: false
        schema:
          type: object
          properties:
            resources: {type: array, items: {type: string}, description: "預設全部：items/vehicles/commodities"}
            with_uex:  {type: boolean, default: true}
    responses:
      202:
        description: 已排入同步佇列
      409:
        description: 已有同步進行中
      429:
        description: 觸發過於頻繁（每小時上限 4 次）
    """
    from tasks.scdata_sync import is_sync_running, sync_scdata

    # 同步是互斥的（見 tasks/scdata_sync.py 的鎖），與其讓使用者按下去、
    # 任務跑起來才發現被略過，不如在這裡就回 409 讓前端顯示「同步中」。
    if is_sync_running():
        return jsonify({
            'success': False,
            'message': '已有一輪同步進行中，請等它結束後再觸發（可用 /item/sync-status 查看）',
        }), 409

    data = request.get_json(silent=True) or {}
    resources = data.get('resources') or None
    with_uex = data.get('with_uex', True)

    async_result = sync_scdata.delay(resources=resources, with_uex=with_uex)
    return jsonify({'success': True, 'task_id': async_result.id,
                    'message': '已排入同步佇列，稍後可用 /item/sync-status 查看結果'}), 202


@app_item.route('/sync-schedule', methods=['GET'])
@admin_api(*READ_ROLES)
def get_sync_schedule():
    """目前的自動同步排程設定。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    schedule = SyncSchedule.get()
    return jsonify({'success': True, 'data': schedule})


@app_item.route('/sync-schedule', methods=['PUT'])
@jwt_required()
@require_role(*WRITE_ROLES)
def update_sync_schedule():
    """修改自動同步排程（cron / 啟用狀態 / 要同步的資源 / 是否含 UEX）。

    排程實際生效方式：tasks/celeryconfig.py 有一個每 5 分鐘的心跳任務
    （check-sync-schedule），每次都會讀這裡存的設定判斷「現在該不該跑」，
    所以存檔後不需要重啟 worker/beat。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            cron:      {type: string,  description: "標準 5 欄位 cron，例如 '30 4 * * 1'"}
            enabled:   {type: boolean}
            resources: {type: array, items: {type: string}}
            with_uex:  {type: boolean}
    responses:
      200:
        description: 成功
      400:
        description: cron 表達式無效或 resources 格式錯誤
    """
    data = request.get_json(silent=True) or {}

    try:
        schedule = SyncSchedule.update(
            cron=data.get('cron'),
            enabled=data.get('enabled'),
            resources=data.get('resources'),
            with_uex=data.get('with_uex'),
            updated_by=get_jwt_identity(),
        )
    except SyncScheduleError as err:
        return jsonify({'success': False, 'message': str(err)}), 400

    return jsonify({'success': True, 'data': schedule})
