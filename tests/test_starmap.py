"""星圖地點資料庫：映射（含中文）、上下層整理、查詢、同步項目。

資料形狀取自 scunpacked-data 的 starmap.json（2026-10 快照）。
"""
from datetime import datetime

import pytest

from src.models.starmap import Starmap
from src.mongo import get_db
from src.scdata import map_starmap

STAR = {'UUID': 'sys-stanton', 'Name': 'Stanton', 'Description': 'A class-G main sequence star.',
        'ParentUUID': None, 'Type': {'Name': 'Star', 'Classification': 'Star'},
        'Jurisdiction': {'Name': 'UEE'}, 'Amenities': []}
PLANET = {'UUID': 'p-hurston', 'Name': 'Hurston', 'Description': 'A wealth of ore is mined on Hurston.',
          'ParentUUID': 'sys-stanton', 'Type': {'Name': 'Planet', 'ValidQuantumTravelDestination': True},
          'Jurisdiction': {'Name': 'Hurston Dynamics'}, 'Amenities': []}
OUTPOST = {'UUID': 'o-lorville', 'Name': 'Lorville', 'Description': '<= UNINITIALIZED =>',
           'ParentUUID': 'p-hurston', 'Type': {'Name': 'Outpost_InvalidQT'},
           'Jurisdiction': None, 'RespawnLocationType': 'Hospital',
           'Amenities': [{'UUID': 'a1', 'Name': 'Hangar L', 'DisplayName': 'Hangar (L)'},
                         {'UUID': 'a2', 'Name': 'Vehicle Services', 'DisplayName': 'Vehicle Services'}],
           'LocationHierarchyTag': {'Name': 'Stanton1'}}
UNNAMED = {'UUID': 'x-1', 'Name': '<= UNINITIALIZED =>', 'ParentUUID': 'p-hurston',
           'Type': {'Name': 'PointOfInterest'}, 'Amenities': []}


@pytest.fixture
def zh(seed_translations):
    seed_translations({
        'Stanton': ('Stanton', '斯坦頓'),
        'Stanton1': ('Hurston', '赫斯頓'),
        'Stanton1_Desc': ('A wealth of ore is mined on Hurston.', '赫斯頓開採大量礦石。'),
        'Stanton1_Lorville': ('Lorville', '羅威爾'),
        'Maps_Amenities_HangarL': ('Hangar (L)', '機庫（L）'),
        'Maps_Amenities_VehicleServices': ('Vehicle Services', '載具服務'),
        'Markers_Subtext_Planet': ('Planet', '星球'),
        'Markers_Subtext_Outpost': ('Outpost', '前哨站'),
        'Markers_Subtext_Star': ('Star', '星'),
        'Jurisdictions_Name_001': ('UEE', '地球聯合帝國'),
        'Human_Surnames_1': ('Green', '綠色的'),   # 不是地點的條目不能被拿來當地名
    })


def _sync(rows):
    db = get_db()
    for r in rows:
        doc = map_starmap(r)
        db['starmap_master'].update_one({'_id': doc['_id']}, {'$set': {**doc, 'is_current': True}}, upsert=True)
    Starmap.rebuild_hierarchy()
    Starmap.apply_storage()


def test_map_starmap_translates(zh):
    doc = map_starmap(OUTPOST)
    assert doc['name_zh'] == '羅威爾'
    assert doc['description'] == '' and doc['description_zh'] is None, '<= UNINITIALIZED => 當成空的'
    assert doc['type'] == 'Outpost_InvalidQT' and doc['type_zh'] == '前哨站', '變體退回基本類型'
    assert doc['amenities'] == [{'name': 'Hangar (L)', 'name_zh': '機庫（L）'},
                                {'name': 'Vehicle Services', 'name_zh': '載具服務'}]
    assert doc['respawn_type'] == 'Hospital' and doc['hierarchy_tag'] == 'Stanton1'
    planet = map_starmap(PLANET)
    assert planet['description_zh'] == '赫斯頓開採大量礦石。' and planet['quantum_travel'] is True
    assert map_starmap(STAR)['jurisdiction_zh'] == '地球聯合帝國'
    assert map_starmap(UNNAMED)['is_named'] is False
    assert map_starmap({**PLANET, 'Name': 'Green'})['name_zh'] is None
    assert map_starmap({}) is None


def test_manual_starmap_types(seed_translations):
    seed_translations({})   # 只寫人工條目
    from src.sc_zh import starmap_type_zh
    assert starmap_type_zh('PointOfInterest') == '興趣點'
    assert starmap_type_zh('JumpPoint') == '跳躍點'


