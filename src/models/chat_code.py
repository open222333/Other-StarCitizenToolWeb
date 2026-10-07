"""玩家頁「中文轉碼」用的字典（聊天輸入用的中文 ↔ @xxx 代碼表）。

遊戲聊天框不能直接打中文，社群的中文化包把每個中文字對應到一組代碼（例如 `0A=八`），
在聊天輸入 `@0A` 遊戲會顯示成「八」。字典來源是社群專案 taksito/chsc-tw 的
textinput.txt（約七千字），原本是 tctp_translator 工具啟動時自己下載。

⚠️ 這是**字元編碼表**，不是遊戲文字的翻譯，所以不放進 sc_translations（翻譯的唯一來源），
另外存在 `chat_code_dictionary`（單筆，_id = 'textinput'）。

快取策略：超過 CACHE_HOURS 才重新下載；下載失敗就繼續用資料庫裡的舊版，
兩者都沒有才回報錯誤。轉換本身在前端做（frontend/src/utils/chatCode.js），
這裡只負責提供字典原文。
"""

from datetime import datetime, timedelta

import httpx

from src.mongo import get_db

DICT_URL = 'https://raw.githubusercontent.com/taksito/chsc-tw/main/textinput.txt'
DICT_ID = 'textinput'
CACHE_HOURS = 24
#: 正常大約一百多 KB；太大或太小都當作下載到錯的東西，不覆蓋舊版
MIN_ENTRIES = 1000
MAX_BYTES = 2 * 1024 * 1024


class ChatCodeError(Exception):
    pass


def _col():
    return get_db()['chat_code_dictionary']


def count_entries(text: str) -> int:
    return sum(1 for line in text.splitlines()
               if '=' in line and not line.lstrip().startswith(('#', ';')))


def _download() -> str:
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        resp = client.get(DICT_URL)
        resp.raise_for_status()
        if len(resp.content) > MAX_BYTES:
            raise ChatCodeError('字典檔異常（太大）')
        text = resp.content.decode('utf-8-sig', errors='ignore')
    if count_entries(text) < MIN_ENTRIES:
        raise ChatCodeError('字典檔異常（內容太少）')
    return text


def get_dictionary(now=None) -> dict:
    """回傳 {text, fetched_at, entries, stale}。stale = 這次想更新但下載失敗、用的是舊版。"""
    now = now or datetime.utcnow()
    doc = _col().find_one({'_id': DICT_ID})
    if doc and doc.get('fetched_at') and now - doc['fetched_at'] < timedelta(hours=CACHE_HOURS):
        return {'text': doc['text'], 'fetched_at': doc['fetched_at'],
                'entries': doc.get('entries'), 'stale': False}
    try:
        text = _download()
    except Exception as err:
        if doc and doc.get('text'):
            return {'text': doc['text'], 'fetched_at': doc.get('fetched_at'),
                    'entries': doc.get('entries'), 'stale': True}
        raise ChatCodeError(f'無法取得中文轉碼字典：{err}')
    entries = count_entries(text)
    _col().update_one({'_id': DICT_ID}, {'$set': {
        'text': text, 'fetched_at': now, 'entries': entries, 'source': DICT_URL}}, upsert=True)
    return {'text': text, 'fetched_at': now, 'entries': entries, 'stale': False}
