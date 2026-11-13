"""靜態 JSON 檔（scunpacked-data、sc-cargo.space、GitHub API 清單）的資料庫快取。

同步抓下來的 JSON 不再每次整份讀進記憶體再丟掉，而是存進資料庫：

  - scdata_json_files：每個網址一筆（_id＝網址）：ETag、目前的版本 gen、最近兩版 gens、
    種類（list／dict）、筆數、大小、抓取時間
  - scdata_json_rows：檔案內容拆成一段一段（陣列的元素、物件的 key 依序每段最多 CHUNK_ITEMS 筆或
    約 CHUNK_BYTES），欄位 url、gen、i（第幾段）、n（這段幾筆）、j（這段的 JSON 陣列字串）

下次抓同一個檔案時帶 If-None-Match，上游回 304（沒變）就直接讀資料庫，不再下載——
例如「地點」與「配裝」兩個同步項目都要 ships.json（43 MB），同一版只會下載一次；
GitHub API 的 304 也不算進每小時 60 次的額度。

下載與解析用串流（ijson）一筆一筆寫進資料庫，讀的時候也是游標一筆一筆讀（JsonRows），
大檔案不會整份放進記憶體。下載與重試在 src/scdata.py 的 fetch_json_url()。

存成 JSON 字串而不是巢狀文件：上游的 key 可能有「.」「$」，而且原樣讀回來最單純。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from src.mongo import get_db

try:                                    # 有 C 版 backend 時解析 43 MB 約一兩秒，記憶體只放一筆
    import ijson
except ImportError:                     # pragma: no cover - requirements 有裝；沒裝就退回整份 json.load
    ijson = None

logger = logging.getLogger(__name__)

FILES = 'scdata_json_files'
ROWS = 'scdata_json_rows'
#: 每段最多幾筆／多大（labels.json 有九萬多個 key，一個 key 一筆文件太多）
CHUNK_ITEMS = 2000
CHUNK_BYTES = 1_000_000
#: 保留最近幾版：另一個同步項目可能還在讀上一版（同一時間兩個項目抓到不同版本時）
KEEP_GENS = 2


class JsonRows:
    """資料庫裡的一個 JSON 陣列：len() 與迭代用起來跟 list 一樣，但是用游標一筆一筆讀。"""

    def __init__(self, url: str, gen: str, count: int):
        self.url = url
        self.gen = gen
        self.count = count

    def __len__(self):
        return self.count

    def __iter__(self):
        cursor = get_db()[ROWS].find({'url': self.url, 'gen': self.gen}, {'j': 1, '_id': 0}).sort('i', 1)
        for doc in cursor:
            yield from json.loads(doc['j'])

    def __getitem__(self, idx):
        return list(self)[idx]

    def __bool__(self):
        return self.count > 0


def meta(url: str) -> Optional[dict]:
    return get_db()[FILES].find_one({'_id': url})


def load(url: str, expect: type = list):
    """讀資料庫裡最新的一版；沒有、種類不對或筆數對不上回 None（呼叫端就重新下載）。"""
    m = meta(url)
    kind = 'list' if expect is list else 'dict'
    if not m or m.get('kind') != kind or not m.get('gen'):
        return None
    col = get_db()[ROWS]
    if col.count_documents({'url': url, 'gen': m['gen']}) != m.get('chunks', -1):
        return None
    rows = JsonRows(url, m['gen'], m['count'])
    if expect is list:
        return rows
    return {k: v for k, v in rows}


def _first_char(fp) -> str:
    fp.seek(0)
    while True:
        ch = fp.read(1)
        if not ch:
            return ''
        if ch not in b' \t\r\n\xef\xbb\xbf':
            fp.seek(0)
            return ch.decode('ascii', 'replace')


def _iter_items(fp, kind: str):
    if ijson is not None:
        if kind == 'list':
            yield from ijson.items(fp, 'item', use_float=True)
        else:
            for k, v in ijson.kvitems(fp, '', use_float=True):
                yield [k, v]
        return
    data = json.load(fp)
    if kind == 'list':
        yield from data
    else:
        for k, v in data.items():
            yield [k, v]


def store(url: str, fp, expect: type = list, etag: str = '', label: str = ''):
    """把下載好的檔案（fp：二進位檔案物件）存成新的一版，回傳跟 load() 一樣的東西。

    最外層型別不對、JSON 壞掉都丟 ValueError（fetch_json_url 會重試）；寫到一半失敗會清掉這一版。
    """
    kind = 'list' if expect is list else 'dict'
    first = _first_char(fp)
    if first != ('[' if kind == 'list' else '{'):
        got = {'[': 'list', '{': 'dict'}.get(first, '不是 JSON')
        raise ValueError(f'預期 JSON {expect.__name__}，收到 {got}')
    fp.seek(0, 2)
    size = fp.tell()
    fp.seek(0)

    db = get_db()
    col = db[ROWS]
    gen = str(ObjectId())
    n = chunks = 0
    parts, size_now = [], 0

    def flush():
        nonlocal parts, size_now, chunks
        if parts:
            col.insert_one({'url': url, 'gen': gen, 'i': chunks, 'n': len(parts), 'j': '[' + ','.join(parts) + ']'})
            chunks += 1
        parts, size_now = [], 0

    try:
        for item in _iter_items(fp, kind):
            text = json.dumps(item, ensure_ascii=False, separators=(',', ':'))
            if parts and (len(parts) >= CHUNK_ITEMS or size_now + len(text) > CHUNK_BYTES):
                flush()
            parts.append(text)
            size_now += len(text)
            n += 1
        flush()
    except Exception as err:            # ijson 的 JSONError、IncompleteJSONError…
        col.delete_many({'url': url, 'gen': gen})
        raise ValueError(f'{label or url} JSON 解析失敗：{err}') from err

    old = meta(url) or {}
    gens = [gen] + [g for g in old.get('gens') or [] if g != gen][:KEEP_GENS - 1]
    db[FILES].update_one({'_id': url}, {'$set': {
        'label': label, 'etag': etag or '', 'gen': gen, 'gens': gens, 'kind': kind, 'count': n, 'chunks': chunks,
        'size': size, 'fetched_at': datetime.now(timezone.utc),
    }}, upsert=True)
    col.delete_many({'url': url, 'gen': {'$nin': gens}})
    logger.info('scdata_cache: %s 存成新版 %s（%d 筆，%.1f MB）', label or url, gen, n, size / 1e6)
    rows = JsonRows(url, gen, n)
    return rows if kind == 'list' else {k: v for k, v in rows}


def touch(url: str):
    """上游回 304：記一下最後確認的時間。"""
    get_db()[FILES].update_one({'_id': url}, {'$set': {'checked_at': datetime.now(timezone.utc)}})

