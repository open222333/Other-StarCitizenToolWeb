"""工具網站連結的後台管理（新增／修改／刪除）。

玩家頁讀取走 /player/tool-links（app/player/view.py，需要玩家 token），
這裡是後台專用，一律 admin_api()。
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from src.models.log import Log
from src.models.tool_link import ToolLink, ToolLinkError
from src.permissions import READ_ROLES, WRITE_ROLES, admin_api

app_links = Blueprint('app_links', __name__)


@app_links.errorhandler(ToolLinkError)
def handle_tool_link_error(err):
    return jsonify({'success': False, 'message': str(err)}), 400


@app_links.route('/', methods=['GET'])
@admin_api(*READ_ROLES)
def list_links():
    """工具網站連結列表（後台）。
    ---
    tags: [Links]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    # tags：標籤的順序（玩家頁依標籤分組、後台標籤欄位的建議都照這個）
    return jsonify({'success': True, 'data': ToolLink.list_all(), 'tags': ToolLink.tags()})


@app_links.route('/', methods=['POST'])
@admin_api(*WRITE_ROLES)
def create_link():
    """新增工具網站連結。
    ---
    tags: [Links]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          required: [title, url]
          properties:
            title:       {type: string}
            url:         {type: string, description: "http:// 或 https://；沒寫的話補 https://"}
            description: {type: string}
            sort_order:  {type: integer, description: "越小越前面"}
            tags:        {type: array, items: {type: string}, description: "標籤，一個網址可以有好幾個（最多 10 個）"}
    responses:
      201:
        description: 成功
      400:
        description: 欄位不合法
    """
    data = request.get_json(silent=True) or {}
    username = get_jwt_identity()
    link_id = ToolLink.create(data, username=username)
    Log.create(username, 'create_tool_link', f'新增工具網站：{data.get("title", "")}', success=True)
    return jsonify({'success': True, 'id': link_id}), 201


@app_links.route('/export', methods=['GET'])
@admin_api(*READ_ROLES)
def export_links():
    """匯出全部工具網站連結（JSON，可直接拿來匯入）。
    ---
    tags: [Links]
    security:
      - Bearer: []
    responses:
      200:
        description: '{"version": 1, "links": [{"title", "url", "description", "sort_order"}]}'
    """
    return jsonify({'success': True, 'data': ToolLink.export()})


@app_links.route('/import', methods=['POST'])
@admin_api(*WRITE_ROLES)
def import_links():
    """JSON 批量匯入工具網站連結。
    ---
    tags: [Links]
    security:
      - Bearer: []
    parameters:
      - in: body
        schema:
          properties:
            data:    {type: object, description: '匯出檔的內容：{"links": [...]} 或直接一個陣列'}
            replace: {type: boolean, description: "true = 檔案裡沒有的現有連結會被刪除"}
    responses:
      200:
        description: 成功，回傳新增／更新／刪除筆數
      400:
        description: 格式或欄位不合法（整批不寫入）
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or 'data' not in body:
        return jsonify({'success': False, 'message': '請帶 {"data": <JSON 檔內容>}'}), 400
    username = get_jwt_identity()
    result = ToolLink.import_links(body['data'], username=username, replace=bool(body.get('replace')))
    Log.create(username, 'import_tool_links',
               f'匯入工具網站：新增 {result["created"]}、更新 {result["updated"]}、刪除 {result["deleted"]}',
               success=True)
    return jsonify({'success': True, 'data': result})


@app_links.route('/<link_id>', methods=['PUT'])
@admin_api(*WRITE_ROLES)
def update_link(link_id):
    """修改工具網站連結（只更新有帶的欄位）。
    ---
    tags: [Links]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
      400:
        description: 欄位不合法
      404:
        description: 找不到
    """
    data = request.get_json(silent=True) or {}
    if not ToolLink.update(link_id, data):
        return jsonify({'success': False, 'message': '找不到這筆工具網站'}), 404
    Log.create(get_jwt_identity(), 'update_tool_link', f'修改工具網站 {link_id}', success=True)
    return jsonify({'success': True})


@app_links.route('/<link_id>', methods=['DELETE'])
@admin_api(*WRITE_ROLES)
def delete_link(link_id):
    """刪除工具網站連結（軟刪除）。
    ---
    tags: [Links]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
      404:
        description: 找不到
    """
    if not ToolLink.soft_delete(link_id):
        return jsonify({'success': False, 'message': '找不到這筆工具網站'}), 404
    Log.create(get_jwt_identity(), 'delete_tool_link', f'刪除工具網站 {link_id}', success=True)
    return jsonify({'success': True})
