"""維克洛交易（src/models/wikelo.py、src/scdata.py 的 map_wikelo_trade、tasks/scdata_sync.py 的 _sync_wikelo）。

上游形狀取自 2026-11 實際打 Star Citizen Wiki API `/missions/<uuid>` 的回應（Asgard Fight Mod）。
"""
from datetime import datetime

import pytest

from src.models import wikelo
from src.mongo import get_db
from src.scdata import ScDataError, is_wikelo_mission, map_wikelo_trade

FAVOR = '3b1cf59f-1e6b-4a91-9edb-f8c5ddf791ae'
ASGARD = 'afae3e97-7f7e-45a3-9f3b-fe268479775b'

ROW = {
    'uuid': '5bf19672-f057-4ccf-bdd4-d309edfeea15', 'title': 'Asgard Fight Mod', 'mission_giver': 'Wikelo',
    'faction': {'name': 'Wikelo Emporium', 'uuid': '5f442fdd-15cc-4f62-bd10-fce2023f4d0c'},
    'reward_scope': 'Other', 'has_prerequisites': True,
}
DETAIL = {
    'uuid': ROW['uuid'], 'title': 'Asgard Fight Mod', 'description': 'Bring things, get ship.',
    'mission_type': 'Collection', 'once_only': False, 'shareable': False, 'game_version': '4.4.0-LIVE',
    'hauling_orders': [
        {'kind': 'Entity', 'name': 'Wikelo Favor', 'uuid': FAVOR, 'items': [], 'max_scu': None, 'min_scu': None,
         'max_amount': 50, 'min_amount': 50, 'max_container_size': -1},
        {'kind': 'Entity', 'name': 'ASD Secure Drive', 'uuid': 'asd-1', 'min_amount': 3, 'max_amount': 3},
        {'kind': 'Resource', 'name': 'Quantainium', 'uuid': 'quan-1', 'min_amount': None, 'max_amount': None,
         'min_scu': 24, 'max_scu': 24},
    ],
    'reward_items': [{'name': 'Anvil Asgard Wikelo War Special', 'uuid': ASGARD, 'amount': 1, 'send_to_home': False}],
    'reward_groups': [{'group_index': 0, 'items': [{'name': 'ignored', 'uuid': 'x', 'amount': 1}]}],
    'reputation_gained': [{'tier': None, 'scope': 'Wikelo', 'amount': 250, 'faction': 'Wikelo Emporium',
                           'faction_uuid': '5f442fdd-15cc-4f62-bd10-fce2023f4d0c'}],
    'prerequisite_groups': [{'required_count': 1, 'excluded_tags': [],
                             'required_tags': [{'name': 'IntroDone', 'uuid': '87e124b5'}],
                             'missions': [{'uuid': '028d7a46', 'title': 'Wikelo Arrive to System',
                                           'mission_type': 'Collection'}]}],
}


def test_is_wikelo_mission():
    assert is_wikelo_mission(ROW)
    assert is_wikelo_mission({'faction': {'name': 'Wikelo Emporium'}})
    assert not is_wikelo_mission({'mission_giver': 'Vaughn', 'faction': {'name': 'Vaughn'}})


def test_map_wikelo_trade():
    doc = map_wikelo_trade({**ROW, **DETAIL})
    assert doc['_id'] == ROW['uuid'] and doc['title'] == 'Asgard Fight Mod'
    assert doc['requirements'][0] == {'item_uuid': FAVOR, 'name': 'Wikelo Favor', 'kind': 'Entity', 'amount': 50,
                                      'max_amount': None, 'min_scu': None, 'max_scu': None}
    assert doc['requirements'][2]['min_scu'] == 24 and doc['requirements'][2]['amount'] is None
    # 有 reward_items 就不用 reward_groups
    assert doc['rewards'] == [{'item_uuid': ASGARD, 'name': 'Anvil Asgard Wikelo War Special', 'amount': 1}]
    assert doc['reputation_amount'] == 250
    g = doc['prerequisite_groups'][0]
    assert g['required_tags'] == ['IntroDone'] and doc['prerequisite_uuids'] == ['028d7a46']
    assert map_wikelo_trade({'title': 'no uuid'}) is None


