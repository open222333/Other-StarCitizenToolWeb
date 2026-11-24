"""新聞（玩家頁「新聞」分頁、「艦長室」上方的公告區；後台「新聞」頁管理；外部程式用 API 金鑰寫入）。

每則：標題、內文（Markdown，前端轉成 HTML 時一律先跳脫，見 frontend/src/utils/markdown.js）、
封面圖片網址、來源連結、分類標籤、置頂、發布時間（可以設未來，到時間才出現在玩家頁）。

外部寫入（POST /news/ingest，API 金鑰，見 src/models/api_key.py）以「來源連結」比對：
同一個來源連結再送一次是更新，不會重複新增；沒有來源連結的一律新增。

刪除一律軟刪除（開發原則：重要資料不永久刪除）。

玩家頁的排法：列表一律依發布時間新到舊；最上面的「置頂區」（featured()）最多 4 則，
先放「官方」標籤的、再放置頂的、不夠再用最新的補。
標籤的顯示方式（collection news_tag_settings，後台「新聞」頁設定，display）：
  - main：玩家頁分類列直接顯示（依 order 排）
  - more：收在「更多」裡（預設：外部 API 帶進來的新標籤沒設定過，一律是這個）
  - hidden：下架，帶這個標籤的新聞對玩家整則隱藏（列表、全文、標籤統計、篩選、搜尋都找不到；後台照常看得到）
沒設定過的標籤：DEFAULT_MAIN_TAGS（官方、社群）是 main，其他是 more。
舊資料只有 listed（False＝下架）的照樣認。

⚠️ 封面、來源連結只接受 http:// 或 https://（玩家頁會做成連結／圖片，`javascript:` 一點就會執行），
寫入時就擋，不能只靠前端。
"""

from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from src.mongo import get_db
from src.timeutil import iso_utc

COLLECTION = 'news'
TAG_COLLECTION = 'news_tag_settings'
#: 置頂區優先放這個標籤的新聞
FEATURED_TAG = '官方'
FEATURED_MAX = 4
MAX_TITLE = 200
MAX_BODY = 20000
MAX_URL = 2000
MAX_TAG = 30
MAX_TAGS = 10
#: 標籤顯示方式
TAG_DISPLAYS = ('main', 'more', 'hidden')
#: 沒設定過時直接顯示在分類列的標籤（照這個順序）
DEFAULT_MAIN_TAGS = ('官方', '社群')
#: 外部一次最多送幾則
MAX_BATCH = 50
#: 列表每頁上限
MAX_LIMIT = 100
#: 列表回傳的摘要長度（純文字）
EXCERPT = 160


class NewsError(ValueError):
    """輸入不合法，訊息可以直接給使用者看。"""


def _col():
    return get_db()[COLLECTION]


def _tag_col():
    return get_db()[TAG_COLLECTION]


def ensure_indexes(db=None):
    col = (db if db is not None else get_db())[COLLECTION]
    col.create_index([('deleted_at', ASCENDING), ('pinned', DESCENDING), ('published_at', DESCENDING)])
    col.create_index('tags')
    # 沒來源時存的是 None，sparse 照樣會收進索引；改成只收字串。舊的 sparse 索引同名，先拿掉
    if 'source_url_1' in col.index_information():
        col.drop_index('source_url_1')
    col.create_index('source_url', name='source_url_str',
                     partialFilterExpression={'source_url': {'$type': 'string'}})


# ── 標籤顯示方式（分類列／更多／下架）───────────────────────────

def _display_of(doc: Optional[dict], tag: str) -> str:
    if doc:
        if doc.get('display') in TAG_DISPLAYS:
            return doc['display']
        if doc.get('listed') is False:
            return 'hidden'
    return 'main' if tag in DEFAULT_MAIN_TAGS else 'more'


def _order_of(doc: Optional[dict], tag: str) -> int:
    if doc and isinstance(doc.get('order'), int):
        return doc['order']
    return DEFAULT_MAIN_TAGS.index(tag) if tag in DEFAULT_MAIN_TAGS else 999


def tag_settings() -> dict:
    """{標籤: {display, order}}（只有設定過的）。"""
    return {d['_id']: {'display': _display_of(d, d['_id']), 'order': _order_of(d, d['_id'])}
            for d in _tag_col().find({})}


def unlisted_tags() -> list:
    """下架的標籤。"""
    return [d['_id'] for d in _tag_col().find({'$or': [{'display': 'hidden'}, {'display': {'$exists': False}, 'listed': False}]},
                                              {'_id': 1})]


def _with_display(rows: list, settings: dict) -> list:
    out = []
    for r in rows:
        st = settings.get(r['tag'])
        display = st['display'] if st else _display_of(None, r['tag'])
        order = st['order'] if st else _order_of(None, r['tag'])
        out.append({**r, 'display': display, 'order': order, 'listed': display != 'hidden'})
    return out


