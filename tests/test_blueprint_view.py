"""藍圖登記管理列表 `/blueprint/` GET 的測試（全站搜尋優化計畫第 2 項）。

模型層的篩選/排序/分頁邏輯已經在 tests/test_models.py::TestBlueprint 測過，
這裡只驗證 view 有沒有把 query string 正確轉成模型參數、以及回應格式
（data/total/limit/offset）——避免兩層各自測「同一件事」卻漏了中間的轉譯。
"""
from src.models.blueprint import Blueprint
from src.models.player import Player


def _player_id(name, scid):
    Player.create(player_name=name, star_citizen_id=scid)
    return str(Player.find_by_star_citizen_id(scid)['_id'])


def test_list_requires_auth(client):
    assert client.get('/blueprint/').status_code == 401


def test_list_returns_total_and_paging_fields(client, auth_headers):
    Blueprint.create(name='A')
    Blueprint.create(name='B')
    resp = client.get('/blueprint/', headers=auth_headers)
    body = resp.get_json()
    assert resp.status_code == 200
    assert body['success'] is True
    assert body['total'] >= 2
    assert 'limit' in body and 'offset' in body
    assert len(body['data']) <= body['limit']


def test_list_single_player_id_backward_compat(client, auth_headers):
    """PlayerDetailView.vue 仍然只送單一 player_id（非陣列）查某位玩家。"""
    alice = _player_id('Alice', 'Alice_SC')
    Blueprint.create(name='Mine', player_id=alice)
    Blueprint.create(name='NotMine')
    resp = client.get(f'/blueprint/?player_id={alice}', headers=auth_headers)
    body = resp.get_json()
    assert body['total'] == 1
    assert body['data'][0]['name'] == 'Mine'


def test_list_multiple_player_id_is_multi_select(client, auth_headers):
    alice = _player_id('Alice', 'Alice_SC')
    bob = _player_id('Bob', 'Bob_SC')
    Blueprint.create(name='A-bp', player_id=alice)
    Blueprint.create(name='B-bp', player_id=bob)
    Blueprint.create(name='C-bp')
    resp = client.get(f'/blueprint/?player_id={alice}&player_id={bob}',
                      headers=auth_headers)
    body = resp.get_json()
    assert {r['name'] for r in body['data']} == {'A-bp', 'B-bp'}


def test_list_acquisition_method_multi_select(client, auth_headers):
    Blueprint.create(name='A', acquisition_method='探索')
    Blueprint.create(name='B', acquisition_method='商店')
    Blueprint.create(name='C', acquisition_method='任務')
    resp = client.get('/blueprint/?acquisition_method=探索&acquisition_method=商店',
                      headers=auth_headers)
    body = resp.get_json()
    assert {r['name'] for r in body['data']} == {'A', 'B'}


def test_list_unlock_status_multi_select(client, auth_headers):
    Blueprint.create(name='A', unlock_status='unlocked')
    Blueprint.create(name='B', unlock_status='locked')
    Blueprint.create(name='C', unlock_status='obtained')
    resp = client.get('/blueprint/?unlock_status=unlocked&unlock_status=locked',
                      headers=auth_headers)
    body = resp.get_json()
    assert {r['name'] for r in body['data']} == {'A', 'B'}


def test_list_acquisition_location_keyword(client, auth_headers):
    Blueprint.create(name='A', acquisition_location='Crusader - Orison')
    Blueprint.create(name='B', acquisition_location='Hurston - Lorville')
    resp = client.get('/blueprint/?acquisition_location=orison', headers=auth_headers)
    body = resp.get_json()
    assert body['total'] == 1
    assert body['data'][0]['name'] == 'A'


def test_list_name_keyword_query(client, auth_headers):
    Blueprint.create(name='Laser Cannon S1')
    Blueprint.create(name='Medical Pen')
    resp = client.get('/blueprint/?q=laser', headers=auth_headers)
    body = resp.get_json()
    assert body['total'] == 1
    assert body['data'][0]['name'] == 'Laser Cannon S1'


def test_list_sort_by_and_dir(client, auth_headers):
    Blueprint.create(name='A', acquisition_method='商店')
    Blueprint.create(name='B', acquisition_method='任務')
    resp = client.get('/blueprint/?sort_by=acquisition_method&sort_dir=asc',
                      headers=auth_headers)
    names = [r['name'] for r in resp.get_json()['data']]
    idx_a, idx_b = names.index('A'), names.index('B')
    assert idx_b < idx_a  # 任務 < 商店（字母/筆劃排序由 Mongo 決定，這裡只驗證 B 在 A 前面）


def test_list_pagination(client, auth_headers):
    for i in range(6):
        Blueprint.create(name=f'bp-{i}')
    page1 = client.get('/blueprint/?limit=4&offset=0', headers=auth_headers).get_json()
    page2 = client.get('/blueprint/?limit=4&offset=4', headers=auth_headers).get_json()
    assert len(page1['data']) == 4
    assert len(page2['data']) == 2
    assert page1['total'] == page2['total']
