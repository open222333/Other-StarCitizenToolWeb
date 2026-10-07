"""遊戲文字翻譯（多語系）—— 全站中文化的唯一來源。

資料來源（由 tasks/scdata_sync.py 的翻譯同步寫入，跟著同步排程定期更新）：

  - 英文（主語言）：scunpacked-data 的 labels.json —— 遊戲本身的英文在地化表，
    key 就是遊戲的 localization key（例如 `vehicle_NameAEGS_Avenger_Stalker`）。
  - 繁體中文（zh-TW）：社群繁中化包 cosmo-chang-1701/sc-translation-pack 的
    global.ini，key 跟 labels.json 完全同一組（翻譯包約 1.3 萬筆 key 帶 `,P`
    後綴，去掉後就對得上）。翻譯包授權是 CC BY-NC-SA 4.0（姓名標示 Cosmo Chang、
    非商業使用、相同方式分享）。
  - 人工條目（source='manual'）：翻譯包沒收錄、之前人工補的中文（藍圖類型、
    岩石／小行星礦床等地質術語…），來自 src/data/sc_translation_manual.json，
    同步時一併寫入，不會被翻譯包覆蓋。

## 資料結構（collection `sc_translations`，一個 key 一筆）

    {
      _id:       'vehicle_NameAEGS_Avenger_Stalker',   # 遊戲 localization key（人工條目是 manual.<domain>.<id>）
      key_lower: 'vehicle_nameaegs_avenger_stalker',
      text:      {'en': 'Aegis Avenger Stalker', 'zh-TW': '聖盾 復仇者 追獵'},
      en_lower:  'aegis avenger stalker',              # 用英文反查其他語言用
      en_norm:   'aegis avenger stalker',              # 寬鬆比對用（代入欄位、引號、空白統一，見 normalize_english）
      source:    'game' | 'manual',
      domain:    None | 'blueprint_type' | ...,        # 只有人工條目有
      h:         '<text 的雜湊>',                      # 同步時判斷內容有沒有變
      updated_at
    }

以英文為主：每筆一定有 `text.en`，其他語言都是 `text.<語言代碼>`，之後加語言
只是多一個欄位，不用改結構。翻譯包的值常是「English\\n中文」或「中文（English）」
這種中英並列格式，寫入時會把英文部分拿掉，`text.zh-TW` 只存中文。跟英文一樣
（沒翻）的不算翻譯，查詢時回 None。

查詢一律走這裡（領域別的包裝在 src/sc_zh.py），不要再各自維護對照表。
"""

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from pymongo import ASCENDING, DeleteOne, UpdateOne

from src.mongo import get_db

COLLECTION = 'sc_translations'
META_COLLECTION = 'sc_translation_meta'

LANG_EN = 'en'
DEFAULT_LANG = 'zh-TW'

SOURCE_GAME = 'game'
SOURCE_MANUAL = 'manual'
MANUAL_PREFIX = 'manual.'

_CJK = re.compile(r'[\u3400-\u9fff\uf900-\ufaff]')

# 快取多久檢查一次 meta 的版本（同步完成就會換版本，快取整批作廢）
_VERSION_CHECK_S = 30


def _col():
    return get_db()[COLLECTION]


def manual_key(domain: str, ident: str) -> str:
    return f'{MANUAL_PREFIX}{domain}.{ident}'


_TOKEN_GAME = re.compile(r'~mission\(([^)|]*)(?:\|[^)]*)?\)')
_TOKEN_BRACKET = re.compile(r'\[([^\]|]+)\|[^\]]*\]')
_QUOTES = str.maketrans({'’': "'", '‘': "'", '“': '"', '”': '"', '\u00a0': ' '})


def soften_english(text: str) -> str:
    """遊戲英文 ↔ Wiki API 英文的寫法差異統一（不改大小寫）：
    `~mission(Location|Address)`／`[Location|Address]` → `[Location]`、彎引號 → 直引號、
    拿掉 <EM4> 之類標籤、多個空白縮成一個。"""
    t = _TOKEN_GAME.sub(lambda m: f'[{m.group(1)}]', text or '')
    t = _TOKEN_BRACKET.sub(lambda m: f'[{m.group(1)}]', t)
    t = re.sub(r'</?[A-Za-z][^>]{0,20}>', '', t.translate(_QUOTES))
    return re.sub(r'\s+', ' ', t.replace('\\n', ' ')).strip()


