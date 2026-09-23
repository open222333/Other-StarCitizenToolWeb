"""艦隊（玩家擁有的船／載具）與載具篩選。

涵蓋：
  - VehicleMaster 的尺寸／類型／廠商／角色篩選與 facets（/item/vehicles、/item/vehicles/facets）
  - 玩家自助艦隊：批量登記、數量、改／刪只能動自己的（/player/fleet*）
  - 「查詢 › 船艦搜尋」：誰有哪款船（/player/fleet/holders）
"""
import pytest

from src.models.fleet import MAX_QUANTITY, Fleet
from src.models.item import VehicleMaster, vehicle_type_of
from src.models.player import Player
from src.mongo import get_db


def _vehicle(uuid, name, *, size, mfr_code, mfr_name, role, career='Combat',
             spaceship=True, gravlev=False, current=True):
    return {
        '_id': uuid, 'name': name, 'name_lower': name.lower(), 'class_name': name.replace(' ', '_'),
        'size_class': size, 'manufacturer_code': mfr_code, 'manufacturer_name': mfr_name,
        'role': role, 'career': career, 'is_spaceship': spaceship, 'is_gravlev': gravlev,
        'cargo_capacity_scu': 0, 'crew_max': 1, 'is_current': current,
    }


VEHICLES = [
    _vehicle('v-avenger', 'Avenger Stalker', size=2, mfr_code='AEGS', mfr_name='Aegis Dynamics',
             role='Interceptor'),
    _vehicle('v-hammerhead', 'Hammerhead', size=5, mfr_code='AEGS', mfr_name='Aegis Dynamics',
             role='Heavy Gun Ship'),
    _vehicle('v-cutlass', 'Cutlass Black', size=3, mfr_code='DRAK', mfr_name='Drake Interplanetary',
             role='Medium Freight', career='Transporter'),
    _vehicle('v-cyclone', 'Cyclone', size=1, mfr_code='TMBL', mfr_name='Tumbril',
             role='Passenger', spaceship=False),
    _vehicle('v-nox', 'Nox', size=1, mfr_code='AOPO', mfr_name='Aopoa',
             role='Racing', career='Competition', spaceship=False, gravlev=True),
    _vehicle('v-retired', 'Old Ship', size=2, mfr_code='AEGS', mfr_name='Aegis Dynamics',
             role='Interceptor', current=False),
]


@pytest.fixture
def seed_vehicles():
    get_db()['vehicle_master'].insert_many([dict(v) for v in VEHICLES])


def _register_player(client, scid, nickname, **extra):
    client.post('/player/register', json={
        'nickname': nickname, 'star_citizen_id': scid, 'password': 'pw-123456',
    })
    if extra:
        get_db()['players'].update_one({'star_citizen_id': scid}, {'$set': extra})
    login = client.post('/player/login', json={'star_citizen_id': scid, 'password': 'pw-123456'})
    return {'Authorization': f"Bearer {login.get_json()['token']}"}


@pytest.fixture
def alice(client):
    return _register_player(client, 'AlicePilot', '愛麗絲',
                            discord_name='alice#1', discord_public=True)


@pytest.fixture
def bob(client):
    return _register_player(client, 'BobHauler', '鮑伯', discord_name='bob#2')


def _bulk(client, headers, uuids, **extra):
    return client.post('/player/fleet/bulk', headers=headers,
                       json={'vehicle_uuids': uuids, **extra})


# ═══════════════════════════════════════════════════════
#  VehicleMaster：類型推導與篩選
# ═══════════════════════════════════════════════════════

def test_vehicle_type_of():
    assert vehicle_type_of({'is_spaceship': True, 'is_gravlev': False}) == 'ship'
    assert vehicle_type_of({'is_spaceship': False, 'is_gravlev': False}) == 'ground'
    # 懸浮載具在資料裡 is_spaceship 是 false，要先看 is_gravlev
    assert vehicle_type_of({'is_spaceship': False, 'is_gravlev': True}) == 'gravlev'
    assert vehicle_type_of({}) == 'ground'


