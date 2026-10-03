"""工具網站連結（後台維護、玩家頁「工具網站」分頁顯示）。

每筆是一個外部網站：標題、網址、說明（玩家頁收在問號裡），加上排序值。
刪除一律軟刪除（開發原則：重要資料不永久刪除）。

⚠️ 網址只接受 http:// 或 https://。玩家頁會把它做成可以點的連結，
`javascript:alert(1)` 這種網址一點就會在玩家的瀏覽器裡執行 —— 後台帳號
（或被盜的後台帳號）就能拿到所有玩家的登入 token。所以一定在寫入時擋，
不能只靠前端表單。
"""

from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from bson import ObjectId
from pymongo import ASCENDING

from src.mongo import get_db

MAX_TITLE = 100
MAX_URL = 2000
MAX_DESCRIPTION = 2000
#: JSON 批量匯入一次最多幾筆
MAX_IMPORT = 500
#: 匯出檔的格式版本（之後欄位有變動時用來判斷）
EXPORT_VERSION = 1


class ToolLinkError(ValueError):
    """輸入不合法（標題空白、網址不是 http/https…），訊息可以直接給使用者看。"""


def normalize_url(url: str) -> str:
    """去掉前後空白並檢查網址；沒寫 scheme 的補上 https://。不合法就丟 ToolLinkError。"""
    url = (url or '').strip()
    if not url:
        raise ToolLinkError('網址不得為空')
    if len(url) > MAX_URL:
        raise ToolLinkError(f'網址太長（最多 {MAX_URL} 字）')
    if '://' not in url and ':' not in url.split('/', 1)[0]:
        url = 'https://' + url
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc:
        raise ToolLinkError('網址必須是 http:// 或 https:// 開頭的網站')
    if any(ch.isspace() for ch in url):
        raise ToolLinkError('網址不能包含空白')
    return url


def _clean(data: dict, *, partial: bool = False) -> dict:
    """驗證並整理表單欄位。partial=True（更新）時只處理有帶的欄位。"""
    out: dict = {}
    if not partial or 'title' in data:
        title = str(data.get('title') or '').strip()
        if not title:
            raise ToolLinkError('標題不得為空')
        if len(title) > MAX_TITLE:
            raise ToolLinkError(f'標題太長（最多 {MAX_TITLE} 字）')
        out['title'] = title
    if not partial or 'url' in data:
        out['url'] = normalize_url(str(data.get('url') or ''))
    if not partial or 'description' in data:
        description = str(data.get('description') or '').strip()
        if len(description) > MAX_DESCRIPTION:
            raise ToolLinkError(f'說明太長（最多 {MAX_DESCRIPTION} 字）')
        out['description'] = description
    if not partial or 'sort_order' in data:
        try:
            out['sort_order'] = int(data.get('sort_order') or 0)
        except (TypeError, ValueError):
            raise ToolLinkError('排序必須是整數')
    return out


