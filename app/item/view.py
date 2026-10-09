"""遊戲主檔查詢（唯讀）。

資料由 tasks/scdata_sync.py 從社群 API 同步而來，本藍圖只讀不寫。

查詢一律只回 is_current=True 的資料；已被遊戲移除的物品仍留在 DB
（庫存外鍵需要），要查到它們得用 include_retired=1。
"""

import re

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from src.limiter import limiter
from src.models.item import CommodityMaster, ItemMaster, SyncRun, VehicleMaster
from src.models import uex_vehicle_price
from src.models.mission import Faction, Mission
from src.models.inventory import uscu_to_scu
from src.models.log import Log
from src.models.sync_schedule import (JOB_KEYS, SCHEDULE_TZ, SyncJobs, SyncScheduleError,
                                      order_jobs)
from src.permissions import (READ_ROLES, WRITE_ROLES, admin_api, require_role, viewer_sees_hidden,
                             visibility_arg)
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
      - {in: query, name: player_visible,     type: integer, description: "後台用：1 = 只看玩家頁面顯示的、0 = 只看不顯示的（玩家 token 一律只看得到顯示的）"}
      - {in: query, name: sort_by,            type: string, description: "name（預設）／crew_max／cargo_capacity_scu／mass_hull／msrp／size_class"}
      - {in: query, name: sort_dir,           type: string, description: "asc（預設）／desc"}
      - {in: query, name: acquire,            type: array, items: {type: string}, description: "取得方式：buy（可用遊戲幣購買）／rent（可租船），可重複帶多個（取聯集），資料來自 UEX"}
      - {in: query, name: with_prices,        type: integer, description: "1 = 每筆附 uex_price（遊戲內最低購買價／租船價與地點數，見 src/models/uex_vehicle_price.py）"}
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
    acquire = [a for a in request.args.getlist('acquire') if a in uex_vehicle_price.ACQUIRE_FIELDS]
    sort_by = request.args.get('sort_by', 'name')
    sort_dir = -1 if request.args.get('sort_dir') == 'desc' else 1

    hide = not viewer_sees_hidden()
    visibility = None if hide else visibility_arg(request.args)
    has_filters = bool(careers or roles or manufacturer_codes or size_classes or types
                       or visibility is not None or acquire)

    if query and not has_filters:
        # ⚠️ search() 只回前 limit 筆，所以 total 只能是「本頁筆數」。
        #    照舊回 len(rows) 的話 total == limit，前端算出「只有一頁」，
        #    使用者永遠翻不到第二頁（而且不會有任何錯誤徵兆）。
        #    回 None 讓前端知道「總數未知」，分頁改用「本頁滿了就還有下一頁」。
        #    帶了其他篩選條件時 search() 沒辦法一起套用，改走 list_all()。
        rows = VehicleMaster.with_type(VehicleMaster.search(query, limit=limit, visible_only=hide))
        total = None
    else:
        rows, total = VehicleMaster.list_all(
            limit=limit, offset=offset, careers=careers, roles=roles,
            manufacturer_codes=manufacturer_codes, size_classes=size_classes,
            query=query, sort_by=sort_by, sort_dir=sort_dir, types=types,
            visible_only=hide, visibility=visibility,
            ids=uex_vehicle_price.vehicle_ids_with(acquire) if acquire else None)

    for row in rows:
        row['vehicle_inventory_scu'] = uscu_to_scu(row.get('vehicle_inventory_uscu'))
    if request.args.get('with_prices') == '1':
        uex_vehicle_price.attach_summaries(rows)
    return jsonify({'success': True, 'data': rows, 'total': total,
                    'limit': limit, 'offset': offset})


@app_item.route('/vehicles/<vehicle_id>/prices', methods=['GET'])
@jwt_required()
def get_vehicle_prices(vehicle_id):
    """載具的遊戲內購買價／租船價（UEX，aUEC），各自依價格由低到高，附交易終端與回報時間。

    官網現金價（美金）是載具本身的 msrp 欄位，不在這裡。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: "data: {purchase: [{terminal, price, date_modified}], rental: [...]}"
    """
    return jsonify({'success': True, 'data': uex_vehicle_price.prices_for(vehicle_id)})


