"""物品資料：列表篩選、選項、UEX 買賣價、說明數值、玩家頁面顯示（app/item/view.py、
src/models/item.py 的 list_all／facets、src/models/uex_item_price.py）。"""
import pytest

from src.models import visibility
from src.models.player import Player
from src.mongo import get_db

ITEMS = [
    {'_id': 'a', 'name': 'Arrowhead Sniper Rifle', 'name_lower': 'arrowhead sniper rifle', 'name_zh': '箭頭狙擊步槍',
     'class_name': 'KLWE_SniperRifle_01', 'type': 'WeaponPersonal', 'sub_type': 'Sniper', 'size': 3, 'grade': 1,
     'manufacturer_code': 'KLWE', 'manufacturer_name': 'Klaus & Werner', 'is_current': True,
     'raw': {'description_data': [{'name': 'Item Type', 'value': 'Sniper Rifle'},
                                  {'name': 'Magazine Size', 'value': '5'}, {'name': 'Empty', 'value': ''}]},
     'description_en': 'A long rifle.'},
    {'_id': 'b', 'name': 'Bracer Cooler', 'name_lower': 'bracer cooler', 'class_name': 'COOL_Bracer',
     'type': 'Cooler', 'size': 1, 'grade': 3, 'manufacturer_code': 'JUST', 'manufacturer_name': 'Juno Starwerk',
     'item_class': 'Military', '_source': 'vehicle-items', 'is_current': True},
    {'_id': 'c', 'name': 'PLACEHOLDER Gun', 'name_lower': 'placeholder gun', 'class_name': 'test_gun',
     'type': 'WeaponPersonal', 'size': 1, 'is_current': True},
    {'_id': 'old', 'name': 'Old Cooler', 'name_lower': 'old cooler', 'type': 'Cooler', 'is_current': False},
]


@pytest.fixture
def items():
    db = get_db()
    db['item_master'].insert_many([dict(i) for i in ITEMS])
    db['uex_items'].insert_many([{'_id': '7', 'id': 7, 'wiki_uuid': 'a'}, {'_id': '8', 'id': 8, 'wiki_uuid': 'b'}])
    db['uex_terminals'].insert_many([
        {'_id': '10', 'id': 10, 'name': 'Center Mass - Area18', 'star_system_name': 'Stanton',
         'planet_name': 'ArcCorp', 'city_name': 'Area18'},
        {'_id': '11', 'id': 11, 'name': 'Port Tressler Shop', 'star_system_name': 'Stanton',
         'planet_name': 'microTech', 'space_station_name': 'Port Tressler'},
    ])
    db['uex_items_prices'].insert_many([
        {'_id': '7:10', 'id_item': 7, 'id_terminal': 10, 'price_buy': 9000, 'price_sell': 0, 'date_modified': 1},
        {'_id': '7:11', 'id_item': 7, 'id_terminal': 11, 'price_buy': 8500, 'price_sell': 4000},
        {'_id': '8:11', 'id_item': 8, 'id_terminal': 11, 'price_buy': 0, 'price_sell': 300},
    ])
    visibility.apply('items')


@pytest.fixture
def player_headers(client):
    Player.create(player_name='Pilot', star_citizen_id='Pilot', password='pw-123456')
    token = client.post('/player/login', json={'star_citizen_id': 'Pilot', 'password': 'pw-123456'}).get_json()['token']
    return {'Authorization': f'Bearer {token}'}


def _ids(client, headers, qs=''):
    body = client.get(f'/item/?{qs}', headers=headers).get_json()
    assert body['success'] is True
    return [r['_id'] for r in body['data']]


def test_list_filters(client, auth_headers, items):
    assert _ids(client, auth_headers) == ['a', 'b', 'c'], '只列現行物品'
    assert _ids(client, auth_headers, 'q=狙擊') == ['a']
    assert _ids(client, auth_headers, 'q=sniper') == ['a']
    assert _ids(client, auth_headers, 'q=cool_') == ['b'], 'class name 也比對'
    assert _ids(client, auth_headers, 'type=Cooler&type=WeaponPersonal&size=3') == ['a']
    assert _ids(client, auth_headers, 'manufacturer_code=JUST') == ['b']
    assert _ids(client, auth_headers, 'grade=3') == ['b']
    assert _ids(client, auth_headers, 'acquire=buy') == ['a']
    assert _ids(client, auth_headers, 'acquire=sell') == ['a', 'b']
    assert _ids(client, auth_headers, 'sort_by=size&sort_dir=desc') == ['a', 'b', 'c']
    assert _ids(client, auth_headers, 'player_visible=0') == ['c'], '佔位名稱自動不顯示'
    assert _ids(client, auth_headers, 'source=vehicle') == ['b'], '飛船組件'
    assert _ids(client, auth_headers, 'source=personal') == ['a', 'c']
    assert _ids(client, auth_headers, 'item_class=Military') == ['b']


