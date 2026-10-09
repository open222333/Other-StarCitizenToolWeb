"""UEX 載具遊戲內購買價／租船價（src/models/uex_vehicle_price.py、API）。"""
from src.models import uex_vehicle_price as P
from src.mongo import get_db


def _seed(db):
    db['vehicle_master'].insert_many([
        {'_id': 'uuid-cutlass', 'name': 'Cutlass Black', 'name_lower': 'cutlass black', 'manufacturer_name': 'Drake Interplanetary',
         'is_current': True, 'is_spaceship': True, 'msrp': 110},
        {'_id': 'uuid-aurora', 'name': 'Aurora MR', 'name_lower': 'aurora mr', 'manufacturer_name': 'Roberts Space Industries',
         'is_current': True, 'is_spaceship': True},
        {'_id': 'uuid-nox', 'name': 'Nox', 'name_lower': 'nox', 'is_current': True},
    ])
    db['uex_vehicles'].insert_many([
        {'_id': '1', 'id': 1, 'uuid': 'uuid-cutlass', 'name': 'Cutlass Black'},          # uuid 對得上
        {'_id': '2', 'id': 2, 'uuid': None, 'name': 'Aurora MR',
         'name_full': 'Roberts Space Industries Aurora MR'},                               # 用名稱對
        {'_id': '3', 'id': 3, 'name': 'Unknown Ship'},                                      # 對不到
    ])
    db['uex_terminals'].insert_many([
        {'_id': '10', 'id': 10, 'name': 'New Deal', 'star_system_name': 'Stanton', 'city_name': 'Lorville'},
        {'_id': '11', 'id': 11, 'name': 'Astro Armada', 'star_system_name': 'Stanton', 'city_name': 'Area18'},
        {'_id': '12', 'id': 12, 'name': 'Vantage Rentals', 'star_system_name': 'Stanton',
         'space_station_name': 'Everus Harbor'},
    ])
    db['uex_vehicles_purchases'].insert_many([
        {'_id': '1:10', 'id_vehicle': 1, 'id_terminal': 10, 'price_buy': 2_100_000, 'vehicle_name': 'Cutlass Black'},
        {'_id': '1:11', 'id_vehicle': 1, 'id_terminal': 11, 'price_buy': 1_950_000, 'vehicle_name': 'Cutlass Black'},
        {'_id': '2:11', 'id_vehicle': 2, 'id_terminal': 11, 'price_buy': 0, 'vehicle_name': 'Aurora MR'},
        {'_id': '3:11', 'id_vehicle': 3, 'id_terminal': 11, 'price_buy': 5, 'vehicle_name': 'Unknown Ship'},
    ])
    db['uex_vehicles_rentals'].insert_many([
        {'_id': '1:12', 'id_vehicle': 1, 'id_terminal': 12, 'price_rent': 90_000},
        {'_id': '2:12', 'id_vehicle': 2, 'id_terminal': 12, 'price_rent': 12_000},
    ])


def test_vehicle_links(app):
    _seed(get_db())
    assert P.vehicle_links() == {'1': 'uuid-cutlass', '2': 'uuid-aurora'}


def test_summary_map(app):
    _seed(get_db())
    s = P.summary_map()
    assert s['uuid-cutlass'] == {'buy_min': 1_950_000, 'buy_count': 2, 'rent_min': 90_000, 'rent_count': 1}
    assert s['uuid-aurora'] == {'buy_min': None, 'buy_count': 0, 'rent_min': 12_000, 'rent_count': 1}, \
        '買價 0 不算買得到'
    assert 'uuid-nox' not in s
    assert set(P.summary_map(['uuid-aurora'])) == {'uuid-aurora'}


def test_prices_for(app):
    _seed(get_db())
    data = P.prices_for('uuid-cutlass')
    assert [r['terminal']['name'] for r in data['purchase']] == ['Astro Armada', 'New Deal'], '由便宜到貴'
    assert data['purchase'][0]['terminal']['location'] == ['Stanton', 'Area18']
    assert data['rental'][0]['price'] == 90_000
    assert P.prices_for('uuid-nox') == {'purchase': [], 'rental': []}


def test_admin_list(app):
    _seed(get_db())
    rows, total = P.admin_list('purchase', q='cutlass')
    assert total == 2 and rows[0]['vehicle'] == {'uuid': 'uuid-cutlass', 'name': 'Cutlass Black'}
    rows, total = P.admin_list('purchase', q='unknown')
    assert total == 1 and rows[0]['vehicle'] is None, '對不到主檔的也要列出來，方便檢查'
    rows, total = P.admin_list('rental')
    assert total == 2
    try:
        P.admin_list('nope')
        assert False
    except ValueError:
        pass


def test_api(client, auth_headers, app):
    _seed(get_db())
    body = client.get('/item/vehicles?with_prices=1&limit=10', headers=auth_headers).get_json()
    by_id = {r['_id']: r for r in body['data']}
    assert by_id['uuid-cutlass']['uex_price']['buy_min'] == 1_950_000
    assert by_id['uuid-nox']['uex_price'] is None
    assert 'uex_price' not in client.get('/item/vehicles?limit=10', headers=auth_headers).get_json()['data'][0]
    body = client.get('/item/vehicles/uuid-aurora/prices', headers=auth_headers).get_json()
    assert body['data']['rental'][0]['price'] == 12_000
    body = client.get('/item/uex-vehicle-prices?kind=rental', headers=auth_headers).get_json()
    assert body['total'] == 2
    assert client.get('/item/uex-vehicle-prices?kind=x', headers=auth_headers).status_code == 400


def test_player_fleet_has_prices(client, app):
    _seed(get_db())
    client.post('/player/register', json={'nickname': 'abcd1234', 'star_citizen_id': 'abcd1234',
                                           'password': 'player-pw-123'})
    token = client.post('/player/login', json={'star_citizen_id': 'abcd1234',
                                                'password': 'player-pw-123'}).get_json()['token']
    headers = {'Authorization': f'Bearer {token}'}
    assert client.post('/player/fleet/bulk', json={'vehicle_uuids': ['uuid-cutlass'], 'quantity': 1},
                       headers=headers).status_code in (200, 201)
    rows = client.get('/player/fleet', headers=headers).get_json()['data']
    assert rows[0]['vehicle']['uex_price']['rent_min'] == 90_000
    assert rows[0]['vehicle']['msrp'] == 110


def test_acquire_filter(client, auth_headers, app):
    _seed(get_db())
    assert P.vehicle_ids_with(['buy']) == {'uuid-cutlass'}
    assert P.vehicle_ids_with(['rent']) == {'uuid-cutlass', 'uuid-aurora'}
    assert P.vehicle_ids_with(['nope']) == set()
    ids = lambda qs: sorted(r['_id'] for r in client.get(f'/item/vehicles?{qs}', headers=auth_headers)
                            .get_json()['data'])
    assert ids('acquire=buy') == ['uuid-cutlass']
    assert ids('acquire=rent') == ['uuid-aurora', 'uuid-cutlass']
    assert ids('acquire=buy&acquire=rent') == ['uuid-aurora', 'uuid-cutlass'], '多選取聯集'
    assert ids('acquire=rent&q=aurora') == ['uuid-aurora'], '跟關鍵字一起用'
    assert len(ids('acquire=bogus')) == 3, '不認得的值當作沒帶'