def test_map_wikelo_rewards_fall_back_to_groups():
    doc = map_wikelo_trade({**DETAIL, 'reward_items': []})
    assert doc['rewards'] == [{'item_uuid': 'x', 'name': 'ignored', 'amount': 1}]


def _run(monkeypatch, rows, detail, run_id='r1'):
    from tasks import scdata_sync
    monkeypatch.setattr(scdata_sync, 'SCDATA_REQUEST_DELAY', 0)
    calls = []

    def fake_rows(client, resource, params=None):
        calls.append((resource, params))
        return iter(rows)
    monkeypatch.setattr(scdata_sync, 'wiki_rows', fake_rows)
    monkeypatch.setattr(scdata_sync, 'wiki_detail', detail)
    return scdata_sync._sync_wikelo(None, run_id, datetime.utcnow()), calls


def test_sync_wikelo(app, monkeypatch):
    other = {'uuid': 'v-1', 'title': 'Not Wikelo', 'mission_giver': 'Vaughn', 'faction': {'name': 'Vaughn'}}
    stats, calls = _run(monkeypatch, [ROW, other], lambda client, resource, uuid: DETAIL)
    assert calls == [('missions', {'filter[mission_giver]': 'Wikelo'})]
    assert stats['seen'] == 1 and stats['retired'] == 0
    doc = get_db()['wikelo_trades'].find_one({'_id': ROW['uuid']})
    assert doc['is_current'] and doc['requirements'][1]['name'] == 'ASD Secure Drive'

    # 下一輪少了這筆（另一筆頂上）→ 下架
    row2 = {**ROW, 'uuid': 'w-2', 'title': 'Other Trade'}
    stats, _ = _run(monkeypatch, [row2], lambda client, resource, uuid: {**DETAIL, 'uuid': uuid}, run_id='r2')
    assert stats['retired'] == 1
    assert get_db()['wikelo_trades'].find_one({'_id': ROW['uuid']})['is_current'] is False


def test_sync_wikelo_fails_whole_run_when_detail_missing(app, monkeypatch):
    _run(monkeypatch, [ROW], lambda client, resource, uuid: DETAIL)
    with pytest.raises(ScDataError):
        _run(monkeypatch, [ROW, {**ROW, 'uuid': 'w-2'}], lambda client, resource, uuid: DETAIL if uuid == ROW['uuid'] else None,
             run_id='r2')
    assert get_db()['wikelo_trades'].find_one({'_id': ROW['uuid']})['is_current'] is True


def test_sync_wikelo_guard_empty(app, monkeypatch):
    _run(monkeypatch, [ROW], lambda client, resource, uuid: DETAIL)
    with pytest.raises(ScDataError):
        _run(monkeypatch, [], lambda *a: DETAIL, run_id='r2')


@pytest.fixture
def trades(app):
    wikelo.save([map_wikelo_trade({**ROW, **DETAIL}),
                 map_wikelo_trade({**ROW, **DETAIL, 'uuid': 'w-hidden', 'title': 'Hidden Trade'})],
                'r1', datetime.utcnow())
    get_db()['item_master'].insert_one({'_id': FAVOR, 'name': 'Wikelo Favor', 'name_zh': '維克洛人情', 'type': 'Misc'})
    get_db()['mission_master'].insert_one({'_id': 'w-hidden', 'title': 'Hidden Trade', 'player_visible': False})


