"""航線規劃（src/models/nav.py）與地點座標同步（Starmap.apply_positions）。"""
import pytest

from src.models import nav
from src.models.starmap import Starmap
from src.mongo import get_db
from src.scdata import map_ship_nav

R = 1_000_000          # 行星半徑 1000 km
GM = 1_000_000_000     # 1 Gm


def _loc(_id, name, type_, parent, pos, **extra):
    return {'_id': _id, 'name': name, 'name_lower': name.lower(), 'is_named': True, 'type': type_,
            'parent_uuid': parent, 'is_current': True, 'system_name': 'Stanton', 'pos_system': 'stanton',
            'pos': dict(zip('xyz', pos)), 'qt_valid': True, **extra}


@pytest.fixture
def world_data():
    db = get_db()
    db.starmap_master.delete_many({})
    db.ship_nav_master.delete_many({})
    db.starmap_master.insert_many([
        _loc('sys', 'Stanton', 'Star', None, (0, 0, 0)),
        # 兩顆行星，B 在 A 和 C 中間
        _loc('pa', 'Alpha', 'Planet', 'sys', (0, 0, 0), size=R, obstruction_radius=R * 1.01),
        _loc('pb', 'Beta', 'Planet', 'sys', (10 * GM, 0, 0), size=R, obstruction_radius=R * 1.01),
        _loc('pc', 'Gamma', 'Planet', 'sys', (20 * GM, 0, 0), size=R, obstruction_radius=R * 1.01),
        # Alpha 地表站點（面向 Beta 的反面）、Alpha 軌道站、Gamma 軌道站（面向 Beta）
        _loc('outA', 'Outpost A', 'Outpost', 'pa', (-R, 0, 0)),
        _loc('stA', 'Station A', 'Manmade', 'pa', (2 * R, 0, 0)),
        _loc('stC', 'Station C', 'Manmade', 'pc', (20 * GM - 2 * R, 0, 0)),
        _loc('stY', 'Station Y', 'Manmade', 'sys', (10 * GM, 5 * GM, 0)),
        _loc('hidden', 'Secret', 'Manmade', 'sys', (5 * GM, 5 * GM, 0), player_visible=False),
        _loc('clinicY', 'Station Y Clinic', 'Outpost', 'stY', (10 * GM, 5 * GM, 0)),
    ])
    db.ship_nav_master.insert_many([
        {'_id': 'ship1', 'name': 'Freighter', 'class_name': 'TEST_Freighter', 'qt_speed': 2e8, 'qt_spool': 10,
         'qt_fuel_capacity': 1000, 'qt_range': 100 * GM, 'qt_fuel_per_m': 1000 / (100 * GM),
         'cargo_scu': 100, 'external_cargo': False, 'mass_total': 100_000},
        {'_id': 'hull', 'name': 'Hull', 'class_name': 'MISC_Hull_C', 'qt_speed': 2e8, 'qt_spool': 10,
         'qt_fuel_capacity': 1000, 'qt_range': 100 * GM, 'qt_fuel_per_m': 1000 / (100 * GM),
         'cargo_scu': 1000, 'external_cargo': True, 'mass_total': 100_000},
    ])
    nav.clear_cache()
    yield
    nav.clear_cache()


def test_surface_and_body(world_data):
    w = nav.world()
    assert w.nodes['outA']['surface'] is True
    assert w.nodes['stA']['surface'] is False
    assert w.nodes['stA']['body'] == 'pa'
    assert len(w.oms['pa']) == 6
    assert w.nodes['pa']['group'] == 'pa' and w.nodes['outA']['group'] == 'pa'
    assert w.nodes['stY']['group'] is None


def test_blocked_leg_detours_via_om(world_data):
    res = nav.plan_route(start_id='stA', waypoints=['stC'], cargo=[], ship_id='ship1')
    steps = res['plans'][0]['legs'][0]['steps']
    names = [s['to']['name'] for s in steps]
    assert names[-1] == 'Station C'
    assert any(n.startswith('Beta OM-') for n in names), names   # Beta 擋在中間


def test_unblocked_leg_is_direct(world_data):
    res = nav.plan_route(start_id='stA', waypoints=['stY'], cargo=[], ship_id='ship1')
    steps = res['plans'][0]['legs'][0]['steps']
    assert [s['to']['id'] for s in steps] == ['stY']
    leg = res['plans'][0]['legs'][0]
    assert leg['time'] == pytest.approx(leg['distance'] / 2e8 + 10)
    assert leg['fuel'] == pytest.approx(leg['distance'] * 1000 / (100 * GM))


