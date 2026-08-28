from flask import Blueprint, jsonify, request
from src.models.log import Log
from src.permissions import READ_ROLES, admin_api

app_log = Blueprint('app_log', __name__)


@app_log.route('/', methods=['GET'])
@admin_api(*READ_ROLES)
def list_logs():
    """後台操作稽核紀錄。

    內容包含後台帳號名稱、登入成功／失敗紀錄與庫存異動明細，
    所以必須是後台帳號才能讀（玩家自助 token 會被 admin_api 擋掉）。
    """
    limit    = min(request.args.get('limit', 200, type=int), 200)
    offset   = max(request.args.get('offset', 0, type=int), 0)
    username = request.args.get('username', '').strip()
    logs     = Log.find_all(limit=limit, offset=offset, username=username)
    total    = Log.count(username=username)
    return jsonify({'success': True, 'data': logs, 'total': total, 'limit': limit, 'offset': offset})
