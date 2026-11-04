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
    """沒填 SCU 的取貨點有兩個以上：不猜各點有多少，同一隊一趟去完（第一個點就預留全部量）再送。"""
    item = {'cargo': 'Food', 'pickups': [{'place': 'stA'}, {'place': 'stC'}],
            'dropoffs': [{'place': 'outA', 'scu': 8}, {'place': 'stC', 'scu': 6}]}
    res = haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [item]}])
    plan = res['plans'][0]
    alloc = plan['allocation']
    assert all(a['unknown'] for a in alloc) and len({a['squad'] for a in alloc}) == 1
    assert all({p['id'] for p in a['pickups']} == {'stA', 'stC'} for a in alloc)
    assert sorted((a['dropoff']['id'], a['scu']) for a in alloc) == [('outA', 8), ('stC', 6)]
    legs = plan['squads'][0]['plan']['legs']
    picks = [k for k, l in enumerate(legs) if l['action'] == 'pickup']
    drops = [k for k, l in enumerate(legs) if l['action'] == 'dropoff']
    assert len(picks) == 2 and max(picks) < min(drops), '取貨點都去完才送'
    assert all(legs[k]['scu'] is None and legs[k]['scu_unknown'] for k in picks)
    assert legs[picks[0]]['load_after'] == 14, '第一個取貨點就預留全部量'
    _check_plan(plan)
    # 剩下的量很少也一樣每個點都去
    one = {'cargo': 'Food', 'pickups': [{'place': 'stA'}, {'place': 'stY'}], 'dropoffs': [{'place': 'stC', 'scu': 1}]}
    res = haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [one]}])
    assert {p['id'] for p in res['plans'][0]['allocation'][0]['pickups']} == {'stA', 'stY'}
    # 只剩一個沒填的：數量就是剩下的量，照一般任務
    item['pickups'][1]['scu'] = 10
    res = haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [item]}])
    flows = sorted((a['pickup']['id'], a['dropoff']['id'], a['scu']) for a in res['plans'][0]['allocation'])
    assert sum(f[2] for f in flows if f[0] == 'stC') == 10 and sum(f[2] for f in flows) == 14
    assert not any(a['unknown'] for a in res['plans'][0]['allocation'])
    item['pickups'][1]['scu'] = 14
    with pytest.raises(nav.RouteError, match='沒有貨可拿'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'big'}], contracts=[{'name': 'A', 'items': [item]}])
    # 量不知道就不能拆趟：超過最大貨艙要填數量
    big = {'cargo': 'Food', 'pickups': [{'place': 'stA'}, {'place': 'stC'}], 'dropoffs': [{'place': 'stY', 'scu': 30}]}
    with pytest.raises(nav.RouteError, match='超過最大貨艙'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'small'}], contracts=[{'name': 'A', 'items': [big]}])


def test_unknown_pickups_in_sequence_and_replan(haulers):
    st = lambda place, kind, scu=None, unknown=False: {
        'place': place, 'kind': kind, 'scu': scu, 'cargo': 1, 'contract': 1, 'contract_name': 'C1', 'item': 1,
        'item_name': 'Ore', **({'scu_unknown': True} if unknown else {})}
    legs = haul.evaluate_sequence(start_id='stA', ship_id='big', steps=[
        st('stA', 'pickup', unknown=True), st('stC', 'pickup', unknown=True), st('stY', 'dropoff', 10)])['plan']['legs']
    assert [l['load_after'] for l in legs] == [10, 10, 0]
    with pytest.raises(nav.RouteError, match='還沒去完'):
        haul.evaluate_sequence(start_id='stA', ship_id='big', steps=[
            st('stA', 'pickup', unknown=True), st('stY', 'dropoff', 10), st('stC', 'pickup', unknown=True)])
    # 中途重新規劃：已經去過第一個取貨點（整趟已預留在貨艙），還剩一個取貨點
    legs = haul.replan_squad(start_id='stA', ship_id='big', onboard=['1'],
                             steps=[st('stC', 'pickup', unknown=True), st('stY', 'dropoff', 10)])['plan']['legs']
    assert legs[0]['load_before'] == 10 and [l['action'] for l in legs] == ['pickup', 'dropoff']
    assert legs[-1]['load_after'] == 0


