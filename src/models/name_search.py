"""全站列表的名稱搜尋規則（資料庫 › 物品、藍圖、艦船、任務共用）。

規則：
  1. 關鍵字用空白分開，每個都要符合（順序不拘）：「gamma ll」「ll gamma」都找得到 Gamma LL。
  2. 英文名稱只比「字首」（以空白／標點分字）：打 LL 找 Delta LL，不會連 Telescopic、Collector
     這種字中間有 ll 的都出來；內部代碼（class name、藍圖 key、任務 debug name）以底線分段、比每段開頭；
     中文名稱任何位置都算。關鍵字前後的標點會去掉（打 "snow 或 (1x 也行）。
  3. 沒有指定排序時依相符程度排：名稱完全相同 → 名稱開頭就符合 → 名稱每個關鍵字都對到字首 → 只在代碼裡符合；
     同一級照名稱排。
  4. 用上面的規則一筆都沒有，才退回「任意位置」比對整串關鍵字（呼叫端回 match='loose'，前端提示）。

用法：fields 描述每個欄位怎麼比：
    NameFields(en=['name_lower'], zh=['name_zh'], code=['class_name'])
  en：存小寫的英文欄位；zh：中文欄位；code：底線分段的代碼（不分大小寫）。
  中文名稱沒存在資料庫的（艦船），用 zh_ids(關鍵字) 回傳符合的 _id 清單代替，排序時用 zh_of(doc) 取中文。
"""

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from pymongo import ASCENDING

_CJK = re.compile(r'[㐀-鿿豈-﫿]')
_EDGE_PUNCT = re.compile(r'^[^\w㐀-鿿]+|[^\w㐀-鿿]+$')
_NON_WORD = re.compile(r'[^0-9a-z㐀-鿿]+')
#: 最多看幾個關鍵字（避免貼一長串進來產生超大查詢）
MAX_TOKENS = 6
#: 依相符程度排序時最多掃幾筆（超過就只排前這麼多筆，後面照名稱）
MAX_RANK_SCAN = 3000


@dataclass
class NameFields:
    en: list = field(default_factory=list)
    zh: list = field(default_factory=list)
    code: list = field(default_factory=list)
    #: 中文不在資料庫時：關鍵字 → 符合的 _id 清單
    zh_ids: Optional[Callable[[str], list]] = None
    #: 中文不在資料庫時：排序用，文件 → 中文名稱
    zh_of: Optional[Callable[[dict], str]] = None
    #: 名稱排序（同一級內）用的欄位
    sort_field: str = 'name_lower'


def tokens(query: str) -> list:
    out = []
    for raw in (query or '').split():
        tok = _EDGE_PUNCT.sub('', raw.strip())
        if tok and tok not in out:
            out.append(tok)
    return out[:MAX_TOKENS]


def _norm(text) -> str:
    return ' '.join(_NON_WORD.sub(' ', str(text or '').lower()).split())


def _token_condition(tok: str, f: NameFields) -> dict:
    esc = re.escape(tok)
    ors = []
    if _CJK.search(tok):
        ors += [{z: {'$regex': esc}} for z in f.zh]
        if f.zh_ids:
            ors.append({'_id': {'$in': f.zh_ids(tok)}})
    else:
        low = esc.lower()
        ors += [{e: {'$regex': f'(^|[^0-9a-z]){low}'}} for e in f.en]
        # 中文名稱裡的英文（例如「德爾塔 LL」）一樣只比字首
        ors += [{z: {'$regex': f'(^|[^0-9A-Za-z]){esc}', '$options': 'i'}} for z in f.zh]
        ors += [{c: {'$regex': f'(^|_){esc}', '$options': 'i'}} for c in f.code]
    return {'$or': ors} if ors else {'_id': {'$in': []}}


def strict_filter(query: str, f: NameFields) -> Optional[dict]:
    """嚴格規則（每個關鍵字都要對到字首／中文任意位置）；沒有關鍵字回 None。
    只有標點（例如 .*）時退回任意位置比對原字串，不會變成「不篩」。"""
    toks = tokens(query)
    if not toks:
        return loose_filter(query, f)
    conds = [_token_condition(t, f) for t in toks]
    return conds[0] if len(conds) == 1 else {'$and': conds}


