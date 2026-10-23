"""精煉站產量加成（src/models/uex_refinery_yield.py、GET /mining/refinery-yields）。"""

from src.models import uex_refinery_yield
from src.mongo import get_db


def _seed():
    get_db()['uex_refinery_yields'].insert_many([
        {'_id': '1:10', 'id_commodity': 1, 'id_terminal': 10, 'commodity_name': 'Quantanium (Raw)',
         'terminal_name': 'ARC-L1 Refinery', 'space_station_name': 'ARC-L1', 'star_system_name': 'Stanton', 'value': 3},
        {'_id': '1:11', 'id_commodity': 1, 'id_terminal': 11, 'commodity_name': 'Quantanium (Raw)',
         'terminal_name': 'CRU-L1 Refinery', 'space_station_name': 'CRU-L1', 'star_system_name': 'Stanton', 'value': -2},
        {'_id': '2:10', 'id_commodity': 2, 'id_terminal': 10, 'commodity_name': 'Gold',
         'terminal_name': 'ARC-L1 Refinery', 'value': '5'},
        {'_id': 'bad', 'commodity_name': 'Iron', 'value': None},
    ])


def test_list_all_normalizes_and_sorts(app):
    _seed()
    rows = uex_refinery_yield.list_all()
    quan = [r for r in rows if r['base'] == 'quantanium']
    assert [(r['terminal'], r['value']) for r in quan] == [('ARC-L1 Refinery', 3.0), ('CRU-L1 Refinery', -2.0)]
    assert quan[0]['place'] == 'ARC-L1' and quan[0]['system'] == 'Stanton'
    assert any(r['base'] == 'gold' and r['value'] == 5.0 for r in rows), '字串數字也要能讀'
    assert not any(r['commodity'] == 'Iron' for r in rows), '沒有加成數值的不列'


def test_refinery_yields_api(client, auth_headers):
    _seed()
    body = client.get('/mining/refinery-yields', headers=auth_headers).get_json()
    assert body['success'] and len(body['data']) == 3


def test_method_stats_latest_version_only(app):
    """精煉紀錄依礦物×方式彙整：產出率＝產出÷原礦、每 SCU 成本與時間，只取最新遊戲版本。"""
    from src.models import uex_refinery_method as M
    db = get_db()
    db['uex_refinery_methods'].insert_many([
        {'_id': '1', 'id': 1, 'name': 'Dinyx Solventation', 'rating_yield': 3},
        {'_id': '2', 'id': 2, 'name': 'Ferron Exchange'},
    ])
    db['uex_refinery_audits'].insert_many([
        {'_id': 'a', 'id': 'a', 'commodity_name': 'Quantanium (Raw)', 'id_method': 1, 'quantity': 100,
         'quantity_yield': 80, 'cost': 2000, 'time_minutes': 120, 'game_version': '4.3.1'},
        {'_id': 'b', 'id': 'b', 'commodity_name': 'Quantanium (Raw)', 'method_name': 'Dinyx Solventation',
         'quantity': 100, 'quantity_yield': 90, 'cost': 1000, 'time_minutes': 60, 'game_version': '4.3.1'},
        {'_id': 'c', 'id': 'c', 'commodity_name': 'Quantanium (Raw)', 'method_name': 'Ferron Exchange',
         'quantity': 50, 'quantity_yield': 30, 'game_version': '4.3.1'},
        {'_id': 'old', 'id': 'old', 'commodity_name': 'Quantanium (Raw)', 'method_name': 'Ferron Exchange',
         'quantity': 50, 'quantity_yield': 50, 'game_version': '4.2'},
        {'_id': 'bad', 'id': 'bad', 'commodity_name': 'Gold', 'method_name': 'Ferron Exchange', 'quantity': 0},
    ])
    assert M.list_methods()[0] == {'id': 1, 'name': 'Dinyx Solventation', 'code': '', 'ratings': {'yield': 3.0}}
    stats = M.method_stats()
    assert stats['version'] == '4.3.1'
    rows = {r['method']: r for r in stats['rows'] if r['base'] == 'quantanium'}
    assert rows['Dinyx Solventation'] == {'base': 'quantanium', 'commodity': 'Quantanium (Raw)',
                                          'method': 'Dinyx Solventation', 'samples': 2, 'yield_pct': 85.0,
                                          'cost_per_scu': 15.0, 'minutes_per_scu': 0.9}
    assert rows['Ferron Exchange']['samples'] == 1 and rows['Ferron Exchange']['yield_pct'] == 60.0, '舊版本不算'
    assert rows['Ferron Exchange']['cost_per_scu'] is None


