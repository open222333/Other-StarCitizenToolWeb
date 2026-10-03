"""遊戲資料「玩家頁面顯示」：自動判斷、手動設定（同步不會蓋掉）、玩家端過濾、後台 API。"""
import pytest

from src.models import visibility as V
from src.mongo import get_db


@pytest.mark.parametrize('name, hidden', [
    ('Laser Cannon S1', False), ('Asteroid (C-Type)', False), ("Grey's Shiv", False),
    ('Tempest Rifle', False), ('Testudo Armor', False), ('Devastator Shotgun', False),
    ('<= PLACEHOLDER =>', True), ('PLACEHOLDER', True), ('[PH] Bounty Hunt', True),
    ('PH - Cargo Run', True), ('WIP\xa0Refinery_0001', True), ('Item TBD', True),
    ('Pyro4 Outpost Col Mcr Test Indy 001', True), ('DO NOT USE Helmet', True),
    ('@item_Name_Foo', True), ('ActorLootbox_Prelude_Vanduul', True), ('', True), (None, True),
])
def test_unfinished_reason(name, hidden):
    assert (V.unfinished_reason(name) is not None) is hidden


def test_auto_reason_uses_codes_and_flags():
    assert V.auto_reason('mining_deposits', {'deposit_name': 'Shale Deposit', 'key': 'MineableRock_test_Gold'})
    assert V.auto_reason('mining_deposits', {'deposit_name': 'Shale Deposit', 'key': 'MineableRock_Shale'}) is None
    assert V.auto_reason('vehicles', {'name': 'RSI Meteor', 'class_name': 'RSI_Meteor_TEMP_LaserRepeater'})
    assert V.auto_reason('missions', {'title': 'Bounty', 'work_in_progress': True}) == '上游標記開發中'
    assert V.auto_reason('missions', {'title': 'Bounty', 'not_for_release': True}) == '上游標記不公開'
    assert V.auto_reason('missions', {'title': 'Bounty', 'released': False}) is None


def _seed_blueprints():
    get_db()['blueprint_master'].insert_many([
        {'_id': 'bp-ok', 'name': 'Laser Cannon S1', 'name_lower': 'laser cannon s1', 'is_current': True},
        {'_id': 'bp-ph', 'name': '<= PLACEHOLDER =>', 'name_lower': '<= placeholder =>', 'is_current': True},
        {'_id': 'bp-test', 'name': 'Medical Pen', 'name_lower': 'medical pen', 'key': 'BP_Test_Pen',
         'is_current': True},
    ])


def test_apply_and_override_survive_resync(app):
    _seed_blueprints()
    assert V.apply('blueprints') == 3
    col = get_db()['blueprint_master']
    assert col.find_one({'_id': 'bp-ph'})['player_visible'] is False
    assert col.find_one({'_id': 'bp-ph'})['player_hidden_reason'] == '佔位文字'
    assert col.find_one({'_id': 'bp-ok'})['player_visible'] is True

    state = V.set_override('blueprints', 'bp-test', True, 'admin')
    assert state['player_visible'] is True and state['player_visible_auto'] is False
    V.set_override('blueprints', 'bp-ok', False, 'admin')
    # 模擬重新同步：mapper 用 $set 寫回整份（沒有顯示欄位），再整理一次
    col.update_one({'_id': 'bp-ok'}, {'$set': {'name': 'Laser Cannon S1', 'is_current': True}})
    assert V.apply('blueprints') == 0
    assert col.find_one({'_id': 'bp-test'})['player_visible'] is True
    assert col.find_one({'_id': 'bp-ok'})['player_visible'] is False
    # 主檔整個重建，手動設定還在
    col.delete_many({})
    _seed_blueprints()
    V.apply('blueprints')
    assert col.find_one({'_id': 'bp-test'})['player_visible'] is True

    assert V.set_override('blueprints', 'bp-test', None)['player_visible'] is False, '回到自動'
    assert V.set_override('blueprints', 'nope', True) is None
    with pytest.raises(ValueError):
        V.set_override('blueprints', 'bp-ok', 'yes')
    with pytest.raises(ValueError):
        V.set_override('nope', 'bp-ok', True)


@pytest.fixture
def player_headers(client):
    client.post('/player/register', json={'nickname': 'Pilot', 'star_citizen_id': 'Pilot',
                                          'password': 'pw-123456'})
    login = client.post('/player/login', json={'star_citizen_id': 'Pilot', 'password': 'pw-123456'})
    return {'Authorization': f"Bearer {login.get_json()['token']}"}


def test_player_sees_only_visible_blueprints(client, auth_headers, player_headers):
    _seed_blueprints()
    V.apply('blueprints')
    ids = lambda body: sorted(r['_id'] for r in body['data'])
    assert ids(client.get('/blueprint/master', headers=player_headers).get_json()) == ['bp-ok']
    assert ids(client.get('/blueprint/master', headers=auth_headers).get_json()) == ['bp-ok', 'bp-ph', 'bp-test']
    assert ids(client.get('/blueprint/master?player_visible=0', headers=auth_headers).get_json()) == ['bp-ph', 'bp-test']
    assert ids(client.get('/blueprint/master?player_visible=0', headers=player_headers).get_json()) == ['bp-ok'], \
        '玩家不能用篩選參數看到不顯示的'
    assert ids(client.get('/blueprint/master/search?q=medical', headers=player_headers).get_json()) == []
    assert ids(client.get('/blueprint/master/search?q=medical', headers=auth_headers).get_json()) == ['bp-test']
    row = client.get('/blueprint/master?q=placeholder', headers=auth_headers).get_json()['data'][0]
    assert row['player_visible'] is False and row['player_hidden_reason'] == '佔位文字'


