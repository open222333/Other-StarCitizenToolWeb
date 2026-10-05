"""後台可直接修改的系統設定（`app_settings` collection，一個設定一筆，_id = 設定名稱）。

目前只有 UEX Corp API token：後台「資料同步排程」頁可以直接填，不用再改 `.env`
重啟容器。後台填的優先；沒填就退回環境變數 `UEX_API_TOKEN`（舊的設定方式照樣能用）。

token 是機密：API 只回「有沒有設定、來源、末 4 碼」，**不會把完整 token 回給前端**，
也不寫進操作紀錄。
"""

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