def test_surface_start_cannot_go_through_own_planet(world_data):
    # Outpost A 在 Alpha 背面，往 Station Y 的直線穿過 Alpha 本身
    res = nav.plan_route(start_id='outA', waypoints=['stY'], cargo=[], ship_id='ship1')
    names = [s['to']['name'] for s in res['plans'][0]['legs'][0]['steps']]
    assert any(n.startswith('Alpha OM-') for n in names), names


def test_auto_order_shorter_than_fixed(world_data):
    kw = dict(start_id='stA', waypoints=['stC', 'stY'], cargo=[], ship_id='ship1')
    fixed = nav.plan_route(auto_order=False, **kw)['plans'][0]
    auto = nav.plan_route(auto_order=True, end_mode='none', **kw)['plans'][0]
    assert [l['to']['id'] for l in fixed['legs']] == ['stC', 'stY']
    assert [l['to']['id'] for l in auto['legs']] == ['stY', 'stC']
    assert auto['totals']['time'] <= fixed['totals']['time']


def test_cargo_pickup_before_dropoff_and_capacity(world_data):
    cargo = [{'pickup': 'stC', 'dropoff': 'stA', 'scu': 60}, {'pickup': 'stY', 'dropoff': 'stC', 'scu': 60}]
    res = nav.plan_route(start_id='stA', waypoints=[], cargo=cargo, ship_id='ship1')
    for plan in res['plans']:
        seen, load = set(), 0
        for leg in plan['legs']:
            if leg['action'] == 'pickup':
                seen.add(leg['cargo'])
            if leg['action'] == 'dropoff':
                assert leg['cargo'] in seen
            load = leg['load_after']
            assert load <= 100
        assert load == 0


def test_cargo_weight_increases_fuel(world_data):
    empty = nav.plan_route(start_id='stA', waypoints=['stY'], cargo=[], ship_id='ship1')['plans'][0]
    full = nav.plan_route(start_id='stA', waypoints=[], ship_id='ship1',
                          cargo=[{'pickup': 'stA', 'dropoff': 'stY', 'scu': 50}])['plans'][0]
    assert full['totals']['fuel'] > empty['totals']['fuel']


def test_over_capacity_and_external_cargo(world_data):
    with pytest.raises(nav.RouteError):
        nav.plan_route(start_id='stA', waypoints=[], ship_id='ship1',
                       cargo=[{'pickup': 'stA', 'dropoff': 'stY', 'scu': 500}])
    with pytest.raises(nav.RouteError, match='外掛貨櫃'):
        nav.plan_route(start_id='stA', waypoints=[], ship_id='hull',
                       cargo=[{'pickup': 'outA', 'dropoff': 'stY', 'scu': 50}])
    # 手動關掉外掛貨櫃就可以
    res = nav.plan_route(start_id='stA', waypoints=[], ship_id='hull', external_cargo=False,
                         cargo=[{'pickup': 'outA', 'dropoff': 'stY', 'scu': 50}])
    assert res['external_cargo'] is False


def test_places_hide_invisible_for_players(world_data):
    ids = {p['id'] for p in nav.places(visible_only=True)}
    assert 'hidden' not in ids and 'stA' in ids
    assert 'hidden' in {p['id'] for p in nav.places(visible_only=False)}
    assert all(p['type'] != 'Asteroid' for p in nav.places())
    assert 'clinicY' not in {p['id'] for p in nav.places()}, '站內設施（上層是太空站）不列'


def test_map_ship_nav():
    doc = {'UUID': 'u1', 'ClassName': 'MISC_Hull_C', 'Name': 'Hull C', 'IsSpaceship': True, 'Cargo': 4608,
           'Mass': 700000, 'MassTotal': 900000,
           'QuantumTravel': {'FuelCapacity': 21900, 'Range': 5e11, 'Speed': 5e8, 'SpoolTime': 9.3}}
    row = map_ship_nav(doc)
    assert row['qt_fuel_per_m'] == pytest.approx(21900 / 5e11)
    assert row['external_cargo'] is True and row['cargo_scu'] == 4608
    assert map_ship_nav({'UUID': 'u2', 'IsSpaceship': True, 'QuantumTravel': {}}) is None