def test_missions_hidden_for_players(client, auth_headers, player_headers):
    get_db()['mission_master'].insert_many([
        {'_id': 'm-1', 'title': 'Bounty', 'title_lower': 'bounty', 'is_current': True, 'blueprint_uuids': ['bp-1']},
        {'_id': 'm-2', 'title': 'Cargo', 'title_lower': 'cargo', 'is_current': True, 'blueprint_uuids': ['bp-1'],
         'work_in_progress': True},
    ])
    V.apply('missions')
    assert [m['_id'] for m in client.get('/mission/for-blueprint/bp-1', headers=player_headers)
            .get_json()['data']] == ['m-1']
    assert len(client.get('/mission/for-blueprint/bp-1', headers=auth_headers).get_json()['data']) == 2
    assert client.get('/mission/', headers=player_headers).get_json()['total'] == 1
    from src.models.mission import Mission
    assert Mission.counts_for_blueprints(['bp-1'], visible_only=True) == {'bp-1': 1}


def test_mining_hides_deposits_and_minerals(client, auth_headers, player_headers):
    get_db()['mining_deposit_master'].insert_many([
        {'_id': 'd-1', 'deposit_name': 'Shale Deposit', 'deposit_name_lower': 'shale deposit', 'key': 'Rock_Shale',
         'is_current': True, 'parts': [{'resource_key': 'gold', 'resource_name': 'Gold'},
                                       {'resource_key': 'ph', 'resource_name': '<= PLACEHOLDER =>'}]},
        {'_id': 'd-2', 'deposit_name': 'Shale Deposit', 'deposit_name_lower': 'shale deposit',
         'key': 'MineableRock_test_Gold', 'is_current': True, 'parts': [{'resource_key': 'gold'}]},
    ])
    get_db()['mining_location_master'].insert_one(
        {'_id': 'l-1', 'location_name': 'Aberdeen', 'location_name_lower': 'aberdeen', 'is_current': True,
         'groups': [{'group_name': 'A', 'deposits': [{'resource_uuid': 'd-1'}, {'resource_uuid': 'd-2'}]},
                    {'group_name': 'B', 'deposits': [{'resource_uuid': 'd-2'}]}]})
    V.apply_for_job('mining')
    deps = client.get('/mining/deposits', headers=player_headers).get_json()['data']
    assert [d['_id'] for d in deps] == ['d-1'] and [p['resource_key'] for p in deps[0]['parts']] == ['gold']
    assert len(client.get('/mining/deposits', headers=auth_headers).get_json()['data']) == 2
    loc = client.get('/mining/locations', headers=player_headers).get_json()['data'][0]
    assert [g['group_name'] for g in loc['groups']] == ['A'] and len(loc['groups'][0]['deposits']) == 1

    # 礦物手動設定
    res = client.put('/item/visibility/minerals/gold', json={'player_visible': False}, headers=auth_headers)
    assert res.status_code == 200 and res.get_json()['data']['player_visible'] is False
    assert client.get('/mining/deposits', headers=player_headers).get_json()['data'][0]['parts'] == []
    states = client.get('/item/visibility/minerals', headers=auth_headers).get_json()['data']
    assert states['gold']['player_visible_override'] is False and states['ph']['player_visible'] is False


def test_visibility_api(client, auth_headers, player_headers):
    _seed_blueprints()
    V.apply('blueprints')
    url = '/item/visibility/blueprints/bp-ph'
    assert client.put(url, json={'player_visible': True}, headers=player_headers).status_code in (401, 403)
    res = client.put(url, json={'player_visible': True}, headers=auth_headers)
    assert res.status_code == 200 and res.get_json()['data']['player_visible_override'] is True
    assert 'bp-ph' in [r['_id'] for r in client.get('/blueprint/master', headers=player_headers).get_json()['data']]
    assert client.put(url, json={'player_visible': None}, headers=auth_headers).get_json()['data']['player_visible'] is False
    assert client.put(url, json={}, headers=auth_headers).status_code == 400
    assert client.put('/item/visibility/nope/x', json={'player_visible': True}, headers=auth_headers).status_code == 400
    assert client.put('/item/visibility/blueprints/nope', json={'player_visible': True},
                      headers=auth_headers).status_code == 404


def test_sync_job_applies_visibility(app, monkeypatch):
    import tasks.scdata_sync as sync_mod
    rows = [{'UUID': 's-1', 'Name': 'Lorville', 'Type': {'Name': 'City'}, 'Amenities': []},
            {'UUID': 's-2', 'Name': 'WIP Refinery_0001', 'Type': {'Name': 'Outpost'}, 'Amenities': []}]
    monkeypatch.setattr(sync_mod, 'fetch_scunpacked_rows', lambda client, path, expect=list: rows)
    assert sync_mod._do_sync(jobs=['locations'])['ok'] is True
    col = get_db()['starmap_master']
    assert col.find_one({'_id': 's-1'})['player_visible'] is True
    assert col.find_one({'_id': 's-2'})['player_visible'] is False