def test_list_attaches_names_and_hides(trades):
    rows = wikelo.list_all()
    assert [r['_id'] for r in rows] == [ROW['uuid'], 'w-hidden']
    assert rows[0]['requirements'][0]['name_zh'] == '維克洛人情' and 'raw' not in rows[0]
    assert [r['_id'] for r in wikelo.list_all(visible_only=True)] == [ROW['uuid']]
    assert [r['_id'] for r in wikelo.list_all('人情')] == [ROW['uuid'], 'w-hidden']
    assert [r['_id'] for r in wikelo.list_all('asgard')] == [ROW['uuid'], 'w-hidden']
    assert wikelo.list_all('nothing') == []
    assert wikelo.get('w-hidden', visible_only=True) is None and wikelo.get('w-hidden')['title'] == 'Hidden Trade'


def test_wikelo_endpoints(client, trades):
    body = client.get('/mission/wikelo').get_json()
    assert body['success'] and body['total'] == 1 and body['data'][0]['rewards'][0]['amount'] == 1
    assert client.get(f'/mission/wikelo/{ROW["uuid"]}').get_json()['data']['title'] == 'Asgard Fight Mod'
    assert client.get('/mission/wikelo/w-hidden').status_code == 404


def test_index_and_for_item(client, trades):
    doc = get_db()['wikelo_trades'].find_one({'_id': ROW['uuid']})
    assert doc['requirement_uuids'] == [FAVOR, 'asd-1', 'quan-1'] and doc['reward_uuids'] == [ASGARD]
    assert doc['reward_names'] == ['anvil asgard wikelo war special']
    idx = wikelo.index()
    assert idx['uuids'][FAVOR] == {'reward': 0, 'requirement': 2} and idx['names']['anvil asgard wikelo war special'] == 2
    assert wikelo.index(visible_only=True)['uuids'][FAVOR]['requirement'] == 1
    hit = wikelo.for_item([FAVOR])
    assert hit['reward'] == [] and len(hit['requirement']) == 2 and 'reward_uuids' not in hit['requirement'][0]
    assert len(wikelo.for_item(names=['Anvil Asgard Wikelo War Special'])['reward']) == 2
    assert wikelo.for_item() == {'reward': [], 'requirement': []}
    body = client.get(f'/mission/wikelo/by-item?uuid={ASGARD}').get_json()['data']
    assert [r['_id'] for r in body['reward']] == [ROW['uuid']] and body['requirement'] == []
    assert client.get('/mission/wikelo/index').get_json()['data']['uuids'][FAVOR]['requirement'] == 1


def test_attach_source_and_acquire(app, trades):
    get_db()['vehicle_master'].insert_one({'_id': ASGARD, 'name': 'Asgard Wikelo War Special', 'name_zh': '阿斯加德'})
    get_db()['blueprint_master'].insert_one({'_id': 'bp-fav', 'output_item_uuid': FAVOR, 'is_current': True})
    row = wikelo.get(ROW['uuid'])
    fav = row['requirements'][0]
    assert fav['source'] == 'item' and fav['blueprint'] == 'bp-fav' and fav['buyable'] is False
    assert fav['master_name'] == 'Wikelo Favor'
    assert row['requirements'][1]['source'] is None and 'buyable' not in row['requirements'][1]
    assert row['rewards'][0]['source'] == 'vehicle' and row['rewards'][0]['name_zh'] == '阿斯加德'


def test_title_zh_from_mission_master_and_name_fallback(app, trades, monkeypatch):
    get_db()['mission_master'].update_one({'_id': ROW['uuid']}, {'$set': {'title_zh': '阿斯加德戰鬥改裝'}}, upsert=True)
    from src import sc_zh
    monkeypatch.setattr(sc_zh, 'item_name_zh', lambda en_name='', class_name='', lang=None: '固態硬碟' if en_name == 'ASD Secure Drive' else None)
    monkeypatch.setattr(sc_zh, 'vehicle_name_zh', lambda **kw: None)
    row = wikelo.get(ROW['uuid'])
    assert row['title_zh'] == '阿斯加德戰鬥改裝'
    assert row['requirements'][1]['name_zh'] == '固態硬碟'
    assert row['requirements'][0]['name_zh'] == '維克洛人情'
