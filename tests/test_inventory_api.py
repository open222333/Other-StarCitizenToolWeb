"""庫存 / 主檔 API 端點測試（app/inventory、app/item）。

重點在 HTTP 層：認證、權限、參數驗證、回應格式。
庫存邏輯本身在 test_inventory.py 測。
"""
import pytest

from src.mongo import get_db

ITEM_BIG = {'_id': 'item-big', 'name': 'Agricium', 'name_lower': 'agricium',
            'type': 'Commodity', 'volume_uscu': 1_000_000, 'is_current': True,
            'size': 1, 'manufacturer_code': 'ORIG'}
ITEM_SMALL = {'_id': 'item-small', 'name': 'Bracer Cooler', 'name_lower': 'bracer cooler',
              'type': 'Cooler', 'volume_uscu': 24_000, 'is_current': True, 'size': 1}
SHIP = {'_id': 'ship-1', 'name': 'Freelancer MAX', 'name_lower': 'freelancer max',
        'cargo_capacity_scu': 120, 'vehicle_inventory_uscu': 710_000, 'is_current': True}


@pytest.fixture
def seed_master():
    get_db()['item_master'].insert_many([dict(ITEM_BIG), dict(ITEM_SMALL)])
    get_db()['vehicle_master'].insert_one(dict(SHIP))


@pytest.fixture
def viewer_token(client, seed_admin):
    """建一個 viewer 帳號並取得 token，用來驗證寫入權限被擋。"""
    from src.models.user import User
    from src.models.user_template import UserTemplate
    tid = UserTemplate.ensure_defaults()
    User.create('viewer1', 'Viewer1234!', role='viewer', template_id=tid)
    resp = client.post('/auth/login', json={'username': 'viewer1',
                                            'password': 'Viewer1234!'})
    return resp.get_json()['token']


# ─────────────────────────────────────────────────────── 認證

def test_endpoints_require_jwt(client):
    for method, path in [('get', '/inventory/'), ('get', '/item/'),
                         ('post', '/inventory/add'), ('get', '/inventory/capacity')]:
        resp = getattr(client, method)(path, json={})
        assert resp.status_code == 401, f'{method.upper()} {path} 應該要求 JWT'


# ─────────────────────────────────────────────────────── 權限

def test_write_requires_operator_role(client, viewer_token, seed_master):
    resp = client.post('/inventory/add',
                       headers={'Authorization': f'Bearer {viewer_token}'},
                       json={'item': 'item-big', 'quantity': 5, 'location': 'Area18'})
    assert resp.status_code == 403
    assert get_db()['inventory'].count_documents({}) == 0, '被拒的請求不該寫入'


def test_read_allowed_for_viewer(client, viewer_token):
    resp = client.get('/inventory/',
                      headers={'Authorization': f'Bearer {viewer_token}'})
    assert resp.status_code == 200
    assert resp.get_json()['success'] is True


# ─────────────────────────────────────────────────────── 入出庫