def test_list_all_filters_by_type(client, seed_vehicles):
    rows, total = VehicleMaster.list_all(types=['ground'])
    assert [r['_id'] for r in rows] == ['v-cyclone'] and total == 1
    rows, _ = VehicleMaster.list_all(types=['ship'])
    assert {r['_id'] for r in rows} == {'v-avenger', 'v-hammerhead', 'v-cutlass'}
    rows, _ = VehicleMaster.list_all(types=['ground', 'gravlev'])
    assert {r['_id'] for r in rows} == {'v-cyclone', 'v-nox'}
    assert all(r['vehicle_type'] in ('ground', 'gravlev') for r in rows)


def test_list_all_filters_are_anded(client, seed_vehicles):
    rows, total = VehicleMaster.list_all(manufacturer_codes=['AEGS'], size_classes=['5'])
    assert [r['_id'] for r in rows] == ['v-hammerhead'] and total == 1
    rows, _ = VehicleMaster.list_all(manufacturer_codes=['AEGS'], roles=['Medium Freight'])
    assert rows == []


def test_list_all_excludes_retired_and_supports_keyword(client, seed_vehicles):
    rows, total = VehicleMaster.list_all()
    assert 'v-retired' not in {r['_id'] for r in rows} and total == 5
    rows, _ = VehicleMaster.list_all(query='cut')
    assert [r['_id'] for r in rows] == ['v-cutlass']


def test_list_all_ignores_garbage_filter_values(client, seed_vehicles):
    rows, total = VehicleMaster.list_all(types=['nope'], size_classes=['abc'])
    assert total == 5, '不認得的類型／非數字尺寸應該被忽略，而不是讓查詢炸掉或變空'


def test_facets(client, seed_vehicles):
    f = VehicleMaster.facets()
    assert f['size_classes'] == [1, 2, 3, 5]
    assert [t['value'] for t in f['types']] == ['ship', 'ground', 'gravlev']
    assert {m['value'] for m in f['manufacturers']} == {'AEGS', 'DRAK', 'TMBL', 'AOPO'}
    assert 'Competition' in f['careers']
    assert 'Racing' in f['roles'] and 'Interceptor' in f['roles']


def test_ids_matching_filter_none_vs_empty(client, seed_vehicles):
    assert VehicleMaster.ids_matching_filter() is None
    assert VehicleMaster.ids_matching_filter(manufacturer_codes=['NOPE']) == []
    assert set(VehicleMaster.ids_matching_filter(types=['ship'], size_classes=[2, 3])) == {
        'v-avenger', 'v-cutlass'}


def test_item_vehicles_keyword_only_still_carries_type(client, auth_headers, seed_vehicles):
    """只帶 q 時走 search()（前綴比對、total 未知），回傳也要帶 vehicle_type。"""
    body = client.get('/item/vehicles?q=cyc', headers=auth_headers).get_json()
    assert [r['_id'] for r in body['data']] == ['v-cyclone']
    assert body['data'][0]['vehicle_type'] == 'ground'


def test_item_vehicles_endpoint_filters_and_types(client, auth_headers, seed_vehicles):
    body = client.get('/item/vehicles?type=ground&type=gravlev', headers=auth_headers).get_json()
    assert body['success'] and body['total'] == 2
    assert {r['vehicle_type'] for r in body['data']} == {'ground', 'gravlev'}
    body = client.get('/item/vehicles?manufacturer_code=AEGS&sort_by=size_class&sort_dir=desc',
                      headers=auth_headers).get_json()
    assert [r['_id'] for r in body['data']] == ['v-hammerhead', 'v-avenger']


def test_vehicle_facets_open_to_player_token(client, alice, seed_vehicles):
    resp = client.get('/item/vehicles/facets', headers=alice)
    assert resp.status_code == 200
    assert resp.get_json()['data']['size_classes'] == [1, 2, 3, 5]


