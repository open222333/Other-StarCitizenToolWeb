"""合約分配（src/models/haul.py）：合約拆趟、小隊分配、各隊航線。"""
import pytest

from src.models import haul, nav
from src.mongo import get_db
from tests.test_nav import GM, world_data  # noqa: F401  （共用測試星圖）

FAST = {'qt_speed': 2e8, 'qt_spool': 10, 'qt_fuel_capacity': 1000, 'qt_fuel_per_m': 1000 / (100 * GM),
        'qt_range': 100 * GM, 'mass_total': 100_000, 'external_cargo': False}


@pytest.fixture
def haulers(world_data, monkeypatch):  # noqa: F811
    monkeypatch.setattr(haul, 'SEARCH_SECONDS', 0.2)
    db = get_db()
    db.ship_nav_master.insert_many([
        {'_id': 'big', 'name': 'Big', 'class_name': 'TEST_Big', 'cargo_scu': 100, **FAST},
        {'_id': 'small', 'name': 'Small', 'class_name': 'TEST_Small', 'cargo_scu': 20, **FAST},
        {'_id': 'fighter', 'name': 'Fighter', 'class_name': 'TEST_Fighter', 'cargo_scu': 0, **FAST},
    ])
    nav.clear_cache()


def _contract(name, *items):
    return {'name': name, 'items': [{'cargo': c, 'pickup': p, 'dropoff': d, 'scu': s} for c, p, d, s in items]}


def _check_plan(plan):
    """每個任務都有人載、先取後送、載貨不超過貨艙、送到同一份合約的送貨點。"""
    picked = {}
    for sq in plan['squads']:
        if not sq['plan']:
            continue
        cap = sq['ship']['cargo_scu']
        for leg in sq['plan']['legs']:
            if leg['action'] == 'pickup':
                picked[leg['cargo']] = (sq['index'], leg['contract'], leg['item'])
            elif leg['action'] == 'dropoff':
                assert picked[leg['cargo']] == (sq['index'], leg['contract'], leg['item'])
            assert leg['load_after'] <= cap + 1e-9
    return picked


def test_contracts_split_across_squads(haulers):
    contracts = [
        _contract('A', ('Gold', 'stA', 'stC', 150)),                 # 比最大貨艙大：拆兩趟
        _contract('B', ('Gold', 'stY', 'stA', 10), ('Iron', 'stC', 'stY', 10)),
    ]
    squads = [{'name': '一隊', 'ship': 'big'}, {'name': '二隊', 'ship': 'small', 'start': 'stY'}]
    res = haul.plan_contracts(start_id='stA', squads=squads, contracts=contracts)
    assert res['trips'] == 4 and res['total_scu'] == 170
    assert [p['key'] for p in res['plans']] == ['time', 'total', 'fuel']
    for plan in res['plans']:
        picked = _check_plan(plan)
        assert len(picked) == 4
        # 75 SCU 的兩趟只有大船載得了
        big_parts = [a for a in plan['allocation'] if a['contract'] == 1]
        assert [a['scu'] for a in big_parts] == [75, 75] and all(a['squad'] == 0 for a in big_parts)
        assert plan['squads'][1]['start']['id'] == 'stY'
        times = [s['plan']['totals']['time'] for s in plan['squads'] if s['plan']]
        assert plan['totals']['makespan'] == pytest.approx(max(times))
    # 最快完成：兩隊都有事做
    assert all(s['trips'] for s in res['plans'][0]['squads'])


def test_end_mode_start_returns_each_squad(haulers):
    res = haul.plan_contracts(start_id='stA', end_mode='start',
                              squads=[{'ship': 'big'}, {'ship': 'small', 'start': 'stC'}],
                              contracts=[_contract('A', ('Ore', 'stY', 'stC', 10), ('Ore', 'stY', 'stA', 10))])
    for sq in res['plans'][0]['squads']:
        if sq['plan']:
            assert sq['plan']['legs'][-1]['action'] == 'end'
            assert sq['plan']['legs'][-1]['to']['id'] == sq['start']['id']


def test_contract_errors(haulers):
    ok = [_contract('A', ('Ore', 'stA', 'stC', 10))]
    with pytest.raises(nav.RouteError, match='請選船'):
        haul.plan_contracts(start_id='stA', squads=[{}], contracts=ok)
    with pytest.raises(nav.RouteError, match='沒有貨艙'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'fighter'}], contracts=ok)
    with pytest.raises(nav.RouteError, match='合約最多'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=ok * 11)
    with pytest.raises(nav.RouteError, match='取貨'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}],
                            contracts=[_contract('A', ('Ore', 'nope', 'stC', 10))])


