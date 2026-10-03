"""遊戲資料「是否在玩家頁面顯示」（藍圖、任務、礦床、礦物、採礦地點、艦船、地點）。

每個資料庫的文件上有這幾個欄位（只有同步後的整理步驟 apply() 會寫，mapper 不輸出，
所以重新同步不會蓋掉）：

  - player_visible_auto：自動判斷（名稱明顯是佔位／開發中的 → False）
  - player_hidden_reason：自動判斷成不顯示的原因（顯示用）
  - player_visible_override：後台手動設定 True／False，None = 跟著自動判斷
  - player_visible：實際結果 = override ?? auto

手動設定另外存在 player_visibility collection（_id = "<資料庫>:<id>"），apply() 每次
從那裡讀回來，就算主檔被整個重建也不會遺失。

礦物沒有自己的 collection（從礦床成分彙整，見 MiningView.vue），只存手動設定，
查詢時用 minerals_state() 算。

玩家端查詢一律用 hidden_filter()（player_visible != False），還沒整理過的舊資料
沒有這個欄位 → 照常顯示。
"""

import re
from datetime import datetime
from typing import Optional

from pymongo import UpdateOne

from src.mongo import get_db

OVERRIDE_COLLECTION = 'player_visibility'

#: 資料庫 key → (顯示名稱, collection, 名稱欄位)；collection 是 None 的是彙整出來的（礦物）
DATASETS = {
    'blueprints':       ('藍圖', 'blueprint_master', 'name'),
    'missions':         ('任務', 'mission_master', 'title'),
    'mining_deposits':  ('礦床', 'mining_deposit_master', 'deposit_name'),
    'minerals':         ('礦物', None, 'resource_name'),
    'mining_locations': ('採礦地點', 'mining_location_master', 'location_name'),
    'vehicles':         ('艦船', 'vehicle_master', 'name'),
    'locations':        ('地點', 'starmap_master', 'name'),
}

#: 同步項目（src/models/sync_schedule.py 的 SYNC_JOBS）→ 同步完要重新整理的資料庫
SYNC_JOB_DATASETS = {
    'blueprints': ['blueprints'],
    'missions': ['missions'],
    'mining': ['mining_deposits', 'mining_locations'],
    'vehicles': ['vehicles'],
    'locations': ['locations'],
}

# ── 自動判斷 ─────────────────────────────────────────────────────

#: (regex, 原因)。比對的是英文名稱；順序 = 優先顯示的原因
_UNFINISHED = [
    (r'^\s*$', '沒有名稱'),
    (r'<=.*=>', '佔位文字'),
    (r'\bplace\s*holder\b|\bplaceholder', '佔位文字'),
    (r'\buninitiali[sz]ed\b', '佔位文字'),
    (r'^@|^loc_', '未翻譯的文字代碼'),
    (r'\[\s*(ph|wip|tbd|todo|test|dev|unused|temp)\s*\]', '開發中標記'),
    (r'^\s*ph[\s_:\-]', '開發中標記'),
    (r'\b(wip|tbd|todo)\b', '開發中標記'),
    (r'work\s*in\s*progress|in\s+development|coming\s+soon', '開發中標記'),
    (r'do\s*not\s*use|\bdnu\b|\bnot\s+used\b|\bunused\b|\bdeprecated\b|\bobsolete\b', '停用標記'),
    (r'\b(test|testing|debug|dummy|temp)\b|(^|_)(test|debug|dummy|temp)(_|$)', '測試用'),
    (r'^[A-Za-z0-9]+(_[A-Za-z0-9]+)+$', '內部代碼（不是顯示名稱）'),
]
_UNFINISHED_RE = [(re.compile(p, re.IGNORECASE), reason) for p, reason in _UNFINISHED]

#: 內部代碼（藍圖 key、礦床 key、任務 debug_name、艦船 class_name）裡的測試／範本標記。
#: 代碼本來就是底線連起來的英文，所以只看這幾個字，不套用上面的「內部代碼」規則。
_KEY_UNFINISHED_RE = re.compile(
    r'(^|_)(test|testing|template|debug|dummy|temp|placeholder|wip|unused|deprecated|dnu)(_|$)', re.IGNORECASE)

#: 資料庫 → 要另外檢查的代碼欄位
_KEY_FIELDS = {
    'blueprints': 'key', 'mining_deposits': 'key', 'missions': 'debug_name', 'vehicles': 'class_name',
}


def unfinished_reason(name) -> Optional[str]:
    """名稱明顯是佔位／開發中／測試用的 → 原因；看起來正常回 None。"""
    text = name if isinstance(name, str) else ''
    for pattern, reason in _UNFINISHED_RE:
        if pattern.search(text):
            return reason
    return None


