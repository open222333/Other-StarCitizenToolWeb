"""429（Flask-Limiter 次數限制）要回中文訊息，不是套件預設的英文 "4 per 1 hour"。

全站測試把 limiter 關掉了（見 conftest.py），這裡另外起一個小 app、掛真的
Limiter，確認 app/__init__.py 的 429 handler 拿到的是真實的例外物件也能解析。
"""
from flask import Flask
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app import handle_rate_limit


def _client(spec):
    mini = Flask('rate_limit_test')
    limiter = Limiter(key_func=get_remote_address, app=mini, storage_uri='memory://')

    @mini.route('/x')
    @limiter.limit(spec)
    def x():
        return 'ok'

    mini.register_error_handler(429, handle_rate_limit)
    return mini.test_client()


def test_hourly_limit_message_is_chinese():
    client = _client('2 per hour')
    assert client.get('/x').status_code == 200
    assert client.get('/x').status_code == 200
    resp = client.get('/x')
    assert resp.status_code == 429
    assert resp.get_json() == {'success': False,
                               'message': '操作太頻繁（上限：每小時 2 次），請稍後再試'}


def test_multi_unit_limit_message():
    client = _client('1 per 5 minute')
    client.get('/x')
    assert client.get('/x').get_json()['message'] == '操作太頻繁（上限：每 5 分鐘 1 次），請稍後再試'