def normalize_english(text: str) -> str:
    """寬鬆比對用的英文（soften_english 再轉小寫）。存在 en_norm 欄位。"""
    return soften_english(text).lower()


def text_hash(text: dict) -> str:
    raw = '\x1f'.join(f'{k}={text[k]}' for k in sorted(text) if text[k] is not None)
    # 只用來判斷「內容有沒有變」，前 16 碼就夠，9 萬筆常駐記憶體時省一半
    return hashlib.sha1(raw.encode('utf-8')).hexdigest()[:16]


def strip_english(value: str, english: str) -> str:
    """把翻譯包的中英並列格式去掉英文，只留翻譯本身。

    - 「English\\n中文」（名稱類最常見）→「中文」
    - 「中文（English）」（地點、陣營…）→「中文」
    其他格式原樣回傳（說明文字裡的 \\n 是真正的換行，不能亂切）。
    """
    v = (value or '').strip()
    en = (english or '').strip()
    if not v:
        return v
    if en and v.startswith(en + '\\n'):
        return v[len(en) + 2:].strip()
    # 翻譯包前半的英文不一定跟遊戲英文表一字不差（例如 "Heph (Raw)\\n火神石（原礦）"，
    # 英文表是 "Hephaestanite (R)"）。第一段完全沒有中文、後面有中文，就當成
    # 「英文\\n翻譯」格式；說明文字的第一段通常就有中文，不會被誤切。
    if '\\n' in v:
        head, tail = v.split('\\n', 1)
        if not _CJK.search(head) and _CJK.search(tail):
            return tail.strip()
    if not en:
        return v
    for left, right in (('（', '）'), ('(', ')')):
        suffix = f'{left}{en}{right}'
        if v.endswith(suffix) and len(v) > len(suffix):
            return v[:-len(suffix)].strip()
    return v


# ── 快取 ────────────────────────────────────────────────────────────
#
# 查詢集中在少數幾千個 key（載具、物品、地點…），同一個 key 會被反覆查，
# 每次都打 Mongo 太浪費。快取以「翻譯版本」為單位：同步完成會寫入新版本，
# 各 process 最多 _VERSION_CHECK_S 秒內發現版本變了就整批丟掉。
_cache: dict = {}
_cache_version = None
_version_checked_at = 0.0


def clear_cache():
    global _cache_version, _version_checked_at
    _cache.clear()
    _cache_version = None
    _version_checked_at = 0.0


def _check_version():
    global _cache_version, _version_checked_at
    now = time.monotonic()
    if now - _version_checked_at < _VERSION_CHECK_S and _cache_version is not None:
        return
    _version_checked_at = now
    meta = get_db()[META_COLLECTION].find_one({'_id': 'status'}, {'version': 1}) or {}
    version = meta.get('version') or '-'
    if version != _cache_version:
        _cache.clear()
        _cache_version = version


def _cached(cache_key, loader):
    _check_version()
    if cache_key in _cache:
        return _cache[cache_key]
    value = loader()
    _cache[cache_key] = value
    return value


def _translation_of(doc: Optional[dict], lang: str) -> Optional[str]:
    """文件裡的翻譯；沒有、或跟英文一樣（沒翻）都回 None。"""
    if not doc:
        return None
    text = doc.get('text') or {}
    value = (text.get(lang) or '').strip()
    if not value:
        return None
    if lang != LANG_EN and value == (text.get(LANG_EN) or '').strip():
        return None
    return value


# ── 查詢 ────────────────────────────────────────────────────────────

def by_key(key: str, lang: str = DEFAULT_LANG) -> Optional[str]:
    """以 localization key 查（不分大小寫）。"""
    k = (key or '').strip().lower()
    if not k:
        return None

    def load():
        doc = _col().find_one({'key_lower': k}, {'text': 1})
        return _translation_of(doc, lang)
    return _cached(('k', k, lang), load)


