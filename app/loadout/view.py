"""配裝模擬 API（玩家頁「配裝模擬」）。

掛在 /item/loadout 底下（不另開頂層前綴，nginx 與 vite 的 API 前綴清單不用動，
見 frontend/vite.api-prefixes.mjs）。資料見 src/models/loadout.py。
"""

from flask import Blueprint, jsonify, request

from src.models import loadout
from src.permissions import public_api

app_loadout = Blueprint('app_loadout', __name__)


def _csv(name: str) -> list:
    return [v.strip() for v in (request.args.get(name) or '').split(',') if v.strip()]


@app_loadout.route('/ships', methods=['GET'])
@public_api
def loadout_ships():
    """可以配裝的船（名稱、廠商、尺寸、角色）。
    ---
    tags: [Loadout]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': loadout.ships()})


@app_loadout.route('/ships/<ship_id>', methods=['GET'])
@public_api
def loadout_ship(ship_id):
    """一艘船的掛點樹、船體／裝甲／飛行數值，附上預設配件。
    ---
    tags: [Loadout]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: ship_id, type: string, required: true}
    responses:
      200:
        description: 成功
      404:
        description: 找不到
    """
    doc = loadout.ship(ship_id)
    if not doc:
        return jsonify({'success': False, 'message': '找不到這艘船的配裝資料'}), 404
    return jsonify({'success': True, 'data': doc})


@app_loadout.route('/items', methods=['GET'])
@public_api
def loadout_items():
    """配件清單（types＝主類，逗號分隔，例如 WeaponGun,Turret；ids＝UUID，逗號分隔）。
    ---
    tags: [Loadout]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: types, type: string}
      - {in: query, name: ids, type: string}
    responses:
      200:
        description: 成功
    """
    types, ids = _csv('types'), _csv('ids')
    if not types and not ids:
        return jsonify({'success': False, 'message': '請指定 types 或 ids'}), 400
    return jsonify({'success': True, 'data': loadout.items(types=types, ids=ids)})
