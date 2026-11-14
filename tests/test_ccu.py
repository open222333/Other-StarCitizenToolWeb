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
