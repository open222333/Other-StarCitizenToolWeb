"""後台「資料備份」：匯出／匯入還原「不是同步排程抓來的」資料。

同步排程會自己重抓的主檔（物品、藍圖主檔、載具、地點、任務、UEX 價格、翻譯…）不在這裡——壞了重跑同步就好。
這裡只管人產生、重抓不回來的資料（BACKUP_SETS）：後台帳號、會員、會員的倉庫／藍圖／艦隊、系統設定、工具網站，
以及可選的紀錄（操作日誌、庫存異動，預設不勾，量可能很大）。

檔案格式：gzip 壓縮的 JSON（MongoDB Extended JSON，ObjectId、日期原樣保留），
    {"format": BACKUP_FORMAT, "version": 1, "exported_at": …, "sets": [key…], "collections": {name: [doc…]}}
包含密碼雜湊、UEX API token 這類機密，檔案要自己保管好。

還原＝整個資料表換成檔案裡的內容（不是合併）：先寫進暫存資料表，全部寫完再一次改名蓋過原本的
（寫到一半出錯，原本的資料表不會動），最後重建索引。
"""

import gzip
import json
from datetime import datetime, timezone

from bson import json_util

from src.mongo import ensure_indexes, get_db

BACKUP_FORMAT = 'sc-tool-backup'
BACKUP_VERSION = 1

#: 可以匯出／還原的資料（key、名稱、資料表、預設勾選）
BACKUP_SETS = [
    {'key': 'accounts', 'label': '後台帳號', 'collections': ['users', 'user_templates', 'device_tokens'], 'default': True},
    {'key': 'players', 'label': '會員', 'collections': ['players', 'discord_bindings'], 'default': True},
    {'key': 'player_data', 'label': '會員資料（倉庫、藍圖、艦隊）', 'collections': ['inventory', 'blueprints', 'fleet'],
     'default': True},
    {'key': 'settings', 'label': '系統設定（分頁設定、物品類型分組、同步排程、玩家頁面顯示、礦物手動關聯、UEX token）',
     'collections': ['app_settings', 'sync_schedule', 'player_visibility', 'mineral_uex_links'], 'default': True},
    {'key': 'tool_links', 'label': '工具網站', 'collections': ['tool_links', 'tool_link_tags'], 'default': True},
    {'key': 'logs', 'label': '紀錄（操作日誌、庫存異動紀錄）', 'collections': ['logs', 'inventory_log'], 'default': False},
]
SETS_BY_KEY = {s['key']: s for s in BACKUP_SETS}


class BackupError(ValueError):
    """檔案或參數不對（給呼叫端回 400）。"""


def list_sets() -> list:
    """每一組的資料表與目前筆數。"""
    db = get_db()
    return [{
        'key': s['key'], 'label': s['label'], 'default': s['default'],
        'collections': [{'name': c, 'count': db[c].estimated_document_count()} for c in s['collections']],
    } for s in BACKUP_SETS]


def _pick(keys) -> list:
    keys = [k for k in (keys or []) if k]
    unknown = [k for k in keys if k not in SETS_BY_KEY]
    if unknown:
        raise BackupError(f'沒有這種資料：{"、".join(unknown)}')
    if not keys:
        raise BackupError('請至少選一種資料')
    return [s for s in BACKUP_SETS if s['key'] in keys]


def export_gzip(keys) -> bytes:
    """選的那幾組資料匯出成 gzip 壓縮的 JSON。"""
    sets = _pick(keys)
    db = get_db()
    payload = {
        'format': BACKUP_FORMAT,
        'version': BACKUP_VERSION,
        'exported_at': datetime.now(timezone.utc).isoformat(),
        'sets': [s['key'] for s in sets],
        'collections': {c: list(db[c].find({})) for s in sets for c in s['collections']},
    }
    text = json_util.dumps(payload, json_options=json_util.RELAXED_JSON_OPTIONS, ensure_ascii=False)
    return gzip.compress(text.encode('utf-8'))


def load_file(raw: bytes) -> dict:
    """讀備份檔（gzip 或純 JSON 都可以），檢查格式。"""
    if not raw:
        raise BackupError('檔案是空的')
    if raw[:2] == b'\x1f\x8b':
        try:
            raw = gzip.decompress(raw)
        except OSError as exc:
            raise BackupError('檔案解壓縮失敗') from exc
    try:
        data = json_util.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, ValueError) as exc:
        raise BackupError('不是有效的備份檔（JSON 讀不出來）') from exc
    if not isinstance(data, dict) or data.get('format') != BACKUP_FORMAT:
        raise BackupError('不是這個網站匯出的備份檔')
    if data.get('version') != BACKUP_VERSION:
        raise BackupError(f'備份檔版本不支援（{data.get("version")}）')
    if not isinstance(data.get('collections'), dict):
        raise BackupError('備份檔缺少資料')
    return data


def summary(data: dict) -> dict:
    """備份檔的內容摘要（還原前給管理員確認）。"""
    cols = data['collections']
    return {
        'exported_at': data.get('exported_at'),
        'sets': [{'key': s['key'], 'label': s['label'],
                  'collections': [{'name': c, 'count': len(cols.get(c) or [])} for c in s['collections']]}
                 for s in BACKUP_SETS if s['key'] in (data.get('sets') or [])],
    }


def restore(data: dict, keys, keep_username: str = '') -> dict:
    """把選的那幾組資料表整個換成備份檔裡的內容，回傳每個資料表還原了幾筆。

    keep_username：目前操作的後台帳號。還原「後台帳號」時備份檔裡要有這個帳號，
    不然還原完自己就登不進來了。
    """
    sets = _pick(keys)
    in_file = set(data.get('sets') or [])
    missing = [s['label'] for s in sets if s['key'] not in in_file]
    if missing:
        raise BackupError(f'備份檔裡沒有：{"、".join(missing)}')
    cols = data['collections']
    if keep_username and any(s['key'] == 'accounts' for s in sets):
        if not any((u or {}).get('username') == keep_username for u in cols.get('users') or []):
            raise BackupError(f'備份檔的後台帳號裡沒有你目前登入的帳號（{keep_username}），還原後會登不進來')

    db = get_db()
    names = [c for s in sets for c in s['collections']]
    # 先全部寫進暫存資料表；任何一個出錯就把暫存的清掉，原本的資料不動
    temps = {}
    try:
        for name in names:
            temp = f'{name}__restore'
            db[temp].drop()
            docs = cols.get(name) or []
            if docs:
                db[temp].insert_many(docs, ordered=True)
            temps[name] = temp
    except Exception:
        for temp in temps.values():
            db[temp].drop()
        raise
    counts = {}
    for name, temp in temps.items():
        docs = cols.get(name) or []
        if docs:
            db[temp].rename(name, dropTarget=True)
        else:
            db[name].delete_many({})
            db[temp].drop()
        counts[name] = len(docs)
    ensure_indexes()
    return counts
