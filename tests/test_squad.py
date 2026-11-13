"""戰術小隊分配表（/player/squads*，src/models/squad.py）。"""
import pytest

from src.mongo import get_db


def _register(client, scid, nickname):
    client.post('/player/register', json={'nickname': nickname, 'star_citizen_id': scid,
                                          'password': 'pw-123456'})
    login = client.post('/player/login', json={'star_citizen_id': scid, 'password': 'pw-123456'})
    return {'Authorization': f"Bearer {login.get_json()['token']}"}


@pytest.fixture
def ships():
    get_db()['vehicle_master'].insert_many([
        {'_id': 'v-perseus', 'name': 'RSI Perseus', 'crew_max': 6, 'is_spaceship': True},
        {'_id': 'v-cutlass', 'name': 'Cutlass Black', 'crew_max': 2, 'is_spaceship': True},
    ])


@pytest.fixture
def alice(client):
    return _register(client, 'AlicePilot', '愛麗絲')


@pytest.fixture
def bob(client):
    return _register(client, 'BobHauler', '鮑伯')


def _board(**extra):
    return {
        'title': '週六攻堅', 'event_at': '2026-11-21T20:00', 'note': '集合在 Orison',
        'squads': [{
            'id': 's1', 'name': 'Alpha', 'leader': 'm1',
            'ships': [{'id': 'v1', 'vehicle_id': 'v-perseus', 'label': '一號機', 'crew': [
                {'id': 'm1', 'scid': 'AlicePilot', 'name': '亂填的名字', 'role': '駕駛'},
                {'id': 'm2', 'scid': None, 'name': '路人甲', 'role': '砲手'},
            ]}],
            'members': [{'id': 'm3', 'scid': 'BobHauler', 'name': '', 'role': '陸戰'}],
        }],
        **extra,
    }


def _create(client, headers, body=None):
    res = client.post('/player/squads', headers=headers, json=body or {'title': '空白表'})
    assert res.status_code == 200, res.get_json()
    return res.get_json()['data']


def _save(client, headers, board_id, body, rev):
    return client.put(f'/player/squads/{board_id}', headers=headers, json={**body, 'rev': rev})


def test_requires_login(client):
    assert client.get('/player/squads').status_code == 401
    assert client.post('/player/squads', json={'title': 'x'}).status_code == 401


def test_create_save_read(client, ships, alice, bob):
    b = _create(client, alice)
    assert b['can_edit'] and b['rev'] == 1 and b['squads'] == []
    res = _save(client, alice, b['id'], _board(), 1)
    assert res.status_code == 200, res.get_json()
    data = res.get_json()['data']
    assert data['rev'] == 2
    sq = data['squads'][0]
    assert sq['leader'] == 'm1'
    ship = sq['ships'][0]
    assert ship['vehicle_name'] == 'RSI Perseus' and ship['crew_max'] == 6 and ship['label'] == '一號機'
    # 綁定玩家的名字用暱稱，不信任前端傳的
    assert [p['name'] for p in ship['crew']] == ['愛麗絲', '路人甲']
    assert [p['registered'] for p in ship['crew']] == [True, False]
    assert sq['members'][0]['name'] == '鮑伯'

    lst = client.get('/player/squads', headers=bob).get_json()['data']
    assert lst[0]['title'] == '週六攻堅'
    assert (lst[0]['squad_count'], lst[0]['ship_count'], lst[0]['people_count']) == (1, 1, 3)
    assert lst[0]['owner_name'] == '愛麗絲'

    other = client.get(f'/player/squads/{b["id"]}', headers=bob).get_json()['data']
    assert other['can_edit'] is False and other['share_token'] is None
    assert other['squads'][0]['ships'][0]['crew'][0]['name'] == '愛麗絲'


def test_only_owner_can_modify(client, ships, alice, bob):
    b = _create(client, alice)
    assert _save(client, bob, b['id'], _board(), 1).status_code == 403
    assert client.delete(f'/player/squads/{b["id"]}', headers=bob).status_code == 403
    assert client.post(f'/player/squads/{b["id"]}/share', headers=bob,
                       json={'enabled': True}).status_code == 403
    assert client.delete(f'/player/squads/{b["id"]}', headers=alice).status_code == 200
    assert client.get(f'/player/squads/{b["id"]}', headers=alice).status_code == 404


def test_rev_conflict(client, ships, alice, bob):
    b = _create(client, alice)
    assert _save(client, alice, b['id'], _board(), 1).status_code == 200
    res = _save(client, alice, b['id'], _board(title='舊視窗'), 1)
    assert res.status_code == 409


