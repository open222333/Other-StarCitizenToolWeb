"""API 金鑰管理（後台「API 金鑰」頁，只給 admin）：給外部程式呼叫寫入用的端點（目前是 POST /news/ingest）。

從「新聞」獨立出來：金鑰是全站共用的，每把金鑰有自己的權限（scope，見 src/models/api_key.py 的 SCOPES），
之後其他需要外部寫入的功能加一個 scope 就好，不用再動這裡。掛在 /data/api-keys（後台資料類前綴，不用新增 API 前綴）。
"""

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from src.models import api_key
from src.models.log import Log
from src.permissions import admin_api

app_api_key = Blueprint('app_api_key', __name__)


@app_api_key.route('', methods=['GET'])
@admin_api('admin')
def list_keys():
    """API 金鑰列表（不含金鑰本身，只有前 8 碼）。
    ---
    tags: [ApiKey]
    security:
      - Bearer: []
    responses:
      200:
        description: "data: [{_id, name, prefix, scopes, created_at, created_by, last_used_at, use_count, revoked}]、scopes: {權限: 說明}"
    """
    return jsonify({'success': True, 'data': api_key.list_keys(), 'scopes': api_key.SCOPES})


@app_api_key.route('', methods=['POST'])
@admin_api('admin')
def create_key():
    """建立 API 金鑰；回傳的 key 只有這一次看得到。
    ---
    tags: [ApiKey]
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required: [name]
          properties:
            name: {type: string, description: 名稱（例如「新聞爬蟲」）}
            scopes: {type: array, items: {type: string}, description: "權限（見 GET 回應的 scopes），至少一個"}
    responses:
      200:
        description: "data: {key, _id, name, prefix, scopes, …}"
      400:
        description: 欄位不合法
    """
    data = request.get_json(silent=True) or {}
    try:
        created = api_key.create(data.get('name'), data.get('scopes') or [], by=get_jwt_identity())
    except api_key.ApiKeyError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    Log.create(get_jwt_identity(), 'create_api_key', f'建立 API 金鑰「{created["name"]}」（{created["prefix"]}…）',
               success=True)
    return jsonify({'success': True, 'data': created})


@app_api_key.route('/<key_id>', methods=['DELETE'])
@admin_api('admin')
def revoke_key(key_id):
    """停用 API 金鑰（立刻失效，紀錄保留）。
    ---
    tags: [ApiKey]
    security:
      - Bearer: []
    parameters:
      - {name: key_id, in: path, type: string, required: true}
    responses:
      200:
        description: 已停用
      404:
        description: 找不到或已經停用
    """
    if not api_key.revoke(key_id, by=get_jwt_identity()):
        return jsonify({'success': False, 'message': '找不到這把金鑰，或已經停用'}), 404
    Log.create(get_jwt_identity(), 'revoke_api_key', f'停用 API 金鑰 {key_id}', success=True)
    return jsonify({'success': True})
