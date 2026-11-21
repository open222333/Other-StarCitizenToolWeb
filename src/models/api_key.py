"""外部程式用的 API 金鑰（目前只有「寫入新聞」一種權限，見 app/news/view.py 的 POST /news/ingest）。

金鑰長這樣：`sct_` ＋ 40 個十六進位字元，只在建立當下回傳一次；資料庫只存 SHA-256 雜湊
（跟密碼一樣，資料庫外洩也拿不到可用的金鑰）與前 8 碼（後台列表辨認用）。
呼叫時放在標頭 `X-API-Key: sct_…`（或 `Authorization: Bearer sct_…`）。
停用（revoked）是軟刪除：紀錄保留，金鑰立刻失效。
"""

import hashlib
import secrets
from datetime import datetime
from functools import wraps
from typing import Optional

from bson import ObjectId
from flask import g, jsonify, request

from src.mongo import get_db

COLLECTION = 'api_keys'
PREFIX = 'sct_'
#: 可以給的權限（scope → 說明）
SCOPES = {'news:write': '寫入新聞（POST /news/ingest）'}
MAX_NAME = 50


class ApiKeyError(ValueError):
    pass


def _col():
    return get_db()[COLLECTION]


def ensure_indexes(db=None):
    (db if db is not None else get_db())[COLLECTION].create_index('key_hash', unique=True)


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


def _public(doc: dict) -> dict:
    iso = lambda d: d.isoformat(timespec='seconds') + 'Z' if isinstance(d, datetime) else None  # noqa: E731
    return {'_id': str(doc['_id']), 'name': doc.get('name'), 'prefix': doc.get('prefix'),
            'scopes': doc.get('scopes') or [], 'created_at': iso(doc.get('created_at')),
            'created_by': doc.get('created_by'), 'last_used_at': iso(doc.get('last_used_at')),
            'use_count': doc.get('use_count') or 0, 'revoked': bool(doc.get('revoked_at')),
            'revoked_at': iso(doc.get('revoked_at'))}


def list_keys() -> list:
    return [_public(d) for d in _col().find({}).sort('created_at', -1)]


def create(name: str, scopes, by: str) -> dict:
    """建立金鑰，回傳 {key（只有這一次看得到）, ...列表欄位}。"""
    name = (name or '').strip() if isinstance(name, str) else ''
    if not name:
        raise ApiKeyError('請填金鑰名稱（例如「新聞爬蟲」）')
    if len(name) > MAX_NAME:
        raise ApiKeyError(f'名稱太長（最多 {MAX_NAME} 字）')
    scopes = [s for s in (scopes or []) if isinstance(s, str)]
    if not scopes or any(s not in SCOPES for s in scopes):
        raise ApiKeyError(f'權限只能是：{"、".join(SCOPES)}')
    key = PREFIX + secrets.token_hex(20)
    doc = {'name': name, 'key_hash': _hash(key), 'prefix': key[:len(PREFIX) + 8], 'scopes': sorted(set(scopes)),
           'created_at': datetime.utcnow(), 'created_by': by, 'last_used_at': None, 'use_count': 0,
           'revoked_at': None}
    doc['_id'] = _col().insert_one(doc).inserted_id
    return {'key': key, **_public(doc)}


def revoke(key_id, by: str) -> bool:
    try:
        oid = ObjectId(str(key_id))
    except Exception:
        return False
    return _col().update_one({'_id': oid, 'revoked_at': None},
                             {'$set': {'revoked_at': datetime.utcnow(), 'revoked_by': by}}).matched_count > 0


def verify(key: str, scope: str) -> Optional[dict]:
    """金鑰有效而且有這個權限 → 金鑰紀錄（順便記最後使用時間）；否則 None。"""
    key = (key or '').strip()
    if not key.startswith(PREFIX):
        return None
    doc = _col().find_one({'key_hash': _hash(key), 'revoked_at': None})
    if not doc or scope not in (doc.get('scopes') or []):
        return None
    _col().update_one({'_id': doc['_id']}, {'$set': {'last_used_at': datetime.utcnow()}, '$inc': {'use_count': 1}})
    return doc


def key_from_request() -> str:
    key = request.headers.get('X-API-Key') or ''
    if not key:
        auth = request.headers.get('Authorization') or ''
        if auth.lower().startswith('bearer ') and auth[7:].strip().startswith(PREFIX):
            key = auth[7:].strip()
    return key.strip()


def api_key_required(scope: str):
    """外部程式用的端點：要帶有這個權限的 API 金鑰（X-API-Key）。g.api_key 是金鑰紀錄。"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = key_from_request()
            if not key:
                return jsonify({'success': False, 'message': '缺少 API 金鑰（X-API-Key）'}), 401
            doc = verify(key, scope)
            if not doc:
                return jsonify({'success': False, 'message': 'API 金鑰無效、已停用，或沒有這個權限'}), 403
            g.api_key = doc
            return fn(*args, **kwargs)
        return wrapper
    return decorator
