"""列表點表頭排序：sort_spec 白名單、各後端分頁列表的 sort_by／sort_dir。"""
from src.models.sorting import sort_spec
from src.mongo import get_db


def test_sort_spec():
    fields = {'name': 'name_lower', 'loc': ['system', 'planet']}
    default = [('name_lower', 1)]
    assert sort_spec('', 'asc', fields, default) == [('name_lower', 1), ('_id', 1)]
    assert sort_spec('bogus', 'desc', fields, default) == [('name_lower', 1), ('_id', 1)], '白名單外用預設'
    assert sort_spec('name', 'desc', fields, default) == [('name_lower', -1), ('_id', 1)]
    assert sort_spec('loc', 'asc', fields, default) == [('system', 1), ('planet', 1), ('name_lower', 1), ('_id', 1)]


def test_starmap_sort(client, auth_headers):
    get_db()['starmap_master'].insert_many([
        {'_id': f's{i}', 'name': n, 'name_lower': n.lower(), 'is_current': True, 'is_named': True,
         'amenity_count': c, 'system_name': 'Stanton'} for i, (n, c) in enumerate([('B', 3), ('A', 1), ('C', 2)])])

    def names(qs):
        return [r['name'] for r in client.get(f'/starmap/?{qs}', headers=auth_headers).get_json()['data']]

    assert names('sort_by=name') == ['A', 'B', 'C']
    assert names('sort_by=name&sort_dir=desc') == ['C', 'B', 'A']
    assert names('sort_by=amenity_count&sort_dir=desc') == ['B', 'C', 'A']


def test_mission_and_blueprint_sort(client, auth_headers):
    db = get_db()
    db['mission_master'].insert_many([
        {'_id': 'm1', 'title': 'Alpha', 'title_lower': 'alpha', 'reward_max': 500, 'is_current': True},
        {'_id': 'm2', 'title': 'Beta', 'title_lower': 'beta', 'reward_max': 9000, 'is_current': True}])
    body = client.get('/mission/?sort_by=reward&sort_dir=desc', headers=auth_headers).get_json()
    assert [r['_id'] for r in body['data']] == ['m2', 'm1']
    db['blueprint_master'].insert_many([
        {'_id': 'b1', 'name': 'Zed', 'name_lower': 'zed', 'craft_time_seconds': 10, 'is_current': True},
        {'_id': 'b2', 'name': 'Ace', 'name_lower': 'ace', 'craft_time_seconds': 99, 'is_current': True}])
    body = client.get('/blueprint/master?sort_by=craft_time&sort_dir=desc', headers=auth_headers).get_json()
    assert [r['_id'] for r in body['data']] == ['b2', 'b1']
    body = client.get('/blueprint/master', headers=auth_headers).get_json()
    assert [r['_id'] for r in body['data']] == ['b2', 'b1'], '預設依名稱'


def test_uex_price_sort(client, auth_headers):
    db = get_db()
    db['uex_commodities_prices'].insert_many([
        {'_id': '1:1', 'id_commodity': 1, 'id_terminal': 1, 'commodity_name': 'A', 'terminal_name': 'T1', 'price_buy': 30},
        {'_id': '1:2', 'id_commodity': 1, 'id_terminal': 2, 'commodity_name': 'A', 'terminal_name': 'T2', 'price_buy': 10}])
    body = client.get('/mining/uex-commodity-prices?sort_by=price_buy', headers=auth_headers).get_json()
    assert [r['price_buy'] for r in body['data']] == [10, 30]


def test_fleet_admin_sort_dir():
    from src.models.fleet import Fleet
    assert Fleet._admin_sort('quantity') == [('quantity', -1), ('name_lower', 1), ('_id', 1)]
    assert Fleet._admin_sort('quantity', 'asc')[0] == ('quantity', 1)
    assert Fleet._admin_sort('size', 'desc')[0] == ('size_class', -1)
    assert Fleet._admin_sort('bogus')[0] == ('name_lower', 1)