def public_tags() -> list:
    """玩家頁的標籤（下架的已排除）：[{tag, count, display: main|more, order}]，分類列的依 order 排在前面。"""
    rows = _with_display(tags(public=True), tag_settings())
    rows.sort(key=lambda r: (r['display'] != 'main', r['order'] if r['display'] == 'main' else 0, -r['count'], r['tag']))
    return [{k: r[k] for k in ('tag', 'count', 'display', 'order')} for r in rows]


def admin_tags() -> list:
    """後台：所有用過的標籤（含排程中的新聞，不含刪除）＋則數、顯示方式；分類列 → 更多 → 下架。"""
    settings = tag_settings()
    rows = tags(public=False)
    seen = {r['tag'] for r in rows}
    rows += [{'tag': t, 'count': 0} for t in settings if t not in seen]
    rows = _with_display(rows, settings)
    rank = {'main': 0, 'more': 1, 'hidden': 2}
    rows.sort(key=lambda r: (rank[r['display']], r['order'] if r['display'] == 'main' else 0, -r['count'], r['tag']))
    return rows


def set_tag_display(tag, display: str, by: str, order=None) -> dict:
    """設定標籤顯示方式（main／more／hidden）；order 是分類列的排序（小的在前，只有 main 用得到）。"""
    tag = str(tag or '').strip()
    if not tag or len(tag) > MAX_TAG:
        raise NewsError(f'標籤要 1～{MAX_TAG} 字')
    if display not in TAG_DISPLAYS:
        raise NewsError('顯示方式只能是 main、more、hidden')
    fields = {'display': display, 'listed': display != 'hidden', 'updated_at': datetime.utcnow(), 'updated_by': by}
    if order is not None:
        try:
            fields['order'] = max(0, min(999, int(order)))
        except (TypeError, ValueError):
            raise NewsError('排序要是數字') from None
    _tag_col().update_one({'_id': tag}, {'$set': fields}, upsert=True)
    doc = _tag_col().find_one({'_id': tag})
    return {'tag': tag, 'display': display, 'order': _order_of(doc, tag), 'listed': display != 'hidden'}


def set_tag_listed(tag, listed: bool, by: str) -> dict:
    """舊介面：上架／下架。上架回到「更多」（官方、社群回到分類列）。"""
    tag = str(tag or '').strip()
    if listed is False:
        return set_tag_display(tag, 'hidden', by)
    return set_tag_display(tag, 'main' if tag in DEFAULT_MAIN_TAGS else 'more', by)


# ── 驗證 ──────────────────────────────────────────────────────────

def _url(value, label: str) -> Optional[str]:
    url = (value or '').strip() if isinstance(value, str) else ''
    if not url:
        return None
    if len(url) > MAX_URL:
        raise NewsError(f'{label}太長（最多 {MAX_URL} 字）')
    parsed = urlparse(url)
    if parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc or any(ch.isspace() for ch in url):
        raise NewsError(f'{label}必須是 http:// 或 https:// 開頭的網址')
    return url


