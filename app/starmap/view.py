"""星圖地點資料庫（後台檢視用）。

資料由 tasks/scdata_sync.py 的「地點」同步項目從 scunpacked-data starmap.json 同步
（starmap_master），詳見 src/models/starmap.py。唯一可寫的是「可存放」的手動設定
（can_store_override，同步不會蓋掉）。
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from src.limiter import limiter
from src.models.log import Log
from src.models.starmap import FEATURE_KEYS, MAX_LIMIT, Starmap
from src.permissions import READ_ROLES, WRITE_ROLES, admin_api, visibility_arg

app_starmap = Blueprint('app_starmap', __name__)


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


@app_starmap.route('/', methods=['GET'])
@admin_api(*READ_ROLES)
def list_locations():
    """星圖地點列表（分頁）。
    ---
    tags: [Starmap]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: q,            type: string,  description: "名稱（中英文）／上層名稱關鍵字"}
      - {in: query, name: type,         type: string,  description: "類型，可重複帶多個（Planet、Outpost…）"}
      - {in: query, name: system,       type: string,  description: "所屬星系，可重複帶多個"}
      - {in: query, name: jurisdiction, type: string,  description: "管轄，可重複帶多個"}
      - {in: query, name: amenity,      type: string,  description: "設施，可重複帶多個（有其中任一個）"}
      - {in: query, name: feature,      type: string,  description: "屬性欄位（has_hangar、shop_weapons…），可重複帶多個（全部都要有）"}
      - {in: query, name: can_store,    type: integer, description: "1 = 只看可存放、0 = 只看不可存放"}
      - {in: query, name: player_visible, type: integer, description: "1 = 只看玩家頁面顯示的、0 = 只看不顯示的"}
      - {in: query, name: include_unnamed, type: integer, description: "1 = 也列出沒有名稱的（遊戲內部用的點）"}
      - {in: query, name: missing_zh,   type: integer, description: "1 = 只看沒有中文名稱的"}
      - {in: query, name: id,           type: string,  description: "指定單一地點"}
      - {in: query, name: parent,       type: string,  description: "只看某個地點底下的"}
      - {in: query, name: limit,        type: integer, default: 50, description: "最多 200"}
      - {in: query, name: offset,       type: integer, default: 0}
    responses:
      200:
        description: 成功
    """
    limit, offset = _paging()
    rows, total = Starmap.list_all(
        limit=limit, offset=offset,
        query=(request.args.get('q') or '').strip(),
        types=_multi('type'), systems=_multi('system'),
        jurisdictions=_multi('jurisdiction'), amenities=_multi('amenity'),
        features=[f for f in _multi('feature') if f in FEATURE_KEYS],
        can_store={'1': True, '0': False}.get(request.args.get('can_store')),
        visibility=visibility_arg(request.args),
        named_only=request.args.get('include_unnamed') != '1',
        missing_zh=request.args.get('missing_zh') == '1',
        location_id=(request.args.get('id') or '').strip(),
        parent_id=(request.args.get('parent') or '').strip(),
    )
    return jsonify({'success': True, 'data': rows, 'total': total, 'limit': limit, 'offset': offset})


@app_starmap.route('/storage-locations', methods=['GET'])
@limiter.limit('60 per minute')
def storage_locations():
    """可存放的地點（玩家站／後台的庫存地點下拉用）。

    公開、不需要 token：內容是公開的遊戲星圖資料（同 /item/translations）。
    ---
    tags: [Starmap]
    responses:
      200:
        description: 成功，data 是 [{name, name_zh, type, type_zh, system, system_zh, parent, parent_zh}]
    """
    return jsonify({'success': True, 'data': Starmap.storage_locations()})


@app_starmap.route('/facets', methods=['GET'])
@admin_api(*READ_ROLES)
def location_facets():
    """篩選下拉的選項：類型、星系、管轄、設施（含筆數）。
    ---
    tags: [Starmap]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': Starmap.facets()})


@app_starmap.route('/<location_id>', methods=['GET'])
@admin_api(*READ_ROLES)
def get_location(location_id):
    """單一地點＋它底下的地點。
    ---
    tags: [Starmap]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: location_id, type: string, required: true}
    responses:
      200:
        description: 成功
      404:
        description: 找不到地點
    """
    doc = Starmap.get(location_id)
    if not doc:
        return jsonify({'success': False, 'message': '找不到地點'}), 404
    return jsonify({'success': True, 'data': doc})


@app_starmap.route('/<location_id>/storage', methods=['PUT'])
@admin_api(*WRITE_ROLES)
def set_location_storage(location_id):
    """手動設定地點「可存放」（null = 回到自動判斷）。
    ---
    tags: [Starmap]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: location_id, type: string, required: true}
      - in: body
        name: body
        schema:
          type: object
          properties:
            can_store: {type: boolean, description: "true／false；null = 依設施自動判斷"}
    responses:
      200:
        description: 成功
      400:
        description: 格式錯誤
      404:
        description: 找不到地點
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or 'can_store' not in body:
        return jsonify({'success': False, 'message': '缺少 can_store'}), 400
    username = get_jwt_identity()
    try:
        doc = Starmap.set_storage_override(location_id, body['can_store'], username)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    if not doc:
        return jsonify({'success': False, 'message': '找不到地點'}), 404
    label = {True: '可存放', False: '不可存放', None: '自動'}[body['can_store']]
    Log.create(username, 'set_location_storage', f'地點 {location_id} 可存放設為{label}', success=True)
    return jsonify({'success': True, 'data': doc})
