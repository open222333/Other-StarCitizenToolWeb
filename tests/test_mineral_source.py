"""礦物取得方式（src/models/mineral_source.py、app/mining/view.py 的 /mining/sources）。"""


def test_crud_and_validation(client, auth_headers):
    assert client.get('/mining/sources').get_json()['data'] == []
    body = {'resource_name': 'Carinite', 'methods': ['special', 'cave'], 'description': '先完成 **特殊行動**',
            'locations': ['Pyro', 'Pyro', ' '], 'source_url': 'https://example.com/x'}
    res = client.put('/mining/sources/Carinite', json=body, headers=auth_headers)
    assert res.status_code == 200
    data = client.get('/mining/sources').get_json()
    assert data['methods_label']['special'] == '特殊行動'
    row = data['data'][0]
    assert row['key'] == 'Carinite' and row['methods'] == ['special', 'cave'] and row['locations'] == ['Pyro']
    assert row['updated_at'].endswith('Z')
    # 改：整筆覆寫
    client.put('/mining/sources/Carinite', json={'methods': ['event']}, headers=auth_headers)
    assert client.get('/mining/sources').get_json()['data'][0]['methods'] == ['event']
    # 驗證
    for bad in ({'methods': ['nope']}, {'methods': []}, {'methods': ['special'], 'source_url': 'javascript:alert(1)'},
                {'methods': 'special'}, {'methods': ['special'], 'description': 'x' * 5001}):
        assert client.put('/mining/sources/Carinite', json=bad, headers=auth_headers).status_code == 400, bad
    # 刪除
    assert client.delete('/mining/sources/Carinite', headers=auth_headers).status_code == 200
    assert client.delete('/mining/sources/Carinite', headers=auth_headers).status_code == 404
    assert client.get('/mining/sources').get_json()['data'] == []


def test_write_requires_admin(client):
    assert client.put('/mining/sources/Carinite', json={'methods': ['special']}).status_code in (401, 403)
    assert client.delete('/mining/sources/Carinite').status_code in (401, 403)


def test_auto_sources_from_commodities(client):
    """Wiki API 標成可開採、卻沒有產地的礦物（例如 Carinite）自動列為「需特殊取得」；有產地的不列。"""
    from src.mongo import get_db
    get_db()['commodity_master'].insert_many([
        {'_id': 'c1', 'key': 'Carinite', 'name': 'Carinite', 'is_mineable': True, 'is_current': True,
         'methods': [], 'location_count': 0, 'description': 'A rare mineral', 'web_url': 'https://w/carinite'},
        {'_id': 'c2', 'key': 'Iron', 'name': 'Iron', 'is_mineable': True, 'is_current': True,
         'methods': ['Ship'], 'location_count': 5},
        # 舊資料（還沒重新同步，新欄位不在）：從 raw 判斷
        {'_id': 'c3', 'key': 'Beradom', 'name': 'Beradom', 'is_mineable': True, 'is_current': True,
         'raw': {'methods': ['GroundVehicle'], 'locations': [{}]}},
        {'_id': 'c4', 'key': 'Water', 'name': 'Water', 'is_mineable': False, 'is_current': True, 'methods': []},
    ])
    body = client.get('/mining/sources').get_json()
    assert [a['key'] for a in body['auto']] == ['Carinite']
    a = body['auto'][0]
    assert a['methods'] == ['unplaced'] and a['description_en'] == 'A rare mineral'
    assert body['methods_label']['unplaced'] == '需特殊取得'
