"""後台可直接修改的系統設定（`app_settings` collection，一個設定一筆，_id = 設定名稱）。

- 玩家頁分頁的排列順序（PlayerTabOrder，後台「系統設定」）
- 玩家頁分頁的開放狀態（PlayerTabAccess：開放／預設不顯示／不開放，後台「系統設定」）

UEX Corp API token：後台「資料同步排程」頁可以直接填，不用再改 `.env`
重啟容器。後台填的優先；沒填就退回環境變數 `UEX_API_TOKEN`（舊的設定方式照樣能用）。

token 是機密：API 只回「有沒有設定、來源、末 4 碼」，**不會把完整 token 回給前端**，
也不寫進操作紀錄。
"""

import re
from datetime import datetime

from src import UEX_API_TOKEN
from src.mongo import get_db

UEX_TOKEN_ID = 'uex_api_token'
UEX_TOKEN_MAX = 500


def _col():
    return get_db()['app_settings']


def _mask(token: str) -> str:
    return '••••' + token[-4:] if len(token) > 4 else '••••'


class UexToken:
    """UEX API token：後台設定（DB）優先，其次環境變數。"""

    @staticmethod
    def get() -> str:
        doc = _col().find_one({'_id': UEX_TOKEN_ID}) or {}
        return (doc.get('value') or '').strip() or UEX_API_TOKEN

    @staticmethod
    def status() -> dict:
        doc = _col().find_one({'_id': UEX_TOKEN_ID}) or {}
        value = (doc.get('value') or '').strip()
        if value:
            return {'configured': True, 'source': 'admin', 'masked': _mask(value),
                    'updated_at': doc.get('updated_at'), 'updated_by': doc.get('updated_by')}
        if UEX_API_TOKEN:
            return {'configured': True, 'source': 'env', 'masked': _mask(UEX_API_TOKEN),
                    'updated_at': None, 'updated_by': None}
        return {'configured': False, 'source': None, 'masked': '',
                'updated_at': None, 'updated_by': None}

    @staticmethod
    def set(token, updated_by=None) -> dict:
        """存後台填的 token；空字串＝清掉（改回用環境變數）。格式不對丟 ValueError。"""
        if not isinstance(token, str):
            raise ValueError('token 格式錯誤')
        token = token.strip()
        if len(token) > UEX_TOKEN_MAX or any(c.isspace() for c in token):
            raise ValueError('token 格式錯誤（不能有空白，最多 500 字）')
        if token:
            _col().update_one({'_id': UEX_TOKEN_ID}, {'$set': {
                'value': token, 'updated_at': datetime.utcnow(), 'updated_by': updated_by}},
                upsert=True)
        else:
            _col().delete_one({'_id': UEX_TOKEN_ID})
        return UexToken.status()


PLAYER_TAB_ORDER_ID = 'player_tab_order'
#: 分頁代號的格式（實際有哪些分頁由前端 frontend/src/utils/playerTabs.js 決定，後端只擋格式、數量）
_TAB_KEY_RE = re.compile(r'^[a-z][a-z0-9_]{0,19}$')
TAB_ORDER_MAX = 30


class PlayerTabOrder:
    """玩家頁分頁的排列順序（後台「系統設定」可拖拉排序）。空清單＝照程式預設順序。

    清單裡沒列到的分頁（例如之後新增的）由前端接在最後面，所以這裡存的順序不會擋住新分頁。
    """

    @staticmethod
    def get() -> list:
        doc = _col().find_one({'_id': PLAYER_TAB_ORDER_ID}) or {}
        value = doc.get('value')
        return [k for k in value if isinstance(k, str)] if isinstance(value, list) else []

    @staticmethod
    def set(keys, updated_by=None) -> list:
        """格式不對丟 ValueError；重複的只留第一個。"""
        if not isinstance(keys, list) or len(keys) > TAB_ORDER_MAX \
                or not all(isinstance(k, str) and _TAB_KEY_RE.match(k) for k in keys):
            raise ValueError('分頁順序格式錯誤')
        keys = list(dict.fromkeys(keys))
        _col().update_one({'_id': PLAYER_TAB_ORDER_ID}, {'$set': {
            'value': keys, 'updated_at': datetime.utcnow(), 'updated_by': updated_by}}, upsert=True)
        return keys


PLAYER_TAB_ACCESS_ID = 'player_tab_access'
#: 分頁開放狀態：open＝開放（預設）、hidden＝預設不顯示（玩家可以在「個人資料」自己打開）、closed＝不開放（玩家看不到也打不開）
TAB_ACCESS_VALUES = ('open', 'hidden', 'closed')
#: 一定開放的分頁（玩家要靠它打開其他分頁）
TAB_ALWAYS_OPEN = ('profile',)


class PlayerTabAccess:
    """玩家頁分頁的開放狀態（後台「系統設定」）。只存不是 open 的分頁：{分頁代號: hidden／closed}。"""

    @staticmethod
    def get() -> dict:
        doc = _col().find_one({'_id': PLAYER_TAB_ACCESS_ID}) or {}
        value = doc.get('value')
        if not isinstance(value, dict):
            return {}
        return {k: v for k, v in value.items()
                if isinstance(k, str) and v in TAB_ACCESS_VALUES and v != 'open' and k not in TAB_ALWAYS_OPEN}

    @staticmethod
    def set(access, updated_by=None) -> dict:
        """access：{分頁代號: open／hidden／closed}；格式不對丟 ValueError。open 的不存。"""
        if not isinstance(access, dict) or len(access) > TAB_ORDER_MAX:
            raise ValueError('分頁開放狀態格式錯誤')
        clean = {}
        for k, v in access.items():
            if not (isinstance(k, str) and _TAB_KEY_RE.match(k)) or v not in TAB_ACCESS_VALUES:
                raise ValueError('分頁開放狀態格式錯誤')
            if v != 'open' and k not in TAB_ALWAYS_OPEN:
                clean[k] = v
        _col().update_one({'_id': PLAYER_TAB_ACCESS_ID}, {'$set': {
            'value': clean, 'updated_at': datetime.utcnow(), 'updated_by': updated_by}}, upsert=True)
        return clean
