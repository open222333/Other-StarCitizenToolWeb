"""藍圖 API。這個藍圖底下有**兩組不同性質**的端點，別搞混：

  1. `/blueprint/master/*` —— 製造藍圖**主檔**（遊戲資料，1,600+ 筆配方）。
     唯讀，由 tasks/scdata_sync.py 從 Star Citizen Wiki API 同步進
     blueprint_master collection。就像 /item/* 對 item_master 那樣。

  2. `/blueprint/` 的 CRUD —— **玩家藍圖名冊**（誰擁有哪張藍圖）。
     資料在 blueprints collection，由人填寫。這裡是後台管理版本，
     可以操作任何玩家的藍圖；玩家自助版（只能動自己的）在
     app/player/view.py 的 `/player/blueprints`。

兩者靠 blueprints.blueprint_uuid → blueprint_master._id 連起來，
但那個欄位允許為空 —— 玩家仍可自由輸入名稱（主檔還沒同步、或遊戲版本
比主檔新的時候需要）。
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from src.models.blueprint import Blueprint as BlueprintModel
from src.models.item import BlueprintMaster
from src.permissions import READ_ROLES, WRITE_ROLES, admin_api

app_blueprint = Blueprint('app_blueprint', __name__)

MAX_LIMIT = 200

_FORM_FIELDS = ('name', 'player_id', 'acquisition_method',
                'acquisition_location', 'unlock_status', 'notes',
                'blueprint_uuid')


def _serialize_form(data: dict, *, partial: bool = False) -> dict:
    """整理表單欄位。

    `partial=True`（PUT 用）只回傳 data 裡實際出現的 key。這很重要 ——
    否則沒傳的欄位會被當成空字串寫進資料庫：只送 {"notes": "x"} 會把 name
    清空、player_id 變 None（藍圖脫離擁有者）、unlock_status 靜默重設回
    'obtained'（把已解鎖狀態吃掉）。
    """
    if partial:
        return {k: (data.get(k) or '').strip() for k in _FORM_FIELDS if k in data}

    fields = {k: (data.get(k) or '').strip() for k in _FORM_FIELDS}
    fields['unlock_status'] = fields['unlock_status'] or 'obtained'
    return fields


@app_blueprint.route('/', methods=['GET'])
@admin_api(*READ_ROLES)
def list_blueprints():
    """列出所有藍圖（不含已軟刪除），可選用 player_id 過濾。"""
    player_id = (request.args.get('player_id') or '').strip()
    return jsonify({'success': True, 'data': BlueprintModel.find_all(player_id=player_id)})


@app_blueprint.route('/<blueprint_id>', methods=['GET'])
@admin_api(*READ_ROLES)
def get_blueprint(blueprint_id):
    bp = BlueprintModel.find_by_id(blueprint_id)
    if not bp:
        return jsonify({'success': False, 'message': '找不到藍圖'}), 404
    return jsonify({'success': True, 'data': bp})


@app_blueprint.route('/', methods=['POST'])
@admin_api(*WRITE_ROLES)
def create_blueprint():
    data = request.get_json(silent=True) or {}
    fields = _serialize_form(data)
    if not fields['name']:
        return jsonify({'success': False, 'message': 'Blueprint 名稱不得為空'}), 400

    blueprint_id = BlueprintModel.create(**fields)
    return jsonify({'success': True, 'id': blueprint_id}), 201


@app_blueprint.route('/<blueprint_id>', methods=['PUT'])
@admin_api(*WRITE_ROLES)
def update_blueprint(blueprint_id):
    """更新藍圖（只更新有傳入的欄位）。"""
    data = request.get_json(silent=True) or {}
    fields = _serialize_form(data, partial=True)

    if not fields:
        return jsonify({'success': False, 'message': '沒有要更新的欄位'}), 400
    if 'name' in fields and not fields['name']:
        return jsonify({'success': False, 'message': 'Blueprint 名稱不得為空'}), 400

    ok = BlueprintModel.update(blueprint_id, **fields)
    if not ok:
        return jsonify({'success': False, 'message': '藍圖不存在或沒有變更'}), 404
    return jsonify({'success': True})


@app_blueprint.route('/<blueprint_id>', methods=['DELETE'])
@admin_api(*WRITE_ROLES)
def delete_blueprint(blueprint_id):
    if not BlueprintModel.soft_delete(blueprint_id):
        return jsonify({'success': False, 'message': '藍圖不存在'}), 404
    return jsonify({'success': True})


# ═══════════════════════════════════════════════════════════
#  製造藍圖主檔（唯讀，來自 API 同步）
#
#  這一段跟上面的玩家名冊 CRUD 是不同性質的資料 —— 見檔頭說明。
#  唯讀且內容是公開遊戲資料，所以只要求登入（比照 /item/*），
#  不限後台角色：玩家端的藍圖自動完成需要打這裡。
# ═══════════════════════════════════════════════════════════

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


@app_blueprint.route('/master', methods=['GET'])
@jwt_required()
def list_master():
    """製造藍圖主檔列表。
    ---
    tags: [Blueprint]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: output_type, type: string, description: "依產出物類型過濾（見 /blueprint/master/types）"}
      - {in: query, name: available,   type: integer, description: "1 = 只看預設就能用的（不需解鎖任務）"}
      - {in: query, name: limit,       type: integer, default: 50, description: "最多 200"}
      - {in: query, name: offset,      type: integer, default: 0}
    responses:
      200:
        description: 成功
    """
    limit, offset = _paging()
    rows, total = BlueprintMaster.list_all(
        limit=limit, offset=offset,
        output_type=(request.args.get('output_type') or '').strip(),
        available_only=request.args.get('available') == '1',
    )
    return jsonify({'success': True, 'data': rows, 'total': total,
                    'limit': limit, 'offset': offset})


@app_blueprint.route('/master/search', methods=['GET'])
@jwt_required()
def search_master():
    """藍圖名稱搜尋（給前端 autocomplete 用，中英文都比對）。
    ---
    tags: [Blueprint]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q,     type: string,  required: true}
      - {in: query, name: limit, type: integer, default: 25, description: "最多 50"}
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
    return jsonify({'success': True,
                    'data': BlueprintMaster.search(query, limit=min(limit, 50))})


