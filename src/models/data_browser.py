"""後台「資料庫檢視」：把沒有專屬後台頁面的資料表（collection）原樣列出來，方便檢查同步進來的資料。

只開放下面 CATALOG 列的遊戲資料／同步紀錄（唯讀）；帳號、玩家、token、登入失敗這類資料一律不列。
列表的欄位是取前 SAMPLE 筆文件的頂層欄位（依出現順序），陣列／物件只回縮短的 JSON 預覽，
完整內容（含 raw）要點開單筆看（doc()）。
"""

import json
import re
from datetime import date, datetime
from typing import Optional

from bson import ObjectId

from src.mongo import get_db

#: 類別 → [(collection, 中文名稱)]
CATALOG = [
    ('物品／藍圖', [
        ('commodity_master', 'Wiki 商品主檔'),
        ('blueprint_quality_master', '藍圖品質試算資料'),
        ('uex_items', 'UEX 物品'),
        ('uex_items_prices', 'UEX 物品價格'),
    ]),
    ('載具', [
        ('uex_vehicles', 'UEX 載具'),
    ]),
    ('礦物／精煉', [
        ('mineral_uex_links', '礦物 UEX 手動關聯'),
        ('uex_commodities_raw_prices', 'UEX 原礦價格'),
        ('uex_refinery_yields', '精煉站產量加成'),
        ('uex_refinery_methods', '精煉方式'),
        ('uex_refinery_audits', '玩家精煉紀錄'),
        ('uex_refinery_capacities', '精煉站容量'),
    ]),
    ('任務／勢力', [
        ('mission_master', '任務主檔（含 raw）'),
        ('faction_master', '勢力主檔（含 raw）'),
    ]),
    ('翻譯', [
        ('sc_translations', '翻譯資料'),
        ('sc_translation_meta', '翻譯同步資訊'),
        ('chat_code_dictionary', '中文轉碼字典'),
    ]),
    ('系統', [
        ('sync_jobs', '同步項目'),
        ('sync_runs', '同步紀錄'),
        ('player_visibility', '玩家頁面顯示設定'),
    ]),
]
LABELS = {name: label for _, items in CATALOG for name, label in items}

SAMPLE = 100
MAX_LIMIT = 200
PREVIEW_CHARS = 160
#: 列表不列的欄位（太大或內部用）；點開單筆仍看得到
HIDDEN_IN_LIST = {'raw', '_sync'}
_FIELD_RE = re.compile(r'^[A-Za-z0-9_][A-Za-z0-9_.\-]*$')


def _plain(value):
    """轉成 JSON 可以表示的值（ObjectId、日期轉字串）。"""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, bytes):
        return f'<{len(value)} bytes>'
    return value


def _preview(value):
    value = _plain(value)
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
        return text if len(text) <= PREVIEW_CHARS else text[:PREVIEW_CHARS] + '…'
    if isinstance(value, str) and len(value) > PREVIEW_CHARS:
        return value[:PREVIEW_CHARS] + '…'
    return value


def _check(collection: str) -> str:
    if collection not in LABELS:
        raise KeyError(collection)
    return collection


def catalog() -> list:
    """[{category, collections: [{name, label, count}]}]"""
    db = get_db()
    return [{'category': cat, 'collections': [
        {'name': name, 'label': label, 'count': db[name].estimated_document_count()} for name, label in items]}
        for cat, items in CATALOG]


def columns(collection: str) -> list:
    """取前 SAMPLE 筆的頂層欄位（依出現順序，_id 第一）。"""
    out = ['_id']
    for doc in get_db()[_check(collection)].find({}).limit(SAMPLE):
        for key in doc:
            if key not in out and key not in HIDDEN_IN_LIST:
                out.append(key)
    return out


def _search_filter(cols: list, field: str, q: str) -> dict:
    q = (q or '').strip()
    if not q:
        return {}
    pattern = {'$regex': re.escape(q), '$options': 'i'}
    conds_for = lambda f: [{f: pattern}] + ([{f: _num(q)}] if _num(q) is not None else []) + ([{f: q}] if f == '_id' else [])
    if field:
        if field not in cols or not _FIELD_RE.match(field):
            raise ValueError('欄位不存在')
        conds = conds_for(field)
    else:
        conds = [c for f in cols for c in conds_for(f)]
    return {'$or': conds}


def _num(text: str):
    try:
        n = float(text)
    except ValueError:
        return None
    return int(n) if n.is_integer() else n


def list_docs(collection: str, *, field: str = '', q: str = '', sort_by: str = '', sort_dir: str = 'asc',
              limit: int = 50, offset: int = 0) -> dict:
    """{label, columns, rows, total}；rows 的陣列／物件值是縮短的 JSON 字串。"""
    cols = columns(collection)
    filt = _search_filter(cols, field, q)
    col = get_db()[collection]
    limit = max(1, min(int(limit or 50), MAX_LIMIT))
    offset = max(0, int(offset or 0))
    cursor = col.find(filt, {k: 0 for k in HIDDEN_IN_LIST})
    if sort_by:
        if sort_by not in cols:
            raise ValueError('欄位不存在')
        cursor = cursor.sort([(sort_by, -1 if sort_dir == 'desc' else 1), ('_id', 1)])
    else:
        cursor = cursor.sort('_id', 1)
    rows = [{k: _preview(v) for k, v in doc.items()} for doc in cursor.skip(offset).limit(limit)]
    return {'label': LABELS[collection], 'columns': cols, 'rows': rows,
            'total': col.count_documents(filt) if filt else col.estimated_document_count()}


def doc(collection: str, doc_id: str) -> Optional[dict]:
    """單筆完整內容（_id 可能是字串、數字或 ObjectId，依序試）。"""
    col = get_db()[_check(collection)]
    candidates = [doc_id]
    if re.fullmatch(r'-?\d+', doc_id or ''):
        candidates.append(int(doc_id))
    if ObjectId.is_valid(doc_id or ''):
        candidates.append(ObjectId(doc_id))
    for cid in candidates:
        found = col.find_one({'_id': cid})
        if found:
            return _plain(found)
    return None
