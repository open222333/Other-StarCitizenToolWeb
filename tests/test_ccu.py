"""CCU 價格資料庫：RSI 商店的抓取流程（假的上游）、欄位映射、上下架歷史、同步項目的防呆。"""
import json
from datetime import datetime, timedelta

import httpx
import pytest

from src import rsi_store
from src.models import ccu
from src.mongo import get_db


def _ship(id_, name, msrp_cents, skus=(), mfr='Aegis Dynamics'):
    return {'id': id_, 'name': name, 'msrp': msrp_cents, 'link': f'/pledge/ships/{id_}', 'focus': 'Combat',
            'type': 'combat', 'flyableStatus': 'Flyable', 'manufacturer': {'id': 1, 'name': mfr}, 'skus': list(skus)}


SHIPS = [
    _ship(1, 'Aurora MR', 2500, mfr='Roberts Space Industries'),
    _ship(2, 'Avenger Titan', 5500, [
        {'id': 21, 'title': 'Standalone Ship', 'price': 5500, 'available': True, 'unlimitedStock': True,
         'body': '<p>Includes 120 Months Insurance</p>'}]),
    _ship(3, 'Galaxy', 38000, [
        {'id': 31, 'title': 'Galaxy - Warbond Edition', 'price': 34000, 'available': True,
         'unlimitedStock': False, 'availableStock': 150, 'body': 'Lifetime Insurance'},
        {'id': 32, 'title': 'Galaxy - Sold out', 'price': 38000, 'available': False}]),
]
UPGRADES = [
    {'id': 2, 'skus': [{'id': 201, 'title': 'Avenger Titan Upgrade', 'price': 5500, 'upgradePrice': 3000,
                        'available': True, 'unlimitedStock': True}]},
    {'id': 3, 'skus': [{'id': 301, 'title': 'Galaxy Warbond Upgrade', 'price': 35000, 'upgradePrice': 32500,
                        'available': True, 'unlimitedStock': True}]},
]


def _transport(ships=SHIPS, upgrades=UPGRADES, calls=None):
    def handler(request: httpx.Request):
        calls is not None and calls.append(request.url.path)
        if request.url.path.endswith('setAuthToken'):
            return httpx.Response(200, json={'success': 1}, headers={'set-cookie': 'Rsi-Token=abc; Path=/'})
        if request.url.path.endswith('setContextToken'):
            assert request.headers.get('x-rsi-token') == 'abc'
            return httpx.Response(200, json={'success': 1})
        body = json.loads(request.content)[0]
        if body['operationName'] == 'initShipUpgrade':
            return httpx.Response(200, json=[{'data': {'ships': ships, 'app': {'pricing': {'exponent': 2}}}}])
        assert body['variables']['fromId'] == 1, '從最便宜的船開始看升級'
        return httpx.Response(200, json=[{'data': {'to': {'ships': upgrades}}}])
    return httpx.MockTransport(handler)


def test_mapping():
    ships = rsi_store.map_ships(SHIPS)
    assert [s['msrp'] for s in ships] == [25.0, 55.0, 380.0]
    assert ships[1]['link'].startswith('https://robertsspaceindustries.com/')
    offers = rsi_store.map_ship_offers(SHIPS)
    assert [o['sku_id'] for o in offers] == [21, 31], '下架的 SKU 不收'
    titan, galaxy = offers
    assert titan['insurance'] == '120 個月' and titan['savings'] == 0 and titan['stock'] is None
    assert galaxy['is_warbond'] and galaxy['is_discount'] and galaxy['savings'] == 40.0
    assert galaxy['insurance'] == 'LTI' and galaxy['stock'] == 150
    ups = rsi_store.map_upgrade_offers(UPGRADES, {s['rsi_id']: s for s in ships}, 1)
    gal = ups[1]
    assert gal['kind'] == 'ccu' and gal['price'] == 350.0 and gal['upgrade_price'] == 325.0
    assert gal['savings'] == 30.0 and gal['is_discount'] and gal['is_warbond']
    assert ups[0]['savings'] == 0 and not ups[0]['is_discount']
    assert rsi_store.parse_insurance('6 Month Insurance') == '6 個月'
    assert rsi_store.parse_insurance('nothing') is None
    assert rsi_store.to_usd('x') is None