def test_add_then_list(client, auth_headers, seed_master):
    resp = client.post('/inventory/add', headers=auth_headers,
                       json={'item': 'item-big', 'quantity': 10,
                             'location': 'Area18', 'note': '首批'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['quantity'] == 10
    assert data['item_name'] == 'Agricium'
    assert data['total_scu'] == 10.0

    resp = client.get('/inventory/?location=Area18', headers=auth_headers)
    body = resp.get_json()
    assert body['total'] == 1
    assert body['data'][0]['item_name'] == 'Agricium'
    assert body['summary']['total_scu'] == 10.0


def test_add_accepts_item_name(client, auth_headers, seed_master):
    """item 欄位可以給名稱，不一定要 uuid。"""
    resp = client.post('/inventory/add', headers=auth_headers,
                       json={'item': 'agricium', 'quantity': 3, 'location': 'Area18'})
    assert resp.status_code == 200
    assert resp.get_json()['data']['item_id'] == 'item-big'


def test_add_unknown_item_400(client, auth_headers, seed_master):
    resp = client.post('/inventory/add', headers=auth_headers,
                       json={'item': '不存在的物品', 'quantity': 1, 'location': 'Area18'})
    assert resp.status_code == 400
    assert '找不到物品' in resp.get_json()['message']


@pytest.mark.parametrize('payload,reason', [
    ({'item': 'item-big', 'quantity': 0, 'location': 'A'}, '數量 0'),
    ({'item': 'item-big', 'quantity': -5, 'location': 'A'}, '負數'),
    ({'item': 'item-big', 'quantity': 'abc', 'location': 'A'}, '非整數'),
    ({'item': 'item-big', 'quantity': 5}, '缺 location'),
    ({'quantity': 5, 'location': 'A'}, '缺 item'),
])
def test_add_validation(client, auth_headers, seed_master, payload, reason):
    resp = client.post('/inventory/add', headers=auth_headers, json=payload)
    assert resp.status_code == 400, reason


def test_remove_insufficient_400(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 5, 'location': 'Area18'})

    resp = client.post('/inventory/remove', headers=auth_headers,
                       json={'item': 'item-big', 'quantity': 99, 'location': 'Area18'})
    assert resp.status_code == 400
    assert '庫存不足' in resp.get_json()['message']

    doc = get_db()['inventory'].find_one({'item_id': 'item-big'})
    assert doc['quantity'] == 5, '失敗的出庫不該改動庫存'


def test_remove_to_zero_flags_emptied(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 4, 'location': 'Area18'})
    resp = client.post('/inventory/remove', headers=auth_headers,
                       json={'item': 'item-big', 'quantity': 4, 'location': 'Area18'})
    assert resp.get_json()['data']['emptied'] is True


def test_move(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 20, 'location': 'Area18'})

    resp = client.post('/inventory/move', headers=auth_headers,
                       json={'item': 'item-big', 'quantity': 8,
                             'source': 'Area18', 'destination': 'Lorville',
                             'destination_container': 'Hangar 3'})
    assert resp.status_code == 200
    data = resp.get_json()['data']
    assert data['source']['remaining'] == 12
    assert data['destination']['quantity'] == 8
    assert data['destination']['container'] == 'Hangar 3'


def test_writes_are_audited(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 6, 'location': 'Area18'})

    # inventory_log（庫存稽核）
    resp = client.get('/inventory/history', headers=auth_headers)
    rows = resp.get_json()['data']
    assert len(rows) == 1
    assert rows[0]['action'] == 'add'
    assert rows[0]['item_name'] == 'Agricium'
    assert rows[0]['actor_id'].startswith('web:')

    # logs（系統操作紀錄）也要有一筆
    assert get_db()['logs'].count_documents({'action': 'inventory_add'}) == 1


# ─────────────────────────────────────────────────────── 個人庫

def test_player_scope_requires_player_param(client, auth_headers):
    resp = client.get('/inventory/?owner_type=player', headers=auth_headers)
    assert resp.status_code == 400
    assert 'player' in resp.get_json()['message']


def test_guild_and_player_isolated(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 10, 'location': 'Area18'})
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 7, 'location': 'Area18',
                      'owner_type': 'player', 'player': 'TomLi'})

    guild = client.get('/inventory/', headers=auth_headers).get_json()
    player = client.get('/inventory/?owner_type=player&player=TomLi',
                        headers=auth_headers).get_json()
    assert guild['summary']['units'] == 10
    assert player['summary']['units'] == 7


# ─────────────────────────────────────────────────────── capacity

def test_capacity_with_ship_fits(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 50, 'location': 'Area18'})

    resp = client.get('/inventory/capacity?location=Area18&ship=ship-1',
                      headers=auth_headers)
    ship = resp.get_json()['ship']
    assert ship['name'] == 'Freelancer MAX'
    assert ship['needed_scu'] == 50.0
    assert ship['fits'] is True
    assert ship['remaining_scu'] == 70.0


def test_capacity_with_ship_too_small(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 300, 'location': 'Area18'})

    ship = client.get('/inventory/capacity?ship=Freelancer MAX',
                      headers=auth_headers).get_json()['ship']
    assert ship['fits'] is False
    assert ship['trips'] == 3      # 300 SCU / 120 SCU 貨艙
    assert ship['remaining_scu'] == 0


