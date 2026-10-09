"""UEX 商品價格／交易終端（src/models/uex_commodity_price.py、玩家與後台 API、同步刪除舊列）。"""
from datetime import datetime

from src.models.uex_commodity_price import MAX_SELECTED, UexCommodityPrice, location_path
from src.mongo import get_db


def _seed(db):
    for cid, code, name in ((1, 'AGRI', 'Agricium'), (2, 'MEDS', 'Medical Supplies'), (3, 'WIDO', 'Widow')):
        db['uex_commodities'].insert_one({'_id': str(cid), 'id': cid, 'code': code, 'name': name,
                                          'kind': 'Metal', 'is_illegal': int(cid == 3)})
    terminals = [
        (10, 'TDD - Area18', 'Stanton', 'ArcCorp', None, 'Area18'),
        (11, 'Admin - Port Tressler', 'Stanton', 'microTech', 'Port Tressler', None),
        (12, 'Ruin Station', 'Pyro', 'Pyro VI', 'Ruin Station', None),
    ]
    for tid, name, system, planet, station, city in terminals:
        db['uex_terminals'].insert_one({'_id': str(tid), 'id': tid, 'name': name, 'star_system_name': system,
                                        'planet_name': planet, 'orbit_name': planet,
                                        'space_station_name': station, 'city_name': city})
    prices = [  # (商品, 終端, 買價, 賣價)
        (1, 10, 25.5, 30), (2, 10, 15, 0),
        (1, 11, 26, 0), (2, 11, 0, 20),          # 11 的 MEDS 只收不賣
        (1, 12, 24, 0), (2, 12, 14, 0), (3, 12, 3000, 0),
    ]
    for cid, tid, buy, sell in prices:
        db['uex_commodities_prices'].insert_one({
            '_id': f'{cid}:{tid}', 'id_commodity': cid, 'id_terminal': tid, 'price_buy': buy,
            'price_sell': sell, 'scu_buy': 100, 'date_modified': 1790000000})


def test_location_path_dedupes():
    assert location_path({'star_system_name': 'Stanton', 'planet_name': 'Hurston', 'orbit_name': 'Hurston',
                          'city_name': 'Lorville'}) == ['Stanton', 'Hurston', 'Lorville']


def test_buyable_commodities(app):
    _seed(get_db())
    rows = {r['code']: r for r in UexCommodityPrice.buyable_commodities()}
    assert rows['AGRI']['terminal_count'] == 3
    assert rows['MEDS']['terminal_count'] == 2, '只收不賣（price_buy=0）的終端不算'
    assert rows['WIDO']['is_illegal'] is True


def test_buy_locations_requires_all_selected(app):
    _seed(get_db())
    data = UexCommodityPrice.buy_locations(['1', '2'])
    names = [loc['terminal']['name'] for loc in data['locations']]
    assert names == ['Ruin Station', 'TDD - Area18'], '依地點路徑排序（Pyro 在 Stanton 前）'
    area18 = data['locations'][1]
    assert area18['terminal']['location'] == ['Stanton', 'ArcCorp', 'Area18']
    assert [i['code'] for i in area18['items']] == ['AGRI', 'MEDS']
    assert area18['items'][0]['price_buy'] == 25.5
    assert {c['code']: c['terminal_count'] for c in data['commodities']} == {'AGRI': 3, 'MEDS': 2}


def test_buy_locations_filters_and_limits(app):
    _seed(get_db())
    data = UexCommodityPrice.buy_locations(['1'], star_systems=['Stanton'])
    assert len(data['locations']) == 2
    assert UexCommodityPrice.buy_locations([]) == {'locations': [], 'commodities': []}
    try:
        UexCommodityPrice.buy_locations([str(i) for i in range(MAX_SELECTED + 1)])
        assert False, '應該擋下'
    except ValueError:
        pass