def test_fetch_store_flow():
    calls = []
    with httpx.Client(transport=_transport(calls=calls)) as client:
        raw = rsi_store.fetch_store(client)
    assert raw['from_id'] == 1 and len(raw['ships']) == 3 and len(raw['upgrades']) == 2
    assert calls[:2] == ['/api/account/v2/setAuthToken', '/api/ship-upgrades/setContextToken']


def test_graphql_errors_raise():
    def handler(request):
        if 'graphql' in request.url.path:
            return httpx.Response(200, json=[{'errors': [{'message': 'nope'}]}])
        return httpx.Response(200, json={})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(rsi_store.RsiStoreError, match='nope'):
            rsi_store.fetch_store(client)

    def blocked(request):
        return httpx.Response(403, text='<html>cloudflare</html>')
    with httpx.Client(transport=httpx.MockTransport(blocked)) as client:
        with pytest.raises(rsi_store.RsiStoreError, match='403'):
            rsi_store.fetch_store(client)


def _save(ships_raw, upgrades_raw, run, at):
    ships = rsi_store.map_ships(ships_raw)
    offers = rsi_store.map_ship_offers(ships_raw) + \
        rsi_store.map_upgrade_offers(upgrades_raw, {s['rsi_id']: s for s in ships}, 1)
    ccu.save_ships(ships, run, at)
    return ccu.save_offers(offers, ships, run, at)


def test_history_periods_and_prices(app):
    db = get_db()
    db.vehicle_master.insert_many([{'_id': 'v-gal', 'name': 'Galaxy', 'is_current': True},
                                   {'_id': 'v-titan', 'name': 'Avenger Titan', 'is_current': True}])
    t0 = datetime(2026, 11, 1)
    stats = _save(SHIPS, UPGRADES, 'r1', t0)
    assert stats['opened'] == 4 and stats['ended'] == 0
    wb = db.ccu_offers.find_one({'_id': 'ccu:301:3'})
    assert wb['ship_name'] == 'Galaxy' and wb['vehicle_uuid'] == 'v-gal' and wb['from_ship_name'] == 'Aurora MR'
    assert wb['periods'] == [{'start': t0, 'end': None}]
    assert db.rsi_ships.find_one({'_id': 3})['msrp_history'] == [{'msrp': 380.0, 'at': t0}]

    # 第二輪：WB 升級下架、Titan 單買價變了
    t1 = t0 + timedelta(hours=6)
    ships2 = [dict(s) for s in SHIPS]
    ships2[1] = _ship(2, 'Avenger Titan', 5500, [{'id': 21, 'title': 'Standalone Ship', 'price': 5000,
                                                  'available': True, 'unlimitedStock': True}])
    stats = _save(ships2, UPGRADES[:1], 'r2', t1)
    assert stats['ended'] == 1 and stats['opened'] == 0
    wb = db.ccu_offers.find_one({'_id': 'ccu:301:3'})
    assert wb['is_current'] is False and wb['ended_at'] == t0 and wb['periods'] == [{'start': t0, 'end': t0}]
    titan = db.ccu_offers.find_one({'_id': 'ship:21:2'})
    assert [p['price'] for p in titan['price_history']] == [55.0, 50.0]

    # 第三輪：WB 又上架 → 新的一段
    t2 = t1 + timedelta(days=30)
    stats = _save(ships2, UPGRADES, 'r3', t2)
    wb = db.ccu_offers.find_one({'_id': 'ccu:301:3'})
    assert wb['is_current'] is True and len(wb['periods']) == 2 and wb['periods'][-1] == {'start': t2, 'end': None}
    assert wb['first_seen_at'] == t0


def test_sync_job(app, monkeypatch):
    import tasks.scdata_sync as sync_mod
    real = sync_mod.build_client
    monkeypatch.setattr(sync_mod, 'build_client', lambda **kw: real(transport=_transport()))
    result = sync_mod._do_sync(jobs=['ccu'])
    assert result['ok'] is True, result
    db = get_db()
    assert db.rsi_ships.count_documents({'is_current': True}) == 3
    assert db.ccu_offers.count_documents({'is_current': True}) == 4
    job = db.sync_jobs.find_one({'_id': 'ccu'})
    assert job['last_ok'] is True and job['last_requests']['rsi']['requests'] == 4


