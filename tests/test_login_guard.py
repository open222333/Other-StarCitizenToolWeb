"""登入防暴力破解（src/models/login_guard.py）＋操作紀錄記 IP。"""
from datetime import datetime, timedelta

from src.models import login_guard
from src.mongo import get_db


def _login(client, password, username='admin', ip='10.0.0.1'):
    return client.post('/auth/login', json={'username': username, 'password': password},
                       environ_base={'REMOTE_ADDR': ip})


def test_admin_account_locked_after_failures(client, seed_admin):
    for _ in range(login_guard.ACCOUNT_MAX):
        assert _login(client, 'wrong').status_code == 401
    res = _login(client, 'Admin1234!')    # 鎖定期間連對的密碼也不放行
    assert res.status_code == 429 and '分鐘後再試' in res.get_json()['message']
    # 換 IP 也一樣（鎖的是帳號）
    assert _login(client, 'Admin1234!', ip='10.0.0.2').status_code == 429
    # 時間過了就解開
    get_db()['login_failures'].update_many({}, {'$set': {'at': datetime.utcnow() - timedelta(hours=1)}})
    assert _login(client, 'Admin1234!').status_code == 200


def test_success_clears_account_failures(client, seed_admin):
    for _ in range(login_guard.ACCOUNT_MAX - 1):
        _login(client, 'wrong')
    assert _login(client, 'Admin1234!').status_code == 200
    assert _login(client, 'wrong').status_code == 401, '成功登入後重新計算'


def test_ip_locked_after_many_accounts(client, seed_admin):
    for i in range(login_guard.IP_MAX):
        _login(client, 'x', username=f'nobody{i}', ip='10.9.9.9')
    assert _login(client, 'Admin1234!', ip='10.9.9.9').status_code == 429
    assert _login(client, 'Admin1234!', ip='10.9.9.8').status_code == 200, '別的 IP 不受影響'


def test_player_login_guard_and_log_ip(client):
    client.post('/player/register', json={'nickname': 'abcd1234', 'star_citizen_id': 'abcd1234',
                                           'password': 'player-pw-123'})
    login = lambda pw: client.post('/player/login', json={'star_citizen_id': 'abcd1234', 'password': pw},
                                   environ_base={'REMOTE_ADDR': '10.1.1.1'})
    for _ in range(login_guard.ACCOUNT_MAX):
        assert login('bad').status_code == 401
    assert login('player-pw-123').status_code == 429
    log = get_db()['logs'].find_one({'username': 'player:abcd1234', 'success': False})
    assert log['ip'] == '10.1.1.1' and log['action'] == 'player_login'


def test_admin_login_log_has_ip(client, seed_admin, auth_headers):
    _login(client, 'wrong', ip='10.2.2.2')
    rows = client.get('/log/', headers=auth_headers).get_json()['data']
    assert any(r.get('ip') == '10.2.2.2' for r in rows)


def test_player_remember_me(client):
    client.post('/player/register', json={'nickname': 'efgh5678', 'star_citizen_id': 'efgh5678',
                                           'password': 'player-pw-123'})
    body = lambda **kw: client.post('/player/login', json={'star_citizen_id': 'efgh5678',
                                                          'password': 'player-pw-123', **kw}).get_json()
    assert 'refresh_token' in body(remember_me=True)
    assert 'refresh_token' not in body(remember_me=False)
    assert 'refresh_token' in body(), '舊版前端沒帶 remember_me 照舊給'