def _tags(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        value = [t for t in value.replace('，', ',').split(',')]
    if not isinstance(value, list):
        raise NewsError('標籤必須是字串陣列')
    out = []
    for t in value:
        t = (t or '').strip() if isinstance(t, str) else ''
        if not t:
            continue
        if len(t) > MAX_TAG:
            raise NewsError(f'標籤「{t[:10]}…」太長（最多 {MAX_TAG} 字）')
        if t not in out:
            out.append(t)
    if len(out) > MAX_TAGS:
        raise NewsError(f'標籤最多 {MAX_TAGS} 個')
    return out


def _time(value) -> Optional[datetime]:
    """ISO 8601 → UTC naive datetime（跟其他資料表一樣存 naive UTC）；空的回 None。"""
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        except ValueError:
            raise NewsError('發布時間格式不對（ISO 8601，例如 2026-11-20T08:00:00Z）')
    else:
        raise NewsError('發布時間格式不對（ISO 8601，例如 2026-11-20T08:00:00Z）')
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def clean(data: dict, partial: bool = False) -> dict:
    """使用者／外部送來的一則新聞 → 要寫入的欄位（不合法丟 NewsError）。partial：只檢查有送的欄位（更新用）。"""
    if not isinstance(data, dict):
        raise NewsError('每則新聞必須是 JSON 物件')
    out = {}
    if not partial or 'title' in data:
        title = (data.get('title') or '').strip() if isinstance(data.get('title'), str) else ''
        if not title:
            raise NewsError('標題不得為空')
        if len(title) > MAX_TITLE:
            raise NewsError(f'標題太長（最多 {MAX_TITLE} 字）')
        out['title'] = title
    if not partial or 'body' in data:
        body = data.get('body') if isinstance(data.get('body'), str) else ''
        if len(body) > MAX_BODY:
            raise NewsError(f'內文太長（最多 {MAX_BODY} 字）')
        out['body'] = body.strip()
    if not partial or 'cover_url' in data:
        out['cover_url'] = _url(data.get('cover_url'), '封面圖片網址')
    if not partial or 'source_url' in data:
        out['source_url'] = _url(data.get('source_url'), '來源連結')
    if not partial or 'tags' in data:
        out['tags'] = _tags(data.get('tags'))
    if not partial or 'pinned' in data:
        out['pinned'] = bool(data.get('pinned'))
    if not partial or 'published_at' in data:
        out['published_at'] = _time(data.get('published_at'))
    return out


# ── 讀 ────────────────────────────────────────────────────────────

def _excerpt(body: str) -> str:
    """Markdown → 純文字摘要（拿掉常見標記，不求完美）。"""
    import re
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', body or '')
    t = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', t)
    t = re.sub(r'[`*_>#~|-]+', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:EXCERPT] + ('…' if len(t) > EXCERPT else '')


_iso = iso_utc


def _edited(doc: dict) -> bool:
    up, cr = doc.get('updated_at'), doc.get('created_at')
    return bool(up and cr and (up - cr).total_seconds() > 60)


def to_public(doc: dict, full: bool = False) -> dict:
    out = {
        '_id': str(doc['_id']), 'title': doc.get('title'), 'cover_url': doc.get('cover_url'),
        'source_url': doc.get('source_url'), 'tags': doc.get('tags') or [], 'pinned': bool(doc.get('pinned')),
        'published_at': _iso(doc.get('published_at')), 'updated_at': _iso(doc.get('updated_at')),
        # 建立後真的改過（超過 1 分鐘）才有：玩家頁顯示「最後編輯」
        'edited_at': _iso(doc['updated_at']) if _edited(doc) else None,
    }
    if full:
        out['body'] = doc.get('body') or ''
    else:
        out['excerpt'] = _excerpt(doc.get('body'))
    return out


def to_admin(doc: dict) -> dict:
    out = to_public(doc, full=True)
    out.update({'created_at': _iso(doc.get('created_at')), 'created_by': doc.get('created_by'),
                'updated_by': doc.get('updated_by'),
                'scheduled': bool(doc.get('published_at') and doc['published_at'] > datetime.utcnow())})
    return out


#: 搜尋字串上限（$regex 掃標題、內文、標籤，太長的字串沒有意義又耗運算）
Q_MAX = 100


def _filter(public: bool, tag: str = '', q: str = '') -> dict:
    """public：只列已發布、不帶下架標籤的。"""
    q = (q or '')[:Q_MAX]
    f = {'deleted_at': None}
    tags_ = [t for t in (tag if isinstance(tag, (list, tuple)) else [tag]) if t]
    cond = {}
    if public:
        f['published_at'] = {'$lte': datetime.utcnow()}
        off = unlisted_tags()
        if off:
            cond['$nin'] = off
    if tags_:
        cond['$in'] = list(tags_)     # 多個標籤取聯集（後台多選篩選）
    if cond:
        f['tags'] = cond
    if q:
        import re
        rx = {'$regex': re.escape(q), '$options': 'i'}
        f['$or'] = [{'title': rx}, {'body': rx}, {'tags': rx}]
    return f


def list_news(public: bool = True, tag: str = '', q: str = '', limit: int = 20, offset: int = 0,
              pinned_only: bool = False, sort: str = '', since=None, until=None) -> tuple:
    """(列表, 總數)。public：只列已發布的，依發布時間新到舊（置頂的另外放在置頂區，見 featured()）。
    後台：置頂在前，再依發布時間；sort='latest' 也只依發布時間。
    since／until：發布時間範圍（ISO 8601，since 含、until 不含；玩家頁的「今日／昨日／上週」由前端用玩家時區算好）。"""
    tag = [t.strip() for t in tag] if isinstance(tag, (list, tuple)) else (tag or '').strip()
    f = _filter(public, tag, (q or '').strip())
    try:
        lo, hi = _time(since), _time(until)
    except NewsError:
        raise NewsError('日期範圍格式不對（ISO 8601）') from None
    if lo or hi:
        rng = dict(f.get('published_at') or {})
        if lo:
            rng['$gte'] = lo
        if hi:
            rng['$lt'] = hi            # 玩家頁另外還有 $lte 現在（未來排程的不出現）
        f['published_at'] = rng
    if pinned_only:
        f['pinned'] = True
    limit = max(1, min(int(limit or 20), MAX_LIMIT))
    offset = max(0, int(offset or 0))
    order = [('published_at', DESCENDING), ('_id', DESCENDING)]
    if not public and sort != 'latest':
        order.insert(0, ('pinned', DESCENDING))
    cur = _col().find(f).sort(order)
    total = _col().count_documents(f)
    rows = list(cur.skip(offset).limit(limit))
    return [(to_public(d) if public else to_admin(d)) for d in rows], total


def featured(limit: int = FEATURED_MAX) -> list:
    """玩家頁置頂區：先「官方」標籤的（新到舊）、再置頂的、不夠再用最新的補，最多 limit 則。"""
    limit = max(1, min(int(limit or FEATURED_MAX), FEATURED_MAX))
    base = _filter(True)
    order = [('published_at', DESCENDING), ('_id', DESCENDING)]
    picked, seen = [], set()
    official = {**base, 'tags': {**base.get('tags', {}), '$in': [FEATURED_TAG]}}
    for f in (official, {**base, 'pinned': True}, base):
        if len(picked) >= limit:
            break
        for d in _col().find({**f, '_id': {'$nin': list(seen)}}).sort(order).limit(limit - len(picked)):
            seen.add(d['_id'])
            picked.append(to_public(d))
    return picked


def tags(public: bool = True) -> list:
    """所有用過的標籤（依使用次數多到少）。"""
    pipeline = [{'$match': _filter(public)}, {'$unwind': '$tags'},
                {'$group': {'_id': '$tags', 'count': {'$sum': 1}}}, {'$sort': {'count': -1, '_id': 1}}]
    return [{'tag': r['_id'], 'count': r['count']} for r in _col().aggregate(pipeline)]


def _oid(news_id) -> Optional[ObjectId]:
    try:
        return ObjectId(str(news_id))
    except Exception:
        return None


def get(news_id, public: bool = True) -> Optional[dict]:
    oid = _oid(news_id)
    if not oid:
        return None
    f = {'_id': oid, **_filter(public)}
    doc = _col().find_one(f)
    if not doc:
        return None
    return to_public(doc, full=True) if public else to_admin(doc)


# ── 寫 ────────────────────────────────────────────────────────────

def create(data: dict, by: str) -> str:
    doc = clean(data)
    now = datetime.utcnow()
    doc.update({'published_at': doc['published_at'] or now, 'created_at': now, 'updated_at': now,
                'created_by': by, 'updated_by': by, 'deleted_at': None})
    return str(_col().insert_one(doc).inserted_id)


def update(news_id, data: dict, by: str) -> bool:
    oid = _oid(news_id)
    if not oid:
        return False
    fields = clean(data, partial=True)
    if 'published_at' in fields and fields['published_at'] is None:
        fields.pop('published_at')       # 清空發布時間＝不改
    fields.update({'updated_at': datetime.utcnow(), 'updated_by': by})
    return _col().update_one({'_id': oid, 'deleted_at': None}, {'$set': fields}).matched_count > 0


def delete(news_id, by: str) -> bool:
    oid = _oid(news_id)
    if not oid:
        return False
    return _col().update_one({'_id': oid, 'deleted_at': None},
                             {'$set': {'deleted_at': datetime.utcnow(), 'deleted_by': by}}).matched_count > 0


def ingest(items, by: str) -> dict:
    """外部寫入：一則（dict）或多則（list，最多 MAX_BATCH）。有來源連結而且已經有那一則（沒刪除）→ 更新，否則新增。
    任何一則不合法整批不寫入（NewsError 訊息指出第幾則）。回傳 {created: [id], updated: [id]}。"""
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list) or not items:
        raise NewsError('請送一則新聞（物件）或新聞陣列')
    if len(items) > MAX_BATCH:
        raise NewsError(f'一次最多 {MAX_BATCH} 則')
    cleaned = []
    for i, it in enumerate(items, 1):
        try:
            cleaned.append(clean(it))
        except NewsError as err:
            raise NewsError(f'第 {i} 則：{err}')
    out = {'created': [], 'updated': [], 'unchanged': []}
    now = datetime.utcnow()
    for doc in cleaned:
        existing = _col().find_one({'source_url': doc['source_url'], 'deleted_at': None}) if doc['source_url'] else None
        if existing:
            fields = {k: v for k, v in doc.items() if not (k == 'published_at' and v is None)}
            # 外部程式常常定時重送整批：內容沒變就不動（最後編輯時間才不會一直跳）
            if all(existing.get(k) == v for k, v in fields.items()):
                out['unchanged'].append(str(existing['_id']))
                continue
            fields.update({'updated_at': now, 'updated_by': by})
            _col().update_one({'_id': existing['_id']}, {'$set': fields})
            out['updated'].append(str(existing['_id']))
        else:
            doc.update({'published_at': doc['published_at'] or now, 'created_at': now, 'updated_at': now,
                        'created_by': by, 'updated_by': by, 'deleted_at': None})
            out['created'].append(str(_col().insert_one(doc).inserted_id))
    return out
