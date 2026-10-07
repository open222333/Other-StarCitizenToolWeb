"""玩家頁「中文轉碼」字典（src/models/chat_code.py）：快取、下載失敗沿用舊版。"""
from datetime import datetime, timedelta

import src.models.chat_code as chat_code
from src.mongo import get_db

DICT = '﻿# comment\n' + '\n'.join(f'{i:04X}=字' for i in range(1200))


def test_dictionary_cache_and_fallback(client, monkeypatch):
    calls = []

    def ok():
        calls.append(1)
        return DICT.lstrip('﻿')

    monkeypatch.setattr(chat_code, '_download', ok)
    first = chat_code.get_dictionary()
    assert first['entries'] == 1200 and first['stale'] is False
    chat_code.get_dictionary()
    assert len(calls) == 1, '24 小時內用快取'

    def fail():
        raise RuntimeError('offline')

    monkeypatch.setattr(chat_code, '_download', fail)
    later = chat_code.get_dictionary(now=datetime.utcnow() + timedelta(hours=25))
    assert later['stale'] is True and later['entries'] == 1200, '下載失敗沿用舊版'

    get_db()['chat_code_dictionary'].delete_many({})
    try:
        chat_code.get_dictionary()
        assert False, '從沒成功過又下載失敗要報錯'
    except chat_code.ChatCodeError:
        pass


def test_count_entries():
    assert chat_code.count_entries('00=一\n; x=y\n# a=b\nbad\n01=乙') == 2


def test_dictionary_endpoint(client, auth_headers, monkeypatch):
    from tests.test_fleet import _register_player
    url = '/player/chat-code/dictionary'
    assert client.get(url).status_code == 401
    assert client.get(url, headers=auth_headers).status_code in (401, 403), '後台身分不是玩家'
    player = _register_player(client, 'CodePilot', 'Code')

    monkeypatch.setattr(chat_code, '_download', lambda: (_ for _ in ()).throw(RuntimeError('x')))
    assert client.get(url, headers=player).status_code == 503

    monkeypatch.setattr(chat_code, '_download', lambda: DICT)
    body = client.get(url, headers=player).get_json()
    assert body['success'] and body['data']['entries'] == 1200 and '0000=字' in body['data']['text']