@app_item.route('/uex-vehicle-prices', methods=['GET'])
@admin_api(*READ_ROLES)
def list_uex_vehicle_prices():
    """後台「艦船 › 購買價格／租船價格」：UEX 載具價格表原始內容（分頁），附對應到的載具主檔。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: kind, type: string, required: true, description: "purchase（購買）／rental（租船）"}
      - {in: query, name: q, type: string, description: "載具或終端名稱"}
      - {in: query, name: star_system, type: string}
      - {in: query, name: limit, type: integer, default: 50}
      - {in: query, name: offset, type: integer, default: 0}
    responses:
      200:
        description: "data: [{id, uex_vehicle, vehicle, terminal, price, date_modified}]、total、star_systems"
      400:
        description: kind 不對
    """
    from src.models.uex_commodity_price import UexCommodityPrice
    args = request.args
    try:
        rows, total = uex_vehicle_price.admin_list(
            args.get('kind') or '', q=args.get('q') or '', star_system=args.get('star_system') or '',
            limit=int(args.get('limit') or 50), offset=int(args.get('offset') or 0))
    except ValueError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    return jsonify({'success': True, 'data': rows, 'total': total,
                    'star_systems': UexCommodityPrice.star_systems()})


@app_item.route('/vehicles/<vehicle_id>/note', methods=['PUT'])
@admin_api(*WRITE_ROLES)
def set_vehicle_note(vehicle_id):
    """後台手寫的艦船說明（玩家頁的艦隊、持有船艦、船艦資料都會顯示）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: vehicle_id, type: string, required: true}
      - in: body
        name: body
        schema:
          type: object
          properties:
            note: {type: string, description: "空字串 = 清掉；最多 1000 字"}
    responses:
      200:
        description: 成功
      400:
        description: 格式錯誤或太長
      404:
        description: 找不到艦船
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or 'note' not in body:
        return jsonify({'success': False, 'message': '缺少 note'}), 400
    username = get_jwt_identity()
    try:
        doc = VehicleMaster.set_note(vehicle_id, body['note'], username)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    if doc is None:
        return jsonify({'success': False, 'message': '找不到艦船'}), 404
    Log.create(username, 'set_vehicle_note',
               f'艦船 {vehicle_id} 說明{"更新" if doc.get("note") else "清除"}', success=True)
    return jsonify({'success': True, 'data': doc})


@app_item.route('/fleet', methods=['GET'])
@admin_api(*READ_ROLES)
def list_player_fleet():
    """後台「艦船 › 玩家擁有艦船」：玩家登記的船／載具（每筆登記一列，唯讀）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q,      type: string,  description: "船名（中英文）"}
      - {in: query, name: player, type: string,  description: "遊戲ID／暱稱／玩家名稱"}
      - {in: query, name: sort,   type: string,  description: "name（預設）／player／quantity／updated"}
      - {in: query, name: limit,  type: integer, default: 50, description: "最多 200"}
      - {in: query, name: offset, type: integer, default: 0}
    responses:
      200:
        description: 成功
    """
    from src.models.fleet import Fleet
    limit, offset = _paging()
    query = (request.args.get('q') or '').strip()
    vehicle_uuids = None
    if query and re.search(r'[\u3400-\u9fff]', query):
        # 中文船名不在登記資料裡，先用主檔的中文對照查成 uuid
        vehicle_uuids = VehicleMaster.ids_matching_zh(query)
    rows, total = Fleet.admin_list(
        query=query, player=(request.args.get('player') or '').strip(),
        vehicle_uuids=vehicle_uuids, sort=(request.args.get('sort') or 'name').strip(),
        limit=limit, offset=offset)
    return jsonify({'success': True, 'data': rows, 'total': total, 'limit': limit, 'offset': offset})


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
    「艦隊」「查詢 › 持有船艦」一進去就要全部用到，省四次往返；多出來的
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
            'missions': Mission.count_current(),
            'factions': Faction.count_current(),
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


def _job_counts() -> dict:
    """各同步項目目前在資料庫裡的筆數（排程頁顯示用）。"""
    from src.models import translation as T
    from src.models.item import BlueprintMaster
    from src.models.mining import MiningDeposit
    from src.models.starmap import Starmap
    from src.mongo import get_db

    return {
        'translations': T.count(T.SOURCE_GAME),
        'items': ItemMaster.count_current(),
        'vehicles': VehicleMaster.count_current(),
        'commodities': CommodityMaster.count_current(),
        'blueprints': BlueprintMaster.count_current(),
        'factions': Faction.count_current(),
        'missions': Mission.count_current(),
        'mining': MiningDeposit.count_current(),
        'locations': Starmap.count_current(),
        'uex': get_db()['uex_items'].estimated_document_count(),
    }


def _serialize_job(job: dict, running: set, counts: dict) -> dict:
    is_running = job['key'] in running
    return {
        'key': job['key'],
        'label': job['label'],
        'cron': job.get('cron'),
        'enabled': job.get('enabled', True),
        'next_run': SyncJobs.next_run(job),
        # 「正在跑」以該項的 Redis 鎖為準：worker 被砍掉時 DB 的 running 標記不會自己清掉
        'running': is_running,
        'running_since': job.get('running_since') if is_running else None,
        'progress': (job.get('progress') or {}) if is_running else {},
        'progress_at': job.get('progress_at') if is_running else None,
        'queued': not is_running and SyncJobs.is_queued(job),
        'queued_at': job.get('queued_at'),
        'queued_by': job.get('queued_by'),
        'count': counts.get(job['key']),
        'last_started_at': job.get('last_started_at'),
        'last_finished_at': job.get('last_finished_at'),
        'last_duration_s': job.get('last_duration_s'),
        'last_ok': job.get('last_ok'),
        'last_error': job.get('last_error'),
        'last_stats': job.get('last_stats') or {},
        'consecutive_failures': job.get('consecutive_failures') or 0,
        'updated_at': job.get('updated_at'),
        'updated_by': job.get('updated_by'),
    }


@app_item.route('/sync-jobs', methods=['GET'])
@admin_api(*READ_ROLES)
def list_sync_jobs():
    """各同步項目（每個資料庫一筆）的排程、下次執行時間、上次結果與目前筆數。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    from datetime import datetime

    from tasks.scdata_sync import running_jobs

    running = set(running_jobs())
    counts = _job_counts()
    jobs = [_serialize_job(j, running, counts) for j in SyncJobs.all()]
    return jsonify({'success': True, 'data': {
        'is_running': bool(running),
        'running': [j['key'] for j in jobs if j['running']],
        'queued': [j['key'] for j in jobs if j['queued']],
        # 前端算「已經跑了多久」用伺服器時間，不受使用者電腦時鐘誤差影響
        'server_time': datetime.utcnow(),
        'timezone': str(SCHEDULE_TZ),
        'jobs': jobs,
    }})