class ToolLink:
    COLLECTION = 'tool_links'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @staticmethod
    def _serialize(doc: dict) -> dict:
        doc = dict(doc)
        doc['_id'] = str(doc['_id'])
        return doc

    @staticmethod
    def _oid(link_id: str) -> Optional[ObjectId]:
        try:
            return ObjectId(link_id)
        except Exception:
            return None

    @classmethod
    def list_all(cls) -> list:
        """全部（未刪除）連結，依排序值、再依標題。"""
        rows = cls._col().find({'deleted_at': None}).sort(
            [('sort_order', ASCENDING), ('title', ASCENDING)])
        return [cls._serialize(r) for r in rows]

    @classmethod
    def list_public(cls) -> list:
        """玩家頁用：只給顯示需要的欄位。"""
        rows = cls._col().find(
            {'deleted_at': None},
            {'title': 1, 'url': 1, 'description': 1, 'sort_order': 1},
        ).sort([('sort_order', ASCENDING), ('title', ASCENDING)])
        return [cls._serialize(r) for r in rows]

    @classmethod
    def create(cls, data: dict, username: str = '') -> str:
        fields = _clean(data)
        now = datetime.utcnow()
        fields.update({'created_at': now, 'updated_at': now, 'created_by': username,
                       'deleted_at': None})
        return str(cls._col().insert_one(fields).inserted_id)

    @classmethod
    def update(cls, link_id: str, data: dict) -> bool:
        oid = cls._oid(link_id)
        if oid is None:
            return False
        fields = _clean(data, partial=True)
        if not fields:
            raise ToolLinkError('沒有要更新的欄位')
        fields['updated_at'] = datetime.utcnow()
        return cls._col().update_one({'_id': oid, 'deleted_at': None},
                                     {'$set': fields}).matched_count > 0

    @classmethod
    def soft_delete(cls, link_id: str) -> bool:
        oid = cls._oid(link_id)
        if oid is None:
            return False
        return cls._col().update_one({'_id': oid, 'deleted_at': None},
                                     {'$set': {'deleted_at': datetime.utcnow()}}).matched_count > 0

    # ── JSON 批量匯入／匯出 ──────────────────────────────────────

    @classmethod
    def export(cls) -> dict:
        """匯出全部（未刪除）連結，格式跟 import_links 吃的一樣。"""
        return {
            'version': EXPORT_VERSION,
            'links': [{'title': r['title'], 'url': r['url'],
                       'description': r.get('description') or '',
                       'sort_order': r.get('sort_order') or 0} for r in cls.list_all()],
        }

    @classmethod
    def import_links(cls, payload, username: str = '', replace: bool = False) -> dict:
        """JSON 批量匯入。payload 可以是 `{"links": [...]}` 或直接一個陣列。

        以網址比對：已經有同網址的就更新標題／說明／排序，沒有的就新增。
        replace=True 時，檔案裡沒有的現有連結會被刪除（軟刪除），等於整份換成檔案內容。

        先把每一筆都驗證過才寫入——任何一筆不合法就整批不寫，錯誤訊息標出是第幾筆。
        """
        items = payload.get('links') if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ToolLinkError('JSON 格式不對：要是 {"links": [...]} 或一個陣列')
        if not items:
            raise ToolLinkError('檔案裡沒有任何連結')
        if len(items) > MAX_IMPORT:
            raise ToolLinkError(f'一次最多匯入 {MAX_IMPORT} 筆（檔案有 {len(items)} 筆）')

        cleaned, seen = [], {}
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ToolLinkError(f'第 {i} 筆：要是一個物件（{{"title": ..., "url": ...}}）')
            try:
                fields = _clean(item)
            except ToolLinkError as err:
                raise ToolLinkError(f'第 {i} 筆：{err}') from None
            key = fields['url'].rstrip('/').lower()
            if key in seen:
                raise ToolLinkError(f'第 {i} 筆：網址跟第 {seen[key]} 筆重複')
            seen[key] = i
            cleaned.append((key, fields))

        now = datetime.utcnow()
        existing = {r['url'].rstrip('/').lower(): r['_id']
                    for r in cls._col().find({'deleted_at': None}, {'url': 1})}
        created = updated = 0
        for key, fields in cleaned:
            if key in existing:
                cls._col().update_one({'_id': existing[key]}, {'$set': {**fields, 'updated_at': now}})
                updated += 1
            else:
                cls._col().insert_one({**fields, 'created_at': now, 'updated_at': now,
                                       'created_by': username, 'deleted_at': None})
                created += 1
        deleted = 0
        if replace:
            stale = [oid for key, oid in existing.items() if key not in seen]
            if stale:
                deleted = cls._col().update_many({'_id': {'$in': stale}, 'deleted_at': None},
                                                 {'$set': {'deleted_at': now}}).modified_count
        return {'created': created, 'updated': updated, 'deleted': deleted}