def auto_reason(dataset: str, doc: dict) -> Optional[str]:
    """自動判斷「不顯示」的原因（None = 顯示）。除了名稱，任務另外看上游的開發中旗標。"""
    if dataset == 'missions':
        if doc.get('work_in_progress') is True:
            return '上游標記開發中'
        if doc.get('not_for_release') is True:
            return '上游標記不公開'
    reason = unfinished_reason(doc.get(DATASETS[dataset][2]))
    if reason:
        return reason
    code = doc.get(_KEY_FIELDS.get(dataset, ''))
    if isinstance(code, str) and _KEY_UNFINISHED_RE.search(code):
        return f'代碼含測試／範本標記（{code}）'
    return None


def hidden_filter() -> dict:
    """玩家端查詢要加的條件（沒整理過、沒有欄位的照常顯示）。"""
    return {'player_visible': {'$ne': False}}


def add_filter(filt: dict, *, visible_only: bool = False, visibility=None) -> dict:
    """查詢條件加上顯示篩選：visible_only（玩家端）或後台篩選 visibility（True 顯示／False 不顯示）。"""
    if visible_only or visibility is True:
        filt['player_visible'] = {'$ne': False}
    elif visibility is False:
        filt['player_visible'] = False
    return filt


def is_visible(doc: dict) -> bool:
    return (doc or {}).get('player_visible') is not False


# ── 手動設定 ─────────────────────────────────────────────────────

def _col():
    return get_db()[OVERRIDE_COLLECTION]


def overrides(dataset: str) -> dict:
    """{doc_id: True/False}"""
    return {r['doc_id']: r['visible'] for r in _col().find({'dataset': dataset},
                                                           {'doc_id': 1, 'visible': 1})}


def _state(dataset: str, doc: dict, override) -> dict:
    reason = auto_reason(dataset, doc)
    auto = reason is None
    return {
        'player_visible_auto': auto,
        'player_hidden_reason': reason,
        'player_visible_override': override,
        'player_visible': auto if override is None else bool(override),
    }


#: auto_reason() 會讀到的其他欄位
_EXTRA_FIELDS = {'work_in_progress': 1, 'not_for_release': 1, 'key': 1, 'debug_name': 1, 'class_name': 1}

STATE_FIELDS = ('player_visible_auto', 'player_hidden_reason', 'player_visible_override', 'player_visible')


def apply(dataset: str) -> int:
    """重新整理一個資料庫的顯示欄位（同步完、翻譯更新完會跑），回傳變動筆數。"""
    label, collection, name_field = DATASETS[dataset]
    if not collection:
        return 0
    col = get_db()[collection]
    manual = overrides(dataset)
    projection = {name_field: 1, **_EXTRA_FIELDS, **{f: 1 for f in STATE_FIELDS}}
    ops = []
    for row in col.find({}, projection):
        new = _state(dataset, row, manual.get(row['_id']))
        if any(row.get(k) != v for k, v in new.items()):
            ops.append(UpdateOne({'_id': row['_id']}, {'$set': new}))
    for i in range(0, len(ops), 1000):
        col.bulk_write(ops[i:i + 1000], ordered=False)
    return len(ops)


def apply_for_job(job_key: str) -> int:
    return sum(apply(ds) for ds in SYNC_JOB_DATASETS.get(job_key, []))


def set_override(dataset: str, doc_id: str, value, username: str = '') -> Optional[dict]:
    """後台手動設定：True／False 蓋過自動判斷，None 回到自動。回傳新的顯示欄位，找不到回 None。"""
    if dataset not in DATASETS:
        raise ValueError(f'不支援的資料庫：{dataset}')
    if value not in (True, False, None):
        raise ValueError('player_visible 只能是 true、false 或 null')
    doc_id = (doc_id or '').strip()
    label, collection, name_field = DATASETS[dataset]
    if collection:
        doc = get_db()[collection].find_one({'_id': doc_id}, {name_field: 1, **_EXTRA_FIELDS})
    else:
        doc = _mineral(doc_id)
    if not doc:
        return None

    key = f'{dataset}:{doc_id}'
    if value is None:
        _col().delete_one({'_id': key})
    else:
        _col().update_one({'_id': key}, {'$set': {
            'dataset': dataset, 'doc_id': doc_id, 'visible': value,
            'updated_by': username or None, 'updated_at': datetime.utcnow()}}, upsert=True)
    state = _state(dataset, doc, value)
    if collection:
        get_db()[collection].update_one({'_id': doc_id}, {'$set': state})
    return state


# ── 礦物（從礦床成分彙整，沒有自己的文件）──────────────────────────

def _mineral(resource_key: str) -> Optional[dict]:
    row = get_db()['mining_deposit_master'].find_one(
        {'is_current': True, 'parts.resource_key': resource_key}, {'parts': 1})
    for part in (row or {}).get('parts') or []:
        if part.get('resource_key') == resource_key:
            return {'_id': resource_key, 'resource_name': part.get('resource_name')}
    return None


def minerals_state(deposits: list) -> dict:
    """{resource_key: 顯示欄位}，礦物清單從礦床的 parts 取。"""
    manual = overrides('minerals')
    out = {}
    for dep in deposits or []:
        for part in dep.get('parts') or []:
            key = part.get('resource_key')
            if key and key not in out:
                out[key] = _state('minerals', {'resource_name': part.get('resource_name')}, manual.get(key))
    return out
