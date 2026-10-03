"""任務／勢力資料庫（唯讀）。

資料由 tasks/scdata_sync.py 從 Star Citizen Wiki API 同步而來（mission_master／
faction_master），本藍圖只讀不寫，詳見 src/models/mission.py。

跟 /blueprint/master、/mining/* 一樣是公開遊戲資料，只要求登入（後台與玩家
token 都可以）：玩家頁點藍圖名稱看「解鎖任務」要打 /mission/for-blueprint/<uuid>。
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from src.permissions import viewer_sees_hidden, visibility_arg

from src.models.mission import MAX_LIMIT, Faction, Mission

app_mission = Blueprint('app_mission', __name__)


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


def _multi(name: str) -> list:
    return [v.strip() for v in request.args.getlist(name) if v.strip()]


@app_mission.route('/', methods=['GET'])
@jwt_required()
def list_missions():
    """任務列表（分頁）。
    ---
    tags: [Mission]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q,             type: string,  description: "標題（中英文）／debug_name／發布者關鍵字"}
      - {in: query, name: reward_scope,  type: string,  description: "類型，可重複帶多個"}
      - {in: query, name: star_system,   type: string,  description: "星系，可重複帶多個"}
      - {in: query, name: faction_uuid,  type: string,  description: "勢力 uuid，可重複帶多個"}
      - {in: query, name: legality,      type: string,  description: "legal／illegal，可重複帶"}
      - {in: query, name: has_blueprints, type: integer, description: "1 = 只看會給藍圖的"}
      - {in: query, name: missing_zh,    type: integer, description: "1 = 只看沒有中文標題的"}
      - {in: query, name: id,            type: string,  description: "指定單一任務 uuid（從別頁跳過來用）"}
      - {in: query, name: blueprint_uuid, type: string, description: "只看會給這張藍圖的任務"}
      - {in: query, name: player_visible, type: integer, description: "後台用：1 = 只看玩家頁面顯示的、0 = 只看不顯示的（玩家 token 一律只看得到顯示的）"}
      - {in: query, name: limit,         type: integer, default: 50, description: "最多 200"}
      - {in: query, name: offset,        type: integer, default: 0}
    responses:
      200:
        description: 成功
    """
    limit, offset = _paging()
    sees_hidden = viewer_sees_hidden()
    rows, total = Mission.list_all(
        limit=limit, offset=offset,
        query=(request.args.get('q') or '').strip(),
        reward_scopes=_multi('reward_scope'),
        star_systems=_multi('star_system'),
        faction_uuids=_multi('faction_uuid'),
        legality=_multi('legality'),
        has_blueprints=request.args.get('has_blueprints') == '1',
        missing_zh=request.args.get('missing_zh') == '1',
        mission_id=(request.args.get('id') or '').strip(),
        blueprint_uuid=(request.args.get('blueprint_uuid') or '').strip(),
        visible_only=not sees_hidden,
        visibility=visibility_arg(request.args) if sees_hidden else None,
    )
    return jsonify({'success': True, 'data': rows, 'total': total,
                    'limit': limit, 'offset': offset})


@app_mission.route('/facets', methods=['GET'])
@jwt_required()
def mission_facets():
    """任務篩選下拉的選項：類型、星系、勢力（含任務數）。
    ---
    tags: [Mission]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': Mission.facets()})


@app_mission.route('/for-blueprint/<blueprint_uuid>', methods=['GET'])
@jwt_required()
def missions_for_blueprint(blueprint_uuid):
    """會給這張藍圖的任務（含掉落機率），玩家頁點藍圖名稱用。
    ---
    tags: [Mission]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: blueprint_uuid, type: string, required: true, description: "blueprint_master 的 uuid"}
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True,
                    'data': Mission.for_blueprint(blueprint_uuid, visible_only=not viewer_sees_hidden())})


@app_mission.route('/factions', methods=['GET'])
@jwt_required()
def list_factions():
    """全部勢力（不分頁，附任務數）。
    ---
    tags: [Mission]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': Faction.list_all()})


@app_mission.route('/factions/<faction_id>', methods=['GET'])
@jwt_required()
def get_faction(faction_id):
    """單一勢力＋它發布的任務。
    ---
    tags: [Mission]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: faction_id, type: string, required: true}
    responses:
      200:
        description: 成功
      404:
        description: 找不到勢力
    """
    doc = Faction.get(faction_id)
    if not doc:
        return jsonify({'success': False, 'message': '找不到勢力'}), 404
    return jsonify({'success': True, 'data': doc})


@app_mission.route('/<mission_id>', methods=['GET'])
@jwt_required()
def get_mission(mission_id):
    """單一任務。
    ---
    tags: [Mission]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: mission_id, type: string, required: true}
    responses:
      200:
        description: 成功
      404:
        description: 找不到任務
    """
    doc = Mission.get(mission_id)
    if not doc:
        return jsonify({'success': False, 'message': '找不到任務'}), 404
    return jsonify({'success': True, 'data': doc})
