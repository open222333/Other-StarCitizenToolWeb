"""工具網站連結：後台 CRUD（/links/）與玩家頁讀取（/player/tool-links）。"""
import pytest

from src.models.tool_link import ToolLinkError, normalize_url


@pytest.fixture
def player_headers(client):
    client.post('/player/register', json={
        'nickname': 'Linker', 'star_citizen_id': 'LinkerSC', 'password': 'pw-123456'})
    login = client.post('/player/login', json={'star_citizen_id': 'LinkerSC', 'password': 'pw-123456'})
    return {'Authorization': f"Bearer {login.get_json()['token']}"}


def _create(client, headers, **data):
    return client.post('/links/', headers=headers, json=data)


def test_normalize_url():
    assert normalize_url(' https://erkul.games ') == 'https://erkul.games'
    assert normalize_url('uexcorp.space/trade') == 'https://uexcorp.space/trade', '沒寫 scheme 補 https://'
    assert normalize_url('http://example.com') == 'http://example.com'
    for bad in ['', 'javascript:alert(1)', 'JavaScript:alert(1)', 'data:text/html,x',
                'ftp://example.com', 'https://', 'https://exa mple.com']:
        with pytest.raises(ToolLinkError):
            normalize_url(bad)


def test_admin_crud_and_player_listing(client, auth_headers, player_headers):
    resp = _create(client, auth_headers, title='Erkul', url='erkul.games',
                   description='船隻配裝計算器', sort_order=2)
    assert resp.status_code == 201, resp.get_json()
    erkul_id = resp.get_json()['id']
    _create(client, auth_headers, title='UEX', url='https://uexcorp.space', sort_order=1)

    rows = client.get('/links/', headers=auth_headers).get_json()['data']
    assert [r['title'] for r in rows] == ['UEX', 'Erkul'], '依排序值'
    assert rows[1]['url'] == 'https://erkul.games'

    # 只更新有帶的欄位
    assert client.put(f'/links/{erkul_id}', headers=auth_headers,
                      json={'sort_order': 0}).status_code == 200
    rows = client.get('/links/', headers=auth_headers).get_json()['data']
    assert [r['title'] for r in rows] == ['Erkul', 'UEX']
    assert rows[0]['description'] == '船隻配裝計算器'

    # 玩家頁只拿顯示需要的欄位
    public = client.get('/player/tool-links', headers=player_headers).get_json()['data']
    assert [r['title'] for r in public] == ['Erkul', 'UEX']
    assert set(public[0]) == {'_id', 'title', 'url', 'description', 'sort_order'}

    assert client.delete(f'/links/{erkul_id}', headers=auth_headers).status_code == 200
    public = client.get('/player/tool-links', headers=player_headers).get_json()['data']
    assert [r['title'] for r in public] == ['UEX']
    assert client.delete(f'/links/{erkul_id}', headers=auth_headers).status_code == 404


def test_rejects_invalid_input(client, auth_headers):
    assert _create(client, auth_headers, title='', url='https://a.com').status_code == 400
    resp = _create(client, auth_headers, title='XSS', url='javascript:alert(document.cookie)')
    assert resp.status_code == 400
    assert 'http' in resp.get_json()['message']
    assert _create(client, auth_headers, title='x' * 101, url='https://a.com').status_code == 400
    assert _create(client, auth_headers, title='a', url='https://a.com',
                   sort_order='abc').status_code == 400

    link_id = _create(client, auth_headers, title='ok', url='https://a.com').get_json()['id']
    assert client.put(f'/links/{link_id}', headers=auth_headers,
                      json={'url': 'javascript:alert(1)'}).status_code == 400
    assert client.put(f'/links/{link_id}', headers=auth_headers, json={}).status_code == 400
    assert client.put('/links/not-an-id', headers=auth_headers,
                      json={'title': 'x'}).status_code == 404


def test_player_listing_requires_player_token(client, auth_headers):
    assert client.get('/player/tool-links').status_code == 401
    assert client.get('/player/tool-links', headers=auth_headers).status_code == 403


# ═══════════════════════════════════════════════════════════
#  JSON 批量匯入／匯出
# ═══════════════════════════════════════════════════════════

def test_export_then_import_roundtrip(client, auth_headers):
    client.post('/links/', headers=auth_headers, json={'title': 'Erkul', 'url': 'https://www.erkul.games', 'sort_order': 1})
    body = client.get('/links/export', headers=auth_headers).get_json()['data']
    assert body['version'] == 1
    assert body['links'] == [{'title': 'Erkul', 'url': 'https://www.erkul.games', 'description': '', 'sort_order': 1}]

    # 同網址（大小寫、結尾斜線不同）→ 更新；新網址 → 新增
    resp = client.post('/links/import', headers=auth_headers, json={'data': {'links': [
        {'title': 'Erkul DPS', 'url': 'https://WWW.erkul.games/', 'description': '配裝計算'},
        {'title': 'UEX', 'url': 'uexcorp.space'},
    ]}})
    assert resp.status_code == 200
    assert resp.get_json()['data'] == {'created': 1, 'updated': 1, 'deleted': 0}
    rows = {r['title']: r for r in client.get('/links/', headers=auth_headers).get_json()['data']}
    assert set(rows) == {'Erkul DPS', 'UEX'}
    assert rows['UEX']['url'] == 'https://uexcorp.space'


def test_import_replace_and_bare_array(client, auth_headers):
    client.post('/links/', headers=auth_headers, json={'title': 'Old', 'url': 'https://old.example'})
    resp = client.post('/links/import', headers=auth_headers, json={
        'replace': True, 'data': [{'title': 'New', 'url': 'https://new.example'}]})
    assert resp.get_json()['data'] == {'created': 1, 'updated': 0, 'deleted': 1}
    assert [r['title'] for r in client.get('/links/', headers=auth_headers).get_json()['data']] == ['New']


@pytest.mark.parametrize('data, message', [
    ({'links': []}, '沒有任何連結'),
    ({'foo': 1}, 'JSON 格式不對'),
    ([{'title': 'A', 'url': 'https://a.example'}, {'title': '', 'url': 'https://b.example'}], '第 2 筆：標題不得為空'),
    ([{'title': 'A', 'url': 'javascript:alert(1)'}], '第 1 筆'),
    ([{'title': 'A', 'url': 'https://a.example'}, {'title': 'B', 'url': 'https://a.example/'}], '跟第 1 筆重複'),
    (['not an object'], '要是一個物件'),
])
def test_import_rejects_whole_batch(client, auth_headers, data, message):
    resp = client.post('/links/import', headers=auth_headers, json={'data': data})
    assert resp.status_code == 400 and message in resp.get_json()['message']
    assert client.get('/links/', headers=auth_headers).get_json()['data'] == [], '有錯就整批不寫'


def test_import_requires_data_key(client, auth_headers):
    assert client.post('/links/import', headers=auth_headers, json=[{'title': 'A'}]).status_code == 400