def test_admin_list_and_terminals(app):
    _seed(get_db())
    rows, total = UexCommodityPrice.admin_list(q='agri')
    assert total == 3 and rows[0]['commodity']['code'] == 'AGRI'
    rows, total = UexCommodityPrice.admin_list(star_system='Pyro', side='buy')
    assert total == 3
    rows, total = UexCommodityPrice.admin_list(side='sell')
    assert total == 2
    rows, total = UexCommodityPrice.admin_list(q='tressler', limit=1)
    assert total == 2 and len(rows) == 1
    terms = {t['name']: t for t in UexCommodityPrice.admin_terminals()}
    assert terms['Admin - Port Tressler']['commodity_buy_count'] == 1
    assert terms['Admin - Port Tressler']['commodity_sell_count'] == 1


def test_player_api(client, app):
    _seed(get_db())
    reg = client.post('/player/register', json={'nickname': 'abcd1234', 'star_citizen_id': 'abcd1234',
                                                'password': 'player-pw-123'})
    assert reg.status_code == 201, reg.get_json()
    login = client.post('/player/login', json={'star_citizen_id': 'abcd1234', 'password': 'player-pw-123'})
    headers = {'Authorization': f"Bearer {login.get_json()['token']}"}
    body = client.get('/player/commodities/buyable', headers=headers).get_json()
    assert body['success'] and body['star_systems'] == ['Pyro', 'Stanton']
    res = client.get('/player/commodities/buy-locations?id=1&id=2&star_system=Pyro', headers=headers)
    assert [loc['terminal']['name'] for loc in res.get_json()['data']['locations']] == ['Ruin Station']
    too_many = '&'.join(f'id={i}' for i in range(MAX_SELECTED + 1))
    assert client.get(f'/player/commodities/buy-locations?{too_many}', headers=headers).status_code == 400
    assert client.get('/player/commodities/buyable').status_code == 401


def test_admin_api(client, auth_headers, app):
    _seed(get_db())
    body = client.get('/mining/uex-commodity-prices?side=buy&limit=2', headers=auth_headers).get_json()
    assert body['total'] == 6 and len(body['data']) == 2
    assert client.get('/mining/uex-commodity-prices?limit=x', headers=auth_headers).status_code == 400
    body = client.get('/mining/uex-terminals', headers=auth_headers).get_json()
    assert len(body['data']) == 3


def test_sync_prunes_stale_price_rows(app, monkeypatch):
    import tasks.scdata_sync as sync_mod
    db = get_db()
    db['uex_commodities_prices'].insert_many([
        {'_id': '1:10', 'id_commodity': 1, 'id_terminal': 10, '_sync': {'run_id': 'old'}},
        {'_id': '9:99', 'id_commodity': 9, 'id_terminal': 99, '_sync': {'run_id': 'old'}},
    ])
    monkeypatch.setattr(sync_mod, 'uex_rows', lambda client, resource, params=None: [
        {'id_commodity': 1, 'id_terminal': 10, 'price_buy': 5},
        {'id_commodity': 2, 'id_terminal': 10, 'price_buy': 6},
    ])
    stats = sync_mod._sync_uex_resource(None, 'commodities_prices_all', 'new', datetime.utcnow())
    assert stats['retired'] == 1
    assert sorted(d['_id'] for d in db['uex_commodities_prices'].find()) == ['1:10', '2:10']


def test_sync_keeps_rows_when_upstream_shrinks(app, monkeypatch):
    import tasks.scdata_sync as sync_mod
    db = get_db()
    db['uex_commodities_prices'].insert_many([
        {'_id': f'{i}:1', 'id_commodity': i, 'id_terminal': 1, '_sync': {'run_id': 'old'}} for i in range(10)])
    monkeypatch.setattr(sync_mod, 'uex_rows', lambda client, resource, params=None: [
        {'id_commodity': 0, 'id_terminal': 1, 'price_buy': 5}])
    stats = sync_mod._sync_uex_resource(None, 'commodities_prices_all', 'new', datetime.utcnow())
    assert stats['retired'] == 0 and db['uex_commodities_prices'].count_documents({}) == 10