@app_blueprint.route('/master/types', methods=['GET'])
@jwt_required()
def master_output_types():
    """所有產出物類型（前端篩選下拉用）。
    ---
    tags: [Blueprint]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': BlueprintMaster.output_types()})


@app_blueprint.route('/master/for-item/<item_uuid>', methods=['GET'])
@jwt_required()
def master_for_item(item_uuid):
    """做出這個物品的所有配方（物品詳細頁的「怎麼做出來」）。
    ---
    tags: [Blueprint]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: item_uuid, type: string, required: true, description: "item_master 的 uuid"}
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True,
                    'data': BlueprintMaster.for_output_item(item_uuid)})


@app_blueprint.route('/holders', methods=['GET'])
@jwt_required()
def blueprint_holders():
    """誰登記了這張藍圖（藍圖版的 /inventory/where）。

    這是**玩家名冊**的跨玩家查詢，不是主檔 —— 回傳的是「公會裡哪些人
    說自己有這張圖」。公會成員互查是刻意提供的功能，所以只要求登入。

    回應不含玩家的 `notes`（那是寫給自己的備註）。
    ---
    tags: [Blueprint]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q,     type: string,  description: "藍圖名稱的一部分；留空 = 全部"}
      - {in: query, name: limit, type: integer, default: 50, description: "最多 200 組"}
    responses:
      200:
        description: 成功
    """
    limit, _ = _paging()
    rows = BlueprintModel.find_holders(
        query=(request.args.get('q') or '').strip(), limit=limit)
    return jsonify({'success': True, 'data': rows, 'total': len(rows)})


@app_blueprint.route('/master/<blueprint_uuid>', methods=['GET'])
@jwt_required()
def get_master(blueprint_uuid):
    """單一藍圖的完整配方（ingredients / dismantle_returns / 產出物）。
    ---
    tags: [Blueprint]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: blueprint_uuid, type: string, required: true}
    responses:
      200:
        description: 成功
      404:
        description: 找不到藍圖
    """
    doc = BlueprintMaster.get(blueprint_uuid)
    if not doc:
        return jsonify({'success': False, 'message': '找不到藍圖'}), 404
    return jsonify({'success': True, 'data': doc})
