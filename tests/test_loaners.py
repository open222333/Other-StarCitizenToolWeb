"""RSI 借用船清單（src/rsi_loaners.py、src/models/ship_loaner.py）：解析、展開船名、對到概念船。"""
from datetime import datetime

import httpx

from src import rsi_loaners as L
from src.models import ccu, ship_loaner
from src.mongo import get_db

# 2026-11 實際文章的節錄（格式照原樣：表頭、<br>、多個空白）
ROWS = [
    ('600i Explorer and Executive', 'Cyclone'), ('Carrack / Carrack Expedition', 'C8 Pisces, URSA Rover'),
    ('Fury Variants', 'Mustang Alpha'), ('Hull D, E', 'Hull C, Hercules C2'),
    ('Idris-M &amp; P', 'F7C-M Super Hornet, MPUV Passenger'), ('Kraken', 'Polaris, Ironclad Assault, Buccaneer'),
    ('Kraken Privateer', 'Polaris, Ironclad, Buccaneer'), ('Odin', 'Idris-P'), ('Pulse (+ LX)', 'Mustang Alpha'),
    ('X1 (+ Velocity, Force)', 'Mustang Alpha'), ('Zeus Mk II MR', 'Zeus Mk II ES'), ('Endeavor', 'Starfarer,  Cutlass Red'),
]
HTML = ('<p>intro</p><table><tbody><tr><td><strong>YOUR SHIP</strong></td><td><strong>OUR LOANER(S)</strong></td></tr>'
        + ''.join(f'<tr><td>{a}</td><td>{b}<br></td></tr>' for a, b in ROWS) + '</tbody></table><table><tr><td>x</td><td>y</td></tr></table>')


def test_parse_matrix_and_names():
    rows = L.parse_matrix(HTML)
    assert len(rows) == len(ROWS) and rows[0] == {'ship': '600i Explorer and Executive', 'loaners': ['Cyclone']}
    assert rows[4]['ship'] == 'Idris-M & P' and rows[-1]['loaners'] == ['Starfarer', 'Cutlass Red']
    names = lambda t: L.parse_ship_names(t)   # noqa: E731
    assert names('600i Explorer and Executive') == [('600i Explorer', False), ('600i Executive', False)]
    assert names('Hull D, E') == [('Hull D', False), ('Hull E', False)]
    assert names('Idris-M & P') == [('Idris-M', False), ('Idris-P', False)]
    assert names('Carrack / Carrack Expedition') == [('Carrack', False), ('Carrack Expedition', False)]
    assert names('Fury Variants') == [('Fury', True)]
    assert names('X1 (+ Velocity, Force)') == [('X1', False), ('X1 Velocity', False), ('X1 Force', False)]


def test_match_row():
    rows = L.parse_matrix(HTML)
    m = lambda n, mfr='': (L.match_row(n, rows, mfr) or {}).get('ship')   # noqa: E731
    assert m('Kraken') == 'Kraken' and m('Kraken Privateer') == 'Kraken Privateer'
    assert m('Hull E') == 'Hull D, E' and m('Idris-P') == 'Idris-M & P'
    assert m('Fury MX') == 'Fury Variants' and m('Fury') == 'Fury Variants'
    assert m('Pulse LX') == 'Pulse (+ LX)' and m('600i Executive') == '600i Explorer and Executive'
    assert m('Anvil Odin', 'Anvil Aerospace') == 'Odin'
    assert m('Odin', 'Anvil Aerospace') == 'Odin'
    assert m('Furyous') is None and m('Galaxy') is None


def test_fetch_matrix():
    def handler(req):
        assert req.url.path.endswith('360003093114.json')
        return httpx.Response(200, json={'article': {'body': HTML, 'updated_at': '2026-11-12T17:18:59Z', 'html_url': 'https://x/a'}})
    data = L.fetch_matrix(httpx.Client(transport=httpx.MockTransport(handler)))
    assert len(data['rows']) == len(ROWS) and data['updated_at'] == '2026-11-12T17:18:59Z'
    bad = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'article': {'body': '<p>no table</p>'}})))
    try:
        L.fetch_matrix(bad)
        raise AssertionError('應該失敗')
    except L.LoanerError as err:
        assert '只解析出 0 列' in str(err)


def test_concept_ship_loaners(app, client):
    """概念船附上借用船（借用船對到載具主檔就帶 uuid）；清單拿掉的列下架。"""
    db = get_db()
    db.vehicle_master.insert_one({'_id': 'v-idris', 'name': 'Idris-P', 'is_current': True})
    db.rsi_ships.insert_many([
        {'_id': 11, 'name': 'Odin', 'manufacturer': 'Anvil Aerospace', 'flyable_status': 'In Production', 'is_current': True},
        {'_id': 12, 'name': 'Galaxy', 'flyable_status': 'In Concept', 'is_current': True},
    ])
    now = datetime.utcnow()
    ship_loaner.save(L.parse_matrix(HTML), 'r1', now, '2026-11-12T17:18:59Z')
    rows = {r['name']: r for r in ccu.concept_ships()}
    lo = rows['Odin']['loaner']
    assert lo['ship'] == 'Odin' and lo['loaners'] == [{'name': 'Idris-P', 'vehicle_uuid': 'v-idris', 'name_zh': None}]
    assert rows['Galaxy']['loaner'] is None
    body = client.get('/item/vehicles?concept=only').get_json()
    assert next(r for r in body['data'] if r['name'] == 'Odin')['loaner']['loaners'][0]['name'] == 'Idris-P'
    # 下一輪清單只剩一列：其他標下架
    st = ship_loaner.save([{'ship': 'Odin', 'loaners': ['Idris-P']}], 'r2', now)
    assert st['retired'] == len(ROWS) - 1 and len(ship_loaner.current_rows()) == 1