@app_item.route('/sync-jobs/<key>', methods=['PUT'])
@jwt_required()
@require_role(*WRITE_ROLES)
def update_sync_job(key):
    """修改某個同步項目的排程（cron／啟用）。

    排程實際生效方式：tasks/celeryconfig.py 有一個每 5 分鐘的心跳任務
    （check-sync-schedule），每次都會讀這裡存的設定判斷哪幾項到期，
    所以存檔後不需要重啟 worker/beat。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: key, type: string, required: true, description: "同步項目，例如 items、missions"}
      - in: body
        name: body
        required: true
        schema:
          type: object
          properties:
            cron:    {type: string,  description: "標準 5 欄位 cron，例如 '30 4 * * 1'"}
            enabled: {type: boolean}
    responses:
      200:
        description: 成功
      400:
        description: cron 表達式無效
      404:
        description: 沒有這個同步項目
    """
    from tasks.scdata_sync import running_jobs

    if key not in JOB_KEYS:
        return jsonify({'success': False, 'message': f'沒有這個同步項目：{key}'}), 404
    data = request.get_json(silent=True) or {}
    try:
        job = SyncJobs.update(key, cron=data.get('cron'), enabled=data.get('enabled'),
                              updated_by=get_jwt_identity())
    except SyncScheduleError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    Log.create(get_jwt_identity(), 'update_sync_job',
               f'修改同步排程 {key}：cron={job.get("cron")} 啟用={job.get("enabled")}')
    return jsonify({'success': True,
                    'data': _serialize_job(job, set(running_jobs()), _job_counts())})


@app_item.route('/sync-uex-token', methods=['GET'])
@admin_api('admin')
def get_uex_token():
    """UEX API token 的設定狀態（只回有沒有設定、來源、末 4 碼，不回完整 token）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: "data: {configured, source: admin|env|null, masked, updated_at, updated_by}"
    """
    from src.models.app_setting import UexToken
    return jsonify({'success': True, 'data': UexToken.status()})


@app_item.route('/sync-uex-token', methods=['PUT'])
@admin_api('admin')
def set_uex_token():
    """設定 UEX API token（只有 admin）。存檔後下一次 UEX 同步就會用，不用重啟容器。
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
            token: {type: string, description: "UEX 的 access token；空字串 = 清掉後台設定（改回用環境變數 UEX_API_TOKEN）"}
    responses:
      200:
        description: 成功，回傳新的設定狀態
      400:
        description: 格式錯誤
    """
    from src.models.app_setting import UexToken
    data = request.get_json(silent=True) or {}
    if 'token' not in data:
        return jsonify({'success': False, 'message': '沒有要更新的 token'}), 400
    try:
        status = UexToken.set(data.get('token'), updated_by=get_jwt_identity())
    except ValueError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    # 操作紀錄只記「改了」，不記 token 內容
    Log.create(get_jwt_identity(), 'update_uex_token',
               '設定 UEX API token' if status['source'] == 'admin' else '清除後台設定的 UEX API token')
    return jsonify({'success': True, 'data': status})