def test_contracts_api(client, auth_headers, haulers):
    resp = client.post('/starmap/nav/contracts', headers=auth_headers, json={
        'start': 'stA', 'squads': [{'ship': 'big'}], 'contracts': [_contract('A', ('Ore', 'stA', 'stY', 30))]})
    assert resp.status_code == 200, resp.get_json()
    plan = resp.get_json()['data']['plans'][0]
    assert [l['action'] for l in plan['squads'][0]['plan']['legs']] == ['pickup', 'dropoff']
    assert plan['squads'][0]['plan']['legs'][0]['contract_name'] == 'A'
    bad = client.post('/starmap/nav/contracts', headers=auth_headers, json={'start': 'stA', 'squads': []})
    assert bad.status_code == 400


def test_commodities_list(client, auth_headers, world_data):  # noqa: F811
    db = get_db()
    db.uex_commodities.insert_many([
        {'_id': '1', 'id': 1, 'code': 'COPP', 'name': 'Copper'},
        {'_id': '2', 'id': 2, 'code': 'AGRI', 'name': 'Agricium'},
        {'_id': '3', 'id': 3, 'code': '', 'name': ''},
    ])
    nav.clear_cache()
    rows = client.get('/starmap/nav/commodities', headers=auth_headers).get_json()['data']
    assert [(r['id'], r['code'], r['name']) for r in rows] == [('2', 'AGRI', 'Agricium'), ('1', 'COPP', 'Copper')]


def test_multi_pickup_and_dropoff_points(haulers):
    item = {'cargo': 'Food', 'pickups': [{'place': 'stA', 'scu': 30}, {'place': 'stC', 'scu': 10}],
            'dropoffs': [{'place': 'stC', 'scu': 25}, {'place': 'stY', 'scu': 15}]}
    res = haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [item]}])
    plan = res['plans'][0]
    flows = sorted((a['pickup']['id'], a['dropoff']['id'], a['scu']) for a in plan['allocation'])
    # 近的先配：stC 的 10 留在 stC，其餘從 stA 出
    assert flows == [('stA', 'stC', 15), ('stA', 'stY', 15), ('stC', 'stC', 10)]
    assert res['total_scu'] == 40
    _check_plan(plan)


def test_single_point_scu_is_optional_and_totals_must_match(haulers):
    item = {'cargo': 'Food', 'pickups': [{'place': 'stA'}],
            'dropoffs': [{'place': 'stC', 'scu': 5}, {'place': 'stY', 'scu': 7}]}
    res = haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [item]}])
    assert res['total_scu'] == 12
    bad = {'cargo': 'Food', 'pickups': [{'place': 'stA', 'scu': 10}], 'dropoffs': [{'place': 'stC', 'scu': 5}]}
    with pytest.raises(nav.RouteError, match='不一樣'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [bad]}])
    both = {'cargo': 'Food', 'pickups': [{'place': 'stA'}], 'dropoffs': [{'place': 'stC'}]}
    with pytest.raises(nav.RouteError, match='送貨的 SCU'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [both]}])


def test_pickup_amounts_can_be_unknown(haulers):
    # 不知道兩個取貨點各有多少：每個取貨點都要去，平均分（各 7），再依距離配
    item = {'cargo': 'Food', 'pickups': [{'place': 'stA'}, {'place': 'stC'}],
            'dropoffs': [{'place': 'outA', 'scu': 8}, {'place': 'stC', 'scu': 6}]}
    res = haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [item]}])
    flows = sorted((a['pickup']['id'], a['dropoff']['id'], a['scu']) for a in res['plans'][0]['allocation'])
    assert flows == [('stA', 'outA', 7), ('stC', 'outA', 1), ('stC', 'stC', 6)]
    # 遠的取貨點也一定要去
    far = {'cargo': 'Food', 'pickups': [{'place': 'stA'}, {'place': 'stY'}], 'dropoffs': [{'place': 'stA', 'scu': 4}]}
    res = haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [far]}])
    assert {a['pickup']['id'] for a in res['plans'][0]['allocation']} == {'stA', 'stY'}
    one = {'cargo': 'Food', 'pickups': [{'place': 'stA'}, {'place': 'stY'}], 'dropoffs': [{'place': 'stC', 'scu': 1}]}
    with pytest.raises(nav.RouteError, match='去不完'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [one]}])
    # 有填的一定拿完，其餘找沒填的
    item['pickups'][1]['scu'] = 10
    res = haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [item]}])
    flows = sorted((a['pickup']['id'], a['dropoff']['id'], a['scu']) for a in res['plans'][0]['allocation'])
    assert sum(f[2] for f in flows if f[0] == 'stC') == 10 and sum(f[2] for f in flows) == 14
    item['pickups'][1]['scu'] = 14
    with pytest.raises(nav.RouteError, match='沒有貨可拿'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [item]}])
