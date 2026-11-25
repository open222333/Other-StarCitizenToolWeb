"""主檔 API 的 ETag（src/http_cache.py）與配裝船清單快取（src/models/loadout.py）。"""
from src.mongo import get_db


def test_etag_and_304(client):
    get_db()['vehicle_master'].insert_one({'_id': 'v1', 'name': 'Aurora', 'name_lower': 'aurora', 'is_current': True,
                                            'player_visible': True})
    r = client.get('/item/vehicles')
    etag = r.headers.get('ETag')
    assert r.status_code == 200 and etag and r.headers['Cache-Control'] == 'private, no-cache'
    r2 = client.get('/item/vehicles', headers={'If-None-Match': etag})
    assert r2.status_code == 304 and not r2.data
    # 內容變了：ETag 跟著變
    get_db()['vehicle_master'].insert_one({'_id': 'v2', 'name': 'Bravo', 'name_lower': 'bravo', 'is_current': True,
                                            'player_visible': True})
    r3 = client.get('/item/vehicles', headers={'If-None-Match': etag})
    assert r3.status_code == 200 and r3.headers['ETag'] != etag


def test_loadout_cache_headers_and_ships_cache(client):
    db = get_db()
    db.ship_loadout_master.insert_one({'_id': 's1', 'name': 'Aurora', 'is_current': True})
    r = client.get('/item/loadout/ships')
    assert r.headers['Cache-Control'] == 'private, max-age=600' and r.headers.get('ETag')
    # 有同步紀錄時快取：再加一艘，run_id 沒變就還是舊清單
    db.sync_jobs.insert_many([{'_id': 'loadout', 'last_run_id': 'a'}, {'_id': 'vehicles', 'last_run_id': 'b'}])
    from src.models import loadout
    assert [s['name'] for s in loadout.ships()] == ['Aurora']
    db.ship_loadout_master.insert_one({'_id': 's2', 'name': 'Bravo', 'is_current': True})
    assert [s['name'] for s in loadout.ships()] == ['Aurora']
    db.sync_jobs.update_one({'_id': 'loadout'}, {'$set': {'last_run_id': 'c'}})
    assert [s['name'] for s in loadout.ships()] == ['Aurora', 'Bravo']


def test_personal_and_admin_write_untouched(client, auth_headers):
    """個人資料（/player…）、非 GET 都不加。"""
    r = client.get('/player/tab-config')
    assert r.status_code == 200 and 'ETag' not in r.headers
    r = client.post('/news/admin', json={'title': 'x'}, headers=auth_headers)
    assert 'ETag' not in r.headers