# ═══════════════════════════════════════════════════════
#  玩家自助艦隊
# ═══════════════════════════════════════════════════════

def test_bulk_register_and_list(client, alice, seed_vehicles):
    body = _bulk(client, alice, ['v-avenger', 'v-cyclone', 'nope', 'v-avenger']).get_json()
    assert body['success'] and body['added'] == 2 and body['not_found'] == 1

    mine = client.get('/player/fleet', headers=alice).get_json()
    assert mine['max_quantity'] == MAX_QUANTITY
    by_uuid = {r['vehicle_uuid']: r for r in mine['data']}
    assert set(by_uuid) == {'v-avenger', 'v-cyclone'}
    assert by_uuid['v-cyclone']['quantity'] == 1
    assert by_uuid['v-cyclone']['vehicle']['vehicle_type'] == 'ground'
    assert by_uuid['v-avenger']['vehicle']['manufacturer_name'] == 'Aegis Dynamics'


def test_bulk_register_skips_already_registered(client, alice, seed_vehicles):
    _bulk(client, alice, ['v-avenger'])
    body = _bulk(client, alice, ['v-avenger', 'v-cutlass']).get_json()
    assert body['added'] == 1 and body['skipped'] == 1
    assert len(client.get('/player/fleet', headers=alice).get_json()['data']) == 2


def test_bulk_register_quantity_is_clamped(client, alice, seed_vehicles):
    _bulk(client, alice, ['v-cyclone'], quantity=500)
    row = client.get('/player/fleet', headers=alice).get_json()['data'][0]
    assert row['quantity'] == MAX_QUANTITY


def test_bulk_register_name_comes_from_master(client, alice, seed_vehicles):
    client.post('/player/fleet/bulk', headers=alice,
                json={'vehicle_uuids': ['v-avenger'], 'name': 'HACKED'})
    row = client.get('/player/fleet', headers=alice).get_json()['data'][0]
    assert row['name'] == 'Avenger Stalker'


def test_bulk_register_rejects_empty_and_oversized(client, alice, seed_vehicles):
    assert _bulk(client, alice, []).status_code == 400
    assert _bulk(client, alice, [f'x{i}' for i in range(201)]).status_code == 400


def test_bulk_register_requires_player_token(client, auth_headers, seed_vehicles):
    assert _bulk(client, auth_headers, ['v-avenger']).status_code == 403
    assert client.post('/player/fleet/bulk', json={'vehicle_uuids': ['v-avenger']}).status_code == 401


def test_update_quantity_and_delete_own(client, alice, seed_vehicles):
    _bulk(client, alice, ['v-cutlass'])
    row = client.get('/player/fleet', headers=alice).get_json()['data'][0]

    resp = client.put(f"/player/fleet/{row['_id']}", headers=alice, json={'quantity': 3})
    assert resp.status_code == 200
    assert client.get('/player/fleet', headers=alice).get_json()['data'][0]['quantity'] == 3

    # 0 或負數夾到 1，不會變成「有 0 艘」的怪登記
    client.put(f"/player/fleet/{row['_id']}", headers=alice, json={'quantity': 0})
    assert client.get('/player/fleet', headers=alice).get_json()['data'][0]['quantity'] == 1

    assert client.delete(f"/player/fleet/{row['_id']}", headers=alice).status_code == 200
    assert client.get('/player/fleet', headers=alice).get_json()['data'] == []
    # 刪掉之後可以重新登記
    assert _bulk(client, alice, ['v-cutlass']).get_json()['added'] == 1


def test_cannot_touch_someone_elses_fleet(client, alice, bob, seed_vehicles):
    _bulk(client, alice, ['v-cutlass'])
    row = client.get('/player/fleet', headers=alice).get_json()['data'][0]

    assert client.put(f"/player/fleet/{row['_id']}", headers=bob,
                      json={'quantity': 9}).status_code == 404
    assert client.delete(f"/player/fleet/{row['_id']}", headers=bob).status_code == 404
    assert client.get('/player/fleet', headers=alice).get_json()['data'][0]['quantity'] == 1


