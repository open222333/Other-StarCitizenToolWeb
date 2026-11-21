"""新聞（src/models/news.py、app/news/view.py）與外部 API 金鑰（src/models/api_key.py）。"""
from datetime import datetime, timedelta


def _create(client, headers, **body):
    body.setdefault('title', '測試新聞')
    return client.post('/news/admin', json=body, headers=headers).get_json()


def test_admin_create_and_public_list(client, auth_headers):
    r = _create(client, auth_headers, title='4.5 改版', body='**重點**：新船', tags=['改版', 'RSI'],
                cover_url='https://example.com/a.jpg', source_url='https://robertsspaceindustries.com/a')
    assert r['success']
    _create(client, auth_headers, title='置頂公告', pinned=True)
    future = (datetime.utcnow() + timedelta(days=1)).isoformat() + 'Z'
    _create(client, auth_headers, title='明天才發布', published_at=future)

    body = client.get('/news/').get_json()
    titles = [n['title'] for n in body['data']]
    assert titles[0] == '置頂公告', '置頂排最前面'
    assert '明天才發布' not in titles, '未來的發布時間還不能出現在玩家頁'
    assert body['total'] == 2
    first = next(n for n in body['data'] if n['title'] == '4.5 改版')
    assert first['excerpt'].startswith('重點') and 'body' not in first
    assert first['published_at'].endswith('Z')

    full = client.get(f'/news/{first["_id"]}').get_json()['data']
    assert full['body'] == '**重點**：新船'
    assert client.get('/news/?tag=改版').get_json()['total'] == 1
    assert client.get('/news/?q=新船').get_json()['total'] == 1
    assert {t['tag'] for t in client.get('/news/tags').get_json()['data']} == {'改版', 'RSI'}

    admin = client.get('/news/admin', headers=auth_headers).get_json()
    assert admin['total'] == 3
    assert next(n for n in admin['data'] if n['title'] == '明天才發布')['scheduled'] is True


def test_validation_blocks_bad_urls(client, auth_headers):
    r = client.post('/news/admin', json={'title': 'x', 'cover_url': 'javascript:alert(1)'}, headers=auth_headers)
    assert r.status_code == 400 and '封面' in r.get_json()['message']
    assert client.post('/news/admin', json={'title': ' '}, headers=auth_headers).status_code == 400


def test_update_and_soft_delete(client, auth_headers):
    nid = _create(client, auth_headers, title='舊標題')['data']['_id']
    assert client.put(f'/news/admin/{nid}', json={'title': '新標題'}, headers=auth_headers).get_json()['success']
    assert client.get(f'/news/{nid}').get_json()['data']['title'] == '新標題'
    assert client.delete(f'/news/admin/{nid}', headers=auth_headers).get_json()['success']
    assert client.get(f'/news/{nid}').status_code == 404
    from src.mongo import get_db
    assert get_db()['news'].find_one({'title': '新標題'})['deleted_at'] is not None, '軟刪除'


def test_ingest_with_api_key(client, auth_headers):
    # 沒帶金鑰／亂帶
    assert client.post('/news/ingest', json={'title': 'x'}).status_code == 401
    assert client.post('/news/ingest', json={'title': 'x'}, headers={'X-API-Key': 'sct_nope'}).status_code == 403
    # 後台 JWT 不能拿來 ingest
    assert client.post('/news/ingest', json={'title': 'x'}, headers=auth_headers).status_code in (401, 403)

    created = client.post('/news/keys', json={'name': '新聞爬蟲'}, headers=auth_headers).get_json()['data']
    key = created['key']
    assert key.startswith('sct_') and created['prefix'] == key[:12]
    listed = client.get('/news/keys', headers=auth_headers).get_json()['data']
    assert 'key' not in listed[0] and 'key_hash' not in listed[0]

    h = {'X-API-Key': key}
    r = client.post('/news/ingest', headers=h, json=[
        {'title': 'Comm-Link A', 'source_url': 'https://rsi.example/a', 'tags': ['RSI']},
        {'title': 'Comm-Link B', 'source_url': 'https://rsi.example/b'},
    ]).get_json()
    assert r['success'] and len(r['data']['created']) == 2
    # 同一個來源連結再送一次＝更新
    r = client.post('/news/ingest', headers=h, json={'title': 'Comm-Link A（更新）', 'source_url': 'https://rsi.example/a'}).get_json()
    assert r['data'] == {'created': [], 'updated': r['data']['updated']} and len(r['data']['updated']) == 1
    assert client.get('/news/').get_json()['total'] == 2
    # 一則不合法整批不寫
    r = client.post('/news/ingest', headers=h, json=[{'title': 'ok'}, {'title': ''}])
    assert r.status_code == 400 and '第 2 則' in r.get_json()['message']
    assert client.get('/news/').get_json()['total'] == 2
    # Authorization: Bearer sct_… 也可以
    assert client.post('/news/ingest', json={'title': 'C'}, headers={'Authorization': f'Bearer {key}'}).get_json()['success']

    # 停用後立刻失效
    assert client.delete(f'/news/keys/{created["_id"]}', headers=auth_headers).get_json()['success']
    assert client.post('/news/ingest', headers=h, json={'title': 'x'}).status_code == 403
    keys = client.get('/news/keys', headers=auth_headers).get_json()['data']
    assert keys[0]['revoked'] is True and keys[0]['use_count'] == 4, '每次用金鑰（含被擋下的內容）都算'


def test_key_management_is_admin_only(client):
    from src.models.user import User
    from src.models.user_template import UserTemplate
    User.create('op1', 'Operator1234!', role='operator', template_id=UserTemplate.ensure_defaults())
    token = client.post('/auth/login', json={'username': 'op1', 'password': 'Operator1234!'}).get_json()['token']
    h = {'Authorization': f'Bearer {token}'}
    assert client.get('/news/keys', headers=h).status_code == 403
    assert client.post('/news/keys', json={'name': 'x'}, headers=h).status_code == 403
    # operator 可以管新聞
    assert client.post('/news/admin', json={'title': 'op 發的'}, headers=h).get_json()['success']