def test_sync_job_guard_keeps_data(app, monkeypatch):
    """抓到的船太少（例如被擋、格式變了）：整輪失敗，原本的資料不下架。"""
    import tasks.scdata_sync as sync_mod
    db = get_db()
    db.rsi_ships.insert_many([{'_id': i, 'name': f'S{i}', 'is_current': True} for i in range(100, 120)])
    real = sync_mod.build_client
    monkeypatch.setattr(sync_mod, 'build_client', lambda **kw: real(transport=_transport()))
    result = sync_mod._do_sync(jobs=['ccu'])
    assert result['ok'] is False
    assert db.rsi_ships.count_documents({'is_current': True}) == 20
    assert db.ccu_offers.count_documents({}) == 0


# ── Open Hangar 上架歷史 ─────────────────────────────────────────────
# 結構照 https://openhangar.space/api/store/catalog 實際回傳（只留用到的欄位）
OH_CATALOG = {
    'at': 1794644024525,
    'items': [
        {'s': None, 'k': 'ccus', 'n': 'Upgrade to Galaxy', 'p': 400, 'hk': 'Galaxy', 'toShipId': 3,
         'wbu': {'p': 360, 'std': 400}},
        {'s': 89, 'k': 'ships', 'n': 'Freelancer', 'p': 110, 'hk': 'Freelancer'},
    ],
    'makers': {'Galaxy': 'Roberts Space Industries', 'Avenger Titan': 'Aegis Dynamics'},
    'avail': {'Galaxy': {'avail': 'hardly', 'firstSold': 1669479486791},
              'Avenger Titan': {'avail': 'always', 'firstSold': 1637273760000}},
    'history': {
        'Galaxy': [[1700928423399, 1701374703709, 380, 'S', 380],
                   [1669479486791, 1673294581915, 380, 'S', 380]],
        'Avenger Titan': [[1637273760000, 1655224863636, 55, 'S', 55],
                          [1655734563841, None, 60, 'S', 55],
                          [1702310703745, 1704744601635, 60, 'U', 60]],
        'Skylark': [[1794585644789, None, 40, 'W', 45]],
        'Broken': [['x'], None],
    },
}


def _oh_transport(payload=OH_CATALOG, status=200):
    def handler(request):
        assert request.url.path == '/api/store/catalog'
        return httpx.Response(status, json=payload)
    return httpx.MockTransport(handler)


def test_openhangar_mapping():
    from src import openhangar
    ships = {s['name']: s for s in openhangar.map_history(OH_CATALOG)}
    assert set(ships) == {'Galaxy', 'Avenger Titan', 'Skylark'}, '格式壞掉的列略過'
    gal = ships['Galaxy']
    assert gal['rsi_id'] == 3 and gal['avail'] == 'hardly' and gal['manufacturer'] == 'Roberts Space Industries'
    assert [p['start'].year for p in gal['periods']] == [2022, 2023], '照開始時間排序'
    assert gal['on_sale'] is False and gal['msrp'] == 380.0
    titan = ships['Avenger Titan']
    assert titan['on_sale'] and titan['last_price'] == 60.0
    assert [p['sale_type'] for p in titan['periods']] == ['standard', 'standard', 'code_u']
    sky = ships['Skylark']
    assert sky['warbond_count'] == 1 and sky['periods'][0]['sale_type'] == 'warbond' and sky['msrp'] == 45.0
    assert sky['periods'][0]['end'] is None and sky['first_sold_at'] == sky['periods'][0]['start']


def test_openhangar_sync_job(app, monkeypatch):
    import tasks.scdata_sync as sync_mod
    db = get_db()
    db.vehicle_master.insert_one({'_id': 'v-titan', 'name': 'Avenger Titan', 'is_current': True})
    db.rsi_ships.insert_one({'_id': 2, 'name': 'Avenger Titan', 'is_current': True})
    real = sync_mod.build_client
    monkeypatch.setattr(sync_mod, 'build_client', lambda **kw: real(transport=_oh_transport()))
    result = sync_mod._do_sync(jobs=['openhangar'])
    assert result['ok'] is True, result
    titan = db.ship_sale_history.find_one({'_id': 'Avenger Titan'})
    assert titan['rsi_id'] == 2 and titan['vehicle_uuid'] == 'v-titan', '沒有升級品項時用名稱對 rsi_ships'
    assert titan['source'] == 'openhangar' and titan['credibility'] == '歷史紀錄'
    assert db.ship_sale_history.find_one({'_id': 'Galaxy'})['rsi_id'] == 3
    job = db.sync_jobs.find_one({'_id': 'openhangar'})
    assert job['last_ok'] is True and job['last_requests']['openhangar']['requests'] == 1