@app_item.route('/sync', methods=['POST'])
@jwt_required()
@require_role(*WRITE_ROLES)
@limiter.limit('30 per hour')
def trigger_sync():
    """手動同步（全部，或指定幾個同步項目）。

    每一項各自派成一個 Celery 任務，不同項目可以同時跑（同時跑幾個看 worker 的
    concurrency，超過的會排隊）。正在跑或已在排隊的項目不重複派送；全部都在跑
    就回 409。
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
            jobs: {type: array, items: {type: string}, description: "同步項目 key，省略 = 全部（見 /item/sync-jobs）"}
    responses:
      202:
        description: 已派送（dispatched）；正在跑／排隊中而略過的在 skipped
      400:
        description: 有不認得的同步項目
      409:
        description: 指定的項目都已經在同步或排隊中
      429:
        description: 觸發過於頻繁
    """
    from tasks.scdata_sync import dispatch_jobs

    data = request.get_json(silent=True) or {}
    jobs = data.get('jobs')
    if jobs is not None:
        if not isinstance(jobs, list) or not jobs:
            return jsonify({'success': False, 'message': 'jobs 必須是非空陣列'}), 400
        unknown = [j for j in jobs if j not in JOB_KEYS]
        if unknown:
            return jsonify({'success': False,
                            'message': f'沒有這個同步項目：{"、".join(map(str, unknown))}'}), 400
    keys = order_jobs(jobs or JOB_KEYS)

    sent, skipped = dispatch_jobs(keys, by=get_jwt_identity())
    if not sent:
        return jsonify({'success': False, 'skipped': skipped,
                        'message': '這些項目都已經在同步或排隊中'}), 409
    Log.create(get_jwt_identity(), 'trigger_sync', f'手動同步：{"、".join(sent)}')
    return jsonify({'success': True, 'dispatched': sent, 'skipped': skipped,
                    'message': '已排入同步佇列'}), 202


# ── 玩家頁面顯示（藍圖、任務、礦床、礦物、採礦地點、艦船、地點共用，見 src/models/visibility.py）──

@app_item.route('/visibility/<dataset>/<path:doc_id>', methods=['PUT'])
@admin_api(*WRITE_ROLES)
def set_player_visibility(dataset, doc_id):
    """手動設定某筆遊戲資料要不要在玩家頁面顯示（null = 回到依名稱自動判斷）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: dataset, type: string, required: true,
         description: "blueprints／missions／mining_deposits／minerals／mining_locations／vehicles／locations"}
      - {in: path, name: doc_id, type: string, required: true, description: "uuid（礦物是 resource_key）"}
      - in: body
        name: body
        schema:
          type: object
          properties:
            player_visible: {type: boolean, description: "true／false；null = 自動判斷"}
    responses:
      200:
        description: 成功，data 是新的顯示欄位
      400:
        description: 格式錯誤或不支援的資料庫
      404:
        description: 找不到資料
    """
    from src.models import visibility
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or 'player_visible' not in body:
        return jsonify({'success': False, 'message': '缺少 player_visible'}), 400
    username = get_jwt_identity()
    try:
        state = visibility.set_override(dataset, doc_id, body['player_visible'], username)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    if state is None:
        return jsonify({'success': False, 'message': '找不到資料'}), 404
    label = {True: '顯示', False: '不顯示', None: '自動'}[body['player_visible']]
    Log.create(username, 'set_player_visibility',
               f'{visibility.DATASETS[dataset][0]} {doc_id} 玩家頁面設為{label}', success=True)
    return jsonify({'success': True, 'data': state})


@app_item.route('/visibility/minerals', methods=['GET'])
@admin_api(*READ_ROLES)
def mineral_visibility():
    """礦物的玩家頁面顯示狀態 {resource_key: 顯示欄位}（礦物從礦床成分彙整，沒有自己的文件）。
    ---
    tags: [Item]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    from src.models import visibility
    from src.models.mining import MiningDeposit
    return jsonify({'success': True, 'data': visibility.minerals_state(MiningDeposit.list_all())})
