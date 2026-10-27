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