def test_hierarchy_and_queries(zh):
    _sync([STAR, PLANET, OUTPOST, UNNAMED])
    lorville = get_db()['starmap_master'].find_one({'_id': 'o-lorville'})
    assert lorville['parent_name'] == 'Hurston' and lorville['parent_name_zh'] == '赫斯頓'
    assert lorville['system_name'] == 'Stanton' and lorville['path'] == ['Stanton', 'Hurston']
    assert lorville['path_zh'] == ['斯坦頓', '赫斯頓']
    assert get_db()['starmap_master'].find_one({'_id': 'sys-stanton'})['system_name'] == 'Stanton'

    rows, total = Starmap.list_all()
    assert total == 3 and [r['_id'] for r in rows] == ['sys-stanton', 'p-hurston', 'o-lorville'], '上下層排在一起'
    assert 'raw' not in rows[0]
    assert Starmap.list_all(named_only=False)[1] == 4
    assert [r['_id'] for r in Starmap.list_all(types=['Outpost_InvalidQT', 'Moon'])[0]] == ['o-lorville']
    assert [r['_id'] for r in Starmap.list_all(amenities=['Hangar (L)'])[0]] == ['o-lorville']
    assert [r['_id'] for r in Starmap.list_all(query='羅威')[0]] == ['o-lorville']
    assert [r['_id'] for r in Starmap.list_all(query='hurston')[0]] == ['p-hurston', 'o-lorville'], '上層名稱也比對'
    assert Starmap.list_all(systems=['Stanton'])[1] == 3

    detail = Starmap.get('p-hurston')
    assert sorted(c['_id'] for c in detail['children']) == ['o-lorville', 'x-1']
    facets = Starmap.facets()
    assert {f['value']: f['count'] for f in facets['types']} == {'Outpost_InvalidQT': 1, 'Planet': 1, 'Star': 1}
    assert facets['systems'][0]['value'] == 'Stanton' and facets['systems'][0]['label_zh'] == '斯坦頓'
    assert {a['value'] for a in facets['amenities']} == {'Hangar (L)', 'Vehicle Services'}


def test_hierarchy_survives_cycles(app):
    _sync([{**PLANET, 'ParentUUID': 'o-lorville'}, {**OUTPOST, 'ParentUUID': 'p-hurston'}])
    assert get_db()['starmap_master'].find_one({'_id': 'o-lorville'})['parent_name'] == 'Hurston'


def test_refresh_translations(app, seed_translations):
    _sync([STAR, PLANET])
    assert get_db()['starmap_master'].find_one({'_id': 'p-hurston'})['name_zh'] is None
    seed_translations({'Stanton1': ('Hurston', '赫斯頓'), 'Stanton': ('Stanton', '斯坦頓')})
    from src.models import translation as T
    T.clear_cache()
    assert Starmap.refresh_translations() == 2
    row = get_db()['starmap_master'].find_one({'_id': 'p-hurston'})
    assert row['name_zh'] == '赫斯頓' and row['system_name_zh'] == '斯坦頓'


def test_locations_sync_job(app, monkeypatch):
    """「地點」同步項目：抓 starmap.json、寫入、整理上下層；跟礦物分開。"""
    import tasks.scdata_sync as sync_mod
    fetched = []

    def fake_fetch(client, path, expect=list):
        fetched.append(path)
        return [STAR, PLANET, OUTPOST]
    monkeypatch.setattr(sync_mod, 'fetch_scunpacked_rows', fake_fetch)
    result = sync_mod._do_sync(jobs=['locations'])
    assert result['ok'] is True and fetched == ['starmap.json']
    assert get_db()['starmap_master'].find_one({'_id': 'o-lorville'})['system_name'] == 'Stanton'
    lorville = get_db()['starmap_master'].find_one({'_id': 'o-lorville'})
    assert lorville['can_store'] is True and lorville['has_hangar'] is True
    assert get_db()['starmap_master'].find_one({'_id': 'p-hurston'})['can_store'] is False
    from src.models.sync_schedule import SyncJobs
    assert SyncJobs.get('locations')['last_ok'] is True


def test_api(client, auth_headers, zh):
    _sync([STAR, PLANET, OUTPOST])
    body = client.get('/starmap/?type=Planet&type=Star', headers=auth_headers).get_json()
    assert body['total'] == 2
    assert client.get('/starmap/facets', headers=auth_headers).get_json()['success'] is True
    assert client.get('/starmap/o-lorville', headers=auth_headers).get_json()['data']['name_zh'] == '羅威爾'
    assert client.get('/starmap/nope', headers=auth_headers).status_code == 404