def test_openhangar_guard(app, monkeypatch):
    import tasks.scdata_sync as sync_mod
    db = get_db()
    db.ship_sale_history.insert_many([{'_id': f'S{i}', 'name': f'S{i}'} for i in range(10)])
    real = sync_mod.build_client
    monkeypatch.setattr(sync_mod, 'build_client', lambda **kw: real(transport=_oh_transport()))
    assert sync_mod._do_sync(jobs=['openhangar'])['ok'] is False, '3 艘 < 10 艘的 80%'
    monkeypatch.setattr(sync_mod, 'build_client', lambda **kw: real(transport=_oh_transport(status=503)))
    assert sync_mod._do_sync(jobs=['openhangar'])['ok'] is False
    assert db.ship_sale_history.count_documents({}) == 10


def test_ship_price_api(app, client):
    """玩家頁「資料庫 › 船價」：RSI 與 Open Hangar 合併；重疊的同種類期間以 RSI 為準；不用登入。"""
    from src import openhangar
    db = get_db()
    db.vehicle_master.insert_one({'_id': 'v-gal', 'name': 'Galaxy', 'is_current': True})
    t0 = datetime(2026, 11, 1)
    _save(SHIPS, UPGRADES, 'r1', t0)
    oh = dict(OH_CATALOG, history=dict(OH_CATALOG['history'], Galaxy=OH_CATALOG['history']['Galaxy'] + [
        [int(datetime(2026, 10, 30).timestamp() * 1000), None, 340, 'W', 380]]))
    ccu.save_sale_history(openhangar.map_history(oh), 'oh1', t0)

    body = client.get('/item/ship-prices').get_json()
    assert body['success'] and 'Open Hangar' in body['attribution']
    rows = {r['name']: r for r in body['data']}
    assert set(rows) == {'Galaxy', 'Avenger Titan', 'Skylark', 'Aurora MR'}, 'RSI 有、歷史沒有的船也列'
    gal = rows['Galaxy']
    assert gal['msrp'] == 380.0 and gal['msrp_source'] == 'rsi' and gal['avail'] == 'hardly'
    assert gal['on_sale'] and gal['warbond_now'] and gal['price_now'] == 340.0
    assert gal['warbond_count'] == 1, 'Open Hangar 的 WB 跟 RSI 的 WB 重疊，只算 RSI 那段'
    assert gal['period_count'] == 3 and 'periods' not in gal and '_periods' not in gal
    assert rows['Aurora MR']['key'] == 'rsi:1' and rows['Aurora MR']['on_sale'] is False
    # Skylark 的 Open Hangar Warbond 在開始抓 RSI（t0）之後才開始：以 RSI 為準，不收
    assert rows['Skylark']['msrp_source'] == 'openhangar' and rows['Skylark']['last_warbond'] is None

    detail = client.get('/item/ship-prices/detail', query_string={'key': 'Galaxy'}).get_json()['data']
    assert [p['source'] for p in detail['periods']] == ['rsi', 'openhangar', 'openhangar']
    assert detail['periods'][0]['credibility'] == '官方確認' and detail['periods'][0]['insurance'] == 'LTI'
    assert client.get('/item/ship-prices/detail', query_string={'key': 'rsi:1'}).get_json()['data']['periods'] == []
    assert client.get('/item/ship-prices/detail', query_string={'key': 'nope'}).status_code == 404
    assert client.get('/item/ship-prices/detail', query_string={'key': 'rsi:x'}).status_code == 404


