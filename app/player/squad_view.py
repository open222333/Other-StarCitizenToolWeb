"""戰術小隊分配表 API（玩家頁「工具箱 › 戰術小隊」）。

掛在 /player/squads（沿用 /player 前綴，nginx 與 vite 的 API 前綴清單不用動）。
登入玩家都能建立、看全部的表；只有建立者能改、刪、設定分享。
/player/squads/shared/<碼> 不用登入（知道分享連結就能看，唯讀）。
資料見 src/models/squad.py。
"""

from flask import Blueprint, g, jsonify, request

from app.player.view import player_required
from src.limiter import limiter
from src.models.log import Log
from src.models.squad import SquadBoard, SquadConflict, SquadError

app_squad = Blueprint('app_squad', __name__)


@app_squad.errorhandler(SquadError)
def handle_squad_error(err):
    return jsonify({'success': False, 'message': str(err)}), 400


def _me() -> str:
    return g.player_doc.get('star_citizen_id')


def _actor() -> str:
    return f'player:{_me()}'


def _board_or_404(board_id):
    doc = SquadBoard.get(board_id)
    if not doc:
        return None, (jsonify({'success': False, 'message': '找不到這張分配表'}), 404)
    return doc, None


def _owned_or_error(board_id):
    doc, err = _board_or_404(board_id)
    if err:
        return None, err
    if doc.get('owner_scid') != _me():
        return None, (jsonify({'success': False, 'message': '只有建立者可以修改這張分配表'}), 403)
    return doc, None


@app_squad.route('', methods=['GET'])
@player_required
def list_squad_boards():
    """全部的分配表（只有統計數字）。
    ---
    tags: [Squad]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': SquadBoard.list_all()})


@app_squad.route('', methods=['POST'])
@player_required
@limiter.limit('30 per minute')
def create_squad_board():
    """新增分配表；帶 copy_from（另一張表的 id）就複製那張。
    ---
    tags: [Squad]
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          properties:
            title: {type: string}
            copy_from: {type: string}
    responses:
      200:
        description: 成功
    """
    data = request.get_json(silent=True) or {}
    source = None
    if data.get('copy_from'):
        source, err = _board_or_404(data['copy_from'])
        if err:
            return err
    doc = SquadBoard.create(_me(), data, copy_from=source)
    Log.create(_actor(), 'create_squad_board',
               f'新增戰術小隊分配表「{doc["title"]}」' + ('（複製）' if source else ''))
    return jsonify({'success': True, 'data': SquadBoard.view(doc, _me())})


@app_squad.route('/<board_id>', methods=['GET'])
@player_required
def get_squad_board(board_id):
    """一張表的完整內容（附 can_edit）。
    ---
    tags: [Squad]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    doc, err = _board_or_404(board_id)
    if err:
        return err
    return jsonify({'success': True, 'data': SquadBoard.view(doc, _me())})


@app_squad.route('/<board_id>', methods=['PUT'])
@player_required
@limiter.limit('60 per minute')
def save_squad_board(board_id):
    """整張儲存（只有建立者）；rev 跟資料庫不同回 409。
    ---
    tags: [Squad]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
      409:
        description: 已經被別的視窗改過
    """
    doc, err = _owned_or_error(board_id)
    if err:
        return err
    try:
        doc = SquadBoard.save(doc, request.get_json(silent=True) or {}, _me())
    except SquadConflict:
        return jsonify({'success': False, 'message': '這張表已經在別的視窗改過，請重新載入'}), 409
    Log.create(_actor(), 'save_squad_board', f'儲存戰術小隊分配表「{doc["title"]}」')
    return jsonify({'success': True, 'data': SquadBoard.view(doc, _me())})


@app_squad.route('/<board_id>', methods=['DELETE'])
@player_required
def delete_squad_board(board_id):
    """刪除（只有建立者）。
    ---
    tags: [Squad]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    doc, err = _owned_or_error(board_id)
    if err:
        return err
    SquadBoard.delete(doc)
    Log.create(_actor(), 'delete_squad_board', f'刪除戰術小隊分配表「{doc.get("title")}」')
    return jsonify({'success': True})


@app_squad.route('/<board_id>/share', methods=['POST'])
@player_required
@limiter.limit('30 per minute')
def share_squad_board(board_id):
    """開關分享連結、重新產生分享碼（只有建立者）。
    ---
    tags: [Squad]
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          properties:
            enabled: {type: boolean}
            regenerate: {type: boolean}
    responses:
      200:
        description: 成功
    """
    doc, err = _owned_or_error(board_id)
    if err:
        return err
    data = request.get_json(silent=True) or {}
    token = SquadBoard.set_share(doc, bool(data.get('enabled')), bool(data.get('regenerate')))
    action = '關閉分享' if not token else ('重新產生分享連結' if data.get('regenerate') else '開啟分享')
    Log.create(_actor(), 'share_squad_board', f'戰術小隊分配表「{doc.get("title")}」{action}')
    return jsonify({'success': True, 'data': {'share_token': token}})


@app_squad.route('/shared/<token>', methods=['GET'])
@limiter.limit('60 per minute')
def shared_squad_board(token):
    """分享連結的公開頁資料（不用登入，唯讀；只回白名單欄位）。
    ---
    tags: [Squad]
    responses:
      200:
        description: 成功
      404:
        description: 連結不存在或已關閉
    """
    doc = SquadBoard.find_shared(token)
    if not doc:
        return jsonify({'success': False, 'message': '這個連結已失效'}), 404
    return jsonify({'success': True, 'data': SquadBoard.public_view(doc)})