def test_list_all_week_month(app):
    """近 7 天／近 30 天加成：候選欄位有值就帶出，沒有就是 None。"""
    get_db()['uex_refinery_yields'].insert_many([
        {'_id': 'w', 'commodity_name': 'Laranite', 'terminal_name': 'HUR-L2 Refinery', 'value': 2,
         'value_week': 1.5, 'value_month': '2.5'},
        {'_id': 'a', 'commodity_name': 'Laranite', 'terminal_name': 'MIC-L1 Refinery', 'value': 1,
         'average_week': 4, 'average_month': 3},
        {'_id': 'n', 'commodity_name': 'Laranite', 'terminal_name': 'CRU-L1 Refinery', 'value': 0},
    ])
    rows = {r['terminal']: r for r in uex_refinery_yield.list_all()}
    assert (rows['HUR-L2 Refinery']['week'], rows['HUR-L2 Refinery']['month']) == (1.5, 2.5)
    assert (rows['MIC-L1 Refinery']['week'], rows['MIC-L1 Refinery']['month']) == (4.0, 3.0)
    assert rows['CRU-L1 Refinery']['week'] is None and rows['CRU-L1 Refinery']['month'] is None


def _seed_capacities():
    get_db()['uex_refinery_capacities'].insert_many([
        {'_id': '10', 'id_terminal': 10, 'terminal_name': 'ARC-L1 Refinery', 'space_station_name': 'ARC-L1',
         'star_system_name': 'Stanton', 'value': 72},
        {'_id': '11', 'id_terminal': 11, 'terminal_name': 'CRU-L1 Refinery', 'capacity_percent': '35.5'},
        {'_id': 'bad', 'terminal_name': 'MIC-L1 Refinery', 'value': None},
    ])


def test_list_capacities(app):
    _seed_capacities()
    rows = uex_refinery_yield.list_capacities()
    assert rows == [
        {'terminal': 'ARC-L1 Refinery', 'place': 'ARC-L1', 'system': 'Stanton', 'capacity_pct': 72.0},
        {'terminal': 'CRU-L1 Refinery', 'place': '', 'system': '', 'capacity_pct': 35.5},
    ]


def test_refinery_capacities_api(client, auth_headers):
    _seed_capacities()
    body = client.get('/mining/refinery-capacities', headers=auth_headers).get_json()
    assert body['success'] and len(body['data']) == 2
    assert client.get('/mining/refinery-capacities').status_code == 401


def test_method_ratings_candidates(app):
    """方法評等：rating_* 與 *_rating 等候選欄位都讀得到。"""
    from src.models import uex_refinery_method as M
    get_db()['uex_refinery_methods'].insert_many([
        {'_id': '1', 'id': 1, 'name': 'Cormack Method', 'yield_rating': 2, 'cost_rating': '1', 'speed_rating': 3},
        {'_id': '2', 'id': 2, 'name': 'Pyrometric Chromalysis', 'rating_yield': 3, 'rating_cost': 2,
         'rating_time': 1},
    ])
    rows = {m['name']: m['ratings'] for m in M.list_methods()}
    assert rows['Cormack Method'] == {'yield': 2.0, 'cost': 1.0, 'speed': 3.0}
    assert rows['Pyrometric Chromalysis'] == {'yield': 3.0, 'cost': 2.0, 'speed': 1.0}
