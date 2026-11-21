"""新聞（src/models/news.py）：玩家頁讀（公開）、後台管理（後台帳號）、外部程式寫入（API 金鑰）。

    GET    /news/                 公開：已發布的新聞（置頂在前），tag、q、limit、offset、pinned=1
    GET    /news/tags             公開：標籤與數量
    GET    /news/<id>             公開：一則全文
    GET    /news/admin            後台：全部（含排程中的）
    POST   /news/admin            後台：新增
    PUT    /news/admin/<id>       後台：修改
    DELETE /news/admin/<id>       後台：刪除（軟刪除）
    POST   /news/ingest           外部：API 金鑰（X-API-Key，權限 news:write）寫入一則或多則，來源連結相同就更新
    GET/POST /news/keys、DELETE /news/keys/<id>   後台 admin：API 金鑰管理（金鑰只在建立時回傳一次）
"""

from flask import Blueprint, g, jsonify, request
from flask_jwt_extended import get_jwt_identity

from src.limiter import limiter
from src.models import api_key, news
from src.models.log import Log
from src.permissions import READ_ROLES, WRITE_ROLES, admin_api, public_api

app_news = Blueprint('app_news', __name__)


def _int(name, default):
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


@app_news.route('/', methods=['GET'])
@public_api
def list_public():
    """已發布的新聞（玩家頁）。
    ---
    tags: [News]
    parameters:
      - {name: tag, in: query, type: string, description: 只看這個標籤}
      - {name: q, in: query, type: string, description: 搜尋標題、內文、標籤}
      - {name: pinned, in: query, type: string, description: "1＝只看置頂"}
      - {name: limit, in: query, type: integer, default: 20, description: 每頁幾則（最多 100）}
      - {name: offset, in: query, type: integer, default: 0}
    responses:
      200:
        description: "data: [{_id, title, excerpt, cover_url, source_url, tags, pinned, published_at}]、total"
    """
    rows, total = news.list_news(public=True, tag=request.args.get('tag', ''), q=request.args.get('q', ''),
                                 limit=_int('limit', 20), offset=_int('offset', 0),
                                 pinned_only=request.args.get('pinned') == '1')
    return jsonify({'success': True, 'data': rows, 'total': total})


@app_news.route('/tags', methods=['GET'])
@public_api
def list_tags():
    """新聞標籤與數量（玩家頁篩選用）。
    ---
    tags: [News]
    responses:
      200:
        description: "data: [{tag, count}]"
    """
    return jsonify({'success': True, 'data': news.tags(public=True)})


@app_news.route('/<news_id>', methods=['GET'])
@public_api
def get_public(news_id):
    """一則新聞全文（Markdown）。
    ---
    tags: [News]
    parameters:
      - {name: news_id, in: path, type: string, required: true}
    responses:
      200:
        description: "data: {_id, title, body, cover_url, source_url, tags, pinned, published_at}"
      404:
        description: 找不到（或還沒到發布時間）
    """
    doc = news.get(news_id, public=True)
    if not doc:
        return jsonify({'success': False, 'message': '找不到這則新聞'}), 404
    return jsonify({'success': True, 'data': doc})


# ── 後台 ──────────────────────────────────────────────────────────

@app_news.route('/admin', methods=['GET'])
@admin_api(*READ_ROLES)
def list_admin():
    """後台：全部新聞（含還沒到發布時間的）。
    ---
    tags: [News]
    security:
      - Bearer: []
    parameters:
      - {name: tag, in: query, type: string}
      - {name: q, in: query, type: string}
      - {name: limit, in: query, type: integer, default: 50}
      - {name: offset, in: query, type: integer, default: 0}
    responses:
      200:
        description: "data: [{_id, title, body, cover_url, source_url, tags, pinned, published_at, scheduled, created_by, …}]、total"
    """
    rows, total = news.list_news(public=False, tag=request.args.get('tag', ''), q=request.args.get('q', ''),
                                 limit=_int('limit', 50), offset=_int('offset', 0))
    return jsonify({'success': True, 'data': rows, 'total': total, 'tags': news.tags(public=False)})


@app_news.route('/admin', methods=['POST'])
@admin_api(*WRITE_ROLES)
def create_admin():
    """後台：新增一則新聞。
    ---
    tags: [News]
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required: [title]
          properties:
            title: {type: string, description: 標題（必填，最多 200 字）}
            body: {type: string, description: 內文（Markdown）}
            cover_url: {type: string, description: 封面圖片網址}
            source_url: {type: string, description: 來源連結}
            tags: {type: array, items: {type: string}}
            pinned: {type: boolean}
            published_at: {type: string, description: "ISO 8601；空的＝現在"}
    responses:
      200:
        description: "data: {_id}"
      400:
        description: 欄位不合法
    """
    try:
        new_id = news.create(request.get_json(silent=True) or {}, by=get_jwt_identity())
    except news.NewsError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    Log.create(get_jwt_identity(), 'create_news', f'新增新聞 {new_id}', success=True)
    return jsonify({'success': True, 'data': {'_id': new_id}})


