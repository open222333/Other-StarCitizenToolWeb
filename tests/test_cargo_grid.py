"""飛船貨物網格（sc-cargo.space）：欄位映射、同步項目、對應載具主檔。"""
from src.models import cargo_grid
from src.mongo import get_db
from src.scdata import CARGO_GRID_LIST_URL, CARGO_GRID_RAW_BASE, map_cargo_grid

HULL_C = {'manufacturer': 'MISC', 'name': 'Hull-C', 'alternativeNames': ['Hull C Hauler'], 'official': {
    'capacity': 4608, 'groups': [{'x': 0, 'z': 0, 'grids': [
        {'x': 0, 'y': 0, 'z': 0, 'width': 12, 'height': 6, 'length': 8},
        {'x': 14, 'y': 0, 'z': 0, 'width': 2, 'height': 2, 'length': 2, 'maxSize': 8, 'unsecured': True}]},
        {'name': 'Spine', 'x': 0, 'z': 11, 'grids': [{'x': 0, 'y': 0, 'z': 0, 'width': 1, 'height': 1, 'length': 1}]}]}}
CAT = {'manufacturer': 'Drake', 'name': 'Caterpillar', 'official': {'capacity': 576, 'groups': []},
       'unofficial': {'capacity': 600, 'groups': []}}


def test_map_cargo_grid():
    doc = map_cargo_grid('hull_c', HULL_C)
    assert doc['_id'] == 'hull_c' and doc['capacity_scu'] == 4608 and doc['grid_count'] == 3
    grids = doc['official']['grids']
    assert grids[0]['scu'] == 576 and grids[1]['max_size'] == 8 and grids[1]['unsecured'] is True
    assert grids[2]['group'] == 'Spine' and grids[2]['z'] == 11 and grids[0]['group'] == '區 1'
    assert doc['max_box_scu'] == 8 and doc['unofficial'] is None
    assert map_cargo_grid('cat', CAT)['unofficial_capacity_scu'] == 600
    assert map_cargo_grid('bad', {'name': 'X'}) is None


def test_cargo_grids_sync_job_and_vehicle_link(app, monkeypatch):
    import tasks.scdata_sync as sync_mod
    db = get_db()
    db.vehicle_master.insert_many([
        {'_id': 'v-hull', 'name': 'Hull C', 'game_name': 'MISC Hull C', 'manufacturer_name': 'MISC', 'is_current': True},
        {'_id': 'v-cat', 'name': 'Caterpillar', 'manufacturer_code': 'DRAK', 'is_current': True},
    ])
    db.cargo_grid_master.insert_one({'_id': 'old_ship', 'name': 'Old', 'is_current': True})
    fetched = []

    def fake_fetch(client, url, expect=list, label=''):
        fetched.append(url)
        if url == CARGO_GRID_LIST_URL:
            return [{'name': 'hull_c.json', 'type': 'file'}, {'name': 'caterpillar.json', 'type': 'file'},
                    {'name': 'README.md', 'type': 'file'}]
        return {f'{CARGO_GRID_RAW_BASE}/hull_c.json': HULL_C, f'{CARGO_GRID_RAW_BASE}/caterpillar.json': CAT}[url]
    monkeypatch.setattr(sync_mod, 'fetch_json_url', fake_fetch)
    result = sync_mod._do_sync(jobs=['cargo_grids'])
    assert result['ok'] is True
    assert len(fetched) == 3, 'README 不抓'
    hull = db.cargo_grid_master.find_one({'_id': 'hull_c'})
    assert hull['vehicle_uuids'] == ['v-hull'] and hull['vehicle_names'] == ['Hull C']
    assert db.cargo_grid_master.find_one({'_id': 'caterpillar'})['vehicle_uuid'] == 'v-cat'
    assert db.cargo_grid_master.find_one({'_id': 'old_ship'})['is_current'] is False
    assert cargo_grid.link_vehicles() == 0