def test_external_cargo_needs_loading_dock(haulers):
    db = get_db()
    db.ship_nav_master.insert_one({'_id': 'hullx', 'name': 'Hull', 'class_name': 'MISC_Hull_C', 'cargo_scu': 500,
                                   **{**FAST, 'external_cargo': True}})
    contracts = [_contract('A', ('Ore', 'stA', 'stC', 10))]
    # 還沒有外部貨運資料：照舊只擋地表，太空站都可以
    nav.clear_cache()
    res = haul.plan_contracts(start_id='stA', squads=[{'ship': 'hullx'}], contracts=contracts)
    assert res['plans'][0]['squads'][0]['trips'] == 1
    # 有資料之後：只有裝卸碼頭（星圖設施或 UEX）的站點能裝卸
    db.starmap_master.update_one({'_id': 'stA'}, {'$set': {'has_loading_dock': True}})
    db.starmap_master.update_one({'_id': 'stY'}, {'$set': {'uex_has_loading_dock': True}})
    nav.clear_cache()
    with pytest.raises(nav.RouteError, match='外部貨運'):
        haul.plan_contracts(start_id='stA', squads=[{'ship': 'hullx'}], contracts=contracts)
    ok = haul.plan_contracts(start_id='stA', squads=[{'ship': 'hullx'}],
                             contracts=[_contract('A', ('Ore', 'stA', 'stY', 10))])
    assert ok['plans'][0]['squads'][0]['trips'] == 1
    # 一般航線也一樣
    with pytest.raises(nav.RouteError, match='外部貨運'):
        nav.plan_route(start_id='stA', waypoints=[], ship_id='hullx', cargo=[{'pickup': 'stA', 'dropoff': 'stC', 'scu': 5}])
    assert {p['id']: p['loading_dock'] for p in nav.places()}['stY'] is True


def test_evaluate_sequence(client, auth_headers, haulers):
    st = lambda place, kind, scu, item='Ore', c=1: {'place': place, 'kind': kind, 'scu': scu, 'contract': c,
                                                    'contract_name': f'C{c}', 'item': 1, 'item_name': item}
    res = haul.evaluate_sequence(start_id='stA', ship_id='big', end_mode='start',
                                 steps=[st('stA', 'pickup', 50), st('stY', 'pickup', 40), st('stC', 'dropoff', 90)])
    legs = res['plan']['legs']
    assert [l['action'] for l in legs] == ['pickup', 'pickup', 'dropoff', 'end'] and legs[2]['load_after'] == 0
    assert legs[0]['contract_name'] == 'C1'
    with pytest.raises(nav.RouteError, match='先取貨'):
        haul.evaluate_sequence(start_id='stA', ship_id='big', steps=[st('stC', 'dropoff', 10), st('stA', 'pickup', 10)])
    with pytest.raises(nav.RouteError, match='先取貨'):   # 不同合約的同名貨物不能互抵
        haul.evaluate_sequence(start_id='stA', ship_id='big',
                               steps=[st('stA', 'pickup', 10, c=1), st('stC', 'dropoff', 10, c=2)])
    with pytest.raises(nav.RouteError, match='超過貨艙'):
        haul.evaluate_sequence(start_id='stA', ship_id='small', steps=[st('stA', 'pickup', 30), st('stC', 'dropoff', 30)])
    resp = client.post('/starmap/nav/sequence', headers=auth_headers, json={
        'start': 'stA', 'ship': 'big', 'steps': [st('stA', 'pickup', 5), st('stY', 'dropoff', 5)]})
    assert resp.status_code == 200 and resp.get_json()['data']['plan']['legs'][-1]['to']['id'] == 'stY'


def test_replan_squad(client, auth_headers, haulers):
    st = lambda place, kind, scu, cargo: {'place': place, 'kind': kind, 'scu': scu, 'cargo': cargo, 'contract': 1,
                                          'contract_name': 'C1', 'item': 1, 'item_name': 'Ore'}
    # 第 1 趟已經在貨艙（只剩送貨到 stC），第 2 趟還沒取；中途插入 stY
    res = haul.replan_squad(start_id='stA', ship_id='big', onboard=['1'], stops=['stY'], end_id='stA',
                            steps=[st('stC', 'dropoff', 30, 1), st('stA', 'pickup', 20, 2), st('stC', 'dropoff', 20, 2)],
                            start_fuel={'mode': 'amount', 'value': 500})
    legs = res['plan']['legs']
    assert legs[0]['load_before'] == 30, '出發時貨艙裡已經有 30'
    assert {l['to']['id'] for l in legs if l['action'] == 'stop'} == {'stY'}
    assert legs[-1]['action'] == 'end' and legs[-1]['to']['id'] == 'stA' and legs[-1]['load_after'] == 0
    assert res['plan']['start_fuel'] == 500
    with pytest.raises(nav.RouteError, match='缺少取貨站'):
        haul.replan_squad(start_id='stA', ship_id='big', steps=[st('stC', 'dropoff', 30, 1)])
    resp = client.post('/starmap/nav/replan', headers=auth_headers, json={
        'start': 'stA', 'ship': 'big', 'stops': ['stC'], 'steps': []})
    assert resp.status_code == 200 and resp.get_json()['data']['plan']['legs'][0]['to']['id'] == 'stC'


def test_evaluate_sequence_with_onboard_and_end(haulers):
    res = haul.evaluate_sequence(start_id='stY', ship_id='big', end_id='stA',
                                 onboard=[{'contract': 1, 'item': 1, 'item_name': 'Ore', 'scu': 30}],
                                 steps=[{'place': 'stC', 'kind': 'dropoff', 'scu': 30, 'contract': 1, 'item': 1,
                                         'item_name': 'Ore', 'cargo': 7}])
    legs = res['plan']['legs']
    assert legs[0]['load_before'] == 30 and legs[0]['cargo'] == 7 and legs[-1]['to']['id'] == 'stA'