def test_capacity_unknown_ship_reports_error_not_500(client, auth_headers):
    payload = client.get('/inventory/capacity?ship=不存在的船',
                         headers=auth_headers).get_json()
    assert payload['success'] is True
    assert 'error' in payload['ship']


# ─────────────────────────────────────────────────────── where

def test_where_spans_owners(client, auth_headers, seed_master):
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 10, 'location': 'Area18'})
    client.post('/inventory/add', headers=auth_headers,
                json={'item': 'item-big', 'quantity': 5, 'location': 'Lorville',
                      'owner_type': 'player', 'player': 'TomLi'})

    body = client.get('/inventory/where/item-big', headers=auth_headers).get_json()
    assert body['summary']['total_quantity'] == 15
    assert body['summary']['total_scu'] == 15.0
    assert {row['owner_type'] for row in body['data']} == {'guild', 'player'}


def test_where_unknown_item_404(client, auth_headers):
    assert client.get('/inventory/where/nope', headers=auth_headers).status_code == 404


# ─────────────────────────────────────────────────────── 主檔 API

def test_item_search(client, auth_headers, seed_master):
    body = client.get('/item/search?q=agri', headers=auth_headers).get_json()
    assert len(body['data']) == 1
    assert body['data'][0]['name'] == 'Agricium'
    assert body['data'][0]['volume_scu'] == 1.0


def test_item_search_requires_q(client, auth_headers):
    assert client.get('/item/search', headers=auth_headers).status_code == 400


def test_item_search_escapes_regex(client, auth_headers, seed_master):
    """使用者輸入的 regex 特殊字元不該被當語法（也不該 500）。"""
    resp = client.get('/item/search?q=.*', headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()['data'] == []


def test_item_detail_hides_raw_by_default(client, auth_headers):
    get_db()['item_master'].insert_one({**ITEM_BIG, 'raw': {'big': 'payload'}})

    body = client.get('/item/item-big', headers=auth_headers).get_json()
    assert 'raw' not in body['data']

    body = client.get('/item/item-big?with_raw=1', headers=auth_headers).get_json()
    assert body['data']['raw'] == {'big': 'payload'}


def test_item_prices_falls_back_to_wiki(client, auth_headers):
    """沒有 UEX 資料時要退回 Wiki API 內嵌價格。"""
    get_db()['item_master'].insert_one({**ITEM_BIG, 'raw': {'uex_prices': {'purchase': [
        {'price_buy': 1508220, 'terminal_name': 'New Deal - Lorville',
         'starmap_location': {'name': 'Lorville'}, 'game_version': '4.9.0-LIVE'},
    ]}}})

    body = client.get('/item/item-big/prices', headers=auth_headers).get_json()
    assert body['source'] == 'wiki'
    assert body['data'][0]['price_buy'] == 1508220
    assert body['data'][0]['location'] == 'Lorville'


def test_item_prices_empty_is_not_error(client, auth_headers, seed_master):
    body = client.get('/item/item-small/prices', headers=auth_headers).get_json()
    assert body['success'] is True
    assert body['data'] == []


def test_sync_status(client, auth_headers, seed_master):
    from datetime import datetime
    get_db()['sync_runs'].insert_one({
        '_id': 'run-1', 'started_at': datetime.utcnow(),
        'finished_at': datetime.utcnow(), 'ok': True, 'errors': [],
        'stats': [{'resource': 'items'}],
    })

    body = client.get('/item/sync-status', headers=auth_headers).get_json()
    assert body['data']['counts']['items'] == 2
    assert body['data']['counts']['vehicles'] == 1
    assert body['data']['latest_run']['ok'] is True
    assert 'stats' not in body['data']['latest_run'], 'stats 太大，列表不該回傳'


def test_paging_limit_is_capped(client, auth_headers, seed_master):
    body = client.get('/item/?limit=9999', headers=auth_headers).get_json()
    assert body['limit'] == 200, 'limit 應被夾到 MAX_LIMIT'


def test_paging_handles_garbage(client, auth_headers, seed_master):
    body = client.get('/item/?limit=abc&offset=xyz', headers=auth_headers).get_json()
    assert body['limit'] == 50 and body['offset'] == 0