@pytest.mark.parametrize('mutate, message', [
    (lambda d: d.update(title=''), '名稱'),
    (lambda d: d.update(title='x' * 61), '名稱'),
    (lambda d: d.update(note='x' * 501), '備註'),
    (lambda d: d.update(event_at='明天'), '行動時間'),
    (lambda d: d['squads'][0]['ships'][0]['crew'].append({'scid': 'Nobody', 'role': ''}), '找不到玩家'),
    (lambda d: d['squads'][0]['ships'][0].update(vehicle_id='v-none'), '找不到艦船'),
    (lambda d: d['squads'][0]['members'].append({'scid': None, 'name': ''}), '人員名稱'),
    (lambda d: d['squads'][0]['members'].append({'name': 'x' * 41}), '人員名稱'),
    (lambda d: d.update(squads=[{'name': f'S{i}'} for i in range(21)]), '小隊最多'),
    (lambda d: d['squads'][0].update(ships=[{'vehicle_id': 'v-cutlass'}] * 31), '艘船'),
    (lambda d: d['squads'][0].update(members=[{'name': f'p{i}'} for i in range(301)]), '人員最多'),
])
def test_validation(client, ships, alice, bob, mutate, message):
    b = _create(client, alice)
    body = _board()
    mutate(body)
    res = _save(client, alice, b['id'], body, 1)
    assert res.status_code == 400
    assert message in res.get_json()['message']


def test_duplicate_ids_are_regenerated(client, ships, alice, bob):
    b = _create(client, alice)
    body = _board()
    body['squads'][0]['members'] = [{'id': 'm1', 'name': '重複 id'}, {'id': '<bad>', 'name': '壞 id'}]
    data = _save(client, alice, b['id'], body, 1).get_json()['data']
    ids = [p['id'] for p in data['squads'][0]['ships'][0]['crew']] + \
          [p['id'] for p in data['squads'][0]['members']]
    assert len(set(ids)) == len(ids) == 4


def test_copy(client, ships, alice, bob):
    b = _create(client, alice)
    _save(client, alice, b['id'], _board(), 1)
    client.post(f'/player/squads/{b["id"]}/share', headers=alice, json={'enabled': True})
    copy = _create(client, bob, {'copy_from': b['id']})
    assert copy['title'] == '週六攻堅（複本）'
    assert copy['owner_scid'] == 'BobHauler' and copy['can_edit']
    assert copy['share_token'] is None
    assert copy['squads'][0]['ships'][0]['vehicle_name'] == 'RSI Perseus'
    assert client.post('/player/squads', headers=bob,
                       json={'copy_from': 'ffffffffffffffffffffffff'}).status_code == 404


def test_share_and_public_view(client, ships, alice, bob):
    b = _create(client, alice)
    _save(client, alice, b['id'], _board(), 1)
    token = client.post(f'/player/squads/{b["id"]}/share', headers=alice,
                        json={'enabled': True}).get_json()['data']['share_token']
    assert len(token) >= 20

    res = client.get(f'/player/squads/shared/{token}')
    assert res.status_code == 200
    pub = res.get_json()['data']
    # 白名單：逐欄位比對，多了欄位就會失敗
    assert set(pub) == {'title', 'event_at', 'note', 'owner_name', 'updated_at', 'squads'}
    sq = pub['squads'][0]
    assert set(sq) == {'id', 'name', 'note', 'leader', 'ships', 'members'}
    ship = sq['ships'][0]
    assert set(ship) == {'id', 'vehicle_name', 'label', 'crew_max', 'crew'}
    for p in ship['crew'] + sq['members']:
        assert set(p) == {'id', 'name', 'role', 'registered'}
    assert pub['owner_name'] == '愛麗絲'
    assert ship['crew'][0]['name'] == '愛麗絲'

    # 重新產生：舊碼失效
    new = client.post(f'/player/squads/{b["id"]}/share', headers=alice,
                      json={'enabled': True, 'regenerate': True}).get_json()['data']['share_token']
    assert new != token
    assert client.get(f'/player/squads/shared/{token}').status_code == 404
    assert client.get(f'/player/squads/shared/{new}').status_code == 200
    # 關閉
    client.post(f'/player/squads/{b["id"]}/share', headers=alice, json={'enabled': False})
    assert client.get(f'/player/squads/shared/{new}').status_code == 404


def test_names_follow_player_changes(client, ships, alice, bob):
    b = _create(client, alice)
    _save(client, alice, b['id'], _board(), 1)
    get_db()['players'].update_one({'star_citizen_id': 'BobHauler'}, {'$set': {'nickname': '鮑伯改名'}})
    data = client.get(f'/player/squads/{b["id"]}', headers=alice).get_json()['data']
    assert data['squads'][0]['members'][0]['name'] == '鮑伯改名'
    # 玩家被移除：用存下來的名字，標成未註冊
    from datetime import datetime
    get_db()['players'].update_one({'star_citizen_id': 'BobHauler'},
                                   {'$set': {'deleted_at': datetime.utcnow()}})
    data = client.get(f'/player/squads/{b["id"]}', headers=alice).get_json()['data']
    m = data['squads'][0]['members'][0]
    assert m['name'] == '鮑伯' and m['registered'] is False


def test_board_limit_per_owner(client, alice, monkeypatch):
    import src.models.squad as squad
    monkeypatch.setattr(squad, 'MAX_BOARDS_PER_OWNER', 2)
    _create(client, alice)
    _create(client, alice)
    res = client.post('/player/squads', headers=alice, json={'title': '第三張'})
    assert res.status_code == 400
