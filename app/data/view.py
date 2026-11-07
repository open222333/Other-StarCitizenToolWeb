"""後台「資料庫檢視」（唯讀）：資料表原樣列出（全部欄位、每欄可篩選），見 src/models/data_browser.py。"""

import json
from datetime import datetime

from flask import Blueprint, Response, jsonify, request
from flask_jwt_extended import get_jwt_identity

from src import backup
from src.models import data_browser
from src.models.log import Log
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


# ═══════════════════════════════════════════
#  資料備份：匯出／匯入還原「不是同步排程抓來的」資料（見 src/backup.py），只有 admin 可以用
# ═══════════════════════════════════════════

@app_data.route('/backup/sets', methods=['GET'])
@admin_api('admin')
def backup_sets():
    """可以匯出／還原的資料（每一組的資料表與目前筆數）。
    ---
    tags: [Data]
    security:
      - Bearer: []
    responses:
      200:
        description: "data: [{key, label, default, collections: [{name, count}]}]"
    """
    return jsonify({'success': True, 'data': backup.list_sets()})


@app_data.route('/backup/export', methods=['GET'])
@admin_api('admin')
def backup_export():
    """匯出成 gzip 壓縮的 JSON 下載（含密碼雜湊、token，檔案要自己保管好）。
    ---
    tags: [Data]
    security:
      - Bearer: []
    parameters:
      - {in: query, name: set, type: string, required: true, description: "要匯出的資料（backup/sets 的 key），可重複帶多個"}
    responses:
      200:
        description: 備份檔（application/gzip）
      400:
        description: 沒選或選了不存在的資料
    """
    keys = request.args.getlist('set')
    try:
        body = backup.export_gzip(keys)
    except backup.BackupError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    Log.create(get_jwt_identity(), 'backup_export', detail=','.join(keys))
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    return Response(body, mimetype='application/gzip', headers={
        'Content-Disposition': f'attachment; filename="sc-tool-backup-{stamp}.json.gz"',
    })


@app_data.route('/backup/import', methods=['POST'])
@admin_api('admin')
def backup_import():
    """匯入還原：選的那幾組資料表整個換成備份檔的內容。dry_run=1 只讀檔回摘要，不寫入。
    ---
    tags: [Data]
    security:
      - Bearer: []
    consumes: [multipart/form-data]
    parameters:
      - {in: formData, name: file, type: file, required: true, description: "匯出的備份檔（.json.gz 或 .json）"}
      - {in: formData, name: set, type: string, description: "要還原的資料，可重複帶多個（dry_run 時不用）"}
      - {in: formData, name: dry_run, type: string, description: "1＝只回摘要"}
    responses:
      200:
        description: "dry_run：data 是摘要；否則 data.restored 是 {資料表: 筆數}"
      400:
        description: 檔案不對、備份檔裡沒有選的資料、或還原後自己會登不進來
    """
    upload = request.files.get('file')
    if not upload:
        return jsonify({'success': False, 'message': '請選擇備份檔'}), 400
    try:
        data = backup.load_file(upload.read())
        if (request.form.get('dry_run') or '') in ('1', 'true'):
            return jsonify({'success': True, 'data': backup.summary(data)})
        keys = request.form.getlist('set')
        counts = backup.restore(data, keys, keep_username=get_jwt_identity())
    except backup.BackupError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    Log.create(get_jwt_identity(), 'backup_import', detail=json.dumps(counts, ensure_ascii=False))
    return jsonify({'success': True, 'data': {'restored': counts}})

