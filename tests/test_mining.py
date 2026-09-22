"""礦物回波參考表的模型與 view 測試（src/models/mining.py, app/mining/view.py）。

這兩個 collection 是唯讀的（由 tasks/scdata_sync.py 單向寫入），所以測試
直接用 get_db() 塞資料，不像 Blueprint/Player 那樣有 .create()。
"""
from src.models.mining import MiningDeposit, MiningLocation
from src.mongo import get_db


def _insert_deposit(db, _id, deposit_name, tier='common', is_current=True, parts=None):
    db['mining_deposit_master'].insert_one({
        '_id': _id, 'key': _id, 'deposit_name': deposit_name,
        'deposit_name_lower': deposit_name.lower(), 'tier': tier,
        'min_distinct_elements': 1,
        'parts': parts or [{'resource_key': 'Ore_Gold', 'resource_name': 'Gold (Ore)',
                            'min_percentage': 20, 'max_percentage': 50, 'probability': 0.3}],
        'is_current': is_current,
    })


def _insert_location(db, _id, location_name, system='Stanton', is_current=True,
                     deposit_uuids=None):
    db['mining_location_master'].insert_one({
        '_id': _id, 'provider_name': _id, 'system': system,
        'location_name': location_name, 'location_name_lower': location_name.lower(),
        'groups': [{
            'group_name': 'g1', 'group_probability': 0.5,
            'deposits': [{'resource_uuid': u, 'relative_probability': 0.5}
                        for u in (deposit_uuids or [])],
        }],
        'is_current': is_current,
    })


# ═══════════════════════════════════════════════════════════
#  模型層
# ═══════════════════════════════════════════════════════════

def test_mining_deposit_list_all_filters_is_current(app):
    db = get_db()
    _insert_deposit(db, 'd1', 'Granite Deposit')
    _insert_deposit(db, 'd2', 'Old Deposit', is_current=False)

    rows = MiningDeposit.list_all()

    assert [r['_id'] for r in rows] == ['d1']
    assert 'raw' not in rows[0]


def test_mining_deposit_list_all_sorted_by_name(app):
    db = get_db()
    _insert_deposit(db, 'd1', 'Zebra Deposit')
    _insert_deposit(db, 'd2', 'Alpha Deposit')

    rows = MiningDeposit.list_all()

    assert [r['deposit_name'] for r in rows] == ['Alpha Deposit', 'Zebra Deposit']


def test_mining_deposit_by_ids_batch_lookup(app):
    db = get_db()
    _insert_deposit(db, 'd1', 'Granite Deposit', tier='common')
    _insert_deposit(db, 'd2', 'Quantainium Deposit', tier='rare')

    result = MiningDeposit.by_ids(['d1', 'd2', 'missing', None, ''])

    assert result == {
        'd1': {'deposit_name': 'Granite Deposit', 'tier': 'common'},
        'd2': {'deposit_name': 'Quantainium Deposit', 'tier': 'rare'},
    }
    assert MiningDeposit.by_ids([]) == {}


def test_mining_deposit_count_current(app):
    db = get_db()
    _insert_deposit(db, 'd1', 'A')
    _insert_deposit(db, 'd2', 'B', is_current=False)

    assert MiningDeposit.count_current() == 1


def test_mining_location_list_all_expands_deposit_names(app):
    db = get_db()
    _insert_deposit(db, 'd1', 'Granite Deposit', tier='common')
    _insert_location(db, 'l1', 'Ship Graveyard', deposit_uuids=['d1', 'unknown-uuid'])

    rows = MiningLocation.list_all()

    assert len(rows) == 1
    deposits = rows[0]['groups'][0]['deposits']
    # 對得到的礦床要補上名稱/tier，對不到的（unknown-uuid）維持 None 而不是報錯
    assert deposits[0] == {
        'resource_uuid': 'd1', 'relative_probability': 0.5,
        'deposit_name': 'Granite Deposit', 'tier': 'common',
    }
    assert deposits[1]['deposit_name'] is None
    assert deposits[1]['tier'] is None


def test_mining_location_list_all_filters_is_current(app):
    db = get_db()
    _insert_location(db, 'l1', 'Current Spot')
    _insert_location(db, 'l2', 'Retired Spot', is_current=False)

    rows = MiningLocation.list_all()

    assert [r['_id'] for r in rows] == ['l1']


def test_mining_location_systems_distinct_and_sorted(app):
    db = get_db()
    _insert_location(db, 'l1', 'A', system='Stanton')
    _insert_location(db, 'l2', 'B', system='Pyro')
    _insert_location(db, 'l3', 'C', system='Stanton')
    _insert_location(db, 'l4', 'D', system=None, is_current=True)

    assert MiningLocation.systems() == ['Pyro', 'Stanton']


# ═══════════════════════════════════════════════════════════
#  view 層
# ═══════════════════════════════════════════════════════════

def test_deposits_requires_auth(client):
    assert client.get('/mining/deposits').status_code == 401


def test_locations_requires_auth(client):
    assert client.get('/mining/locations').status_code == 401


def test_list_deposits_returns_data(client, auth_headers):
    db = get_db()
    _insert_deposit(db, 'd1', 'Granite Deposit')

    resp = client.get('/mining/deposits', headers=auth_headers)
    body = resp.get_json()

    assert resp.status_code == 200
    assert body['success'] is True
    assert body['data'][0]['deposit_name'] == 'Granite Deposit'


def test_list_locations_returns_expanded_data(client, auth_headers):
    db = get_db()
    _insert_deposit(db, 'd1', 'Granite Deposit', tier='common')
    _insert_location(db, 'l1', 'Ship Graveyard', deposit_uuids=['d1'])

    resp = client.get('/mining/locations', headers=auth_headers)
    body = resp.get_json()

    assert resp.status_code == 200
    assert body['data'][0]['groups'][0]['deposits'][0]['deposit_name'] == 'Granite Deposit'


def test_list_systems_returns_distinct_systems(client, auth_headers):
    db = get_db()
    _insert_location(db, 'l1', 'A', system='Stanton')
    _insert_location(db, 'l2', 'B', system='Pyro')

    resp = client.get('/mining/systems', headers=auth_headers)
    body = resp.get_json()

    assert resp.status_code == 200
    assert body['data'] == ['Pyro', 'Stanton']