def test_list_with_prices_and_facets(client, auth_headers, items):
    rows = {r['_id']: r for r in client.get('/item/?with_prices=1', headers=auth_headers).get_json()['data']}
    assert rows['a']['uex_price'] == {'buy_min': 8500, 'buy_count': 2, 'sell_max': 4000, 'sell_count': 1}
    assert rows['b']['uex_price'] == {'buy_min': None, 'buy_count': 0, 'sell_max': 300, 'sell_count': 1}
    assert rows['c']['uex_price'] is None
    facets = client.get('/item/facets', headers=auth_headers).get_json()['data']
    assert facets['types'] == ['Cooler', 'WeaponPersonal']
    assert facets['manufacturers'] == [{'value': 'JUST', 'label': 'Juno Starwerk（JUST）'},
                                       {'value': 'KLWE', 'label': 'Klaus & Werner（KLWE）'}]
    assert facets['sizes'] == [1, 3] and facets['grades'] == [1, 3]
    assert facets['item_classes'] == ['Military']


def test_player_sees_visible_only(client, player_headers, items):
    assert _ids(client, player_headers) == ['a', 'b']
    assert _ids(client, player_headers, 'player_visible=0') == ['a', 'b'], '玩家不能看不顯示的'


def test_uex_prices_and_stats(client, player_headers, items):
    body = client.get('/item/a/uex-prices', headers=player_headers).get_json()
    assert body['source'] == 'uex'
    assert [r['price'] for r in body['data']['buy']] == [8500, 9000], '由便宜到貴'
    assert body['data']['buy'][1]['terminal']['place'] == 'Area18'
    assert [r['price'] for r in body['data']['sell']] == [4000]
    empty = client.get('/item/c/uex-prices', headers=player_headers).get_json()
    assert empty['data'] == {'buy': [], 'sell': []} and empty['source'] is None
    detail = client.get('/item/a?with_stats=1', headers=player_headers).get_json()['data']
    assert detail['stats'] == [{'name': 'Item Type', 'value': 'Sniper Rifle'}, {'name': 'Magazine Size', 'value': '5'}]
    assert detail['description'] == 'A long rifle.' and 'raw' not in detail


def test_uex_prices_falls_back_to_wiki(client, auth_headers):
    get_db()['item_master'].insert_one({'_id': 'w', 'name': 'W', 'is_current': True, 'raw': {'uex_prices': {
        'purchase': [{'price_buy': 120, 'terminal_name': 'Shop', 'starmap_location': {'name': 'Lorville'}}]}}})
    body = client.get('/item/w/uex-prices', headers=auth_headers).get_json()
    assert body['source'] == 'wiki' and body['data']['buy'][0]['terminal']['place'] == 'Lorville'


def test_visibility_toggle_items(client, auth_headers, items):
    res = client.put('/item/visibility/items/c', json={'player_visible': True}, headers=auth_headers)
    assert res.status_code == 200 and res.get_json()['data']['player_visible'] is True


def test_item_type_translations(client, seed_translations):
    """物品類型／子類型中文：遊戲 key item_Type<代碼>／item_SubType<代碼>；沒有就退回藍圖類型的人工條目。"""
    seed_translations({
        'item_TypeWeaponPersonal': ('Personal Weapon', '個人武器'),
        'item_SubTypeSniper': ('Sniper', '狙擊'),
        'item_TypeFlightController,P': ('Flight Controller', '引擎'),
        'item_SubTypeBombRack,P': ('Bomb Rack', '炸彈架'),
    })
    from src.sc_zh import item_sub_type_zh, item_type_zh
    assert item_type_zh('WeaponPersonal') == '個人武器'
    assert item_type_zh('Cooler') == '散熱器', '退回藍圖類型的人工條目'
    assert item_type_zh('FlightController') == '引擎', '遊戲 key 尾巴多了 ,P'
    assert item_type_zh('SeatAccess') == '座椅出入口', '翻譯包沒有的內部類型用人工條目'
    assert item_sub_type_zh('BombRack') == '炸彈架'
    assert item_sub_type_zh('MidRangeRadar') == '中程雷達'
    assert item_sub_type_zh('Sniper') == '狙擊' and item_sub_type_zh('UNDEFINED') is None
    body = client.get('/item/translations?domain=item_type&text=WeaponPersonal&text=Nope').get_json()
    assert body['data'] == {'WeaponPersonal': '個人武器', 'Nope': ''} or body['data'].get('WeaponPersonal') == '個人武器'
