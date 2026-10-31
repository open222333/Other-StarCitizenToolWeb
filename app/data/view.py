"""後台「資料庫檢視」（唯讀）：資料表原樣列出（全部欄位、每欄可篩選），見 src/models/data_browser.py。"""

import json

from flask import Blueprint, jsonify, request

from src.models import data_browser
from src.permissions import READ_ROLES, admin_api

app_data = Blueprint('app_data', __name__)


@app_data.route('/collections', methods=['GET'])
@admin_api(*READ_ROLES)
def list_collections():
    """可以檢視的資料表，依類別分組（附筆數）。
    ---
    tags: [Data]
    security:
      - Bearer: []
    responses:
      200:
        description: "data: [{category, collections: [{name, label, count}]}]"
    """
    return jsonify({'success': True, 'data': data_browser.catalog()})


@app_data.route('/collections/<name>', methods=['GET'])
@admin_api(*READ_ROLES)
def list_documents(name):
    """某個資料表的文件（分頁）；欄位是取樣文件的全部欄位（物件展開成 a.b），陣列只給縮短的預覽。
    ---
    tags: [Data]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: name, type: string, required: true}
      - {in: query, name: field, type: string, description: "搜尋的欄位；空的＝全部欄位"}
      - {in: query, name: q, type: string, description: "關鍵字（不分大小寫的部分比對；數字也比對相等）"}
      - {in: query, name: sort_by, type: string}
      - {in: query, name: sort_dir, type: string, description: "asc／desc"}
      - {in: query, name: filters, type: string, description: "篩選條件 JSON：[{field, op, value}]，op 是 contains／not_contains／eq／ne／gt／gte／lt／lte／empty／not_empty，全部都要符合；field 可以是任何欄位路徑（例如 raw.class）"}
      - {in: query, name: limit, type: integer, default: 50}
      - {in: query, name: offset, type: integer, default: 0}
    responses:
      200:
        description: "data: {label, columns, rows, total}"
      400:
        description: 欄位不存在
      404:
        description: 不開放檢視的資料表
    """
    args = request.args
    try:
        filters = json.loads(args.get('filters') or '[]')
    except ValueError:
        return jsonify({'success': False, 'message': '篩選條件格式錯誤'}), 400
    try:
        limit = int(args.get('limit') or 50)
        offset = int(args.get('offset') or 0)
        data = data_browser.list_docs(name, field=args.get('field') or '', q=args.get('q') or '',
                                      sort_by=args.get('sort_by') or '', sort_dir=args.get('sort_dir') or 'asc',
                                      limit=limit, offset=offset, filters=filters)
    except KeyError:
        return jsonify({'success': False, 'message': '不開放檢視的資料表'}), 404
    except ValueError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    return jsonify({'success': True, 'data': data})


@app_data.route('/collections/<name>/doc', methods=['GET'])
@admin_api(*READ_ROLES)
def get_document(name):
    """單筆完整內容（含 raw）。
    ---
    tags: [Data]
    security:
      - Bearer: []
    parameters:
      - {in: path, name: name, type: string, required: true}
      - {in: query, name: id, type: string, required: true}
    responses:
      200:
        description: 成功
      404:
        description: 找不到
    """
    try:
        found = data_browser.doc(name, request.args.get('id') or '')
    except KeyError:
        return jsonify({'success': False, 'message': '不開放檢視的資料表'}), 404
    if found is None:
        return jsonify({'success': False, 'message': '找不到這筆資料'}), 404
    return jsonify({'success': True, 'data': found})
