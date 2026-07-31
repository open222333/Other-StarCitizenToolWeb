from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required
from src.models.log import Log

app_log = Blueprint('app_log', __name__)


@app_log.route('/', methods=['GET'])
@jwt_required()
def list_logs():
    limit    = min(request.args.get('limit', 200, type=int), 1000)
    offset   = max(request.args.get('offset', 0, type=int), 0)
    username = request.args.get('username', '').strip()
    logs     = Log.find_all(limit=limit, offset=offset, username=username)
    total    = Log.count(username=username)
    return jsonify({'success': True, 'data': logs, 'total': total, 'limit': limit, 'offset': offset})