def by_keys(keys: Iterable[str], lang: str = DEFAULT_LANG) -> Optional[str]:
    """依序試多個 key，回傳第一個有翻譯的。"""
    for key in keys:
        value = by_key(key, lang)
        if value:
            return value
    return None


def by_english(text: str, prefixes: Iterable[str], lang: str = DEFAULT_LANG) -> Optional[str]:
    """以英文原文反查翻譯，只看 key 開頭符合 prefixes 的條目（不分大小寫）。

    同一段英文常對到很多 key（例如 "Lorville" 同時是地點名稱、任務文字…），
    所以一定要指定這次查的是哪一類 key；多筆符合時依 prefixes 的順序優先，
    同一個 prefix 內取 key 最短的（通常是名稱本身，不是衍生的說明／變體）。
    人工條目（manual.<domain>.）要放在 prefixes 最前面才會優先。
    """
    t = (text or '').strip().lower()
    prefix_list = [p.lower() for p in prefixes if p]
    if not t or not prefix_list:
        return None

    def load():
        rows = list(_col().find({'en_lower': t}, {'key_lower': 1, 'text': 1}))
        best = None
        for row in rows:
            k = row.get('key_lower') or ''
            rank = next((i for i, p in enumerate(prefix_list) if k.startswith(p)), None)
            if rank is None:
                continue
            value = _translation_of(row, lang)
            if not value:
                continue
            score = (rank, len(k), k)
            if best is None or score < best[0]:
                best = (score, value)
        return best[1] if best else None
    return _cached(('e', t, tuple(prefix_list), lang), load)


def match_english(text: str, patterns: Iterable[str], lang: str = DEFAULT_LANG) -> Optional[tuple]:
    """以英文原文反查翻譯，key 用正規式（re.search，比對小寫 key）篩選，回傳
    `(key_lower, 翻譯)`；查不到回 None。

    跟 by_english() 一樣是「同一段英文對到很多 key 時要指定是哪一類」，差別是
    有些類別的 key 沒有共同前綴、只有共同的片段——任務標題是
    `mg_klim_..._title_intro`、`Intersec_TSG_Group_Title_001`…，勢力名稱是
    `Adagio_RepUI_DisplayName`、`Aciedo_RepUI_Name`…。多筆符合時依 patterns
    的順序優先，同一個 pattern 內取 key 最短的。

    回傳 key 是為了讓呼叫端從同一組 key 推出相關條目（例如任務標題 key →
    說明 key、勢力名稱 key → 勢力介紹 key）。
    """
    t = (text or '').strip().lower()
    compiled = [re.compile(p) for p in patterns if p]
    if not t or not compiled:
        return None

    def load():
        rows = _rows_by_english(text)
        best = None
        for row in rows:
            k = row.get('key_lower') or ''
            rank = next((i for i, rx in enumerate(compiled) if rx.search(k)), None)
            if rank is None:
                continue
            value = _translation_of(row, lang)
            if not value:
                continue
            score = (row['_exact'], rank, len(k), k)
            if best is None or score < best[0]:
                best = (score, (k, value))
        return best[1] if best else None
    return _cached(('m', t, tuple(p.pattern for p in compiled), lang), load)


def _rows_by_english(text: str) -> list:
    """英文完全相同（en_lower）優先，其次寬鬆相同（en_norm）的條目；每筆多一個
    `_exact`（0 = 完全相同、1 = 寬鬆相同）給排序用。"""
    t = (text or '').strip().lower()
    n = normalize_english(text)
    rows = list(_col().find({'$or': [{'en_lower': t}, {'en_norm': n}]},
                            {'key_lower': 1, 'text': 1, 'en_lower': 1}))
    for row in rows:
        row['_exact'] = 0 if row.get('en_lower') == t else 1
    return rows


