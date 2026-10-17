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