def test_update_with_bad_id_or_no_fields(client, alice, seed_vehicles):
    assert client.put('/player/fleet/not-an-id', headers=alice,
                      json={'quantity': 2}).status_code == 404
    assert client.put('/player/fleet/not-an-id', headers=alice, json={}).status_code == 400


# ═══════════════════════════════════════════════════════
#  查詢 › 船艦搜尋
# ═══════════════════════════════════════════════════════

@pytest.fixture
def seeded_fleets(client, alice, bob, seed_vehicles):
    _bulk(client, alice, ['v-avenger', 'v-cyclone'], quantity=2)
    _bulk(client, bob, ['v-avenger', 'v-cutlass'])
    return alice


def _holders(client, headers, **params):
    from urllib.parse import urlencode
    resp = client.get(f'/player/fleet/holders?{urlencode(params, doseq=True)}', headers=headers)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return resp.get_json()['data']


def test_holders_without_filters_lists_everything(client, seeded_fleets):
    groups = _holders(client, seeded_fleets)
    assert [g['vehicle_uuid'] for g in groups][0] == 'v-avenger', '持有人數多的排前面'
    avenger = groups[0]
    assert avenger['holder_count'] == 2 and avenger['total_quantity'] == 3
    assert avenger['vehicle']['size_class'] == 2


def test_holders_filter_by_type_and_manufacturer(client, seeded_fleets):
    assert [g['vehicle_uuid'] for g in _holders(client, seeded_fleets, type='ground')] == ['v-cyclone']
    assert [g['vehicle_uuid'] for g in _holders(client, seeded_fleets, manufacturer_code='DRAK')] == ['v-cutlass']
    assert _holders(client, seeded_fleets, manufacturer_code='NOPE') == []


def test_holders_filter_by_player(client, seeded_fleets):
    groups = _holders(client, seeded_fleets, player_id='BobHauler')
    assert {g['vehicle_uuid'] for g in groups} == {'v-avenger', 'v-cutlass'}
    assert all(h['star_citizen_id'] == 'BobHauler' for g in groups for h in g['holders'])


def test_holders_filters_are_anded(client, seeded_fleets):
    groups = _holders(client, seeded_fleets, size_class='3', player_id='AlicePilot')
    assert groups == [], 'Alice 沒有尺寸 3 的船'


def test_holders_redacts_private_discord_and_hides_notes(client, seeded_fleets):
    Fleet._col().update_many({}, {'$set': {'notes': 'secret'}})
    avenger = _holders(client, seeded_fleets, q='avenger')[0]
    by_scid = {h['star_citizen_id']: h for h in avenger['holders']}
    assert by_scid['AlicePilot']['discord_name'] == 'alice#1'   # 勾了公開
    assert by_scid['BobHauler']['discord_name'] == ''           # 沒勾公開
    assert 'notes' not in avenger and all('notes' not in h for h in avenger['holders'])
    assert all('discord_public' not in h for h in avenger['holders'])


def test_holders_excludes_deleted_players(client, seeded_fleets):
    bob_doc = Player.find_by_star_citizen_id('BobHauler')
    Player.soft_delete(bob_doc['_id'])
    groups = _holders(client, seeded_fleets)
    assert 'v-cutlass' not in {g['vehicle_uuid'] for g in groups}


def test_holders_rejects_admin_token(client, auth_headers, seed_vehicles):
    assert client.get('/player/fleet/holders', headers=auth_headers).status_code == 403


def test_holders_filter_by_exact_vehicle_id(client, seeded_fleets):
    groups = _holders(client, seeded_fleets, vehicle_id='v-cutlass')
    assert [g['vehicle_uuid'] for g in groups] == ['v-cutlass']
    # 跟其他條件 AND：Cutlass 不是地面載具
    assert _holders(client, seeded_fleets, vehicle_id='v-cutlass', type='ground') == []
