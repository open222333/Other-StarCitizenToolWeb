"""玩家定居點：設定（只能選可選居住地）、全部物品轉移到定居點（app/player/view.py）。"""
import pytest

from src import WMS_SCOPE_ID
from src.models.inventory import Inventory
from src.models.player import Player
from src.mongo import get_db


@pytest.fixture
def setup(client):
    db = get_db()
    db['starmap_master'].insert_many([
        {'_id': 'l', 'name': 'Lorville', 'is_current': True, 'is_named': True, 'is_home': True},
        {'_id': 'a', 'name': 'Area18', 'is_current': True, 'is_named': True, 'is_home': True},
        {'_id': 'x', 'name': 'HUR-L1', 'is_current': True, 'is_named': True, 'is_home': False},
    ])
    db['item_master'].insert_many([{'_id': 'i1', 'name': 'Agricium', 'is_current': True},
                                   {'_id': 'i2', 'name': 'Medpen', 'is_current': True}])
    Player.create(player_name='Pilot', star_citizen_id='Pilot', password='pw-123456')
    token = client.post('/player/login', json={'star_citizen_id': 'Pilot', 'password': 'pw-123456'}).get_json()['token']
    return {'Authorization': f'Bearer {token}'}


def _stock():
    return sorted((r['item_id'], r['location'], r.get('container'), r['quantity'])
                  for r in get_db()['inventory'].find({'player': 'Pilot', 'quantity': {'$gt': 0}}))


def test_set_home_and_move_all(client, setup):
    h = setup
    assert client.post('/player/inventory/move-all-home', headers=h).status_code == 400, '沒設定定居點'
    assert client.put('/player/me/home', json={'home_location': 'HUR-L1'}, headers=h).status_code == 400
    res = client.put('/player/me/home', json={'home_location': 'Lorville'}, headers=h)
    assert res.status_code == 200 and res.get_json()['data']['home_location'] == 'Lorville'
    assert client.get('/player/me', headers=h).get_json()['data']['home_location'] == 'Lorville'

    for item, loc, qty, cont in [('i1', 'Area18', 5, None), ('i1', 'Lorville', 2, None),
                                 ('i2', 'HUR-L1', 3, 'Box A'), ('i2', 'Lorville', 1, 'Locker')]:
        Inventory.adjust(WMS_SCOPE_ID, 'player', 'Pilot', location=loc, container=cont,
                         item_id=item, delta=qty, actor='t')
    body = client.post('/player/inventory/move-all-home', headers=h).get_json()
    assert body['data']['moved'] == 3 and body['data']['units'] == 9 and body['data']['failed'] == []
    assert _stock() == [('i1', 'Lorville', None, 7), ('i2', 'Lorville', None, 4)]

    assert client.put('/player/me/home', json={'home_location': None}, headers=h).get_json()['data']['home_location'] is None
    assert client.post('/player/inventory/move-all-home', headers=h).status_code == 400