def test_features_from_amenities():
    from src.models.starmap import FEATURE_KEYS, features_from_amenities
    f = features_from_amenities(['Hangar (XL)', 'Hangar (S)', 'Buy Weapons', 'Buy/Rent Vehicles', 'Landing Pad (M)'])
    assert f['has_hangar'] and f['has_landing_pad'] and f['shop_weapons']
    assert f['shop_vehicles'] and f['rent_vehicles'], '買／租載具兩個屬性都算'
    assert f['hangar_sizes'] == ['S', 'XL'] and f['landing_pad_sizes'] == ['M']
    assert f['can_store_auto'] is True and f['has_refinery'] is False
    empty = features_from_amenities([])
    assert all(empty[k] is False for k in FEATURE_KEYS) and empty['can_store_auto'] is False
    assert features_from_amenities(['Docking'])['can_store_auto'] is True
    assert features_from_amenities(['Clinic', 'Food Court'])['can_store_auto'] is False
    doc = map_starmap({**OUTPOST, 'Amenities': OUTPOST['Amenities'] * 2})
    assert len(doc['amenities']) == 2, '重複的設施只留一個'
    assert doc['has_hangar'] is True and doc['has_vehicle_services'] is True and doc['can_store_auto'] is True


def test_storage_override_survives_resync(zh):
    _sync([STAR, PLANET, OUTPOST])
    assert [r['_id'] for r in Starmap.list_all(can_store=True)[0]] == ['o-lorville']
    assert Starmap.list_all(can_store=False)[1] == 2
    assert [r['_id'] for r in Starmap.list_all(features=['has_hangar', 'has_vehicle_services'])[0]] == ['o-lorville']
    assert Starmap.list_all(features=['has_hangar', 'shop_weapons'])[1] == 0, '屬性要全部都有'

    row = Starmap.set_storage_override('p-hurston', True, 'admin')
    assert row['can_store'] is True and row['can_store_override'] is True and row['can_store_updated_by'] == 'admin'
    Starmap.set_storage_override('o-lorville', False, 'admin')
    _sync([STAR, PLANET, OUTPOST])   # 重新同步不會蓋掉手動設定
    col = get_db()['starmap_master']
    assert col.find_one({'_id': 'p-hurston'})['can_store'] is True
    assert col.find_one({'_id': 'o-lorville'})['can_store'] is False
    facets = Starmap.facets()
    assert facets['can_store'] == {'yes': 1, 'no': 2, 'override': 2}
    hangar = next(f for f in facets['features'] if f['value'] == 'has_hangar')
    assert hangar['count'] == 1 and hangar['label'] == 'Hangar' and hangar['storage'] is True

    assert Starmap.set_storage_override('o-lorville', None)['can_store'] is True, '回到自動'
    assert Starmap.set_storage_override('nope', True) is None
    with pytest.raises(ValueError):
        Starmap.set_storage_override('o-lorville', 'yes')


def test_feature_labels_zh(zh):
    from src.sc_zh import starmap_feature_zh
    assert starmap_feature_zh('has_hangar', ['Hangar (S)', 'Hangar (L)']) == '機庫'
    assert starmap_feature_zh('has_vehicle_services', ['Vehicle Services']) == '載具服務'
    assert starmap_feature_zh('has_docking', ['Docking']) == '對接口', '人工條目優先'


def test_storage_api(client, auth_headers, zh):
    _sync([STAR, PLANET, OUTPOST])
    assert client.get('/starmap/?can_store=1', headers=auth_headers).get_json()['total'] == 1
    assert client.get('/starmap/?can_store=0', headers=auth_headers).get_json()['total'] == 2
    assert client.get('/starmap/?feature=has_hangar&feature=bogus', headers=auth_headers).get_json()['total'] == 1
    res = client.put('/starmap/p-hurston/storage', json={'can_store': True}, headers=auth_headers)
    assert res.status_code == 200 and res.get_json()['data']['can_store'] is True
    assert client.put('/starmap/p-hurston/storage', json={'can_store': None}, headers=auth_headers) \
        .get_json()['data']['can_store'] is False
    assert client.put('/starmap/p-hurston/storage', json={'can_store': 'x'}, headers=auth_headers).status_code == 400
    assert client.put('/starmap/p-hurston/storage', json={}, headers=auth_headers).status_code == 400
    assert client.put('/starmap/nope/storage', json={'can_store': True}, headers=auth_headers).status_code == 404


def test_storage_locations(client, zh):
    """庫存地點下拉：只列可存放的、同名只留一個、不需要 token。"""
    dup = {**OUTPOST, 'UUID': 'o-lorville-2', 'ParentUUID': 'sys-stanton'}
    _sync([STAR, PLANET, OUTPOST, dup])
    Starmap.set_storage_override('p-hurston', True)
    rows = Starmap.storage_locations()
    assert [r['name'] for r in rows] == ['Hurston', 'Lorville']
    lorville = rows[1]
    assert lorville['name_zh'] == '羅威爾' and lorville['system'] == 'Stanton' and lorville['parent'] == 'Hurston'
    body = client.get('/starmap/storage-locations').get_json()
    assert body['success'] is True and [r['name'] for r in body['data']] == ['Hurston', 'Lorville']
