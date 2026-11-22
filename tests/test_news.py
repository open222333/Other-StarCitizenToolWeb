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
    assert titles[0] == '置頂公告', '最新的在最前面'
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

    created = client.post('/data/api-keys', json={'name': '新聞爬蟲', 'scopes': ['news:write']}, headers=auth_headers).get_json()['data']
    key = created['key']
    assert key.startswith('sct_') and created['prefix'] == key[:12]
    listed = client.get('/data/api-keys', headers=auth_headers).get_json()['data']
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
    assert client.delete(f'/data/api-keys/{created["_id"]}', headers=auth_headers).get_json()['success']
    assert client.post('/news/ingest', headers=h, json={'title': 'x'}).status_code == 403
    keys = client.get('/data/api-keys', headers=auth_headers).get_json()['data']
    assert keys[0]['revoked'] is True and keys[0]['use_count'] == 4, '每次用金鑰（含被擋下的內容）都算'


def test_key_management_is_admin_only(client):
    from src.models.user import User
    from src.models.user_template import UserTemplate
    User.create('op1', 'Operator1234!', role='operator', template_id=UserTemplate.ensure_defaults())
    token = client.post('/auth/login', json={'username': 'op1', 'password': 'Operator1234!'}).get_json()['token']
    h = {'Authorization': f'Bearer {token}'}
    assert client.get('/data/api-keys', headers=h).status_code == 403
    assert client.post('/data/api-keys', json={'name': 'x'}, headers=h).status_code == 403
    # operator 可以管新聞
    assert client.post('/news/admin', json={'title': 'op 發的'}, headers=h).get_json()['success']


def test_public_sort_latest_query_cap_and_cache_headers(client, auth_headers):
    """跑馬燈用 sort=latest（不管置頂）；搜尋字串截到 100 字；公開端點有短時間快取。"""
    old = (datetime.utcnow() - timedelta(days=3)).isoformat() + 'Z'
    _create(client, auth_headers, title='舊的置頂', pinned=True, published_at=old)
    _create(client, auth_headers, title='最新一則')
    res = client.get('/news/?sort=latest')
    assert [n['title'] for n in res.get_json()['data']] == ['最新一則', '舊的置頂']
    assert [n['title'] for n in client.get('/news/').get_json()['data']][0] == '最新一則', '玩家頁列表只依時間'
    assert [n['title'] for n in client.get('/news/admin', headers=auth_headers).get_json()['data']][0] == '舊的置頂', '後台置頂在前'
    assert 'max-age' in res.headers.get('Cache-Control', '')
    assert 'max-age' in client.get('/news/tags').headers.get('Cache-Control', '')
    assert client.get('/news/?q=' + '最' + 'x' * 300).get_json()['total'] == 0
    from src.models import news
    assert len(news._filter(True, q='a' * 500)['$or'][0]['title']['$regex']) == news.Q_MAX


def test_admin_list_filters_and_pages(client, auth_headers):
    """後台列表：後端篩選（關鍵字、多個標籤取聯集）＋分頁。"""
    _create(client, auth_headers, title='A', tags=['改版'])
    _create(client, auth_headers, title='B', tags=['活動'])
    _create(client, auth_headers, title='C', tags=['其他'])
    r = client.get('/news/admin?tag=改版&tag=活動', headers=auth_headers).get_json()
    assert r['total'] == 2 and {n['title'] for n in r['data']} == {'A', 'B'}
    r = client.get('/news/admin?limit=1&offset=1', headers=auth_headers).get_json()
    assert r['total'] == 3 and len(r['data']) == 1
    assert client.get('/news/admin?q=C', headers=auth_headers).get_json()['total'] == 1


def test_api_key_requires_scope(client, auth_headers):
    """金鑰管理獨立在 /data/api-keys：建立時要選權限（之後新功能加 scope 就好）。"""
    r = client.post('/data/api-keys', json={'name': '沒權限'}, headers=auth_headers)
    assert r.status_code == 400
    body = client.get('/data/api-keys', headers=auth_headers).get_json()
    assert 'news:write' in body['scopes']


def test_featured_and_unlisted_tags(client, auth_headers):
    """置頂區：官方優先、再置頂、再最新，最多 4 則；下架的標籤：玩家看不到也搜不到，後台照常。"""
    t = lambda d: (datetime.utcnow() - timedelta(days=d)).isoformat() + 'Z'   # noqa: E731
    _create(client, auth_headers, title='官方舊', tags=['官方'], published_at=t(5))
    _create(client, auth_headers, title='官方新', tags=['官方'], published_at=t(4))
    _create(client, auth_headers, title='置頂', pinned=True, published_at=t(6))
    _create(client, auth_headers, title='一般1', published_at=t(1))
    _create(client, auth_headers, title='一般2', published_at=t(2))
    _create(client, auth_headers, title='外流', tags=['外流', '社群'], published_at=t(0))
    f = [n['title'] for n in client.get('/news/featured').get_json()['data']]
    assert f == ['官方新', '官方舊', '置頂', '外流']

    assert client.put('/news/admin/tag-settings', json={'tag': '外流', 'listed': False}, headers=auth_headers).get_json()['success']
    body = client.get('/news/').get_json()
    assert [n['title'] for n in body['data']] == ['一般1', '一般2', '官方新', '官方舊', '置頂'] and body['total'] == 5
    assert [n['title'] for n in client.get('/news/featured').get_json()['data']][-1] == '一般1'
    assert client.get('/news/?q=外流').get_json()['total'] == 0
    assert client.get('/news/?tag=社群').get_json()['total'] == 0, '下架標籤的新聞連其他標籤也篩不到'
    assert '外流' not in {x['tag'] for x in client.get('/news/tags').get_json()['data']}
    hid = next(n for n in client.get('/news/admin', headers=auth_headers).get_json()['data'] if n['title'] == '外流')
    assert client.get(f'/news/{hid["_id"]}').status_code == 404
    rows = {r['tag']: r for r in client.get('/news/admin/tag-settings', headers=auth_headers).get_json()['data']}
    assert rows['外流']['listed'] is False and rows['官方']['listed'] is True

    client.put('/news/admin/tag-settings', json={'tag': '外流', 'listed': True}, headers=auth_headers)
    assert client.get('/news/').get_json()['total'] == 6
    assert client.put('/news/admin/tag-settings', json={'tag': '', 'listed': False}, headers=auth_headers).status_code == 400
    assert client.put('/news/admin/tag-settings', json={'tag': 'x', 'listed': False}).status_code in (401, 403)