def test_openhangar_only_before_rsi(app):
    """開始抓 RSI 之後的期間只用 RSI：Open Hangar 在那之後開始的段不收（例如標錯的 Warbond、重複的上架），跨過那天的截到那天。"""
    from src.models import ccu
    t0 = datetime(2026, 11, 1)
    _save(SHIPS, UPGRADES, 'r1', t0)
    hist = {'periods': [
        {'start': datetime(2026, 5, 23), 'end': datetime(2026, 5, 24), 'price': 485, 'sale_type': 'warbond'},
        {'start': datetime(2026, 10, 1), 'end': None, 'price': 520, 'sale_type': 'standard'},
        {'start': datetime(2026, 11, 16), 'end': None, 'price': 520, 'sale_type': 'standard'},
        {'start': datetime(2026, 11, 14), 'end': datetime(2026, 11, 15), 'price': 480, 'sale_type': 'warbond'},
    ]}
    assert ccu.rsi_since() == t0
    out = ccu._merged_periods(hist, [], datetime(2026, 11, 20), ccu.rsi_since())
    assert [(p['start'].month, p['start'].day, p['end'].month, p['end'].day) for p in out] == [(10, 1, 11, 1), (5, 23, 5, 24)]
    assert ccu._merged_periods(hist, [], datetime(2026, 11, 20)) and len(ccu._merged_periods(hist, [], datetime(2026, 11, 20))) == 4, '還沒抓過 RSI 時全收'


def test_concept_ships_in_vehicle_list(app, client):
    """資料庫 › 艦船：RSI 商店裡還沒做進遊戲的船（概念、製作中）接在列表最後，只有美金價與上架紀錄。"""
    db = get_db()
    assert ccu.concept_status('In Concept') == 'concept' and ccu.concept_status('in-production') == 'production'
    assert ccu.concept_status('Flight Ready') == '' and ccu.concept_status(None) == ''
    db.vehicle_master.insert_many([
        {'_id': 'v-a', 'name': 'Aurora MR', 'manufacturer_name': 'Roberts Space Industries', 'manufacturer_code': 'RSIN',
         'is_current': True, 'player_visible': True},
    ])
    db.rsi_ships.insert_many([
        {'_id': 10, 'name': 'Galaxy', 'manufacturer': 'Roberts Space Industries', 'msrp': 380, 'focus': 'Multi-Role',
         'flyable_status': 'In Concept', 'vehicle_uuid': None, 'is_current': True},
        {'_id': 11, 'name': 'Odin', 'manufacturer': 'Anvil Aerospace', 'msrp': 900, 'flyable_status': 'In Production',
         'vehicle_uuid': None, 'is_current': True},
        {'_id': 12, 'name': 'Aurora MR', 'manufacturer': 'Roberts Space Industries', 'msrp': 25,
         'flyable_status': 'Flight Ready', 'vehicle_uuid': 'v-a', 'is_current': True},
        {'_id': 13, 'name': 'Old Concept', 'flyable_status': 'In Concept', 'is_current': False},
    ])
    db.ship_sale_history.insert_one({'_id': 'Galaxy', 'name': 'Galaxy', 'rsi_id': 10, 'periods': []})
    rows = ccu.concept_ships()
    assert [r['name'] for r in rows] == ['Galaxy', 'Odin']
    assert rows[0]['price_key'] == 'Galaxy' and rows[1]['price_key'] == 'rsi:11' and rows[0]['manufacturer_code'] == 'RSIN'

    body = client.get('/item/vehicles').get_json()
    assert [r['name'] for r in body['data']] == ['Aurora MR', 'Galaxy', 'Odin'] and body['total'] == 3
    assert body['data'][1]['is_concept'] and body['data'][1]['concept_status'] == 'concept'
    assert [r['name'] for r in client.get('/item/vehicles?q=gal').get_json()['data']] == ['Galaxy']
    assert [r['name'] for r in client.get('/item/vehicles?manufacturer_code=RSIN').get_json()['data']] == ['Aurora MR', 'Galaxy']
    assert [r['name'] for r in client.get('/item/vehicles?usd_min=500').get_json()['data']] == ['Odin']
    # 遊戲內數值的條件（尺寸、貨艙、取得方式…）概念船都沒有：不列
    assert [r['name'] for r in client.get('/item/vehicles?scu_min=1').get_json()['data']] == []
    page2 = client.get('/item/vehicles?limit=2&offset=2').get_json()
    assert [r['name'] for r in page2['data']] == ['Odin'] and page2['total'] == 3


