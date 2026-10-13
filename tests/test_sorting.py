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


def test_mission_sort(client, auth_headers):
    db = get_db()
    db['mission_master'].insert_many([
        {'_id': 'm1', 'title': 'Alpha', 'title_lower': 'alpha', 'reward_max': 500, 'is_current': True},
        {'_id': 'm2', 'title': 'Beta', 'title_lower': 'beta', 'reward_max': 9000, 'is_current': True}])
    body = client.get('/mission/?sort_by=reward&sort_dir=desc', headers=auth_headers).get_json()
    assert [r['_id'] for r in body['data']] == ['m2', 'm1']



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