def candidates_by_english(text: str, patterns: Iterable[str], lang: str = DEFAULT_LANG) -> list:
    """同 match_english()，但回傳全部符合的 `(key_lower, 翻譯)`（依優先順序排好）。

    給「同一個英文標題對到好幾個 key、要再用別的線索挑」的情況用——例如兩個
    任務都叫 "Additional Resources For Research"，標題翻譯可能不同，要再比對
    說明文字才知道是哪一個。
    """
    t = (text or '').strip().lower()
    compiled = [re.compile(p) for p in patterns if p]
    if not t or not compiled:
        return []

    def load():
        out = []
        for row in _rows_by_english(text):
            k = row.get('key_lower') or ''
            rank = next((i for i, rx in enumerate(compiled) if rx.search(k)), None)
            if rank is None:
                continue
            value = _translation_of(row, lang)
            if value:
                out.append(((row['_exact'], rank, len(k), k), (k, value)))
        return [pair for _, pair in sorted(out)]
    return _cached(('c', t, tuple(p.pattern for p in compiled), lang), load)


#: 樣板比對時，樣板裡除了代入欄位之外至少要有這麼多個英數字，
#: 不然 "~mission(Title)" 這種整句都是代入欄位的樣板會對到任何標題
_TEMPLATE_MIN_LITERAL = 6


def template_candidates(text: str, patterns: Iterable[str], lang: str = DEFAULT_LANG) -> list:
    """英文裡有代入欄位的樣板（例如 "Delivery for ~mission(Destination) Ready"）比對
    已經填好值的英文（"Delivery for Lorville Ready"），回傳
    `[(key_lower, 翻譯, {欄位名稱小寫: 填進去的值})]`，字面部分越長的越優先。

    只看 key 符合 patterns 的條目；完全比對不到時才用（比較慢，結果有快取）。
    """
    target = soften_english(text)
    compiled = [re.compile(p) for p in patterns if p]
    if not target or not compiled:
        return []

    def load_templates():
        out = []
        for row in _col().find({'text.en': {'$regex': r'~mission\('}}, {'key_lower': 1, 'text': 1}):
            k = row.get('key_lower') or ''
            rank = next((i for i, rx in enumerate(compiled) if rx.search(k)), None)
            value = _translation_of(row, lang)
            if rank is None or not value:
                continue
            soft = soften_english(row['text'][LANG_EN])
            parts = re.split(r'\[([^\]]+)\]', soft)
            literal = ''.join(parts[0::2])
            if len(re.sub(r'[^A-Za-z0-9]', '', literal)) < _TEMPLATE_MIN_LITERAL:
                continue
            names, regex = [], ''
            for i, part in enumerate(parts):
                if i % 2:
                    names.append(part.strip().lower())
                    regex += f'(?P<g{len(names) - 1}>.+?)'
                else:
                    regex += re.escape(part)
            out.append((len(literal), rank, k, re.compile(f'^{regex}$', re.I), names, value))
        out.sort(key=lambda x: (-x[0], x[1], len(x[2])))
        return out

    templates = _cached(('tpl', tuple(p.pattern for p in compiled), lang), load_templates)

    def load():
        hits = []
        for _, _, k, rx, names, value in templates:
            m = rx.match(target)
            if m:
                hits.append((k, value, {n: m.group(f'g{i}') for i, n in enumerate(names)}))
        return hits
    return _cached(('tc', target, tuple(p.pattern for p in compiled), lang), load)


def english_of(key: str) -> Optional[str]:
    """某個 key 的英文原文（不分大小寫），沒有回 None。"""
    k = (key or '').strip().lower()
    if not k:
        return None

    def load():
        doc = _col().find_one({'key_lower': k}, {'text': 1})
        return ((doc or {}).get('text') or {}).get(LANG_EN) or None
    return _cached(('en', k), load)


def by_key_pattern(pattern: str, lang: str = DEFAULT_LANG) -> dict:
    """key（小寫）符合正規式的全部條目 {英文: 翻譯}，沒有翻譯的也收（值是 None）。

    給「列出某一類已知名稱」用（例如所有星系地點名稱），pattern 必須以 ^ 開頭，
    才吃得到 key_lower 的索引。
    """
    def load():
        out = {}
        for row in _col().find({'key_lower': {'$regex': pattern}}, {'text': 1}).sort('key_lower', 1):
            en = ((row.get('text') or {}).get(LANG_EN) or '').strip()
            if en and en not in out:
                out[en] = _translation_of(row, lang)
        return out
    return _cached(('p', pattern, lang), load)