def test_apply_positions_and_jump_links():
    db = get_db()
    db.starmap_master.delete_many({})
    db.starmap_master.insert_many([{'_id': 'a', 'name': 'A'}, {'_id': 'b', 'name': 'B'},
                                   {'_id': 'c', 'name': 'C', 'pos': {'x': 1, 'y': 1, 'z': 1}}])
    payload = {'entities': [
        {'uuid': 'a', 'system': 'stanton', 'qt_valid': True, 'hidden': False, 'x': 1, 'y': 2, 'z': 3},
        {'uuid': 'b', 'system': 'pyro', 'qt_valid': True, 'hidden': True, 'x': 4, 'y': 5, 'z': 6},
        {'uuid': 'b', 'system': 'pyro', 'qt_valid': True, 'hidden': False, 'x': 7, 'y': 8, 'z': 9},
    ], 'connections': [{'entry_uuid': 'a', 'exit_uuid': 'b', 'entry_system': 'stanton',
                        'exit_system': 'pyro', 'fuel_cost': 0.2}]}
    Starmap.apply_positions(payload)
    a, b, c = (db.starmap_master.find_one({'_id': k}) for k in 'abc')
    assert a['pos'] == {'x': 1.0, 'y': 2.0, 'z': 3.0} and a['positions'] is None
    assert b['pos'] == {'x': 7.0, 'y': 8.0, 'z': 9.0} and len(b['positions']) == 2
    assert a['jump_links'][0]['to'] == 'b' and b['jump_links'][0]['to'] == 'a'
    assert c['pos'] is None
    with pytest.raises(ValueError):
        Starmap.apply_positions({'entities': []})


def test_route_api(client, auth_headers, world_data):
    resp = client.post('/starmap/nav/route', headers=auth_headers,
                       json={'start': 'stA', 'waypoints': ['stY'], 'ship': 'ship1'})
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()['data']
    assert [p['key'] for p in data['plans']] == ['fastest', 'fuel', 'simple']
    bad = client.post('/starmap/nav/route', headers=auth_headers, json={'start': 'nope', 'waypoints': ['stY']})
    assert bad.status_code == 400
    assert client.get('/starmap/nav/ships', headers=auth_headers).get_json()['data'][0]['id']
    assert client.get('/starmap/nav/places', headers=auth_headers).status_code == 200


def test_quantum_drive_override_and_size_check(world_data):
    db = get_db()
    db.ship_nav_master.update_one({'_id': 'ship1'}, {'$set': {'qd_uuid': 'qd-default', 'qd_size': 2}})
    qd = lambda _id, name, size, speed, spool, fuel: {
        '_id': _id, 'name': name, 'type': 'QuantumDrive', 'size': size, 'is_current': True,
        'qd_speed': speed, 'qd_spool': spool, 'qd_fuel_per_gm': fuel}
    db.item_master.insert_many([
        qd('qd-default', 'Default', 2, 2e8, 10, 10), qd('qd-fast', 'Fast', 2, 4e8, 4, 20),
        qd('qd-small', 'Small', 1, 1e8, 3, 5),
        {'_id': 'not-qd', 'name': 'Cooler', 'type': 'Cooler', 'size': 2, 'is_current': True},
    ])
    base = nav.plan_route(start_id='stA', waypoints=['stY'], cargo=[], ship_id='ship1')['plans'][0]['legs'][0]
    fast = nav.plan_route(start_id='stA', waypoints=['stY'], cargo=[], ship_id='ship1',
                          qd_id='qd-fast')
    leg = fast['plans'][0]['legs'][0]
    assert fast['ship']['qd_name'] == 'Fast'
    assert leg['time'] == pytest.approx(leg['distance'] / 4e8 + 4)
    assert leg['fuel'] == pytest.approx(base['fuel'] * 2)
    with pytest.raises(nav.RouteError, match='S2'):
        nav.plan_route(start_id='stA', waypoints=['stY'], cargo=[], ship_id='ship1', qd_id='qd-small')
    with pytest.raises(nav.RouteError):
        nav.plan_route(start_id='stA', waypoints=['stY'], cargo=[], ship_id='ship1', qd_id='not-qd')
    assert [q['id'] for q in nav.quantum_drives()] == ['qd-small', 'qd-default', 'qd-fast']


