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
from src.models.translation import DEFAULT_LANG
from src.sc_zh import LOOKUPS, blueprint_type_names, known_location_names

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
    """載具主檔列表（太空船＋地面載具＋懸浮載具，含 SCU 貨艙容量）。

    上游 Wiki API 的 vehicles 本來就同時包含太空船與地面載具，用 `type`
    分開（由 is_spaceship／is_gravlev 推出來，見 src/models/item.py 的
    VEHICLE_TYPES），每筆回傳也帶 `vehicle_type`。

    篩選/排序/分頁比照全站搜尋優化計畫（藍圖登記管理／操作紀錄那批）的
    做法：多選用 getlist（可重複帶同一個 key），排序欄位在 model 端有
    白名單擋著。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q,                 type: string, description: "名稱前綴搜尋"}
      - {in: query, name: career,             type: array, items: {type: string}, description: "可重複帶多個（見 /item/vehicles/careers）"}
      - {in: query, name: role,               type: array, items: {type: string}, description: "可重複帶多個（見 /item/vehicles/roles）"}
      - {in: query, name: manufacturer_code,  type: array, items: {type: string}, description: "可重複帶多個（見 /item/vehicles/manufacturers）"}
      - {in: query, name: size_class,         type: array, items: {type: integer}, description: "可重複帶多個（見 /item/vehicles/size-classes）"}
      - {in: query, name: type,               type: array, items: {type: string}, description: "ship（太空船）／ground（地面載具）／gravlev（懸浮載具），可重複帶多個"}
      - {in: query, name: sort_by,            type: string, description: "name（預設）／crew_max／cargo_capacity_scu／mass_hull／msrp／size_class"}
      - {in: query, name: sort_dir,           type: string, description: "asc（預設）／desc"}
      - {in: query, name: limit,              type: integer, default: 50}
      - {in: query, name: offset,             type: integer, default: 0}
    responses:
      200:
        description: 成功
    """
    limit, offset = _paging()
    query = (request.args.get('q') or '').strip()
    careers = request.args.getlist('career')
    roles = request.args.getlist('role')
    manufacturer_codes = request.args.getlist('manufacturer_code')
    size_classes = request.args.getlist('size_class')
    types = request.args.getlist('type')
    sort_by = request.args.get('sort_by', 'name')
    sort_dir = -1 if request.args.get('sort_dir') == 'desc' else 1

    has_filters = bool(careers or roles or manufacturer_codes or size_classes or types)

    if query and not has_filters:
        # ⚠️ search() 只回前 limit 筆，所以 total 只能是「本頁筆數」。
        #    照舊回 len(rows) 的話 total == limit，前端算出「只有一頁」，
        #    使用者永遠翻不到第二頁（而且不會有任何錯誤徵兆）。
        #    回 None 讓前端知道「總數未知」，分頁改用「本頁滿了就還有下一頁」。
        #    帶了其他篩選條件時 search() 沒辦法一起套用，改走 list_all()。
        rows = VehicleMaster.with_type(VehicleMaster.search(query, limit=limit))
        total = None
    else:
        rows, total = VehicleMaster.list_all(
            limit=limit, offset=offset, careers=careers, roles=roles,
            manufacturer_codes=manufacturer_codes, size_classes=size_classes,
            query=query, sort_by=sort_by, sort_dir=sort_dir, types=types)

    for row in rows:
        row['vehicle_inventory_scu'] = uscu_to_scu(row.get('vehicle_inventory_uscu'))
    return jsonify({'success': True, 'data': rows, 'total': total,
                    'limit': limit, 'offset': offset})


@app_item.route('/vehicles/careers', methods=['GET'])
@jwt_required()
def list_vehicle_careers():
    """所有載具 career 值（後台篩選下拉用）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': VehicleMaster.careers()})


@app_item.route('/vehicles/roles', methods=['GET'])
@jwt_required()
def list_vehicle_roles():
    """所有載具 role 值（後台篩選下拉用）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': VehicleMaster.roles()})


@app_item.route('/vehicles/manufacturers', methods=['GET'])
@jwt_required()
def list_vehicle_manufacturers():
    """所有載具製造商（代碼＋全名，後台篩選下拉用）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': VehicleMaster.manufacturers()})


@app_item.route('/vehicles/size-classes', methods=['GET'])
@jwt_required()
def list_vehicle_size_classes():
    """所有載具尺寸等級（後台篩選下拉用）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': VehicleMaster.size_classes()})


@app_item.route('/vehicles/facets', methods=['GET'])
@jwt_required()
def vehicle_facets():
    """載具篩選選單的選項一次拿齊：類型、尺寸、廠商、角色、career。

    跟上面四支 distinct 清單是同樣的資料，只是合成一次回應 —— 玩家頁
    「艦隊」「查詢 › 船艦搜尋」一進去就要全部用到，省四次往返；多出來的
    「類型」（太空船／地面載具／懸浮載具）只有這支有。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功（data 含 types／size_classes／manufacturers／roles／careers）
    """
    return jsonify({'success': True, 'data': VehicleMaster.facets()})