def manual_domain(domain: str, lang: str = DEFAULT_LANG) -> dict:
    """某個人工條目 domain 的完整對照 {id: 翻譯}（給前端一次載入的小型封閉清單用）。"""
    prefix = manual_key(domain, '')

    def load():
        out = {}
        for row in _col().find({'source': SOURCE_MANUAL, 'domain': domain}, {'text': 1}):
            value = _translation_of(row, lang)
            if value:
                out[row['_id'][len(prefix):]] = value
        return out
    return _cached(('d', domain, lang), load)


SEARCH_MODES = ('auto', 'key', 'zh', 'en')
SEARCH_LIMIT = 50


def guess_search_mode(query: str) -> str:
    """有中文 → 中文反查代碼；有底線或沒有空白的英數字 → 代碼；其餘當英文。"""
    q = (query or '').strip()
    if _CJK.search(q):
        return 'zh'
    if '_' in q or (q and ' ' not in q and re.fullmatch(r'[\w.,@-]+', q) and re.search(r'[A-Z].*[a-z]|[a-z].*[A-Z]|\d', q)):
        return 'key'
    return 'en'


def search(query: str, mode: str = 'auto', lang: str = DEFAULT_LANG, limit: int = SEARCH_LIMIT) -> tuple:
    """玩家頁「中文轉碼 › 遊戲文字代碼」：代碼 ⇄ 中文（也可以用英文找）。

    mode：key＝以代碼找（完全相同排第一，再來是開頭相同、包含）；zh＝中文包含；
    en＝英文包含；auto＝依輸入猜（guess_search_mode）。只查遊戲本身的文字（不含人工條目）。
    回傳 (結果 [{key, en, zh}], 實際用的 mode)。
    """
    q = (query or '').strip()[:100]
    if mode not in SEARCH_MODES:
        mode = 'auto'
    if mode == 'auto':
        mode = guess_search_mode(q)
    if not q:
        return [], mode
    limit = max(1, min(int(limit), SEARCH_LIMIT))
    base = {'source': SOURCE_GAME}
    fields = {'text': 1}
    pattern = re.escape(q.lower())

    if mode == 'key':
        k = q.lstrip('@').lower()
        esc = re.escape(k)
        docs, seen = [], set()
        for filt in ({'key_lower': k}, {'key_lower': {'$regex': f'^{esc}'}}, {'key_lower': {'$regex': esc}}):
            for doc in _col().find({**base, **filt}, fields).limit(limit):
                if doc['_id'] not in seen:
                    seen.add(doc['_id'])
                    docs.append(doc)
            if len(docs) >= limit:
                break
        docs = docs[:limit]
    elif mode == 'zh':
        docs = list(_col().find({**base, f'text.{lang}': {'$regex': re.escape(q)}}, fields).limit(limit))
        # 短的（最接近輸入的）排前面
        docs.sort(key=lambda d: len((d.get('text') or {}).get(lang) or ''))
    else:
        docs = list(_col().find({**base, 'en_lower': {'$regex': pattern}}, fields).limit(limit))
        docs.sort(key=lambda d: len((d.get('text') or {}).get(LANG_EN) or ''))

    return [{'key': d['_id'], 'en': (d.get('text') or {}).get(LANG_EN),
             'zh': _translation_of(d, lang)} for d in docs], mode


def status() -> dict:
    return get_db()[META_COLLECTION].find_one({'_id': 'status'}) or {}


# ── 寫入（同步用）──────────────────────────────────────────────────

def ensure_indexes(db=None):
    # pymongo 的 Database 不能拿來做 bool 判斷（會丟 NotImplementedError），
    # 一定要跟 None 比；mongomock 沒有這個限制，測試抓不到
    if db is None:
        db = get_db()
    db[COLLECTION].create_index('key_lower')
    db[COLLECTION].create_index([('en_lower', ASCENDING), ('key_lower', ASCENDING)])
    db[COLLECTION].create_index('en_norm')
    db[COLLECTION].create_index([('source', ASCENDING), ('domain', ASCENDING)])