def test_refuel_stops(world_data):
    db = get_db()
    # 小油箱：250，每 Gm 耗 10；stA→stY→stC 各約 112，stC→stA 約 200
    db.ship_nav_master.insert_one({'_id': 'tiny', 'name': 'Tiny', 'qt_speed': 2e8, 'qt_spool': 5,
                                   'qt_fuel_capacity': 250, 'qt_fuel_per_m': 10 / 1e9, 'qt_range': 25 * GM})
    kw = dict(start_id='stA', waypoints=['stY', 'stC'], cargo=[], ship_id='tiny', auto_order=False, end_mode='start')
    plan = nav.plan_route(**kw)['plans'][0]
    # 到 Station C 剩的油不夠回 Station A → 在 Station C（第 2 站）補滿，不管有沒有 Vehicle Services
    assert plan['refuel_stops'] == [2] and 'fuel_short' not in plan['warnings']
    assert plan['legs'][1].get('refuel_here') is True
    assert plan['legs'][2]['fuel_after'] == pytest.approx(250 - plan['legs'][2]['fuel'])
    assert plan['legs'][0]['fuel_after'] == pytest.approx(250 - plan['legs'][0]['fuel'])

    # 單段就超過油箱：補滿也不夠
    db.ship_nav_master.update_one({'_id': 'tiny'}, {'$set': {'qt_fuel_capacity': 150}})
    nav.clear_cache()
    plan = nav.plan_route(**kw)['plans'][0]
    assert 'fuel_short' in plan['warnings'] and plan['legs'][2].get('fuel_short') is True


def test_map_item_quantum_drive_fields():
    from src.scdata import map_item
    row = map_item({'uuid': 'q1', 'name': 'Kama', 'type': 'QuantumDrive', 'quantum_drive': {
        'quantum_fuel_requirement': 0.03864,
        'standard_jump': {'drive_speed': 532468700, 'spool_up_time': 9.3, 'cooldown_time': 15}}})
    assert row['qd_speed'] == 532468700 and row['qd_spool'] == 9.3
    assert row['qd_fuel_per_gm'] == pytest.approx(38.64)
    assert 'qd_speed' not in map_item({'uuid': 'c1', 'name': 'Cooler', 'type': 'Cooler'})
    assert map_item({'uuid': 'c2', 'name': 'Glacier', 'type': 'Cooler', 'class': 'Military'})['item_class'] == 'Military'
def test_route_includes_map_and_positions(world_data):
    res = nav.plan_route(start_id='stA', waypoints=['stC'], cargo=[], ship_id='ship1')
    assert set(res['map']) == {'stanton'}
    names = {b['name'] for b in res['map']['stanton']['bodies']}
    assert {'Alpha', 'Beta', 'Gamma', 'Stanton'} <= names
    leg = res['plans'][0]['legs'][0]
    assert leg['to']['p'] == [20 * GM - 2 * R, 0, 0] and res['plans'][0]['start']['p'] == [2 * R, 0, 0]
    assert all('p' in s['to'] for s in leg['steps'])


def test_ships_dedupe_variants_and_zh_name(world_data, monkeypatch):
    db = get_db()
    base = {'qt_speed': 2e8, 'qt_spool': 5, 'qt_fuel_capacity': 100, 'qt_fuel_per_m': 1e-9}
    db.ship_nav_master.insert_many([
        {'_id': 'apo', 'name': 'RSI Apollo Medivac', 'class_name': 'RSI_Apollo_Medivac', **base},
        {'_id': 'apo1', 'name': 'RSI Apollo Medivac', 'class_name': 'RSI_Apollo_Medivac_Tier_1', **base},
        {'_id': 'apo2', 'name': 'RSI Apollo Medivac', 'class_name': 'RSI_Apollo_Medivac_Tier_2', **base},
    ])
    monkeypatch.setattr(nav, 'vehicle_name_zh', lambda cls='', name='': '阿波羅醫療' if 'Apollo' in cls else None)
    rows = [r for r in nav.ships() if r['name'] == 'RSI Apollo Medivac']
    assert [r['id'] for r in rows] == ['apo'] and rows[0]['name_zh'] == '阿波羅醫療'
    assert nav.ship('apo1')['name_zh'] == '阿波羅醫療'


def test_quantum_drive_class_and_grade_fallback(world_data):
    db = get_db()
    base = {'is_current': True, 'type': 'QuantumDrive', 'size': 1, 'qd_speed': 1e8, 'qd_fuel_per_gm': 10}
    db.item_master.insert_many([
        {'_id': 'q1', 'name': 'Atlas', 'grade': 'C', 'item_class': 'Military', **base},
        # 舊資料沒有 item_class：從 raw 的 description_data 取
        {'_id': 'q2', 'name': 'Bolt', 'grade': 2, **base,
         'raw': {'description_data': [{'name': 'Grade', 'value': 'B'}, {'name': 'Class', 'value': 'Civilian'}]}},
    ])
    rows = {r['id']: r for r in nav.quantum_drives()}
    assert rows['q1']['item_class'] == 'Military' and rows['q1']['grade'] == 'C'
    assert rows['q2']['item_class'] == 'Civilian' and rows['q2']['grade'] == 'B'