def test_match_vehicle_name_variants(app):
    """商店船名對載具主檔：遊戲全名、標點空白、商店名稱較短（只有一艘符合）都對得到。"""
    from src.models import ccu
    db = get_db()
    db.vehicle_master.insert_many([
        {'_id': 'v-m2', 'name': 'M2 Hercules Starlifter', 'game_name': 'Crusader M2 Hercules Starlifter',
         'manufacturer_name': 'Crusader Industries', 'is_current': True},
        {'_id': 'v-c2', 'name': 'C2 Hercules Starlifter', 'manufacturer_name': 'Crusader Industries', 'is_current': True},
        {'_id': 'v-p', 'name': 'RSI Perseus', 'is_current': True},
    ])
    index = ccu._vehicle_index()
    assert ccu.match_vehicle('M2 Hercules Starlifter', 'Crusader Industries', index) == 'v-m2'
    assert ccu.match_vehicle('Crusader M2 Hercules  Starlifter', '', index) == 'v-m2'
    assert ccu.match_vehicle('M2 Hercules', 'Crusader Industries', index) == 'v-m2'
    assert ccu.match_vehicle('Perseus', 'RSI', index) == 'v-p'
    assert ccu.match_vehicle('Hercules', 'Crusader Industries', index) is None, '好幾艘都符合時不亂猜'


def test_price_rows_relink_unmatched_history(app):
    """同步時還對不到載具（vehicle_uuid=None）的歷史，讀取時再對一次。"""
    from src.models import ccu
    db = get_db()
    db.ship_sale_history.insert_one({'_id': 'M2 Hercules', 'name': 'M2 Hercules', 'manufacturer': 'Crusader Industries',
                                     'vehicle_uuid': None, 'rsi_id': None, 'periods': []})
    db.vehicle_master.insert_one({'_id': 'v-m2', 'name': 'M2 Hercules Starlifter', 'is_current': True})
    rows = ccu.ship_price_list()
    assert [r['vehicle_uuid'] for r in rows if r['name'] == 'M2 Hercules'] == ['v-m2']


def test_ship_price_cache_and_etag(app, client):
    """船價列表：三個同步項目的 run_id 當版本，沒變就用快取、帶 ETag 回 304；明細只查那一艘。"""
    ccu._list_cache.update(version=None, rows=None)   # 模組層快取，測試之間要清掉
    db = get_db()
    db.vehicle_master.insert_one({'_id': 'v-gal', 'name': 'Galaxy', 'is_current': True})
    db.ship_sale_history.insert_one({'_id': 'Galaxy', 'name': 'Galaxy', 'rsi_id': 7, 'vehicle_uuid': 'v-gal',
                                     'periods': []})
    db.rsi_ships.insert_one({'_id': 7, 'name': 'Galaxy', 'is_current': True})
    db.sync_jobs.insert_many([{'_id': 'ccu', 'last_run_id': 'r1'}, {'_id': 'openhangar', 'last_run_id': 'r2'},
                              {'_id': 'vehicles', 'last_run_id': 'r3'}])
    res = client.get('/item/ship-prices')
    etag = res.headers.get('ETag')
    assert etag and 'max-age' in res.headers['Cache-Control']
    assert client.get('/item/ship-prices', headers={'If-None-Match': etag}).status_code == 304
    # 版本沒變時資料庫改了也還是舊的（快取）；同步一次（run_id 變了）就重組
    db.ship_sale_history.insert_one({'_id': 'Idris', 'name': 'Idris', 'periods': []})
    assert len(client.get('/item/ship-prices').get_json()['data']) == 1
    db.sync_jobs.update_one({'_id': 'ccu'}, {'$set': {'last_run_id': 'r9'}})
    res2 = client.get('/item/ship-prices')
    assert len(res2.get_json()['data']) == 2 and res2.headers['ETag'] != etag
    d = client.get('/item/ship-prices/detail?key=Galaxy')
    assert d.get_json()['data']['vehicle_uuid'] == 'v-gal' and 'max-age' in d.headers['Cache-Control']
    ccu._list_cache.update(version=None, rows=None)
