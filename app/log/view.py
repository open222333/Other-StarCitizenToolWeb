from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from src.models.log import Log
from src.permissions import READ_ROLES, admin_api

app_log = Blueprint('app_log', __name__)

_SUCCESS_TRUE = {'1', 'true', 'yes'}
_SUCCESS_FALSE = {'0', 'false', 'no'}


def _success_filter():
    """把「結果」的成功／失敗兩個 checkbox 轉成單一 Optional[bool]。

    兩個都勾、或兩個都沒勾，都代表「不篩」——不能把「兩個都勾」誤判成
    「什麼都不符合」，那樣使用者會以為介面壞了（畫面突然空掉）。
    """
    raw = {v.strip().lower() for v in request.args.getlist('success') if v.strip()}
    is_true = bool(raw & _SUCCESS_TRUE)
    is_false = bool(raw & _SUCCESS_FALSE)
    if is_true and not is_false:
        return True
    if is_false and not is_true:
        return False
    return None


def _parse_dt(raw: str):
    """時間範圍篩選用。壞格式直接當沒填，不要讓整支 API 500。

    前端 <input type="datetime-local"> 轉出來的值經過 `Date.toISOString()`
    會帶 Z 結尾（例如 2026-09-18T02:00:00.000Z），但 Python 3.10 的
    `datetime.fromisoformat` 不吃 Z（3.11 才支援），要自己換成 +00:00。
    轉完是 tz-aware，created_at 存的是 `datetime.utcnow()`（naive UTC），
    兩者比較前要統一成 naive，不然 mongomock／部分驅動比較會出錯。
    """
    raw = (raw or '').strip()
    if not raw:
        return None
    if raw.endswith('Z'):
        raw = raw[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


@app_log.route('/', methods=['GET'])
@admin_api(*READ_ROLES)
def list_logs():
    """後台操作稽核紀錄。
    ---
    tags: [Log]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: username, type: array, items: {type: string}, description: "操作者，可重複帶多個（多選）"}
      - {in: query, name: action,   type: array, items: {type: string}, description: "動作，可重複帶多個（多選）"}
      - {in: query, name: success,  type: array, items: {type: string}, description: "結果，1/0 可重複帶（都帶或都不帶＝不篩）"}
      - {in: query, name: since,    type: string, description: "只看這個時間之後（ISO 格式）"}
      - {in: query, name: until,    type: string, description: "只看這個時間之前（ISO 格式）"}
      - {in: query, name: sort_dir, type: string, enum: [asc, desc], default: desc, description: "依時間排序方向"}
      - {in: query, name: limit,    type: integer, default: 200, description: "最多 200"}
      - {in: query, name: offset,   type: integer, default: 0}
    responses:
      200:
        description: 成功
    """
    limit  = min(request.args.get('limit', 200, type=int), 200)
    offset = max(request.args.get('offset', 0, type=int), 0)

    usernames = [u.strip() for u in request.args.getlist('username') if u.strip()]
    actions   = [a.strip() for a in request.args.getlist('action') if a.strip()]
    success   = _success_filter()
    since     = _parse_dt(request.args.get('since', ''))
    until     = _parse_dt(request.args.get('until', ''))
    sort_dir  = 1 if (request.args.get('sort_dir') or 'desc').strip().lower() == 'asc' else -1

    logs = Log.find_all(limit=limit, offset=offset, usernames=usernames, actions=actions,
                         success=success, since=since, until=until, sort_dir=sort_dir)
    total = Log.count(usernames=usernames, actions=actions, success=success,
                       since=since, until=until)
    return jsonify({'success': True, 'data': logs, 'total': total, 'limit': limit, 'offset': offset})


@app_log.route('/usernames', methods=['GET'])
@admin_api(*READ_ROLES)
def list_usernames():
    """「操作者」多選篩選的選項清單。

    不能用 GET /user/ 代替 —— 那份只有註冊過的後台帳號，漏掉 `unknown`
    （登入失敗）與 `player:<遊戲ID>`（玩家自助動作）這兩種也會出現在
    紀錄裡的值。見 src/models/log.py 檔頭說明。
    ---
    tags: [Log]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': Log.distinct_usernames()})


@app_log.route('/actions', methods=['GET'])
@admin_api(*READ_ROLES)
def list_actions():
    """「動作」多選篩選的選項清單（從實際資料 distinct，不是手動維護的列舉）。
    ---
    tags: [Log]
    security:
      - Bearer: []
    responses:
      200:
        description: 成功
    """
    return jsonify({'success': True, 'data': Log.distinct_actions()})
