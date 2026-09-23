"""玩家搜尋（GET /player/search）——「查詢」頁「玩家id」「玩家暱稱」兩個
自動完成欄位在用，見 src/models/player.py 的 Player.search_basic()。
"""
import pytest

from src.models.player import Player


@pytest.fixture
def player_headers(client):
    client.post('/player/register', json={
        'nickname': 'Searcher', 'star_citizen_id': 'SearcherSC', 'password': 'pw-123456',
    })
    login = client.post('/player/login', json={
        'star_citizen_id': 'SearcherSC', 'password': 'pw-123456',
    })
    return {'Authorization': f"Bearer {login.get_json()['token']}"}


@pytest.fixture
def seed_players(player_headers):
    """player_headers 已經建了 SearcherSC 自己，這裡再補兩個給搜尋用。"""
    Player.create(player_name='Tom Li', star_citizen_id='TomLi', nickname='湯姆',
                 password='pw-123456')
    Player.create(player_name='Alice A', star_citizen_id='AlicePilot', nickname='愛麗絲',
                 password='pw-123456')


# ══════════════════════════════════════════════════════
#  模型層：Player.search_basic
# ═══════════════════════════════════════════════════════

def test_search_basic_matches_nickname(client, seed_players):
    rows = Player.search_basic('愛麗絲')
    assert [r['star_citizen_id'] for r in rows] == ['AlicePilot']


def test_search_basic_matches_scid(client, seed_players):
    rows = Player.search_basic('TomLi')
    assert {r['star_citizen_id'] for r in rows} == {'TomLi'}


def test_search_basic_matches_player_name(client, seed_players):
    rows = Player.search_basic('Alice A')
    assert [r['star_citizen_id'] for r in rows] == ['AlicePilot']


def test_search_basic_is_case_insensitive(client, seed_players):
    assert [r['star_citizen_id'] for r in Player.search_basic('tomli')] == ['TomLi']


def test_search_basic_returns_display_fields_only(client, seed_players):
    """不帶 Discord——這支對任何登入玩家開放，見 model 方法的說明。"""
    row = Player.search_basic('TomLi')[0]
    assert set(row.keys()) == {'star_citizen_id', 'nickname', 'player_name'}


def test_search_basic_blank_query_lists_everyone(client, seed_players):
    """空字串＝列出全部現役玩家（「查詢」頁玩家欄位一 focus 就要看到完整名單，
    打字時在前端逐字篩選），依暱稱排序。"""
    rows = Player.search_basic('')
    assert {r['star_citizen_id'] for r in rows} == {'SearcherSC', 'TomLi', 'AlicePilot'}
    assert [r['nickname'] for r in rows] == sorted(r['nickname'] for r in rows)
    assert Player.search_basic('   ') == rows


def test_search_basic_blank_query_excludes_deleted(client, seed_players):
    tom = Player.find_by_star_citizen_id('TomLi')
    Player.soft_delete(tom['_id'])
    assert 'TomLi' not in {r['star_citizen_id'] for r in Player.search_basic('')}


def test_search_basic_excludes_deleted(client, seed_players):
    tom = Player.find_by_star_citizen_id('TomLi')
    Player.soft_delete(tom['_id'])
    assert Player.search_basic('TomLi') == []


# ═══════════════════════════════════════════════════════
#  HTTP 層：GET /player/search
# ══════════════════════════════════════════════════════

def test_endpoint_requires_auth(client):
    assert client.get('/player/search?q=Tom').status_code == 401


def test_endpoint_rejects_admin_token(client, auth_headers, seed_players):
    """掛 @player_required，不是這個檔案其他端點慣用的 admin_api()——
    後台 token 不是玩家 token，該被擋。"""
    resp = client.get('/player/search?q=Tom', headers=auth_headers)
    assert resp.status_code == 403


def test_endpoint_allows_player_token(client, player_headers, seed_players):
    resp = client.get('/player/search?q=愛麗絲', headers=player_headers)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()['data']
    assert [r['star_citizen_id'] for r in data] == ['AlicePilot']
    assert data[0]['nickname'] == '愛麗絲'


def test_endpoint_blank_q_lists_full_roster(client, player_headers, seed_players):
    resp = client.get('/player/search', headers=player_headers)
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert {r['star_citizen_id'] for r in data} == {'SearcherSC', 'TomLi', 'AlicePilot'}
    # 列全部時也一樣不帶 Discord
    assert all(set(r.keys()) == {'star_citizen_id', 'nickname', 'player_name'} for r in data)


def test_endpoint_query_limit_still_capped_at_50(client, player_headers, seed_players):
    for i in range(60):
        Player.create(player_name=f'Bulk {i}', star_citizen_id=f'BulkSC{i}',
                      nickname=f'bulk{i:02d}', password='pw-123456')
    resp = client.get('/player/search?q=bulk&limit=500', headers=player_headers)
    assert len(resp.get_json()['data']) == 50
    resp = client.get('/player/search', headers=player_headers)
    assert len(resp.get_json()['data']) == 63, '不帶 q 時要回完整名單，不受 50 筆上限'


def test_endpoint_soft_deleted_player_cannot_call_it(client, player_headers, seed_players):
    """比照 player_required 的說明：帳號被軟刪後 token 到期前也不該能用。"""
    me = Player.find_by_star_citizen_id('SearcherSC')
    Player.soft_delete(me['_id'])

    resp = client.get('/player/search?q=Tom', headers=player_headers)
    assert resp.status_code == 403