def loose_filter(query: str, f: NameFields) -> Optional[dict]:
    """放寬規則：整串關鍵字在名稱任意位置（英文不分大小寫）。"""
    q = (query or '').strip()
    if not q:
        return None
    esc = re.escape(q)
    ors = [{e: {'$regex': esc.lower()}} for e in f.en] + [{z: {'$regex': esc, '$options': 'i'}} for z in f.zh]
    if f.zh_ids and _CJK.search(q):
        ors.append({'_id': {'$in': f.zh_ids(q)}})
    return {'$or': ors} if ors else None


def text_fields_filter(query: str, fields: list, loose: bool = False) -> Optional[dict]:
    """玩家自己登記的名稱（存原本大小寫的英文、或中文）用：同一套規則，loose=True 取放寬版。
    給沒辦法用 find() 的聚合查詢——呼叫端先用嚴格版，查不到再用 loose=True 重查一次。"""
    f = NameFields(zh=list(fields))
    return loose_filter(query, f) if loose else strict_filter(query, f)


def merge(base: dict, cond: Optional[dict]) -> dict:
    """把名稱條件 AND 進既有的查詢條件（不覆蓋既有的 $or／$and）。"""
    if not cond:
        return base
    out = dict(base)
    out['$and'] = [*out.get('$and', []), cond]
    return out


def rank(doc: dict, query: str, f: NameFields) -> int:
    """相符程度：0 名稱完全相同、1 名稱開頭就符合、2 名稱的字首都對到、3 其他（只在代碼裡符合等）。"""
    q = _norm(query)
    names = [_norm(doc.get(e)) for e in f.en] + [_norm(doc.get(z)) for z in f.zh]
    if f.zh_of:
        names.append(_norm(f.zh_of(doc)))
    names = [n for n in names if n]
    if any(n == q for n in names):
        return 0
    if any(n.startswith(q) for n in names):
        return 1
    toks = [_norm(t) for t in tokens(query)]
    for n in names:
        words = n.split()
        if all(any(w.startswith(t) for w in words) or (_CJK.search(t) and t in n) for t in toks if t):
            return 2
    return 3


def find(col, base_filter: dict, query: str, f: NameFields, projection: dict, *,
         sort=None, offset: int = 0, limit: int = 50, relevance: bool = True) -> tuple:
    """套用名稱搜尋規則查一頁：回傳 (rows, total, match)。match：''＝沒有關鍵字、'strict'、'loose'（放寬後才找到）。

    sort：pymongo 的排序 spec（沒有關鍵字、或 relevance=False 時用）；relevance：有關鍵字時依相符程度排。
    limit=0 表示全部。
    """
    sort = sort or [(f.sort_field, ASCENDING)]
    cond = strict_filter(query, f)
    match = ''
    filt = base_filter
    if cond:
        filt = merge(base_filter, cond)
        match = 'strict'
        if not col.count_documents(filt, limit=1):
            loose = loose_filter(query, f)
            if loose:
                filt = merge(base_filter, loose)
                match = 'loose'
    total = col.count_documents(filt)
    if not match or not relevance or total > MAX_RANK_SCAN:
        cur = col.find(filt, projection).sort(sort).skip(offset)
        rows = list(cur.limit(limit) if limit else cur)
        return rows, total, match

    # 依相符程度：先撈名稱欄位算分數，排好再取這一頁
    name_proj = {k: 1 for k in [*f.en, *f.zh, f.sort_field]}
    if f.zh_of:
        name_proj.update({'class_name': 1, 'name': 1, 'game_name': 1})
    lite = list(col.find(filt, name_proj))
    lite.sort(key=lambda d: (rank(d, query, f), str(d.get(f.sort_field) or '').lower(), str(d['_id'])))
    page_ids = [d['_id'] for d in (lite[offset:offset + limit] if limit else lite[offset:])]
    by_id = {d['_id']: d for d in col.find({'_id': {'$in': page_ids}}, projection)}
    return [by_id[i] for i in page_ids if i in by_id], total, match
