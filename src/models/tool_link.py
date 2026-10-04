"""工具網站連結（後台維護、玩家頁「工具網站」分頁顯示）。

每筆是一個外部網站（網址不重複）：標題、網址、說明（玩家頁收在問號裡）、排序值，
加上**標籤** tags（一個網址可以有好幾個標籤，例如同時是「交易」和「資料」）。

標籤另外存在 tool_link_tags collection（_id = 標籤名稱、order = 順序）：玩家頁依標籤
分組的順序、後台標籤的下拉建議都從這裡來。新標籤（後台新增或匯入）自動加到最後；
匯入時勾「取代現有清單」會照檔案重排順序。

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

from src.mongo import get_db

MAX_TITLE = 100
MAX_URL = 2000
MAX_DESCRIPTION = 2000
MAX_TAG = 50
MAX_TAGS_PER_LINK = 10
#: JSON 批量匯入一次最多幾筆
MAX_IMPORT = 500
#: 匯出檔的格式版本：
#:   1 = {"links": [...]}（舊）
#:   2 = {"categories": [{"name", "links": [...]}]}（分類版，匯入時分類名稱當成標籤）
#:   3 = {"tags": [...順序], "links": [{..., "tags": [...]}]}（現在的匯出格式）
EXPORT_VERSION = 3
TAG_COLLECTION = 'tool_link_tags'


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
    if not partial or 'tags' in data:
        out['tags'] = clean_tags(data.get('tags'))
    return out


def clean_tags(value) -> list:
    """標籤清單：接受陣列或逗號分隔字串，去空白、去重複（保留第一次出現的順序）。"""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.replace('，', ',').split(',')
    if not isinstance(value, list):
        raise ToolLinkError('標籤要是陣列')
    out = []
    for tag in value:
        if not isinstance(tag, str):
            raise ToolLinkError('標籤要是文字')
        tag = tag.strip()
        if not tag or tag in out:
            continue
        if len(tag) > MAX_TAG:
            raise ToolLinkError(f'標籤太長（最多 {MAX_TAG} 字）')
        out.append(tag)
    if len(out) > MAX_TAGS_PER_LINK:
        raise ToolLinkError(f'一個網址最多 {MAX_TAGS_PER_LINK} 個標籤')
    return out


class ToolLink:
    COLLECTION = 'tool_links'

    @classmethod
    def _col(cls):
        return get_db()[cls.COLLECTION]

    @staticmethod
    def _tag_col():
        return get_db()[TAG_COLLECTION]

    @staticmethod
    def _serialize(doc: dict) -> dict:
        doc = dict(doc)
        doc['_id'] = str(doc['_id'])
        doc['tags'] = list(doc.get('tags') or [])
        return doc

    @staticmethod
    def _oid(link_id: str) -> Optional[ObjectId]:
        try:
            return ObjectId(link_id)
        except Exception:
            return None

    # ── 標籤 ─────────────────────────────────────────────────────

    @classmethod
    def _ensure_tags(cls, tags, reorder: bool = False) -> None:
        """把標籤存進 tool_link_tags：沒有的加到最後；reorder=True 時照傳進來的順序重排
        （匯入「取代現有清單」用）。"""
        tags = [t for t in dict.fromkeys(tags or []) if t]
        if not tags:
            return
        col = cls._tag_col()
        now = datetime.utcnow()
        if reorder:
            for i, tag in enumerate(tags, start=1):
                col.update_one({'_id': tag}, {'$set': {'order': i},
                                              '$setOnInsert': {'created_at': now}}, upsert=True)
            others = [r['_id'] for r in col.find({'_id': {'$nin': tags}}).sort('order', 1)]
            for i, tag in enumerate(others, start=len(tags) + 1):
                col.update_one({'_id': tag}, {'$set': {'order': i}})
            return
        existing = {r['_id'] for r in col.find({'_id': {'$in': tags}}, {'_id': 1})}
        last = col.find_one({}, {'order': 1}, sort=[('order', -1)])
        order = (last or {}).get('order') or 0
        for tag in tags:
            if tag not in existing:
                order += 1
                col.insert_one({'_id': tag, 'order': order, 'created_at': now})

    @classmethod
    def tags(cls) -> list:
        """目前有網址在用的標籤（照順序）。舊資料裡有、標籤表沒有的排在最後。"""
        used = set()
        for r in cls._col().find({'deleted_at': None}, {'tags': 1}):
            used.update(r.get('tags') or [])
        ordered = [r['_id'] for r in cls._tag_col().find({}, {'_id': 1}).sort('order', 1)]
        out = [t for t in ordered if t in used]
        return out + sorted(used - set(out))

    # ── 查詢 ─────────────────────────────────────────────────────

    @staticmethod
    def _order_key(row: dict):
        return (row.get('sort_order') or 0, (row.get('title') or '').lower())

    @classmethod
    def list_all(cls) -> list:
        """全部（未刪除）連結，依排序值、標題（量很少，排序在 Python 做）。"""
        return [cls._serialize(r) for r in sorted(cls._col().find({'deleted_at': None}), key=cls._order_key)]

    @classmethod
    def list_public(cls) -> list:
        """玩家頁用：只給顯示需要的欄位。"""
        rows = cls._col().find({'deleted_at': None},
                               {'title': 1, 'url': 1, 'description': 1, 'sort_order': 1, 'tags': 1})
        return [cls._serialize(r) for r in sorted(rows, key=cls._order_key)]

    # ── 新增／修改／刪除 ─────────────────────────────────────────

    @staticmethod
    def _url_key(url: str) -> str:
        return url.rstrip('/').lower()

    @classmethod
    def _find_by_url(cls, url: str, exclude_id=None) -> Optional[dict]:
        key = cls._url_key(url)
        for r in cls._col().find({'deleted_at': None}, {'url': 1}):
            if cls._url_key(r['url']) == key and r['_id'] != exclude_id:
                return r
        return None

    @classmethod
    def create(cls, data: dict, username: str = '') -> str:
        fields = _clean(data)
        if cls._find_by_url(fields['url']):
            raise ToolLinkError('這個網址已經有了，要加分類請在那一筆加標籤')
        cls._ensure_tags(fields['tags'])
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
        if 'url' in fields and cls._find_by_url(fields['url'], exclude_id=oid):
            raise ToolLinkError('這個網址已經有了')
        if 'tags' in fields:
            cls._ensure_tags(fields['tags'])
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
        """匯出全部（未刪除）連結（格式 3），可以直接拿來匯入。"""
        return {
            'version': EXPORT_VERSION,
            'tags': cls.tags(),
            'links': [{'title': r['title'], 'url': r['url'],
                       'description': r.get('description') or '',
                       'sort_order': r.get('sort_order') or 0,
                       'tags': r['tags']} for r in cls.list_all()],
        }

    @staticmethod
    def _flatten(payload) -> tuple:
        """匯入檔攤平成 ([連結 dict…], [標籤順序])。三種格式都吃：

          - 格式 3：{"tags": [...], "links": [{..., "tags": [...]}]}
          - 格式 2：{"categories": [{"name": "交易", "links": [...]}]}，分類名稱變成標籤
          - 格式 1：{"links": [...]} 或直接一個陣列，每筆可以帶 "tags" 或舊的 "category"
        """
        tag_order: list = []

        def note(tags):
            for t in tags:
                if isinstance(t, str) and t.strip() and t.strip() not in tag_order:
                    tag_order.append(t.strip())

        if isinstance(payload, dict) and 'categories' in payload:
            categories = payload['categories']
            if not isinstance(categories, list):
                raise ToolLinkError('JSON 格式不對："categories" 要是一個陣列')
            out = []
            for ci, cat in enumerate(categories, start=1):
                if not isinstance(cat, dict) or not isinstance(cat.get('links'), list):
                    raise ToolLinkError(f'第 {ci} 個分類：要是 {{"name": ..., "links": [...]}}')
                name = str(cat.get('name') or '').strip()
                note([name])
                for item in cat['links']:
                    if isinstance(item, dict):
                        extra = item.get('tags') if isinstance(item.get('tags'), list) else []
                        item = {**item, 'tags': ([name] if name else []) + extra}
                    out.append(item)
            return out, tag_order
        if isinstance(payload, dict) and isinstance(payload.get('tags'), list):
            note(payload['tags'])
        items = payload.get('links') if isinstance(payload, dict) else payload
        if not isinstance(items, list):
            raise ToolLinkError('JSON 格式不對：要是 {"links": [...]}、{"categories": [...]} 或一個陣列')
        out = []
        for item in items:
            if isinstance(item, dict) and 'tags' not in item and item.get('category'):
                item = {**item, 'tags': [item['category']]}
            if isinstance(item, dict) and isinstance(item.get('tags'), list):
                note(item['tags'])
            out.append(item)
        return out, tag_order

    @classmethod
    def import_links(cls, payload, username: str = '', replace: bool = False) -> dict:
        """JSON 批量匯入（格式見 _flatten）。

        以網址比對：檔案裡同一個網址出現好幾次（例如在不同分類底下）會合併成一筆、
        標籤取聯集；資料庫已經有同網址的就更新，沒有的新增。replace=True 時檔案裡沒有
        的現有連結會被刪除（軟刪除），標籤順序也照檔案重排。

        先把每一筆都驗證過才寫入——任何一筆不合法就整批不寫，錯誤訊息標出是第幾筆。
        """
        items, tag_order = cls._flatten(payload)
        if not items:
            raise ToolLinkError('檔案裡沒有任何連結')
        if len(items) > MAX_IMPORT:
            raise ToolLinkError(f'一次最多匯入 {MAX_IMPORT} 筆（檔案有 {len(items)} 筆）')

        merged: dict = {}   # 網址 key → 欄位（保留第一次出現的順序）
        for i, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ToolLinkError(f'第 {i} 筆：要是一個物件（{{"title": ..., "url": ...}}）')
            try:
                fields = _clean(item)
            except ToolLinkError as err:
                raise ToolLinkError(f'第 {i} 筆：{err}') from None
            key = cls._url_key(fields['url'])
            if key in merged:
                prev = merged[key]
                prev['tags'] = list(dict.fromkeys(prev['tags'] + fields['tags']))
                if len(prev['tags']) > MAX_TAGS_PER_LINK:
                    raise ToolLinkError(f'第 {i} 筆：一個網址最多 {MAX_TAGS_PER_LINK} 個標籤')
                if not prev['description'] and fields['description']:
                    prev['description'] = fields['description']
            else:
                merged[key] = fields

        all_tags = list(dict.fromkeys(tag_order + [t for f in merged.values() for t in f['tags']]))
        cls._ensure_tags(all_tags, reorder=replace)

        now = datetime.utcnow()
        existing = {cls._url_key(r['url']): r['_id']
                    for r in cls._col().find({'deleted_at': None}, {'url': 1})}
        created = updated = 0
        for key, fields in merged.items():
            if key in existing:
                cls._col().update_one({'_id': existing[key]}, {'$set': {**fields, 'updated_at': now}})
                updated += 1
            else:
                cls._col().insert_one({**fields, 'created_at': now, 'updated_at': now,
                                       'created_by': username, 'deleted_at': None})
                created += 1
        deleted = 0
        if replace:
            stale = [oid for key, oid in existing.items() if key not in merged]
            if stale:
                deleted = cls._col().update_many({'_id': {'$in': stale}, 'deleted_at': None},
                                                 {'$set': {'deleted_at': now}}).modified_count
        return {'created': created, 'updated': updated, 'deleted': deleted}