def replace_source(entries, source: str, stamp: datetime, bulk_size: int = 1000) -> dict:
    """把某個來源（game／manual）的全部條目換成 entries，回傳統計。

    entries：可迭代的 (_id, text, domain)。刻意用串流（generator）而不是先組好
    一整個 dict：遊戲在地化表約 9 萬筆，worker container 記憶體只有 256MB，
    一次把英文表、翻譯包、組好的文件全留在記憶體裡會很吃緊。

    內容沒變（雜湊相同）的不重寫；這個來源裡這次沒出現的 key 會刪掉
    （翻譯表是衍生資料，不需要保留歷史）。
    """
    col = _col()
    existing = {row['_id']: row.get('h') for row in
                col.find({'source': source}, {'_id': 1, 'h': 1})}
    seen_ids = set()
    ops: list = []
    written = 0

    def flush():
        nonlocal ops, written
        if ops:
            col.bulk_write(ops, ordered=False)
            written += sum(1 for op in ops if isinstance(op, UpdateOne))
            ops = []

    for _id, text, domain in entries:
        text = {k: v for k, v in (text or {}).items() if v}
        if not _id or not text.get(LANG_EN) or _id in seen_ids:
            continue
        seen_ids.add(_id)
        h = text_hash(text)
        if existing.get(_id) == h:
            continue
        ops.append(UpdateOne({'_id': _id}, {'$set': {
            'key_lower': _id.lower(),
            'text': text,
            'en_lower': text[LANG_EN].strip().lower(),
            'en_norm': normalize_english(text[LANG_EN]),
            'source': source,
            'domain': domain,
            'h': h,
            'updated_at': stamp,
        }}, upsert=True))
        if len(ops) >= bulk_size:
            flush()

    stale = [i for i in existing if i not in seen_ids]
    for _id in stale:
        ops.append(DeleteOne({'_id': _id}))
        if len(ops) >= bulk_size:
            flush()
    flush()
    return {'seen': len(seen_ids), 'written': written, 'retired': len(stale)}


MANUAL_FILE = Path(__file__).resolve().parent.parent / 'data' / 'sc_translation_manual.json'


def iter_manual_entries(path: Path = MANUAL_FILE):
    """人工條目（src/data/sc_translation_manual.json）→ yield (_id, text, domain)。"""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for domain, entries in data.items():
        if domain.startswith('_') or not isinstance(entries, dict):
            continue
        for ident, langs in entries.items():
            text = {LANG_EN: (langs.get(LANG_EN) or ident)}
            text.update({k: v for k, v in langs.items() if k != LANG_EN and v})
            yield manual_key(domain, ident), text, domain


def backfill_en_norm(bulk_size: int = 2000) -> int:
    """補上舊資料沒有的 en_norm（內容沒變的條目同步時不會重寫，所以要另外補一次）。"""
    col = _col()
    ops, done = [], 0
    for row in col.find({'en_norm': {'$exists': False}}, {'text.en': 1}):
        ops.append(UpdateOne({'_id': row['_id']}, {'$set': {
            'en_norm': normalize_english(((row.get('text') or {}).get(LANG_EN)) or '')}}))
        if len(ops) >= bulk_size:
            col.bulk_write(ops, ordered=False)
            done += len(ops)
            ops = []
    if ops:
        col.bulk_write(ops, ordered=False)
        done += len(ops)
    if done:
        clear_cache()
    return done


def sync_manual(stamp: datetime = None) -> dict:
    """把人工條目寫進資料庫（每次翻譯同步、以及 app 啟動時都會跑，很便宜）。"""
    stats = replace_source(iter_manual_entries(), SOURCE_MANUAL, stamp or datetime.utcnow())
    if stats['written'] or stats['retired']:
        clear_cache()
    return stats


def count(source: str) -> int:
    return _col().count_documents({'source': source})


def mark_synced(version: str, stamp: datetime, **info):
    get_db()[META_COLLECTION].update_one(
        {'_id': 'status'},
        {'$set': {'version': version, 'synced_at': stamp, **info}},
        upsert=True)
    clear_cache()