#: /item/translations 一次最多查幾段文字、每段最長幾個字
MAX_TRANSLATION_TEXTS = 300
MAX_TRANSLATION_TEXT_LEN = 200


@app_item.route('/translations', methods=['GET'])
@limiter.limit('120 per minute')
def lookup_translations():
    """遊戲文字翻譯查詢（給前端用；翻譯存在 sc_translations，見 src/models/translation.py）。

    公開、不需要 token：內容是公開的遊戲在地化文字與社群翻譯包，後台與玩家站
    （還沒登入的頁面也一樣）都會用到。
    ---
    tags: [Item]
    parameters:
      - {in: query, name: domain, type: string, required: true,
         description: "location／item／vehicle／vehicle_role／mining_resource／mining_deposit／blueprint_type"}
      - {in: query, name: text, type: array, items: {type: string},
         description: "要翻譯的英文（可重複帶多個）；domain=blueprint_type／location 時可省略，回傳整份清單"}
      - {in: query, name: lang, type: string, default: zh-TW}
    responses:
      200:
        description: 成功，data 是 {英文: 翻譯}，查不到的不會出現
      400:
        description: domain 不認得、沒帶 text、或 text 太多
    """
    domain = (request.args.get('domain') or '').strip()
    lang = (request.args.get('lang') or DEFAULT_LANG).strip()
    lookup = LOOKUPS.get(domain)
    if lookup is None:
        return jsonify({'success': False, 'message': f'不支援的 domain：{domain}'}), 400

    texts = [t.strip() for t in request.args.getlist('text') if t and t.strip()]
    if not texts:
        # 兩個封閉的小清單可以不帶 text 整份拿：藍圖類型、遊戲已知地點名稱
        #（地點回傳 {英文: 翻譯或 null}，沒有翻譯的也列出來，給地點下拉選單用）
        if domain == 'blueprint_type':
            return jsonify({'success': True, 'data': blueprint_type_names(lang)})
        if domain == 'location':
            return jsonify({'success': True, 'data': known_location_names(lang)})
        return jsonify({'success': False, 'message': '請帶 text 參數'}), 400
    if len(texts) > MAX_TRANSLATION_TEXTS:
        return jsonify({'success': False,
                        'message': f'一次最多 {MAX_TRANSLATION_TEXTS} 段文字'}), 400

    data = {}
    for text in dict.fromkeys(t[:MAX_TRANSLATION_TEXT_LEN] for t in texts):
        value = lookup(text, lang=lang)
        if value:
            data[text] = value
    return jsonify({'success': True, 'data': data})


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
    from tasks.scdata_sync import is_sync_running

    run = SyncRun.latest()
    if run:
        run.pop('stats', None)

    return jsonify({'success': True, 'data': {
        'latest_run': run,
        # 真正決定「現在是否有一輪在跑」的是 Redis 鎖，不是 latest_run——
        # worker 沒開的話任務只是卡在佇列裡，鎖根本沒被拿到，latest_run
        # 也不會變，畫面上得靠這個欄位才看得出「其實沒有在跑」。
        'is_running': is_sync_running(),
        'game_versions': ItemMaster.game_versions(),
        'counts': {
            'items': ItemMaster.count_current(),
            'vehicles': VehicleMaster.count_current(),
            'commodities': CommodityMaster.count_current(),
        },
    }})


@app_item.route('/sync-runs', methods=['GET'])
@admin_api(*READ_ROLES)
def sync_runs():
    """最近幾輪同步的執行紀錄（給「同步排程」頁面顯示歷史用）。

    刻意不含 stats 逐資源明細（跟 /sync-status 的 latest_run 一樣），
    列表只需要看得出「這輪跑了多久、成功了沒、涵蓋哪些資源」。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - in: query
        name: limit
        type: integer
        default: 20
    responses:
      200:
        description: 成功
    """
    limit = request.args.get('limit', 20, type=int)
    limit = max(1, min(limit, 100))
    return jsonify({'success': True, 'data': SyncRun.recent(limit=limit)})


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
            with_scunpacked: {type: boolean, default: true, description: "是否同步礦物回波參考表"}
            with_translations: {type: boolean, default: true, description: "是否同步遊戲文字翻譯（英文表＋社群繁中化包）"}
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
    with_scunpacked = data.get('with_scunpacked', True)
    with_translations = data.get('with_translations', True)

    async_result = sync_scdata.delay(
        resources=resources, with_uex=with_uex, with_scunpacked=with_scunpacked,
        with_translations=with_translations)
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
    schedule['next_run'] = SyncSchedule.next_run()
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

    schedule['next_run'] = SyncSchedule.next_run()
    return jsonify({'success': True, 'data': schedule})