def test_link_vehicles_prefix_fallback(app):
    """完全對不到的船名用「載具名稱以它開頭」補對；已經完全對到別的網格的載具不搶，符合好幾個時給最長的。"""
    db = get_db()
    db.vehicle_master.insert_many([
        {'_id': 'v-c2', 'name': 'C2 Hercules Starlifter', 'manufacturer_name': 'Crusader Industries', 'is_current': True},
        {'_id': 'v-mpuv', 'name': 'MPUV Cargo', 'manufacturer_code': 'ARGO', 'is_current': True},
        {'_id': 'v-pisces', 'name': 'C8X Pisces Expedition', 'is_current': True},
        {'_id': 'v-pisces-x', 'name': 'C8X Pisces', 'is_current': True},
        {'_id': 'v-galaxy', 'name': 'Galaxy', 'is_current': True},
        {'_id': 'v-nomad', 'name': 'Consolidated Outland Nomad', 'manufacturer_name': 'Consolidated Outland',
         'is_current': True},
        {'_id': 'v-mustang', 'name': 'C.O. Mustang Alpha', 'is_current': True},
        {'_id': 'v-aurora', 'name': 'RSI Aurora Mk I CL', 'manufacturer_code': 'RSI', 'is_current': True},
    ])
    db.cargo_grid_master.insert_many([
        {'_id': 'c2', 'name': 'C2 Hercules', 'manufacturer': 'Crusader'},
        {'_id': 'mpuv', 'name': 'MPUV-C', 'manufacturer': 'Argo'},
        {'_id': 'pisces', 'name': 'C8X Pisces', 'manufacturer': 'Anvil'},
        {'_id': 'galaxy', 'name': 'Galaxy [Cargo Concept]', 'manufacturer': 'RSI'},
        {'_id': 'gal', 'name': 'Gal', 'manufacturer': 'X'},
        {'_id': 'nomad', 'name': 'Nomad', 'manufacturer': 'Consolidated Outland'},
        {'_id': 'mustang', 'name': 'Mustang Alpha', 'manufacturer': 'Consolidated Outland'},
        {'_id': 'aurora', 'name': 'Aurora CL (Mk I)', 'manufacturer': 'RSI'},
    ])
    assert cargo_grid.link_vehicles() == 7
    got = {r['_id']: r.get('vehicle_uuids') for r in db.cargo_grid_master.find()}
    assert got['c2'] == ['v-c2'] and got['mpuv'] == ['v-mpuv'] and got['nomad'] == ['v-nomad']
    assert got['pisces'] == ['v-pisces-x'], '完全對到就不用開頭比對（Expedition 不併進來）'
    assert got['galaxy'] == ['v-galaxy'], '概念船標記拿掉再比'
    assert not got['gal'], '太短的名稱不做開頭比對'
    assert got['mustang'] == ['v-mustang'], '廠商縮寫前綴（C.O.）拿掉再比'
    assert got['aurora'] == ['v-aurora'], '型號（Mk I）在後面的寫法也比'
    assert cargo_grid.link_vehicles() == 0


def test_cargo_grids_api(client, auth_headers, app):
    from src.models import nav
    from src.scdata import map_cargo_grid
    db = get_db()
    db.vehicle_master.insert_one({'_id': 'v-hull', 'name': 'Hull C', 'class_name': 'MISC_Hull_C', 'is_current': True})
    doc = map_cargo_grid('hull_c', HULL_C)
    doc.update({'is_current': True, 'vehicle_uuids': ['v-hull']})
    db.cargo_grid_master.insert_many([doc, {'_id': 'gone', 'name': 'Gone', 'is_current': False,
                                            'official': {'grids': [{'width': 1}]}}])
    nav.clear_cache()
    rows = client.get('/starmap/nav/cargo-grids', headers=auth_headers).get_json()['data']
    assert [r['id'] for r in rows] == ['hull_c']
    hull = rows[0]
    assert hull['capacity'] == 4608 and hull['vehicle_uuids'] == ['v-hull'] and len(hull['official']['grids']) == 3
    assert hull['official']['grids'][1] == {'x': 14.0, 'y': 0.0, 'z': 0.0, 'width': 2.0, 'height': 2.0, 'length': 2.0,
                                            'max_size': 8, 'min_size': None, 'unsecured': True, 'group': '區 1',
                                            'name': None}
    assert hull['aliases'] == ['Hull C Hauler']