@app_news.route('/admin/<news_id>', methods=['PUT'])
@admin_api(*WRITE_ROLES)
def update_admin(news_id):
    """後台：修改一則新聞（只改有送的欄位）。
    ---
    tags: [News]
    security:
      - Bearer: []
    parameters:
      - {name: news_id, in: path, type: string, required: true}
      - in: body
        name: body
        schema:
          type: object
          properties:
            title: {type: string}
            body: {type: string}
            cover_url: {type: string}
            source_url: {type: string}
            tags: {type: array, items: {type: string}}
            pinned: {type: boolean}
            published_at: {type: string}
    responses:
      200:
        description: 已更新
      400:
        description: 欄位不合法
      404:
        description: 找不到
    """
    try:
        ok = news.update(news_id, request.get_json(silent=True) or {}, by=get_jwt_identity())
    except news.NewsError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    if not ok:
        return jsonify({'success': False, 'message': '找不到這則新聞'}), 404
    Log.create(get_jwt_identity(), 'update_news', f'修改新聞 {news_id}', success=True)
    return jsonify({'success': True})


@app_news.route('/admin/<news_id>', methods=['DELETE'])
@admin_api(*WRITE_ROLES)
def delete_admin(news_id):
    """後台：刪除一則新聞（軟刪除）。
    ---
    tags: [News]
    security:
      - Bearer: []
    parameters:
      - {name: news_id, in: path, type: string, required: true}
    responses:
      200:
        description: 已刪除
      404:
        description: 找不到
    """
    if not news.delete(news_id, by=get_jwt_identity()):
        return jsonify({'success': False, 'message': '找不到這則新聞'}), 404
    Log.create(get_jwt_identity(), 'delete_news', f'刪除新聞 {news_id}', success=True)
    return jsonify({'success': True})


# ── 外部寫入（API 金鑰） ──────────────────────────────────────────

@app_news.route('/ingest', methods=['POST'])
@limiter.limit('60 per minute')
@api_key.api_key_required('news:write')
def ingest():
    """外部程式寫入新聞：標頭帶 `X-API-Key: sct_…`（後台「新聞 › API 金鑰」建立，權限 news:write）。
    內容是一則（物件）或多則（陣列，最多 50 則）；有 source_url 而且已經有同一個來源連結的新聞＝更新，否則新增。
    任何一則不合法整批不寫入。
    ---
    tags: [News]
    parameters:
      - {name: X-API-Key, in: header, type: string, required: true, description: "API 金鑰（sct_ 開頭）"}
      - in: body
        name: body
        description: 一則新聞，或新聞陣列
        schema:
          type: object
          required: [title]
          properties:
            title: {type: string, description: 標題（必填）}
            body: {type: string, description: 內文（Markdown）}
            cover_url: {type: string}
            source_url: {type: string, description: 來源連結（同一個來源連結再送一次＝更新）}
            tags: {type: array, items: {type: string}}
            pinned: {type: boolean}
            published_at: {type: string, description: "ISO 8601；空的＝現在"}
    responses:
      200:
        description: "data: {created: [id], updated: [id]}"
      400:
        description: 內容不合法（訊息會指出第幾則）
      401:
        description: 沒帶 API 金鑰
      403:
        description: 金鑰無效、已停用或沒有 news:write 權限
    """
    by = f'api:{g.api_key.get("name")}'
    try:
        result = news.ingest(request.get_json(silent=True), by=by)
    except news.NewsError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    Log.create(by, 'ingest_news', f'外部寫入新聞：新增 {len(result["created"])}、更新 {len(result["updated"])}',
               success=True)
    return jsonify({'success': True, 'data': result})


# ── API 金鑰管理（只給 admin） ────────────────────────────────────

@app_news.route('/keys', methods=['GET'])
@admin_api('admin')
def list_keys():
    """API 金鑰列表（不含金鑰本身，只有前 8 碼）。
    ---
    tags: [News]
    security:
      - Bearer: []
    responses:
      200:
        description: "data: [{_id, name, prefix, scopes, created_at, created_by, last_used_at, use_count, revoked}]、scopes: {權限: 說明}"
    """
    return jsonify({'success': True, 'data': api_key.list_keys(), 'scopes': api_key.SCOPES})


@app_news.route('/keys', methods=['POST'])
@admin_api('admin')
def create_key():
    """建立 API 金鑰；回傳的 key 只有這一次看得到。
    ---
    tags: [News]
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
            scopes: {type: array, items: {type: string}, description: "權限，目前只有 news:write（預設）"}
    responses:
      200:
        description: "data: {key, _id, name, prefix, scopes, …}"
      400:
        description: 欄位不合法
    """
    data = request.get_json(silent=True) or {}
    try:
        created = api_key.create(data.get('name'), data.get('scopes') or ['news:write'], by=get_jwt_identity())
    except api_key.ApiKeyError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    Log.create(get_jwt_identity(), 'create_api_key', f'建立 API 金鑰「{created["name"]}」（{created["prefix"]}…）',
               success=True)
    return jsonify({'success': True, 'data': created})


@app_news.route('/keys/<key_id>', methods=['DELETE'])
@admin_api('admin')
def revoke_key(key_id):
    """停用 API 金鑰（立刻失效，紀錄保留）。
    ---
    tags: [News]
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
